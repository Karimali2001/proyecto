import json
import time
import collections
import cv2
import numpy as np
from pathlib import Path
from types import SimpleNamespace

from src.core.object_detection.byte_tracker import BYTETracker
from src.core.priority_queue import AudioPriorityQueue

base_path = Path.cwd()
translations_path = str(base_path / "assets" / "translations.json")

with open(translations_path, "r") as f:
    translations = json.load(f)


class ObjectDetector:
    def __init__(
        self, camera_driver, hailo_driver, audio_queue=None, video_w=1280, video_h=960
    ):
        self.camera_driver = camera_driver
        self.hailo_driver = hailo_driver
        self.audio_queue = audio_queue

        self.video_w = video_w
        self.video_h = video_h

        self.raw_detections = []

        # 1. Stabilization Filter (Last 5 frames)
        self.detection_history = collections.deque(maxlen=5)

        # 2. Initialize the Tracker (ByteTrack)
        tracker_args = SimpleNamespace(
            track_thresh=0.4, track_buffer=30, match_thresh=0.8, mot20=False
        )
        self.tracker = BYTETracker(tracker_args, frame_rate=15)

        # 3. Short-term memories for Vehicle Tracking
        self.vehicle_history = {}  # track_id -> deque of coordinates (x, y)
        self.vehicle_cooldown = {}  # track_id -> time of the last warning

        # 4. GLOBAL Memory for Traffic Lights (Avoids spam if ID is lost)
        self.global_tl_color = None
        self.global_tl_warn_time = 0.0

    def getLastDetection(self):
        """Returns objects that have appeared in at least 3 of the last 5 frames."""
        if len(self.detection_history) == 0:
            return []

        counter = collections.Counter()
        for frame_objects in self.detection_history:
            for obj in frame_objects:
                counter[obj] += 1

        # We require stability: must be in >= 3 frames
        threshold = 3 if len(self.detection_history) == 5 else 1
        stable_detections = [
            obj for obj, count in counter.items() if count >= threshold
        ]

        return stable_detections

    def getRawDetections(self):
        return self.raw_detections

    def setRawDetections(self, detections):
        self.raw_detections = detections

    def _get_traffic_light_color(self, frame, box):
        """Analyzes whether the traffic light is Red, Yellow, Green, or Off."""
        x1, y1, x2, y2 = map(int, box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return "error"

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # Color masks
        mask_red1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)

        mask_yellow = cv2.inRange(hsv, np.array([15, 50, 50]), np.array([35, 255, 255]))
        mask_green = cv2.inRange(hsv, np.array([40, 50, 50]), np.array([90, 255, 255]))

        # Count the bright pixels
        red_pixels = cv2.countNonZero(mask_red)
        yellow_pixels = cv2.countNonZero(mask_yellow)
        green_pixels = cv2.countNonZero(mask_green)

        # Find the dominant color
        colors = {"red": red_pixels, "yellow": yellow_pixels, "green": green_pixels}
        dominant_color = max(colors, key=colors.get)

        # 🔥 THE NEW RULE 🔥
        # If not even the dominant color can exceed 20 pixels,
        # it means the lamp is not emitting light (it is damaged or off).
        if colors[dominant_color] > 20:
            return dominant_color

        return "off"

    def _compute_iou(self, boxA, boxB):
        """Calculates the overlap index to map the Tracker ID to the YOLO Class."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0:
            return 0
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        return interArea / float(boxAArea + boxBArea - interArea)

    def process_frame(self, frame):
        try:
            detections = self.hailo_driver.infer(frame)
            detections = self.hailo_driver.extract_detections(
                detections, self.video_w, self.video_h
            )
            self.setRawDetections(detections)

            if len(detections) == 0:
                self.detection_history.append([])
                return

            # 1. Prepare YOLO boxes for ByteTrack: [x1, y1, x2, y2, score]
            dets_for_tracker = []
            for det in detections:
                name, bbox, score = det
                dets_for_tracker.append([bbox[0], bbox[1], bbox[2], bbox[3], score])

            dets_for_tracker = np.array(dets_for_tracker)

            # 2. Update the Tracker to give each object a unique ID
            online_targets = self.tracker.update(dets_for_tracker)

            current_frame_objects = []

            for track in online_targets:
                track_id = track.track_id
                x1, y1, x2, y2 = track.tlbr

                # 3. Pair the Tracker ID with the YOLO name using IoU
                best_iou = 0
                best_det = None
                for det in detections:
                    iou = self._compute_iou(track.tlbr, det[1])
                    if iou > best_iou:
                        best_iou = iou
                        best_det = det

                if not best_det:
                    continue

                name, bbox, score = best_det
                translated_name = translations.get(name, name)

                # Calculate the direction (Clock)
                x_center = (x1 + x2) / 2
                ratio = x_center / self.video_w
                hour = round(9 + (ratio * 6))
                if hour > 12:
                    hour -= 12

                # Add to the frame's list for the manual report of button 1
                current_frame_objects.append(f"{translated_name} a las {hour}")

                # ==========================================
                # AUTOMATIC LOGIC 1: TRAFFIC LIGHTS (GLOBAL MEMORY)
                # ==========================================
                if name == "traffic light" and self.audio_queue:
                    color = self._get_traffic_light_color(frame, track.tlbr)

                    if color != "error":
                        current_time = time.time()
                        time_since_last_warn = current_time - self.global_tl_warn_time

                        # Conditions to warn: Color change OR 3 minutes passed
                        if (
                            color != self.global_tl_color and time_since_last_warn > 3.0
                        ) or (time_since_last_warn > 180.0):
                            print(f"[ObjectDetector] Traffic light detected in {color}!")

                            # 🔥 Dynamic message based on status 🔥
                            if color == "off":
                                audio_message = f"Caution, traffic light at {hour} is off or damaged"
                            else:
                                audio_message = f"Traffic light at {hour} in {color}"

                            self.audio_queue.put(
                                AudioPriorityQueue.DANGEROUS_OBJECTS, audio_message
                            )

                            # Update the global memory
                            self.global_tl_color = color
                            self.global_tl_warn_time = current_time

                # ==========================================
                # AUTOMATIC LOGIC 2: MOVING VEHICLES
                # ==========================================
                if name in ["car", "bus", "motorcycle", "truck"] and self.audio_queue:
                    y_center = (y1 + y2) / 2

                    if track_id not in self.vehicle_history:
                        self.vehicle_history[track_id] = collections.deque(maxlen=10)

                    self.vehicle_history[track_id].append((x_center, y_center))

                    # If we have enough frames to evaluate movement
                    if len(self.vehicle_history[track_id]) >= 5:
                        old_x, old_y = self.vehicle_history[track_id][0]

                        # Calculate how many pixels it moved
                        dist = np.sqrt(
                            (x_center - old_x) ** 2 + (y_center - old_y) ** 2
                        )
                        last_warn = self.vehicle_cooldown.get(track_id, 0)

                        # If it moved more than 40 pixels and we haven't warned in the last 5 seconds
                        if dist > 40 and (time.time() - last_warn > 5.0):
                            print(
                                f"[ObjectDetector] Moving vehicle detected! ID: {track_id}"
                            )
                            self.audio_queue.put(
                                AudioPriorityQueue.DANGEROUS_OBJECTS,
                                f"Caution, moving {translated_name} at {hour}",
                            )
                            self.vehicle_cooldown[track_id] = time.time()

            # Save the objects in the stabilization history
            self.detection_history.append(current_frame_objects)

        except Exception as e:
            print(f"\n[Object Detection] Error: {e}")
            self.detection_history.append([])
            self.setRawDetections([])

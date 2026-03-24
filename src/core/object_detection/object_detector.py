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

        self.detection_history = collections.deque(maxlen=5)

        tracker_args = SimpleNamespace(
            track_thresh=0.4, track_buffer=30, match_thresh=0.8, mot20=False
        )
        self.tracker = BYTETracker(tracker_args, frame_rate=15)

        self.vehicle_history = {}
        self.vehicle_cooldown = {}
        self.global_tl_color = None
        self.global_tl_warn_time = 0.0

        # Seat Finder Memory
        self.seat_finder_mode = False
        self.seat_state = 0
        self.seat_last_seen = 0.0
        self.last_seat_beep = 0.0
        self.last_seat_ratio = 0.0  # NEW SIZE MEMORY

    def toggle_seat_finder(self):
        self.seat_finder_mode = not self.seat_finder_mode
        if self.seat_finder_mode:
            self.seat_state = 0
            self.seat_last_seen = time.time()
            self.last_seat_ratio = 0.0
        return self.seat_finder_mode

    def getLastDetection(self):
        if len(self.detection_history) == 0:
            return []
        counter = collections.Counter()
        for frame_objects in self.detection_history:
            for obj in frame_objects:
                counter[obj] += 1
        threshold = 3 if len(self.detection_history) == 5 else 1
        return [obj for obj, count in counter.items() if count >= threshold]

    def getRawDetections(self):
        return self.raw_detections

    def setRawDetections(self, detections):
        self.raw_detections = detections

    def _get_traffic_light_color(self, frame, box):
        x1, y1, x2, y2 = map(int, box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return "error"

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask_red1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        mask_yellow = cv2.inRange(hsv, np.array([15, 50, 50]), np.array([35, 255, 255]))
        mask_green = cv2.inRange(hsv, np.array([40, 50, 50]), np.array([90, 255, 255]))

        colors = {
            "rojo": cv2.countNonZero(mask_red),
            "amarillo": cv2.countNonZero(mask_yellow),
            "verde": cv2.countNonZero(mask_green),
        }
        dominant = max(colors, key=colors.get)
        if colors[dominant] > 20:
            return dominant
        return "apagado"

    def _compute_iou(self, boxA, boxB):
        xA, yA = max(boxA[0], boxB[0]), max(boxA[1], boxB[1])
        xB, yB = min(boxA[2], boxB[2]), min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0:
            return 0
        return interArea / float(
            ((boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
            + ((boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))
            - interArea
        )

    def process_frame(self, frame):
        try:
            detections = self.hailo_driver.extract_detections(
                self.hailo_driver.infer(frame), self.video_w, self.video_h
            )
            self.setRawDetections(detections)
            if len(detections) == 0:
                self.detection_history.append([])
                return

            dets_for_tracker = np.array(
                [[d[1][0], d[1][1], d[1][2], d[1][3], d[2]] for d in detections]
            )
            online_targets = self.tracker.update(dets_for_tracker)
            current_frame_objects = []

            for track in online_targets:
                best_iou, best_det = 0, None
                for det in detections:
                    iou = self._compute_iou(track.tlbr, det[1])
                    if iou > best_iou:
                        best_iou, best_det = iou, det
                if not best_det:
                    continue

                name, _, _ = best_det
                translated_name = translations.get(name, name)
                hour = round(
                    9 + (((track.tlbr[0] + track.tlbr[2]) / 2) / self.video_w * 6)
                )
                if hour > 12:
                    hour -= 12
                current_frame_objects.append(f"{translated_name} a las {hour}")

                # if name == "traffic light" and self.audio_queue:
                #     color = self._get_traffic_light_color(frame, track.tlbr)
                #     if color != "error":
                #         tslw = time.time() - self.global_tl_warn_time
                #         if (color != self.global_tl_color and tslw > 3.0) or (
                #             tslw > 180.0
                #         ):
                #             msg = (
                #                 f"Precaución, semáforo a las {hour} está apagado o dañado"
                #                 if color == "apagado"
                #                 else f"Semáforo a las {hour} en {color}"
                #             )
                #             self.audio_queue.put(
                #                 AudioPriorityQueue.DANGEROUS_OBJECTS, msg
                #             )
                #             self.global_tl_color, self.global_tl_warn_time = (
                #                 color,
                #                 time.time(),
                #             )

                # if (
                #     False
                #     and name in ["car", "bus", "motorcycle", "truck"]
                #     and self.audio_queue
                # ):
                #     y_c, x_c = (
                #         (track.tlbr[1] + track.tlbr[3]) / 2,
                #         (track.tlbr[0] + track.tlbr[2]) / 2,
                #     )
                #     if track.track_id not in self.vehicle_history:
                #         self.vehicle_history[track.track_id] = collections.deque(
                #             maxlen=10
                #         )
                #     self.vehicle_history[track.track_id].append((x_c, y_c))
                #     if len(self.vehicle_history[track.track_id]) >= 5:
                #         old_x, old_y = self.vehicle_history[track.track_id][0]
                #         if np.sqrt((x_c - old_x) ** 2 + (y_c - old_y) ** 2) > 40 and (
                #             time.time() - self.vehicle_cooldown.get(track.track_id, 0)
                #             > 5.0
                #         ):
                #             self.audio_queue.put(
                #                 AudioPriorityQueue.DANGEROUS_OBJECTS,
                #                 f"Precaución, {translated_name} en movimiento a las {hour}",
                #             )
                #             self.vehicle_cooldown[track.track_id] = time.time()

            # ==========================================
            # FINDER STATE MACHINE
            # ==========================================
            if self.seat_finder_mode and self.audio_queue:
                persons = [det[1] for det in detections if det[0] == "person"]
                seats = [det for det in detections if det[0] in ["chair", "couch"]]
                best_seat, max_area = None, 0

                for seat in seats:
                    s_box = seat[1]
                    is_occupied = False
                    for p_box in persons:
                        if self._compute_iou(s_box, p_box) > 0.05 or (
                            s_box[0] < (p_box[0] + p_box[2]) / 2 < s_box[2]
                            and s_box[1] < (p_box[1] + p_box[3]) / 2 < s_box[3]
                        ):
                            is_occupied = True
                            break
                    if not is_occupied:
                        area = (s_box[2] - s_box[0]) * (s_box[3] - s_box[1])
                        if area > max_area:
                            max_area, best_seat = area, seat

                current_time = time.time()

                if best_seat:
                    s_box = best_seat[1]
                    ratio = max_area / (self.video_w * self.video_h)
                    self.last_seat_ratio = ratio  # Save size memory

                    if ratio > 0.20:  # Direct arrival
                        self.audio_queue.put(
                            AudioPriorityQueue.OBJECT_DETECTION, "Llegaste a tu asiento"
                        )
                        self.toggle_seat_finder()
                    else:
                        if self.seat_state == 0:
                            self.seat_state = 1
                        self.seat_last_seen = current_time

                        x_c = (s_box[0] + s_box[2]) / 2
                        if x_c < self.video_w * 0.35:
                            pos = "left"
                        elif x_c > self.video_w * 0.65:
                            pos = "right"
                        else:
                            pos = "center"

                        interval = max(0.15, 1.0 - (ratio * 2.5))
                        if current_time - self.last_seat_beep > interval:
                            self.audio_queue.put(
                                AudioPriorityQueue.OBJECT_DETECTION,
                                {
                                    "action": "sound",
                                    "position": pos,
                                    "sound_type": "sonar",
                                },
                            )
                            self.last_seat_beep = current_time
                else:
                    if self.seat_state == 1 and (
                        current_time - self.seat_last_seen > 1.5
                    ):
                        # SMART ARRIVAL CHECK
                        # If we lost the chair but before it was big (>= 8% screen), sure user sat/turned
                        if self.last_seat_ratio > 0.08:
                            self.audio_queue.put(
                                AudioPriorityQueue.OBJECT_DETECTION,
                                "Llegaste a tu asiento",
                            )
                            self.toggle_seat_finder()
                        else:
                            self.audio_queue.put(
                                AudioPriorityQueue.OBJECT_DETECTION,
                                "Referencia perdida",
                            )
                            self.seat_state = 0

            self.detection_history.append(current_frame_objects)

        except Exception as e:
            print(f"\n[Object Detection] Error: {e}")
            self.detection_history.append([])
            self.setRawDetections([])

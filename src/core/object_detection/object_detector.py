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

    def _get_traffic_light_color(self, frame, box, track_id=0, score=0.0):
        x1, y1, x2, y2 = map(int, box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return "error"

        h, w, _ = crop.shape
        area = h * w

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # Red 1: 0-10, Red 2: 170-180, Yellow: 15-35, Green: 40-90 (con S y V altos para evitar sombras)
        mask_red1 = cv2.inRange(hsv, np.array([0, 70, 150]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(
            hsv, np.array([170, 70, 150]), np.array([180, 255, 255])
        )
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        mask_yellow = cv2.inRange(
            hsv, np.array([15, 50, 150]), np.array([35, 255, 255])
        )
        mask_green = cv2.inRange(hsv, np.array([40, 50, 150]), np.array([90, 255, 255]))

        colors = {
            "rojo": cv2.countNonZero(mask_red),
            "amarillo": cv2.countNonZero(mask_yellow),
            "verde": cv2.countNonZero(mask_green),
        }
        dominant = max(colors, key=colors.get)  # type: ignore

        # ==========================================
        # Save image for debug
        # ==========================================
        debug_dir = Path.cwd() / "debug_semaforos"
        debug_dir.mkdir(exist_ok=True)
        timestamp = int(time.time() * 1000)

        # The name includes track_id, confidence score, dominant color, and pixel count for that color
        filename = (
            debug_dir
            / f"tl_{timestamp}_id{track_id}_conf{score:.2f}_{dominant}_px{colors[dominant]}.jpg"
        )
        cv2.imwrite(str(filename), crop)

        # ==========================================
        # Proportional threshold: at least 50 pixels AND 5% of the box area must match the dominant color
        # ==========================================
        # This prevents false positives in small boxes (where 10 pixels might be enough) and ensures larger boxes have a more significant color presence.
        min_pixels = max(50, area * 0.05)

        if colors[dominant] > min_pixels:
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

                name, bbox, score = best_det
                translated_name = translations.get(name, name)
                hour = round(
                    9 + (((track.tlbr[0] + track.tlbr[2]) / 2) / self.video_w * 6)
                )
                if hour > 12:
                    hour -= 12
                current_frame_objects.append(f"{translated_name} a las {hour}")

                if name == "traffic light" and score > 0.70 and self.audio_queue:
                    # Pasamos el track_id y el score para que salgan en el nombre de la foto
                    color = self._get_traffic_light_color(
                        frame, track.tlbr, track.track_id, score
                    )

                    if color != "error":
                        tslw = time.time() - self.global_tl_warn_time
                        if (color != self.global_tl_color and tslw > 3.0) or (
                            tslw > 180.0
                        ):
                            msg = (
                                f"Precaución, semáforo a las {hour} está apagado"
                                if color == "apagado"
                                else f"Semáforo a las {hour} en {color}"
                            )
                            # Usamos la voz rápida en segundo plano para no interrumpir
                            self.audio_queue.play_concurrent(
                                {"action": "fast_voice", "text": msg}
                            )
                            self.global_tl_color, self.global_tl_warn_time = (
                                color,
                                time.time(),
                            )

                if name in ["car", "bus", "motorcycle", "truck"] and self.audio_queue:
                    # 1. Calculamos el ÁREA del vehículo, no su centro
                    w = track.tlbr[2] - track.tlbr[0]
                    h = track.tlbr[3] - track.tlbr[1]
                    area = w * h

                    if track.track_id not in self.vehicle_history:
                        self.vehicle_history[track.track_id] = collections.deque(
                            maxlen=10
                        )

                    # Guardamos el área en el historial
                    self.vehicle_history[track.track_id].append(area)

                    # 2. DETECCIÓN DE MOVIMIENTO REAL (EFECTO LOOMING)
                    if len(self.vehicle_history[track.track_id]) >= 5:
                        old_area = self.vehicle_history[track.track_id][0]

                        # Si el área creció un 15% o más en apenas 5 frames, viene directo hacia ti
                        # (O tú vas caminando muy rápido directo hacia él)
                        if old_area > 0 and (area / old_area) > 1.15:
                            # Cooldown de 4 segundos para emergencias
                            if (
                                time.time()
                                - self.vehicle_cooldown.get(track.track_id, 0)
                                > 4.0
                            ):
                                self.audio_queue.play_concurrent(
                                    {
                                        "action": "fast_voice",
                                        "text": f"Carro {translated_name}",
                                    }
                                )
                                self.vehicle_cooldown[track.track_id] = time.time()

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

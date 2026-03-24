import numpy as np
import cv2
import time
from src.core.priority_queue import AudioPriorityQueue


class AerialObstacleDetector:
    def __init__(
        self, hailo_driver, audio_queue, user_height_mm=1780, camera_height_mm=1220
    ):
        self.hailo_driver = hailo_driver
        self.audio_queue = audio_queue

        # Main switch
        self.is_active = False

        self.danger_streak = 0
        self.frame_counter = 0
        self.last_alarm_time = 0  # 10 seconds cooldown

        self.model_h, self.model_w, _ = self.hailo_driver.get_input_shape()

        # Threshold to detect close objects (calibrated for the street)
        self.proximity_threshold = 7000.0

        # Auto-calibrate the geometry for a single frame (Facial Protection)
        self._calibrate_geometry(user_height_mm, camera_height_mm)

    def _calibrate_geometry(self, user_height, camera_height):
        """Calculates the face box based on your real height."""
        horizon_y = (
            self.model_h // 2
        )  # 128 (The vertical center of the lens, camera height)
        center_x = self.model_w // 2  # 160 (The horizontal center of the lens)
        scale_factor = 0.15

        # Distance from the camera to the top of the head
        head_mm = user_height - camera_height
        if head_mm < 0:
            head_mm = 200  # Failsafe

        head_pixels = int(head_mm * scale_factor)

        # We center the box horizontally
        self.rect_width = 80
        self.rect_x = center_x - (self.rect_width // 2)

        # The box grows from the horizon (your chest) upwards, until covering your head
        self.rect_y = max(0, horizon_y - head_pixels)

        # The height of the box will be exactly the calculated distance in pixels
        self.rect_height = head_pixels

        # print("\n====================================")
        # print(f"AUTO-CALIBRATED RADAR (OUTDOORS MODE) 🔧")
        # print(f"User: {user_height}mm | Camera: {camera_height}mm")
        # print(
        #     f"Protection Zone: Y={self.rect_y} to {self.rect_y + self.rect_height}"
        # )
        # print("====================================\n")

    def toggle_radar(self):
        """Turns the aerial radar on or off."""
        self.is_active = not self.is_active
        state = "ACTIVATED" if self.is_active else "DEACTIVATED"
        print(f"📡 [Aerial Radar] System {state}")
        return self.is_active

    def check_yolo_overlap(self, yolo_detections, video_w=1280, video_h=960):
        """Checks if any person or known object is INSIDE OR TOUCHING the danger box."""
        if not yolo_detections:
            return False

        safe_objects = [
            "person",
            "car",
            "truck",
            "bus",
            "motorcycle",
            "bicycle",
            "train",
            "horse",
            "cow",
            "dog",
            "cat",
            "refrigerator",
            "tv",
            "microwave",
            "oven",
        ]

        for det in yolo_detections:
            name, bbox, score = det
            if name not in safe_objects:
                continue

            x0, y0, x1, y1 = bbox
            x0_radar = x0 * (self.model_w / video_w)
            x1_radar = x1 * (self.model_w / video_w)
            y0_radar = y0 * (self.model_h / video_h)
            y1_radar = y1 * (self.model_h / video_h)

            # Does the YOLO box touch our radar box?
            touches_x = (x0_radar < (self.rect_x + self.rect_width)) and (
                x1_radar > self.rect_x
            )
            touches_y = (y0_radar < (self.rect_y + self.rect_height)) and (
                y1_radar > self.rect_y
            )

            if touches_x and touches_y:
                # print(
                #     f"[Aerial Radar] Ignoring obstacle: It's a '{name}' TOUCHING the box."
                # )
                return True

        return False

    def process_frame(self, frame, yolo_detections=[]):
        if not self.is_active:
            return False, 0.0

        self.frame_counter += 1
        if self.frame_counter % 3 != 0:
            return False, 0.0

        # 1. Infer Depth
        frame_resized = cv2.resize(frame, (self.model_w, self.model_h))
        raw_output = self.hailo_driver.infer(frame_resized)
        depth_array = self.hailo_driver.extract_depth_map(raw_output)

        if depth_array is None:
            return False, 0.0

        # 2. Extract tunnel (Only one for now)
        high_tunnel = depth_array[
            self.rect_y : self.rect_y + self.rect_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        # 3. Calculate Blockage
        high_blockage = (
            np.sum(high_tunnel > self.proximity_threshold) / high_tunnel.size
        ) * 100
        has_danger = high_blockage > 15.0

        # 4. SMART FILTER (YOLO)
        if has_danger:
            is_ignored_object = self.check_yolo_overlap(yolo_detections)
            if is_ignored_object:
                has_danger = False  # Cancel the alarm

        # print(f"[Radar] Facial Protection: {high_blockage:.1f}% | Alarm: {has_danger}")

        # 5. Hysteresis
        if has_danger:
            self.danger_streak += 1
        else:
            self.danger_streak = 0

        confirmed_danger = self.danger_streak >= 3

        # 6. TRIGGER ALARM AND PHOTO
        if confirmed_danger:
            current_time = time.time()
            if current_time - self.last_alarm_time >= 10.0:
                # print("SPATIAL BEEP! AERIAL DANGER CONFIRMED 🚨")

                cmd = {
                    "action": "sound",
                    "position": "center",
                    "sound_type": "aerial",
                }

                self.audio_queue.play_concurrent(cmd)
                self.last_alarm_time = current_time

                # Save evidence
                debug_img = frame_resized.copy()
                cv2.rectangle(
                    debug_img,
                    (self.rect_x, self.rect_y),
                    (self.rect_x + self.rect_width, self.rect_y + self.rect_height),
                    (0, 0, 255),
                    2,
                )
                cv2.imwrite("smart_aerial_danger.jpg", debug_img)

            self.danger_streak = 0

        return confirmed_danger, high_blockage

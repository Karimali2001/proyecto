import numpy as np
import cv2
import time
from pathlib import Path


class AerialObstacleDetector:
    def __init__(
        self, hailo_driver, audio_queue, user_height_mm=1780, camera_height_mm=1220
    ):
        self.hailo_driver = hailo_driver
        self.audio_queue = audio_queue

        # Main switch
        self.is_active = False
        self.frame_counter = 0

        # --- STATE VARIABLES (Anti-Spam) ---
        self.danger_streak = 0
        self.clear_streak = 0
        self.is_currently_blocked = False
        self.last_alarm_time = 0.0

        # --- NEW: HEADING MEMORY (IMU) ---
        self.last_obstacle_heading = None

        self.model_h, self.model_w, _ = self.hailo_driver.get_input_shape()
        self.proximity_threshold = 8000.0
        self._calibrate_geometry(user_height_mm, camera_height_mm)

    def _calibrate_geometry(self, user_height, camera_height):
        y_offset = 30
        horizon_y = (self.model_h // 2) + y_offset
        center_x = self.model_w // 2
        scale_factor = 0.15

        head_mm = user_height - camera_height
        if head_mm < 0:
            head_mm = 200

        head_pixels = int(head_mm * scale_factor)

        self.rect_width = 80
        self.rect_x = center_x - (self.rect_width // 2)
        self.rect_y = max(0, horizon_y - head_pixels)
        self.rect_height = head_pixels

    def toggle_radar(self):
        self.is_active = not self.is_active
        state = "ACTIVATED" if self.is_active else "DEACTIVATED"
        print(f"📡 [Aerial Radar] System {state}")
        return self.is_active

    def check_yolo_overlap(self, yolo_detections, video_w=1280, video_h=960):
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

            touches_x = (x0_radar < (self.rect_x + self.rect_width)) and (
                x1_radar > self.rect_x
            )
            touches_y = (y0_radar < (self.rect_y + self.rect_height)) and (
                y1_radar > self.rect_y
            )

            if touches_x and touches_y:
                return True
        return False

    def process_frame(self, frame, yolo_detections=[], current_heading=None):
        """
        NEW: Receives 'current_heading' from IMU to detect if the user turned.
        """
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

        # 2. Extract tunnel
        high_tunnel = depth_array[
            self.rect_y : self.rect_y + self.rect_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        # 3. Calculate Blockage (Adjusted to 25% to avoid ghosts)
        high_blockage = (
            np.sum(high_tunnel > self.proximity_threshold) / high_tunnel.size
        ) * 100
        has_danger = high_blockage > 25.0

        # 4. SMART FILTER (YOLO)
        if has_danger and self.check_yolo_overlap(yolo_detections):
            has_danger = False

        # ==========================================
        # 5. TURN DETECTION (Immediate Reset)
        # ==========================================
        # If we were muted looking at a wall, and IMU tells us you turned...
        if (
            current_heading is not None
            and self.is_currently_blocked
            and self.last_obstacle_heading is not None
        ):
            # Calculate exact angular difference (handles 360 to 0 wrap)
            diff = (current_heading - self.last_obstacle_heading + 180) % 360 - 180

            # If you turned more than 45 degrees left or right:
            if abs(diff) > 45.0:
                self.is_currently_blocked = False
                self.last_alarm_time = 0.0  # Reset clock to beep IMMEDIATELY
                self.danger_streak = 0
                self.clear_streak = 0

        # ==========================================
        # 6. STATE MACHINE
        # ==========================================
        if has_danger:
            self.danger_streak += 1
            self.clear_streak = 0
        else:
            self.clear_streak += 1
            self.danger_streak = 0

        # If the path is clear for 15 frames (enough time to be sure), unblock
        if self.clear_streak >= 15:
            self.is_currently_blocked = False

        confirmed_danger = self.danger_streak >= 3

        # ==========================================
        # 7. TRIGGER ALARM AND PHOTO
        # ==========================================
        current_time = time.time()

        # General cooldown increased to 6.0 seconds (ignored if you turn, thanks to step 5)
        if (
            confirmed_danger
            and not self.is_currently_blocked
            and (current_time - self.last_alarm_time >= 6.0)
        ):
            # Trigger the sound
            cmd = {"action": "sound", "position": "center", "sound_type": "aerial"}
            self.audio_queue.play_concurrent(cmd)

            # BLOCK THE STATE FOR THIS OBSTACLE
            self.is_currently_blocked = True
            self.last_alarm_time = current_time

            # Save WHERE you were looking when it beeped
            if current_heading is not None:
                self.last_obstacle_heading = current_heading

            # --- DEBUG SAVE ---
            debug_dir = Path.cwd() / "debug_radar"
            debug_dir.mkdir(exist_ok=True)
            timestamp = int(current_time * 1000)

            debug_img = frame_resized.copy()
            cv2.rectangle(
                debug_img,
                (self.rect_x, self.rect_y),
                (self.rect_x + self.rect_width, self.rect_y + self.rect_height),
                (0, 0, 255),
                2,
            )

            # Corrected heatmap without "None" error
            depth_norm = np.zeros_like(depth_array, dtype=np.uint8)
            cv2.normalize(depth_array, depth_norm, 0, 255, cv2.NORM_MINMAX)
            depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

            cv2.rectangle(
                depth_color,
                (self.rect_x, self.rect_y),
                (self.rect_x + self.rect_width, self.rect_y + self.rect_height),
                (255, 255, 255),
                2,
            )

            base_filename = (
                debug_dir
                / f"radar_{timestamp}_blockage{high_blockage:.1f}_thresh{self.proximity_threshold}"
            )
            cv2.imwrite(str(base_filename) + "_rgb.jpg", debug_img)
            cv2.imwrite(str(base_filename) + "_depth.jpg", depth_color)

        # Prevent memory overflows
        if self.danger_streak > 30:
            self.danger_streak = 15
        if self.clear_streak > 30:
            self.clear_streak = 15

        return confirmed_danger, high_blockage

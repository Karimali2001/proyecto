import numpy as np
import time
from pathlib import Path
import cv2


class HoleDetector:
    def __init__(
        self, hailo_driver, audio_queue, user_height_mm=1780, camera_height_mm=1220
    ):
        self.hailo_driver = hailo_driver
        self.audio_queue = audio_queue

        # Main switch (Off by default, as requested)
        self.is_active = False

        # Anti-Spam state variables
        self.danger_streak = 0
        self.clear_streak = 0
        self.is_currently_blocked = False
        self.last_alarm_time = 0.0

        # Memory for the IMU to reset alarm if user turns
        self.last_hole_heading = None

        if self.hailo_driver:
            self.model_h, self.model_w, _ = self.hailo_driver.get_input_shape()
            self._calibrate_geometry(user_height_mm, camera_height_mm)
        else:
            print("[HoleDetector] Warning: Hailo driver not provided.")

    def _calibrate_geometry(self, user_height, camera_height):
        """
        Calibrates the rectangles to look towards the GROUND.
        We need two zones: One at your feet (reference) and another further ahead (exam).
        """
        # The depth image is 320x256
        center_x = self.model_w // 2

        # The width of our scan zone
        self.rect_width = 120
        self.rect_x = center_x - (self.rect_width // 2)

        # 1. REFERENCE ZONE (Right in front of your feet, lowest part of the image)
        self.ref_y = 220
        self.ref_height = 36  # Until the bottom (256)

        # 2. EXAM ZONE (The ground that is one or two steps ahead)
        self.exam_y = 150
        self.exam_height = 50

    def toggle_radar(self):
        """Turns the hole detection radar on or off."""
        self.is_active = not self.is_active
        state = "ACTIVATED" if self.is_active else "DEACTIVATED"
        print(f"📡 [Hole Radar] System {state}")
        return self.is_active

    def process_frame(self, frame_resized, depth_array, current_heading=None):
        """
        Analyzes the frame looking for unevenness or holes by comparing the reference ground
        with the ground ahead.
        """
        if not self.is_active or depth_array is None:
            return False

        # 2. Extract the two ground zones
        reference_ground = depth_array[
            self.ref_y : self.ref_y + self.ref_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        exam_zone = depth_array[
            self.exam_y : self.exam_y + self.exam_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        # 3. Gradient Logic (The Hole)
        # Calculate the average depth at the feet
        feet_average = np.mean(reference_ground)

        # Define the "void" threshold. If a pixel ahead is MUCH lighter (farther)
        # than the average at your feet, it's a hole.
        # Adjust '80.0' according to your video tests.
        hole_threshold = feet_average + 80.0

        # How many pixels in the exam zone exceed that critical threshold?
        danger_pixels = np.sum(exam_zone > hole_threshold)
        hole_percentage = (danger_pixels / exam_zone.size) * 100

        # If more than 20% of the exam zone is "void", there is a real hole
        has_danger = hole_percentage > 20.0

        # ==========================================
        # 4. TURN DETECTION (Immediate Reset via IMU)
        # ==========================================
        if (
            current_heading is not None
            and self.is_currently_blocked
            and self.last_hole_heading is not None
        ):
            diff = (current_heading - self.last_hole_heading + 180) % 360 - 180
            if abs(diff) > 45.0:
                self.is_currently_blocked = False
                self.last_alarm_time = 0.0
                self.danger_streak = 0
                self.clear_streak = 0

        # ==========================================
        # 5. STATE MACHINE (Anti-Spam)
        # ==========================================
        if has_danger:
            self.danger_streak += 1
            self.clear_streak = 0
        else:
            self.clear_streak += 1
            self.danger_streak = 0

        if self.clear_streak >= 15:
            self.is_currently_blocked = False

        confirmed_danger = self.danger_streak >= 3

        # ==========================================
        # 6. ALARM TRIGGER
        # ==========================================
        current_time = time.time()

        if (
            confirmed_danger
            and not self.is_currently_blocked
            and (current_time - self.last_alarm_time >= 5.0)
        ):
            # Play the sound
            cmd = {"action": "sound", "position": "center", "sound_type": "hole"}
            self.audio_queue.play_concurrent(cmd)

            self.is_currently_blocked = True
            self.last_alarm_time = current_time

            if current_heading is not None:
                self.last_hole_heading = current_heading

            # --- DEBUG SAVE ---
            debug_dir = Path.cwd() / "debug_holes"
            debug_dir.mkdir(exist_ok=True)
            timestamp = int(current_time * 1000)

            # Color map to see the hole
            depth_norm = np.zeros_like(depth_array, dtype=np.uint8)
            cv2.normalize(depth_array, depth_norm, 0, 255, cv2.NORM_MINMAX)
            depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

            # Draw rectangles: Green (Reference), Red (Exam)
            cv2.rectangle(
                depth_color,
                (self.rect_x, self.ref_y),
                (self.rect_x + self.rect_width, self.ref_y + self.ref_height),
                (0, 255, 0),
                2,
            )
            cv2.rectangle(
                depth_color,
                (self.rect_x, self.exam_y),
                (self.rect_x + self.rect_width, self.exam_y + self.exam_height),
                (0, 0, 255),
                2,
            )

            filename = (
                debug_dir
                / f"hole_{timestamp}_perc{hole_percentage:.1f}_ref{feet_average:.1f}.jpg"
            )
            cv2.imwrite(str(filename), depth_color)

        if self.danger_streak > 30:
            self.danger_streak = 15
        if self.clear_streak > 30:
            self.clear_streak = 15

        return confirmed_danger

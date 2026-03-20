import time
import numpy as np
import json


from src.drivers.tof_driver import Tof
from src.core.priority_queue import AudioPriorityQueue


class HoleDetector:
    def __init__(self, audio_queue, sensor_height_mm=1220, ignore_tof=False):
        self.ignore_tof = ignore_tof
        self.tof = Tof(sensor_height_mm=sensor_height_mm) if not ignore_tof else None
        self.audio_queue = audio_queue
        self.floor_matrix = None
        self.is_calibrating = False
        self.is_active = False  # Disabled by default
        if not ignore_tof:
            self.recalibrate_sensor()

    def toggle_radar(self):
        """Turns the ToF (hole detection) radar on or off."""
        self.is_active = not self.is_active
        state = "ACTIVATED" if self.is_active else "DEACTIVATED"
        print(f"📡 [ToF Radar] System {state}")
        return self.is_active

    def recalibrate_sensor(self):
        self.is_calibrating = True
        time.sleep(0.1)
        if self.tof:
            self.floor_matrix = self.tof.get_stable_matrix()
        self.is_calibrating = False
        self.is_active = True  # Automatically activated when calibrated

    def detect_hole(self, matrix_cm):
        """
        Analyzes the lower rows (pointing at the feet) looking for drops/holes.
        Filters noise by requiring at least 2 pixels to confirm the hole.
        """
        ground_zone = matrix_cm[5:8, :]

        # Increased to -15cm to ignore normal floor unevenness or sensor noise
        danger_threshold_cm = -15.0

        left_zone = ground_zone[:, 0:3]
        center_zone = ground_zone[:, 3:5]
        right_zone = ground_zone[:, 5:8]

        # Instead of np.min() (which is scared by 1 single bad pixel),
        # we count HOW MANY pixels are seeing the hole in each zone.
        holes_left = np.sum(left_zone <= danger_threshold_cm)
        holes_center = np.sum(center_zone <= danger_threshold_cm)
        holes_right = np.sum(right_zone <= danger_threshold_cm)

        has_hole = False
        positions = []

        # We only trigger the alarm if at least 2 pixels confirm the danger
        if holes_left >= 2:
            has_hole = True
            positions.append("izquierda")

        if holes_center >= 2:
            has_hole = True
            positions.append("centro")

        if holes_right >= 2:
            has_hole = True
            positions.append("derecha")

        if not has_hole:
            return False, ""

        if len(positions) == 3:
            return True, "frente completo"

        return True, ", ".join(positions)

    def detect_hole_thread(self):
        if self.ignore_tof:
            return

        try:
            detected = False
            H = self.tof.sensor_height_mm

            while True:
                if not self.is_active or self.is_calibrating:
                    time.sleep(0.1)
                    continue

                # 1. We get the raw millimeters
                current_matrix = self.tof.get_matrix()

                if current_matrix is not None:
                    # 2. APPLY MATHEMATICAL MAGIC
                    height_matrix = np.zeros((8, 8))
                    valid_mask = (self.floor_matrix > 0) & (current_matrix > 0)

                    height_matrix[valid_mask] = H * (
                        1.0
                        - (current_matrix[valid_mask] / self.floor_matrix[valid_mask])
                    )

                    # 3. We convert it to Real Centimeters (which is what the function expects)
                    matrix_cm = np.round(height_matrix / 10.0, 1)

                    # 4. Now yes, we pass the centimeter matrix to the detection
                    is_hole, pos_hole = self.detect_hole(matrix_cm)

                    if is_hole and not detected:
                        sound_position = "center"
                        if "izquierda" in pos_hole:
                            sound_position = "left"
                        elif "derecha" in pos_hole:
                            sound_position = "right"

                        cmd = json.dumps(
                            {
                                "position": sound_position,
                                "frequencyCenter": 400,
                                "frequencySide": 300,
                            }
                        )

                        self.audio_queue.put(
                            AudioPriorityQueue.HOLE_DETECTION,
                            cmd,
                        )
                        time.sleep(4)
                        detected = True
                    elif not is_hole:
                        detected = False

                time.sleep(0.005)
        except Exception as e:
            print(f"[Tof] Error: {e}")

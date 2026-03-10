import time


from src.drivers.tof_driver import Tof
from src.core.priority_queue import AudioPriorityQueue


class ObstacleDetector:
    def __init__(self, audio_queue):
        self.tof = Tof()
        self.audio_queue = audio_queue

    def detect_hole(self, matrix):
        """
        Analyzes the top rows (0 and 1) to detect sudden drops.
        Returns (Boolean, Position)
        """

        # 1. Filter out zeros (errors/infinite) to calculate the normal floor
        valid_readings = [dist for row in matrix[0:2] for dist in row if dist > 0]

        if not valid_readings:
            return True, "frente completo"

        current_distance = sum(valid_readings) / len(valid_readings)

        # 2. Compare against autocalibrated baseline and variability
        difference = current_distance - self.tof.baseline_floor

        # 3. Detection logic: Trigger only if drop exceeds the sensor's calculated noise/variability plus 30cm
        dynamic_threshold = (
            self.tof.variability + 300
        )  # Baseline jitter + 30cm actual drop

        if difference > dynamic_threshold:
            print(
                f"[Tof] Detected a drop! Current: {current_distance:.1f}mm, Baseline: {self.tof.baseline_floor:.1f}mm, Difference: {difference:.1f}mm"
            )

            print("[Tof] Matrix: ", matrix)
            # HOLE! Combine pixels from Row 0 and Row 1 for greater precision
            left_pixels = list(matrix[0][0:3]) + list(matrix[1][0:3])
            center_pixels = list(matrix[0][3:5]) + list(matrix[1][3:5])
            right_pixels = list(matrix[0][5:8]) + list(matrix[1][5:8])

            # Treat zeros as infinite (e.g., 4000mm) for hole calculation
            left_pixels = [4000 if v == 0 else v for v in left_pixels]
            center_pixels = [4000 if v == 0 else v for v in center_pixels]
            right_pixels = [4000 if v == 0 else v for v in right_pixels]

            avg_left = sum(left_pixels) / len(left_pixels)
            avg_center = sum(center_pixels) / len(center_pixels)
            avg_right = sum(right_pixels) / len(right_pixels)

            danger_threshold = self.tof.baseline_floor + dynamic_threshold

            # Check if ALL zones exceeded the threshold (Total drop)
            if (
                avg_left > danger_threshold
                and avg_center > danger_threshold
                and avg_right > danger_threshold
            ):
                return True, "frente completo (caída total)"

            # Find the deepest zone
            zones = {"izquierda": avg_left, "medio": avg_center, "derecha": avg_right}
            dangerous_zones = {k: v for k, v in zones.items() if v > danger_threshold}

            if dangerous_zones:
                position = max(dangerous_zones, key=dangerous_zones.get)  # type: ignore
                return True, position

        return False, ""

    def detect_hole_thread(self):
        try:
            detected = False

            while True:
                matrix = self.tof.get_matrix()

                if matrix is not None:
                    """
                    *************************
                    Hole
                    *************************
                    """
                    is_hole, pos_hole = self.detect_hole(matrix)

                    if is_hole and not detected:
                        sound_position = "center"
                        if "izquierda" in pos_hole:
                            sound_position = "left"
                        elif "derecha" in pos_hole:
                            sound_position = "right"

                        # Dump as JSON String
                        # Uses lower frequencies for holes vs higher frequencies for obstacles
                        import json

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

    def detect_air_obstacle(self, matrix):
        """
        Checks the upper rows (for the sensor facing upwards/forward).
        If the distance is less than 1500mm (1.5 meters), it triggers an alert.
        """

        left_danger = False
        center_danger = False
        right_danger = False

        # Check first 3 rows
        for row in range(3):
            for col in range(8):
                distance = matrix[row, col]

                # 0 is an error/infinite or the object is less than 1500mm
                if 0 < distance < 1000:
                    if col <= 2:
                        left_danger = True
                    elif col >= 5:
                        right_danger = True
                    else:
                        center_danger = True

        # boolean logic

        if not (left_danger or center_danger or right_danger):
            return False, ""

        if left_danger and center_danger and right_danger:
            return True, "pared"

        elif left_danger and right_danger and not center_danger:
            return True, "ambos lados"

        elif left_danger and center_danger:
            return True, "frente e izquierda"

        elif right_danger and center_danger:
            return True, "frente y derecha"

        elif center_danger:
            return True, "frente"

        elif left_danger:
            return True, "izquierda"

        elif right_danger:
            return True, "derecha"

        return False, ""

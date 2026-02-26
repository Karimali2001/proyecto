#!/usr/bin/env python
# -------------------------------------------------------------------------------
# qwiic_vl53l5cx_ex1_distance_array.py
#
# This example shows how to read all 64 distance readings at once.
# -------------------------------------------------------------------------------
# Written by SparkFun Electronics, November 2024
#
# This python library supports the SparkFun Electroncis Qwiic ecosystem
#
# More information on Qwiic is at https://www.sparkfun.com/qwiic
#
# Do you like this library? Help support SparkFun. Buy a board!
# ===============================================================================
# Copyright (c) 2024 SparkFun Electronics
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ===============================================================================

import qwiic_vl53l5cx
import time
import numpy as np
import math

from .audio_output_driver import AudioOutputDriver


audio = AudioOutputDriver()


class TofDriver:
    def __init__(self, baseline_floor=14000, angle_grad=45):
        """
        baseline_floor: Distance in millimeters from the sensor to the floor.
        angle_grad: Angle in degrees from the sensor to the floor.
        """
        print("[Tof] Initializing Tof")

        # Create instance of device
        self.sensor = qwiic_vl53l5cx.QwiicVL53L5CX()

        # Check if it's connected
        if not self.sensor.is_connected():
            raise RuntimeError(
                "[Tof] The device isn't connected to the system. Please check your connection"
            )

        # Initialize the device
        print("Initializing sensor board. This can take up to 10s. Please wait.")
        if not self.sensor.begin():
            raise RuntimeError("[Tof] Sensor initialization unsuccessful.")

        audio.speak("Sensor de distancia inicializado")

        self.sensor.set_resolution(8 * 8)  # enable all 64 pads
        # image_resolution = self.sensor.get_resolution()  # Query sensor for current resolution - either 4x4 or 8x8

        # image_width = int(sqrt(image_resolution)) # Calculate printing width
        self.sensor.start_ranging()

        # distance of the sensor to the ground
        angle_rad = math.radians(angle_grad)

        hip = baseline_floor / math.cos(angle_rad)

        self.baseline_floor = hip

        print("[ToF] Sensor listo y capturando datos.")

    def get_matrix(self):
        """Devuelve una matriz 2D (8x8) con las distancias en milímetros."""

        sensor = self.sensor

        if sensor.check_data_ready():
            measurement_data = sensor.get_ranging_data()
            flat_array = measurement_data.distance_mm

            # Transform list to array 8x8
            matrix = np.array(flat_array).reshape((8, 8))

            return matrix

        return None

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

        # 2. Initialize the baseline if it's the first time
        if self.baseline_floor is None:
            self.baseline_floor = current_distance
            return False, ""

        # 3. Detection logic: If the general distance jumps more than 30cm
        difference = current_distance - self.baseline_floor

        if difference > 300:
            print(
                f"[Tof] Detected a drop! Current: {current_distance:.1f}mm, Baseline: {self.baseline_floor:.1f}mm, Difference: {difference:.1f}mm"
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

            danger_threshold = self.baseline_floor + 300

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
                position = max(dangerous_zones, key=dangerous_zones.get)
                return True, position

        # 4. Smoothly update the baseline if everything is normal
        # self.baseline_floor = (self.baseline_floor * 0.9) + (current_distance * 0.1)
        return False, ""

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
                if 0 < distance < 1500:
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


if __name__ == "__main__":
    try:
        tof = TofDriver()

        detected = False

        while True:
            matrix = tof.get_matrix()
            if matrix is not None:
                """
                *************************
                Hole
                *************************
                """
                is_hole, pos_hole = tof.detect_hole(matrix)

                if is_hole and not detected:
                    detected = True
                    print("[Main]: Hole detected at position:", pos_hole)

                    audio.speak("¡Cuidado! Hay un agujero: " + pos_hole)

                    time.sleep(2)
                elif not is_hole:
                    detected = False

                """
                *************************
                Air obstacle
                *************************
                """

                # isAirObstacle, pos_air = tof.detect_air_obstacle(matrix)

                # if isAirObstacle and not detected:
                #     detected = True
                #     print("[Main]: Air obstacle detected")
                #     time.sleep(2)
                # elif not isAirObstacle:
                #     detected = False

            time.sleep(0.005)
    except KeyboardInterrupt:
        print("[Tof]: Program stopped")
    except Exception as e:
        print(f"[Tof] Error: {e}")

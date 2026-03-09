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

from src.drivers.audio_driver import Audio


audio = Audio()


class Tof:
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

        # audio.speak("Sensor de distancia inicializado")

        print("[Tof] Initialized sensor")

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


if __name__ == "__main__":
    try:
        tof = Tof()

        detected = False

        while True:
            matrix = tof.get_matrix()
            if matrix is not None:
                print(matrix)

            time.sleep(0.005)
    except KeyboardInterrupt:
        print("[Tof]: Program stopped")
    except Exception as e:
        print(f"[Tof] Error: {e}")

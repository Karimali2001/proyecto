#!/usr/bin/env python
import qwiic_vl53l5cx
import time
import numpy as np
import warnings


class Tof:
    def __init__(self, sensor_height_mm=1220):
        print("[Tof] Initializing Tof in 8x8 mode (Safe)...")
        self.sensor = qwiic_vl53l5cx.QwiicVL53L5CX()

        self.sensor_height_mm = sensor_height_mm

        if not self.sensor.is_connected():
            raise RuntimeError("[Tof] Device is not connected.")

        print("Starting VL53L5CX sensor...")
        if not self.sensor.begin():
            raise RuntimeError("[Tof] Initialization failed.")

        # We return to the 8x8 configuration that we know works perfectly
        self.sensor.set_resolution(self.sensor.kResolution8x8)
        self.sensor.set_target_order(self.sensor.kTargetOrderClosest)
        self.sensor.set_ranging_frequency_hz(5)
        self.sensor.set_integration_time_ms(150)
        self.sensor.set_sharpener_percent(50)

        self.sensor.start_ranging()

    def get_matrix(self):
        if self.sensor.check_data_ready():
            measurement_data = self.sensor.get_ranging_data()

            # We extract the 64 values
            flat_distance = measurement_data.distance_mm
            flat_status = measurement_data.target_status

            dist_matrix = np.array(flat_distance).reshape((8, 8))
            status_matrix = np.array(flat_status).reshape((8, 8))

            mask = np.isin(status_matrix, [5, 9])
            return np.where(mask, dist_matrix, 0)
        return None

    def get_stable_matrix(self, frames=15):
        samples = []
        for _ in range(frames):
            matrix = None
            while matrix is None:
                matrix = self.get_matrix()
                time.sleep(0.01)
            samples.append(matrix)
            time.sleep(0.05)

        stack = np.array(samples, dtype=float)
        stack[stack == 0] = np.nan

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            stable = np.nanmedian(stack, axis=0)

        return np.nan_to_num(stable, nan=0.0)


if __name__ == "__main__":
    try:
        tof = Tof(sensor_height_mm=770)

        print("\n" + "=" * 50)
        print("EXACT HEIGHT DETECTION SYSTEM (8x8)")
        print("=" * 50 + "\n")

        while True:
            # STEP 1
            input("1. Make sure THERE IS NOTHING (only empty floor) and press ENTER...")
            print("Scanning the floor...", end="", flush=True)
            floor_matrix = tof.get_stable_matrix()
            print(" Saved!\n")

            # STEP 2
            input("2. Put the 25cm book and press ENTER...")
            print("Scanning the object...", end="", flush=True)
            obj_matrix = tof.get_stable_matrix()
            print(" Saved!\n")

            # PER-PIXEL MAGIC CALCULATION (8x8 Matrix)
            height_matrix = np.zeros((8, 8))
            valid_mask = (floor_matrix > 0) & (obj_matrix > 0)

            H = tof.sensor_height_mm
            height_matrix[valid_mask] = H * (
                1.0 - (obj_matrix[valid_mask] / floor_matrix[valid_mask])
            )

            print("--- OBJECT HEIGHT MATRIX (real cm) ---")
            matrix_in_cm = np.round(height_matrix / 10.0, 1)
            print(matrix_in_cm)

            valid_pixels = matrix_in_cm[matrix_in_cm > 5.0]

            print("\n" + "=" * 50)
            if len(valid_pixels) > 0:
                estimated_height = np.max(valid_pixels)
                print(f"=> OBSTACLE HEIGHT: {estimated_height} cm")
            else:
                print("=> NO OBSTACLE DETECTED.")
            print("=" * 50 + "\n")

            input("Press ENTER to try again...")

    except KeyboardInterrupt:
        print("\n[Tof]: Program stopped.")
    except Exception as e:
        print(f"\n[Tof] Error: {e}")

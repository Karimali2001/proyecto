import smbus2
import time
import math


class IMU:
    def __init__(self):
        self.bus = smbus2.SMBus(1)
        self.compass_address = 0x0D
        self.compass_active = False

        # Keep the offset from your test intact
        self.COMPASS_OFFSET = 119.0

        # --- TRUTH TABLE (Unfolding the compass) ---
        # (Raw, Real)
        self.calibration = [
            (33.3, 0.0),  # Raw North -> Real North (0°)
            (146.4, 90.0),  # Raw East -> Real East (90°)
            (203.8, 180.0),  # Raw South -> Real South (180°)
            (269.1, 270.0),  # Raw West -> Real West (270°)
            (393.3, 360.0),  # North + 360 -> To close the circle
        ]

        self.last_time = time.time()

        self._init_compass()

    def _init_compass(self):
        try:
            # QMC5883L: Set/Reset Period
            self.bus.write_byte_data(self.compass_address, 0x0B, 0x01)
            # QMC5883L: Continuous mode, 50Hz, Range 8G, 512 OSR
            self.bus.write_byte_data(self.compass_address, 0x09, 0x1D)
            self.compass_active = True
            print("[IMU] QMC5883L GPS Compass detected and active.")
        except Exception as e:
            print(f"[IMU] Failed to initialize Compass: {e}")
            self.compass_active = False

    def _convert_i2c(self, lsb, msb):
        value = (msb << 8) | lsb
        if value >= 32768:
            value -= 65536
        return value

    def get_heading(self):
        if not self.compass_active:
            return 0.0

        try:
            data = self.bus.read_i2c_block_data(self.compass_address, 0x00, 6)

            # --- BASE CALIBRATION VALUES ---
            offset_y = -3489.5
            offset_z = -6360.0
            scale_y = 0.7979
            scale_z = 0.7796

            y_raw = self._convert_i2c(data[2], data[3]) - offset_y
            z_raw = self._convert_i2c(data[4], data[5]) - offset_z

            y = y_raw * scale_y
            z = z_raw * scale_z

            heading_rad = math.atan2(y, z)
            heading_deg = math.degrees(heading_rad)

            # Base from your test
            heading_deg -= 15.0
            heading_deg += self.COMPASS_OFFSET
            heading_deg = heading_deg % 360.0

            # --- APPLYING LINEAR INTERPOLATION ---
            # If the value is below our "Raw North" (33.3)
            # We raise it to the next lap of the circle so the math doesn't fail
            if heading_deg < self.calibration[0][0]:
                heading_deg += 360.0

            corrected_heading = heading_deg

            # We look for which "slice" of the magnetic pizza we are in and scale
            for i in range(len(self.calibration) - 1):
                x0, y0 = self.calibration[i]
                x1, y1 = self.calibration[i + 1]

                if x0 <= heading_deg <= x1:
                    corrected_heading = y0 + (heading_deg - x0) * (y1 - y0) / (x1 - x0)
                    break

            return round(corrected_heading % 360.0, 1)

        except Exception:
            return 0.0


if __name__ == "__main__":
    imu = IMU()
    print("=" * 40)
    print(" CORRECTED COMPASS TEST")
    print("=" * 40)
    print("Move your chest and see if the poles are now exact.")
    while True:
        heading = imu.get_heading()

        # Add label for easier reading
        direction = ""
        if heading >= 315 or heading < 45:
            direction = "(NORTE)"
        elif 45 <= heading < 135:
            direction = "(ESTE)"
        elif 135 <= heading < 225:
            direction = "(SUR)"
        elif 225 <= heading < 315:
            direction = "(OESTE)"

        print(f"Real Heading: {heading:05.1f}° {direction}")
        time.sleep(0.2)

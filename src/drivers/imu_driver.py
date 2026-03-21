import smbus2
import time
import math


class IMU:
    def __init__(self):
        self.bus = smbus2.SMBus(1)
        self.last_time = time.time()

        # Hardware Addresses
        self.mpu_address = 0x68
        self.compass_address = 0x0D

        # State variables
        self.yaw = 0.0
        self.gyro_x_offset = 0.0  # NOW WE USE X
        self.compass_active = False

        # --- HARDWARE ORIENTATION OFFSETS ---
        # Since the GPS points to the right, we add or subtract 90 degrees
        # so its "North" is aligned with the front of your chest.
        self.COMPASS_OFFSET = 90.0

        # If turning right physically realistically lowers degrees instead of raising them,
        # we will change this to -1.0. For now we assume 1.0.
        self.GYRO_INVERT = 1.0

        self._init_gyro()
        self._init_compass()

    def _init_gyro(self):
        try:
            # Wake up MPU9250
            self.bus.write_byte_data(self.mpu_address, 0x6B, 0x00)
            time.sleep(0.1)
            # Set gyro scale to 250 deg/s
            self.bus.write_byte_data(self.mpu_address, 0x1B, 0x00)
            time.sleep(0.1)

            print(
                "[IMU] Calibrating Gyroscope... Keep the device completely still."
            )
            samples = 200
            total = 0
            for _ in range(samples):
                total += self._read_raw_gyro_x()  # READING X
                time.sleep(0.005)
            self.gyro_x_offset = total / samples
            print("[IMU] Calibration ready.")
        except Exception as e:
            print(f"[IMU] Failed to initialize Gyroscope: {e}")

    def _init_compass(self):
        try:
            # QMC5883L: Set/Reset Period
            self.bus.write_byte_data(self.compass_address, 0x0B, 0x01)
            # QMC5883L: Continuous mode, 50Hz, Range 8G, 512 OSR
            self.bus.write_byte_data(self.compass_address, 0x09, 0x1D)
            self.compass_active = True
            print("[IMU] QMC5883L GPS Compass detected and active.")

            self.yaw = self._read_compass_heading()
        except Exception as e:
            print(f"[IMU] Failed to initialize Compass: {e}")
            self.compass_active = False

    def _read_raw_gyro_x(self):
        # REGISTERS 0x43 and 0x44 CORRESPOND TO THE X AXIS (YOUR BODY VERTICAL AXIS NOW)
        try:
            high = self.bus.read_byte_data(self.mpu_address, 0x43)
            low = self.bus.read_byte_data(self.mpu_address, 0x44)
            value = (high << 8) | low
            if value > 32767:
                value -= 65536
            return value
        except Exception:
            return 0

    def _convert_i2c(self, lsb, msb):
        value = (msb << 8) | lsb
        if value >= 32768:
            value -= 65536
        return value

    def _read_compass_heading(self):
        if not self.compass_active:
            return 0.0

        try:
            data = self.bus.read_i2c_block_data(self.compass_address, 0x00, 6)

            offset_x = -3532.5
            offset_y = -5691.5
            scale_x = 2.5836
            scale_y = 0.7385

            x_raw = self._convert_i2c(data[0], data[1]) - offset_x
            y_raw = self._convert_i2c(data[2], data[3]) - offset_y

            x = x_raw * scale_x
            y = y_raw * scale_y

            # Compass in 2D plane (Y and X)
            heading_rad = math.atan2(y, x)
            heading_deg = math.degrees(heading_rad)

            heading_deg -= 15.0  # Magnetic declination
            heading_deg += self.COMPASS_OFFSET

            return heading_deg % 360.0
        except Exception:
            return 0.0

    def get_heading(self):
        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time

        # 1. Read Rotation in X (Because your sensor points to the floor)
        raw_x = self._read_raw_gyro_x() - self.gyro_x_offset
        gx = (raw_x / 131.0) * self.GYRO_INVERT

        # 2. Read GPS Compass
        mag_heading = self._read_compass_heading()

        if self.compass_active:
            # COMPLEMENTARY FILTER
            diff = mag_heading - self.yaw
            if diff > 180.0:
                diff -= 360.0
            elif diff < -180.0:
                diff += 360.0

            # Merging: 95% gyroscope, 5% compass
            self.yaw += (gx * dt) + (0.05 * diff)
        else:
            if abs(gx) > 1.0:
                self.yaw += gx * dt

        self.yaw = self.yaw % 360.0
        return round(self.yaw, 1)


if __name__ == "__main__":
    imu = IMU()
    print("Orientation System Active. Physically rotate your body.")
    while True:
        heading = imu.get_heading()
        compass_only = imu._read_compass_heading()
        print(
            f"Merged Heading: {heading:05.1f}  |  Pure GPS Compass: {compass_only:05.1f}"
        )
        time.sleep(0.1)

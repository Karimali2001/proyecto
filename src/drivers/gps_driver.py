import serial
import smbus2
import math
import time


class GPS:
    def __init__(self):
        # Port configuration
        try:
            self.ser = serial.Serial("/dev/ttyAMA0", 115200, timeout=1)
        except Exception as e:
            print(f"Error opening port: {e}")
            exit()

        # --- 2. QMC5883L COMPASS CONFIGURATION (I2C) ---
        try:
            self.bus = smbus2.SMBus(1)
            self.compass_address = 0x0D

            # Initialize compass chip
            # Register 0x0B: Set/Reset Period
            self.bus.write_byte_data(self.compass_address, 0x0B, 0x01)
            # Register 0x09: Control (Continuous mode, 50Hz, Range 8G, 512 OSR)
            self.bus.write_byte_data(self.compass_address, 0x09, 0x1D)
            self.compass_active = True
        except Exception as e:
            print(f"[ERROR] Could not connect to compass via I2C: {e}")
            self.compass_active = False

    def get_location(self):
        # Read and decode the serial line
        line = self.ser.readline().decode("ascii", errors="replace").strip()

        # Filter only the GGA sentence (the most complete for location and altitude)
        if "$GNGGA" in line or "$GPGGA" in line:
            data = line.split(",")

            # Verify that there is a valid position fix (index 2 is latitude)
            if len(data) > 5 and data[2] != "":
                lat = self.convert_to_degrees(data[2], data[3])
                lon = self.convert_to_degrees(data[4], data[5])
                sats = data[7]
                alt = data[9]

                return lat, lon, sats, alt

        return None

    def is_ser_open(self):
        return "ser" in locals() and gps.is_ser_open()

    def convert_to_degrees(self, value, direction):
        if not value:
            return 0.0

        if direction in ["E", "W"]:
            degrees = float(value[:3])
            minutes = float(value[3:])
        else:
            degrees = float(value[:2])
            minutes = float(value[2:])

        decimal = degrees + (minutes / 60.0)

        if direction in ["S", "W"]:
            decimal = -decimal

        return decimal

    def _convert_i2c(self, lsb, msb):
        # Converts two I2C bytes to a signed integer
        value = (msb << 8) | lsb
        if value >= 32768:
            value -= 65536
        return value

    def close(self):
        if hasattr(self, "ser") and self.ser.is_open:
            self.ser.close()
        if hasattr(self, "bus") and self.compass_active:
            self.bus.close()

    def get_heading(self):
        if not self.compass_active:
            return 0.0

        try:
            data = self.bus.read_i2c_block_data(self.compass_address, 0x00, 6)

            offset_x = -3532.5
            offset_y = -5691.5
            offset_z = -7722.5
            scale_x = 2.5836
            scale_y = 0.7385
            scale_z = 0.7943

            # 1. Subtract magnetic interference (Center the circle)
            x_raw = self._convert_i2c(data[0], data[1]) - offset_x
            y_raw = self._convert_i2c(data[2], data[3]) - offset_y
            z_raw = self._convert_i2c(data[4], data[5]) - offset_z

            # 2. Multiply by scale (Round the circle)
            x = x_raw * scale_x
            y = y_raw * scale_y
            z = z_raw * scale_z

            # 3. Calculate angle with perfect circle
            heading_rad = math.atan2(z, x)

            declination_angle = -0.2617
            heading_rad += declination_angle

            if heading_rad < 0:
                heading_rad += 2 * math.pi
            if heading_rad > 2 * math.pi:
                heading_rad -= 2 * math.pi

            heading_deg = heading_rad * (180.0 / math.pi)

            return heading_deg

        except Exception:
            return 0.0


if __name__ == "__main__":
    gps = GPS()

    print("NAVIGATION SYSTEM ACTIVE")
    print("Filtering data... (Press Ctrl+C to stop)")

    try:
        while True:
            location = gps.get_location()

            # heading = gps.get_heading()

            # print(f"HEADING:   {heading:.2f}°")
            # time.sleep(0.5)  # Update every 0.5 seconds

            if location:
                lat, lon, sats, alt = location

                print("-" * 40)
                print(f"LATITUDE:  {lat:.6f}")
                print(f"LONGITUDE: {lon:.6f}")
                print(f"SATELLITES: {sats} | ALTITUDE: {alt}m")
                # Fixed Google Maps URL format
                print(f"MAP: https://www.google.com/maps?q={lat:.6f},{lon:.6f}")

    except KeyboardInterrupt:
        print("\nNavigation stopped.")
        if gps.is_ser_open():
            gps.close()

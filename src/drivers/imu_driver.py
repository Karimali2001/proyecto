import smbus2
import math


class IMU:
    def __init__(self):
        self.bus = smbus2.SMBus(1)
        self.compass_address = 0x0D
        self.compass_active = False

        self.COMPASS_OFFSET = 119.0

        self.calibration = [
            (33.3, 0.0),
            (146.4, 90.0),
            (203.8, 180.0),
            (269.1, 270.0),
            (393.3, 360.0),
        ]

        # --- Valores de calibración por defecto (Los tuyos) ---
        self.offset_x = -3989.5
        self.offset_y = -2614.5
        self.offset_z = -6894.5

        # --- Variables de Autocalibración ---
        self.is_calibrating = False
        self.cal_min_y = 32767
        self.cal_max_y = -32768
        self.cal_min_z = 32767
        self.cal_max_z = -32768

        self._init_compass()

    def _init_compass(self):
        try:
            self.bus.write_byte_data(self.compass_address, 0x0B, 0x01)
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

    def start_calibration(self):
        """Inicia el proceso de recopilación de datos máximos y mínimos."""
        print("[IMU] Iniciando calibración en segundo plano...")
        self.cal_min_y = 32767
        self.cal_max_y = -32768
        self.cal_min_z = 32767
        self.cal_max_z = -32768
        self.is_calibrating = True

    def finish_calibration(self):
        """Termina la calibración, calcula y aplica los nuevos offsets."""
        self.is_calibrating = False

        # Calculamos los nuevos centros
        self.offset_y = (self.cal_max_y + self.cal_min_y) / 2.0
        self.offset_z = (self.cal_max_z + self.cal_min_z) / 2.0

        print(
            f"[IMU] Calibración terminada. Nuevos Offsets -> Y: {self.offset_y}, Z: {self.offset_z}"
        )

    def get_heading(self):
        if not self.compass_active:
            return 0.0

        try:
            data = self.bus.read_i2c_block_data(self.compass_address, 0x00, 6)

            # Leemos los valores crudos de I2C
            raw_y = self._convert_i2c(data[2], data[3])
            raw_z = self._convert_i2c(data[4], data[5])

            # Si estamos en modo calibración, actualizamos los mínimos y máximos silenciosamente
            if self.is_calibrating:
                if raw_y < self.cal_min_y:
                    self.cal_min_y = raw_y
                if raw_y > self.cal_max_y:
                    self.cal_max_y = raw_y
                if raw_z < self.cal_min_z:
                    self.cal_min_z = raw_z
                if raw_z > self.cal_max_z:
                    self.cal_max_z = raw_z

            # Aplicamos los offsets (ya sean los viejos o los recién calibrados)
            y_raw = raw_y - self.offset_y
            z_raw = raw_z - self.offset_z

            scale_y = 0.7948
            scale_z = 0.7555

            y = y_raw * scale_y
            z = z_raw * scale_z

            heading_rad = math.atan2(y, z)
            heading_deg = math.degrees(heading_rad)

            heading_deg -= 15.0
            heading_deg += self.COMPASS_OFFSET
            heading_deg = heading_deg % 360.0

            if heading_deg < self.calibration[0][0]:
                heading_deg += 360.0

            corrected_heading = heading_deg

            for i in range(len(self.calibration) - 1):
                x0, y0 = self.calibration[i]
                x1, y1 = self.calibration[i + 1]

                if x0 <= heading_deg <= x1:
                    corrected_heading = y0 + (heading_deg - x0) * (y1 - y0) / (x1 - x0)
                    break

            return round(corrected_heading % 360.0, 1)

        except Exception:
            return 0.0

import serial
import time


class GPS:
    def __init__(self):
        # Port configuration
        try:
            self.ser = serial.Serial("/dev/ttyAMA0", 115200, timeout=1)
        except Exception as e:
            print(f"Error opening port: {e}")
            exit()

    def get_location(self):
        try:
            # Read and decode the serial line, replacing bad bits
            raw_line = self.ser.readline().decode("ascii", errors="replace").strip()

            # ANTI-NOISE FILTER: Find where the frame actually starts ($)
            if "$" in raw_line:
                line = raw_line[raw_line.find("$") :]
            else:
                return None

            # Filter only the GGA sentence
            if line.startswith("$GNGGA") or line.startswith("$GPGGA"):
                data = line.split(",")

                # Verify that there is a valid position fix (index 2 is latitude)
                if len(data) > 9 and data[2] != "":
                    lat = self.convert_to_degrees(data[2], data[3])
                    lon = self.convert_to_degrees(data[4], data[5])
                    # sats = data[7]
                    # alt = data[9]

                    # Return True (Fix achieved) and the data
                    return lat, lon

                elif len(data) > 7:
                    # Return False (No Fix) and the number of satellites it currently uses
                    return False

        except Exception:
            # If electrical noise causes a decoding failure, ignore it
            pass

        return None

    def is_ser_open(self):
        # Fixed infinite recursion error
        return hasattr(self, "ser") and self.ser.is_open

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

    def close(self):
        if hasattr(self, "ser") and self.ser.is_open:
            self.ser.close()


if __name__ == "__main__":
    gps = GPS()

    print("SISTEMA DE NAVEGACIÓN ACTIVO")
    print("Filtrando ruido y buscando satélites... (Presiona Ctrl+C para detener)")

    try:
        while True:
            result = gps.get_location()

            if result is not None:
                is_fixed = result[0]

                if is_fixed:
                    lat, lon = result

                    print("\n" + "-" * 40)
                    print(f"¡POSICIÓN ENCONTRADA!")
                    print(f"LATITUD:   {lat:.6f}")
                    print(f"LONGITUD:  {lon:.6f}")
                    print(
                        f"MAPA: https://www.google.com/maps/place/{lat:.6f},{lon:.6f}"
                    )
                    print("-" * 40)
                else:
                    sats = result[1]
                    # Print on the same line (\r) so as not to flood the terminal
                    print(
                        f"Sincronizando... Satélites en uso: {sats if sats else '0'}   ",
                        end="\r",
                    )

            # Small pause to avoid saturating the Raspberry Pi's CPU
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nNavegación detenida.")
        if gps.is_ser_open():
            gps.close()

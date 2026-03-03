import serial


class GPS:
    def __init__(self):
        pass

    def get_location(self):
        # Placeholder for GPS location retrieval logic
        return {"latitude": 0.0, "longitude": 0.0}


def convert_to_degrees(value, direction):
    # Returns 0.0 if the string is empty
    if not value:
        return 0.0

    # Longitude (E/W) uses 3 digits for degrees. Latitude (N/S) uses 2.
    if direction in ["E", "W"]:
        degrees = float(value[:3])
        minutes = float(value[3:])
    else:
        degrees = float(value[:2])
        minutes = float(value[2:])

    # Convert NMEA coordinates to decimal degrees
    decimal = degrees + (minutes / 60.0)

    # South and West are negative coordinates
    if direction in ["S", "W"]:
        decimal = -decimal

    return decimal


if __name__ == "__main__":
    # Port configuration
    try:
        ser = serial.Serial("/dev/ttyAMA0", 115200, timeout=1)
    except Exception as e:
        print(f"Error opening port: {e}")
        exit()

    print("NAVIGATION SYSTEM ACTIVE")
    print("Filtering data... (Press Ctrl+C to stop)")

    try:
        while True:
            # Read and decode the serial line
            line = ser.readline().decode("ascii", errors="replace").strip()

            # Filter only the GGA sentence (the most complete for location and altitude)
            if "$GNGGA" in line or "$GPGGA" in line:
                data = line.split(",")

                # Verify that there is a valid position fix (index 2 is latitude)
                if len(data) > 5 and data[2] != "":
                    lat = convert_to_degrees(data[2], data[3])
                    lon = convert_to_degrees(data[4], data[5])
                    sats = data[7]
                    alt = data[9]

                    print("-" * 40)
                    print(f"LATITUDE:  {lat:.6f}")
                    print(f"LONGITUDE: {lon:.6f}")
                    print(f"SATELLITES: {sats} | ALTITUDE: {alt}m")
                    # Fixed Google Maps URL format
                    print(f"MAP: https://www.google.com/maps?q={lat:.6f},{lon:.6f}")

    except KeyboardInterrupt:
        print("\nNavigation stopped.")
        if "ser" in locals() and ser.is_open:
            ser.close()

import smbus2
import time


def calibrate():
    bus = smbus2.SMBus(1)
    address = 0x0D

    try:
        # Initialize QMC5883L
        bus.write_byte_data(address, 0x0B, 0x01)
        bus.write_byte_data(address, 0x09, 0x1D)
    except Exception as e:
        print("Error conectando con la brújula:", e)
        return

    def convert(lsb, msb):
        val = (msb << 8) | lsb
        return val - 65536 if val >= 32768 else val

    print("=" * 50)
    print("CALIBRACIÓN 3D DE BRÚJULA")
    print("=" * 50)
    print("Ponte el equipo en la posición en la que lo vas a usar.")
    print("En 3 segundos, empieza a dar vueltas de 360 grados sobre ti mismo.")
    print("Sigue dando vueltas lentamente hasta que el programa te avise.")
    time.sleep(3)

    print("\n¡GIRA AHORA! (Capturando datos durante 20 segundos...)")

    min_x, max_x = 32767, -32768
    min_y, max_y = 32767, -32768
    min_z, max_z = 32767, -32768

    start_time = time.time()

    while time.time() - start_time < 20.0:
        try:
            data = bus.read_i2c_block_data(address, 0x00, 6)
            x = convert(data[0], data[1])
            y = convert(data[2], data[3])
            z = convert(data[4], data[5])

            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
            if z < min_z:
                min_z = z
            if z > max_z:
                max_z = z

            time.sleep(0.05)
        except:
            pass

    print("\n¡TIEMPO TERMINDADO! Puedes dejar de girar.\n")

    # Calculate ranges to see which axes to ignore
    range_x = max_x - min_x
    range_y = max_y - min_y
    range_z = max_z - min_z

    print(f"Rango de movimiento Eje X: {range_x}")
    print(f"Rango de movimiento Eje Y: {range_y}")
    print(f"Rango de movimiento Eje Z: {range_z}")

    print("-" * 30)
    print("NUEVOS OFFSETS (Copia esto para tu código):")
    print(f"offset_x = {(max_x + min_x) / 2.0}")
    print(f"offset_y = {(max_y + min_y) / 2.0}")
    print(f"offset_z = {(max_z + min_z) / 2.0}")

    # Calculate scales
    average_range = (range_x + range_y + range_z) / 3.0
    print(f"scale_x = {average_range / range_x if range_x > 0 else 0:.4f}")
    print(f"scale_y = {average_range / range_y if range_y > 0 else 0:.4f}")
    print(f"scale_z = {average_range / range_z if range_z > 0 else 0:.4f}")


if __name__ == "__main__":
    calibrate()

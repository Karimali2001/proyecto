import smbus2
import time

bus = smbus2.SMBus(1)
address = 0x0D

bus.write_byte_data(address, 0x0B, 0x01)
bus.write_byte_data(address, 0x09, 0x1D)


def convert(lsb, msb):
    v = (msb << 8) | lsb
    if v >= 32768:
        v -= 65536
    return v


x_min = y_min = z_min = 32767
x_max = y_max = z_max = -32768

print("--- CALIBRACIÓN COMPLETA (OFFSETS Y ESCALAS) ---")
print("Gira el prototipo 360 grados sobre su propio eje (Posición Vertical).")
time.sleep(3)
print("¡GIRANDO AHORA! (Tienes 20 segundos)...")

for i in range(200):
    data = bus.read_i2c_block_data(address, 0x00, 6)
    x = convert(data[0], data[1])
    y = convert(data[2], data[3])
    z = convert(data[4], data[5])

    x_min, x_max = min(x_min, x), max(x_max, x)
    y_min, y_max = min(y_min, y), max(y_max, y)
    z_min, z_max = min(z_min, z), max(z_max, z)

    print(f"Midiendo... X:{x:6} Z:{z:6}", end="\r")
    time.sleep(0.1)

# Calcular Offsets (Centro)
offset_x = (x_max + x_min) / 2
offset_y = (y_max + y_min) / 2
offset_z = (z_max + z_min) / 2

# Calcular Amplitudes (Radio)
amp_x = (x_max - x_min) / 2
amp_y = (y_max - y_min) / 2
amp_z = (z_max - z_min) / 2

# Evitar división por cero
amp_x = 1 if amp_x == 0 else amp_x
amp_y = 1 if amp_y == 0 else amp_y
amp_z = 1 if amp_z == 0 else amp_z

# Calcular Escalas (Para volverlo un círculo perfecto)
avg_amp = (amp_x + amp_y + amp_z) / 3
scale_x = avg_amp / amp_x
scale_y = avg_amp / amp_y
scale_z = avg_amp / amp_z

print("\n\n=== REEMPLAZA ESTO EN TU FUNCIÓN get_heading() ===")
print("            # --- CALIBRACIÓN DE CENTRO ---")
print(f"            offset_x = {offset_x}")
print(f"            offset_y = {offset_y}")
print(f"            offset_z = {offset_z}")
print("            # --- CALIBRACIÓN DE FORMA (ESCALA) ---")
print(f"            scale_x = {scale_x:.4f}")
print(f"            scale_y = {scale_y:.4f}")
print(f"            scale_z = {scale_z:.4f}")

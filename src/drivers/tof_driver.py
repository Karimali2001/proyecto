#!/usr/bin/env python
import qwiic_vl53l5cx
import time
import numpy as np
import warnings


class Tof:
    def __init__(self, sensor_height_mm=1220):
        print("[Tof] Initializando Tof en modo 8x8 (Seguro)...")
        self.sensor = qwiic_vl53l5cx.QwiicVL53L5CX()

        self.sensor_height_mm = sensor_height_mm

        if not self.sensor.is_connected():
            raise RuntimeError("[Tof] El dispositivo no está conectado.")

        print("Iniciando sensor VL53L5CX...")
        if not self.sensor.begin():
            raise RuntimeError("[Tof] Falló la inicialización.")

        # Volvemos a la configuración 8x8 que ya sabemos que funciona perfecto
        self.sensor.set_resolution(self.sensor.kResolution8x8)
        self.sensor.set_target_order(self.sensor.kTargetOrderClosest)
        self.sensor.set_ranging_frequency_hz(5)
        self.sensor.set_integration_time_ms(150)
        self.sensor.set_sharpener_percent(50)

        self.sensor.start_ranging()

    def get_matrix(self):
        if self.sensor.check_data_ready():
            measurement_data = self.sensor.get_ranging_data()

            # Extraemos los 64 valores
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
        print("SISTEMA DE DETECCIÓN DE ALTURA EXACTA (8x8)")
        print("=" * 50 + "\n")

        while True:
            # PASO 1
            input(
                "1. Asegúrate de que NO HAY NADA (solo piso vacío) y presiona ENTER..."
            )
            print("Escaneando el suelo...", end="", flush=True)
            floor_matrix = tof.get_stable_matrix()
            print(" ¡Guardado!\n")

            # PASO 2
            input("2. Pon el libro de 25cm y presiona ENTER...")
            print("Escaneando el objeto...", end="", flush=True)
            obj_matrix = tof.get_stable_matrix()
            print(" ¡Guardado!\n")

            # CÁLCULO MÁGICO PER-PÍXEL (Matriz 8x8)
            height_matrix = np.zeros((8, 8))
            valid_mask = (floor_matrix > 0) & (obj_matrix > 0)

            H = tof.sensor_height_mm
            height_matrix[valid_mask] = H * (
                1.0 - (obj_matrix[valid_mask] / floor_matrix[valid_mask])
            )

            print("--- MATRIZ DE ALTURA DEL OBJETO (cm reales) ---")
            matrix_en_cm = np.round(height_matrix / 10.0, 1)
            print(matrix_en_cm)

            píxeles_validos = matrix_en_cm[matrix_en_cm > 5.0]

            print("\n" + "=" * 50)
            if len(píxeles_validos) > 0:
                altura_estimada = np.max(píxeles_validos)
                print(f"=> ALTURA DEL OBSTÁCULO: {altura_estimada} cm")
            else:
                print("=> NO SE DETECTÓ NINGÚN OBSTÁCULO.")
            print("=" * 50 + "\n")

            input("Presiona ENTER para probar de nuevo...")

    except KeyboardInterrupt:
        print("\n[Tof]: Programa detenido.")
    except Exception as e:
        print(f"\n[Tof] Error: {e}")

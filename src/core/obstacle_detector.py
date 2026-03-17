import time
import numpy as np
import json


from src.drivers.tof_driver import Tof
from src.core.priority_queue import AudioPriorityQueue


class ObstacleDetector:
    def __init__(self, audio_queue, sensor_height_mm=1220):
        self.tof = Tof(sensor_height_mm=sensor_height_mm)
        self.audio_queue = audio_queue
        self.floor_matrix = None
        self.is_calibrating = False
        self.recalibrate_sensor()

    def recalibrate_sensor(self):
        self.is_calibrating = True
        time.sleep(0.1)
        self.floor_matrix = self.tof.get_stable_matrix()
        self.is_calibrating = False

    def detect_hole(self, matrix_cm):
        """
        Analiza las filas inferiores (que apuntan a los pies) buscando caídas.
        Filtra el ruido exigiendo que al menos 2 píxeles confirmen el hueco.
        """
        zona_suelo = matrix_cm[5:8, :]

        # Aumentamos a -15cm para ignorar desniveles normales del piso o ruido del sensor
        umbral_peligro_cm = -15.0

        zona_izq = zona_suelo[:, 0:3]
        zona_cen = zona_suelo[:, 3:5]
        zona_der = zona_suelo[:, 5:8]

        # En lugar de np.min() (que se asusta con 1 solo píxel malo),
        # contamos CUÁNTOS píxeles están viendo el hueco en cada zona.
        huecos_izq = np.sum(zona_izq <= umbral_peligro_cm)
        huecos_cen = np.sum(zona_cen <= umbral_peligro_cm)
        huecos_der = np.sum(zona_der <= umbral_peligro_cm)

        hay_hueco = False
        posiciones = []

        # Solo disparamos la alarma si al menos 2 píxeles confirman el peligro
        if huecos_izq >= 2:
            hay_hueco = True
            posiciones.append("izquierda")

        if huecos_cen >= 2:
            hay_hueco = True
            posiciones.append("centro")

        if huecos_der >= 2:
            hay_hueco = True
            posiciones.append("derecha")

        if not hay_hueco:
            return False, ""

        if len(posiciones) == 3:
            return True, "frente completo"

        return True, ", ".join(posiciones)

    def detect_hole_thread(self):
        try:
            detected = False
            H = self.tof.sensor_height_mm

            while True:
                if self.is_calibrating:
                    time.sleep(0.1)
                    continue
                # 1. Obtenemos los milímetros crudos
                current_matrix = self.tof.get_matrix()

                if current_matrix is not None:
                    # 2. APLICAMOS LA MAGIA MATEMÁTICA
                    height_matrix = np.zeros((8, 8))
                    valid_mask = (self.floor_matrix > 0) & (current_matrix > 0)

                    height_matrix[valid_mask] = H * (
                        1.0
                        - (current_matrix[valid_mask] / self.floor_matrix[valid_mask])
                    )

                    # 3. Lo convertimos a Centímetros Reales (que es lo que espera la función)
                    matrix_cm = np.round(height_matrix / 10.0, 1)

                    # 4. Ahora sí, pasamos la matriz de centímetros a la detección
                    is_hole, pos_hole = self.detect_hole(matrix_cm)

                    if is_hole and not detected:
                        sound_position = "center"
                        if "izquierda" in pos_hole:
                            sound_position = "left"
                        elif "derecha" in pos_hole:
                            sound_position = "right"

                        cmd = json.dumps(
                            {
                                "position": sound_position,
                                "frequencyCenter": 400,
                                "frequencySide": 300,
                            }
                        )

                        self.audio_queue.put(
                            AudioPriorityQueue.HOLE_DETECTION,
                            cmd,
                        )
                        time.sleep(4)
                        detected = True
                    elif not is_hole:
                        detected = False

                time.sleep(0.005)
        except Exception as e:
            print(f"[Tof] Error: {e}")

    def detect_air_obstacle(self, matrix):
        """
        Checks the upper rows (for the sensor facing upwards/forward).
        If the distance is less than 1500mm (1.5 meters), it triggers an alert.
        """

        left_danger = False
        center_danger = False
        right_danger = False

        # Check first 3 rows
        for row in range(3):
            for col in range(8):
                distance = matrix[row, col]

                # 0 is an error/infinite or the object is less than 1500mm
                if 0 < distance < 1000:
                    if col <= 2:
                        left_danger = True
                    elif col >= 5:
                        right_danger = True
                    else:
                        center_danger = True

        # boolean logic

        if not (left_danger or center_danger or right_danger):
            return False, ""

        if left_danger and center_danger and right_danger:
            return True, "pared"

        elif left_danger and right_danger and not center_danger:
            return True, "ambos lados"

        elif left_danger and center_danger:
            return True, "frente e izquierda"

        elif right_danger and center_danger:
            return True, "frente y derecha"

        elif center_danger:
            return True, "frente"

        elif left_danger:
            return True, "izquierda"

        elif right_danger:
            return True, "derecha"

        return False, ""

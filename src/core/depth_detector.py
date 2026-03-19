import numpy as np
import cv2
import time
import json
from src.core.priority_queue import AudioPriorityQueue


class DepthDetector:
    # 🔥 VOLVIERON TUS MEDIDAS EXACTAS 🔥
    def __init__(
        self, hailo_driver, audio_queue, user_height_mm=1780, camera_height_mm=1220
    ):
        self.hailo_driver = hailo_driver
        self.audio_queue = audio_queue

        # Interruptor Principal
        self.is_active = True

        self.danger_streak = 0
        self.frame_counter = 0
        self.last_alarm_time = 0  # Cooldown de 10 segundos

        self.model_h, self.model_w, _ = self.hailo_driver.get_input_shape()

        # Umbral para detectar objetos cerca (calibrado para la calle)
        self.umbral_cercania = 7000.0

        # Auto-calibrar la geometría para un solo cuadro (Protección Facial)
        self._calibrate_geometry(user_height_mm, camera_height_mm)

    def _calibrate_geometry(self, user_height, camera_height):
        """Calcula el cuadro de la cara basado en tu altura real."""
        horizon_y = (
            self.model_h // 2
        )  # 128 (El centro vertical del lente, altura de la cámara)
        center_x = self.model_w // 2  # 160 (El centro horizontal del lente)
        scale_factor = 0.15

        # Distancia desde la cámara hasta el tope de la cabeza
        head_mm = user_height - camera_height
        if head_mm < 0:
            head_mm = 200  # Seguro anti-errores

        head_pixels = int(head_mm * scale_factor)

        # Centramos el cuadro horizontalmente
        self.rect_width = 80
        self.rect_x = center_x - (self.rect_width // 2)

        # El cuadro crece desde el horizonte (tu pecho) hacia arriba, hasta cubrir tu cabeza
        self.rect_y = max(0, horizon_y - head_pixels)

        # El alto del cuadro será exactamente la distancia calculada en píxeles
        self.rect_height = head_pixels

        print("\n====================================")
        print(f"🔧 RADAR AUTO-CALIBRADO (MODO EXTERIORES) 🔧")
        print(f"Usuario: {user_height}mm | Cámara: {camera_height}mm")
        print(
            f"🔴 Zona de Protección: Y={self.rect_y} a {self.rect_y + self.rect_height}"
        )
        print("====================================\n")

    def toggle_radar(self):
        """Enciende o apaga el radar aéreo."""
        self.is_active = not self.is_active
        estado = "ACTIVADO" if self.is_active else "DESACTIVADO"
        print(f"📡 [Radar Aéreo] Sistema {estado}")
        return self.is_active

    def check_yolo_overlap(self, yolo_detections, video_w=1280, video_h=960):
        """Revisa si alguna persona u objeto conocido está DENTRO O TOCANDO el cuadro de peligro."""
        if not yolo_detections:
            return False

        objetos_seguros = [
                    "person", "car", "truck", "bus", "motorcycle", "bicycle", "train",
                    "horse", "cow", "dog", "cat", 
                    "refrigerator", "tv", "microwave", "oven"
                ]

        for det in yolo_detections:
            name, bbox, score = det
            if name not in objetos_seguros:
                continue

            x0, y0, x1, y1 = bbox
            x0_radar = x0 * (self.model_w / video_w)
            x1_radar = x1 * (self.model_w / video_w)
            y0_radar = y0 * (self.model_h / video_h)
            y1_radar = y1 * (self.model_h / video_h)

            # ¿El recuadro de YOLO toca nuestro recuadro del radar?
            choca_x = (x0_radar < (self.rect_x + self.rect_width)) and (
                x1_radar > self.rect_x
            )
            choca_y = (y0_radar < (self.rect_y + self.rect_height)) and (
                y1_radar > self.rect_y
            )

            if choca_x and choca_y:
                print(
                    f"[Radar Aéreo] 🛑 Ignorando obstáculo: Es un(a) '{name}' TOCANDO el cuadro."
                )
                return True

        return False

    def process_frame(self, frame, yolo_detections=[]):
        if not self.is_active:
            return False, 0.0

        self.frame_counter += 1
        if self.frame_counter % 3 != 0:
            return False, 0.0

        # 1. Inferir Profundidad
        frame_resized = cv2.resize(frame, (self.model_w, self.model_h))
        raw_output = self.hailo_driver.infer(frame_resized)
        depth_array = self.hailo_driver.extract_depth_map(raw_output)

        if depth_array is None:
            return False, 0.0

        # 2. Extraer túnel (Solo uno ahora)
        tunel_alto = depth_array[
            self.rect_y : self.rect_y + self.rect_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        # 3. Calcular Bloqueo
        bloqueo_alto = (
            np.sum(tunel_alto > self.umbral_cercania) / tunel_alto.size
        ) * 100
        hay_peligro = bloqueo_alto > 15.0

        # 4. FILTRO INTELIGENTE (YOLO)
        if hay_peligro:
            es_objeto_ignorado = self.check_yolo_overlap(yolo_detections)
            if es_objeto_ignorado:
                hay_peligro = False  # Cancelamos la alarma

        print(f"[Radar] Protección Facial: {bloqueo_alto:.1f}% | Alarma: {hay_peligro}")

        # 5. Histéresis
        if hay_peligro:
            self.danger_streak += 1
        else:
            self.danger_streak = 0

        peligro_confirmado = self.danger_streak >= 3

        # 6. LANZAR ALARMA Y FOTO
        if peligro_confirmado:
            current_time = time.time()
            if current_time - self.last_alarm_time >= 10.0:
                print("🚨 ¡BIP ESPACIAL! PELIGRO AÉREO CONFIRMADO 🚨")

                cmd = json.dumps(
                    {"position": "center", "frequencyCenter": 800, "frequencySide": 800}
                )
                self.audio_queue.put(AudioPriorityQueue.AIR_OBSTACLE, cmd)
                self.last_alarm_time = current_time

                # Guardar evidencia
                debug_img = frame_resized.copy()
                cv2.rectangle(
                    debug_img,
                    (self.rect_x, self.rect_y),
                    (self.rect_x + self.rect_width, self.rect_y + self.rect_height),
                    (0, 0, 255),
                    2,
                )
                cv2.imwrite("peligro_aereo_inteligente.jpg", debug_img)

            self.danger_streak = 0

        return peligro_confirmado, bloqueo_alto

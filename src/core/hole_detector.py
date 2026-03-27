import numpy as np
import time
from pathlib import Path
import cv2


class HoleDetector:
    def __init__(
        self,
        hailo_driver,
        audio_queue,
        user_height_mm=1000,
        camera_height_mm=850,  # Ajustado a ~85cm
    ):
        self.hailo_driver = hailo_driver
        self.audio_queue = audio_queue

        self.is_active = False

        self.danger_streak = 0
        self.clear_streak = 0
        self.is_currently_blocked = False
        self.last_alarm_time = 0.0
        self.last_hole_heading = None

        if self.hailo_driver:
            self.model_h, self.model_w, _ = self.hailo_driver.get_input_shape()
            self._calibrate_geometry()
        else:
            print("[HoleDetector] Warning: Hailo driver not provided.")

    def _calibrate_geometry(self):
        # La imagen es 320x256
        center_x = self.model_w // 2

        # Hacemos la zona un poco más ancha para agarrar bien el escalón
        self.rect_width = 140
        self.rect_x = center_x - (self.rect_width // 2)

        # 1. ZONA DE REFERENCIA (Tus pies, lo más oscuro/cerca en el borde inferior)
        self.ref_y = 210
        self.ref_height = 40

        # 2. ZONA DE EXAMEN (El hueco, el parche blanco brillante que está más arriba)
        self.exam_y = 120
        self.exam_height = 60

    def toggle_radar(self):
        self.is_active = not self.is_active
        state = "ACTIVATED" if self.is_active else "DEACTIVATED"
        print(f"📡 [Hole Radar] System {state}")
        return self.is_active

    def process_frame(self, frame_resized, depth_array, current_heading=None):
        if not self.is_active or depth_array is None:
            return False

        # 1. Extraer zonas
        reference_ground = depth_array[
            self.ref_y : self.ref_y + self.ref_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        exam_zone = depth_array[
            self.exam_y : self.exam_y + self.exam_height,
            self.rect_x : self.rect_x + self.rect_width,
        ]

        # 2. MATEMÁTICA CORREGIDA (BLANCO = LEJOS = NÚMEROS ALTOS)
        feet_average = np.mean(reference_ground)

        # Si el parche de adelante tiene valores un 35% MÁS ALTOS que tus pies, es un hueco.
        hole_threshold = feet_average * 1.35

        # IMPORTANTE: Ahora sí buscamos píxeles MAYORES (>) al umbral (más blancos/lejanos)
        danger_pixels = np.sum(exam_zone > hole_threshold)
        hole_percentage = (danger_pixels / exam_zone.size) * 100

        # Si más del 20% es "vacío", hay hueco
        has_danger = hole_percentage > 20.0

        # ==========================================
        # 3. TURN DETECTION (IMU)
        # ==========================================
        if (
            current_heading is not None
            and self.is_currently_blocked
            and self.last_hole_heading is not None
        ):
            diff = (current_heading - self.last_hole_heading + 180) % 360 - 180
            if abs(diff) > 45.0:
                self.is_currently_blocked = False
                self.last_alarm_time = 0.0
                self.danger_streak = 0
                self.clear_streak = 0

        # ==========================================
        # 4. STATE MACHINE
        # ==========================================
        if has_danger:
            self.danger_streak += 1
            self.clear_streak = 0
        else:
            self.clear_streak += 1
            self.danger_streak = 0

        if self.clear_streak >= 15:
            self.is_currently_blocked = False

        confirmed_danger = self.danger_streak >= 3

        # ==========================================
        # 5. ALARMA Y FOTO DE DEBUG
        # ==========================================
        current_time = time.time()

        if (
            confirmed_danger
            and not self.is_currently_blocked
            and (current_time - self.last_alarm_time >= 5.0)
        ):
            cmd = {"action": "sound", "position": "center", "sound_type": "hole"}
            self.audio_queue.play_concurrent(cmd)

            self.is_currently_blocked = True
            self.last_alarm_time = current_time

            if current_heading is not None:
                self.last_hole_heading = current_heading

            # --- DEBUG SAVE ---
            debug_dir = Path.cwd() / "debug_holes"
            debug_dir.mkdir(exist_ok=True)
            timestamp = int(current_time * 1000)

            # Normalización para que la foto no se vea azul por culpa de un píxel infinito
            clipped_depth = np.clip(depth_array, 0, 25000)
            depth_norm = cv2.normalize(
                clipped_depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U
            )
            depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

            # Verde = Referencia (Pies), Rojo = Examen (Hueco)
            cv2.rectangle(
                depth_color,
                (self.rect_x, self.ref_y),
                (self.rect_x + self.rect_width, self.ref_y + self.ref_height),
                (0, 255, 0),
                2,
            )
            cv2.rectangle(
                depth_color,
                (self.rect_x, self.exam_y),
                (self.rect_x + self.rect_width, self.exam_y + self.exam_height),
                (0, 0, 255),
                2,
            )

            filename = (
                debug_dir
                / f"hole_{timestamp}_perc{hole_percentage:.1f}_ref{feet_average:.1f}.jpg"
            )
            cv2.imwrite(str(filename), depth_color)

        if self.danger_streak > 30:
            self.danger_streak = 15
        if self.clear_streak > 30:
            self.clear_streak = 15

        return confirmed_danger

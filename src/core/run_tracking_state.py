import cv2
import time
from picamera2 import MappedArray
import threading
import numpy as np
from types import SimpleNamespace
import json
from pathlib import Path
import inspect
from queue import Queue, Empty

from src.utils.byte_tracker import BYTETracker

from .state import State
from .error_state import ErrorState


BASE_PATH = Path.cwd()
TRANSLATIONS_PATH = Path(BASE_PATH / "assets/translations.json")


class RunTracking(State):
    def __init__(self):
        # Variable para compartir las detecciones entre el proceso principal y el callback de dibujo
        self.current_detections = []
        self.lock = threading.Lock()

        self.running = False
        self.inference_thread = None
        self.audio_thread = None

        # Initialize Tracker
        tracker_args = SimpleNamespace(
            track_thresh=0.4, track_buffer=60, match_thresh=0.7, mot20=False
        )
        self.tracker = BYTETracker(tracker_args)
        self.active_ids = set()  # To keep track of currently visible IDs for logging
        self.logged_ids = set()  # New set to remember what we have already logged

        self.track_id_to_label_map = {}

        self.translations_map = {}
        with open(TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
            self.translations_map = json.load(f)

        #
        self._tracker_update_uses_img_meta = self._detect_tracker_update_signature()

        self.speak_labels_queue = Queue()

    def draw_detections_callback(self, request):
        """Esta función es llamada automáticamente por Picamera2 antes de mostrar cada frame."""
        if self.current_detections:
            with MappedArray(request, "main") as m:
                # Updated unpacking to include track_id
                for class_name, bbox, score, track_id in self.current_detections:
                    x0, y0, x1, y1 = bbox
                    # Add ID to label
                    label = f"#{track_id} {class_name} {int(score * 100)}%"

                    # Dibujar rectángulo
                    cv2.rectangle(m.array, (x0, y0), (x1, y1), (0, 255, 0), 2)

                    # Dibujar texto con fondo para mejor legibilidad
                    (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(m.array, (x0, y0 - 20), (x0 + w, y0), (0, 255, 0), -1)
                    cv2.putText(
                        m.array,
                        label,
                        (x0, y0 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 0, 0),
                        1,
                        cv2.LINE_AA,
                    )

    def _detect_tracker_update_signature(self) -> bool:
        """True si update espera metadata de imagen además de detecciones."""
        try:
            # Método ligado: parámetros aquí no incluyen 'self'
            param_count = len(inspect.signature(self.tracker.update).parameters)
            return param_count >= 3
        except Exception:
            return False

    def _tracker_update(self, dets_array, video_h, video_w):
        """Llama update con la firma correcta y hace fallback automático."""
        img_info = (video_h, video_w)
        img_size = (video_h, video_w)

        try:
            if self._tracker_update_uses_img_meta:
                return self.tracker.update(dets_array, img_info, img_size)
            return self.tracker.update(dets_array)
        except TypeError:
            # Fallback si la detección inicial no coincide con la implementación real
            self._tracker_update_uses_img_meta = not self._tracker_update_uses_img_meta
            if self._tracker_update_uses_img_meta:
                return self.tracker.update(dets_array, img_info, img_size)
            return self.tracker.update(dets_array)

    def _announce_object_loop(self):

        driver_audio = self.context.audio_output_driver
        if driver_audio is not None:
            driver_audio.speak("Encontré ")

            while self.running:
                try:
                    # Si no hay nada en la cola en 0.5 seg, lanza Empty y repite el bucle verificando self.running
                    speak_label = self.speak_labels_queue.get(timeout=0.5)

                    # Verificar de nuevo por si running cambió mientras esperábamos

                    if speak_label is None or not self.running:
                        break

                    print(f"[TRACKING] Hilo de audio hablando: {speak_label}")
                    driver_audio.speak(self.translations_map[speak_label])
                except Empty:
                    # Esto es NORMAL. Significa que no hay nada que decir por ahora.
                    # Simplemente continuamos el bucle para verificar self.running de nuevo.
                    continue
                except Exception as e:
                    print(f"[ERROR] Hilo de audio falló: {e}")

    def _run_inference_loop(self):

        driver_cam = self.context.camera_driver
        driver_ai = self.context.hailo_driver

        while self.running:
            try:
                # 1. Capturar frame de baja resolución para IA
                frame = driver_cam.capture_array("lores")

                # 2. Inferencia (Lo pesado)
                raw_detections = driver_ai.infer(frame)

                # 3. Procesar resultados
                video_w, video_h = self.context.camera_driver.video_size

                clean_detections = driver_ai.extract_detections(
                    raw_detections, video_w, video_h
                )

                # --- TRACKING LOGIC START ---
                # Convert clean_detections to format for BYTETracker
                # extract_detections returns list of (label, [x1, y1, x2, y2], score)
                # BYTETracker expects (N, 5) numpy array: [x1, y1, x2, y2, score]

                dets_to_track = []
                dets_labels = []

                for label, bbox, score in clean_detections:
                    # bbox is [x1, y1, x2, y2]
                    dets_to_track.append(list(bbox) + [score])
                    dets_labels.append(label)

                final_tracks = []
                current_frame_ids = set()
                # Dictionary to store ID -> Label mapping for this frame for logging
                id_to_label_map = {}

                if dets_to_track:
                    dets_array = np.array(dets_to_track, dtype=float)

                    online_targets = self._tracker_update(dets_array, video_h, video_w)

                    for t in online_targets:
                        # Map back to closest class label or just use the one from tracking if tracker stored it (BYTETracker usually just tracks boxes)
                        # We will try to match simple box overlap or just assume order if possible,
                        # but often we just take the first label if single class, or we need to pass class info to tracker.
                        # For simplicity, we re-associate loosely or just use "Obj".
                        # Since clean_detections might filter, we'll try to keep it simple.

                        tlwh = t.tlwh
                        tid = t.track_id
                        vertical = tlwh[2] / tlwh[3] > 1.6
                        if tlwh[2] * tlwh[3] > 10 and not vertical:
                            x1, y1, w, h = tlwh
                            bbox_int = [int(x1), int(y1), int(x1 + w), int(y1 + h)]

                            # Find best matching original detection to recover label
                            label_str = "Object"
                            best_iou = 0.0

                            t_area = w * h

                            # Simple IoU-like check to find which detection this track belongs to
                            for orig_label, orig_bbox, orig_score in clean_detections:
                                # orig_bbox is [x1, y1, x2, y2]
                                ox1, oy1, ox2, oy2 = orig_bbox

                                # Intersect
                                ix1 = max(x1, ox1)
                                iy1 = max(y1, oy1)
                                ix2 = min(x1 + w, ox2)
                                iy2 = min(y1 + h, oy2)

                                iw = max(0, ix2 - ix1)
                                ih = max(0, iy2 - iy1)
                                intersection = iw * ih

                                # Using intersection over tracked area as a simple proxy for matching
                                if t_area > 0:
                                    match_score = intersection / t_area
                                    if match_score > best_iou and match_score > 0.5:
                                        best_iou = match_score
                                        label_str = orig_label

                            final_tracks.append((label_str, bbox_int, t.score, tid))
                            current_frame_ids.add(tid)
                            id_to_label_map[tid] = label_str
                            self.track_id_to_label_map[tid] = label_str

                # --- LOGGING LOGIC ---
                # Check for completely new objects that haven't been logged yet

                # If you want to log ONLY once per session per ID:
                new_ids = current_frame_ids - self.logged_ids

                if new_ids:
                    # Prepare list of labels for new IDs
                    # We create separate strings for logging with ID and speaking just label

                    log_entries = []
                    speak_labels = []

                    # print(
                    #     f"[TRACKING] current_frame_ids: {current_frame_ids}"
                    #     f" logged_ids: {self.logged_ids}"
                    #     f" new_ids: {new_ids}"
                    # )

                    # Find new labels to announce
                    for uid in new_ids:
                        label = id_to_label_map[uid]
                        log_entries.append(f" Found {label} (ID: {uid})")
                        speak_labels.append(label)
                        self.speak_labels_queue.put(label)

                    print(
                        f"[TRACKING] Detected new object(s): {', '.join(log_entries)}"
                    )

                    # Add to logged set so we don't spam print them
                    self.logged_ids.update(new_ids)

                # Update active set to current frame for other logic if needed
                self.active_ids = current_frame_ids

                # -------------------------

                with self.lock:
                    # 4. ACTUALIZAR VARIABLE COMPARTIDA
                    # Esto es lo que lee la función 'draw_detections_callback'
                    self.current_detections = final_tracks

                if clean_detections:
                    pass  # handled above

                time.sleep(0.01)

            except Exception as e:
                print(f"[ERROR] Hilo de inferencia falló: {e}")
                self.running = False

    def stop(self) -> None:

        print("[TRACKING] Deteniendo estado...", flush=True)
        self.running = False  # Bandera principal abajo

        # 1. Vaciar cola de audio para desbloquear el hilo si está esperando
        # Importante: Poner un "poison pill" o simplemente vaciar
        with self.speak_labels_queue.mutex:
            self.speak_labels_queue.queue.clear()
        self.speak_labels_queue.put(None)

        # 2. Detener Hilo de Audio
        if self.audio_thread and self.audio_thread.is_alive():
            print("[TRACKING] Esperando a que muera hilo de audio...", flush=True)
            self.audio_thread.join(timeout=10.0)
            if self.audio_thread.is_alive():
                print("[TRACKING] ALERTA: Hilo de audio no murió a tiempo.", flush=True)

        # 4. Detener Hilo de Inferencia
        if self.inference_thread and self.inference_thread.is_alive():
            print("[TRACKING] Esperando a que muera hilo de inferencia...", flush=True)
            self.inference_thread.join()
            if self.inference_thread.is_alive():
                print(
                    "[TRACKING] ALERTA: Hilo de inferencia no murió a tiempo.",
                    flush=True,
                )

        print("[TRACKING] Estado detenido completamente.", flush=True)

    def process(self) -> None:
        """Método principal del estado (Hilo Principal)."""

        driver_cam = self.context.camera_driver

        if driver_cam is None or self.context.hailo_driver is None:
            print("[Error] Drivers no inicializados en RunTracking")
            self.context.transition_to(ErrorState())
            return

        if driver_cam.picam2.pre_callback is None:
            print("[TRACKING] Activando visualización en cámara...")
            driver_cam.set_callback(self.draw_detections_callback)

        if not self.running:
            self.running = True
            self.inference_thread = threading.Thread(
                target=self._run_inference_loop, daemon=True
            )
            self.audio_thread = threading.Thread(
                target=self._announce_object_loop, daemon=True
            )
            self.inference_thread.start()
            self.audio_thread.start()
        try:
            while self.running:
                time.sleep(0.01)
        except KeyboardInterrupt:
            self.stop()

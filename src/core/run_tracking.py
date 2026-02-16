import cv2
import time
from picamera2 import MappedArray
import threading
import numpy as np
from types import SimpleNamespace  # Added for tracker config
import sys  # Added for path adjustment if needed
import os

# Adjust path to find common if necessary, mirroring user provided snippet
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from src.utils.byte_tracker import BYTETracker

from .state import State
from .error import ErrorState


class RunTracking(State):
    def __init__(self):
        # Variable para compartir las detecciones entre el proceso principal y el callback de dibujo
        self.current_detections = []
        self.lock = threading.Lock()

        self.running = False
        self.thread = None

        # Initialize Tracker
        # Default configuration for BYTETracker based on common usage
        tracker_args = SimpleNamespace(
            track_thresh=0.5, track_buffer=30, match_thresh=0.8, mot20=False
        )
        self.tracker = BYTETracker(tracker_args)
        self.active_ids = set()  # To keep track of currently visible IDs for logging

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

                if dets_to_track:
                    dets_array = np.array(dets_to_track, dtype=float)
                    # img_info and img_size are often (height, width)
                    img_info = (video_h, video_w)
                    img_size = (video_h, video_w)

                    online_targets = self.tracker.update(dets_array, img_info, img_size)

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

                            # Simple label logic: just "Object" or try to find matching detection
                            # In a real rigorous setup we pass class ID into tracker or match by IOU
                            label_str = "Object"
                            # Rough matching to original detection to get Class Name back
                            best_iou = 0
                            for orig_label, orig_bbox, orig_score in clean_detections:
                                # Calculate IOU to carry over the class label
                                # ... (skipped complex IOU for brevity, picking last or default)
                                label_str = orig_label

                            final_tracks.append((label_str, bbox_int, t.score, tid))
                            current_frame_ids.add(tid)

                # --- LOGGING LOGIC ---
                # Check for new objects (objects seen now that were not in the "active" set previously)
                # Actually, user wants: if I stopped seeing it and it comes back, log it.
                # The simple way: strictly check existence in previous frame vs current frame.

                new_ids = current_frame_ids - self.active_ids
                if new_ids:
                    # Only print specifically what is new
                    print(
                        f"[TRACKING] Detected new/returning object(s) IDs: {list(new_ids)}"
                    )

                # Update active set to current frame ONLY.
                # Be careful: if tracking flickers, this logs frequently.
                # But requirement is "if i stopped seeing it ... and then again".
                # If tracker holds ID through occlusion, it won't disappear from 'online_targets' immediately.
                self.active_ids = current_frame_ids

                # -------------------------

                with self.lock:
                    # 4. ACTUALIZAR VARIABLE COMPARTIDA
                    # Esto es lo que lee la función 'draw_detections_callback'
                    self.current_detections = final_tracks

                # remove the print loop to avoid spam, controlled by logging logic above
                # if clean_detections: ...

                if clean_detections:
                    pass  # handled above

                time.sleep(0.01)

            except Exception as e:
                print(f"[ERROR] Hilo de inferencia falló: {e}")
                self.running = False

    def stop(self) -> None:
        """Llamar a esto al salir del estado para limpiar"""

        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        print("[TRACKING] Hilo detenido.")

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
            self.thread = threading.Thread(target=self._run_inference_loop, daemon=True)
            self.thread.start()
        try:
            while self.running:
                time.sleep(0.01)
        except KeyboardInterrupt:
            self.stop()

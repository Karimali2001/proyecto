#!/usr/bin/env python3
import sys
import os
import cv2
import time
import re
import queue
import threading
import requests
from dotenv import load_dotenv
from pathlib import Path
from loguru import logger
from PIL import Image
import easyocr
import google.genai as genai

# Cargar variables de entorno
load_dotenv()

# Configuración de rutas limpia con pathlib
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parent))
sys.path.append(str(current_dir.parent.parent))

from common.hailo_inference import HailoInfer
from src.core.paddle_ocr_utils import det_postprocess
from src.drivers.camera_driver import CameraDriver
from src.core.priority_queue import AudioPriorityQueue


class OCR:
    """
    OCR manages Hailo for text detection, Gemini API for cloud reading,
    and EasyOCR for offline fallback & continuous sign reading.
    """

    # 🔥 AÑADIMOS AUDIO_QUEUE AL INIT 🔥
    def __init__(
        self, camera_driver, audio_queue=None, det_model_path="assets/ocr_det.hef"
    ):
        self.det_model_path = det_model_path
        self.camera_driver = camera_driver
        self.audio_queue = audio_queue

        # 🔥 SISTEMA ANTICHOQUES (MUTEX) PARA LA CÁMARA 🔥
        self.camera_lock = threading.Lock()

        # Variables del Modo Letreros
        self.continuous_mode = False
        self.last_continuous_read = 0.0

        logger.info("[OCR] Initializing Hailo chip for text detection...")
        try:
            self.detector_hailo = HailoInfer(self.det_model_path, batch_size=1)
            self.model_height, self.model_width, _ = (
                self.detector_hailo.get_input_shape()
            )
            logger.info("[OCR] Hailo-8L ready.")
        except Exception as e:
            logger.error(f"[OCR] Error initializing Hailo: {e}")
            self.detector_hailo = None

        logger.info("[OCR] Cargando modelo EasyOCR (Español) en CPU...")
        self.reader = easyocr.Reader(["es", "en"], gpu=False)
        logger.info("[OCR] EasyOCR listo.")

        logger.info("[OCR] Preparando motor Gemini API...")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning(
                "[OCR] GEMINI_API_KEY no encontrada en las variables de entorno."
            )
        self.gemini_client = genai.Client(api_key=api_key)

        # 🔥 INICIAMOS EL HILO FANTASMA AQUÍ MISMO 🔥
        self.continuous_thread = threading.Thread(
            target=self._continuous_reading_task, daemon=True
        )
        self.continuous_thread.start()

    def toggle_continuous_mode(self):
        """Activa o desactiva la lectura pasiva de carteles."""
        self.continuous_mode = not self.continuous_mode
        if self.continuous_mode:
            self.last_continuous_read = (
                time.time() - 5.0
            )  # Listo para leer de inmediato
        return self.continuous_mode

    def _continuous_reading_task(self):
        """Hilo en segundo plano. Lee carteles usando autoenfoque guiado por IA."""
        while True:
            time.sleep(1.0)

            if not self.continuous_mode:
                continue

            if time.time() - self.last_continuous_read < 5.0:
                continue

            # Verificamos que el usuario no esté usando la cámara con el botón
            if not self.camera_lock.acquire(blocking=False):
                continue

            try:
                # 1. Tomamos un frame de baja resolución en silencio y sin enfocar
                frame_lores = self.camera_driver.capture_array(stream_name="lores")
                if frame_lores is None:
                    continue

                # 2. Le preguntamos a Hailo si hay texto ahí
                det_pp_res, boxes = self._detect_text(frame_lores)

                # Si hay al menos 1 letrero
                if len(det_pp_res) >= 1:
                    logger.info(
                        "[Modo Letreros] Texto detectado a lo lejos. Calculando coordenadas de enfoque..."
                    )

                    # 3. Buscamos el cartel más grande para usarlo como punto de enfoque
                    max_area = 0
                    roi_relativo = None

                    for box in boxes:
                        try:
                            # Calculamos las esquinas de la caja
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                            x_min, x_max = min(xs), max(xs)
                            y_min, y_max = min(ys), max(ys)

                            area = (x_max - x_min) * (y_max - y_min)
                            if area > max_area:
                                max_area = area
                                # Convertimos a porcentajes (0.0 a 1.0) basados en la resolución de Hailo (640x640)
                                roi_relativo = (
                                    x_min / self.model_width,
                                    y_min / self.model_height,
                                    (x_max - x_min) / self.model_width,
                                    (y_max - y_min) / self.model_height,
                                )
                        except Exception:
                            pass

                    # 4. AHORA SÍ: Le pedimos a la cámara que enfoque ESA zona exacta y capturamos
                    self.camera_driver.trigger_autofocus(roi_relativo=roi_relativo)
                    frame_main = self.camera_driver.capture_array(stream_name="main")

                    # Volvemos a detectar el texto, pero ahora en la foto HD perfectamente enfocada
                    det_pp_res_hd, _ = self._detect_text(frame_main)

                    found_texts = []
                    for i, crop in enumerate(det_pp_res_hd):
                        h, w = crop.shape[:2]
                        if h < 20 or w < 20:
                            continue
                        try:
                            resultados = self.reader.readtext(crop, detail=0)
                            if resultados:
                                for txt in resultados:
                                    clean_txt = self._clean_text(txt)
                                    if len(clean_txt) > 2:
                                        found_texts.append(clean_txt)
                        except Exception:
                            pass

                    final_text = " ".join(found_texts)

                    if final_text and self.audio_queue:
                        logger.info(
                            f"[Modo Letreros] 🎯 Letrero nítido leído: {final_text}"
                        )
                        # Lo anunciamos
                        self.audio_queue.put(3, f"Letrero: {final_text}")
                        # Reiniciamos temporizador
                        self.last_continuous_read = time.time()

                    # Restauramos el autoenfoque al centro para el siguiente uso
                    self.camera_driver.trigger_autofocus(roi_relativo=None)

            except Exception as e:
                logger.error(f"[Modo Letreros] Error: {e}")
            finally:
                self.camera_lock.release()

    def check_internet(self):
        try:
            requests.get("https://8.8.8.8", timeout=2)
            return True
        except (requests.ConnectionError, requests.Timeout):
            return False

    def preprocess_image(self, frame):
        resized_frame = cv2.resize(
            frame, (self.model_width, self.model_height), interpolation=cv2.INTER_AREA
        )
        rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        return [rgb_frame]

    def _clean_text(self, text):
        clean = re.sub(r"[>|*•_=~^]", "", text)
        clean = re.sub(r"(?i)\b(?![yaeou])[b-df-hj-np-tv-xz]\b", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _detect_text(self, frame_bgr):
        if self.detector_hailo is None:
            return [], []
        preprocessed_batch = self.preprocess_image(frame_bgr)
        response_queue = queue.Queue()

        def callback(completion_info, bindings_list):
            if completion_info.exception:
                response_queue.put(("error", completion_info.exception))
            else:
                response_queue.put(("success", bindings_list))

        try:
            self.detector_hailo.run(preprocessed_batch, callback)
        except Exception:
            return [], []
        status, hailo_result = response_queue.get()
        if status == "error":
            return [], []
        raw_result = hailo_result[0].output().get_buffer()
        det_pp_res, boxes = det_postprocess(
            raw_result, frame_bgr, self.model_height, self.model_width
        )
        return det_pp_res, boxes

    def _read_with_gemini(self, frame):
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(rgb_frame)
            prompt = (
                "Eres los ojos de una persona ciega. Tu tarea es extraer el texto de esta imagen.\n"
                "REGLAS ESTRICTAS:\n"
                "1. Si el texto está demasiado borroso, desenfocado, cortado o es ilegible, NO inventes nada. Responde ÚNICAMENTE con la palabra: ERROR_BORROSO\n"
                "2. Si es legible, extrae la información de forma clara y concisa. Ve al grano.\n"
                "3. NO uses formato Markdown, ni asteriscos, ni viñetas. Responde en texto plano."
            )
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash", contents=[prompt, img_pil]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"[OCR] Error en Gemini API: {e}")
            return None

    def capture_and_read(self, stream_name="main"):
        if not self.camera_driver:
            return "Cámara no inicializada."

        # 🔥 PONEMOS EL SEGURO: El usuario tiene prioridad absoluta 🔥
        with self.camera_lock:
            max_intentos = 2
            for intento in range(max_intentos):
                logger.info(
                    f"[OCR] Intento de captura {intento + 1} de {max_intentos}..."
                )
                self.camera_driver.trigger_autofocus()
                frame = self.camera_driver.capture_array(stream_name=stream_name)

                if frame is None:
                    continue

                det_pp_res, boxes = self._detect_text(frame)
                if len(det_pp_res) > 0:
                    logger.info(f"[OCR] ¡Texto detectado! ({len(det_pp_res)} zonas).")
                    cv2.imwrite("assets/captured_ocr.jpg", frame)
                    return self.read_text(frame, det_pp_res, boxes)
                else:
                    logger.warning(
                        "[OCR] No se encontró texto en este intento. Reintentando..."
                    )

            return "No encontré ningún texto en la imagen. Intenta de nuevo."

    def read_text(self, frame_bgr, det_pp_res, boxes):
        start_time = time.time()
        if self.check_internet():
            logger.info("[OCR] Wi-Fi detectado. Procesando foto completa con Gemini...")
            gemini_text = self._read_with_gemini(frame_bgr)
            if gemini_text:
                if "ERROR_BORROSO" in gemini_text:
                    return "El texto está borroso. Por favor, centra bien el documento frente a la cámara y vuelve a intentarlo."
                logger.info(
                    f"[OCR] Gemini terminó en {time.time() - start_time:.2f} segundos."
                )
                return gemini_text
            logger.warning("[OCR] Gemini falló o devolvió vacío. Cayendo a EasyOCR...")
        else:
            logger.warning("[OCR] Sin Wi-Fi. Procesando en modo Offline con EasyOCR...")

        found_texts = []
        positioned_crops = []
        for i, crop in enumerate(det_pp_res):
            box = boxes[i]
            try:
                x1, y1 = box[0][0], box[0][1]
            except TypeError:
                x1, y1 = box[0], box[1]
            positioned_crops.append({"crop": crop, "y": y1, "x": x1})

        sorted_crops = sorted(
            positioned_crops, key=lambda c: (round(c["y"] / 20), c["x"])
        )

        for item in sorted_crops:
            crop = item["crop"]
            h, w = crop.shape[:2]
            if h < 15 or w < 15:
                continue
            try:
                resultados = self.reader.readtext(crop, detail=0)
                if resultados:
                    for txt in resultados:
                        clean_txt = self._clean_text(txt)
                        if len(clean_txt) > 2:
                            found_texts.append(clean_txt)
                            logger.info(f"Text read: '{clean_txt}'")
            except Exception as e:
                logger.error(f"[OCR] Error with EasyOCR: {e}")

        final_text = ", ".join(found_texts)
        logger.info(
            f"[OCR] EasyOCR terminó en {time.time() - start_time:.2f} segundos."
        )
        return final_text if final_text else "Hubo un error al leer el texto"

    def close(self):
        if self.detector_hailo:
            self.detector_hailo.close()

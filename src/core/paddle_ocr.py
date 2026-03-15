#!/usr/bin/env python3
import sys
import cv2
import time
import pytesseract
import re
from pathlib import Path
from loguru import logger
import queue

# Configuración de rutas limpia con pathlib
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parent))
sys.path.append(str(current_dir.parent.parent))

from common.hailo_inference import HailoInfer
from src.core.paddle_ocr_utils import det_postprocess
from src.drivers.camera_driver import CameraDriver


class OCR:
    """
    OCR manages the Hailo AI chip for text detection
    and Tesseract for text recognition in Spanish.
    """

    def __init__(self, camera_driver, det_model_path="assets/ocr_det.hef"):
        self.det_model_path = det_model_path
        self.camera_driver = camera_driver

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

        logger.info("[OCR] Tesseract OCR engine (Spanish) ready.")

    def preprocess_image(self, frame):
        """
        Resize and convert frame for Hailo model.
        """
        # INTER_AREA promedia los píxeles. Elimina el ruido que confunde a Hailo.
        resized_frame = cv2.resize(
            frame, (self.model_width, self.model_height), interpolation=cv2.INTER_AREA
        )
        rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        return [rgb_frame]

    def capture_and_read(self, stream_name="main"):
        """
        Captures a frame from the camera, saves it for debugging,
        and processes it to read text.
        """
        if not self.camera_driver:
            return "Cámara no inicializada."

        self.camera_driver.trigger_autofocus()

        frame = self.camera_driver.capture_array(stream_name=stream_name)
        if frame is None:
            return "No se pudo capturar la imagen."

        # Save the captured image for review
        save_path = "assets/captured_ocr.jpg"
        cv2.imwrite(save_path, frame)
        logger.info(f"[OCR] Image saved to {save_path} for review.")

        return self.read_text(frame)

    def _clean_text(self, text):
        """
        Cleans OCR artifacts like misinterpreted bullet points,
        isolated stray characters, and weird symbols.
        """
        # 1. Remove weird symbols often produced by noisy OCR (keep punctuation)
        clean = re.sub(r"[>|*•_=~^]", "", text)

        # 2. Remove isolated single letters (except 'y', 'a', 'e', 'o', 'u' which are valid Spanish words)
        # Fix: The case-insensitive flag (?i) is moved to the start of the pattern.
        clean = re.sub(r"(?i)\b(?![yaeou])[b-df-hj-np-tv-xz]\b", "", clean)

        # 3. Clean up excessive whitespace left behind by the deletions
        clean = re.sub(r"\s+", " ", clean).strip()

        return clean

    def read_text(self, frame_bgr):
        """
        Runs text detection via Hailo, crops the regions, sorts them,
        and uses Tesseract to read the Spanish text.
        """
        if self.detector_hailo is None:
            return "Error de hardware."

        start_time = time.time()
        found_texts = []

        preprocessed_batch = self.preprocess_image(frame_bgr)
        response_queue = queue.Queue()

        def callback(completion_info, bindings_list):
            if completion_info.exception:
                response_queue.put(("error", completion_info.exception))
            else:
                response_queue.put(("success", bindings_list))

        try:
            self.detector_hailo.run(preprocessed_batch, callback)
        except Exception as e:
            logger.error(f"[OCR] Error sending to Hailo: {e}")
            return ""

        status, hailo_result = response_queue.get()

        if status == "error":
            return ""

        raw_result = hailo_result[0].output().get_buffer()

        # Capture original crops and boxes
        det_pp_res, boxes = det_postprocess(
            raw_result, frame_bgr, self.model_height, self.model_width
        )

        if len(det_pp_res) == 0:
            return "No encontré ningún texto en la imagen."

        logger.info(f"[OCR] Hailo detected {len(det_pp_res)} text zones.")

        # --- SMART BOX SORTING ---
        positioned_crops = []
        for i, crop in enumerate(det_pp_res):
            box = boxes[i]

            # Safely extract coordinates regardless of the format
            try:
                # If it comes as a 2D list: [[x1, y1], [x2, y2], ...]
                x1 = box[0][0]
                y1 = box[0][1]
            except TypeError:
                # If it comes as a 1D list: [x, y, width, height]
                x1 = box[0]
                y1 = box[1]

            positioned_crops.append({"crop": crop, "y": y1, "x": x1})

        # Sort: top to bottom (Y) and left to right (X)
        # Tolerance of 20 pixels to align rows
        sorted_crops = sorted(
            positioned_crops, key=lambda c: (round(c["y"] / 20), c["x"])
        )

        # --- STEP 2: RECOGNITION WITH TESSERACT (SPANISH) ---
        for item in sorted_crops:
            crop = item["crop"]

            # 1. Filtro Anti-Basura: Ignorar recortes muy pequeños (ruido)
            h, w = crop.shape[:2]
            if h < 15 or w < 15:
                continue

            try:
                # 2. TRUCO DE MAGIA: Convertir a blanco y negro puro
                # Tesseract necesita alto contraste para no alucinar
                gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

                # Binarización de Otsu (Fuerza el texto a negro y el fondo a blanco)
                _, binary_crop = cv2.threshold(
                    gray_crop, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
                )

                # Si el fondo es oscuro y la letra clara, invertimos los colores
                # (Opcional, pero ayuda mucho con libros oscuros)
                if cv2.countNonZero(binary_crop) > (h * w) / 2:
                    binary_crop = cv2.bitwise_not(binary_crop)

                # 3. Cambiamos el PSM a 6 (Asume un solo bloque de texto uniforme, es más estable que 7)
                config_tesseract = "--psm 6"

                text = pytesseract.image_to_string(
                    binary_crop, lang="spa", config=config_tesseract
                ).strip()

                # Clean the text using Regex
                cleaned_text = self._clean_text(text)

                if (
                    cleaned_text and len(cleaned_text) > 2
                ):  # Exigimos al menos 3 letras para ignorar "NN" o "OS"
                    found_texts.append(cleaned_text)
                    logger.info(f"Text read: '{cleaned_text}'")
            except Exception as e:
                logger.error(f"[OCR] Error with Tesseract: {e}")

        # Join the text
        final_text = ", ".join(found_texts)
        total_time = time.time() - start_time
        logger.info(f"[OCR] Full process in {total_time:.2f} seconds.")

        return final_text

    def close(self):
        """
        Close the Hailo detector.
        """
        if self.detector_hailo:
            self.detector_hailo.close()


if __name__ == "__main__":
    # 1. Instantiate the camera
    camera_driver = CameraDriver(camera_num=1, enable_af=True)  # 64MP camera

    # 2. Configure and start the camera
    camera_driver.configure(video_w=2312, video_h=1736, model_w=640, model_h=640)
    camera_driver.start(preview=False)

    if not Path("assets/ocr_det.hef").exists():
        print("Missing ocr_det.hef model.")
        sys.exit(1)

    ocr = OCR(camera_driver, det_model_path="assets/ocr_det.hef")

    print("\n--- INITIATING READING ---")

    # 3. ¡LA MAGIA DEL MANUAL! Le decimos al lente que enfoque AHORA (sin usar sleep)
    camera_driver.trigger_autofocus()

    # 4. Capturamos la foto
    frame = camera_driver.capture_array(stream_name="main")

    # 5. Picamera2 entrega la imagen en RGB puro. OpenCV funciona en BGR.

    save_path = "assets/debug_64mp.jpg"
    cv2.imwrite(save_path, frame)
    print(f"📸 Imagen nítida y con color real guardada en: {save_path}")

    # 6. Pasamos el frame convertido en BGR al OCR
    result = ocr.read_text(frame)
    print(f"\n[Karim would say]: {result}\n")

    # 7. Clean up
    ocr.close()
    camera_driver.stop()

#!/usr/bin/env python3
import sys
import cv2
import time
import re
from pathlib import Path
from loguru import logger
import queue
import easyocr  # 🔥 IMPORTAMOS EASYOCR

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
    and EasyOCR for text recognition in Spanish.
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

        logger.info("[OCR] Cargando modelo EasyOCR (Español) en CPU...")
        # 🔥 AQUÍ INICIALIZAMOS EL LECTOR DE EASYOCR 🔥
        self.reader = easyocr.Reader(["es", "en"], gpu=False)
        logger.info("[OCR] EasyOCR listo.")

    def preprocess_image(self, frame):
        """
        Resize and convert frame for Hailo model.
        """
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
        clean = re.sub(r"[>|*•_=~^]", "", text)
        clean = re.sub(r"(?i)\b(?![yaeou])[b-df-hj-np-tv-xz]\b", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        return clean

    def read_text(self, frame_bgr):
        """
        Runs text detection via Hailo, crops the regions, sorts them,
        and uses EasyOCR to read the Spanish text.
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
            try:
                x1 = box[0][0]
                y1 = box[0][1]
            except TypeError:
                x1 = box[0]
                y1 = box[1]

            positioned_crops.append({"crop": crop, "y": y1, "x": x1})

        sorted_crops = sorted(
            positioned_crops, key=lambda c: (round(c["y"] / 20), c["x"])
        )

        # --- STEP 2: RECOGNITION WITH EASYOCR (SPANISH) ---
        for item in sorted_crops:
            crop = item["crop"]

            h, w = crop.shape[:2]
            if h < 15 or w < 15:
                continue

            try:
                # 🔥 LA MAGIA DE EASYOCR 🔥
                # detail=0 nos devuelve directo los textos sin coordenadas
                resultados = self.reader.readtext(crop, detail=0)

                if resultados:
                    for texto_leido in resultados:
                        cleaned_text = self._clean_text(texto_leido)

                        if cleaned_text and len(cleaned_text) > 2:
                            found_texts.append(cleaned_text)
                            logger.info(f"Text read: '{cleaned_text}'")
            except Exception as e:
                logger.error(f"[OCR] Error with EasyOCR: {e}")

        final_text = ", ".join(found_texts)
        total_time = time.time() - start_time
        logger.info(f"[OCR] Full process in {total_time:.2f} seconds.")

        return final_text if final_text else "Hubo un error al leer el texto"

    def close(self):
        """
        Close the Hailo detector.
        """
        if self.detector_hailo:
            self.detector_hailo.close()


if __name__ == "__main__":
    camera_driver = CameraDriver(camera_num=1, enable_af=True)
    camera_driver.configure(video_w=2312, video_h=1736, model_w=640, model_h=640)
    camera_driver.start(preview=False)

    if not Path("assets/ocr_det.hef").exists():
        print("Missing ocr_det.hef model.")
        sys.exit(1)

    ocr = OCR(camera_driver, det_model_path="assets/ocr_det.hef")

    print("\n--- INITIATING READING ---")
    camera_driver.trigger_autofocus()
    frame = camera_driver.capture_array(stream_name="main")

    save_path = "assets/debug_64mp.jpg"
    cv2.imwrite(save_path, frame)
    print(f"📸 Imagen nítida y con color real guardada en: {save_path}")

    result = ocr.read_text(frame)
    print(f"\n[Karim would say]: {result}\n")

    ocr.close()
    camera_driver.stop()

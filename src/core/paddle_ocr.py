#!/usr/bin/env python3
import os
import sys
import cv2
import time
import pytesseract
import re
from pathlib import Path
from loguru import logger
import queue

# Adjust this path if necessary so it finds Hailo utilities
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.hailo_inference import HailoInfer
from src.core.paddle_ocr_utils import det_postprocess

from src.drivers.camera_driver import CameraDriver


class OCRDriver:
    """
    OCRDriver manages the Hailo AI chip for text detection
    and Tesseract for text recognition in Spanish.
    """

    def __init__(self, camera_driver, det_model_path="assets/ocr_det.hef"):
        self.det_model_path = det_model_path
        self.camera_driver = camera_driver

        logger.info("[OCRDriver] Initializing Hailo chip for text detection...")
        try:
            self.detector_hailo = HailoInfer(self.det_model_path, batch_size=1)
            self.model_height, self.model_width, _ = (
                self.detector_hailo.get_input_shape()
            )
            logger.info("[OCRDriver] Hailo-8L ready.")
        except Exception as e:
            logger.error(f"[OCRDriver] Error initializing Hailo: {e}")
            self.detector_hailo = None

        logger.info("[OCRDriver] Tesseract OCR engine (Spanish) ready.")

    def preprocess_image(self, frame):
        """
        Resize and convert frame for Hailo model.
        """
        resized_frame = cv2.resize(frame, (self.model_width, self.model_height))
        rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        return [rgb_frame]

    def capture_and_read(self, stream_name="lores"):
        """
        Captures a frame from the camera, saves it for debugging,
        and processes it to read text.
        """
        if not self.camera_driver:
            return "Cámara no inicializada."

        frame = self.camera_driver.capture_array(stream_name=stream_name)
        if frame is None:
            return "No se pudo capturar la imagen."

        try:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        except Exception:
            frame_bgr = frame

        # Save the captured image for review
        save_path = "assets/captured_ocr.jpg"
        cv2.imwrite(save_path, frame_bgr)
        logger.info(f"[OCRDriver] Image saved to {save_path} for review.")

        return self.read_text(frame_bgr)

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
            logger.error(f"[OCRDriver] Error sending to Hailo: {e}")
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

        logger.info(f"[OCRDriver] Hailo detected {len(det_pp_res)} text zones.")

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

            if crop.size == 0:
                continue

            try:
                # psm 7 to read line by line
                config_tesseract = "--psm 7"
                text = pytesseract.image_to_string(
                    crop, lang="spa", config=config_tesseract
                ).strip()

                # Clean the text using Regex
                cleaned_text = self._clean_text(text)

                if cleaned_text and len(cleaned_text) > 1:
                    found_texts.append(cleaned_text)
                    logger.info(f"Text read: '{cleaned_text}'")
            except Exception as e:
                logger.error(f"[OCRDriver] Error with Tesseract: {e}")

        # Join the text
        final_text = ", ".join(found_texts)
        total_time = time.time() - start_time
        logger.info(f"[OCRDriver] Full process in {total_time:.2f} seconds.")

        return final_text

    def close(self):
        """
        Close the Hailo detector.
        """
        if self.detector_hailo:
            self.detector_hailo.close()


if __name__ == "__main__":
    # 1. Instantiate the camera
    camera_driver = CameraDriver()

    # 2. Configure and start the camera
    # Using 640x640 for the model size since that's what the Hailo model expects
    camera_driver.configure(video_w=1280, video_h=960, model_w=640, model_h=640)
    camera_driver.start(preview=False)

    # Wait a tiny bit for the camera sensor to warm up and adjust exposure
    time.sleep(1)

    if not Path("assets/ocr_det.hef").exists():
        print("Missing ocr_det.hef model.")
        sys.exit(1)

    ocr = OCRDriver(camera_driver, det_model_path="assets/ocr_det.hef")

    print("\n--- INITIATING READING ---")

    # 3. Capture the frame from the camera
    frame = camera_driver.capture_array(stream_name="lores")

    # 4. Pass the frame to the OCR driver
    result = ocr.read_text(frame)
    print(f"\n[Karim would say]: {result}\n")

    # 5. Clean up
    ocr.close()
    camera_driver.stop()

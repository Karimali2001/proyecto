import json
from pathlib import Path

from src.drivers.hailo_driver import HailoDriver
from src.drivers.camera_driver import CameraDriver

base_path = Path.cwd()

model_path = str(base_path / "assets" / "yolov8s.hef")
labels_path = str(base_path / "assets" / "coco.txt")
translations_path = str(base_path / "assets" / "translations.json")

with open(translations_path, "r") as f:
    translations = json.load(f)

video_w, video_h = 1280, 960


class ObjectDetector:
    def __init__(self):
        
        self.last_detection = []
        
    def getLastDetection(self):
        return self.last_detection

    def object_detection_thread(self):

        # ******** Initializing hailo and camera
        try:
            camera = CameraDriver()
            hailo = HailoDriver(model_path, labels_path)
        except Exception as e:
            print(f"[Main]: Error initializing camera and model: {e}")

        hailo.start()

        model_h, model_w, _ = hailo.get_input_shape()

        camera.configure(video_w, video_h, model_w, model_h)

        camera.start()

        # ****************

        # ******* Starting loop

        while True:
            try:
                frame = camera.capture_array()

                detections = hailo.infer(frame)

                detections = hailo.extract_detections(detections, video_w, video_h)

                objects_frame = []

                if len(detections) != 0:
                    for detection in detections:
                        # Get all the data from the detection
                        name, bbox, score = detection

                        # Get the position of the detected object
                        x0, y0, x1, y1 = bbox

                        # Calculate the center of the object
                        x_center = (x0 + x1) / 2

                        # Calculate the where is the object in x in the screen (0.00-1.00)
                        ratio = x_center / video_w

                        # 9 cause we start from the left(9)
                        # 6 cause is the the difference between 9 and 6(right)
                        hour = round(9 + (ratio * 6))

                        if hour > 12:
                            hour -= 12

                        translated_name = translations.get(name, name)

                        message = f"{translated_name} a las {hour}"

                        objects_frame.append(message)

                # If Captured objects put last detection
                # if nothing is captured empty
                self.last_detection = objects_frame
            except Exception as e:
                camera.stop()
                print(f"\n[Object Detection] Error: {e}")
                break

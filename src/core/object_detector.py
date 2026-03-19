import json
from pathlib import Path

base_path = Path.cwd()

translations_path = str(base_path / "assets" / "translations.json")

with open(translations_path, "r") as f:
    translations = json.load(f)


class ObjectDetector:
    def __init__(self, camera_driver, hailo_driver, video_w=1280, video_h=960):
        self.camera_driver = camera_driver
        self.hailo_driver = hailo_driver
        self.last_detection = []
        self.raw_detections = []
        self.video_w = video_w
        self.video_h = video_h

    def getLastDetection(self):
        return self.last_detection

    def getRawDetections(self):
        return self.raw_detections

    def setRawDetections(self, detections):
        self.raw_detections = detections

    def process_frame(self, frame):
        try:
            detections = self.hailo_driver.infer(frame)
            detections = self.hailo_driver.extract_detections(
                detections, self.video_w, self.video_h
            )

            self.setRawDetections(detections)

            objects_frame = []

            if len(detections) != 0:
                for detection in detections:
                    name, bbox, score = detection
                    x0, y0, x1, y1 = bbox
                    x_center = (x0 + x1) / 2
                    ratio = x_center / self.video_w

                    hour = round(9 + (ratio * 6))
                    if hour > 12:
                        hour -= 12

                    translated_name = translations.get(name, name)
                    message = f"{translated_name} a las {hour}"
                    objects_frame.append(message)

            self.last_detection = objects_frame

        except Exception as e:
            print(f"\n[Object Detection] Error: {e}")
            self.last_detection = []
            self.setRawDetections([])
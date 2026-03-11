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
        self.video_w = video_w
        self.video_h = video_h

    def getLastDetection(self):
        return self.last_detection

    def object_detection_thread(self):

        # ****************

        # ******* Starting loop

        while True:
            try:
                frame = self.camera_driver.capture_array()

                detections = self.hailo_driver.infer(frame)

                detections = self.hailo_driver.extract_detections(
                    detections, self.video_w, self.video_h
                )

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
                        ratio = x_center / self.video_w

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
                self.camera_driver.stop()
                print(f"\n[Object Detection] Error: {e}")
                break

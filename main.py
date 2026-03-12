import time
import json

from threading import Thread
from pathlib import Path


from src.core.object_detector import ObjectDetector
from src.core.obstacle_detector import ObstacleDetector
from src.core.menu_controller import MenuController
from src.core.paddle_ocr import OCRDriver
from src.drivers.audio_driver import Audio
from src.core.priority_queue import AudioPriorityQueue
from src.drivers.camera_driver import CameraDriver
from src.drivers.hailo_driver import HailoDriver
from src.core.navigation import Navigation


base_path = Path.cwd()


model_path = str(base_path / "assets" / "yolov8s.hef")
labels_path = str(base_path / "assets" / "coco.txt")

video_w, video_h = 1280, 960


audio = Audio()
audio_queue = AudioPriorityQueue(audio)


def audio_consumer_thread():
    """This is the only thread aloud to speak"""
    """"Consumes text from the queue that needs to be logged"""

    while True:
        priority, message = audio_queue.get()
        print(f"\n[Simulated Audio] Playing Priority {priority}: {message}")

        # Check if the message is a JSON string intended for spatial sound
        if (
            isinstance(message, str)
            and message.startswith("{")
            and message.endswith("}")
        ):
            try:
                data = json.loads(message)
                if "position" in data:
                    kwargs = {"position": data["position"]}
                    if "frequencyCenter" in data:
                        kwargs["frequencyCenter"] = data["frequencyCenter"]
                    if "frequencySide" in data:
                        kwargs["frequencySide"] = data["frequencySide"]

                    audio.play_spatial_sound(**kwargs)
                    time.sleep(0.5)
                else:
                    audio.speak(message)
            except json.JSONDecodeError:
                audio.speak(message)
        else:
            audio.speak(message)

        audio_queue.task_done()


if __name__ == "__main__":
    # ******** Initializing hailo and camera
    try:
        camera_driver = CameraDriver()
        hailo_driver = HailoDriver(model_path, labels_path)

        hailo_driver.start()

        model_h, model_w, _ = hailo_driver.get_input_shape()

        camera_driver.configure(video_w, video_h, model_w, model_h)

        camera_driver.start()
    except Exception as e:
        print(f"[Main]: Error initializing camera and model: {e}")

    object_detector = ObjectDetector(camera_driver, hailo_driver)
    # obstacle_detector = ObstacleDetector(audio_queue)

    try:
        ocr_driver = OCRDriver(
            camera_driver, det_model_path=str(base_path / "assets" / "ocr_det.hef")
        )
    except Exception as e:
        print(f"[Main]: Error initializing OCR: {e}")
        ocr_driver = None

    navigation = Navigation()

    menuController = MenuController(
        object_detector, navigation, audio_queue, ocr_driver
    )

    t_audio = Thread(target=audio_consumer_thread, daemon=True)
    t_camera = Thread(target=object_detector.object_detection_thread, daemon=True)
    # t_tof = Thread(target=obstacle_detector.detect_hole_thread, daemon=True)
    t_navigation = Thread(target=navigation.thread_update_location, daemon=True)

    t_audio.start()
    t_camera.start()
    # t_tof.start()
    t_navigation.start()

    try:
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("[Main] Stopped Main")

import time

from queue import Queue
from threading import Thread


from src.core.object_detector import ObjectDetector
from src.core.obstacle_detector import ObstacleDetector
from src.core.menu_controller import MenuController
from src.drivers.audio_driver import Audio
from src.core.priority_queue import AudioPriorityQueue


audio = Audio()
audio_queue = AudioPriorityQueue(audio)


def audio_consumer_thread():
    """This is the only thread aloud to speak"""
    """"Consumes text from the queue that needs to be logged"""

    while True:
        priority, message = audio_queue.get()
        print(f"\n[Simulated Audio] Playing Priority {priority}: {message}")
        audio.speak(message)


if __name__ == "__main__":
    object_detector = ObjectDetector()
    obstacle_detector = ObstacleDetector(audio_queue)

    menuController = MenuController(object_detector, audio_queue)

    t_audio = Thread(target=audio_consumer_thread, daemon=True)
    t_camera = Thread(target=object_detector.object_detection_thread, daemon=True)
    t_tof = Thread(target=obstacle_detector.detect_hole_thread, daemon=True)

    t_audio.start()
    t_camera.start()
    t_tof.start()

    try:
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("[Main] Stopped Main")

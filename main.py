from queue import Queue
from threading import Thread


from src.core.object_detector import ObjectDetector
from src.core.obstacle_detector import ObstacleDetector


detectionsQueue = Queue()


def audio_consumer_thread():
    """This is the only thread aloud to speak"""
    """"Consumes text from the queue that needs to be logged"""

    while True:
        message = detectionsQueue.get()
        print([f"\n[Simulated Audio] Playing: {message}"])
        detectionsQueue.task_done()


if __name__ == "__main__":
    object_detector = ObjectDetector()
    obstacle_detector = ObstacleDetector(detectionsQueue)

    t_audio = Thread(target=audio_consumer_thread, daemon=True)
    t_camera = Thread(target=object_detector.object_detection_thread, daemon=True)
    t_tof = Thread(target=obstacle_detector.detect_hole_thread, daemon=True)

    t_audio.start()
    t_camera.start()
    t_tof.start()

    try:
        while True:
            input("[Main] Press ENTER to detect objects")

            if len(object_detector.getLastDetection()) == 0:
                detectionsQueue.put("Camino Despejado")
            else:
                complete_frase = ",".join(object_detector.getLastDetection())
                detectionsQueue.put(complete_frase)

    except KeyboardInterrupt:
        print("[Main] Stopped Main")

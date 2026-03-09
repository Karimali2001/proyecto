from queue import Queue
from threading import Thread
import time


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


def detect_hole_thread():
    try:
        obstacleDetector = ObstacleDetector()

        detected = False

        while True:
            matrix = obstacleDetector.tof.get_matrix()
            if matrix is not None:
                """
                *************************
                Hole
                *************************
                """
                is_hole, pos_hole = obstacleDetector.detect_hole(matrix)

                if is_hole and not detected:
                    detectionsQueue.put("¡Cuidado! Hay un agujero: " + pos_hole)
                    time.sleep(4)
                    detected = True
                elif not is_hole:
                    detected = False

            time.sleep(0.005)
    except Exception as e:
        print(f"[Tof] Error: {e}")


if __name__ == "__main__":
    object_detector = ObjectDetector()

    t_audio = Thread(target=audio_consumer_thread, daemon=True)
    t_camera = Thread(target=object_detector.object_detection_thread, daemon=True)
    # t_tof = Thread(target=detect_hole_thread, daemon=True)

    t_audio.start()
    t_camera.start()
    # t_tof.start()

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

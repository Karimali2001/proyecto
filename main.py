import json


from queue import Queue
from pathlib import Path
from threading import Thread
import time
import random


from src.drivers.hailo_driver import HailoDriver
from src.drivers.camera_driver import CameraDriver
from src.drivers.tof import TofDriver

base_path = Path.cwd()

model_path = str(base_path / "assets" / "yolov8s.hef")
labels_path = str(base_path / "assets" / "coco.txt")
translations_path = str(base_path / "assets" / "translations.json")

video_w, video_h = 1280, 960

detectionsQueue = Queue()

last_detection = []

with open(translations_path, "r") as f:
    translations = json.load(f)


def audio_consumer_thread():
    """This is the only thread aloud to speak"""
    """"Consumes text from the queue that needs to be logged"""

    while True:
        message = detectionsQueue.get()
        print([f"\n[Simulated Audio] Playing: {message}"])
        detectionsQueue.task_done()


def object_detection_thread():

    global last_detection

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
            last_detection = objects_frame
        except Exception as e:
            camera.stop()
            print(f"\n[Object Detection] Error: {e}")
            break


def object_detection_thread_dummy():

    global last_detection

    dummy = ["carro a las 12", "persona a las 7", "vaso a las 5"]

    while True:
        try:
            last_detection = [random.choice(dummy)]
            time.sleep(10)
            pass
        except Exception as e:
            print(f"\n[Object Detection] Error: {e}")
            break


def detect_hole_thread():
    try:
        tof = TofDriver()

        detected = False

        while True:
            matrix = tof.get_matrix()
            if matrix is not None:
                """
                *************************
                Hole
                *************************
                """
                is_hole, pos_hole = tof.detect_hole(matrix)

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
    t_audio = Thread(target=audio_consumer_thread, daemon=True)
    t_camera = Thread(target=object_detection_thread_dummy, daemon=True)
    t_tof = Thread(target=detect_hole_thread, daemon=True)

    t_audio.start()
    t_camera.start()
    t_tof.start()

    try:
        while True:
            input("[Main] Press ENTER to detect objects")

            if len(last_detection) == 0:
                detectionsQueue.put("Camino Despejado")
            else:
                complete_frase = ",".join(last_detection)
                detectionsQueue.put(complete_frase)

    except KeyboardInterrupt:
        print("[Main] Stopped Main")

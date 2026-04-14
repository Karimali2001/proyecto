import time
import cv2

from threading import Thread
from pathlib import Path


from src.core.object_detection.object_detector import ObjectDetector
from src.core.hole_detector import HoleDetector
from src.core.menu_controller import MenuController
from src.core.ocr.paddle_ocr import OCR
from src.drivers.audio_driver import Audio
from src.core.priority_queue import AudioPriorityQueue
from src.drivers.camera_driver import CameraDriver
from src.drivers.hailo_driver import HailoDriver
from src.core.navigation import Navigation
from src.core.aerial_obstacle_detector import AerialObstacleDetector
from src.ui.audio_interface import AudioInterface


base_path = Path.cwd()


detection_model_path = str(base_path / "assets" / "yolov8s.hef")
labels_path = str(base_path / "assets" / "coco.txt")

ocr_det_model_path = str(base_path / "assets" / "ocr_det.hef")

depth_model_path = str(base_path / "assets" / "scdepthv3.hef")

video_w, video_h = 1280, 960


audio_driver = Audio()
audio_interface = AudioInterface(audio_driver)
audio_queue = AudioPriorityQueue(audio_interface)


# Añade 'depth_driver' a los argumentos del hilo
def frame_producer_thread(
    camera_driver,
    object_detector,
    aerial_obstacle_detector,
    hole_detector,
    depth_driver,
    navigation,
):

    depth_h, depth_w, _ = depth_driver.get_input_shape()

    while True:
        try:
            frame = camera_driver.capture_array()

            if frame is not None:
                # --- A: OBJECT DETECTION ---
                object_detector.process_frame(frame)
                raw_detections = object_detector.getRawDetections()

                # --- B: Depth Inference ---
                frame_resized = cv2.resize(frame, (depth_w, depth_h))
                raw_output = depth_driver.infer(frame_resized)
                depth_array = depth_driver.extract_depth_map(raw_output)

                if depth_array is not None:
                    # --- C: Distribute depth matrix ---
                    aerial_obstacle_detector.process_frame(
                        frame_resized,
                        depth_array,
                        raw_detections,
                        current_heading=navigation.compass,
                    )

                    hole_detector.process_frame(
                        frame_resized, depth_array, current_heading=navigation.compass
                    )

        except Exception as e:
            print(f"[Vision Thread] Error: {e}")
            break


if __name__ == "__main__":
    # ******** Initialize hardware drivers and core components

    try:
        # Initialize camera drivers
        global_shutter_camera = CameraDriver(camera_num=0, enable_af=False)
        owlsight64mp_camera = CameraDriver(camera_num=1, enable_af=True)

        # Initialize Hailo driver for object detection
        object_detection_driver = HailoDriver(detection_model_path, labels_path)
        object_detection_driver.start()

        # Get model input shape for camera configuration
        model_h, model_w, _ = object_detection_driver.get_input_shape()

        # Configure cameras with model input shape
        global_shutter_camera.configure(video_w, video_h, model_w, model_h)
        owlsight64mp_camera.configure(video_w, video_h, model_w, model_h)

        # Start camera streams (no preview)
        global_shutter_camera.start(preview=False)
        owlsight64mp_camera.start(preview=False)
    except Exception as e:
        print(f"[Main]: Error initializing camera and model: {e}")

    # Initialize OCR driver
    try:
        ocr_driver = OCR(
            owlsight64mp_camera,
            audio_queue,
            det_model_path=str(base_path / "assets" / "ocr_det.hef"),
        )
    except Exception as e:
        print(f"[Main]: Error initializing OCR: {e}")
        ocr_driver = None

    # Initialize depth model driver
    try:
        depth_driver = HailoDriver(depth_model_path, labels_path="")
        depth_driver.start()
    except Exception as e:
        print(f"[Main]: Error initializing Depth Model: {e}")
        depth_driver = None

    # Initialize depth detector
    aerial_obstacle_detector = AerialObstacleDetector(
        hailo_driver=depth_driver,
        audio_queue=audio_queue,
        user_height_mm=1400,
        camera_height_mm=1100,
    )

    # Initialize object detector
    object_detector = ObjectDetector(
        global_shutter_camera, object_detection_driver, audio_queue
    )

    # Initialize obstacle detector
    hole_detector = HoleDetector(
        hailo_driver=depth_driver,
        audio_queue=audio_queue,
        user_height_mm=1780,
        camera_height_mm=1220,
    )

    # Initialize navigation logic
    navigation = Navigation(audio_queue)

    # Initialize menu controller
    menuController = MenuController(
        object_detector,
        navigation,
        hole_detector,
        audio_queue,
        ocr_driver,
        aerial_obstacle_detector,
    )

    t_audio = Thread(
        target=audio_interface.consume_queue_forever,
        args=(audio_queue,),
        daemon=True,
    )
    t_camera = Thread(
        target=frame_producer_thread,
        args=(
            global_shutter_camera,
            object_detector,
            aerial_obstacle_detector,
            hole_detector,
            depth_driver,
            navigation,
        ),
        daemon=True,
    )

    t_navigation = Thread(target=navigation.thread_update_location, daemon=True)
    t_imu = Thread(target=navigation.thread_update_imu, daemon=True)

    t_audio.start()
    t_camera.start()
    t_navigation.start()
    t_imu.start()

    try:
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("[Main] Stopped Main")

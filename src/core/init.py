import argparse
from .state import State
from src.drivers.camera_driver import CameraDriver
from src.drivers.hailo_driver import HailoDriver
from src.drivers.audio_output_driver import AudioOutputDriver

class InitState(State):
    def process(self) -> None:
        # Avoid circular imports usually, but here specifically we need the next state
        from .run_tracking import RunTracking

        print("[INIT] Inicializando recursos...")

        # 1. Parse Arguments (Can be moved to config loader later)
        parser = argparse.ArgumentParser(description="Detection Example")
        default_model_path = "/home/kness/Desktop/Hailo-Application-Code-Examples/runtime/python/object_detection/yolov8s.hef"
        default_labels_path = "/home/kness/Desktop/Hailo-Application-Code-Examples/runtime/python/object_detection/coco.txt"
        
        parser.add_argument("-m", "--model", default=default_model_path)
        parser.add_argument("-l", "--labels", default=default_labels_path)
        parser.add_argument("-s", "--score_thresh", type=float, default=0.5)
        args, _ = parser.parse_known_args() # Use known args to avoid conflict with main if any

        # 2. Initialize Hailo Driver
        try:
            self.context.hailo_driver = HailoDriver(args.model, args.labels, args.score_thresh)
            self.context.hailo_driver.start()
            model_h, model_w, _ = self.context.hailo_driver.get_input_shape()
        except Exception as e:
            print(f"[INIT] Error initializing Hailo: {e}")
            # Transition to ErrorState?
            return

        # 3. Initialize Camera Driver
        try:
            video_w, video_h = 1280, 960
            self.context.camera_driver = CameraDriver()
            self.context.camera_driver.configure(video_w, video_h, model_w, model_h)
            self.context.camera_driver.start(preview=True)
        except Exception as e:
            print(f"[INIT] Error initializing Camera: {e}")
            return

        try:
            self.context.audio_output_driver = AudioOutputDriver()
        except Exception as e:
            print(f"[INIT] Error initializing audio output: {e}")
            return
        print("[INIT] Todo listo. Cambiando a Tracking.")
        self.context.transition_to(RunTracking())
        
    
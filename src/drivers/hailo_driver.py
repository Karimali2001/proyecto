import numpy as np
import queue

# Necessary to import HailoInfer
import os
import sys

# Adjust this path depending on where your HailoDriver file is located with respect to common/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.hailo_inference import HailoInfer


class HailoDriver:
    def __init__(self, model_path: str, labels_path: str, threshold: float = 0.5):
        self.model_path = model_path
        self.labels_path = labels_path
        self.threshold = threshold
        self.device = None
        self.class_names = []

        # These variables will save the dimensions that the model needs
        self.model_height = 0
        self.model_width = 0

        # Load labels immediately
        self._load_labels()

    def _load_labels(self):
        try:
            with open(self.labels_path, "r", encoding="utf-8") as f:
                self.class_names = f.read().splitlines()
        except FileNotFoundError:
            print(f"Warning: Labels file not found at {self.labels_path}")

    def start(self):
        """Initializes the Hailo device context using HailoInfer."""
        try:
            print(f"[HailoDriver] Starting Hailo chip with model: {self.model_path}")
            # We initialize with batch_size = 1 because we will process frame by frame
            self.device = HailoInfer(self.model_path, batch_size=1)

            # We save the shape that the model requires (e.g. 640x640x3)
            self.model_height, self.model_width, _ = self.device.get_input_shape()
            print("[HailoDriver] Hailo-8L successfully initialized.")

        except Exception as e:
            print(f"[HailoDriver] Error starting HailoInfer: {e}")
            self.device = None

        return self

    def get_input_shape(self):
        if not self.device:
            raise RuntimeError("Hailo device not initialized. Call start() first.")
        # returns height, width, channels
        return self.device.get_input_shape()

    def infer(self, frame):
        """
        Executes inference on the frame.
        The frame must come with basic pre-processing already done
        (resize to self.model_width x self.model_height and in RGB format).
        """
        if not self.device:
            return None

        # HailoInfer expects a "batch" (list of images)
        preprocessed_batch = [frame]

        # We use a Queue to wait for the asynchronous response and make it synchronous
        response_queue = queue.Queue()

        def my_callback(completion_info, bindings_list):
            if completion_info.exception:
                response_queue.put(("error", completion_info.exception))
            else:
                response_queue.put(("success", bindings_list))

        try:
            self.device.run(preprocessed_batch, my_callback)
        except Exception as e:
            print(f"[HailoDriver] Error sending frame to Hailo: {e}")
            return None

        # We wait for Hailo to finish and put the result in the queue
        status, hailo_result = response_queue.get()

        if status == "error":
            print(f"[HailoDriver] Internal inference error: {hailo_result}")
            return None

        bindings = hailo_result[0]

        # Depending on the model, it may return 1 buffer or multiple (like YOLO models)
        if len(bindings._output_names) == 1:
            raw_result = bindings.output().get_buffer()
            # We encapsulate in a list to emulate the structure expected by extract_detections
            return [raw_result]
        else:
            # If the model gives multiple outputs, we group them in a dictionary
            raw_result = {
                name: np.expand_dims(bindings.output(name).get_buffer(), axis=0)
                for name in bindings._output_names
            }
            # WARNING: Depending on the detection model you use (YOLOv8, YOLOv5),
            # how these dictionaries are parsed changes drastically.
            return raw_result

    def extract_detections(self, hailo_output, video_w, video_h):
        results = []
        if not hailo_output or len(hailo_output) == 0:
            return results

        try:
            # hailo_output[0] is the list of 80 classes
            detections_by_class = hailo_output[0]

            for class_id, class_detections in enumerate(detections_by_class):
                # If there are no detections for this class, the array is empty (shape 0,5)
                if len(class_detections) == 0:
                    continue

                for detection in class_detections:
                    score = detection[4]

                    if score >= self.threshold:
                        # Hailo NMS exports by default: ymin, xmin, ymax, xmax
                        y0, x0, y1, x1 = (
                            detection[0],
                            detection[1],
                            detection[2],
                            detection[3],
                        )

                        bbox = (
                            int(x0 * video_w),
                            int(y0 * video_h),
                            int(x1 * video_w),
                            int(y1 * video_h),
                        )

                        name = (
                            self.class_names[class_id]
                            if class_id < len(self.class_names)
                            else str(class_id)
                        )
                        results.append((name, bbox, score))

        except Exception as e:
            print(f"[HailoDriver] Error parsing Hailo output: {e}")

        return results

    def extract_depth_map(self, hailo_output):
        """
        Extracts and formats the output of the scdepthv3 model.
        Returns the 2D depth matrix (256x320) ready for analysis.
        """
        if not hailo_output or len(hailo_output) == 0:
            return None

        try:
            # In scdepthv3, the output is usually a single flat array.
            raw_depth = hailo_output[0]

            # The Hailo scdepthv3 model produces a 256x320 matrix
            # We resize the flat array to the correct 2D shape.
            depth_array = np.array(raw_depth).reshape((256, 320))

            return depth_array

        except Exception as e:
            print(f"[HailoDriver] Error processing depth map: {e}")
            return None

    def stop(self):
        if self.device:
            self.device.close()
            self.device = None

from picamera2.devices import Hailo
import numpy as np

class HailoDriver:
    def __init__(self, model_path: str, labels_path: str, threshold: float = 0.8):
        self.model_path = model_path
        self.labels_path = labels_path
        self.threshold = threshold
        self.device = None
        self.class_names = []
        
        # Load labels immediately
        self._load_labels()

    def _load_labels(self):
        try:
            with open(self.labels_path, 'r', encoding="utf-8") as f:
                self.class_names = f.read().splitlines()
        except FileNotFoundError:
            print(f"Warning: Labels file not found at {self.labels_path}")

    def start(self):
        """Initializes the Hailo device context."""
        self.device = Hailo(self.model_path)
        # We return self to allow usage in 'with' blocks if needed, 
        # though here we manage it manually for the state machine.
        return self

    def get_input_shape(self):
        if not self.device:
            raise RuntimeError("Hailo device not initialized. Call start() first.")
        # returns height, width, channels
        return self.device.get_input_shape()

    def infer(self, frame):
        if not self.device:
            return []
        return self.device.run(frame)

    def extract_detections(self, hailo_output, video_w, video_h, ):
        """
        Parses raw Hailo output into a list of (class_name, bbox, score).
        bbox is (x0, y0, x1, y1)
        """
        results = []
        # Checks if valid output
        if hailo_output is None: 
            return results

        for class_id, class_detections in enumerate(hailo_output):
            for detection in class_detections:
                score = detection[4]
                if score >= self.threshold:
                    y0, x0, y1, x1 = detection[:4]
                    # Convert normalized coordinates to pixel coordinates
                    bbox = (int(x0 * video_w), int(y0 * video_h), int(x1 * video_w), int(y1 * video_h))
                    name = self.class_names[class_id] if class_id < len(self.class_names) else str(class_id)
                    results.append((name, bbox, score))
        return results
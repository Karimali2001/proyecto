import numpy as np
import queue

# Necesario para importar HailoInfer
import os
import sys

# Ajusta esta ruta según dónde esté tu archivo HailoDriver con respecto a common/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.hailo_inference import HailoInfer


class HailoDriver:
    def __init__(self, model_path: str, labels_path: str, threshold: float = 0.5):
        self.model_path = model_path
        self.labels_path = labels_path
        self.threshold = threshold
        self.device = None
        self.class_names = []

        # Estas variables guardarán las dimensiones que el modelo necesita
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
            print(f"[HailoDriver] Iniciando chip Hailo con modelo: {self.model_path}")
            # Inicializamos con batch_size = 1 porque procesaremos frame por frame
            self.device = HailoInfer(self.model_path, batch_size=1)

            # Guardamos la forma que requiere el modelo (ej. 640x640x3)
            self.model_height, self.model_width, _ = self.device.get_input_shape()
            print("[HailoDriver] Hailo-8L inicializado exitosamente.")

        except Exception as e:
            print(f"[HailoDriver] Error al iniciar HailoInfer: {e}")
            self.device = None

        return self

    def get_input_shape(self):
        if not self.device:
            raise RuntimeError("Hailo device not initialized. Call start() first.")
        # returns height, width, channels
        return self.device.get_input_shape()

    def infer(self, frame):
        """
        Ejecuta la inferencia sobre el frame.
        El frame debe venir ya con el pre-procesamiento básico
        (resize a self.model_width x self.model_height y en formato RGB).
        """
        if not self.device:
            return None

        # HailoInfer espera un "batch" (lista de imágenes)
        preprocessed_batch = [frame]

        # Usamos una Queue para esperar la respuesta asíncrona y hacerla síncrona
        buzon_respuesta = queue.Queue()

        def mi_callback(completion_info, bindings_list):
            if completion_info.exception:
                buzon_respuesta.put(("error", completion_info.exception))
            else:
                buzon_respuesta.put(("exito", bindings_list))

        try:
            self.device.run(preprocessed_batch, mi_callback)
        except Exception as e:
            print(f"[HailoDriver] Error al enviar frame a Hailo: {e}")
            return None

        # Esperamos a que Hailo termine y ponga el resultado en la cola
        estado, resultado_hailo = buzon_respuesta.get()

        if estado == "error":
            print(f"[HailoDriver] Error interno de inferencia: {resultado_hailo}")
            return None

        bindings = resultado_hailo[0]

        # Dependiendo del modelo, puede devolver 1 buffer o múltiples (como los YOLO)
        if len(bindings._output_names) == 1:
            raw_result = bindings.output().get_buffer()
            # Encapsulamos en una lista para emular la estructura esperada por extract_detections
            return [raw_result]
        else:
            # Si el modelo bota múltiples salidas, las agrupamos en un diccionario
            raw_result = {
                name: np.expand_dims(bindings.output(name).get_buffer(), axis=0)
                for name in bindings._output_names
            }
            # OJO: Dependiendo del modelo de detección que uses (YOLOv8, YOLOv5),
            # el cómo se parsean estos diccionarios cambia drásticamente.
            return raw_result

    def extract_detections(self, hailo_output, video_w, video_h):
        results = []
        if not hailo_output or len(hailo_output) == 0:
            return results

        try:
            # hailo_output[0] es la lista de 80 clases
            detections_by_class = hailo_output[0]

            for class_id, class_detections in enumerate(detections_by_class):
                # Si no hay detecciones para esta clase, el array está vacío (shape 0,5)
                if len(class_detections) == 0:
                    continue

                for detection in class_detections:
                    score = detection[4]

                    if score >= self.threshold:
                        # Hailo NMS exporta por defecto: ymin, xmin, ymax, xmax
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
            print(f"[HailoDriver] Error parseando salida de Hailo: {e}")

        return results

    def extract_depth_map(self, hailo_output):
        """
        Extrae y da formato a la salida del modelo scdepthv3.
        Retorna la matriz de profundidad 2D (256x320) lista para analizar.
        """
        if not hailo_output or len(hailo_output) == 0:
            return None

        try:
            # En scdepthv3, la salida suele ser un solo array plano.
            raw_depth = hailo_output[0]

            # El modelo scdepthv3 de Hailo produce una matriz de 256x320
            # Redimensionamos el array plano a la forma 2D correcta.
            depth_array = np.array(raw_depth).reshape((256, 320))

            return depth_array

        except Exception as e:
            print(f"[HailoDriver] Error procesando mapa de profundidad: {e}")
            return None

    def stop(self):
        if self.device:
            self.device.close()
            self.device = None

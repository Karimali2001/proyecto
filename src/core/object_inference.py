"""
Object Inference Module
Pipeline: Captura -> Redimensionar -> Normalizar -> Inferir -> Post-procesar
Basado en diagrama de actividades proporcionado
"""

import logging
import time
from typing import Optional, List, Dict, Tuple
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class Detection:
    """Clase para representar una detección de objeto"""
    
    def __init__(self, class_id: int, class_name: str, confidence: float, bbox: Tuple[int, int, int, int]):
        """
        Args:
            class_id: ID de la clase COCO
            class_name: Nombre de la clase
            confidence: Confianza de la detección (0-1)
            bbox: Bounding box (x1, y1, x2, y2)
        """
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox
        
    def get_center(self) -> Tuple[int, int]:
        """Retorna el centro del bounding box"""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)
    
    def is_in_aerial_zone(self, zone_y_max: int) -> bool:
        """Verifica si el objeto está en zona aérea (parte superior)"""
        _, y1, _, y2 = self.bbox
        center_y = (y1 + y2) // 2
        return center_y < zone_y_max


class ObjectInference:
    """Motor de inferencia de objetos usando YOLOv8s en Hailo-8L"""
    
    def __init__(self, hailo_driver, config: dict):
        """
        Args:
            hailo_driver: Instancia del HailoDriver
            config: Configuración (MODEL_INPUT_SIZE, CONFIDENCE_THRESHOLD, etc.)
        """
        self.hailo = hailo_driver
        self.config = config
        
        self.input_size = config['MODEL_INPUT_SIZE']
        self.conf_threshold = config['CONFIDENCE_THRESHOLD']
        self.nms_threshold = config['NMS_THRESHOLD']
        
        # COCO class names (80 clases)
        self.class_names = self._load_coco_names()
        
        # Métricas de rendimiento
        self.fps = 0.0
        self.avg_inference_time = 0.0
        
    def _load_coco_names(self) -> List[str]:
        """Carga nombres de clases COCO"""
        # 80 clases de COCO dataset
        return [
            'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 
            'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
            'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
            'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
            'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
            'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
            'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
            'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
            'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
            'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
            'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
            'toothbrush'
        ]
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Pre-procesa imagen para inferencia
        Pipeline: Redimensionar -> Normalizar
        
        Args:
            image: Imagen RGB (H, W, 3)
        
        Returns:
            Imagen pre-procesada lista para Hailo
        """
        # Paso 1: Redimensionar a 640x640
        resized = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)
        
        # Paso 2: Normalizar a rango [0, 1]
        normalized = resized.astype(np.float32) / 255.0
        
        return normalized
    
    def postprocess_outputs(self, outputs: Dict[str, np.ndarray], original_shape: Tuple[int, int]) -> List[Detection]:
        """
        Post-procesa salidas del modelo YOLOv8
        
        Args:
            outputs: Salidas del Hailo (diccionario de tensores)
            original_shape: Shape original de la imagen (H, W)
        
        Returns:
            Lista de detecciones filtradas
        """
        # NOTA: Esta implementación es un placeholder
        # La estructura real de outputs depende del formato .hef compilado
        
        detections = []
        
        # Placeholder: generar detecciones de ejemplo
        # En producción, parsear los tensores de salida de YOLOv8
        
        return detections
    
    def infer_frame(self, frame: np.ndarray) -> Tuple[List[Detection], float]:
        """
        Ejecuta pipeline completo de inferencia
        
        Args:
            frame: Frame RGB de la cámara
        
        Returns:
            Tupla (detecciones, tiempo_inferencia_ms)
        """
        start_time = time.time()
        
        try:
            # Guardar shape original
            original_shape = frame.shape[:2]
            
            # Pre-procesamiento
            preprocessed = self.preprocess_image(frame)
            
            # Inferencia en Hailo-8L
            outputs = self.hailo.infer(preprocessed)
            
            if outputs is None:
                logger.warning("Inferencia retornó None")
                return [], 0.0
            
            # Post-procesamiento
            detections = self.postprocess_outputs(outputs, original_shape)
            
            # Calcular tiempo de inferencia
            inference_time = (time.time() - start_time) * 1000  # ms
            
            # Actualizar métricas
            self.avg_inference_time = 0.9 * self.avg_inference_time + 0.1 * inference_time
            self.fps = 1000.0 / inference_time if inference_time > 0 else 0.0
            
            return detections, inference_time
            
        except Exception as e:
            logger.error(f"Error en inferencia: {e}")
            return [], 0.0
    
    def get_metrics(self) -> dict:
        """Retorna métricas de rendimiento"""
        return {
            'fps': self.fps,
            'avg_inference_ms': self.avg_inference_time,
        }

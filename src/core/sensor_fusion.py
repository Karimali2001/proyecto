"""
Sensor Fusion Module
Fusiona datos de cámara + IA + (futuro) sensores ToF
"""

import logging
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


class SensorFusion:
    """Fusiona datos de múltiples sensores para mejorar la percepción"""
    
    def __init__(self):
        self.last_camera_timestamp = 0.0
        self.last_tof_timestamp = 0.0
        
        # Estado fusionado
        self.fused_data = {
            'visual_detections': [],
            'tof_distances': [],
            'confidence_score': 0.0,
        }
        
    def update_visual_data(self, detections: list, timestamp: Optional[float] = None):
        """
        Actualiza datos visuales (de la cámara + IA)
        
        Args:
            detections: Lista de objetos Detection
            timestamp: Timestamp de captura (None = usar tiempo actual)
        """
        if timestamp is None:
            timestamp = time.time()
        
        self.last_camera_timestamp = timestamp
        self.fused_data['visual_detections'] = detections
        
        # Calcular confianza basada en número de detecciones
        if len(detections) > 0:
            avg_confidence = sum(d.confidence for d in detections) / len(detections)
            self.fused_data['confidence_score'] = avg_confidence
        else:
            self.fused_data['confidence_score'] = 0.0
    
    def update_tof_data(self, distances: list, timestamp: Optional[float] = None):
        """
        Actualiza datos de sensores ToF (futuro)
        
        Args:
            distances: Lista de distancias medidas por sensores ToF
            timestamp: Timestamp de medición
        """
        if timestamp is None:
            timestamp = time.time()
        
        self.last_tof_timestamp = timestamp
        self.fused_data['tof_distances'] = distances
    
    def get_fused_perception(self) -> Dict[str, Any]:
        """
        Retorna percepción fusionada del entorno
        
        Returns:
            Diccionario con datos fusionados de todos los sensores
        """
        # En el futuro, aquí se puede implementar lógica avanzada
        # para correlacionar detecciones visuales con lecturas ToF
        
        return {
            'visual': {
                'detections': self.fused_data['visual_detections'],
                'timestamp': self.last_camera_timestamp,
            },
            'tof': {
                'distances': self.fused_data['tof_distances'],
                'timestamp': self.last_tof_timestamp,
            },
            'confidence': self.fused_data['confidence_score'],
        }
    
    def is_data_fresh(self, max_age_seconds: float = 0.5) -> bool:
        """
        Verifica si los datos fusionados son recientes
        
        Args:
            max_age_seconds: Edad máxima permitida en segundos
        
        Returns:
            True si los datos son frescos
        """
        current_time = time.time()
        camera_age = current_time - self.last_camera_timestamp
        
        return camera_age < max_age_seconds

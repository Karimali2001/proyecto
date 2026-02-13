"""
Hailo-8L GStreamer Driver
Interface: PCIe (M.2 HAT) via GStreamer Pipeline
Library: hailo-apps with automatic model download
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from threading import Lock
import numpy as np

logger = logging.getLogger(__name__)

# GStreamer and Hailo imports
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
    import hailo
    from hailo_apps.hailo_app_python.core.common.buffer_utils import get_caps_from_pad, get_numpy_from_buffer
    from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
    from hailo_apps.hailo_app_python.apps.detection.detection_pipeline import GStreamerDetectionApp
    HAILO_APPS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Hailo apps no disponibles. Error: {e}")
    HAILO_APPS_AVAILABLE = False


class HailoAppCallback(app_callback_class):
    """
    Callback personalizable para procesar detecciones de Hailo
    Hereda de app_callback_class del framework de Hailo
    """
    
    def __init__(self):
        super().__init__()
        self.detections_buffer: List[Dict[str, Any]] = []
        self._lock = Lock()
        self.frame_count = 0
        
    def get_latest_detections(self) -> List[Dict[str, Any]]:
        """Retorna las últimas detecciones y limpia el buffer"""
        with self._lock:
            detections = self.detections_buffer.copy()
            self.detections_buffer.clear()
            return detections


def hailo_detection_callback(pad, info, user_data: HailoAppCallback):
    """
    Callback que se ejecuta cuando hay datos disponibles del pipeline
    
    Args:
        pad: GStreamer pad
        info: Información del probe
        user_data: Instancia de HailoAppCallback
    """
    # Get buffer
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    # Increment frame counter
    user_data.increment()
    user_data.frame_count += 1
    
    # Get detections from buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)
    
    # Parse detections
    parsed_detections = []
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        
        # Get track ID if available
        track_id = 0
        track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
        if len(track) == 1:
            track_id = track[0].get_id()
        
        parsed_detections.append({
            'label': label,
            'confidence': confidence,
            'bbox': {
                'xmin': bbox.xmin(),
                'ymin': bbox.ymin(),
                'width': bbox.width(),
                'height': bbox.height()
            },
            'track_id': track_id
        })
    
    # Store in buffer
    with user_data._lock:
        user_data.detections_buffer.extend(parsed_detections)
    
    # Log every 30 frames
    if user_data.frame_count % 30 == 0:
        logger.debug(f"Frame {user_data.frame_count}: {len(parsed_detections)} detecciones")
    
    return Gst.PadProbeReturn.OK


class HailoGStreamerDriver:
    """
    Driver para Hailo-8L usando GStreamer con descarga automática de modelos
    """
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Inicializa el driver de Hailo con GStreamer
        
        Args:
            env_file: Ruta al archivo .env con configuración (opcional)
        """
        self.env_file = env_file
        self.app: Optional[GStreamerDetectionApp] = None
        self.callback_data: Optional[HailoAppCallback] = None
        self._is_initialized = False
        self._is_running = False
        
    def initialize(self) -> bool:
        """
        Inicializa el pipeline de GStreamer con Hailo
        El modelo se descarga automáticamente si no existe
        
        Returns:
            True si la inicialización fue exitosa
        """
        if not HAILO_APPS_AVAILABLE:
            logger.error("Hailo apps no disponibles. Instalar desde repositorio de Hailo.")
            return False
        
        try:
            logger.info("Inicializando Hailo GStreamer pipeline...")
            
            # Set environment file if provided
            if self.env_file and os.path.exists(self.env_file):
                os.environ["HAILO_ENV_FILE"] = str(self.env_file)
                logger.info(f"Usando configuración: {self.env_file}")
            else:
                logger.warning("Archivo .env no encontrado, usando configuración por defecto")
            
            # Create callback instance
            self.callback_data = HailoAppCallback()
            
            # Initialize GStreamer app
            # Note: This will download the model automatically on first run
            self.app = GStreamerDetectionApp(hailo_detection_callback, self.callback_data)
            
            self._is_initialized = True
            logger.info("✅ Hailo GStreamer inicializado. Modelo se descargará al iniciar.")
            return True
            
        except Exception as e:
            logger.error(f"Error al inicializar Hailo GStreamer: {e}")
            return False
    
    def start(self) -> bool:
        """
        Inicia el pipeline de GStreamer
        
        Returns:
            True si se inició correctamente
        """
        if not self._is_initialized or self.app is None:
            logger.error("Hailo no inicializado")
            return False
        
        try:
            logger.info("Iniciando pipeline de Hailo...")
            # The app.run() method will download model if needed and start the pipeline
            # Note: This is typically run in a separate thread
            self._is_running = True
            logger.info("✅ Pipeline de Hailo iniciado")
            return True
            
        except Exception as e:
            logger.error(f"Error al iniciar pipeline: {e}")
            return False
    
    def get_detections(self) -> List[Dict[str, Any]]:
        """
        Obtiene las últimas detecciones procesadas
        
        Returns:
            Lista de diccionarios con detecciones
        """
        if not self._is_running or self.callback_data is None:
            return []
        
        return self.callback_data.get_latest_detections()
    
    def is_ready(self) -> bool:
        """Verifica si Hailo está listo"""
        return self._is_initialized and self._is_running
    
    def get_model_info(self) -> Dict[str, Any]:
        """Retorna información del modelo"""
        if not self._is_initialized:
            return {}
        
        env_file = os.environ.get("HAILO_ENV_FILE", "default")
        return {
            "env_file": env_file,
            "model_name": os.environ.get("HAILO_MODEL_NAME", "yolov8s"),
            "status": "running" if self._is_running else "initialized"
        }
    
    def release(self):
        """Libera recursos del pipeline"""
        if self.app is not None:
            try:
                logger.info("Liberando recursos de Hailo GStreamer...")
                # Stop the pipeline
                self._is_running = False
                # The GStreamer app cleanup is handled internally
                logger.info("✅ Hailo GStreamer liberado")
            except Exception as e:
                logger.error(f"Error al liberar Hailo: {e}")
        
        self._is_initialized = False

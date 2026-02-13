"""
Camera Driver - Arducam IMX296 Global Shutter
Interface: CSI (Camera Serial Interface)
Library: picamera2
"""

import logging
from threading import Lock
from typing import Optional, Tuple
import numpy as np
from picamera2 import Picamera2
from libcamera import controls

logger = logging.getLogger(__name__)


class CameraDriver:
    """Driver para cámara Arducam IMX296 conectada por CSI"""
    
    def __init__(self, resolution: Tuple[int, int] = (640, 640), framerate: int = 120):
        """
        Inicializa el driver de cámara
        
        Args:
            resolution: Tupla (width, height) para captura
            framerate: FPS objetivo (máx. 120 para IMX296)
        """
        self.resolution = resolution
        self.framerate = framerate
        self.camera: Optional[Picamera2] = None
        self._lock = Lock()
        self._is_running = False
        
    def initialize(self) -> bool:
        """
        Inicializa la cámara y la configura
        
        Returns:
            True si la inicialización fue exitosa, False en caso contrario
        """
        try:
            logger.info("Inicializando cámara Arducam IMX296...")
            
            self.camera = Picamera2()
            
            # Configuración optimizada para latencia mínima
            config = self.camera.create_video_configuration(
                main={"size": self.resolution, "format": "RGB888"},
                controls={
                    "FrameRate": self.framerate,
                    "AeEnable": False,  # Deshabilitar auto-exposure para latencia constante
                    "ExposureTime": 8000,  # 8ms exposure (fijo)
                }
            )
            
            self.camera.configure(config)
            self.camera.start()
            
            self._is_running = True
            logger.info(f"Cámara inicializada: {self.resolution} @ {self.framerate} FPS")
            return True
            
        except Exception as e:
            logger.error(f"Error al inicializar cámara: {e}")
            return False
    
    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Captura un frame de la cámara
        
        Returns:
            Array numpy (H, W, 3) en formato RGB, o None si hay error
        """
        if not self._is_running or self.camera is None:
            logger.warning("Intento de captura con cámara no inicializada")
            return None
        
        try:
            with self._lock:
                # Captura directa sin buffer (mínima latencia)
                frame = self.camera.capture_array("main")
                return frame
                
        except Exception as e:
            logger.error(f"Error al capturar frame: {e}")
            return None
    
    def is_ready(self) -> bool:
        """Verifica si la cámara está lista para capturar"""
        return self._is_running and self.camera is not None
    
    def stop(self):
        """Detiene la cámara y libera recursos"""
        if self.camera is not None:
            try:
                logger.info("Deteniendo cámara...")
                self.camera.stop()
                self.camera.close()
                self._is_running = False
                logger.info("Cámara detenida correctamente")
            except Exception as e:
                logger.error(f"Error al detener cámara: {e}")
    
    def get_status(self) -> dict:
        """Retorna estado actual de la cámara"""
        return {
            "running": self._is_running,
            "resolution": self.resolution,
            "framerate": self.framerate,
        }

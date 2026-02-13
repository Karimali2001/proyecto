"""
Hailo-8L NPU Driver
Interface: PCIe (M.2 HAT)
Library: hailo_platform
"""

import logging
from typing import Optional, List, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

# Placeholder para imports de Hailo (requiere SDK instalado)
try:
    from hailo_platform import (
        HEF, VDevice, HailoStreamInterface, 
        InferVStreams, ConfigureParams
    )
    HAILO_AVAILABLE = True
except ImportError:
    logger.warning("Hailo SDK no disponible. Usando modo simulado.")
    HAILO_AVAILABLE = False


class HailoDriver:
    """Driver para acelerador de IA Hailo-8L conectado vía PCIe"""
    
    def __init__(self, model_path: str, batch_size: int = 1):
        """
        Inicializa el driver Hailo-8L
        
        Args:
            model_path: Ruta al archivo .hef compilado
            batch_size: Tamaño de batch (usar 1 para mínima latencia)
        """
        self.model_path = model_path
        self.batch_size = batch_size
        self.device: Optional[Any] = None
        self.network_group = None
        self.input_vstreams = None
        self.output_vstreams = None
        self._is_initialized = False
        
    def initialize(self) -> bool:
        """
        Inicializa el dispositivo Hailo y carga el modelo .hef
        
        Returns:
            True si la inicialización fue exitosa, False en caso contrario
        """
        if not HAILO_AVAILABLE:
            logger.error("SDK de Hailo no está instalado")
            return False
        
        try:
            logger.info("Inicializando Hailo-8L NPU...")
            
            # Crear dispositivo virtual (PCIe)
            self.device = VDevice()
            
            # Cargar HEF (Hailo Executable Format)
            hef = HEF(self.model_path)
            logger.info(f"Modelo cargado: {self.model_path}")
            
            # Configurar red neuronal
            configure_params = ConfigureParams.create_from_hef(
                hef=hef, 
                interface=HailoStreamInterface.PCIe
            )
            
            self.network_group = self.device.configure(hef, configure_params)[0]
            
            # Obtener input/output virtual streams
            self.input_vstreams = InferVStreams(self.network_group, self.batch_size)
            self.output_vstreams = self.input_vstreams
            
            self._is_initialized = True
            logger.info("Hailo-8L inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error al inicializar Hailo-8L: {e}")
            return False
    
    def infer(self, image: np.ndarray) -> Optional[Dict[str, np.ndarray]]:
        """
        Ejecuta inferencia en la NPU
        
        Args:
            image: Array numpy (batch, H, W, C) o (H, W, C)
        
        Returns:
            Diccionario con las salidas del modelo, o None si hay error
        """
        if not self._is_initialized:
            logger.warning("Intento de inferencia con Hailo no inicializado")
            return None
        
        try:
            # Asegurar dimensión de batch
            if image.ndim == 3:
                image = np.expand_dims(image, axis=0)
            
            # Ejecutar inferencia
            with self.input_vstreams as input_stream, \
                 self.output_vstreams as output_stream:
                
                # Enviar imagen a la NPU
                input_data = {input_stream.name: image}
                output_data = output_stream.infer(input_data)
                
                return output_data
                
        except Exception as e:
            logger.error(f"Error durante inferencia: {e}")
            return None
    
    def is_ready(self) -> bool:
        """Verifica si el Hailo está listo para inferencia"""
        return self._is_initialized and self.device is not None
    
    def get_model_info(self) -> Dict[str, Any]:
        """Retorna información del modelo cargado"""
        if not self._is_initialized:
            return {}
        
        try:
            return {
                "model_path": self.model_path,
                "batch_size": self.batch_size,
                "network_group": str(self.network_group),
            }
        except Exception as e:
            logger.error(f"Error obteniendo info del modelo: {e}")
            return {}
    
    def release(self):
        """Libera recursos del Hailo"""
        if self.device is not None:
            try:
                logger.info("Liberando recursos de Hailo-8L...")
                # Cleanup de recursos
                if self.network_group:
                    self.network_group.release()
                self._is_initialized = False
                logger.info("Hailo-8L liberado correctamente")
            except Exception as e:
                logger.error(f"Error al liberar Hailo: {e}")

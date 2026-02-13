"""
Communication Protocols Driver
Protocols: I2C (ToF sensors VL53L5CX), Serial/UART (future expansion)
"""

import logging
from typing import Optional, List
import time

logger = logging.getLogger(__name__)

try:
    from smbus2 import SMBus
    I2C_AVAILABLE = True
except ImportError:
    logger.warning("smbus2 no disponible. Instalar con: pip install smbus2")
    I2C_AVAILABLE = False


class CommProtocols:
    """Driver para protocolos de comunicación I2C y Serial"""
    
    def __init__(self, i2c_bus: int = 1):
        """
        Inicializa los protocolos de comunicación
        
        Args:
            i2c_bus: Número de bus I2C (1 para I2C1 en RPi5)
        """
        self.i2c_bus_number = i2c_bus
        self.i2c_bus: Optional[SMBus] = None
        self._i2c_initialized = False
        
        # Direcciones I2C de sensores ToF (futuro)
        self.tof_addresses = [0x29, 0x30, 0x31]  # Direcciones base VL53L5CX
        
    def initialize_i2c(self) -> bool:
        """
        Inicializa el bus I2C
        
        Returns:
            True si la inicialización fue exitosa
        """
        if not I2C_AVAILABLE:
            logger.warning("I2C no disponible (smbus2 no instalado)")
            return False
        
        try:
            logger.info(f"Inicializando bus I2C-{self.i2c_bus_number}...")
            self.i2c_bus = SMBus(self.i2c_bus_number)
            self._i2c_initialized = True
            logger.info("Bus I2C inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error al inicializar I2C: {e}")
            return False
    
    def scan_i2c_devices(self) -> List[int]:
        """
        Escanea el bus I2C buscando dispositivos
        
        Returns:
            Lista de direcciones I2C encontradas
        """
        if not self._i2c_initialized:
            logger.warning("I2C no inicializado")
            return []
        
        devices = []
        logger.info("Escaneando bus I2C...")
        
        for address in range(0x03, 0x78):  # Rango válido de direcciones I2C
            try:
                self.i2c_bus.read_byte(address)
                devices.append(address)
                logger.info(f"Dispositivo encontrado en 0x{address:02X}")
            except Exception:
                pass  # Dispositivo no presente
        
        return devices
    
    def read_i2c_byte(self, address: int, register: int) -> Optional[int]:
        """
        Lee un byte desde un dispositivo I2C
        
        Args:
            address: Dirección I2C del dispositivo
            register: Registro a leer
        
        Returns:
            Valor leído, o None si hay error
        """
        if not self._i2c_initialized:
            return None
        
        try:
            value = self.i2c_bus.read_byte_data(address, register)
            return value
        except Exception as e:
            logger.error(f"Error leyendo I2C 0x{address:02X}:0x{register:02X}: {e}")
            return None
    
    def write_i2c_byte(self, address: int, register: int, value: int) -> bool:
        """
        Escribe un byte a un dispositivo I2C
        
        Args:
            address: Dirección I2C del dispositivo
            register: Registro a escribir
            value: Valor a escribir
        
        Returns:
            True si la escritura fue exitosa
        """
        if not self._i2c_initialized:
            return False
        
        try:
            self.i2c_bus.write_byte_data(address, register, value)
            return True
        except Exception as e:
            logger.error(f"Error escribiendo I2C 0x{address:02X}:0x{register:02X}: {e}")
            return False
    
    def read_tof_distance(self, sensor_index: int = 0) -> Optional[float]:
        """
        Lee distancia de sensor ToF VL53L5CX (placeholder)
        
        Args:
            sensor_index: Índice del sensor (0-2)
        
        Returns:
            Distancia en metros, o None si no está disponible
        """
        # NOTA: Esta es una implementación placeholder
        # La implementación real requiere el driver específico de VL53L5CX
        logger.debug(f"Leyendo ToF sensor {sensor_index} (placeholder)")
        
        # Por ahora retornar None (sensor no implementado)
        return None
    
    def cleanup(self):
        """Cierra el bus I2C"""
        if self._i2c_initialized and self.i2c_bus:
            try:
                logger.info("Cerrando bus I2C...")
                self.i2c_bus.close()
                self._i2c_initialized = False
                logger.info("Bus I2C cerrado")
            except Exception as e:
                logger.error(f"Error al cerrar I2C: {e}")

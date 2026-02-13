"""
Console Logger - Sistema de logging configurado
"""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(log_path: str, log_level: str = "INFO", max_bytes: int = 10485760, backup_count: int = 5):
    """
    Configura el sistema de logging
    
    Args:
        log_path: Ruta del archivo de log
        log_level: Nivel de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        max_bytes: Tamaño máximo del archivo de log
        backup_count: Número de archivos de respaldo
    """
    # Crear directorio de logs si no existe
    log_dir = os.path.dirname(log_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configurar formato
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Handler para archivo (con rotación)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    
    # Configurar logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Log inicial
    logging.info("=" * 80)
    logging.info("Sistema de Asistencia a Invidentes - Raspberry Pi 5 + Hailo-8L")
    logging.info("=" * 80)
    logging.info(f"Nivel de log: {log_level}")
    logging.info(f"Log guardado en: {log_path}")

"""
Navigation System - Sistema de Alertas de Navegación
Responsable de determinar si un objeto es un obstáculo aéreo y activar alertas
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class NavigationSystem:
    """Sistema de navegación y alertas para obstáculos aéreos"""
    
    def __init__(self, config: dict, voice_interface, io_controller):
        """
        Args:
            config: Configuración (AERIAL_OBSTACLES, AERIAL_ZONE_Y_MAX, etc.)
            voice_interface: Interfaz de voz para TTS
            io_controller: Controlador de I/O para audio
        """
        self.config = config
        self.voice = voice_interface
        self.io = io_controller
        
        self.aerial_obstacles = config['AERIAL_OBSTACLES']
        self.aerial_zone_y_max = config.get('AERIAL_ZONE_Y_MAX', 400)
        
        # Estado de alertas (para evitar spam)
        self._last_alert_time = 0.0
        self._alert_cooldown = 2.0  # Segundos entre alertas
        
    def analyze_detections(self, detections: List) -> Optional[dict]:
        """
        Analiza detecciones y determina si hay obstáculos aéreos
        
        Args:
            detections: Lista de objetos Detection
        
        Returns:
            Diccionario con análisis, o None si no hay obstáculos
        """
        import time
        
        aerial_threats = []
        
        for detection in detections:
            # Verificar si es una clase de obstáculo aéreo
            if detection.class_name not in self.aerial_obstacles:
                continue
            
            # Verificar si está en zona aérea
            if not detection.is_in_aerial_zone(self.aerial_zone_y_max):
                continue
            
            # Es un obstáculo aéreo
            priority = self.aerial_obstacles[detection.class_name]
            
            aerial_threats.append({
                'object': detection.class_name,
                'confidence': detection.confidence,
                'priority': priority,
                'center': detection.get_center(),
            })
        
        if not aerial_threats:
            return None
        
        # Ordenar por prioridad (menor número = mayor prioridad)
        aerial_threats.sort(key=lambda x: x['priority'])
        
        return {
            'count': len(aerial_threats),
            'highest_priority': aerial_threats[0],
            'all_threats': aerial_threats,
        }
    
    def trigger_alert(self, threat_info: dict):
        """
        Activa alerta de audio para obstáculo
        
        Args:
            threat_info: Información del obstáculo desde analyze_detections()
        """
        import time
        
        # Verificar cooldown para evitar spam
        current_time = time.time()
        if current_time - self._last_alert_time < self._alert_cooldown:
            return
        
        self._last_alert_time = current_time
        
        # Obtener información del obstáculo más peligroso
        threat = threat_info['highest_priority']
        object_name = threat['object']
        
        # Traducir nombre al español
        translations = {
            'person': 'persona',
            'bicycle': 'bicicleta',
            'car': 'automóvil',
            'motorcycle': 'motocicleta',
            'bus': 'autobús',
            'truck': 'camión',
            'traffic light': 'semáforo',
            'fire hydrant': 'hidrante',
            'stop sign': 'señal de alto',
            'bench': 'banca',
            'bird': 'ave',
            'cat': 'gato',
            'dog': 'perro',
        }
        
        object_name_es = translations.get(object_name, object_name)
        
        # Generar mensaje de alerta
        message = f"Cuidado, {object_name_es} adelante"
        
        logger.info(f"ALERTA: {message} (prioridad {threat['priority']})")
        
        # Activar alerta de voz
        if self.voice:
            self.voice.speak(message)
        
        # Opcional: reproducir sonido de alerta
        # if self.io:
        #     self.io.play_audio(self.config.get('ALERT_SOUND_PATH'))
    
    def process_frame_navigation(self, detections: List):
        """
        Procesa un frame completo: analiza y activa alertas si es necesario
        
        Args:
            detections: Lista de objetos Detection del frame actual
        """
        # Analizar si hay obstáculos aéreos
        threat_info = self.analyze_detections(detections)
        
        # Si hay amenazas, activar alerta
        if threat_info:
            self.trigger_alert(threat_info)

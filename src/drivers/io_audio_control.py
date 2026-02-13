"""
GPIO and Audio Control Driver
Hardware: RPi.GPIO, ALSA (Advanced Linux Sound Architecture)
Functions: Fan control (PWM), LED indicators, Buzzer, Audio output
"""

import logging
from typing import Optional
import subprocess

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    logger.warning("RPi.GPIO no disponible. Usando modo simulado.")
    GPIO_AVAILABLE = False


class IOAudioController:
    """Controlador para GPIO (LEDs, Fan, Buzzer) y Audio (ALSA)"""
    
    def __init__(self, pinout_config: dict):
        """
        Inicializa el controlador de I/O
        
        Args:
            pinout_config: Diccionario con configuración de pines
        """
        self.config = pinout_config
        self._gpio_initialized = False
        self._fan_pwm = None
        
    def initialize(self) -> bool:
        """Inicializa GPIO y configura pines"""
        if not GPIO_AVAILABLE:
            logger.warning("GPIO no disponible, usando modo simulado")
            return True
        
        try:
            logger.info("Inicializando GPIO...")
            
            # Configurar modo BCM
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Configurar LEDs como salidas
            GPIO.setup(self.config['LED_STATUS_OK'], GPIO.OUT)
            GPIO.setup(self.config['LED_STATUS_WARN'], GPIO.OUT)
            GPIO.setup(self.config['LED_STATUS_ERROR'], GPIO.OUT)
            
            # Configurar buzzer
            GPIO.setup(self.config['BUZZER_PIN'], GPIO.OUT)
            GPIO.output(self.config['BUZZER_PIN'], GPIO.LOW)
            
            # Configurar PWM para ventilador
            GPIO.setup(self.config['FAN_PWM_PIN'], GPIO.OUT)
            self._fan_pwm = GPIO.PWM(
                self.config['FAN_PWM_PIN'], 
                self.config['FAN_PWM_FREQ']
            )
            self._fan_pwm.start(0)  # Iniciar con ventilador apagado
            
            # Estado inicial: LED verde encendido
            self.set_led_status('ok')
            
            self._gpio_initialized = True
            logger.info("GPIO inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error al inicializar GPIO: {e}")
            return False
    
    def set_led_status(self, status: str):
        """
        Establece el estado de los LEDs
        
        Args:
            status: 'ok', 'warn', 'error'
        """
        if not self._gpio_initialized:
            return
        
        try:
            # Apagar todos los LEDs
            GPIO.output(self.config['LED_STATUS_OK'], GPIO.LOW)
            GPIO.output(self.config['LED_STATUS_WARN'], GPIO.LOW)
            GPIO.output(self.config['LED_STATUS_ERROR'], GPIO.LOW)
            
            # Encender LED correspondiente
            if status == 'ok':
                GPIO.output(self.config['LED_STATUS_OK'], GPIO.HIGH)
            elif status == 'warn':
                GPIO.output(self.config['LED_STATUS_WARN'], GPIO.HIGH)
            elif status == 'error':
                GPIO.output(self.config['LED_STATUS_ERROR'], GPIO.HIGH)
                
        except Exception as e:
            logger.error(f"Error al configurar LED: {e}")
    
    def set_fan_speed(self, speed_percent: int):
        """
        Establece la velocidad del ventilador
        
        Args:
            speed_percent: Velocidad de 0 a 100%
        """
        if not self._gpio_initialized or self._fan_pwm is None:
            return
        
        try:
            speed_percent = max(0, min(100, speed_percent))
            self._fan_pwm.ChangeDutyCycle(speed_percent)
            logger.debug(f"Velocidad de ventilador: {speed_percent}%")
        except Exception as e:
            logger.error(f"Error al configurar ventilador: {e}")
    
    def trigger_buzzer(self, duration_ms: int = 200):
        """
        Activa el buzzer por un tiempo determinado
        
        Args:
            duration_ms: Duración en milisegundos
        """
        if not self._gpio_initialized:
            return
        
        try:
            import time
            GPIO.output(self.config['BUZZER_PIN'], GPIO.HIGH)
            time.sleep(duration_ms / 1000.0)
            GPIO.output(self.config['BUZZER_PIN'], GPIO.LOW)
        except Exception as e:
            logger.error(f"Error al activar buzzer: {e}")
    
    def play_audio(self, audio_path: str) -> bool:
        """
        Reproduce un archivo de audio usando ALSA
        
        Args:
            audio_path: Ruta al archivo .wav
        
        Returns:
            True si se reprodujo correctamente
        """
        try:
            # Usar aplay (ALSA player) para reproducir audio
            subprocess.run(
                ['aplay', '-q', audio_path],
                check=True,
                timeout=5
            )
            return True
        except subprocess.TimeoutExpired:
            logger.error("Timeout al reproducir audio")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Error al reproducir audio: {e}")
            return False
        except FileNotFoundError:
            logger.error("aplay no encontrado. Instalar alsa-utils.")
            return False
    
    def cleanup(self):
        """Limpia recursos GPIO"""
        if self._gpio_initialized:
            try:
                logger.info("Limpiando GPIO...")
                if self._fan_pwm:
                    self._fan_pwm.stop()
                GPIO.cleanup()
                self._gpio_initialized = False
                logger.info("GPIO limpiado correctamente")
            except Exception as e:
                logger.error(f"Error al limpiar GPIO: {e}")

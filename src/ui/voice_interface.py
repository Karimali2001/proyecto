"""
Voice Interface - Text-to-Speech (TTS)
Library: pyttsx3
"""

import logging
from threading import Thread, Lock
from queue import Queue
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    logger.warning("pyttsx3 no disponible. Instalar con: pip install pyttsx3")
    TTS_AVAILABLE = False


class VoiceInterface:
    """Interfaz de voz para Text-to-Speech"""
    
    def __init__(self, rate: int = 150, volume: float = 0.9):
        """
        Inicializa la interfaz de voz
        
        Args:
            rate: Velocidad de habla (palabras por minuto)
            volume: Volumen (0.0 a 1.0)
        """
        self.rate = rate
        self.volume = volume
        self.engine: Optional[Any] = None
        self._is_initialized = False
        
        # Cola de mensajes para hablar
        self._speak_queue = Queue()
        self._speak_thread: Optional[Thread] = None
        self._running = False
        self._lock = Lock()
        
    def initialize(self) -> bool:
        """
        Inicializa el motor TTS
        
        Returns:
            True si la inicialización fue exitosa
        """
        if not TTS_AVAILABLE:
            logger.warning("TTS no disponible (pyttsx3 no instalado)")
            return False
        
        try:
            logger.info("Inicializando motor TTS...")
            
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', self.rate)
            self.engine.setProperty('volume', self.volume)
            
            # Configurar voz en español si está disponible
            voices = self.engine.getProperty('voices')
            for voice in voices:
                if 'spanish' in voice.name.lower() or 'español' in voice.name.lower():
                    self.engine.setProperty('voice', voice.id)
                    logger.info(f"Voz en español configurada: {voice.name}")
                    break
            
            self._is_initialized = True
            
            # Iniciar hilo de procesamiento de voz
            self._running = True
            self._speak_thread = Thread(target=self._speak_worker, daemon=True)
            self._speak_thread.start()
            
            logger.info("Motor TTS inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error al inicializar TTS: {e}")
            return False
    
    def speak(self, text: str, wait: bool = False):
        """
        Habla un texto (no bloqueante por defecto)
        
        Args:
            text: Texto a hablar
            wait: Si True, espera a que termine de hablar
        """
        if not self._is_initialized:
            logger.warning(f"TTS no inicializado. Texto: '{text}'")
            return
        
        if wait:
            # Modo bloqueante: hablar directamente
            with self._lock:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception as e:
                    logger.error(f"Error al hablar: {e}")
        else:
            # Modo no bloqueante: agregar a cola
            self._speak_queue.put(text)
    
    def _speak_worker(self):
        """Worker thread que procesa la cola de mensajes de voz"""
        while self._running:
            try:
                # Obtener texto de la cola (timeout 1 segundo)
                text = self._speak_queue.get(timeout=1.0)
                
                with self._lock:
                    self.engine.say(text)
                    self.engine.runAndWait()
                
                self._speak_queue.task_done()
                
            except Exception:
                # Queue vacía o error
                continue
    
    def is_ready(self) -> bool:
        """Verifica si el TTS está listo"""
        return self._is_initialized
    
    def stop(self):
        """Detiene el motor TTS"""
        if self._is_initialized:
            try:
                logger.info("Deteniendo motor TTS...")
                self._running = False
                
                if self._speak_thread:
                    self._speak_thread.join(timeout=2.0)
                
                if self.engine:
                    self.engine.stop()
                
                self._is_initialized = False
                logger.info("Motor TTS detenido correctamente")
            except Exception as e:
                logger.error(f"Error al detener TTS: {e}")

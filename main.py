#!/usr/bin/env python3
"""
Main Orchestrator - Sistema de Asistencia a Invidentes
Raspberry Pi 5 + Hailo-8L + Arducam IMX296

Arquitectura:
- Threading para pipeline de cámara + IA (no bloquear captura)
- State Machine para gestión de estados (Booting -> Running -> Throttling -> Error)
- Monitoreo de temperatura con watchdog
"""

import sys
import os
import time
import signal
import logging
from threading import Thread, Event
from typing import Optional

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Importar configuración
from config import pinout, constants

# Importar drivers
from src.drivers.camera_driver import CameraDriver
from src.drivers.hailo_gstreamer_driver import HailoGStreamerDriver
from src.drivers.io_audio_control import IOAudioController
from src.drivers.comm_protocols import CommProtocols

# Importar core
from src.core.state_manager import StateManager, SystemState
from src.core.object_inference import ObjectInference
from src.core.navigation_system import NavigationSystem
from src.core.sensor_fusion import SensorFusion

# Importar UI
from src.ui.voice_interface import VoiceInterface
from src.ui.console_logger import setup_logger

# Configurar logger
setup_logger(
    log_path=constants.LOG_PATH,
    log_level=constants.LOG_LEVEL,
    max_bytes=constants.LOG_MAX_BYTES,
    backup_count=constants.LOG_BACKUP_COUNT
)

logger = logging.getLogger(__name__)


class AssistiveDevice:
    """Orquestador principal del dispositivo de asistencia"""
    
    def __init__(self):
        # State Manager
        self.state_manager = StateManager()
        
        # Drivers
        self.camera: Optional[CameraDriver] = None
        self.hailo: Optional[HailoGStreamerDriver] = None
        self.io_controller: Optional[IOAudioController] = None
        self.comm: Optional[CommProtocols] = None
        
        # Core modules
        self.inference_engine: Optional[ObjectInference] = None
        self.navigation: Optional[NavigationSystem] = None
        self.sensor_fusion: Optional[SensorFusion] = None
        
        # UI modules
        self.voice: Optional[VoiceInterface] = None
        
        # Threading control
        self.stop_event = Event()
        self.inference_thread: Optional[Thread] = None
        self.thermal_thread: Optional[Thread] = None
        
        # System metrics
        self.current_temp = 0.0
        self.frame_count = 0
        
        # Registrar callbacks de estado
        self._register_state_callbacks()
        
    def _register_state_callbacks(self):
        """Registra callbacks para entry/exit de cada estado"""
        # Booting
        self.state_manager.register_entry_callback(
            SystemState.BOOTING, 
            self._on_enter_booting
        )
        
        # Running
        self.state_manager.register_entry_callback(
            SystemState.RUNNING,
            self._on_enter_running
        )
        
        # Throttling
        self.state_manager.register_entry_callback(
            SystemState.THROTTLING,
            self._on_enter_throttling
        )
        
        # Error
        self.state_manager.register_entry_callback(
            SystemState.ERROR,
            self._on_enter_error
        )
    
    def _on_enter_booting(self):
        """Entry action para estado Booting"""
        logger.info("📌 ESTADO: Booting - Verificando hardware...")
        if self.io_controller:
            self.io_controller.set_led_status('warn')
    
    def _on_enter_running(self):
        """Entry action para estado Running"""
        logger.info("✅ ESTADO: Running - Sistema operativo")
        if self.io_controller:
            self.io_controller.set_led_status('ok')
            self.io_controller.set_fan_speed(pinout.FAN_SPEED_AUTO)
    
    def _on_enter_throttling(self):
        """Entry action para estado Throttling"""
        logger.warning("⚠️  ESTADO: Throttling - Temperatura alta, limitando FPS")
        if self.io_controller:
            self.io_controller.set_led_status('warn')
            self.io_controller.set_fan_speed(100)  # Fan al máximo
    
    def _on_enter_error(self):
        """Entry action para estado Error"""
        logger.error("❌ ESTADO: Error - Fallo crítico del sistema")
        if self.io_controller:
            self.io_controller.set_led_status('error')
            self.io_controller.trigger_buzzer(duration_ms=500)
        
        # Reproducir sonido de error si está disponible
        if constants.ALERT_SOUND_PATH and os.path.exists(constants.ALERT_SOUND_PATH):
            if self.io_controller:
                self.io_controller.play_audio(constants.ALERT_SOUND_PATH)
    
    def initialize_hardware(self) -> bool:
        """
        Inicializa todo el hardware (ESTADO: Booting)
        
        Returns:
            True si todo se inicializó correctamente
        """
        logger.info("Inicializando hardware...")
        
        try:
            # 1. GPIO y Audio
            logger.info("1/5 Inicializando GPIO y Audio...")
            self.io_controller = IOAudioController(pinout.__dict__)
            if not self.io_controller.initialize():
                raise Exception("Fallo al inicializar GPIO")
            
            # 2. Comunicaciones I2C
            logger.info("2/5 Inicializando I2C...")
            self.comm = CommProtocols(i2c_bus=pinout.I2C_BUS)
            self.comm.initialize_i2c()  # No crítico si falla
            
            # 3. Cámara
            logger.info("3/5 Inicializando cámara Arducam IMX296...")
            self.camera = CameraDriver(
                resolution=constants.MODEL_INPUT_SIZE,
                framerate=constants.TARGET_FPS
            )
            if not self.camera.initialize():
                raise Exception("Fallo al inicializar cámara")
            
            # 4. Hailo-8L NPU con GStreamer (auto-descarga de modelo)
            logger.info("4/5 Inicializando Hailo-8L con GStreamer...")
            self.hailo = HailoGStreamerDriver(
                env_file=str(constants.HAILO_ENV_FILE)
            )
            if not self.hailo.initialize():
                raise Exception("Fallo al inicializar Hailo-8L")
            
            # 5. TTS
            logger.info("5/5 Inicializando voz...")
            self.voice = VoiceInterface(
                rate=constants.TTS_RATE,
                volume=constants.TTS_VOLUME
            )
            if constants.TTS_ENABLED:
                self.voice.initialize()  # No crítico si falla
            
            logger.info("✅ Hardware inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error durante inicialización: {e}")
            return False
    
    def initialize_core_modules(self):
        """Inicializa módulos de lógica de negocio"""
        logger.info("Inicializando módulos core...")
        
        # Inference engine
        self.inference_engine = ObjectInference(self.hailo, constants.__dict__)
        
        # Sensor fusion
        self.sensor_fusion = SensorFusion()
        
        # Navigation system
        self.navigation = NavigationSystem(
            constants.__dict__,
            self.voice,
            self.io_controller
        )
        
        logger.info("✅ Módulos core inicializados")
    
    def inference_loop(self):
        """
        Loop principal de inferencia (ejecutado en thread separado)
        Pipeline: Captura -> Inferencia -> Navegación
        """
        logger.info("🚀 Iniciando loop de inferencia...")
        
        while not self.stop_event.is_set():
            try:
                # Solo procesar si estamos en Running o Throttling
                current_state = self.state_manager.get_state()
                
                if current_state == SystemState.RUNNING:
                    # Modo normal
                    self._process_frame()
                    
                elif current_state == SystemState.THROTTLING:
                    # Modo throttling: procesar más lento
                    self._process_frame()
                    time.sleep(constants.THROTTLE_SLEEP_MS / 1000.0)
                    
                else:
                    # En otros estados, esperar
                    time.sleep(0.1)
                    continue
                
            except Exception as e:
                logger.error(f"Error en loop de inferencia: {e}")
                self.state_manager.transition_to(
                    SystemState.ERROR, 
                    f"Exception en inference: {str(e)}"
                )
                break
        
        logger.info("Loop de inferencia detenido")
    
    def _process_frame(self):
        """Procesa un frame completo: captura -> inferencia -> navegación"""
        # 1. Capturar frame
        frame = self.camera.capture_frame()
        if frame is None:
            logger.warning("Frame perdido")
            return
        
        # 2. Inferencia
        detections, inference_time = self.inference_engine.infer_frame(frame)
        
        # 3. Actualizar fusión de sensores
        self.sensor_fusion.update_visual_data(detections)
        
        # 4. Navegación (analizar y alertar)
        self.navigation.process_frame_navigation(detections)
        
        # 5. Métricas
        self.frame_count += 1
        if self.frame_count % 30 == 0:  # Log cada 30 frames
            metrics = self.inference_engine.get_metrics()
            logger.debug(f"FPS: {metrics['fps']:.1f} | Latencia: {metrics['avg_inference_ms']:.1f}ms")
    
    def thermal_monitor_loop(self):
        """
        Loop de monitoreo térmico (ejecutado en thread separado)
        Verifica temperatura y gestiona transiciones Throttling
        """
        logger.info("🌡️  Iniciando monitoreo térmico...")
        
        try:
            import psutil
        except ImportError:
            logger.warning("psutil no disponible, monitoreo térmico deshabilitado")
            return
        
        while not self.stop_event.is_set():
            try:
                # Leer temperatura
                temps = psutil.sensors_temperatures()
                
                if 'cpu_thermal' in temps:
                    self.current_temp = temps['cpu_thermal'][0].current
                else:
                    # Fallback para RPi5
                    self.current_temp = temps.get('coretemp', [{'current': 0}])[0].current
                
                current_state = self.state_manager.get_state()
                
                # Decisiones basadas en temperatura
                if self.current_temp >= pinout.TEMP_CRITICAL:
                    # CRÍTICO: Shutdown de emergencia
                    logger.critical(f"🔥 Temperatura crítica: {self.current_temp}°C")
                    self.state_manager.transition_to(
                        SystemState.ERROR,
                        f"Temperatura crítica: {self.current_temp}°C"
                    )
                    
                elif self.current_temp >= pinout.TEMP_THROTTLE:
                    # ADVERTENCIA: Activar throttling
                    if current_state == SystemState.RUNNING:
                        logger.warning(f"🔥 Temperatura alta: {self.current_temp}°C")
                        self.state_manager.transition_to(
                            SystemState.THROTTLING,
                            f"Overheat: {self.current_temp}°C"
                        )
                        
                elif self.current_temp < pinout.TEMP_NORMAL:
                    # NORMAL: Desactivar throttling
                    if current_state == SystemState.THROTTLING:
                        logger.info(f"❄️  Temperatura normal: {self.current_temp}°C")
                        self.state_manager.transition_to(
                            SystemState.RUNNING,
                            f"Cooled: {self.current_temp}°C"
                        )
                
                # Esperar antes de próxima lectura
                time.sleep(constants.TEMP_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error en monitoreo térmico: {e}")
                time.sleep(constants.TEMP_CHECK_INTERVAL)
        
        logger.info("Monitoreo térmico detenido")
    
    def start(self):
        """Inicia el sistema completo"""
        logger.info("=" * 80)
        logger.info("🚀 INICIANDO SISTEMA DE ASISTENCIA A INVIDENTES")
        logger.info("=" * 80)
        
        # Estado inicial: Booting
        self.state_manager.transition_to(SystemState.BOOTING, "Power ON")
        
        # Inicializar hardware
        if not self.initialize_hardware():
            self.state_manager.transition_to(
                SystemState.ERROR,
                "Init_Fail: Hardware no disponible"
            )
            return False
        
        # Inicializar módulos core
        self.initialize_core_modules()
        
        # Transición a Running
        self.state_manager.transition_to(
            SystemState.RUNNING,
            "Init_Success: Todo OK"
        )
        
        # Iniciar threads
        self.inference_thread = Thread(target=self.inference_loop, daemon=True)
        self.inference_thread.start()
        
        self.thermal_thread = Thread(target=self.thermal_monitor_loop, daemon=True)
        self.thermal_thread.start()
        
        logger.info("✅ Sistema iniciado correctamente")
        
        # Anuncio de voz
        if self.voice and self.voice.is_ready():
            self.voice.speak("Sistema iniciado")
        
        return True
    
    def stop(self):
        """Detiene el sistema de manera ordenada"""
        logger.info("🛑 Deteniendo sistema...")
        
        # Señal de parada
        self.stop_event.set()
        
        # Esperar threads
        if self.inference_thread:
            self.inference_thread.join(timeout=2.0)
        if self.thermal_thread:
            self.thermal_thread.join(timeout=2.0)
        
        # Limpiar hardware
        if self.camera:
            self.camera.stop()
        if self.hailo:
            self.hailo.release()
        if self.voice:
            self.voice.stop()
        if self.comm:
            self.comm.cleanup()
        if self.io_controller:
            self.io_controller.cleanup()
        
        logger.info("✅ Sistema detenido correctamente")
    
    def run_forever(self):
        """Ejecuta el sistema indefinidamente (hasta Ctrl+C)"""
        try:
            logger.info("Sistema en ejecución. Presiona Ctrl+C para detener.")
            
            while not self.stop_event.is_set():
                time.sleep(1)
                
                # Verificar estado de error para auto-recovery
                if self.state_manager.is_in_state(SystemState.ERROR):
                    logger.warning("⚠️  En estado Error, esperando watchdog...")
                    time.sleep(constants.ERROR_RECOVERY_DELAY)
                    
                    # Auto-reset (watchdog)
                    logger.info("🔄 Watchdog: Intentando auto-reset...")
                    self.state_manager.transition_to(
                        SystemState.BOOTING,
                        "Watchdog Auto-Reset"
                    )
                    
                    # Re-inicializar
                    if self.initialize_hardware():
                        self.state_manager.transition_to(
                            SystemState.RUNNING,
                            "Recovery Success"
                        )
                    else:
                        logger.error("❌ Recovery falló, quedando en Error")
                        
        except KeyboardInterrupt:
            logger.info("\n⚠️  Ctrl+C detectado")
        finally:
            self.stop()


def signal_handler(sig, frame):
    """Handler para señales del sistema (Ctrl+C, SIGTERM)"""
    logger.info(f"\n⚠️  Señal {sig} recibida, deteniendo...")
    sys.exit(0)


def main():
    """Función principal"""
    # Registrar handler de señales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Crear e iniciar dispositivo
    device = AssistiveDevice()
    
    if device.start():
        device.run_forever()
    else:
        logger.error("❌ Fallo al iniciar sistema")
        sys.exit(1)


if __name__ == "__main__":
    main()

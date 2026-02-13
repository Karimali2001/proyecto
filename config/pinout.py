"""
Pinout Configuration for Raspberry Pi 5
Hardware: Hailo-8L (PCIe), Arducam IMX296 (CSI), VL53L5CX ToF Sensors (I2C)
"""

# === GPIO Pins (BCM Numbering) ===
GPIO_MODE = "BCM"  # Use Broadcom pin numbering

# === Fan Control (PWM) ===
FAN_PWM_PIN = 18  # GPIO 18 (PWM0) - Control de ventilador
FAN_PWM_FREQ = 25000  # 25 kHz PWM frequency

# === Status LEDs ===
LED_STATUS_OK = 17    # GPIO 17 - LED Verde (Sistema OK)
LED_STATUS_WARN = 27  # GPIO 27 - LED Amarillo (Throttling)
LED_STATUS_ERROR = 22 # GPIO 22 - LED Rojo (Error crítico)

# === Audio Control ===
AUDIO_ENABLE_PIN = 23  # GPIO 23 - Habilitar amplificador de audio
BUZZER_PIN = 24        # GPIO 24 - Buzzer para alertas críticas

# === Future Expansion (ToF Sensors) ===
# Los sensores VL53L5CX usan I2C1 (pines 3 y 5)
I2C_BUS = 1            # I2C1: SDA=GPIO2, SCL=GPIO3
TOF_XSHUT_PINS = [25, 8, 7]  # GPIO para desactivar sensores individualmente

# === Camera Interface ===
CAM_PORT = 0  # CSI Port 0 (CAM0 connector)

# === PCIe/M.2 HAT (Hailo-8L) ===
# No requiere configuración de GPIO, usa PCIe Gen 3 x1
HAILO_DEVICE_ID = 0  # Device ID del Hailo-8L en el sistema

# === Temperature Thresholds (°C) ===
TEMP_NORMAL = 60      # Por debajo: funcionamiento normal
TEMP_THROTTLE = 80    # Por encima: activar throttling
TEMP_CRITICAL = 95    # Por encima: shutdown de emergencia

# === Watchdog Configuration ===
WATCHDOG_TIMEOUT = 30  # Segundos antes de auto-reset

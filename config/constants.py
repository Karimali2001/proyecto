"""
System Constants - Business Logic Configuration
"""

from pathlib import Path

# === Hailo Configuration (auto-download) ===
HAILO_ENV_FILE = Path(__file__).parent.parent / ".env"
# El modelo se descarga automáticamente según configuración en .env

# === Model Configuration ===
MODEL_INPUT_SIZE = (640, 640)  # YOLOv8s input resolution
MODEL_BATCH_SIZE = 1           # Batch=1 para mínima latencia
TARGET_FPS = 113               # FPS objetivo según hardware Hailo-8L

# === Detection Thresholds ===
CONFIDENCE_THRESHOLD = 0.5     # Umbral de confianza mínima
NMS_THRESHOLD = 0.4            # Non-Maximum Suppression
MAX_DETECTIONS = 20            # Máximo de objetos por frame

# === Obstacle Categories (COCO Classes prioritarias) ===
AERIAL_OBSTACLES = {
    # Clase COCO: Prioridad de alerta
    'person': 1,
    'bicycle': 2,
    'car': 2,
    'motorcycle': 2,
    'bus': 2,
    'truck': 2,
    'traffic light': 3,
    'fire hydrant': 3,
    'stop sign': 3,
    'bench': 4,
    'bird': 5,
    'cat': 5,
    'dog': 5,
}

# Zona de peligro aéreo (altura en la imagen)
AERIAL_ZONE_Y_MIN = 0      # Desde el tope
AERIAL_ZONE_Y_MAX = 400    # Hasta 400px (de 640 total)

# === Audio Configuration ===
TTS_ENABLED = True
TTS_RATE = 150              # Palabras por minuto
TTS_VOLUME = 0.9            # 0.0 a 1.0
ALERT_SOUND_PATH = "/home/kness/Desktop/proyecto/assets/alert.wav"

# === Thermal Management ===
TEMP_CHECK_INTERVAL = 5     # Segundos entre lecturas de temperatura
FAN_SPEED_AUTO = 50         # Velocidad de ventilador en modo normal (%)
FAN_SPEED_MAX = 100         # Velocidad máxima en throttling (%)

# === State Machine Timings ===
BOOT_TIMEOUT = 10           # Segundos máximo para boot
ERROR_RECOVERY_DELAY = 3    # Segundos antes de auto-reset
THROTTLE_SLEEP_MS = 50      # Milisegundos de sleep en modo throttling

# === Logging ===
LOG_LEVEL = "INFO"          # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_PATH = "/home/kness/Desktop/proyecto/logs/system.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5        # Número de archivos de respaldo

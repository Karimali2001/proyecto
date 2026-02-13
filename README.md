# Sistema de Asistencia a Invidentes
**Raspberry Pi 5 + Hailo-8L + Arducam IMX296**

Sistema embebido de asistencia visual para personas con discapacidad visual, utilizando IA en edge para detección de obstáculos aéreos en tiempo real.

## 🔧 Hardware

- **SBC**: Raspberry Pi 5 (8GB RAM)
- **NPU**: Hailo-8L (PCIe M.2 HAT) @ 13 TOPS
- **Cámara**: Arducam IMX296 Global Shutter (CSI)
- **Audio**: Salida USB/Jack para TTS
- **Sensores**: (Futuro) VL53L5CX ToF para distancia

## 📦 Estructura del Proyecto

```
proyecto/
├── assets/              # Recursos binarios (.hef, .wav)
├── config/              # Configuración
│   ├── pinout.py        # Pinout GPIO y constantes de hardware
│   └── constants.py     # Constantes de lógica de negocio
├── src/
│   ├── drivers/         # Capa de drivers (HAL)
│   │   ├── camera_driver.py
│   │   ├── hailo_driver.py
│   │   ├── comm_protocols.py
│   │   └── io_audio_control.py
│   ├── core/            # Lógica de negocio
│   │   ├── state_manager.py
│   │   ├── object_inference.py
│   │   ├── sensor_fusion.py
│   │   └── navigation_system.py
│   └── ui/              # Interfaz de usuario
│       ├── voice_interface.py
│       └── console_logger.py
├── logs/                # Logs del sistema
├── main.py              # Orquestador principal
└── requirements.txt     # Dependencias Python 3.11
```

## 🚀 Instalación

### 1. Clonar el repositorio
```bash
cd ~/Desktop/proyecto
```

### 2. Crear entorno virtual
```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Instalar SDK de Hailo
Descargar e instalar el Hailo Platform SDK desde [Hailo Developer Zone](https://hailo.ai/developer-zone/)

```bash
# Ejemplo (ajustar según versión)
pip install hailo-platform hailo-apps-infra
```

### 5. Preparar modelo YOLOv8s
Compilar YOLOv8s a formato .hef usando Hailo Dataflow Compiler y colocarlo en:
```bash
assets/yolov8s.hef
```

## ▶️ Ejecución

### Modo normal
```bash
sudo python3 main.py
```

> **Nota**: Requiere `sudo` para acceso a GPIO y PCIe.

### En background (systemd)
```bash
sudo systemctl enable assistive-device
sudo systemctl start assistive-device
```

## 📊 Arquitectura del Sistema

### Diagrama de Estados
El sistema implementa una máquina de estados finita con las siguientes transiciones:

- **Booting**: Verificación de hardware (PCIe, Cámara)
- **Running**: Inferencia @ 113 FPS con YOLOv8s
- **Throttling**: Limitación de FPS cuando temperatura > 80°C
- **Error**: Estado de error con log y sonido de alerta
- **Auto-Recovery**: Watchdog reinicia el sistema tras 30s

### Pipeline de Procesamiento
1. **Captura**: Frame RGB 640x640 desde cámara
2. **Redimensionamiento**: Resize a input del modelo
3. **Normalización**: Normalizar valores [0,1]
4. **Inferencia**: YOLOv8s en Hailo-8L
5. **Análisis**: Detección de obstáculos aéreos
6. **Alerta**: TTS en español si hay obstáculo

## 🎯 Funcionalidades Clave

- ✅ **Detección en tiempo real**: 113 FPS con batch=1
- ✅ **Alertas de voz**: TTS en español para obstáculos
- ✅ **Manejo térmico**: Throttling automático
- ✅ **Auto-recuperación**: Watchdog con reset automático
- ✅ **Arquitectura multithreading**: No bloquea captura durante inferencia
- ✅ **Logging robusto**: Rotación automática de logs

## 📝 Configuración

### Pinout (config/pinout.py)
- GPIO 18: PWM para ventilador
- GPIO 17, 27, 22: LEDs de estado
- GPIO 24: Buzzer de alertas

### Constantes (config/constants.py)
- Confidence threshold: 0.5
- Target FPS: 113
- Temperatura throttling: 80°C
- Temperatura crítica: 95°C

## 🔊 Clases de Obstáculos

El sistema detecta y alerta sobre:
- **Prioridad 1**: Personas
- **Prioridad 2**: Vehículos (bicicletas, autos, motos)
- **Prioridad 3**: Señalización (semáforos, señales)
- **Prioridad 4**: Mobiliario urbano
- **Prioridad 5**: Animales

## 📚 Dependencias Principales

- `picamera2`: Control de cámara CSI
- `hailo-platform`: SDK de Hailo-8L
- `opencv-python`: Procesamiento de imágenes
- `pyttsx3`: Text-to-Speech
- `RPi.GPIO`: Control de GPIO
- `psutil`: Monitoreo térmico

## 🐛 Troubleshooting

### La cámara no se detecta
```bash
# Verificar módulo de cámara
libcamera-hello --list-cameras
```

### Hailo no se detecta
```bash
# Verificar PCIe
lspci | grep Hailo
hailo scan
```

### Sin permisos GPIO
```bash
# Agregar usuario a grupo gpio
sudo usermod -a -G gpio $USER
```

## 📄 Licencia

Este proyecto está diseñado como sistema de asistencia para personas con discapacidad visual.

## 👥 Autor

Sistema desarrollado para Raspberry Pi 5 con aceleración Hailo-8L.

---

**Nota**: Este es un sistema experimental. Siempre usar en combinación con otras ayudas de movilidad.

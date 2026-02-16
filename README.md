# Proyecto de Detección de Objetos con Hailo

Este documento detalla los pasos de instalación y ejecución del proyecto en un entorno Linux (ej. Raspberry Pi con Raspberry Pi OS Bookworm).

## 1. Requisitos del Sistema (APT)

Es necesario instalar varias librerías del sistema para el manejo de la cámara, formatos de imagen y soporte de interfaz gráfica. Ejecuta el siguiente comando en la terminal:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-imath libopenexr-dev libimath-dev libxcb-cursor0
```

## 2. Configuración del Entorno Virtual

Debido a que `picamera2` es una librería del sistema, debemos crear un entorno virtual que tenga acceso a los paquetes del sistema (`--system-site-packages`).

1. **Crear el entorno virtual:**
   ```bash
   python3 -m venv venv --system-site-packages
   ```

2. **Activar el entorno:**
   ```bash
   source venv/bin/activate
   ```

3. **Instalar dependencias de Python:**
   Asegúrate de tener el archivo `requirements.txt` actualizado y ejecuta:
   ```bash
   pip install -r requirements.txt
   ```
   *Nota: Esto instalará una versión compatible de NumPy (<2.0) y la versión `headless` de OpenCV para evitar conflictos gráficos.*

## 3. Ejecución del Proyecto

Para correr la inferencia de objetos, asegúrate de estar en la carpeta raíz del proyecto (`/home/kness/Desktop/proyecto`) y ejecuta:

### Opción A: Usando el modelo incluido en assets (Recomendado)
```bash
python src/core/object_inference.py --model assets/yolov8s.hef --labels assets/coco.txt
```

### Opción B: Usando rutas por defecto
Si tienes los modelos en las rutas hardcodeadas del script:
```bash
python src/core/object_inference.py
```

Para detener la ejecución, presiona `Ctrl+C` en la terminal.

import os
from pathlib import Path
import subprocess

# RUTA AL BINARIO DE PIPER
PIPER_PATH = "/home/kness/Desktop/proyecto/venv/bin/piper"
# RUTA AL MODELO ONNX
BASE_DIRECTORY = Path.cwd()
MODEL_PATH = BASE_DIRECTORY / "assets/es_MX-claude-high.onnx"

class AudioOutputDriver:
    def __init__(self):
        # Desactivamos los logs innecesarios de ONNX para que no ensucien la terminal
        os.environ["ORT_LOGGING_LEVEL"] = "3" 

    def speak(self, text, length_scale="1.0"):
        if not MODEL_PATH.exists():
            print(f"[ERROR]: No existe el modelo en: {MODEL_PATH}")
            return

        # EXPLICACIÓN DE LAS MEJORAS:
        # 1. --buffer-size=200000: Evita el mensaje de 'underrun' dándole más aire al CPU.
        # 2. 2>/dev/null: Escondemos los mensajes de error de ONNX/GPU.
        command = (
            f'echo "{text}" | '
            f"{PIPER_PATH} --model {MODEL_PATH} --output_raw --length_scale {length_scale} 2>/dev/null | "
            f"aplay -D plughw:2,0 -f S16_LE -r 22050 -c 1 --buffer-size=200000 2>/dev/null"
        )
        
        print(f"🎙️ Karim dice: {text}")
        subprocess.run(command, shell=True)

if __name__ == "__main__":
    audio = AudioOutputDriver()
    audio.speak("Sistema de audio optimizado. Sin avisos de error y funcionando en estéreo.", "1.0")
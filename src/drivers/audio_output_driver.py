from pathlib import Path
import subprocess

BASE_DIRECTORY = Path.cwd()

MODEL_PATH = Path(BASE_DIRECTORY / "assets/es_MX-claude-high.onnx")


class AudioOutputDriver:
    def __init__(self):
        pass

    def speak(self, text, length_scale="0.8"):
        if not Path.exists(MODEL_PATH):
            print("[audio_output_driver.py]: No existe esta ruta")
            print(MODEL_PATH)
            subprocess.run(["espeak", "-a", "200", "-v", "es-la", text])
            return

        command = (
            f'echo "{text}" | '
            f"piper --model {MODEL_PATH} --output_raw --length_scale {length_scale} | "
            f"paplay --raw --format=s16le --rate=22050 --channels=1"
        )
        subprocess.run(command, shell=True, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    
    audio = AudioOutputDriver()
    audio.speak("hola me llamo karim", "0.5")

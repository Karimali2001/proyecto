from pathlib import Path
import subprocess
import time
import pygame
import numpy as np


# RUTA AL BINARIO DE PIPER
PIPER_PATH = "/home/kness/Desktop/proyecto/venv/bin/piper"
# RUTA AL MODELO ONNX
BASE_DIRECTORY = Path.cwd()
MODEL_PATH = BASE_DIRECTORY / "assets/es_MX-claude-high.onnx"


class AudioOutputDriver:
    def __init__(self, sample_rate=44100):
        # Initialize mixer of pygame in stereo mode (2 channels)
        pygame.mixer.pre_init(sample_rate, -16, 2, 512)
        pygame.mixer.init()
        self.sample_rate = sample_rate

    def generate_beep(self, frequency=150, duration=0.4, volume=0.8):
        """Generates a beep sound with a 'hollow' body using a square wave and fade-out"""
        n_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, n_samples, False)

        # 1. Use a square wave (sign of sine) for a 'dirtier' and lower tone
        wave = np.sign(np.sin(frequency * t * 2 * np.pi))

        # 2. Apply a decay envelope (Fade-out)
        # This makes it sound like a 'DUMMM...' hit instead of a 'PIIIII'
        envelope = np.exp(-3 * t / duration)
        wave = wave * envelope

        # Scale to 16-bit PCM
        audio = np.int16(wave * volume * 32767)

        # Duplicate to 2 channels
        stereo_audio = np.column_stack((audio, audio))
        return pygame.sndarray.make_sound(stereo_audio)

    def play_spatial_sound(self, position="center"):
        """
        Plays an alert sound and sends it to the indicated speaker.
        """
        if position == "center":
            # HOLLOW TONE: Higher, longer, and louder (Imminent Danger)
            sound = self.generate_beep(frequency=880, duration=0.3, volume=0.9)
            channel = sound.play()
            if channel:
                channel.set_volume(1.0, 1.0)  # Left and Right at maximum
            print("Alert: CENTER (Front)")

        elif position == "left":
            # LEFT OBSTACLE TONE: Medium frequency
            sound = self.generate_beep(frequency=500, duration=0.15, volume=0.7)
            channel = sound.play()
            if channel:
                channel.set_volume(1.0, 0.0)  # Left only
            print("Alert: LEFT")

        elif position == "right":
            # RIGHT OBSTACLE TONE: Medium frequency
            sound = self.generate_beep(frequency=500, duration=0.15, volume=0.7)
            channel = sound.play()
            if channel:
                channel.set_volume(0.0, 1.0)  # Right only
            print("Alert: RIGHT")

    def speak(self, text, length_scale="1.0"):

        if not Path(PIPER_PATH).exists():
            print(f"[ERROR]: No se encontró el binario de Piper en: {PIPER_PATH}")
            return

        if not MODEL_PATH.exists():
            print(f"[ERROR]: No existe el modelo en: {MODEL_PATH}")
            return

        print(f"🗣️ Sintetizando voz: '{text}'")

        # Temporal saved archive in RAM of Linux
        temp_wav = "/tmp/karim_voz.wav"

        # We tell Piper not to use 'raw', but to save a perfect WAV file
        # We hide GPU warnings using 2>/dev/null
        command = (
            f'echo "{text}" | '
            f"{PIPER_PATH} --model {MODEL_PATH} --length_scale {length_scale} "
            f"--output_file {temp_wav} 2>/dev/null"
        )

        # We run Piper (blocks until the .wav file is ready)
        subprocess.run(command, shell=True)

        # Let Pygame speak!
        try:
            # Load the generated voice
            voice = pygame.mixer.Sound(temp_wav)

            # Play it (Pygame automatically adjusts to I2S format)
            voice.play()

            # Keep the script alive until the voice finishes
            while pygame.mixer.get_busy():
                time.sleep(0.1)

        except Exception as e:
            print(f"[ERROR] Pygame failed to play the voice: {e}")


if __name__ == "__main__":
    audio = AudioOutputDriver()

    time.sleep(1)
    audio.play_spatial_sound("left")

    time.sleep(1)
    audio.play_spatial_sound("right")

    time.sleep(1)
    audio.play_spatial_sound("center")

    time.sleep(1)
    audio.speak(
        "Sistema de audio. Sin avisos de error y funcionando en estéreo.",
        "1.0",
    )

    time.sleep(2)  # Wait to let the audio finish before exiting

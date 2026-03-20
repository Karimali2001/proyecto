from pathlib import Path
import subprocess
import time
import pygame
import numpy as np


# RUTA AL BINARIO DE PIPER
PIPER_PATH = "/home/kness/Desktop/proyecto/venv/bin/piper"
BASE_DIRECTORY = Path.cwd()
MODEL_PATH = BASE_DIRECTORY / "assets/es_MX-claude-high.onnx"


class Audio:
    def __init__(self, sample_rate=44100):
        pygame.mixer.pre_init(sample_rate, -16, 2, 512)
        pygame.mixer.init()
        self.sample_rate = sample_rate
        self.current_process = None
        self.stop_flag = False

        print("[Audio] Sintetizando sonidos en memoria RAM...")
        # 🔥 EL SINTETIZADOR INTERNO: Latencia cero, sin archivos externos 🔥
        self.sound_bank = {
            # 1. HUECO: Empieza en 300Hz y cae rápidamente a 50Hz (onda triangular, suena a caída/peligro grave)
            "hole": self._create_synth_sound(
                300, 50, 0.4, wave_type="triangle", volume=1.0
            ),
            # 2. AÉREO: Empieza en 1200Hz y sube a 1500Hz (onda senoidal pura, suena a radar/cristal/ping!)
            "aerial": self._create_synth_sound(
                1200, 1500, 0.2, wave_type="sine", volume=0.7
            ),
            # 3. UI/BOTONES: Un "bloop" rápido de 600Hz a 400Hz
            "ui": self._create_synth_sound(600, 400, 0.1, wave_type="sine", volume=0.7),
        }

    def _create_synth_sound(
        self, start_freq, end_freq, duration, wave_type="sine", volume=0.8
    ):
        """Genera un sonido sintetizado matemáticamente con barrido de frecuencia y envolvente."""
        n_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, n_samples, False)

        # Barrido de frecuencia (Dinámico)
        freqs = np.linspace(start_freq, end_freq, n_samples)
        phase = np.cumsum(freqs) / self.sample_rate

        # Generador de Forma de Onda
        if wave_type == "sine":
            wave = np.sin(2 * np.pi * phase)  # Suave y limpio
        elif wave_type == "square":
            wave = np.sign(np.sin(2 * np.pi * phase))  # Ruidoso y robótico
        elif wave_type == "triangle":
            wave = (
                2 * np.abs(2 * (phase - np.floor(phase + 0.5))) - 1
            )  # Intermedio (zumbido)

        # Envolvente (Fade out rápido para que suene como un "golpe" y no un timbre continuo)
        envelope = np.exp(-5 * t / duration)
        wave = wave * envelope * volume

        # Convertir a audio PCM de 16-bits estéreo
        audio = np.int16(wave * 32767)
        stereo = np.column_stack((audio, audio))
        return pygame.sndarray.make_sound(stereo)

    def play_spatial_sound(self, position="center", sound_type="ui"):
        """Reproduce un sonido sintetizado en el canal espacial indicado."""
        sound = self.sound_bank.get(sound_type)
        if not sound:
            return

        channel = sound.play()
        if channel:
            # Paneo 3D
            if position == "center":
                channel.set_volume(1.0, 1.0)  # Izquierda y Derecha al máximo
            elif position == "left":
                channel.set_volume(1.0, 0.0)  # Solo Izquierda
            elif position == "right":
                channel.set_volume(0.0, 1.0)  # Solo Derecha

            print(
                f"🔊 [Efecto de Sonido] Tipo: '{sound_type}' | Posición: '{position.upper()}'"
            )

    def speak(self, text, length_scale="1.0"):
        self.stop_flag = False

        if not Path(PIPER_PATH).exists() or not MODEL_PATH.exists():
            print(f"[ERROR]: Faltan binarios o modelo de Piper.")
            return

        print(f"🗣️ Sintetizando voz: '{text}'")
        temp_wav = "/tmp/karim_voz.wav"
        command = f'echo "{text}" | {PIPER_PATH} --model {MODEL_PATH} --length_scale {length_scale} --output_file {temp_wav} 2>/dev/null'

        self.current_process = subprocess.Popen(command, shell=True)
        self.current_process.communicate()
        self.current_process = None

        if self.stop_flag:
            return

        try:
            voice = pygame.mixer.Sound(temp_wav)
            voice.play()
            while pygame.mixer.get_busy():
                if self.stop_flag:
                    break
                time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] Pygame failed to play the voice: {e}")

    def stop(self):
        self.stop_flag = True
        pygame.mixer.stop()
        if self.current_process is not None:
            self.current_process.terminate()

    def speak_thread(self):
        self.speak(
            "Sistema de audio. Sin avisos de error y funcionando en estéreo.", "1.0"
        )


if __name__ == "__main__":
    audio = Audio()

    # Prueba del nuevo sintetizador
    time.sleep(1)
    audio.play_spatial_sound("left", "hole")
    time.sleep(1)
    audio.play_spatial_sound("right", "aerial")
    time.sleep(1)
    audio.play_spatial_sound("center", "ui")
    time.sleep(1)

    audio.stop()

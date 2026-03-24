from pathlib import Path
import subprocess
import time
import pygame
import numpy as np


# PATH TO PIPER BINARY
PIPER_PATH = "/home/kness/Desktop/proyecto/venv/bin/piper"
BASE_DIRECTORY = Path.cwd()
MODEL_PATH = BASE_DIRECTORY / "assets/es_MX-claude-high.onnx"


class Audio:
    def __init__(self, sample_rate=44100):
        pygame.mixer.pre_init(sample_rate, -16, 2, 512)
        pygame.mixer.init()
        # Reservamos el canal 0 estrictamente para la voz principal
        pygame.mixer.set_reserved(1)
        self.voice_channel = pygame.mixer.Channel(0)

        self.sample_rate = sample_rate
        self.current_process = None
        self.stop_flag = False

        print("[Audio] Synthesizing sounds in RAM...")
        self.sound_bank = {
            "hole": self._create_synth_sound(
                300, 50, 0.4, wave_type="triangle", volume=1.0
            ),
            "aerial": self._create_synth_sound(
                1200, 1500, 0.2, wave_type="sine", volume=0.7
            ),
            "ui": self._create_synth_sound(600, 400, 0.1, wave_type="sine", volume=0.7),
            "sonar_left": self._create_synth_sound(
                400, 400, 0.1, wave_type="triangle", volume=1.0
            ),
            "sonar_center": self._create_synth_sound(
                600, 600, 0.1, wave_type="triangle", volume=1.0
            ),
            "sonar_right": self._create_synth_sound(
                800, 800, 0.1, wave_type="triangle", volume=1.0
            ),
        }

    def _create_synth_sound(
        self, start_freq, end_freq, duration, wave_type="sine", volume=0.8
    ):
        n_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, n_samples, False)

        freqs = np.linspace(start_freq, end_freq, n_samples)
        phase = np.cumsum(freqs) / self.sample_rate

        if wave_type == "sine":
            wave = np.sin(2 * np.pi * phase)
        elif wave_type == "square":
            wave = np.sign(np.sin(2 * np.pi * phase))
        elif wave_type == "triangle":
            wave = 2 * np.abs(2 * (phase - np.floor(phase + 0.5))) - 1

        envelope = np.exp(-5 * t / duration)
        wave = wave * envelope * volume

        audio = np.int16(wave * 32767)
        stereo = np.column_stack((audio, audio))
        return pygame.sndarray.make_sound(stereo)

    def play_spatial_sound(self, position="center", sound_type="ui"):
        if sound_type == "sonar":
            sound_type = f"sonar_{position}"

        sound = self.sound_bank.get(sound_type)
        if not sound:
            return

        # find_channel() busca un canal libre (ignora el 0 que está reservado)
        channel = pygame.mixer.find_channel()
        if channel:
            channel.play(sound)
            if position == "center":
                channel.set_volume(1.0, 1.0)
            elif position == "left":
                channel.set_volume(1.0, 0.0)
            elif position == "right":
                channel.set_volume(0.0, 1.0)

    def speak_fast_background(self, text, length_scale="0.6"):
        """Synthesizes and plays a very fast voice on a secondary channel (does NOT cut off the main voice)"""
        temp_wav = f"/tmp/karim_fast_{time.time()}.wav"
        command = f'echo "{text}" | {PIPER_PATH} --model {MODEL_PATH} --length_scale {length_scale} --output_file {temp_wav} 2>/dev/null'

        subprocess.run(command, shell=True)
        try:
            fast_voice = pygame.mixer.Sound(temp_wav)
            channel = pygame.mixer.find_channel()
            if channel:
                channel.play(fast_voice)
        except Exception as e:
            print(f"[ERROR] Pygame failed to play fast voice: {e}")

    def speak(self, text, length_scale="1.0"):
        self.stop_flag = False

        if not Path(PIPER_PATH).exists() or not MODEL_PATH.exists():
            print(f"[ERROR]: Piper binaries or model are missing.")
            return

        print(f"[Audio] Synthesizing voice: '{text}'")
        temp_wav = "/tmp/karim_voz.wav"
        command = f'echo "{text}" | {PIPER_PATH} --model {MODEL_PATH} --length_scale {length_scale} --output_file {temp_wav} 2>/dev/null'

        self.current_process = subprocess.Popen(command, shell=True)
        self.current_process.communicate()
        self.current_process = None

        if self.stop_flag:
            return

        try:
            voice = pygame.mixer.Sound(temp_wav)
            self.voice_channel.play(voice)
            while self.voice_channel.get_busy():
                if self.stop_flag:
                    self.voice_channel.stop()
                    break
                time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] Pygame failed to play the voice: {e}")

    def stop(self):
        """Stops main voice immediately and terminates any ongoing synthesis process"""
        self.stop_flag = True
        self.voice_channel.stop()
        if self.current_process is not None:
            self.current_process.terminate()

    def is_busy(self):
        if self.current_process is not None and self.current_process.poll() is None:
            return True
        if self.voice_channel.get_busy():
            return True
        return False


if __name__ == "__main__":
    audio = Audio()
    time.sleep(1)
    audio.play_spatial_sound("left", "hole")
    time.sleep(1)
    audio.play_spatial_sound("right", "aerial")
    time.sleep(1)
    audio.play_spatial_sound("center", "ui")
    time.sleep(1)
    audio.stop()

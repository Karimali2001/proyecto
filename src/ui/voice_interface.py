import speech_recognition as sr
import json
import time
from pathlib import Path
from vosk import Model, KaldiRecognizer
from src.drivers.microphone_driver import no_alsa_error

from src.core.priority_queue import AudioPriorityQueue

base_path = Path.cwd()


class VoiceInterface:
    def __init__(self, audio_queue):
        self.audio_queue = audio_queue
        self.recognizer = sr.Recognizer()

        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 400
        self.recognizer.dynamic_energy_threshold = False

        model_path = Path(base_path / "assets" / "vosk-model-small-es-0.42")

        if not model_path.exists():
            print(f"[Error] No se encontró el modelo Vosk en: {model_path}")
            self.vosk_model = None
        else:
            print(
                "[VoiceInterface] Cargando modelo Vosk a la RAM... (Solo ocurre una vez)"
            )
            # Mantenemos el modelo vivo en memoria para latencia cero al presionar botones
            # We load the model once and reuse it for all recognition tasks insuring less latency when pressing button pattern
            self.vosk_model = Model(str(model_path))
            print("[VoiceInterface] ¡Modelo Vosk listo!")

    def listen_and_recognize(self):
        """
        Listens to the microphone and uses VOSK 100% OFFLINE to convert audio to text.
        """
        if self.vosk_model is None:
            print("[VoiceInterface] Error: Cannot listen, Vosk model is missing.")
            return None

        with no_alsa_error():
            # ¡AQUÍ ESTÁ LA MAGIA!
            # Forzamos los 16000Hz para Vosk y el chunk_size de 8192 para evitar los cortes
            source = sr.Microphone(chunk_size=8192)

        with source:
            print("[VoiceInterface] Calibrating for ambient noise...")

            print("[VoiceInterface] Listening... (Speak now!)")

            # 1. Start signal via spatial sound queue instead of speaking "Bip"
            start_cmd = json.dumps(
                {"position": "center", "frequencyCenter": 800, "frequencySide": 800}
            )
            self.audio_queue.put(AudioPriorityQueue.VOICE_MENU, start_cmd)

            # Wait for it to play so microphone doesn't record the beep itself
            time.sleep(0.5)

            try:
                # Capture the audio (stops if user stops talking, or forcefully after 7 seconds)
                audio_data = self.recognizer.listen(
                    source, timeout=5, phrase_time_limit=7
                )

                # Save the captured audio to a file for debugging purposes
                debug_audio_path = (
                    base_path / "assets" / "recordings" / "debug_audio.wav"
                )
                debug_audio_path.parent.mkdir(parents=True, exist_ok=True)
                with open(debug_audio_path, "wb") as f:
                    f.write(audio_data.get_wav_data())
                print(f"[VoiceInterface] Saved debug audio to {debug_audio_path}")

                # 2. End signal when it finishes capturing
                end_cmd = json.dumps(
                    {"position": "center", "frequencyCenter": 400, "frequencySide": 400}
                )
                self.audio_queue.put(AudioPriorityQueue.VOICE_MENU, end_cmd)

                print("[VoiceInterface] Processing audio offline...")

                # Use KaldiRecognizer directly with the pre-loaded Vosk model
                rec = KaldiRecognizer(self.vosk_model, 16000)
                rec.AcceptWaveform(
                    audio_data.get_raw_data(convert_rate=16000, convert_width=2)
                )
                vosk_json = rec.Result()

                # Vosk returns a JSON string, convert it to a Python dict
                result_dict = json.loads(vosk_json)

                # Extract only the "text" key
                text = result_dict.get("text", "")

                print(f"[VoiceInterface] Recognized text: '{text}'")
                return text

            except sr.WaitTimeoutError:
                print("[VoiceInterface] Timeout: No speech detected.")
            except Exception as e:
                print(f"[VoiceInterface] Recognition error: {e}")

        return None

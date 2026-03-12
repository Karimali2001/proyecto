import pyaudio
import wave
import ctypes
from pathlib import Path
from contextlib import contextmanager

# Define C types to intercept and silence ALSA warnings
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
)


def py_error_handler(filename, line, function, err, fmt):
    pass


c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)


@contextmanager
def no_alsa_error():
    """Context manager to suppress PyAudio's ALSA C-level error warnings on Linux."""
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
        asound.snd_lib_error_set_handler(None)
    except:
        yield


class MicrophoneDriver:
    """
    Hardware abstraction layer for standard USB microphones (e.g., MAONO USB Lavalier).
    Uses PyAudio to interface with the system's audio capture device.
    """

    # Increased chunk_size to 8192 to prevent buffer overflows and choppy audio on embedded Linux
    def __init__(self, sample_rate=44100, chunk_size=8192):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.format = pyaudio.paInt16
        self.channels = 1

        # Initialize PyAudio inside the suppressor to hide the ALSA spam
        with no_alsa_error():
            self.audio = pyaudio.PyAudio()

        self.stream = None

    def start_stream(self):
        """Initializes and starts capturing audio from the default USB microphone."""
        try:
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
            print("Microphone stream started successfully.")
        except Exception as e:
            print(f"Failed to start microphone stream: {e}")

    def read_audio(self):
        """
        Reads a chunk of audio data from the microphone buffer.
        Returns raw bytes, or None if the stream is not active.
        """
        if self.stream and self.stream.is_active():
            # exception_on_overflow=False prevents crashes, but a larger chunk_size
            # prevents the data loss that causes stuttering audio
            return self.stream.read(self.chunk_size, exception_on_overflow=False)
        return None

    def stop_stream(self):
        """Stops the audio stream and cleanly releases hardware resources."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        print("Microphone stream stopped.")

    def record_audio_to_file(self, filename="assets/recordings/output.wav", duration=5):
        """
        Records audio from the microphone driver and saves it as a WAV file.
        """
        # Ensure the directory exists
        Path(filename).parent.mkdir(parents=True, exist_ok=True)

        self.start_stream()
        frames = []

        print(f"Recording for {duration} seconds...")
        # Calculate total chunks needed for the specified duration
        num_chunks = int((self.sample_rate / self.chunk_size) * duration)

        for _ in range(num_chunks):
            data = self.read_audio()
            if data:
                frames.append(data)

        self.stop_stream()

        # Save data to a WAV file
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))

        print(f"Audio saved to: {filename}")


if __name__ == "__main__":
    mic_driver = MicrophoneDriver()
    mic_driver.record_audio_to_file()

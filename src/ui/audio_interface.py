import time


class AudioInterface:
    """UI-layer facade that presents audio feedback to the user."""

    def __init__(self, audio_driver):
        self.audio_driver = audio_driver

    def consume_queue_forever(self, audio_queue):
        """Consumes queued audio messages and dispatches them to the driver."""
        while True:
            priority, message = audio_queue.get()
            try:
                self.handle_message(priority, message)
            finally:
                audio_queue.task_done()

    def handle_message(self, priority, message):
        """Routes high-level UI audio messages to the low-level audio driver."""
        if isinstance(message, dict):
            action = message.get("action")

            if action == "sound":
                self.play_spatial_sound(
                    position=message.get("position", "center"),
                    sound_type=message.get("sound_type", "ui"),
                )
                time.sleep(0.2)
            elif action == "fast_voice":
                text = message.get("text")
                if text:
                    self.speak_fast_background(text)
            return

        if isinstance(message, str):
            print(f"\n[Audio Thread] Priority {priority}: {message}")
            self.speak(message)

    def play_spatial_sound(self, position="center", sound_type="ui"):
        self.audio_driver.play_spatial_sound(position=position, sound_type=sound_type)

    def speak_fast_background(self, text, length_scale="0.6"):
        self.audio_driver.speak_fast_background(text, length_scale=length_scale)

    def speak(self, text, length_scale="1.0"):
        self.audio_driver.speak(text, length_scale=length_scale)

    def stop(self):
        self.audio_driver.stop()

    def is_busy(self):
        return self.audio_driver.is_busy()

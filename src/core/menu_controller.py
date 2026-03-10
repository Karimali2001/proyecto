from gpiozero import Button
import time


from src.ui.voice_interface import VoiceInterface

# pyright: reportAttributeAccessIssue=false


class MenuController:
    def __init__(self, object_detector, audio_queue):

        self.object_detector = object_detector
        self.audio_queue = audio_queue

        # Initialize Voice Interface for STT commands
        self.voice_interface = VoiceInterface(audio_queue)

        # bounce_time is set to 0.1 seconds to prevent multiple triggers from a single press
        self.btn_1 = Button(27, bounce_time=0.05)
        self.btn_2 = Button(17, bounce_time=0.05)

        # semafore to prevent from double command
        self.last_both_pressed = 0.0

        # Callbacks
        self.btn_1.when_pressed = self.handle_btn_1
        self.btn_2.when_pressed = self.handle_btn_2

    def handle_btn_1(self):

        time.sleep(0.05)

        if self.btn_2.is_pressed:
            self.both_btns_pressed()
            return

        if self.btn_1.is_pressed:
            if len(self.object_detector.getLastDetection()) == 0:
                self.audio_queue.put(
                    self.audio_queue.OBJECT_DETECTION, "Camino Despejado"
                )
            else:
                complete_frase = ",".join(self.object_detector.getLastDetection())
                self.audio_queue.put(self.audio_queue.OBJECT_DETECTION, complete_frase)
            print("[Btn1] btn1 pressed")

    def handle_btn_2(self):

        time.sleep(0.05)

        if self.btn_1.is_pressed:
            self.both_btns_pressed()
            return

        if self.btn_2.is_pressed:
            print("[Btn2] Read text")

    def both_btns_pressed(self):

        current_time = time.time()

        if current_time - self.last_both_pressed > 0.5:
            # Start the STT process

            text_command = self.voice_interface.listen_and_recognize()

            if text_command:
                # For now, just print the result or send to the audio queue to repeat it
                print(f"[MenuController] Command received: {text_command}")

            self.last_both_pressed = current_time

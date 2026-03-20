from gpiozero import Button
import time
import difflib
import threading

from src.ui.voice_interface import VoiceInterface

# pyright: reportAttributeAccessIssue=false


class MenuController:
    def __init__(
        self,
        object_detector,
        navigation,
        hole_detector,
        audio_queue,
        ocr,
        aerial_obstacle_detector=None,
    ):

        self.object_detector = object_detector
        self.hole_detector = hole_detector
        self.audio_queue = audio_queue
        self.ocr = ocr
        self.navigation = navigation
        self.aerial_obstacle_detector = aerial_obstacle_detector

        # Initialize Voice Interface for STT commands
        self.voice_interface = VoiceInterface(audio_queue)

        # bounce_time is set to 0.1 seconds to prevent multiple triggers from a single press
        self.btn_1 = Button(27, bounce_time=0.05)
        self.btn_2 = Button(17, bounce_time=0.05)

        # semaphore to prevent double command
        self.last_both_pressed = 0.0

        self.last_btn_2_press = 0.0
        self.btn_2_timer = None

        # Callbacks
        self.btn_1.when_pressed = self.handle_btn_1
        self.btn_2.when_pressed = self.handle_btn_2

    def handle_btn_1(self):
        time.sleep(0.05)

        # If button 2 is pressed, it is a voice command
        if self.btn_2.is_pressed:
            self.both_btns_pressed()
            return

        current_time = time.time()

        # Double Click Logic for Button 1
        # We use a timer 'btn_1_timer' that must be initialized in __init__
        if not hasattr(self, "last_btn_1_press"):
            self.last_btn_1_press = 0.0
            self.btn_1_timer = None

        if current_time - self.last_btn_1_press < 0.6:
            # Double click detected!
            self.last_btn_1_press = 0.0
            if self.btn_1_timer is not None:
                self.btn_1_timer.cancel()
            self._double_click_obj()
        else:
            # First click
            self.last_btn_1_press = current_time
            if self.btn_1_timer is not None:
                self.btn_1_timer.cancel()

            # We wait 0.6s. If no double click, we read the objects.
            self.btn_1_timer = threading.Timer(0.6, self._single_click_obj)
            self.btn_1_timer.start()

    def _single_click_obj(self):
        """Single click action: Reads the objects in front."""
        if self.audio_queue.is_priority_active_or_queued(
            self.audio_queue.OBJECT_DETECTION
        ):
            return

        if len(self.object_detector.getLastDetection()) == 0:
            self.audio_queue.put(self.audio_queue.OBJECT_DETECTION, "Clear path")
        else:
            complete_phrase = ", ".join(self.object_detector.getLastDetection())
            self.audio_queue.put(self.audio_queue.OBJECT_DETECTION, complete_phrase)
        print("[Btn1] Single Click (Object Detection)")

    def _double_click_obj(self):
        """Double click action: Activates the free seat finder."""
        print("[Btn1] Double Click! Seat finder.")
        is_active = self.object_detector.toggle_seat_finder()
        state = "activated" if is_active else "deactivated"

        # Inform the user by voice
        self.audio_queue.put(
            self.audio_queue.VOICE_MENU, f"Free seat finder {state}"
        )

    def handle_btn_2(self):
        time.sleep(0.05)

        # If button 1 is pressed, it's a combined command
        if self.btn_1.is_pressed:
            self.both_btns_pressed()
            return

        current_time = time.time()

        # Increased to 0.6s to give a more human margin to double click
        if current_time - self.last_btn_2_press < 0.6:
            # Double Click Detected!
            self.last_btn_2_press = 0.0  # Reset to avoid triple clicks

            # Cancel single click action if it was pending
            if self.btn_2_timer is not None:
                self.btn_2_timer.cancel()

            # Execute double click action
            self._double_click_ocr()
        else:
            # First Click Detected
            self.last_btn_2_press = current_time

            if self.btn_2_timer is not None:
                self.btn_2_timer.cancel()

            # Wait 0.6 seconds. If there is no other click in that time, execute normal photo.
            self.btn_2_timer = threading.Timer(0.6, self._single_click_ocr)
            self.btn_2_timer.start()

    def _single_click_ocr(self):
        """Single Click Action: Read text with Gemini/EasyOCR."""
        if self.audio_queue.is_priority_active_or_queued(
            self.audio_queue.TEXT_RECOGNITION
        ):
            print(
                "[MenuController] Text recognition message already active or queued, skipping new message."
            )
            return

        print("[Btn2] Read text (Single Click)")
        if self.ocr:
            detected_text = self.ocr.capture_and_read(stream_name="main")

            if detected_text and detected_text not in [
                "Hardware error.",
                "No text found in the image.",
                "Camera not initialized.",
                "Could not capture the image.",
            ]:
                self.audio_queue.put(self.audio_queue.TEXT_RECOGNITION, detected_text)
            elif detected_text == "No text found in the image.":
                self.audio_queue.put(
                    self.audio_queue.TEXT_RECOGNITION, "No text found"
                )
            else:
                self.audio_queue.put(
                    self.audio_queue.TEXT_RECOGNITION,
                    "There was an error reading the text",
                )
        else:
            self.audio_queue.put(
                self.audio_queue.TEXT_RECOGNITION, "Text reader not initialized"
            )

    def _double_click_ocr(self):
        """Double Click Action: Activates or deactivates continuous Sign Mode."""
        print("[Btn2] Double Click! Toggling Continuous OCR Mode.")
        if self.ocr:
            is_active = self.ocr.toggle_continuous_mode()
            state = "activated" if is_active else "deactivated"
            self.audio_queue.put(
                self.audio_queue.VOICE_MENU,
                f"Sign reading mode {state}.",
            )
        else:
            self.audio_queue.put(
                self.audio_queue.VOICE_MENU, "Text reader not initialized."
            )

    def both_btns_pressed(self):

        if self.audio_queue.is_priority_active_or_queued(self.audio_queue.VOICE_MENU):
            print(
                "[MenuController] Voice menu already active or queued, skipping new voice menu activation."
            )
            return

        current_time = time.time()

        if current_time - self.last_both_pressed > 0.5:
            self.last_both_pressed = current_time

            # Loop to allow retrying if the command is not understood
            while True:
                text_command = self.voice_interface.listen_and_recognize()

                # If timeout or nothing was recognized, just exit
                if not text_command:
                    print(
                        "[MenuController] No voice detected or timeout reached. Exiting voice menu."
                    )
                    break

                text_lower = text_command.lower().strip()
                print(f"[MenuController] Processing command: '{text_lower}'")

                # Define standard commands for difflib matching
                standard_commands = [
                    "menu",
                    "donde estoy",
                    "calibrar",
                    "huecos",
                    "aereo",
                ]

                # Check standard commands using difflib for fuzzy matching
                matches = difflib.get_close_matches(
                    text_lower, standard_commands, n=1, cutoff=0.6
                )

                if matches:
                    best_match = matches[0]
                    if best_match == "menu":
                        print("[MenuController] Action detected: Menu")

                        menu_text = (
                            "This is the help menu. You can say the following commands. "
                            "Number one. Say Menu. to list what I can do for you. "
                            "Number two. Say Where am I. to know your current location on the map. "
                            "Number three. Say Calibrate. to adjust the sensor to your current posture and height. "
                            "Number four. Say Holes. to activate or deactivate the detection of holes in the floor. "
                            "Number five. Say Aerial. to activate or deactivate the detection of aerial obstacles. "
                            "To continue, press the buttons again and say a command."
                        )

                        self.audio_queue.put(self.audio_queue.VOICE_MENU, menu_text)

                    elif best_match == "donde estoy":
                        print("[MenuController] Action detected: Where am I")

                        location_message = self.navigation.get_where_am_i_message()

                        self.audio_queue.put(
                            self.audio_queue.NAVIGATION, location_message
                        )
                    elif best_match == "calibrar":
                        print("[MenuController] Action detected: Calibrate")

                        # 1. Warn user to stay still
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Calibrating. Please stay still looking forward in a clear space.",
                        )

                        # If hole_detector has a calibrate function or activates here, we call it
                        if self.hole_detector:
                            self.hole_detector.is_active = True
                            print(
                                "[MenuController] Hole detector activated by calibration."
                            )

                        self.hole_detector.recalibrate_sensor()

                        # 2. Inform it has finished
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Calibration completed successfully. Ready to walk.",
                        )

                    elif best_match == "huecos":
                        print("[MenuController] Action detected: Holes")
                        if self.hole_detector:
                            is_active = self.hole_detector.toggle_radar()
                            state = "activated" if is_active else "deactivated"
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"Holes detection {state}.",
                            )

                    elif best_match == "aereo":
                        print("[MenuController] Action detected: Aerial")
                        if self.aerial_obstacle_detector:
                            is_active = self.aerial_obstacle_detector.toggle_radar()
                            state = "activated" if is_active else "deactivated"
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"Aerial obstacles detection {state}.",
                            )

                    break  # Command understood, exit the loop

                else:
                    print("[MenuController] Command not recognized, asking to repeat.")
                    self.audio_queue.put(
                        self.audio_queue.VOICE_MENU,
                        "I didn't understand you. Please try again by pressing both buttons.",
                    )
                    break  # Exit after one attempt to avoid infinite loop in case of unrecognized commands

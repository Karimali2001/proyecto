from gpiozero import Button
import time
import difflib


from src.ui.voice_interface import VoiceInterface

# pyright: reportAttributeAccessIssue=false


class MenuController:
    def __init__(
        self,
        object_detector,
        navigation,
        obstacle_detector,
        audio_queue,
        ocr,
        depth_detector=None,
    ):

        self.object_detector = object_detector
        self.obstacle_detector = obstacle_detector
        self.audio_queue = audio_queue
        self.ocr = ocr
        self.navigation = navigation
        self.depth_detector = depth_detector

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
            if self.ocr:
                detected_text = self.ocr.capture_and_read(stream_name="main")

                if detected_text and detected_text not in [
                    "Error de hardware.",
                    "No encontré ningún texto en la imagen.",
                    "Cámara no inicializada.",
                    "No se pudo capturar la imagen.",
                ]:
                    self.audio_queue.put(
                        self.audio_queue.TEXT_RECOGNITION, detected_text
                    )
                elif detected_text == "No encontré ningún texto en la imagen.":
                    self.audio_queue.put(
                        self.audio_queue.TEXT_RECOGNITION, "No encontré texto"
                    )
                else:
                    self.audio_queue.put(
                        self.audio_queue.TEXT_RECOGNITION,
                        "Hubo un error al leer el texto",
                    )
            else:
                self.audio_queue.put(
                    self.audio_queue.TEXT_RECOGNITION, "Lector de texto no inicializado"
                )

    def both_btns_pressed(self):

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
                        print("[MenuController] Acción detectada: Menú")

                        menu_text = (
                            "Este es el menú de ayuda. Puedes decir los siguientes comandos. "
                            "Número uno. Di Menú. para listar qué puedo hacer por ti. "
                            "Número dos. Di Dónde estoy. para conocer tu posición actual en el mapa. "
                            "Número tres. Di Calibrar. para ajustar el sensor a tu postura y altura actual. "
                            "Número cuatro. Di Huecos. para activar o desactivar la detección de huecos en el piso. "
                            "Número cinco. Di Aéreo. para activar o desactivar la detección de obstáculos oclusión facial. "
                            "Para continuar. vuelve a presionar los botones y di un comando."
                        )

                        self.audio_queue.put(self.audio_queue.VOICE_MENU, menu_text)

                    elif best_match == "donde estoy":
                        print("[MenuController] Acción detectada: Donde estoy")

                        ubication_message = self.navigation.get_where_am_i_message()

                        self.audio_queue.put(
                            self.audio_queue.NAVIGATION, ubication_message
                        )
                    elif best_match == "calibrar":
                        print("[MenuController] Acción detectada: Calibrar")

                        # 1. Avisamos al usuario que se quede quieto
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Calibrando. Por favor quédate quieto mirando al frente en un espacio despejado.",
                        )

                        # Si obstacle_detector tiene una función de calibración o se activa aquí, lo llamamos
                        if self.obstacle_detector:
                            self.obstacle_detector.is_active = True
                            print("[MenuController] Obst activado por calibración.")

                        self.obstacle_detector.recalibrate_sensor()

                        # 2. Avisamos que terminó
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Calibración completada con éxito. Listo para caminar.",
                        )

                    elif best_match == "huecos":
                        print("[MenuController] Acción detectada: Huecos")
                        if self.obstacle_detector:
                            is_active = self.obstacle_detector.toggle_radar()
                            estado = "activada" if is_active else "desactivada"
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"Detección de huecos {estado}.",
                            )

                    elif best_match == "aereo":
                        print("[MenuController] Acción detectada: Aereo")
                        if self.depth_detector:
                            is_active = self.depth_detector.toggle_radar()
                            estado = "activada" if is_active else "desactivada"
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"Detección de obstáculos aéreos {estado}.",
                            )

                    break  # Command understood, exit the loop

                else:
                    print(
                        "[MenuController] Comando no reconocido, pidiendo repetición."
                    )
                    self.audio_queue.put(
                        self.audio_queue.VOICE_MENU,
                        "No te entendí. Vuelve a intentarlo presionando los dos botones.",
                    )
                    break  # Exit after one attempt to avoid infinite loop in case of unrecognized commands

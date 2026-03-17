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
    ):

        self.object_detector = object_detector
        self.obstacle_detector = obstacle_detector
        self.audio_queue = audio_queue
        self.ocr = ocr
        self.navigation = navigation

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
                    "cancela el viaje",
                    "listame mis ubicaciones",
                    "donde estoy",
                    "calibrar",
                ]

                # 1. Check for dynamic commands first by prefix
                if text_lower.startswith("llevame a"):
                    destino = text_lower.replace("llevame a", "").strip()
                    print(
                        f"[MenuController] Acción detectada: Llevame a tal lugar. Destino: {destino}"
                    )
                    break
                elif text_lower.startswith(
                    "guarda la ubicacion como"
                ) or text_lower.startswith("guarda la ubicación como"):
                    nombre = (
                        text_lower.replace("guarda la ubicacion como", "")
                        .replace("guarda la ubicación como", "")
                        .strip()
                    )
                    print(
                        f"[MenuController] Acción detectada: Guarda la ubicación como. Nombre: {nombre}"
                    )
                    break

                # 2. Check standard commands using difflib for fuzzy matching
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
                            "Número dos. Di Llévame a. seguido de un lugar para iniciar la navegación. "
                            "Número tres. Di Cancela el viaje. para detener tu navegación actual. "
                            "Número cuatro. Di Guarda la ubicación como. seguido de un nombre para guardar el lugar donde estás. "
                            "Número cinco. Di Lístame mis ubicaciones. para escuchar tus lugares guardados. "
                            "Número seis. Di Dónde estoy. para conocer tu posición actual en el mapa. "
                            "Número siete. Di Calibrar. para ajustar el sensor a tu postura y altura actual. "
                            "Para continuar. vuelve a presionar los botones y di un comando."
                        )

                        self.audio_queue.put(self.audio_queue.VOICE_MENU, menu_text)

                    elif best_match == "cancela el viaje":
                        print("[MenuController] Acción detectada: Cancela el viaje")
                    elif best_match == "listame mis ubicaciones":
                        print(
                            "[MenuController] Acción detectada: Listame mis ubicaciones"
                        )
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

                        self.obstacle_detector.recalibrate_sensor()

                        # 2. Avisamos que terminó
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Calibración completada con éxito. Listo para caminar.",
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

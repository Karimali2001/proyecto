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
        self.is_voice_active = False

        self.last_btn_2_press = 0.0
        self.btn_2_timer = None

        # Callbacks
        self.btn_1.when_pressed = self.handle_btn_1
        self.btn_2.when_pressed = self.handle_btn_2

    def handle_btn_1(self):
        # We add a small delay to allow for the possibility of the other button being pressed for a combined command
        if self.is_voice_active or (time.time() - self.last_both_pressed < 1.0):
            return
        time.sleep(0.05)

        # If button 2 is pressed, it is a voice command
        if self.btn_2.is_pressed:
            self.both_btns_pressed()
            return

        if time.time() - self.last_both_pressed < 0.5:
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
            self.audio_queue.put(self.audio_queue.OBJECT_DETECTION, "Camino Despejado")
        else:
            complete_phrase = ", ".join(self.object_detector.getLastDetection())
            self.audio_queue.put(self.audio_queue.OBJECT_DETECTION, complete_phrase)
        print("[Btn1] Single Click (Object Detection)")

    def _double_click_obj(self):
        """Double click action: Activates the free seat finder."""
        print("[Btn1] Double Click! Seat finder.")
        is_active = self.object_detector.toggle_seat_finder()
        state = "activado" if is_active else "desactivado"

        # Inform the user by voice
        self.audio_queue.put(
            self.audio_queue.VOICE_MENU, f"Buscador de asientos libres {state}"
        )

    def handle_btn_2(self):

        if self.is_voice_active or (time.time() - self.last_both_pressed < 1.0):
            return
        time.sleep(0.05)

        # If button 1 is pressed, it's a combined command
        if self.btn_1.is_pressed:
            self.both_btns_pressed()
            return

        if time.time() - self.last_both_pressed < 0.5:
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
                "Error de hardware.",
                "No encontré ningún texto en la imagen.",
                "Cámara no inicializada.",
                "No se pudo capturar la imagen.",
            ]:
                self.audio_queue.put(self.audio_queue.TEXT_RECOGNITION, detected_text)
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

    def _double_click_ocr(self):
        """Double Click Action: Activates or deactivates continuous Sign Mode."""
        print("[Btn2] Double Click! Toggling Continuous OCR Mode.")
        if self.ocr:
            is_active = self.ocr.toggle_continuous_mode()
            state = "activado" if is_active else "desactivado"
            self.audio_queue.put(
                self.audio_queue.VOICE_MENU,
                f"Modo lectura de letreros {state}.",
            )
        else:
            self.audio_queue.put(
                self.audio_queue.VOICE_MENU, "Lector de texto no inicializado."
            )

    def both_btns_pressed(self):

        # if we are already in voice menu, we ignore new activations until it's finished to avoid conflicts and overlapping commands
        if self.is_voice_active:
            return

        if self.audio_queue.is_priority_active_or_queued(self.audio_queue.VOICE_MENU):
            print(
                "[MenuController] Voice menu already active or queued, skipping new voice menu activation."
            )
            return

        current_time = time.time()

        if current_time - self.last_both_pressed > 0.5:
            self.is_voice_active = True
            self.last_both_pressed = current_time

            # Cancel any pending single click actions to avoid conflicts with the voice menu
            if getattr(self, "btn_1_timer", None) is not None:
                self.btn_1_timer.cancel()  # type: ignore
            if getattr(self, "btn_2_timer", None) is not None:
                self.btn_2_timer.cancel()  # type: ignore

            # Loop to allow retrying if the command is not understood
            while True:
                text_command = self.voice_interface.listen_and_recognize()

                print(f"[MenuController] Recognized text: '{text_command}'")

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
                    "quiero ir",
                    "cancelar ruta",
                    "guardar ubicación",
                    "botones",
                    "sonidos",
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
                            "Este es el menú de ayuda. Puedes decir los siguientes comandos. "
                            "Número uno. Di Menú. para listar qué puedo hacer por ti. "
                            "Número dos. Di Dónde estoy. para conocer tu posición actual en el mapa. "
                            "Número tres. Di Calibrar. para ajustar la brújula"
                            "Número cuatro. Di Huecos. para activar o desactivar la detección de huecos en el piso. "
                            "Número cinco. Di Aéreo. para activar o desactivar la detección de obstáculos aéreo. "
                            "Número seis. Di Botones. para aprender para qué sirve cada botón. "
                            "Número siete. Di Sonidos. para escuchar una demostración de las alarmas. "
                            "Para continuar. vuelve a presionar los botones y di un comando."
                            "Para continuar. vuelve a presionar los botones y di un comando."
                        )

                        self.audio_queue.put(self.audio_queue.VOICE_MENU, menu_text)

                    elif best_match == "donde estoy":
                        print("[MenuController] Action detected: Where am I")

                        location_message = self.navigation.get_where_am_i_message()

                        self.audio_queue.put(
                            self.audio_queue.NAVIGATION, location_message
                        )
                    elif best_match == "calibrar":
                        print("[MenuController] Action detected: Calibrate Compass")

                        # 1. Avisamos al usuario y le damos instrucciones
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Calibrando brújula. Por favor, da vueltas sobre tu propio eje lentamente hasta que te avise que terminó la calibración.",
                        )

                        # Esperamos a que la voz termine de hablar para empezar a medir
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        # 2. Iniciamos la recolección de datos en el IMU
                        if hasattr(self.navigation, "imu"):
                            self.navigation.imu.start_calibration()

                            # 3. Creamos un temporizador que detendrá la calibración en 15 segundos
                            # Esto se ejecuta en un hilo separado (no bloquea el programa)
                            def finish_imu_cal():
                                self.navigation.imu.finish_calibration()
                                self.audio_queue.put(
                                    self.audio_queue.VOICE_MENU,
                                    "Calibración de brújula exitosa",
                                )

                            threading.Timer(15.0, finish_imu_cal).start()
                        else:
                            print(
                                "[MenuController] Error: IMU no está conectado a Navigation"
                            )

                    elif best_match == "huecos":
                        print("[MenuController] Action detected: Holes")
                        if self.hole_detector:
                            is_active = self.hole_detector.toggle_radar()
                            state = "activada" if is_active else "desactivada"
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"Detección de huecos {state}.",
                            )

                    elif best_match == "aereo":
                        print("[MenuController] Action detected: Aerial")
                        if self.aerial_obstacle_detector:
                            is_active = self.aerial_obstacle_detector.toggle_radar()
                            state = "activada" if is_active else "desactivada"
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"Detección de obstáculos aéreos {state}.",
                            )

                    elif best_match == "guardar ubicación":
                        print("[MenuController] Action detected: Guardar ubicación")

                        # 1. We ask for the name
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "¿Con qué nombre quieres guardar este lugar?",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        raw_name = self.voice_interface.listen_and_recognize()

                        if not raw_name:
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                "No escuché ningún nombre. Operación cancelada.",
                            )
                            break

                        name = raw_name.lower().strip()
                        print(f"[MenuController] Heard name: '{name}'")

                        # 2. Security confirmation to save
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            f"¿Guardar ubicación actual como {name}? Responde sí o no.",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        confirmation = self.voice_interface.listen_and_recognize()

                        if confirmation and (
                            "sí" in confirmation.lower() or "si" in confirmation.lower()
                        ):
                            success, message = self.navigation.save_current_location(
                                name
                            )
                            self.audio_queue.put(self.audio_queue.VOICE_MENU, message)
                        else:
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU, "Guardado cancelado."
                            )
                    elif best_match == "quiero ir":
                        print(
                            "[MenuController] Action detected: Navegación (Quiero ir)"
                        )

                        # 1. We ask for the destination
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU, "¿A dónde quieres ir?"
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        # 2. We listen only for the name of the place
                        raw_destination = self.voice_interface.listen_and_recognize()

                        if not raw_destination:
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                "No escuché ningún destino. Operación cancelada.",
                            )
                            break

                        destination = raw_destination.lower().strip()
                        print(f"[MenuController] Heard destination: '{destination}'")

                        # 3. Intelligent autocomplete with Difflib (NEW)
                        # We search the list of keys (place names) of your JSON file
                        favorite_names = list(self.navigation.favorites.keys())
                        matches_destination = difflib.get_close_matches(
                            destination, favorite_names, n=1, cutoff=0.5
                        )

                        if matches_destination:
                            # It found the place, we calculate the route immediately without asking "Yes or No"
                            corrected_destination = matches_destination[0]
                            success, message = (
                                self.navigation.calculate_route_to_favorite(
                                    corrected_destination
                                )
                            )
                            self.audio_queue.put(self.audio_queue.NAVIGATION, message)
                        else:
                            # If it doesn't look like anything on the list, we warn
                            self.audio_queue.put(
                                self.audio_queue.VOICE_MENU,
                                f"No encontré {destination} en tu lista de destinos guardados.",
                            )

                    elif best_match == "cancelar ruta":
                        print("[MenuController] Action detected: Cancelar Navegación")
                        message = self.navigation.cancel_navigation()
                        self.audio_queue.put(self.audio_queue.VOICE_MENU, message)

                    elif best_match == "botones":
                        print(
                            "[MenuController] Action detected: Explicación de Botones"
                        )
                        explicacion_botones = (
                            "Este sistema se controla con dos botones principales. "
                            "Presionar el botón izquierdo una vez te dirá los obstáculos que tienes enfrente y la dirección con respecto a las agujas del reloj. "
                            "Presionarlo dos veces activará el buscador de asientos libres. "
                            "Presionar el botón derecho una vez leerá los textos o letreros que tengas frente a ti. "
                            "Presionarlo dos veces activará el modo de lectura continua, ideal para leer letreros mientras caminas. "
                            "Por último, mantener presionados ambos botones al mismo tiempo activará este menú de voz. "
                        )
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU, explicacion_botones
                        )

                    # === NUEVA SECCIÓN: DEMOSTRACIÓN DE SONIDOS ===
                    elif best_match == "sonidos":
                        print(
                            "[MenuController] Action detected: Demostración de Sonidos"
                        )

                        # Explicación Inicial
                        intro_sonidos = (
                            "A continuación escucharás una demostración de los sonidos del sistema. "
                            "Presta atención al tono y de qué lado provienen."
                        )
                        self.audio_queue.put(self.audio_queue.VOICE_MENU, intro_sonidos)
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        # Demo: Huecos
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "El siguiente sonido indica un hueco o escalón hacia abajo en el suelo.",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "center",
                                "sound_type": "hole",
                            },
                        )
                        time.sleep(1.5)  # Pausa dramática para escuchar el sonido

                        # Demo: Aéreo
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Este sonido te avisa de un obstáculo aéreo a la altura de tu cabeza o pecho.",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "center",
                                "sound_type": "aerial",
                            },
                        )
                        time.sleep(1.5)

                        # Demo: Buscador de Asientos / Sonares
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Cuando actives el buscador de asientos. "
                            "Si escuchas el pitido solo por tu audífono izquierdo, significa que la silla está a tu izquierda.",
                        )

                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)
                        # Sonar Izquierdo
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "left",
                                "sound_type": "sonar",
                            },
                        )
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "left",
                                "sound_type": "sonar",
                            },
                        )
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "left",
                                "sound_type": "sonar",
                            },
                        )

                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Si el pitido suena solo por la derecha, la silla está a tu derecha.",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        # Sonar Derecho
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "right",
                                "sound_type": "sonar",
                            },
                        )
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "right",
                                "sound_type": "sonar",
                            },
                        )
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "right",
                                "sound_type": "sonar",
                            },
                        )

                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Y si el pitido suena en el centro, en ambos oídos al mismo tiempo, significa que vas por buen camino y la silla está justo frente a ti. "
                            "El pitido se hará más rápido a medida que te acerques.",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        # Sonar Centro (Simulando acercamiento con dos pitidos rápidos)
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "center",
                                "sound_type": "sonar",
                            },
                        )
                        time.sleep(0.5)
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            {
                                "action": "sound",
                                "position": "center",
                                "sound_type": "sonar",
                            },
                        )
                        time.sleep(1.5)

                        # Demo: Vehículos
                        self.audio_queue.put(
                            self.audio_queue.VOICE_MENU,
                            "Finalmente, si te acercas a un vehículo, te avisaré rapidamente de la siguiente manera:",
                        )
                        self.audio_queue.wait_for_priority(self.audio_queue.VOICE_MENU)

                        self.audio_queue.play_concurrent(
                            {
                                "action": "fast_voice",
                                "text": "Carro",
                            }
                        )

                    break  # Command understood, exit the loop

                else:
                    print("[MenuController] Command not recognized, asking to repeat.")
                    self.audio_queue.put(
                        self.audio_queue.VOICE_MENU,
                        "No te entendí. Vuelve a intentarlo presionando los dos botones.",
                    )
                    break  # Exit after one attempt to avoid infinite loop in case of unrecognized commands
            self.last_both_pressed = time.time()
            self.is_voice_active = False

import time

from src.core.state import State
from src.drivers.audio_output_driver import AudioOutputDriver
from src.drivers.raspberry_driver import RaspberryDriver
from src.core.init_state import InitState


class OverheatState(State):
    def __init__(self):

        self.audio_driver = AudioOutputDriver()
        self.rpi_driver = RaspberryDriver()
        self.alert_sent = False

    def close_drivers(self):

        if self.context.camera_driver is not None:
            self.context.camera_driver.stop()

    def process(self) -> None:

        if not self.alert_sent:
            print("[OVERHEAT] Iniciando protocolo de enfriamiento...")

            self.audio_driver.speak(
                "Sistema muy caliente, empezando proceso de enfriamento"
            )
            self.close_drivers()
            self.alert_sent = True
            time.sleep(2)
            return

        temperature = self.rpi_driver.get_cpu_temperature()
        print(f"[OverheatState] Current Temp: {temperature}")

        if temperature is not None and temperature < 47:
            self.audio_driver.speak(
                "El proceso de enfriamiento ha finalizado, puede continuar usando el sistema"
            )
            self.context.transition_to(InitState())
        else:
            time.sleep(1)

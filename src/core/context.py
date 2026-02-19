from typing import Optional, Any
from .state import State
from threading import Thread
import time

from src.drivers.raspberry_driver import RaspberryDriver
from src.core.overheat_state import OverheatState


class Context:
    """
    The Context defines the interface of interest to clients. It also maintains
    a reference to an instance of a State subclass.
    """

    _state: State

    # Update these types to your actual classes if possible, or use Any/Optional
    camera_driver: Optional[Any] = None
    hailo_driver: Optional[Any] = None
    audio_output_driver: Optional[Any] = None

    def __init__(self, state: State) -> None:

        self.raspberry = RaspberryDriver()

        self.cpu_temperature_thread = Thread(
            target=self._check_cpu_temperature, daemon=True
        )
        self.cpu_temperature_thread.start()

        self.transition_to(state)

    def _check_cpu_temperature(self):

        while True:
            temperature = self.raspberry.get_cpu_temperature()

            print(f"[Context] CPU Temperature: {temperature}°C")

            if temperature is not None and temperature > 49:
                if not isinstance(self._state, OverheatState):
                    print("Context: Overheating detected! Switching state.")
                    self.transition_to(OverheatState())

            time.sleep(10)

    def transition_to(self, state: State):
        print(f"Context: Transition to {type(state).__name__}")

        if hasattr(self, "_state") and self._state is not None:
            # Avoid stopping if we are mistakenly transitioning to the same state class
            if type(self._state) == type(state):
                return
            # Verificamos si tiene el método stop (todos tus estados deberían tenerlo, aunque sea vacío)
            if hasattr(self._state, "stop"):
                print(f"Context: Stopping {type(self._state).__name__}...")
                self._state.stop()

        self._state = state
        self._state.context = self

    def run(self):
        self._state.process()

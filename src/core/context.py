from typing import Optional, Any
from .state import State

class Context:
    """
    The Context defines the interface of interest to clients. It also maintains
    a reference to an instance of a State subclass.
    """

    _state: State
    
    # Update these types to your actual classes if possible, or use Any/Optional
    camera_driver: Optional[Any] = None
    hailo_driver: Optional[Any] = None

    def __init__(self, state: State) -> None:
        self.transition_to(state)

    def transition_to(self, state: State):
        print(f"Context: Transition to {type(state).__name__}")
        self._state = state
        self._state.context = self

    def run(self):
        self._state.process()

from .state import State

class ErrorState(State):
    
    def process(self) -> None:
        print("[Error] Registrando error en logs...")
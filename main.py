import time
from src.core.context import Context
from src.core.init import InitState

if __name__ == "__main__":
    # Arrancamos en estado INIT
    context = Context(InitState())

    # Bucle principal de la aplicación
    try:
        while True:
            context.run()
            time.sleep(1) # Simula el ciclo de reloj
    except KeyboardInterrupt:
        # # Forzar transición a shutdown si se cancela manualmente (Ctrl+C)
        # from src.core.shutdown import ShutdownState
        # context.transition_to(ShutdownState())
        context.run()
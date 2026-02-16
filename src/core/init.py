from .state import State

from src.drivers.camera_driver import CameraDriver


class InitState(State):
    def process(self) -> None:
        from .run_tracking import RunTracking

        print("[INIT] Inicializando recursos...")

        # Inicializar y guardar en el contexto
        self.context.camera = CameraDriver()
        # self.context.yolo_model = YOLOModel() # Descomentar cuando tengas el modelo

        print("[INIT] Todo listo. Cambiando a Tracking.")
        self.context.transition_to(RunTracking())

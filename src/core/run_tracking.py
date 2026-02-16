import cv2
import time
from picamera2 import MappedArray
import threading


from .state import State
from .error import ErrorState

class RunTracking(State):
    
    def __init__(self):
        # Variable para compartir las detecciones entre el proceso principal y el callback de dibujo
        self.current_detections = []
        self.lock = threading.Lock()
        
        self.running = False
        self.thread = None
        
    def draw_detections_callback(self, request):
        """Esta función es llamada automáticamente por Picamera2 antes de mostrar cada frame."""
        if self.current_detections:
            with MappedArray(request, "main") as m:
                for class_name, bbox, score in self.current_detections:
                    x0, y0, x1, y1 = bbox
                    label = f"{class_name} {int(score * 100)}%"
                    
                    # Dibujar rectángulo
                    cv2.rectangle(m.array, (x0, y0), (x1, y1), (0, 255, 0), 2)
                    
                    # Dibujar texto con fondo para mejor legibilidad
                    (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(m.array, (x0, y0 - 20), (x0 + w, y0), (0, 255, 0), -1)
                    cv2.putText(m.array, label, (x0, y0 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
                    
    def _run_inference_loop(self):
        
        driver_cam = self.context.camera_driver
        driver_ai = self.context.hailo_driver
       
        while self.running:
           try:
            
             # 1. Capturar frame de baja resolución para IA
            frame = driver_cam.capture_array("lores")
            
            if frame is None:
                continue
            
            # 2. Inferencia (Lo pesado)
            raw_detections = driver_ai.infer(frame)
            
            
            
            # 3. Procesar resultados
            video_w, video_h = self.context.camera_driver.video_size 
             
            clean_detections = driver_ai.extract_detections(raw_detections, video_w, video_h)
            
            with self.lock:
                # 4. ACTUALIZAR VARIABLE COMPARTIDA
                # Esto es lo que lee la función 'draw_detections_callback'
                self.current_detections = clean_detections
                
            if clean_detections:
                # Solo imprimimos nombres para no saturar la consola
                print(f"[TRACKING] Viendo: {[d[0] for d in clean_detections]}")
                
                time.sleep(0.01)
                
           except Exception as e:
                print(f"[ERROR] Hilo de inferencia falló: {e}")
                self.running = False
                
    def stop(self) -> None:
        """Llamar a esto al salir del estado para limpiar"""
        
        self.running = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        print("[TRACKING] Hilo detenido.")
               
        
    def process(self) -> None:
        """Método principal del estado (Hilo Principal)."""
        
        driver_cam = self.context.camera_driver

        if driver_cam is None or self.context.hailo_driver is None:
            print("[Error] Drivers no inicializados en RunTracking")
            self.context.transition_to(ErrorState())
            return
        
        
        if driver_cam.picam2.pre_callback is None:
             print("[TRACKING] Activando visualización en cámara...")
             driver_cam.set_callback(self.draw_detections_callback)

        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_inference_loop(), daemon=True)
            self.thread.start()
        try:
            while self.running:
                time.sleep(0.01)
        except KeyboardInterrupt:
            self.stop()
            

            
    
            
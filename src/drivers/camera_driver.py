
# docs: https://pip-assets.raspberrypi.com/categories/652-raspberry-pi-camera-module-2/documents/RP-008156-DS-2-picamera2-manual.pdf?disposition=inline


from picamera2 import Picamera2

class CameraDriver:
    
    def __init__(self):
        self.picam2 = Picamera2()
        camera_config = self.picam2.create_preview_configuration()
        self.picam2.configure(camera_config)

    

    def start(self):
    
        try:
            self.picam2.start()
        except Exception as e:
            print(f"Error al iniciar la cámara: {e}")

    def stop(self):
        try:
            self.picam2.stop()
        except Exception as e:
            print(f"Error al detener la cámara: {e}")

    def capture(self):
        try:
            self.picam2.capture_file("image.jpg")
        except Exception as e:
            print(f"Error al capturar la imagen: {e}")
            





    
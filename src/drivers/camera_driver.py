from picamera2 import Picamera2, Preview

class CameraDriver:
    def __init__(self):
        self.picam2 = Picamera2()
        self.video_size = (1280, 960) # Default video size
        self.model_size = (640, 640)  # Default, gets overwritten

    def configure(self, video_w, video_h, model_w, model_h):
        self.video_size = (video_w, video_h)
        self.model_size = (model_w, model_h)

        main = {'size': self.video_size, 'format': 'XRGB8888'}
        lores = {'size': self.model_size, 'format': 'RGB888'}
        controls = {'FrameRate': 30}
        
        config = self.picam2.create_preview_configuration(main, lores=lores, controls=controls)
        self.picam2.configure(config)

    def start(self, preview=True):
        try:
            if preview:
                # Be careful with Preview.QTGL in headless environments
                self.picam2.start_preview(Preview.QTGL, x=0, y=0, width=self.video_size[0], height=self.video_size[1])
            
            self.picam2.start()
            print("Camera started.")
        except Exception as e:
            print(f"Error starting camera: {e}")

    def stop(self):
        try:
            self.picam2.stop()
        except Exception as e:
            print(f"Error stopping camera: {e}")

    def capture_array(self, stream_name='lores'):
        return self.picam2.capture_array(stream_name)

    def set_callback(self, callback_func):
        """Sets the callback for drawing/processing on the main thread loop (preview)"""
        self.picam2.pre_callback = callback_func
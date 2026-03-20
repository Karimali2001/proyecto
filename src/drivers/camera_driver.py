from picamera2 import Picamera2
from libcamera import controls, Transform  # type: ignore


class CameraDriver:
    def __init__(self, camera_num=0, enable_af=False):
        """
        camera_num: Index of the camera to use (default is 0).
        enable_af: Boolean to enable autofocus (default is False).
        """

        self.picam2 = Picamera2(camera_num=camera_num)
        self.enable_af = enable_af
        self.camera_num = camera_num

        self.video_size = (1280, 960)  # Default video size
        self.model_size = (640, 640)  # Default, gets overwritten

    def configure(self, video_w, video_h, model_w, model_h):
        self.video_size = (video_w, video_h)
        self.model_size = (model_w, model_h)

        main = {"size": self.video_size, "format": "XRGB8888"}
        lores = {"size": self.model_size, "format": "RGB888"}

        cam_controls = {"FrameRate": 30}

        if self.enable_af:
            # Set autofocus mode to Auto (AfMode 0) in the configuration if autofocus is enabled
            cam_controls["AfMode"] = controls.AfModeEnum.Auto

        if self.camera_num == 1:
            # For 64mp camera, we need to flip the image due to the physical orientation of the sensor
            cam_transform = Transform(hflip=True, vflip=True)
        else:
            cam_transform = Transform()

        config = self.picam2.create_preview_configuration(
            main, lores=lores, controls=cam_controls, transform=cam_transform
        )

        self.picam2.configure(config)
        self.picam2.configure(config)

    def start(self, preview=True):
        try:
            self.picam2.start()

            print("Camera started.")

        except Exception as e:
            print(f"Error starting camera: {e}")

    def stop(self):
        try:
            self.picam2.stop()
            self.picam2.stop_preview()  # Cierra la ventana QT
            print("CameraDriver: Camera stopped.", flush=True)
        except Exception as e:
            print(f"Error stopping camera: {e}")

    def capture_array(self, stream_name="lores"):
        return self.picam2.capture_array(stream_name)

    def set_callback(self, callback_func):
        """Sets the callback for drawing/processing on the main thread loop (preview)"""
        self.picam2.pre_callback = callback_func

    def trigger_autofocus(self, roi_relativo=None):
        """
        Triggers the autofocus cycle.
        roi_relativo: Tupla (x, y, width, height) en porcentajes de 0.0 a 1.0
        """
        if self.enable_af:
            print("--> Triggering autofocus cycle...")
            try:
                if roi_relativo is not None:
                    # 1. Obtenemos las coordenadas reales del sensor físico
                    meta = self.picam2.capture_metadata()
                    if "ScalerCrop" in meta:
                        cx, cy, cw, ch = meta["ScalerCrop"]
                        rx, ry, rw, rh = roi_relativo

                        # 2. Mapeamos el porcentaje de la IA a los píxeles físicos del lente
                        win_x = int(cx + (rx * cw))
                        win_y = int(cy + (ry * ch))
                        win_w = int(rw * cw)
                        win_h = int(rh * ch)

                        # 3. Le damos la orden al hardware de la cámara
                        self.picam2.set_controls(
                            {
                                "AfMetering": controls.AfMeteringEnum.Windows,
                                "AfWindows": [(win_x, win_y, win_w, win_h)],
                            }
                        )
                        print(f"--> 🎯 IA forzando enfoque en zona de texto...")
                else:
                    # Si no hay coordenadas, vuelve al autoenfoque normal en el centro
                    self.picam2.set_controls(
                        {"AfMetering": controls.AfMeteringEnum.Auto}
                    )

                success = self.picam2.autofocus_cycle()
                if success:
                    print("--> Perfect focus achieved!")
                else:
                    print("--> Warning: The lens did not achieve perfect focus.")
            except Exception as e:
                print(f"Error triggering autofocus: {e}")

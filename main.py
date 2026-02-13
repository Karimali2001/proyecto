import time


from src.drivers.camera_driver import CameraDriver


camera = CameraDriver()
camera.start()
time.sleep(2)
camera.capture()
camera.stop()

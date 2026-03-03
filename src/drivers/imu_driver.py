import board
import adafruit_bno055
import time


class ImuDriver:
    def __init__(self):
        # Configuration of the I2C bus (Blinka automatically detects the Pi's pins)
        i2c = board.I2C()
        self.sensor = adafruit_bno055.BNO055_I2C(i2c)

    def getData(self):
        """
        Returns data from IMU sensor as a tuple: (heading, roll, pitch)
        heading is the compass direction (0-360°),
        roll is the tilt to the left or right
        pitch is the tilt forward or backward
        """
        return self.sensor.euler


while True:
    imu = ImuDriver()
    heading, roll, pitch = imu.getData()

    print(f"Compass: {heading:.2f}° | Pitch: {pitch:.2f}° | Roll: {roll:.2f}°")

    time.sleep(0.1)

import board
import adafruit_bno055
import time


class ImuDriver:
    def __init__(self):
        # Configuration of the I2C bus (Blinka automatically detects the Pi's pins)
        i2c = board.I2C()
        self.sensor = adafruit_bno055.BNO055_I2C(i2c)

        self.pitch_offset = 0.0
        self.roll_offset = 0.0

    def initial_calibration(self):

        print("[IMU] Starting Calibration...")

        for _ in range(5):
            euler = self.getData()

            if euler is not None:
                compass, pitch, roll = euler

                self.pitch_offset = pitch
                self.roll_offset = roll

                time.sleep(0.5)

        print("[IMU] Calibration Finished...")

    def getData(self):
        """
        Returns data from IMU sensor as a tuple: (heading, roll, pitch)
        heading is the compass direction (0-360°),
        roll is the tilt to the left or right
        pitch is the tilt forward or backward
        """
        euler = self.sensor.euler

        if euler[0] is None:
            return (0.0, 0.0, 0.0)

        compass, pitch, roll = euler

        adjusted_pitch = pitch - self.pitch_offset
        adjusted_roll = roll - self.roll_offset

        return compass, adjusted_pitch, adjusted_roll


if __name__ == "__main__":
    imu = ImuDriver()
    time.sleep(1)  # Wait a moment for the sensor to initialize

    imu.initial_calibration()

    while True:
        compass, pitch, roll = imu.getData()

        if pitch != 0.0 and roll != 0.0:
            print(
                f"Compass: {compass:6.2f}° | Pitch: {pitch:6.2f}° | Roll: {roll:6.2f}°",
                end="\r",
            )

        time.sleep(0.1)

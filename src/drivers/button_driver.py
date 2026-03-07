from gpiozero import Button


class ButtonDriver:
    def __init__(self, gpio_pin):

        # pull_up is 3.3V by default
        self.button = Button(pin=gpio_pin, pull_up=True)

    def is_pressed(self):
        """
        Returns True if the button is currently pressed, False otherwise.
        """
        return self.button.is_pressed  # type: ignore


if __name__ == "__main__":
    import time

    # Example GPIO pin
    driver = ButtonDriver(27)

    try:
        while True:
            if driver.is_pressed():
                print("Button pressed!")
                # Debounce: wait until released
                while driver.is_pressed():
                    time.sleep(0.05)
                print("Button released!")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting.")

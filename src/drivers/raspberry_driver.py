

TEMPERATURE_PATH = "/sys/class/thermal/thermal_zone0/temp"


class RaspberryDriver:
    
    def __init__(self):
        pass
        
    
    def get_cpu_temperature(self):
        """Returns the CPU temperature in Celsius."""
        try:
            with open(TEMPERATURE_PATH, "r") as f:
                temp_str = f.read()
            return float(temp_str) / 1000.0
        except Exception as e:
            print(f"Error reading CPU temperature: {e}")
            return None
        
        
        
        

if __name__ == "__main__":
    
    driver = RaspberryDriver()
    temp = driver.get_cpu_temperature()
    print(f"CPU Temperature: {temp} °C")
import time
import threading
import requests

from src.drivers.gps_driver import GPS
from src.drivers.imu_driver import ImuDriver


class Navigation:
    def __init__(self):

        try:
            self.gps = GPS()
            self.imu = ImuDriver()

        except Exception as e:
            print(f"Error initializing GPS or IMU: {e}")

        self.latitude = 0.0
        self.longitude = 0.0
        self.compass = 0.0

        self.last_fix_time = None

    def thread_update_location(self):
        """Continuously updates the current location and compass heading."""

        while True:
            location = self.gps.get_location()

            if location:
                lat, lon, _, _ = location

                if (
                    lat != 0.0
                    and lon != 0.0
                    and (self.latitude != lat or self.longitude != lon)
                ):
                    self.last_fix_time = time.time()
                    self.latitude = lat
                    self.longitude = lon

            compass, pitch, roll = self.imu.getData()
            if compass is not None:
                self.compass = compass
            time.sleep(3)  # Update every 3 seconds

    def get_address_from_coordinates(self, lat, lon):
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&namedetails=1&extratags=1"
            headers = {"User-Agent": "KarimAsistenteNavegacion/1.0"}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})
                namedetails = data.get("namedetails", {})

                # 1. Buscar local, tienda, oficina o edificio
                local = address.get(
                    "shop",
                    address.get(
                        "office",
                        address.get(
                            "amenity",
                            address.get("building", address.get("leisure", "")),
                        ),
                    ),
                )

                # 2. Buscar marcas o nombres de centros comerciales ocultos en los detalles
                centro_comercial = namedetails.get("addr:housename", "")
                marca = namedetails.get("brand", "")

                # 3. Buscar "Lugares" grandes
                lugar_macro = address.get("place", address.get("housenumber", ""))

                # 4. Extraer calle, sector y CIUDAD
                calle = address.get("road", "una calle sin nombre")
                sector = address.get(
                    "suburb",
                    address.get("neighbourhood", address.get("residential", "")),
                )

                # Extraemos la ciudad (Por defecto Puerto Ordaz si falla)
                ciudad_cruda = address.get("city", address.get("town", "Puerto Ordaz"))

                # --- ARMAMOS EL MENSAJE COMO UN ROMPECABEZAS ---
                mensaje = ""

                # Caso A: Estamos dentro de una tienda o local específico
                if local:
                    mensaje += f"justo en {local}"
                    if marca and marca.lower() not in local.lower():
                        mensaje += f" de {marca}"
                    if centro_comercial:
                        mensaje += f", dentro de {centro_comercial}"
                    mensaje += f", sobre la {calle}"

                # Caso B: No hay local, pero estamos en un lugar macro (como la UCAB)
                elif lugar_macro and not lugar_macro.isdigit():
                    mensaje += f"en la zona de {lugar_macro}, sobre la {calle}"

                # Caso C: Solo estamos en una calle normal
                else:
                    mensaje += f"en la {calle}"

                # Añadimos el sector
                if sector:
                    mensaje += f", sector {sector}"

                # Añadimos y limpiamos la ciudad al final
                if ciudad_cruda:
                    # Si el mapa manda "Ciudad Guayana (Puerto Ordaz)", extraemos solo "Puerto Ordaz"
                    if "(" in ciudad_cruda:
                        ciudad_limpia = (
                            ciudad_cruda.split("(")[-1].replace(")", "").strip()
                        )
                    else:
                        ciudad_limpia = ciudad_cruda

                    mensaje += f", {ciudad_limpia}"

                return mensaje
            else:
                return "una ubicación desconocida"

        except requests.exceptions.RequestException:
            return "una ubicación desconocida por falta de conexión"

    def get_where_am_i_message(self):
        """
        Generates a user-friendly message about the current location based on GPS data.
        Handles different scenarios of GPS signal availability and freshness.
        """
        # Case 1: Just powered on and never got a signal
        if (
            self.latitude is None
            or self.longitude is None
            or self.last_fix_time is None
        ):
            return "Aún estoy buscando señal de los satélites. Por favor, asegúrate de estar a cielo abierto."

        # Calculate how much time has passed since the last valid location fix
        transcurred_time = time.time() - self.last_fix_time

        # Transform la lat/lon in text (your Nominatim function)
        direction = self.get_address_from_coordinates(self.latitude, self.longitude)

        # Case 2: We have a fresh signal (less than 20 seconds)
        if transcurred_time < 20:
            return f"Actualmente estás en {direction}"

        # Case 3: We lost the signal recently (e.g., entered a roof, minutes passed)
        else:
            minutes = int(transcurred_time // 60)
            if minutes == 0:
                return f"Perdí la señal del GPS hace unos segundos. Tu última ubicación conocida fue en {direction}"
            else:
                return f"No tengo señal actual. Hace {minutes} minutos estabas cerca de {direction}"

    def start_navigation(self, target_lat, target_lon, target_name="tu destino"):
        pass

    def cancel_navigation(self):
        pass

    def save_current_location(self, name):
        pass

    def list_saved_locations(self):
        pass

    def delete_saved_location(self, name):
        pass


if __name__ == "__main__":
    navigation = Navigation()

    # Start the location update thread
    t_location = threading.Thread(target=navigation.thread_update_location, daemon=True)
    t_location.start()

    time.sleep(20)

    # Keep the main thread alive to allow the location update thread to run
    try:
        while True:
            print(navigation.get_where_am_i_message())
            time.sleep(5)
    except KeyboardInterrupt:
        print("Exiting...")

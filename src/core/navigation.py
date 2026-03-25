import time
import threading
import requests
from dotenv import load_dotenv
from pathlib import Path
import os
import json
import math

from src.drivers.gps_driver import GPS
from src.drivers.imu_driver import IMU

load_dotenv()

ORS_API_KEY = os.getenv("ORS_API_KEY")
GOOGLE_DIRECTIONS_API_KEY = os.getenv("GOOGLE_DIRECTIONS_API_KEY")


class Navigation:
    def __init__(self, audio_queue):
        self.audio_queue = audio_queue

        try:
            self.gps = GPS()
            self.imu = IMU()
        except Exception as e:
            print(f"Error initializing GPS or IMU: {e}")

        self.latitude = 0.0
        self.longitude = 0.0

        # Now we ONLY use this variable fed by the physical compass
        self.compass = 0.0

        self.last_fix_time = None
        self.is_navigating = False
        self.is_imu_active = False
        self.waypoints = []
        self.current_destination = ""
        self.nav_thread = None
        self.imu_thread = None

        self.favorites = {}  # name -> (lat, lon)
        self._load_favorites()

    def thread_update_imu(self):
        """Updates the IMU compass heading in real time"""
        print("[Navigation] IMU thread started. Listening in real time...")
        while True:
            if hasattr(self, "imu"):
                self.compass = self.imu.get_heading()
            time.sleep(0.05)

    def thread_update_location(self):
        """Updates the GPS location in real time (without guessing headings)."""
        print("[Navigation] GPS thread started. Listening in real time...")

        while True:
            location = self.gps.get_location()

            if location:
                lat, lon = location

                if lat != 0.0 and lon != 0.0:
                    self.last_fix_time = time.time()

                    if self.latitude != lat or self.longitude != lon:
                        self.latitude = lat
                        self.longitude = lon

            time.sleep(0.01)

    def get_address_from_coordinates(self, lat, lon):
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&namedetails=1&extratags=1"
            headers = {"User-Agent": "KarimAsistenteNavegacion/1.0"}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})
                namedetails = data.get("namedetails", {})

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
                shopping_center = namedetails.get("addr:housename", "")
                brand = namedetails.get("brand", "")
                macro_place = address.get("place", address.get("housenumber", ""))
                street = address.get("road", "una calle sin nombre")
                sector = address.get(
                    "suburb",
                    address.get("neighbourhood", address.get("residential", "")),
                )
                raw_city = address.get("city", address.get("town", "Puerto Ordaz"))

                message = ""
                if local:
                    message += f"justo en {local}"
                    if brand and brand.lower() not in local.lower():
                        message += f" de {brand}"
                    if shopping_center:
                        message += f", dentro de {shopping_center}"
                    message += f", sobre la {street}"
                elif macro_place and not macro_place.isdigit():
                    message += f"en la zona de {macro_place}, sobre la {street}"
                else:
                    message += f"en la {street}"

                if sector:
                    message += f", sector {sector}"

                if raw_city:
                    if "(" in raw_city:
                        clean_city = raw_city.split("(")[-1].replace(")", "").strip()
                    else:
                        clean_city = raw_city
                    message += f", {clean_city}"

                return message
            else:
                return "una ubicación desconocida"
        except requests.exceptions.RequestException:
            return "una ubicación desconocida por falta de conexión"

    def get_where_am_i_message(self):
        if (
            self.latitude is None
            or self.longitude is None
            or self.last_fix_time is None
        ):
            return "Aún estoy buscando señal de los satélites. Por favor, asegúrate de no estar en un lugar cerrado."

        elapsed_time = time.time() - self.last_fix_time
        direction = self.get_address_from_coordinates(self.latitude, self.longitude)

        # Get cardinal direction from IMU
        cardinal = "una dirección desconocida"
        if hasattr(self, "imu"):
            heading = self.imu.get_heading()
            if heading >= 315 or heading < 45:
                cardinal = "el norte"
            elif 45 <= heading < 135:
                cardinal = "el este"
            elif 135 <= heading < 225:
                cardinal = "el sur"
            elif 225 <= heading < 315:
                cardinal = "el oeste"

        if elapsed_time < 20:
            return f"Actualmente estás en {direction}, mirando hacia {cardinal}"
        else:
            minutes = int(elapsed_time // 60)
            if minutes == 0:
                return f"Perdí la señal del GPS hace unos segundos. Tu última ubicación conocida fue en {direction}, mirando hacia {cardinal}"
            else:
                return f"No tengo señal actual. Hace {minutes} minutos estabas cerca de {direction}"

    def _load_favorites(self):
        fav_path = Path.cwd() / "assets" / "ubication_favorites.json"
        try:
            if fav_path.exists():
                with open(fav_path, "r", encoding="utf-8") as f:
                    self.favorites = json.load(f)
                print(f"[Navigation] {len(self.favorites)} favorites loaded.")
            else:
                print("[Navigation] favorites.json file not found.")
        except Exception as e:
            print(f"[Navigation] Error loading favorites: {e}")

    def _decode_polyline(self, polyline_str):
        index, lat, lng = 0, 0, 0
        coordinates = []
        changes = {"latitude": 0, "longitude": 0}

        while index < len(polyline_str):
            for unit in ["latitude", "longitude"]:
                shift, result = 0, 0
                while True:
                    byte = ord(polyline_str[index]) - 63
                    index += 1
                    result |= (byte & 0x1F) << shift
                    shift += 5
                    if not byte >= 0x20:
                        break
                if result & 1:
                    changes[unit] = ~(result >> 1)
                else:
                    changes[unit] = result >> 1

            lat += changes["latitude"]
            lng += changes["longitude"]
            coordinates.append([lat / 100000.0, lng / 100000.0])

        return coordinates

    def calculate_route_to_favorite(self, place_name):
        place_key = place_name.lower().strip()

        if place_key not in self.favorites:
            return False, f"No encontré {place_name} en tu lista de destinos guardados."

        target = self.favorites[place_key]
        target_lat = target["lat"]
        target_lon = target["lon"]

        if not self.last_fix_time or (time.time() - self.last_fix_time > 15):
            return (
                False,
                "No tengo señal GPS actual para calcular la ruta. Sal a un lugar despejado.",
            )

        direct_distance = self._haversine(
            self.latitude, self.longitude, target_lat, target_lon
        )

        # Adjusted threshold to 15 meters
        if direct_distance < 15.0:
            print(
                f"[Navigation] Destination at {direct_distance:.1f}m. Canceling due to proximity."
            )
            return True, f"Ya te encuentras en {place_name}. Has llegado a tu destino."

        print(f"[Navigation] Requesting Google Maps route to {place_name}...")

        url = f"https://maps.googleapis.com/maps/api/directions/json?origin={self.latitude},{self.longitude}&destination={target_lat},{target_lon}&mode=walking&key={GOOGLE_DIRECTIONS_API_KEY}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()

                if data.get("status") == "OK":
                    polyline_str = data["routes"][0]["overview_polyline"]["points"]
                    self.waypoints = self._decode_polyline(polyline_str)

                    if len(self.waypoints) > 1:
                        self.waypoints.pop(0)

                    self.current_destination = place_name
                    self.is_navigating = True

                    self.is_imu_active = True
                    if hasattr(self, "imu"):
                        self.imu.last_time = time.time()  # type: ignore

                    if self.imu_thread is None or not self.imu_thread.is_alive():
                        self.imu_thread = threading.Thread(
                            target=self._thread_update_imu, daemon=True
                        )
                        self.imu_thread.start()

                    if self.nav_thread is None or not self.nav_thread.is_alive():
                        self.nav_thread = threading.Thread(
                            target=self._navigation_loop, daemon=True
                        )
                        self.nav_thread.start()

                    return (
                        True,
                        f"Ruta calculada hacia {place_name}. Comienza a caminar.",
                    )
                else:
                    error_msg = data.get("status", "Unknown Error")
                    print(f"[Navigation] Google Maps Error: {error_msg}")
                    return (
                        False,
                        "Google Maps no pudo encontrar una ruta peatonal válida.",
                    )
            else:
                return False, "Hubo un error al comunicarse con el servidor de mapas."

        except Exception as e:
            print(f"[Navigation] Error calculating route: {e}")
            return False, "Error de conexión al calcular la ruta."

    def _navigation_loop(self):
        time.sleep(1)
        print("[Navigation] Phase 4 started. Guiding the user.")

        log_file_path = Path.cwd() / "navigation_log.txt"

        def write_log(message):
            print(message)
            try:
                with open(log_file_path, "a", encoding="utf-8") as f:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {message}\n")
            except Exception:
                pass

        write_log(
            f"\n--- STARTING NAVIGATION TOWARDS: {self.current_destination.upper()} ---"
        )

        last_instruction = ""
        last_instruction_time = 0

        while self.is_navigating and len(self.waypoints) > 0:
            current_lat = self.latitude
            current_lon = self.longitude
            current_time = time.time()

            target_lat = self.waypoints[0][0]
            target_lon = self.waypoints[0][1]

            final_lat = self.waypoints[-1][0]
            final_lon = self.waypoints[-1][1]

            # 1. SMART ARRIVAL (15 meters tolerance)
            dist_to_final = self._haversine(
                current_lat, current_lon, final_lat, final_lon
            )
            if dist_to_final < 30.0:
                write_log(
                    f"Smart arrival: {dist_to_final:.1f}m from final destination."
                )
                self.waypoints = []
                break

            # 2. Proximity Check to Corner
            distance_to_wp = self._haversine(
                current_lat, current_lon, target_lat, target_lon
            )
            if distance_to_wp < 12.0:
                write_log(
                    f"Corner passed (Dist: {distance_to_wp:.1f}m). {len(self.waypoints) - 1} points remaining."
                )
                self.waypoints.pop(0)
                last_instruction = ""
                continue

            # 3. Headings (Using ONLY the IMU)
            ideal_bearing = self._calculate_bearing(
                current_lat, current_lon, target_lat, target_lon
            )
            current_heading = self.compass

            # 4. Error Calculation
            error = (ideal_bearing - current_heading + 540) % 360 - 180
            abs_error = abs(error)
            instruction = ""

            if abs_error <= 20:
                instruction = "sigue derecho"
            elif 20 < error <= 50:
                instruction = "gira levemente a la derecha"
            elif error > 50:
                instruction = "gira a la derecha"
            elif -50 <= error < -20:
                instruction = "gira levemente a la izquierda"
            elif error < -50:
                instruction = "gira a la izquierda"

            # 5. Anti-Spam Control (45 seconds of silence)
            should_speak = False

            if instruction != last_instruction:
                should_speak = True
            else:
                wait_time = 45
                if current_time - last_instruction_time > wait_time:
                    should_speak = True

            if should_speak and self.audio_queue:
                message = f"{instruction}."
                self.audio_queue.put(self.audio_queue.NAVIGATION, message)
                last_instruction = instruction
                last_instruction_time = current_time

            log_msg = f"Pos: [{current_lat:.6f}, {current_lon:.6f}] | Target: {dist_to_final:.1f}m | Ideal: {ideal_bearing:.0f}° | IMU: {current_heading:.0f}° | Err: {error:.0f}° -> {instruction.upper()}"
            write_log(log_msg)

            time.sleep(2.0)

        # End of route
        if self.is_navigating and len(self.waypoints) == 0:
            self.is_navigating = False
            self.is_imu_active = False
            if self.audio_queue:
                self.audio_queue.put(
                    self.audio_queue.NAVIGATION,
                    f"Has llegado a {self.current_destination}.",
                )
            write_log("Destination reached. Navigation finished.")

    def cancel_navigation(self):
        if self.is_navigating:
            self.is_navigating = False
            self.is_imu_active = False
            self.waypoints = []
            return "Navegación cancelada."
        return "No hay ninguna ruta activa."

    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _calculate_bearing(self, lat1, lon1, lat2, lon2):
        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        diff_lon = math.radians(lon2 - lon1)
        x = math.sin(diff_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (
            math.sin(lat1) * math.cos(lat2) * math.cos(diff_lon)
        )
        initial_bearing = math.atan2(x, y)
        initial_bearing = math.degrees(initial_bearing)
        return (initial_bearing + 360) % 360

    def save_current_location(self, name):
        if not self.last_fix_time or (time.time() - self.last_fix_time > 15):
            return False, "No tengo señal de GPS para guardar esta ubicación."

        name_key = name.lower().strip()
        self.favorites[name_key] = {"lat": self.latitude, "lon": self.longitude}
        fav_path = Path.cwd() / "assets" / "ubication_favorites.json"

        try:
            with open(fav_path, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=4)
            return True, f"Ubicación guardada exitosamente como {name}."
        except Exception:
            return False, "Ocurrió un error al guardar el archivo."

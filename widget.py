import customtkinter as ctk
import threading
import requests  

from utils import blend

WEATHER_CITY = "Ottawa"                 # change to your city
WEATHER_REFRESH_MS = 10 * 60 * 1000      # refresh every 10 minutes

WEATHER_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

class Widget(ctk.CTkFrame):
    """A single dashboard tile. Each widget type has its own build_* function."""

    CORNER_RADIUS = 15
    TEXT_PAD_X = 15
    TEXT_PAD_Y = 10

    def __init__(self, master, widget_type, size, width, height,
                 bg="#22242a", fg="#ffffff"):
        super().__init__(master, width=width, height=height,
                         corner_radius=self.CORNER_RADIUS, fg_color=bg)
        self.widget_type = widget_type
        self.size = size
        self.bg = bg
        self.fg = fg

        # Keep the tile at its fixed size regardless of its contents
        self.pack_propagate(False)
        self.grid_propagate(False)

        # Map each widget type to its build function.
        # Children are placed directly on the tile (no full-size inner frame),
        # so nothing covers the rounded corners.
        builders = {
            "Volume": self.build_volume,
            "Weather": self.build_weather,
        }
        builders.get(widget_type, self.build_default)()

    # ---------- helpers ----------
    def add_title(self, text):
        """Tile text, pinned to the top-left corner."""
        label = ctk.CTkLabel(
            self, text=text, justify="left", anchor="w",
            text_color=self.fg, font=("Arial", 16, "bold")
        )
        label.place(x=self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="nw")
        return label

    # ---------- widget types ----------
    def build_default(self):
        self.add_title(f"{self.widget_type}\n({self.size})")

    def build_volume(self):
        # Top left: title
        self.add_title("Volume")

        # Top right: percent
        self.volume_label = ctk.CTkLabel(
            self, text="50%",
            text_color=self.fg, font=("Arial", 16, "bold")
        )
        self.volume_label.place(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")

        # Slider in the middle of the tile
        self.volume_slider = ctk.CTkSlider(
            self, from_=0, to=100, number_of_steps=100,
            command=self.on_volume_change,
            height=28,                 # thickness of the bar (default is 16)
            button_length=6,           # makes the handle wider (0 = round handle)
            button_corner_radius=14,   # roundness of the handle
            border_width=6,            # extra space around the track, which also makes the handle bigger
            fg_color=blend(self.bg, self.fg, 0.25),
            progress_color=self.fg,
            button_color=self.fg,
            button_hover_color=blend(self.fg, self.bg, 0.3),
        )
        self.volume_slider.set(50)
        self.volume_slider.place(relx=0.5, rely=0.55, anchor="center", relwidth=0.85)

    def build_weather(self):
        wide = getattr(self, "size", "1x1") != "1x1"    # 2x1 and 2x2 have room for details
        dim = blend(self.fg, self.bg, 0.35)

        # Top left: title
        self.add_title("Weather")

        # Big temperature (centred on 1x1, left side on wider tiles)
        cx = 0.27 if wide else 0.5
        self.temp_label = ctk.CTkLabel(
            self, text="--\u00b0",
            text_color=self.fg, font=("Arial", 30, "bold")
        )
        self.temp_label.place(relx=cx, rely=0.5, anchor="center")

        # Condition under the temperature
        self.cond_label = ctk.CTkLabel(
            self, text="Loading...",
            text_color=dim, font=("Arial", 10)
        )
        self.cond_label.place(relx=cx, rely=0.82, anchor="center")

        if wide:
            # Top right: city
            self.city_label = ctk.CTkLabel(
                self, text=WEATHER_CITY,
                text_color=dim, font=("Arial", 12)
            )
            self.city_label.place(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")

            # Right side: feels like, humidity, wind
            self.detail_label = ctk.CTkLabel(
                self, text="",
                text_color=dim, font=("Arial", 11), justify="right"
            )
            self.detail_label.place(relx=0.97, rely=0.62, anchor="e")

        self._weather_coords = None
        self._weather_result = None
        self.weather_refresh()

    # ---------- callbacks ----------
    def on_volume_change(self, value):
        self.volume_label.configure(text=f"{int(value)}%")
        # Hook your real system volume control in here

    def weather_refresh(self):
        if not self.winfo_exists():
            return                      # the tile was deleted, so stop the timer
        self._weather_result = None
        threading.Thread(target=self._weather_fetch, daemon=True).start()
        self.after(200, self._weather_poll)
        self.after(WEATHER_REFRESH_MS, self.weather_refresh)

    def _weather_fetch(self):
        """Runs in a background thread, so it must not touch any tkinter widget."""
        try:
            if self._weather_coords is None:
                geo = requests.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": WEATHER_CITY, "count": 1}, timeout=10
                ).json()["results"][0]
                self._weather_coords = (geo["latitude"], geo["longitude"])
            lat, lon = self._weather_coords
            self._weather_result = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,"
                                "relative_humidity_2m,wind_speed_10m,weather_code",
                }, timeout=10
            ).json()["current"]
        except Exception as e:
            self._weather_result = {"error": str(e)}

    def _weather_poll(self):
        """Runs on the main thread: picks up the result and updates the labels."""
        if not self.winfo_exists():
            return
        r = self._weather_result
        if r is None:
            self.after(200, self._weather_poll)         # not back yet, check again shortly
            return
        self._weather_result = None

        if "error" in r:
            self.cond_label.configure(text="Offline")
            return
        self.temp_label.configure(text=f"{round(r['temperature_2m'])}\u00b0")
        self.cond_label.configure(text=WEATHER_CODES.get(r["weather_code"], "Unknown"))
        if hasattr(self, "detail_label"):
            self.detail_label.configure(
                text=f"Feels {round(r['apparent_temperature'])}\u00b0\n"
                        f"Humidity {r['relative_humidity_2m']}%\n"
                        f"Wind {round(r['wind_speed_10m'])} km/h")
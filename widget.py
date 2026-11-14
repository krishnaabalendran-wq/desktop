import customtkinter as ctk
import threading
import requests  
import math
import time
from datetime import datetime
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

NOTIFY_CONTACTS = {
    "Thomas": "office",
    "Krishna": "billy_joe",
}

NOTIFY_MESSAGES = [        # (button label, text that gets sent). 1x1 and 2x1 use the first two.
    ("Come by", "Can you come by my desk when you get a minute?"),
    ("Urgent", "Urgent: can we talk right now?"),
    ("Free now?", "Are you free right now?"),
    ("Coffee?", "Coffee break? Meet me in the kitchen"),
]

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
            "Timer": self.build_timer,
            "Notify": self.build_notify,
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

    # ============================================
    # WEATHER LAYOUTS
    #   1x1 -> temp + condition
    #   2x1 -> temp + condition + city + details
    #   2x2 -> temp + condition + city + details + 3-day 
    # ============================================
 
    def build_weather(self):
        dim = blend(self.fg, self.bg, 0.35) #mixes 35% of the background into the foreground.

        self.city_label = None
        self.detail_label = None
        self.forecast_labels = [] #empty unless 2x2
        self._detail_separator = "\n" 

        self.add_title("Weather")

        if self.size == "1x1":
            self._weather_layout_1x1(dim)
        elif self.size == "2x1":
            self._weather_layout_2x1(dim)
        else:
            self._weather_layout_2x2(dim)

        self._weather_coords = None
        self._weather_result = None
        self.weather_refresh()

    def _weather_label(self, text, font_size, colour, bold=False, justify="center", wrap=0, **place):
        font = ("Arial", font_size, "bold") if bold else ("Arial", font_size)
        label = ctk.CTkLabel(self, text=text, text_color=colour, font=font, justify=justify, wraplength=wrap)
        label.place(**place) # **place -> everything else goes to .place() (relx, rely, anchor, x, y)
        return label

    def _weather_layout_1x1(self, dim):
        #Big temperature, Note: "\u00b0" is the degree symbol and -- is a placeholder for when the temperature is not yet loaded
        self.temp_label = self._weather_label(
            text="--\u00b0", font_size=36, colour=self.fg,
            bold=True, relx=0.5, rely=0.5, anchor="center"
        )
        #Condition text below the temperature
        self.cond_label = self._weather_label(
            text="Loading...", font_size=11, colour=dim, wrap=110,
            relx=0.5, rely=0.8, anchor="center")

    def _weather_layout_2x1(self, dim):
        self.temp_label = self._weather_label(
            text="--\u00b0", font_size=34, colour=self.fg,
            bold=True, relx=0.25, rely=0.5, anchor="center"
        )
        self.cond_label = self._weather_label(
            text="Loading...", font_size=11, colour=dim, 
            relx=0.25, rely=0.82, anchor="center"
        )
        self.city_label = self._weather_label(
            text=WEATHER_CITY, font_size=12, colour=dim,
            relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne" #x=-self.TEXT_PAD_X pulls the label in by the same margin as the title
        )
        self.detail_label = self._weather_label(
            text="", font_size=11, colour=dim, justify="right",
            relx=0.97, rely=0.62, anchor="e"
        )

    def _weather_layout_2x2(self, dim):
        self.city_label = self._weather_label(
            text=WEATHER_CITY, font_size=12, colour=dim,
            relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne"
        )
        self.temp_label = self._weather_label(
            text="--\u00b0", font_size=52, colour=self.fg,
            bold=True, relx=0.5, rely=0.26, anchor="center"
        )
        self.cond_label = self._weather_label(
            text="Loading...", font_size=14, colour=dim,
            relx=0.5, rely=0.42, anchor="center"
        )
        self.detail_label = self._weather_label(
            text="", font_size=11, colour=dim,
            relx=0.5, rely=0.52, anchor="center"
        )
        self._detail_separator = "   "

        # Thin divider line
        ctk.CTkFrame(
            self, height=1, corner_radius=0, 
            fg_color=blend(self.bg, self.fg, 0.2)
        ).place(relx=0.5, rely=0.64, anchor="center", relwidth=0.88)

        #Three forcast columns at 20%, 50%, 80% of the width, all on the same row
        for relx in (0.2, 0.5, 0.8):
            label = self._weather_label(
                text="--\n--", font_size=12, colour=dim,
                relx=relx, rely=0.79, anchor="center"
            )
            self.forecast_labels.append(label)

    # ============================================
    # TIMER
    #    wider sizes have - / + buttons to change length
    # ============================================
    def build_timer(self):
        self.timer_total = 5 * 60   # default: 5 minutes
        self.timer_left = self.timer_total
        self.timer_end = 0
        self.timer_running = False
        self.timer_job = None
        
        self.add_title("Timer")
        wide = self.size != "1x1"

        # The big MM:SS timer display in the middle of the tile
        self.timer_label = ctk.CTkLabel(
            self, text=self._format_time(self.timer_left), font=("Arial", 44 if wide else 32, "bold"))
        self.timer_label.place(relx=0.5, rely=0.45, anchor="center")

        # All buttons have the same display
        display = dict(
            height=28, corner_radius=14, text_color=self.fg, 
            fg_color=blend(self.bg, self.fg, 0.25), 
            hover_color=blend(self.fg, self.bg, 0.4)
        )

        bw = 0.40 if not wide else 0.22

        #Start/Pause button and Reset button
        self.start_timer_button = ctk.CTkButton(
            self, text="Start", command=self.timer_toggle, **display
        )
        self.start_timer_button.place(relx=0.08, rely=0.82, relwidth=bw, anchor="w")
        ctk.CTkButton(
            self, text="Reset", command=self.timer_reset, **display
        ).place(relx=0.73, rely=0.82, relwidth=bw, anchor="center")

        if wide:
            # - and + buttons to change the timer duration
            ctk.CTkButton(
                self, text="\u2212", width=36, command=lambda: self.adjust_time(-60), **display
            ).place(relx=0.08, rely=0.45, anchor="w")
            ctk.CTkButton(
                self, text="+", width=36, command=lambda: self.adjust_time(60), **display
            ).place(relx=0.92, rely=0.45, anchor="e")

    @staticmethod
    def _format_time(seconds):
        """seconds -> 'MM:SS'"""
        minutes, secs = divmod(seconds, 60) # divmod gives (whole minutes and the leftover seconds)
        return f"{minutes:02d}:{secs:02d}"

    def timer_toggle(self):
        if self.timer_running:
            self.timer_pause()
        else:
            self.timer_start()

    def timer_start(self):
        if self.timer_left <= 0:
            self.timer_left = self.timer_total
        self.timer_end = time.monotonic() + self.timer_left
        self.timer_running = True
        self.timer_label.configure(text_color=self.fg)
        self.start_timer_button.configure(text="Pause")
        self._timer_tick()

    def timer_reset(self):
        self._timer_stop_tick()
        self.timer_running = False
        self.timer_left = self.timer_total
        self.timer_label.configure(text=self._format_time(self.timer_left), text_color=self.fg)
        self.start_timer_button.configure(text="Start")

    def adjust_time(self, delta):
        if self.timer_running:      # time can only be adjusted when not running
            return
        self.timer_total = min(99 * 60, max(60, self.timer_total + delta))
        self.timer_reset()

    def _timer_stop_tick(self):
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
            self.timer_job = None

    def _timer_tick(self):
        if not self.winfo_exists() or not self.timer_running:   # tile deleted or paused
            return

        self.timer_left = max(0, math.ceil(self.timer_end - time.monotonic()))  # ceil is used so that at the last moment 00:01 is displayed
        self.timer_label.configure(text=self._format_time(self.timer_left))
        if self.timer_left == 0:
            self._timer_finished()
        else:
            self.timer_job = self.after(200, self._timer_tick)

    def _timer_finished(self):
        self.timer_running = False
        self.timer_job = None
        self.start_timer_button.configure(text="Start")
        self.bell()     # system beep
        self._flash(6)

    def _flash(self, times):
        if not self.winfo_exists():
            return
        if times == 0:
            self.timer_label.configure(text_color=self.fg)
            return
        self.timer_label.configure(text_color="#ff6b6b" if times % 2 == 0 else self.fg)
        self.after(400, lambda: self._flash(times - 1))

    # ============================================
    # NOTIFY
    # ============================================

    def build_notify(self):
        self.add_title("Notify")
        dim = blend(self.fg, self.bg, 0.35)
        shade = blend(self.bg, self.fg, 0.25)
        hover = blend(self.bg, self.fg, 0.4)

        # count: how many message buttons, btn_h/btn_w: their height and width (width is a
        # fraction of the tile), menu_place: where the name dropdown goes,
        # slots: (relx, rely) of each button, status_*: the status label
        if self.size == "1x1":
            count, btn_h, btn_w = 2, 28, 0.84
            menu_place = dict(relx=0.5, rely=0.37, anchor="center", relwidth=0.84)
            slots = [(0.5, 0.61), (0.5, 0.83)]                 # stacked
            status_place = dict(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y + 3, anchor="ne")
            status_size, status_wrap, status_text = 10, 60, ""
        elif self.size == "2x1":
            count, btn_h, btn_w = 2, 32, 0.42
            menu_place = dict(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")
            slots = [(0.27, 0.62), (0.73, 0.62)]               # side by side
            status_place = dict(relx=0.5, rely=0.89, anchor="center")
            status_size, status_wrap, status_text = 11, 260, "Choose a message"
        else:                                                  # 2x2
            count, btn_h, btn_w = 4, 40, 0.42
            menu_place = dict(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")
            slots = [(0.27, 0.32), (0.73, 0.32), (0.27, 0.54), (0.73, 0.54)]   # 2 by 2 grid
            status_place = dict(relx=0.5, rely=0.86, anchor="center")
            status_size, status_wrap, status_text = 14, 260, "Choose a message"

        # Name options, styled to match the buttons
        self.notify_to = ctk.CTkOptionMenu(
            self, values=list(NOTIFY_CONTACTS), width=100, height=26,
            font=("Arial", 12), dropdown_font=("Arial", 12),
            text_color=self.fg, fg_color=shade, button_color=hover,
            button_hover_color=blend(self.bg, self.fg, 0.5),
            dropdown_fg_color=self.bg, dropdown_text_color=self.fg,
            dropdown_hover_color=shade)
        self.notify_to.place(**menu_place)

        # One button per message, placed in its slot
        for (label, message), (rx, ry) in zip(NOTIFY_MESSAGES[:count], slots):
            btn = ctk.CTkButton(
                self, text=label, height=btn_h, corner_radius=btn_h // 2,
                font=("Arial", 12), text_color=self.fg, fg_color=shade, hover_color=hover,
                command=lambda m=message: self.notify_send(m))
            btn.place(relx=rx, rely=ry, relwidth=btn_w, anchor="center")

        if count == 4:                                         
            ctk.CTkFrame(self, height=1, corner_radius=0,
                         fg_color=blend(self.bg, self.fg, 0.2)
                         ).place(relx=0.5, rely=0.72, anchor="center", relwidth=0.88)

        self.notify_status = ctk.CTkLabel(
            self, text=status_text, font=("Arial", status_size),
            text_color=dim, wraplength=status_wrap)
        self.notify_status.place(**status_place)
        self._notify_dim = dim
        self._notify_result = None
        self._notify_name = ""

    def notify_send(self, text):
        self._notify_result = None
        self._notify_name = self.notify_to.get()
        self.notify_status.configure(text="Sending...", text_color=self._notify_dim)
        topic = NOTIFY_CONTACTS[self._notify_name]
        threading.Thread(
            target=lambda: setattr(self, "_notify_result", self._send_push(topic, text)),
            daemon=True).start()
        self.after(200, self._notify_poll)

    def _notify_poll(self):
        if not self.winfo_exists():
            return
        if self._notify_result is None:
            self.after(200, self._notify_poll)
            return
        ok, info = self._notify_result
        if ok:
            text = "Sent" if self.size == "1x1" else f"Sent to {self._notify_name}"
            self.notify_status.configure(text=text, text_color=self.fg)
        else:
            self.notify_status.configure(text=info, text_color="#ff6b6b")

    @staticmethod
    def _send_push(topic, body):
        """Send notification through ntfy.sh. Returns (Tre, "Sent") or (False, reason)."""
        try:
            r = requests.post(
                f"https://ntfy.sh/{topic}",
                data=body.encode("utf-8"),
                headers={"Title": "Thomas's Deck"},
                timeout=10,
            )
        except requests.RequestException:
            return False, "Offline"
        return (True, "Sent") if r.ok else (False, f"Error {r.status_code}")

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
            # Step 1: turn the city name into coordinates
            if self._weather_coords is None:
                geo = requests.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": WEATHER_CITY, "count": 1}, timeout=10
                ).json()["results"][0]
                self._weather_coords = (geo["latitude"], geo["longitude"])
            lat, lon = self._weather_coords

            # Step 2: ask for the weather. This keeps the WHOLE reply (current + daily)
            self._weather_result = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,"
                                "relative_humidity_2m,wind_speed_10m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "forecast_days": 4,
                    "timezone": "auto"
                }, timeout=10
            ).json()
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

        cur = r["current"]
        self.temp_label.configure(text=f"{round(cur['temperature_2m'])}\u00b0")
        self.cond_label.configure(text=WEATHER_CODES.get(cur["weather_code"], "Unknown"))

        #only for 2x1 and 2x2 labels
        if self.detail_label is not None:
            sep = self._detail_separator
            self.detail_label.configure(
                text=f"Feels like {round(cur['apparent_temperature'])}\u00b0{sep}"
                     f"{round(cur['relative_humidity_2m'])}% humidity{sep}"
                     f"{round(cur['wind_speed_10m'])} km/h wind"
            )

        #only for the 2x2 layout
        if self.forecast_labels:
            daily = r["daily"]
            for i, label in enumerate(self.forecast_labels):
                day_index = i + 1
                day = datetime.strptime(daily["time"][day_index], "%Y-%m-%d").strftime("%a")
                high = round(daily["temperature_2m_max"][day_index])
                low = round(daily["temperature_2m_min"][day_index])
                label.configure(text=f"{day}\n{high}\u00b0 / {low}\u00b0")
import calendar
import math
import os
import platform
import random
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from urllib.parse import quote_plus

import customtkinter as ctk
import pyttsx3
import requests
import speech_recognition as sr
from PIL import Image, ImageTk, ImageDraw

try:
    import psutil
except ImportError:
    psutil = None   # System tile shows a hint instead

from style import mono
from utils import blend
from volume import read_system_volume, set_system_volume

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

# voiceassistant voice assistant settings
voiceassistant_WAKE_WORDS = ["computer", "voiceassistant"]
voiceassistant_EXIT_WORDS = ["exit", "bye", "stop"]
voiceassistant_YOUTUBE_WORDS = ["youtube", "play", "watch", "video", "videos", "a video"]
voiceassistant_GOOGLE_WORDS = ["google", "search", "look up", "find", "go to", "go on"]

voiceassistant_WEBSITES = {
    "brightspace": "https://brightspace.carleton.ca/",
    "gemini": "https://gemini.google.com/",
    "youtube": "https://www.youtube.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class CornerGlowCanvas(tk.Canvas):
    """Soft ambient corner radial glow with rounded corners matching the tile."""

    def __init__(self, master, width, height, bg_hex, fg_hex=None, fps=20, corner_radius=12):
        super().__init__(master, width=width-2, height=height-2, highlightthickness=0, bd=0, bg="#0a0a0a")
        self.w = width - 2
        self.h = height - 2
        self.corner_radius = corner_radius

        self.bg_rgb = _hex_to_rgb("#0a0a0a")
        self.glow_rgb = _hex_to_rgb(bg_hex)

        self.phase = random.uniform(0, math.pi * 2)
        self.delay = int(1000 / fps)
        self._photo = None
        self._img_id = self.create_image(0, 0, anchor="nw")

        self.place(x=1, y=1, width=self.w, height=self.h)
        self.tk.call("lower", self._w)
        self._animate()

    def _get_color_at(self, nx, ny, pulse):
        # Distance from top-left corner (0,0) for the radial glow effect
        dist = math.sqrt(nx**2 + ny**2)
        glow_spread = 1.2 + 0.15 * pulse
        
        # Smooth exponential falloff for an ambient lighting feel
        intensity = max(0.0, 1.0 - dist * glow_spread) ** 2.2
        
        return tuple(int(base * (1 - intensity) + glow * intensity)
                     for base, glow in zip(self.bg_rgb, self.glow_rgb))

    def _animate(self):
        if not self.winfo_exists():
            return

        t = time.time()
        pulse = 0.5 + 0.5 * math.sin(t * 1.5 + self.phase)

        # Render a compact 24x24 sample grid and let PIL Bicubic smoothing blend it
        gw, gh = 24, 24
        img = Image.new("RGB", (gw, gh))
        px = img.load()
        for y in range(gh):
            ny = y / (gh - 1)
            for x in range(gw):
                nx = x / (gw - 1)
                px[x, y] = self._get_color_at(nx, ny, pulse)

        full_img = img.resize((max(1, self.w), max(1, self.h)), Image.Resampling.BICUBIC)
        
        # Apply smooth rounded corners mask matching the tile's corner radius
        mask = Image.new("L", (self.w, self.h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, self.w, self.h], radius=self.corner_radius, fill=255)
        
        output_img = Image.new("RGBA", (self.w, self.h))
        output_img.paste(full_img, (0, 0))
        output_img.putalpha(mask)
        
        self._photo = ImageTk.PhotoImage(output_img)
        self.itemconfig(self._img_id, image=self._photo)

        self.after(self.delay, self._animate)


class Widget(ctk.CTkFrame):
    """A single dashboard tile. Each widget type has its own build_* function."""

    CORNER_RADIUS = 12
    TEXT_PAD_X = 18
    TEXT_PAD_Y = 15

    def __init__(self, master, widget_type, size, width, height,
                 bg="#171717", fg="#9a9a9a"):

        self.default_border = blend(bg, fg, 0.18)

        # Force the frame background to perfectly match the canvas's #0a0a0a deep black.
        # This makes the default transparent labels perfectly blend in.
        super().__init__(master, width=width, height=height,
                         corner_radius=self.CORNER_RADIUS, fg_color="#0a0a0a",
                         border_width=1, border_color=self.default_border)

        self.widget_type = widget_type
        self.size = size
        self.bg = bg
        self.fg = fg

        self.hovering = False
        self._base_y = None

        self.pack_propagate(False)
        self.grid_propagate(False)

        # 1. Add the animated mostly-black corner glow
        self.bg_canvas = CornerGlowCanvas(self, width, height, bg, fg)

        # 2. Build internal widgets
        builders = {
            "Volume": self.build_volume,
            "Weather": self.build_weather,
            "Timer": self.build_timer,
            "Notify": self.build_notify,
            "Date": self.build_date,
            "System": self.build_system,
            "voiceassistant": self.build_voiceassistant,
        }
        builders.get(widget_type, self.build_default)()

        # 3. Bind hover
        self.bind_hover_events(self)

    def bind_hover_events(self, widget):
        widget.bind("<Enter>", self.on_enter, add="+")
        for child in widget.winfo_children():
            if isinstance(child, tk.Canvas):
                continue
            self.bind_hover_events(child)

    def on_enter(self, event):
        try:
            if hasattr(self.master, "drag") and getattr(self.master.drag, "editing", False):
                return
        except Exception:
            pass

        if not self.hovering:
            self.hovering = True
            try:
                info = self.place_info()
                if 'y' in info:
                    self._base_y = float(info['y'])
                    self.place_configure(y=self._base_y - 4)
                else:
                    self._base_y = None
            except Exception:
                self._base_y = None

            self.animate_glow()

    def animate_glow(self):
        if not self.hovering:
            return

        is_editing = False
        try:
            if hasattr(self.master, "drag") and getattr(self.master.drag, "editing", False):
                is_editing = True
        except Exception:
            pass

        inside = False
        try:
            x, y = self.winfo_pointerxy()
            rx, ry = self.winfo_rootx(), self.winfo_rooty()
            inside = (rx <= x <= rx + self.winfo_width() and ry <= y <= ry + self.winfo_height())
        except Exception:
            pass

        if is_editing or not inside:
            self.hovering = False
            self.configure(border_color=self.default_border)
            if self._base_y is not None:
                try:
                    self.place_configure(y=self._base_y)
                except Exception:
                    pass
                self._base_y = None
            return

        t = time.time() * 4
        v = max(0, min(255, int(math.sin(t) * 45 + 175)))
        color = f"#{v:02x}{v:02x}{v:02x}"
        try:
            self.configure(border_color=color)
        except Exception:
            pass

        self.after(30, self.animate_glow)

    # ---------- shared helpers ----------
    def add_title(self, text):
        """Tile name, pinned to the top-left corner."""
        label = ctk.CTkLabel(
            self, text=text, justify="left", anchor="w",
            text_color=self.fg, font=mono(11, True)
        )
        label.place(x=self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="nw")
        return label

    # ---------- widget types ----------
    def build_default(self):
        title_lbl = ctk.CTkLabel(self, text=self.widget_type.upper(), text_color=self.fg, font=mono(11, True), fg_color="transparent")
        title_lbl.place(x=self.TEXT_PAD_X, rely=1.0, y=-self.TEXT_PAD_Y, anchor="sw")

        size_lbl = ctk.CTkLabel(self, text=self.size, text_color=blend(self.fg, self.bg, 0.45), font=mono(10), fg_color="transparent")
        size_lbl.place(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")

    def build_volume(self):
        # Bottom Left: "VOLUME"
        title_lbl = ctk.CTkLabel(self, text="VOLUME", text_color=self.fg, font=mono(11, True), fg_color="transparent")
        title_lbl.place(x=self.TEXT_PAD_X, rely=1.0, y=-self.TEXT_PAD_Y, anchor="sw")

        # Top Right: "50%"
        self.volume_label = ctk.CTkLabel(self, text="50%", text_color=blend(self.fg, self.bg, 0.45), font=mono(11, True), fg_color="transparent")
        self.volume_label.place(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")

        self.volume_slider = ctk.CTkSlider(
            self, from_=0, to=100, number_of_steps=100,
            command=self.on_volume_change,
            height=24,
            corner_radius=1,
            button_length=10,
            button_corner_radius=1,
            border_width=8,
            fg_color=blend(self.bg, self.fg, 0.22),
            progress_color=blend(self.bg, self.fg, 0.6),
            button_color=self.fg,
            button_hover_color=blend(self.bg, self.fg, 0.8),
            bg_color="transparent"
        )
        # Start the slider at the real system volume (50 if it can't be read)
        current = read_system_volume()
        current = 50 if current is None else current
        self.volume_slider.set(current)
        self.volume_label.configure(text=f"{current}%")
        self.volume_slider.place(relx=0.5, rely=0.45, anchor="center", relwidth=0.75)

    # ============================================
    # WEATHER LAYOUTS
    #   1x1 -> temp + condition
    #   2x1 -> temp + condition + city + details
    #   2x2 -> temp + condition + city + details + 3-day
    # ============================================

    def build_weather(self):
        dim = blend(self.fg, self.bg, 0.35)

        self.city_label = None
        self.detail_label = None
        self.forecast_labels = []   # empty unless 2x2
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
        label = ctk.CTkLabel(self, text=text, text_color=colour, font=mono(font_size, bold),
                             justify=justify, wraplength=wrap)
        label.place(**place)
        return label

    def _weather_layout_1x1(self, dim):
        # "--" is a placeholder until the first reading arrives
        self.temp_label = self._weather_label(
            text="--\u00b0", font_size=36, colour=self.fg,
            bold=True, relx=0.5, rely=0.5, anchor="center"
        )
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
            relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne"
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

        # Thin divider line (sharp, like the rest of the style)
        ctk.CTkFrame(
            self, height=1, corner_radius=0,
            fg_color=blend(self.bg, self.fg, 0.2)
        ).place(relx=0.5, rely=0.64, anchor="center", relwidth=0.88)

        # Three forecast columns at 20%, 50%, 80% of the width, all on the same row
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
            self, text=self._format_time(self.timer_left), font=mono(44 if wide else 32, True))
        self.timer_label.place(relx=0.5, rely=0.45, anchor="center")

        # All buttons share this look
        display = dict(
            height=28, corner_radius=0, text_color=self.fg,
            fg_color=blend(self.bg, self.fg, 0.25),
            hover_color=blend(self.fg, self.bg, 0.4),
            font=mono(11, True),
        )

        bw = 0.40 if not wide else 0.22

        # Start/Pause and Reset buttons
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
        minutes, secs = divmod(seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def timer_toggle(self):
        if self.timer_running:
            self.timer_pause()
        else:
            self.timer_start()

    def timer_pause(self):
        self._timer_stop_tick()
        self.timer_running = False
        self.timer_left = max(0, math.ceil(self.timer_end - time.monotonic()))
        self.timer_label.configure(text=self._format_time(self.timer_left))
        self.start_timer_button.configure(text="Start")

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

        # ceil so the display shows 00:01 right up to the end
        self.timer_left = max(0, math.ceil(self.timer_end - time.monotonic()))
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
            font=mono(11), dropdown_font=mono(11), corner_radius=0,
            text_color=self.fg, fg_color=shade, button_color=hover,
            button_hover_color=blend(self.bg, self.fg, 0.5),
            dropdown_fg_color=self.bg, dropdown_text_color=self.fg,
            dropdown_hover_color=shade)
        self.notify_to.place(**menu_place)

        # One button per message, placed in its slot
        for (label, message), (rx, ry) in zip(NOTIFY_MESSAGES[:count], slots):
            btn = ctk.CTkButton(
                self, text=label, height=btn_h, corner_radius=0,
                font=mono(11), text_color=self.fg, fg_color=shade, hover_color=hover,
                command=lambda m=message: self.notify_send(m))
            btn.place(relx=rx, rely=ry, relwidth=btn_w, anchor="center")

        if count == 4:
            ctk.CTkFrame(self, height=1, corner_radius=0,
                         fg_color=blend(self.bg, self.fg, 0.2)
                         ).place(relx=0.5, rely=0.72, anchor="center", relwidth=0.88)

        self.notify_status = ctk.CTkLabel(
            self, text=status_text, font=mono(status_size),
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
        """Send notification through ntfy.sh. Returns (True, "Sent") or (False, reason)."""
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

    # ============================================
    # DATE
    #    1x1 -> day number + weekday
    #    2x1 -> day number + weekday, and month / year
    #    2x2 -> month calendar with today highlighted
    # ============================================
    @staticmethod
    def _cal_x(col):
        """Horizontal position of calendar column 0-6 (Sunday first)."""
        return 0.1 + col * (0.8 / 6)

    def build_date(self):
        self.add_title("Date")
        dim = blend(self.fg, self.bg, 0.35)
        self._date_dim = dim
        self._day_label = None
        self._weekday_label = None
        self._month_label = None
        self._cal_cells = []

        if self.size == "2x2":
            self._month_label = self._weather_label(
                "", 11, dim, bold=True, relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")
            for col, name in enumerate("SMTWTFS"):
                self._weather_label(name, 9, dim, relx=self._cal_x(col), rely=0.36, anchor="center")
            for row in range(6):
                cells = []
                for col in range(7):
                    cells.append(self._weather_label(
                        "", 9, dim, relx=self._cal_x(col), rely=0.46 + row * 0.085, anchor="center"))
                self._cal_cells.append(cells)
        elif self.size == "2x1":
            self._day_label = self._weather_label("", 40, self.fg, bold=True, relx=0.22, rely=0.56, anchor="center")
            self._weekday_label = self._weather_label("", 10, dim, relx=0.22, rely=0.86, anchor="center")
            self._month_label = self._weather_label("", 13, self.fg, bold=True, relx=0.7, rely=0.5, anchor="center")
        else:
            self._day_label = self._weather_label("", 34, self.fg, bold=True, relx=0.5, rely=0.55, anchor="center")
            self._weekday_label = self._weather_label("", 10, dim, relx=0.5, rely=0.84, anchor="center")

        self._date_refresh()

    def _date_refresh(self):
        if not self.winfo_exists():
            return
        now = datetime.now()
        if self._day_label is not None:
            self._day_label.configure(text=str(now.day))
        if self._weekday_label is not None:
            weekday_fmt = "%a" if self.size == "1x1" else "%A"   # short name fits the small tile
            self._weekday_label.configure(text=now.strftime(weekday_fmt).upper())
        if self._month_label is not None:
            self._month_label.configure(text=now.strftime("%B %Y").upper())
        if self._cal_cells:
            self._fill_calendar(now)
        self.after(60_000, self._date_refresh)   # once a minute is enough to roll over at midnight

    def _fill_calendar(self, now):
        weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(now.year, now.month)
        for row, cells in enumerate(self._cal_cells):
            for col, label in enumerate(cells):
                day = weeks[row][col] if row < len(weeks) else 0
                if day == 0:
                    label.configure(text="", fg_color="transparent", text_color=self._date_dim)
                elif day == now.day:
                    label.configure(text=str(day), fg_color=self.fg, text_color=self.bg)
                else:
                    label.configure(text=str(day), fg_color="transparent", text_color=self._date_dim)

    # ============================================
    # SYSTEM STATS (needs: pip install psutil)
    #    1x1 -> CPU %
    #    2x1 -> CPU and memory bars
    #    2x2 -> CPU, memory, disk and battery bars
    # ============================================
    SYSTEM_STATS_MS = 2000

    def build_system(self):
        self.add_title("System")
        dim = blend(self.fg, self.bg, 0.35)
        shade = blend(self.bg, self.fg, 0.25)
        self._sys_rows = {}
        self._sys_big = None

        if psutil is None:
            self._weather_label("Needs psutil\npip install psutil", 9, dim, justify="center",
                                relx=0.5, rely=0.55, anchor="center")
            return

        psutil.cpu_percent(interval=None)   # the first call always returns 0, so prime it

        if self.size == "1x1":
            self._sys_big = self._weather_label("--%", 30, self.fg, bold=True, relx=0.5, rely=0.5, anchor="center")
            self._weather_label("CPU", 9, dim, relx=0.5, rely=0.82, anchor="center")
        else:
            if self.size == "2x1":
                names, top, step, bar_dy = ["CPU", "MEM"], 0.42, 0.3, 0.15
            else:
                names, top, step, bar_dy = ["CPU", "MEM", "DISK", "BATT"], 0.3, 0.18, 0.085
            for name in names:
                self._weather_label(name, 10, dim, relx=0.0, x=self.TEXT_PAD_X, rely=top, anchor="nw")
                value = self._weather_label("--", 10, self.fg, bold=True,
                                            relx=1.0, x=-self.TEXT_PAD_X, rely=top, anchor="ne")
                bar = ctk.CTkProgressBar(self, height=4, corner_radius=0,
                                         progress_color=self.fg, fg_color=shade)
                bar.set(0)
                bar.place(relx=0.5, rely=top + bar_dy, anchor="n", relwidth=0.86)
                self._sys_rows[name] = (value, bar)
                top += step

        self._sys_tick()

    def _sys_tick(self):
        if not self.winfo_exists():
            return
        if self._sys_big is not None:
            self._sys_big.configure(text=f"{psutil.cpu_percent(interval=None):.0f}%")
        for name, (value, bar) in self._sys_rows.items():
            pct, text = self._sys_read(name)
            value.configure(text=text)
            bar.set(pct / 100)
        self.after(self.SYSTEM_STATS_MS, self._sys_tick)

    @staticmethod
    def _sys_read(name):
        """Returns (percent 0-100, label text) for one stat row."""
        if name == "CPU":
            pct = psutil.cpu_percent(interval=None)
        elif name == "MEM":
            pct = psutil.virtual_memory().percent
        elif name == "DISK":
            pct = psutil.disk_usage(os.path.expanduser("~")).percent
        else:  # BATT
            battery = psutil.sensors_battery()
            if battery is None:
                return 0, "N/A"
            tag = " CHG" if battery.power_plugged else ""
            return battery.percent, f"{battery.percent:.0f}%{tag}"
        return pct, f"{pct:.0f}%"

    # ============================================
    # voiceassistant VOICE ASSISTANT
    #    1x1 -> status + Listen/Stop button
    #    2x1 -> status + heard command + Listen/Stop button
    #    2x2 -> status + heard command + assistant reply + Listen/Stop button
    # ============================================
    def build_voiceassistant(self):
        self.add_title("voiceassistant")
        dim = blend(self.fg, self.bg, 0.35)
        self._voiceassistant_dim = dim
        self._voiceassistant_running = False
        self._voiceassistant_thread = None

        self._voiceassistant_recognizer = sr.Recognizer()
        self._voiceassistant_recognizer.pause_threshold = 1.6
        self._voiceassistant_recognizer.non_speaking_duration = 0.8
        self._voiceassistant_recognizer.phrase_threshold = 0.2

        self.voiceassistant_state_label = self._weather_label(
            text="IDLE", font_size=10, colour=dim, bold=True,
            relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne"
        )

        btn_style = dict(
            height=28, corner_radius=0, text_color=self.fg,
            fg_color=blend(self.bg, self.fg, 0.25),
            hover_color=blend(self.fg, self.bg, 0.4),
            font=mono(11, True),
        )

        self.voiceassistant_heard_label = None
        self.voiceassistant_reply_label = None

        if self.size == "1x1":
            self.voiceassistant_heard_label = self._weather_label(
                text='Say "computer..."', font_size=10, colour=dim, wrap=120,
                relx=0.5, rely=0.48, anchor="center"
            )
            self.voiceassistant_btn = ctk.CTkButton(
                self, text="Listen", command=self.voiceassistant_toggle, **btn_style
            )
            self.voiceassistant_btn.place(relx=0.5, rely=0.82, relwidth=0.84, anchor="center")

        elif self.size == "2x1":
            self.voiceassistant_heard_label = self._weather_label(
                text='Say "computer" + command', font_size=11, colour=self.fg,
                justify="left", wrap=190,
                relx=0.0, x=self.TEXT_PAD_X, rely=0.48, anchor="w"
            )
            self.voiceassistant_reply_label = self._weather_label(
                text="Ready", font_size=10, colour=dim,
                justify="left", wrap=190,
                relx=0.0, x=self.TEXT_PAD_X, rely=0.78, anchor="w"
            )
            self.voiceassistant_btn = ctk.CTkButton(
                self, text="Listen", command=self.voiceassistant_toggle, **btn_style
            )
            self.voiceassistant_btn.place(relx=0.84, rely=0.60, relwidth=0.24, anchor="center")

        else:  # 2x2
            self.voiceassistant_heard_label = self._weather_label(
                text='Say "computer" or "voiceassistant"...', font_size=12, colour=self.fg,
                justify="left", wrap=280,
                relx=0.0, x=self.TEXT_PAD_X, rely=0.34, anchor="w"
            )
            ctk.CTkFrame(
                self, height=1, corner_radius=0,
                fg_color=blend(self.bg, self.fg, 0.2)
            ).place(relx=0.5, rely=0.50, anchor="center", relwidth=0.88)

            self.voiceassistant_reply_label = self._weather_label(
                text="Click Listen to start voice control.", font_size=11, colour=dim,
                justify="left", wrap=280,
                relx=0.0, x=self.TEXT_PAD_X, rely=0.65, anchor="w"
            )
            self.voiceassistant_btn = ctk.CTkButton(
                self, text="Listen", command=self.voiceassistant_toggle, **btn_style
            )
            self.voiceassistant_btn.place(relx=0.5, rely=0.86, relwidth=0.88, anchor="center")

    def _voiceassistant_ui_update(self, state=None, heard=None, reply=None, running=None):
        """Thread-safe helper to update voiceassistant labels on the main Tkinter thread."""
        def _apply():
            if not self.winfo_exists():
                return
            if state is not None:
                self.voiceassistant_state_label.configure(
                    text=state,
                    text_color=self.fg if state in ("LISTENING", "SPEAKING") else self._voiceassistant_dim
                )
            if heard is not None and self.voiceassistant_heard_label is not None:
                self.voiceassistant_heard_label.configure(text=heard)
            if reply is not None and self.voiceassistant_reply_label is not None:
                self.voiceassistant_reply_label.configure(text=reply)
            if running is not None:
                self.voiceassistant_btn.configure(text="Stop" if running else "Listen")

        try:
            self.after(0, _apply)
        except Exception:
            pass

    def voiceassistant_toggle(self):
        if self._voiceassistant_running:
            self._voiceassistant_running = False
            self._voiceassistant_ui_update(state="IDLE", reply="Stopped.", running=False)
        else:
            self._voiceassistant_running = True
            self._voiceassistant_ui_update(state="CALIBRATING", reply="Calibrating mic...", running=True)
            self._voiceassistant_thread = threading.Thread(target=self._voiceassistant_loop, daemon=True)
            self._voiceassistant_thread.start()

    @staticmethod
    def _voiceassistant_open_url(url):
        if platform.system() == "Darwin":
            subprocess.run(["open", "-a", "/Applications/Google Chrome.app", url])
        else:
            import webbrowser
            webbrowser.open(url)

    def _voiceassistant_speak(self, text):
        print(f"Assistant: {text}")
        self._voiceassistant_ui_update(state="SPEAKING", reply=text)
        if platform.system() == "Darwin":
            subprocess.run(["say", text])
        else:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        time.sleep(0.6)

    def _voiceassistant_wish_user(self):
        hour = datetime.now().hour
        if hour < 12:
            self._voiceassistant_speak("Good Morning!")
        elif hour < 18:
            self._voiceassistant_speak("Good Afternoon!")
        else:
            self._voiceassistant_speak("Good Evening!")
        self._voiceassistant_speak("All systems nominal. Say computer followed by a command.")

    def _voiceassistant_take_command(self):
        if not self._voiceassistant_running or not self.winfo_exists():
            return ""
        self._voiceassistant_ui_update(state="LISTENING")
        try:
            with sr.Microphone() as source:
                audio = self._voiceassistant_recognizer.listen(source, timeout=2, phrase_time_limit=12)
        except sr.WaitTimeoutError:
            return ""
        except Exception:
            return ""

        if not self._voiceassistant_running or not self.winfo_exists():
            return ""

        self._voiceassistant_ui_update(state="RECOGNIZING")
        try:
            query = self._voiceassistant_recognizer.recognize_google(audio, language="en-US")
            print(f"You: {query}")
            cleaned = query.lower().strip()
            self._voiceassistant_ui_update(heard=f"You: {cleaned}")
            return cleaned
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            self._voiceassistant_speak("Speech service is unavailable right now.")
            return ""

    @staticmethod
    def _voiceassistant_remove_wake_word(query):
        for word in voiceassistant_WAKE_WORDS:
            if query == word:
                return ""
            if query.startswith(word + " "):
                return query[len(word):].strip()
            if query.startswith(word + ","):
                return query[len(word) + 1:].strip()
        return None

    @staticmethod
    def _voiceassistant_get_direct_website(command):
        prefixes = ["go to ", "go on ", "open up ", "open "]
        target = command

        for prefix in prefixes:
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break

        if target in voiceassistant_WEBSITES:
            return target, voiceassistant_WEBSITES[target]

        return None, None

    @staticmethod
    def _voiceassistant_get_destination(command):
        if "youtube" in command:
            return "youtube"
        if "google" in command:
            return "google"

        cleaned = command
        used_open = False
        if cleaned.startswith("open up "):
            cleaned = cleaned[len("open up "):].strip()
            used_open = True
        elif cleaned.startswith("open "):
            cleaned = cleaned[len("open "):].strip()
            used_open = True

        for word in voiceassistant_YOUTUBE_WORDS:
            if cleaned == word or cleaned.startswith(word + " "):
                return "youtube"

        for word in voiceassistant_GOOGLE_WORDS:
            if cleaned == word or cleaned.startswith(word + " "):
                return "google"

        if used_open and cleaned != "":
            return "google"

        return None

    @staticmethod
    def _voiceassistant_get_search_query(command, destination):
        text = command

        openings = [
            f"go on {destination} and",
            f"go to {destination} and",
            f"go on {destination}",
            f"go to {destination}",
            f"open up {destination} and",
            f"open {destination} and",
            f"open up {destination}",
            f"open {destination}",
            destination,
        ]
        for opening in openings:
            if text == opening:
                return ""
            if text.startswith(opening + " "):
                text = text[len(opening):].strip()
                break

        endings = [
            f"on {destination}",
            f"in {destination}",
            f"to {destination}",
            destination,
        ]
        for ending in endings:
            if text.endswith(" " + ending):
                text = text[:-len(ending)].strip()
                break

        front_phrases = [
            "search up",
            "search for",
            "look up",
            "a video of",
            "videos of",
            "video of",
            "open up",
        ]
        front_words = [
            "go", "to", "open", "search", "google", "youtube",
            "play", "watch", "find", "up", "for", "on", "about", "and",
        ]

        keeping_cleaning = True
        while keeping_cleaning and text != "":
            keeping_cleaning = False

            for phrase in front_phrases:
                if text == phrase:
                    return ""
                if text.startswith(phrase + " "):
                    text = text[len(phrase):].strip()
                    keeping_cleaning = True
                    break

            if not keeping_cleaning:
                words = text.split()
                if words[0] in front_words:
                    words.pop(0)
                    text = " ".join(words)
                    keeping_cleaning = True

        return text

    @staticmethod
    def _voiceassistant_get_weather(city=WEATHER_CITY):
        try:
            geo = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1},
                timeout=8,
            ).json()

            if not geo.get("results"):
                return f"I couldn't find weather data for {city}."

            place = geo["results"][0]
            lat, lon = place["latitude"], place["longitude"]
            resolved_name = place.get("name", city)

            data = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,weather_code",
                    "timezone": "auto",
                },
                timeout=8,
            ).json()

            cur = data["current"]
            temp = round(cur["temperature_2m"])
            feels = round(cur["apparent_temperature"])
            condition = WEATHER_CODES.get(cur["weather_code"], "clear").lower()
            return f"It is currently {temp} degrees and {condition} in {resolved_name}, feeling like {feels}."
        except Exception:
            return "Sorry, I couldn't check the weather right now."

    def _voiceassistant_loop(self):
        try:
            with sr.Microphone() as source:
                self._voiceassistant_recognizer.adjust_for_ambient_noise(source, duration=1.0)
                self._voiceassistant_recognizer.dynamic_energy_threshold = False
        except Exception as e:
            self._voiceassistant_running = False
            self._voiceassistant_ui_update(state="ERROR", reply=f"Mic error: {e}", running=False)
            return

        if not self._voiceassistant_running or not self.winfo_exists():
            return

        self._voiceassistant_wish_user()

        while self._voiceassistant_running and self.winfo_exists():
            raw_query = self._voiceassistant_take_command()

            if raw_query == "":
                continue
            if raw_query.startswith("opening ") or raw_query.startswith("searching "):
                continue

            command = self._voiceassistant_remove_wake_word(raw_query)
            if command is None:
                continue

            if command == "":
                self._voiceassistant_speak("Yes?")
                command = self._voiceassistant_take_command()
                if command == "":
                    continue
                second_check = self._voiceassistant_remove_wake_word(command)
                if second_check is not None:
                    command = second_check

            words = command.split()
            if len(words) > 0 and words[0] in voiceassistant_EXIT_WORDS:
                self._voiceassistant_speak("Goodbye! Have a nice day!")
                self._voiceassistant_running = False
                self._voiceassistant_ui_update(state="IDLE", running=False)
                break

            if command in ["hello", "hi", "hey"]:
                self._voiceassistant_speak("Hello! How can I help you?")
                continue

            if "how are you" in command:
                self._voiceassistant_speak("I am doing well and ready to help.")
                continue

            if "who are you" in command or "your name" in command:
                self._voiceassistant_speak("I am voiceassistant, your voice assistant.")
                continue

            if command.startswith("say "):
                phrase = command[len("say "):].strip()
                if phrase == "hello":
                    self._voiceassistant_speak("Greetings, all.")
                elif phrase != "":
                    self._voiceassistant_speak(phrase)
                continue

            if "date" in command or "day is it" in command:
                today = datetime.now().strftime("%A, %B %d, %Y")
                self._voiceassistant_speak(f"Today is {today}")
                continue

            if "time" in command:
                current_time = datetime.now().strftime("%I:%M %p")
                self._voiceassistant_speak(f"The current time is {current_time}")
                continue

            if "weather" in command or "temperature" in command:
                city = WEATHER_CITY
                if " in " in command:
                    spoken_city = command.split(" in ", 1)[1].strip()
                    if spoken_city != "":
                        city = spoken_city
                self._voiceassistant_speak("Checking the weather...")
                report = self._voiceassistant_get_weather(city)
                self._voiceassistant_speak(report)
                continue

            site_name, site_url = self._voiceassistant_get_direct_website(command)
            if site_url is not None:
                self._voiceassistant_speak(f"Opening {site_name.capitalize()}...")
                self._voiceassistant_open_url(site_url)
                continue

            destination = self._voiceassistant_get_destination(command)
            if destination is not None:
                search_query = self._voiceassistant_get_search_query(command, destination)

                if search_query != "":
                    encoded_query = quote_plus(search_query)
                    if destination == "google":
                        url = f"https://www.google.com/search?q={encoded_query}"
                        self._voiceassistant_speak(f"Searching Google for {search_query}...")
                    else:
                        url = f"https://www.youtube.com/results?search_query={encoded_query}"
                        self._voiceassistant_speak(f"Searching YouTube for {search_query}...")
                    self._voiceassistant_open_url(url)
                else:
                    if destination == "google":
                        self._voiceassistant_speak("Opening Google...")
                        self._voiceassistant_open_url("https://www.google.com/")
                    else:
                        self._voiceassistant_speak("Opening YouTube...")
                        self._voiceassistant_open_url("https://www.youtube.com/")
                continue

            self._voiceassistant_speak("Sorry, I didn't understand that. Try again.")

        self._voiceassistant_ui_update(state="IDLE", running=False)

    # ---------- callbacks ----------
    def on_volume_change(self, value):
        self.volume_label.configure(text=f"{int(value)}%")
        set_system_volume(value)

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

            # Step 2: current conditions plus the daily range for the forecast
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

        # only for 2x1 and 2x2
        if self.detail_label is not None:
            sep = self._detail_separator
            self.detail_label.configure(
                text=f"Feels like {round(cur['apparent_temperature'])}\u00b0{sep}"
                     f"{round(cur['relative_humidity_2m'])}% humidity{sep}"
                     f"{round(cur['wind_speed_10m'])} km/h wind"
            )

        # only for the 2x2 layout
        if self.forecast_labels:
            daily = r["daily"]
            for i, label in enumerate(self.forecast_labels):
                day_index = i + 1
                day = datetime.strptime(daily["time"][day_index], "%Y-%m-%d").strftime("%a")
                high = round(daily["temperature_2m_max"][day_index])
                low = round(daily["temperature_2m_min"][day_index])
                label.configure(text=f"{day}\n{high}\u00b0 / {low}\u00b0")

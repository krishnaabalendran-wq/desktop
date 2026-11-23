import calendar
import math
import os
import random
import threading
import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
import requests
from PIL import Image, ImageTk

try:
    import psutil
except ImportError:
    psutil = None   # System tile shows a hint instead

from style import mono
from utils import blend
from volume import read_system_volume, set_system_volume
from scenes import load_scenes, get_scene_color

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


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class CornerGlowCanvas(tk.Canvas):
    """Animated gradient: the theme colour in the top left, fading to near-black across the tile."""

    def __init__(self, master, width, height, bg_hex, fg_hex=None, fps=20):
        # We inset by 1px so the CustomTkinter border is not covered
        super().__init__(master, width=width-2, height=height-2, highlightthickness=0, bd=0, bg="#0a0a0a")
        self.w = width - 2
        self.h = height - 2

        # Override the base background to be very dark (mostly black)
        self.bg_rgb = _hex_to_rgb("#0a0a0a")
        self.glow_rgb = _hex_to_rgb(bg_hex)   # the theme colour, shown at the top-left

        self.phase = random.uniform(0, math.pi * 2)
        self.delay = int(1000 / fps)
        self._photo = None
        self._img_id = self.create_image(0, 0, anchor="nw")

        self.place(x=1, y=1, width=self.w, height=self.h)
        self.tk.call("lower", self._w)
        self._animate()

    def _get_color_at(self, nx, ny, pulse):
        dist = math.sqrt(nx**2 + ny**2)
        glow_spread = 1.4 + 0.2 * pulse
        # Non-linear falloff (cube) so the white stays in the corner and it's mostly black
        intensity = max(0.0, 1.0 - dist * glow_spread) ** 3.0
        blend_factor = intensity   # 1.0 at the top-left corner, so it shows the full theme colour

        return tuple(int(base * (1 - blend_factor) + glow * blend_factor)
                     for base, glow in zip(self.bg_rgb, self.glow_rgb))

    def _animate(self):
        if not self.winfo_exists():
            return

        t = time.time()
        pulse = 0.5 + 0.5 * math.sin(t * 1.2 + self.phase)

        # Render a tiny 16x16 image and let PIL Bicubic sampling smooth it perfectly
        gw, gh = 16, 16
        img = Image.new("RGB", (gw, gh))
        px = img.load()
        for y in range(gh):
            ny = y / (gh - 1)
            for x in range(gw):
                nx = x / (gw - 1)
                px[x, y] = self._get_color_at(nx, ny, pulse)

        full_img = img.resize((max(1, self.w), max(1, self.h)), Image.Resampling.BICUBIC)
        self._photo = ImageTk.PhotoImage(full_img)
        self.itemconfig(self._img_id, image=self._photo)

        self.after(self.delay, self._animate)


class Widget(ctk.CTkFrame):
    """A single dashboard tile. Each widget type has its own build_* function."""

    CORNER_RADIUS = 0
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
            "Scenes": self.build_scenes
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


    def build_scenes(self):
        self.add_title("Scenes")

        # How the buttons are laid out depends on the tile size
        if self.size == "2x2":
            self.scenes_columns, self.scenes_rows, self.scenes_button_height = 2, 4, 44
        elif self.size == "2x1":
            self.scenes_columns, self.scenes_rows, self.scenes_button_height = 2, 2, 32
        else:                                            # 1x1
            self.scenes_columns, self.scenes_rows, self.scenes_button_height = 1, 2, 30

        self.scene_list = load_scenes()                  # read once, when the tile is built
        self.scenes_page_index = 0                       # which group of scenes is showing
        self.scene_widgets = []                          # the buttons currently on the tile

        # Only shown when the scenes don't all fit on one page
        self.scenes_page_button = ctk.CTkButton(
            self, text="", width=40, height=18, corner_radius=0, font=mono(9, True),
            text_color=self.fg, fg_color=blend(self.bg, self.fg, 0.2),
            hover_color=blend(self.bg, self.fg, 0.35), command=self.scenes_next_page)

        self._scenes_draw_page()

    def scenes_next_page(self):
        self.scenes_page_index += 1
        self._scenes_draw_page()

    def _scenes_draw_page(self):
        """Remove the old buttons and draw the ones for the current page."""
        for old_widget in self.scene_widgets:
            old_widget.destroy()
        self.scene_widgets = []

        scenes_per_page = self.scenes_columns * self.scenes_rows
        page_count = max(1, math.ceil(len(self.scene_list) / scenes_per_page))
        self.scenes_page_index %= page_count             # wrap back to the first page after the last
        first_scene = self.scenes_page_index * scenes_per_page
        visible_scenes = self.scene_list[first_scene:first_scene + scenes_per_page]

        if page_count > 1:
            self.scenes_page_button.configure(text=f"{self.scenes_page_index + 1}/{page_count}")
            self.scenes_page_button.place(relx=1.0, x=-self.TEXT_PAD_X, y=self.TEXT_PAD_Y, anchor="ne")
        else:
            self.scenes_page_button.place_forget()

        if not visible_scenes:
            empty_label = ctk.CTkLabel(self, text="No scenes in scenes.json", font=mono(10),
                                       text_color=blend(self.fg, self.bg, 0.35))
            empty_label.place(relx=0.5, rely=0.55, anchor="center")
            self.scene_widgets.append(empty_label)
            return

        if self.scenes_columns == 2:
            column_positions, button_width = (0.27, 0.73), 0.44     
        else:
            column_positions, button_width = (0.5,), 0.88          

        for position, scene in enumerate(visible_scenes):
            column = position % self.scenes_columns
            row = position // self.scenes_columns
            color = get_scene_color(scene)
            button = ctk.CTkButton(
                self, text=scene["name"], height=self.scenes_button_height, corner_radius=0,
                font=mono(10 if self.size == "1x1" else 11, True),
                text_color=blend(color, "#ffffff", 0.85), fg_color=color,
                hover_color=blend(color, "#ffffff", 0.18),
                command=lambda chosen_scene=scene: self._run_scene(chosen_scene))
            button.place(relx=column_positions[column],
                         y=46 + row * (self.scenes_button_height + 8),   
                         relwidth=button_width, anchor="n")
            self.scene_widgets.append(button)

    def _run_scene(self, scene):
        """Ask the main window (App) to run the scene."""
        app = self.winfo_toplevel()
        if hasattr(app, "run_scene"):
            app.run_scene(scene)
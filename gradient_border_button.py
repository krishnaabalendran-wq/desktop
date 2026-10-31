import math
import time

import customtkinter as ctk


class GradientBorderButton(ctk.CTkButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hovering = False
        self.configure(border_color="#ffffff")
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def on_enter(self, event):
        self.hovering = True
        self.animate_border()

    def on_leave(self, event):
        self.hovering = False
        self.configure(border_color="#ffffff")

    def animate_border(self):
        if not self.hovering:
            return
        t = time.time() * 4
        r = max(0, min(255, int(math.sin(t) * 50 + 145)))
        g = max(0, min(255, int(math.sin(t + 2) * 50 + 90)))
        b = max(0, min(255, int(math.sin(t + 4) * 50 + 210)))
        color = f"#{r:02x}{g:02x}{b:02x}"
        try:
            self.configure(border_color=color)
        except Exception:
            pass
        self.after(30, self.animate_border)
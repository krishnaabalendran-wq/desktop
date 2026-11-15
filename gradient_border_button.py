import math
import time

import customtkinter as ctk

from style import BORDER


class GradientBorderButton(ctk.CTkButton):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hovering = False
        self.configure(border_color=BORDER)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def on_enter(self, event):
        self.hovering = True
        self.animate_border()

    def on_leave(self, event):
        self.hovering = False
        self.configure(border_color=BORDER)

    def animate_border(self):
        if not self.hovering:
            return
        t = time.time() * 4
        v = max(0, min(255, int(math.sin(t) * 45 + 175)))
        color = f"#{v:02x}{v:02x}{v:02x}"
        try:
            self.configure(border_color=color)
        except Exception:
            pass
        self.after(30, self.animate_border)

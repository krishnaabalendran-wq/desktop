import customtkinter as ctk

from utils import blend


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
            "Volume": self.build_volume
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

    # ---------- callbacks ----------
    def on_volume_change(self, value):
        self.volume_label.configure(text=f"{int(value)}%")
        # Hook your real system volume control in here
import time

import customtkinter as ctk

from gradient_border_button import GradientBorderButton
from grid_manager import GridManager

DEFAULT_SIZE = "1x1"
DEFAULT_THEME = ("#22242a", "#ffffff")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Home Grid Dashboard")
        self.geometry("1000x600")
        self.configure(fg_color="#121212")

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. TOP BAR
        self.topbar_frame = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="#121212")
        self.topbar_frame.grid(row=0, column=0, sticky="ew")

        self.topbar_frame.grid_columnconfigure(0, weight=1)
        self.topbar_frame.grid_columnconfigure(1, weight=1)
        self.topbar_frame.grid_columnconfigure(2, weight=1)

        # Clock Text (Top Left)
        self.time_label = ctk.CTkLabel(self.topbar_frame, text="", font=("Arial", 22, "bold"), text_color="#ffffff")
        self.time_label.grid(row=0, column=0, sticky="w", padx=20, pady=15)
        self.update_clock()  # Start ticking

        # 2. MIDDLE DOTS NAVIGATION (Top Center)
        self.dots_container = ctk.CTkFrame(self.topbar_frame, fg_color="transparent")
        self.dots_container.grid(row=0, column=1, sticky="nsew", pady=15)

        self.title_label = ctk.CTkLabel(self.dots_container, text="Meetings", font=("Arial", 14, "bold"), text_color="#ffffff")
        self.title_label.pack(side="left", padx=(0, 10))

        self.dots = []
        for i in range(3):
            # Active dot is white, inactive is gray
            color = "#ffffff" if i == 0 else "#333333"
            dot = ctk.CTkButton(self.dots_container, text="", width=10, height=10, corner_radius=5,
                                fg_color=color, hover_color="#00b3cc",
                                command=lambda idx=i: self.on_dot_clicked(idx))
            dot.pack(side="left", padx=4)
            self.dots.append(dot)

        # 3. RIGHT-SIDE BUTTONS (Top Right): Settings sits to the left of Add
        self.right_buttons = ctk.CTkFrame(self.topbar_frame, fg_color="transparent")
        self.right_buttons.grid(row=0, column=2, sticky="e", padx=10, pady=14)

        self.add_button = GradientBorderButton(
            self.right_buttons,
            text="Add",
            width=110,
            height=32,
            fg_color="#1e1e1e",
            hover_color="#2b2b2b",
            corner_radius=16,
            border_width=2,
            command=self.toggle_main_menu
        )
        self.add_button.pack(side="right")

        self.settings_button = GradientBorderButton(
            self.right_buttons,
            text="Settings",
            width=110,
            height=32,
            fg_color="#1e1e1e",
            hover_color="#2b2b2b",
            corner_radius=16,
            border_width=2,
            command=self.toggle_settings_panel
        )
        self.settings_button.pack(side="right", padx=(0, 10))

        self.edit_button = GradientBorderButton(
            self.right_buttons,
            text="Edit",
            width=110,
            height=32,
            fg_color="#1e1e1e",
            hover_color="#2b2b2b",
            corner_radius=16,
            border_width=2,
            command=self.toggle_edit_mode)
        self.edit_button.pack(side="right", padx=(0, 10))

        # 4. GRID MANAGER (Body)
        self.grid_manager = GridManager(master=self, fg_color="transparent")
        self.grid_manager.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # Menu tracking states
        self.menu_is_open = False
        self.size_menu_is_open = False
        self.color_menu_is_open = False
        self.settings_is_open = False
        self.pending_widget_type = ""
        self.pending_size = ""

        self.create_widget_menus()
        self.bind("<Configure>", self.on_window_configure)

    def update_clock(self):
        current_time = time.strftime("%H:%M")
        self.time_label.configure(text=current_time)
        self.after(1000, self.update_clock)

    def on_dot_clicked(self, index):
        for i, dot in enumerate(self.dots):
            dot.configure(fg_color="#00e5ff" if i == index else "#333333")
        self.grid_manager.switch_page(index)

    def on_window_configure(self, event):
        if event.widget == self:
            self.grid_manager.on_configure()
            if self.settings_is_open:
                self.size_settings_panel()

    def create_widget_menus(self):
        # 1. Main Menu (Widget Types)
        self.popout_menu = ctk.CTkFrame(self, width=160, height=250, corner_radius=15, fg_color="#2b2b2b")
        self.popout_menu.grid_propagate(False)

        self.menu_scroll = ctk.CTkScrollableFrame(self.popout_menu, fg_color="transparent", width=140, height=230)
        self.menu_scroll.pack(padx=10, pady=10, fill="both", expand=True)

        widgets_to_add = ["Timer", "Volume", "Weather", "Notify"]
        sizes = ["1x1", "2x1", "2x2"]

        for w_type in widgets_to_add:
            btn = ctk.CTkButton(self.menu_scroll, text=w_type,
                    fg_color="#403D3D", hover_color="#504D4D")
            btn.pack(pady=5, fill="x")
            self.grid_manager.drag.attach_palette(
                btn, w_type, DEFAULT_SIZE, *DEFAULT_THEME,
                on_tap=lambda t=w_type: self.toggle_size_menu(t, sizes))
        self.grid_manager.drag.set_remove_zone(self.popout_menu)  # Drop a tile here to delete it

        # 2. Size Menu
        self.size_menu = ctk.CTkFrame(self, width=80, corner_radius=15, fg_color="#1e1e1e")
        self.size_menu.grid_propagate(False)

        # 3. Color Menu
        self.color_menu = ctk.CTkFrame(self, width=100, corner_radius=15, fg_color="#1a1a1a")
        self.color_menu.grid_propagate(False)

        # 4. Settings panel (right-hand sidebar, empty for now)
        self.settings_panel = ctk.CTkFrame(self, width=260, height=400, corner_radius=15, fg_color="#2b2b2b")
        self.settings_panel.pack_propagate(False)

        header = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 6))
        ctk.CTkLabel(header, text="Settings", font=("Arial", 18, "bold"),
                     text_color="#ffffff").pack(side="left")
        ctk.CTkButton(header, text="\u2715", width=28, height=28, corner_radius=14,
                      fg_color="#403D3D", hover_color="#504D4D",
                      command=self.hide_menus).pack(side="right")

    def show_add_menu(self):
        self.hide_menus()  # close the settings panel if it's open
        self.popout_menu.place(relx=1.0, rely=0.0, y=60, x=-20, anchor="ne")
        self.menu_is_open = True
        self.popout_menu.lift()

    def toggle_main_menu(self):
        if self.menu_is_open:
            self.hide_menus()
        else:
            self.show_add_menu()

    def toggle_edit_mode(self):
        editing = not self.grid_manager.drag.editing
        self.grid_manager.drag.set_editing(editing)
        self.edit_button.configure(text="Done" if editing else "Edit")
        if editing:
            self.show_add_menu()
        else:
            self.hide_menus()

    def toggle_settings_panel(self):
        if self.settings_is_open:
            self.hide_menus()
            return
        self.hide_menus()  # close the widget menus if they are open
        # Full-height sidebar on the right, under the top bar
        self.size_settings_panel()
        self.settings_panel.place(relx=1.0, rely=0.0, x=-10, y=65, anchor="ne")
        self.settings_panel.lift()
        self.settings_is_open = True

    def size_settings_panel(self):
        """Keep the sidebar the full window height (minus the top bar)."""
        self.settings_panel.configure(height=max(250, self.winfo_height() - 75))

    def toggle_size_menu(self, widget_type, sizes):
        self.color_menu.place_forget()
        self.color_menu_is_open = False

        if self.size_menu_is_open and self.pending_widget_type == widget_type:
            self.size_menu.place_forget()
            self.size_menu_is_open = False
        else:
            self.pending_widget_type = widget_type

            for widget in self.size_menu.winfo_children():
                widget.destroy()

            for size in sizes:
                btn = ctk.CTkButton(self.size_menu, text=size, width=60, fg_color="#403D3D", hover_color="#504D4D",
                                    command=lambda s=size: self.toggle_color_menu(s))
                btn.pack(pady=5, padx=10)

            menu_height = (len(sizes) * 40) + 10
            self.size_menu.configure(height=menu_height)

            self.size_menu.place(relx=0.98, rely=0.0, y=60, x=-190, anchor="ne")
            self.size_menu.lift()
            self.size_menu_is_open = True

    def toggle_color_menu(self, size):
        if self.color_menu_is_open and self.pending_size == size:
            self.color_menu.place_forget()
            self.color_menu_is_open = False
        else:
            self.pending_size = size
            for widget in self.color_menu.winfo_children():
                widget.destroy()

            # (Name, Background Color, Font Color)
            themes = [
                ("Slate", "#22242a", "#ffffff"),
                ("Crimson", "#3d262a", "#ff9999"),
                ("Amber", "#2b2216", "#ffcc80"),
                ("Sky", "#1e3a5f", "#87ceeb"),
                ("Obsidian", "#0b0b0d", "#a9a9b3"),
                ("Cobalt", "#00204a", "#4da8da"),
                ("Saffron", "#4a3000", "#ffc34d"),
                ("Viridian", "#0d3b36", "#66cdaa")
            ]

            for name, bg, fg in themes:
                btn = ctk.CTkButton(self.color_menu, text=name, width=80,
                                    fg_color=bg, text_color=fg, hover_color="#504D4D",
                                    command=lambda b=bg, f=fg: self.add_themed_widget(b, f))
                btn.pack(pady=5, padx=10)

            menu_height = (len(themes) * 40) + 10
            self.color_menu.configure(height=menu_height)

            # Place to the left of the size menu
            self.color_menu.place(relx=0.98, rely=0.0, y=60, x=-280, anchor="ne")
            self.color_menu.lift()
            self.color_menu_is_open = True

    def hide_menus(self):
        self.popout_menu.place_forget()
        self.size_menu.place_forget()
        self.color_menu.place_forget()
        self.settings_panel.place_forget()
        self.menu_is_open = False
        self.size_menu_is_open = False
        self.color_menu_is_open = False
        self.settings_is_open = False

    def add_themed_widget(self, bg_color, font_color):
        if self.pending_widget_type and self.pending_size:
            self.grid_manager.add_widget(self.pending_widget_type, self.pending_size, bg_color, font_color)
        self.hide_menus()
import time
import json
import os
import math
import customtkinter as ctk
from PIL import Image, ImageDraw

from gradient_border_button import GradientBorderButton
from grid_manager import GridManager
from utils import blend
from style import BG, SURFACE, SURFACE_ALT, BORDER, BORDER_HOVER, TEXT, DIM, BTN, BTN_HOVER, mono

DEFAULT_SIZE = "1x1"
DEFAULT_THEME = ("#171717", "#9a9a9a")   # Graphite

class BrandLogo(ctk.CTkFrame):
    """Recreates the CSS rotated square with gradient inner square."""
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        
        self.logo_img = ctk.CTkImage(
            light_image=self._generate_icon(), 
            dark_image=self._generate_icon(), 
            size=(38, 38)
        )
        
        self.icon_label = ctk.CTkLabel(self, text="", image=self.logo_img)
        self.icon_label.pack(side="left")
        
        self.text_label = ctk.CTkLabel(
            self, text="D E S K L Y", 
            font=("Arial", 13, "bold"), text_color=TEXT
        )
        self.text_label.pack(side="left", padx=(12, 2))

    def _generate_icon(self):
        inner = Image.new("RGBA", (9, 9))
        is_light = ctk.get_appearance_mode() == "Light"
        for y in range(9):
            for x in range(9):
                factor = (x + y) / 16.0
                v = int(120 - factor * 80) if is_light else int(255 - factor * 151)
                inner.putpixel((x, y), (v, v, v, 255))
                
        box = Image.new("RGBA", (27, 27), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box)
        outline_color = "#a0a0a0" if is_light else "#5b5b5b"
        box_draw.rectangle([0, 0, 26, 26], outline=outline_color, width=1)
        
        inner_rot = inner.rotate(45, resample=Image.Resampling.BICUBIC, expand=True)
        box_rot = box.rotate(45, resample=Image.Resampling.BICUBIC, expand=True)
        
        final = Image.new("RGBA", box_rot.size, (0, 0, 0, 0))
        final.alpha_composite(box_rot)
        
        fw, fh = final.size
        iw, ih = inner_rot.size
        final.paste(inner_rot, (fw // 2 - iw // 2, fh // 2 - ih // 2), inner_rot)
        return final


class SplashScreen(ctk.CTkToplevel):
    """Small, borderless floating window that pulses the logo while loading."""
    def __init__(self, master):
        super().__init__(master, fg_color=BG)
        self.overrideredirect(True)  # Remove window borders and title bar
        self.attributes("-topmost", True)
        
        # Center the small splash screen on the monitor
        width = 200
        height = 200
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        self.center_container = ctk.CTkFrame(self, fg_color="transparent")
        self.center_container.place(relx=0.5, rely=0.5, anchor="center")

        self.base_icon = self._generate_base_icon()
        self.base_size = 65 
        
        self.logo_img = ctk.CTkImage(
            light_image=self.base_icon,
            dark_image=self.base_icon,
            size=(self.base_size, self.base_size)
        )

        self.icon_label = ctk.CTkLabel(self.center_container, text="", image=self.logo_img)
        self.icon_label.pack(side="left")
        
        self.is_running = True
        self.start_time = time.time()
        self._animate()

    def _generate_base_icon(self):
        # 4x resolution for smooth animated scaling
        inner = Image.new("RGBA", (36, 36))
        is_light = ctk.get_appearance_mode() == "Light"
        for y in range(36):
            for x in range(36):
                factor = (x + y) / 64.0
                v = int(120 - factor * 80) if is_light else int(255 - factor * 151)
                inner.putpixel((x, y), (v, v, v, 255))
                
        box = Image.new("RGBA", (108, 108), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box)
        outline_color = "#a0a0a0" if is_light else "#5b5b5b"
        box_draw.rectangle([0, 0, 107, 107], outline=outline_color, width=4)
        
        inner_rot = inner.rotate(45, resample=Image.Resampling.BICUBIC, expand=True)
        box_rot = box.rotate(45, resample=Image.Resampling.BICUBIC, expand=True)
        
        final = Image.new("RGBA", box_rot.size, (0, 0, 0, 0))
        final.alpha_composite(box_rot)
        
        fw, fh = final.size
        iw, ih = inner_rot.size
        final.paste(inner_rot, (fw // 2 - iw // 2, fh // 2 - ih // 2), inner_rot)
        return final

    def _animate(self):
        if not self.is_running:
            return
        
        t = time.time() - self.start_time
        scale = 1.0 + 0.15 * math.sin(t * 4) 
        
        new_size = max(1, int(self.base_size * scale))
        self.logo_img.configure(size=(new_size, new_size))
        
        self.after(30, self._animate)
        
    def stop(self):
        self.is_running = False


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Hide the main window immediately so only the splash screen shows
        self.withdraw()
        
        self.title("Home Grid Dashboard")
        self.geometry("1000x600")
        self.configure(fg_color=BG)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. TOP BAR
        self.topbar_frame = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color=BG)
        self.topbar_frame.grid(row=0, column=0, sticky="ew")

        self.topbar_frame.grid_columnconfigure(0, weight=1)
        self.topbar_frame.grid_columnconfigure(1, weight=1)
        self.topbar_frame.grid_columnconfigure(2, weight=1)

        # Top Left (Logo + Clock)
        self.top_left_frame = ctk.CTkFrame(self.topbar_frame, fg_color="transparent")
        self.top_left_frame.grid(row=0, column=0, sticky="w", padx=20, pady=10)

        self.brand_logo = BrandLogo(self.top_left_frame)
        self.brand_logo.pack(side="left")

        self.time_label = ctk.CTkLabel(self.top_left_frame, text="", font=mono(12), text_color=DIM)
        self.time_label.pack(side="left", padx=(25, 0))
        self.update_clock() 

        # 2. MIDDLE DOTS NAVIGATION (Top Center)
        self.dots_container = ctk.CTkFrame(self.topbar_frame, fg_color="transparent")
        self.dots_container.grid(row=0, column=1, sticky="nsew", pady=15)

        self.title_label = ctk.CTkLabel(self.dots_container, text="MEETINGS", font=mono(11, True), text_color=DIM)
        self.title_label.pack(side="left", padx=(0, 10))

        self.dots = []
        for i in range(3):
            color = ("#111111", "#ffffff") if i == 0 else ("#d1d1d6", "#333333")
            dot = ctk.CTkButton(self.dots_container, text="", width=8, height=8, corner_radius=0,
                                fg_color=color, hover_color=BORDER_HOVER,
                                command=lambda idx=i: self.on_dot_clicked(idx))
            dot.pack(side="left", padx=4)
            self.dots.append(dot)

        # 3. RIGHT-SIDE BUTTONS (Top Right)
        self.right_buttons = ctk.CTkFrame(self.topbar_frame, fg_color="transparent")
        self.right_buttons.grid(row=0, column=2, sticky="e", padx=10, pady=14)

        self.add_button = GradientBorderButton(
            self.right_buttons,
            text="ADD",
            width=110,
            height=32,
            fg_color=SURFACE,
            hover_color=BTN_HOVER,
            corner_radius=0,
            border_width=1,
            font=mono(11, True),
            text_color=TEXT,
            command=self.toggle_main_menu
        )
        self.add_button.pack(side="right")

        self.settings_button = GradientBorderButton(
            self.right_buttons,
            text="SETTINGS",
            width=110,
            height=32,
            fg_color=SURFACE,
            hover_color=BTN_HOVER,
            corner_radius=0,
            border_width=1,
            font=mono(11, True),
            text_color=TEXT,
            command=self.toggle_settings_panel
        )
        self.settings_button.pack(side="right", padx=(0, 10))

        self.edit_button = GradientBorderButton(
            self.right_buttons,
            text="EDIT",
            width=110,
            height=32,
            fg_color=SURFACE,
            hover_color=BTN_HOVER,
            corner_radius=0,
            border_width=1,
            font=mono(11, True),
            text_color=TEXT,
            command=self.toggle_edit_mode)

        # 4. GRID MANAGER (Body)
        self.grid_manager = GridManager(master=self, fg_color="transparent")
        self.grid_manager.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        self.menu_is_open = False
        self.size_menu_is_open = False
        self.color_menu_is_open = False
        self.settings_is_open = False
        self.pending_widget_type = ""
        self.pending_size = ""

        self.create_widget_menus()
        self.grid_manager.drag.on_edit_request = self.toggle_edit_mode   # holding a tile turns on edit mode
        self.bind("<Configure>", self.on_window_configure)
        
        # Load saved widgets and settings silently in the background
        self.load_settings_and_layout()
        
        # 5. SPLASH SCREEN
        self.splash = SplashScreen(self)
        
        # Reveal the main window after 2.5 seconds
        self.after(2500, self.end_loading)

    def end_loading(self):
        self.splash.stop()
        self.splash.destroy()
        self.deiconify()  # Brings the fully loaded main window onto the screen

    # --- SAVE / LOAD MECHANISM ---
    def save_layout_and_settings(self):
        layout = []
        if hasattr(self, 'grid_manager'):
            for w, item in self.grid_manager.tiles.items():
                layout.append({
                    "type": w.widget_type,
                    "size": w.size,
                    "bg": w.bg,
                    "fg": w.fg,
                    "page": item["page_idx"],
                    "r": item["row"],
                    "c": item["col"]
                })
            with open("layout.json", "w") as f:
                json.dump(layout, f)
                
        settings = {"appearance": self.mode_switch.get() if hasattr(self, "mode_switch") else "Dark"}
        with open("settings.json", "w") as f:
            json.dump(settings, f)

    def load_settings_and_layout(self):
        try:
            if os.path.exists("settings.json"):
                with open("settings.json", "r") as f:
                    settings = json.load(f)
                    mode = settings.get("appearance", "Dark")
                    ctk.set_appearance_mode(mode)
                    if hasattr(self, "mode_switch"):
                        self.mode_switch.set(mode)
            else:
                ctk.set_appearance_mode("Dark")
        except Exception as e:
            print("Settings load error:", e)
            
        if not os.path.exists("layout.json"):
            return
            
        try:
            with open("layout.json", "r") as f:
                layout = json.load(f)
            for item in layout:
                self.grid_manager.current_page_idx = item.get("page", 0)
                self.grid_manager.add_widget(
                    item["type"], item["size"], item["bg"], item["fg"], 
                    at=(item["r"], item["c"])
                )
            self.grid_manager.switch_page(0, animate=False)
        except Exception as e:
            print("Layout load error:", e)

    def on_closing(self):
        self.save_layout_and_settings()
        self.destroy()

    # --- STANDARD LOGIC ---
    def update_clock(self):
        current_time = time.strftime("%H:%M")
        self.time_label.configure(text=current_time)
        self.after(1000, self.update_clock)

    def on_dot_clicked(self, index, animate=True):
        for i, dot in enumerate(self.dots):
            color = ("#111111", "#ffffff") if i == index else ("#d1d1d6", "#333333")
            dot.configure(fg_color=color)
        self.grid_manager.switch_page(index, animate=animate)

    def on_window_configure(self, event):
        if event.widget == self:
            self.grid_manager.on_configure()
            if self.settings_is_open:
                self.size_settings_panel()

    def create_widget_menus(self):
        self.popout_menu = ctk.CTkFrame(self, width=160, height=250, corner_radius=0, fg_color=SURFACE,
                                        border_width=1, border_color=BORDER)
        self.popout_menu.grid_propagate(False)

        self.menu_scroll = ctk.CTkScrollableFrame(self.popout_menu, fg_color="transparent", width=140, height=230,
                                                corner_radius=0, scrollbar_button_color=BORDER,
                                                scrollbar_button_hover_color=BORDER_HOVER)
        self.menu_scroll.pack(padx=10, pady=10, fill="both", expand=True)

        widgets_to_add = ["Timer", "Volume", "Weather", "Notify", "System", "Date"]
        sizes = ["1x1", "2x1", "2x2"]

        for w_type in widgets_to_add:
            btn = ctk.CTkButton(self.menu_scroll, text=w_type.upper(), font=mono(11, True),
                    corner_radius=0, border_width=1, border_color=BORDER,
                    text_color=TEXT, fg_color=BTN, hover_color=BTN_HOVER)
            btn.pack(pady=5, fill="x")
            self.grid_manager.drag.attach_palette(
                btn, w_type, DEFAULT_SIZE, *DEFAULT_THEME,
                on_tap=lambda t=w_type: self.toggle_size_menu(t, sizes))
        self.grid_manager.drag.set_remove_zone(self.popout_menu)

        self.size_menu = ctk.CTkFrame(self, width=80, corner_radius=0, fg_color=SURFACE,
                                      border_width=1, border_color=BORDER)
        self.size_menu.grid_propagate(False)

        self.color_menu = ctk.CTkFrame(self, width=110, corner_radius=0, fg_color=SURFACE,
                                       border_width=1, border_color=BORDER)
        self.color_menu.grid_propagate(False)

        self.settings_panel = ctk.CTkFrame(self, width=260, height=400, corner_radius=0, fg_color=SURFACE,
                                           border_width=1, border_color=BORDER)
        self.settings_panel.pack_propagate(False)

        header = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 6))
        ctk.CTkLabel(header, text="SETTINGS", font=mono(14, True),
                     text_color=TEXT).pack(side="left")
        ctk.CTkButton(header, text="\u2715", width=28, height=28, corner_radius=0,
                      border_width=1, border_color=BORDER, text_color=TEXT,
                      fg_color=BTN, hover_color=BTN_HOVER,
                      command=self.hide_menus).pack(side="right")
                      
        # --- SETTINGS MODE TOGGLE ---
        settings_body = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        settings_body.pack(fill="both", expand=True, padx=15, pady=10)
        
        mode_label = ctk.CTkLabel(settings_body, text="APPEARANCE", font=mono(11, True), text_color=DIM)
        mode_label.pack(anchor="w", pady=(10, 5))
        
        self.mode_switch = ctk.CTkSegmentedButton(
            settings_body, 
            values=["Dark", "Light"],
            command=self.change_appearance_mode,
            font=mono(11, True),
            fg_color=BG,
            selected_color=BORDER_HOVER,
            unselected_color=SURFACE,
            selected_hover_color=BORDER
        )
        self.mode_switch.set("Dark")
        self.mode_switch.pack(fill="x")

    def change_appearance_mode(self, new_mode: str):
        """Switches the CustomTkinter theme between Light and Dark."""
        ctk.set_appearance_mode(new_mode)
        
        # Redraw brand logo when theme changes
        if hasattr(self, 'brand_logo'):
            self.brand_logo.logo_img.configure(
                light_image=self.brand_logo._generate_icon(),
                dark_image=self.brand_logo._generate_icon()
            )

    def show_add_menu(self):
        self.hide_menus()
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
        self.edit_button.configure(text="DONE" if editing else "EDIT")
        if editing:
            self.edit_button.configure(text="DONE")
            self.edit_button.pack(side="right", padx=(0, 10))
            self.hide_menus()
        else:
            self.edit_button.pack_forget()
            self.hide_menus()

    def toggle_settings_panel(self):
        if self.settings_is_open:
            self.hide_menus()
            return
        self.hide_menus()
        self.size_settings_panel()
        self.settings_panel.place(relx=1.0, rely=0.0, x=-10, y=65, anchor="ne")
        self.settings_panel.lift()
        self.settings_is_open = True

    def size_settings_panel(self):
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
                btn = ctk.CTkButton(self.size_menu, text=size.upper(), width=60, font=mono(11, True),
                                    corner_radius=0, border_width=1, border_color=BORDER,
                                    text_color=TEXT, fg_color=BTN, hover_color=BTN_HOVER,
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
                btn = ctk.CTkButton(self.color_menu, text=name.upper(), width=90, font=mono(11, True),
                                    corner_radius=0, border_width=1, border_color=BORDER,
                                    fg_color=bg, text_color=fg, hover_color=blend(bg, fg, 0.2),
                                    command=lambda b=bg, f=fg: self.add_themed_widget(b, f))
                btn.pack(pady=5, padx=10)

            menu_height = (len(themes) * 40) + 10
            self.color_menu.configure(height=menu_height)

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

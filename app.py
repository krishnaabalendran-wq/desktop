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
from actions import SceneContext
from scene_runner import SceneRunner
from automation_overlay import AutomationOverlay
from layouts import load_presets, save_preset, delete_preset, find_preset
from scenes import SCENES_FILE, load_scenes
from context import get_frontmost_app, get_idle_seconds
from triggers import TriggerEngine
from history import History, day_key, day_recap, recap_lines

DEFAULT_SIZE = "1x1"
DEFAULT_THEME = ("#171717", "#9a9a9a")   # Graphite
TRIGGER_CHECK_MS = 2000                  # how often the deck looks at the front app, idle time and the clock 
DEBUG_TRIGGERS = True                    # prints why suggestions do or don't appear (set False when done)
ACTIVE_IDLE_LIMIT_SECONDS = 120          # app time only counts if the computer was used in the last 2 minutes
SETTINGS_SIZE = (300, 560)               # width, height of the Settings window


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
            corner_radius=12,
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
            corner_radius=12,
            border_width=1,
            font=mono(11, True),
            text_color=TEXT,
            command=self.toggle_settings_panel
        )
        self.settings_button.pack(side="right", padx=(0, 10))

        # Only packed while jiggly edit mode is active
        self.edit_button = GradientBorderButton(
            self.right_buttons,
            text="DONE",
            width=110,
            height=32,
            fg_color=SURFACE,
            hover_color=BTN_HOVER,
            corner_radius=12,
            border_width=1,
            font=mono(11, True),
            text_color=TEXT,
            command=self.toggle_edit_mode
        )

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
        
        self.automation_overlay = AutomationOverlay(self)
        self.automation_overlay.covered = [self.topbar_frame, self.grid_manager]
        self.scene_runner = SceneRunner(context=SceneContext(), schedule=self.after, cancel_schedule=self.after_cancel, on_change=self.automation_overlay.refresh, on_finished=self.on_scene_finished, apply_layout=self.apply_layout_preset)
        
        self.history = History()
        self.trigger_engine = TriggerEngine()
        self._scenes_modified_time = -1.0        # so scenes.json is read the first time and again whenever it changes
        self.after(5000, self.check_triggers)

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
        # CTkToplevel windows can re-appear shortly after startup even though they were hidden,
        # so make sure settings starts closed (once now, once after customtkinter's own delayed setup).

    # --- SAVE / LOAD MECHANISM ---
    def save_layout_and_settings(self):
        layout = []
        if hasattr(self, 'grid_manager'):
            layout = self.grid_manager.snapshot()
            with open("layout.json", "w") as f:
                json.dump(layout, f)
                
        settings = {
            "appearance": self.mode_switch.get() if hasattr(self, "mode_switch") else "Dark",
            "suggestions_enabled": bool(self.suggestions_switch.get()) if hasattr(self, "suggestions_switch") else True,
            "app_awareness": bool(self.app_awareness_switch.get()) if hasattr(self, "app_awareness_switch") else False,
        }
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
                    if hasattr(self, "suggestions_switch"):
                        if settings.get("suggestions_enabled", True):
                            self.suggestions_switch.select()
                        else:
                            self.suggestions_switch.deselect()
                        if settings.get("app_awareness", False):
                            self.app_awareness_switch.select()
                        else:
                            self.app_awareness_switch.deselect()
            else:
                ctk.set_appearance_mode("Dark")
        except Exception as e:
            print("Settings load error:", e)
            
        if not os.path.exists("layout.json"):
            return
            
        try:
            with open("layout.json", "r") as f:
                layout = json.load(f)
            self.grid_manager.apply_snapshot(layout)
            self.grid_manager.switch_page(0, animate=False)
        except Exception as e:
            print("Layout load error:", e)

    def on_closing(self):
        self.save_layout_and_settings()
        if hasattr(self, "history"):
            self.history.flush()                     # save any app time not yet written to disk
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

    def create_widget_menus(self):
        self.popout_menu = ctk.CTkFrame(self, width=160, height=250, corner_radius=0, fg_color=SURFACE,
                                        border_width=1, border_color=BORDER)
        self.popout_menu.grid_propagate(False)

        self.menu_scroll = ctk.CTkScrollableFrame(self.popout_menu, fg_color="transparent", width=140, height=230,
                                                corner_radius=0, scrollbar_button_color=BORDER,
                                                scrollbar_button_hover_color=BORDER_HOVER)
        self.menu_scroll.pack(padx=10, pady=10, fill="both", expand=True)

        widgets_to_add = ["Timer", "Volume", "Weather", "Notify", "System", "Date", "Scenes", "voiceassistant"]
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

        self.settings_window = ctk.CTkToplevel(self, fg_color=SURFACE)
        self.settings_window.title("Settings")
        self.settings_window.geometry(f"{SETTINGS_SIZE[0]}x{SETTINGS_SIZE[1]}")
        self.settings_window.minsize(260, 320)
        self.settings_window.transient(self)
        self.settings_window.withdraw()
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_settings)

        settings_body = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        settings_body.pack(fill="both", expand=True, padx=15, pady=15)
        
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

        # --- SUGGESTIONS ---
        ctk.CTkLabel(settings_body, text="SUGGESTIONS", font=mono(11, True), text_color=DIM).pack(anchor="w", pady=(20, 5))
        self.suggestions_switch = ctk.CTkSwitch(settings_body, text="SUGGEST SCENES", font=mono(11, True), text_color=TEXT)
        self.suggestions_switch.select()                     # on by default
        self.suggestions_switch.pack(anchor="w", pady=(0, 6))
        self.app_awareness_switch = ctk.CTkSwitch(settings_body, text="APP AWARENESS", font=mono(11, True), text_color=TEXT)
        self.app_awareness_switch.pack(anchor="w")           # off until you turn it on
        ctk.CTkLabel(settings_body, text="Reads only the NAME of the app in front. Used for app triggers and the recap.",
                     font=mono(10), text_color=DIM, anchor="w", justify="left", wraplength=210).pack(anchor="w", pady=(2, 8))
        ctk.CTkButton(settings_body, text="TODAY'S RECAP", command=self.show_recap, height=28, corner_radius=0,
                      border_width=1, border_color=BORDER, font=mono(11, True), text_color=TEXT,
                      fg_color=BTN, hover_color=BTN_HOVER).pack(fill="x")

        ctk.CTkLabel(settings_body, text="LAYOUT PRESETS", font=mono(11, True), text_color=DIM).pack(anchor="w", pady=(20, 5))
        save_row = ctk.CTkFrame(settings_body, fg_color="transparent")
        save_row.pack(fill="x")
        self.preset_name_entry = ctk.CTkEntry(
            save_row, placeholder_text="Name", height=30, corner_radius=0,
            border_width=1, border_color=BORDER, font=mono(11), fg_color=BG, text_color=TEXT
        )
        self.preset_name_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            save_row, text="SAVE", width=60, height=30, corner_radius=0, border_width=1,
            border_color=BORDER, font=mono(11, True), text_color=TEXT, fg_color=BTN, hover_color=BTN_HOVER,
            command=self.save_current_as_preset
        ).pack(side="left", padx=(6, 0))
        self.preset_status = ctk.CTkLabel(
            settings_body, text="", font=mono(10), text_color=DIM,
            anchor="w", justify="left", wraplength=210
        )
        self.preset_status.pack(anchor="w", pady=(4, 4))
        self.preset_list = ctk.CTkScrollableFrame(settings_body, fg_color="transparent", corner_radius=0)
        self.preset_list.pack(fill="both", expand=True)
        self.refresh_preset_list()

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
        if editing:
            self.edit_button.configure(text="DONE")
            self.edit_button.pack(side="right", padx=(0, 10))
            self.hide_menus()
        else:
            self.edit_button.pack_forget()
            self.hide_menus()

    def toggle_settings_panel(self):
        if self.settings_window.winfo_viewable():
            self.close_settings()
        else:
            self.open_settings()

    def open_settings(self):
        self.hide_menus()
        width, height = SETTINGS_SIZE
        x = self.winfo_rootx() + self.winfo_width() - width - 10
        y = self.winfo_rooty() + 65
        self.settings_window.geometry(f"{width}x{height}+{x}+{y}")
        self.settings_window.deiconify()
        self.refresh_preset_list()               # rebuild now that the window is visible
        self.settings_window.lift()
        self.settings_window.focus_force()

    def close_settings(self):
        self.settings_window.withdraw()

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
        self.menu_is_open = False
        self.size_menu_is_open = False
        self.color_menu_is_open = False

    def add_themed_widget(self, bg_color, font_color):
        if self.pending_widget_type and self.pending_size:
            self.grid_manager.add_widget(self.pending_widget_type, self.pending_size, bg_color, font_color)
        self.hide_menus()

    def save_current_as_preset(self):
        name = self.preset_name_entry.get().strip()
        if not name:
            self.preset_status.configure(text="Type a name first.")
            return
        widgets = self.grid_manager.snapshot()
        try:
            replaced = save_preset(name, widgets)
        except OSError as error:
            self.preset_status.configure(text=f"Could not save: {error}")
            return
        self.preset_name_entry.delete(0, "end")
        self.preset_status.configure(text=f"{'Updated' if replaced else 'Saved'} '{name}' ({len(widgets)} widgets)")
        self.refresh_preset_list()

    def refresh_preset_list(self):
        for child in self.preset_list.winfo_children():
            child.destroy()
        presets = load_presets()
        if not presets:
            ctk.CTkLabel(self.preset_list, text="No presets yet", font=mono(10), text_color=DIM).pack(anchor="w")
        for preset in presets:
            row = ctk.CTkFrame(self.preset_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkButton(
                row, text="\u2715", width=26, height=26, corner_radius=0, border_width=1,
                border_color=BORDER, text_color=TEXT, fg_color=BTN, hover_color=BTN_HOVER,
                command=lambda pid=preset["id"]: self.delete_layout_preset(pid)
            ).pack(side="right")
            ctk.CTkButton(
                row, text="APPLY", width=52, height=26, corner_radius=0, border_width=1,
                border_color=BORDER, font=mono(10, True), text_color=TEXT, fg_color=BTN,
                hover_color=BTN_HOVER,
                command=lambda pid=preset["id"]: self.apply_layout_preset(pid)
            ).pack(side="right", padx=(0, 4))
            ctk.CTkLabel(row, text=preset["name"], font=mono(11), text_color=TEXT,
                         anchor="w").pack(side="left", fill="x", expand=True)

    def delete_layout_preset(self, preset_id):
        try:
            delete_preset(preset_id)
        except OSError as error:
            self.preset_status.configure(text=f"Could not delete: {error}")
        self.refresh_preset_list()

    def apply_layout_preset(self, reference):
        """Replace the whole layout with a saved preset (by id or name)."""
        preset = find_preset(load_presets(), reference)
        if preset is None:
            raise LookupError(f"no layout named '{reference}'")
        if self.grid_manager.drag.editing:
            self.toggle_edit_mode()
        self.hide_menus()
        self.close_settings()
        return self.grid_manager.apply_snapshot(preset["widgets"])

    def run_scene(self, scene):
        """Run a scene."""
        if self.scene_runner.is_running:
            return                                   # one scene at a time
        self.hide_menus()    
        self.close_settings()                        # close any open menus first
        self.grid_manager.drag.cancel()              # drop any drag in progress
        self.automation_overlay.show(self.scene_runner)
        self.scene_runner.start(scene)

    def on_scene_finished(self, summary):
        """Called when a scene ends, whether it finished or was stopped."""
        self.last_scene_summary = summary
        self.history.log_scene_run(summary)              # feeds the recap 
        self.automation_overlay.lift()
        scene = self.scene_runner.scene or {}
        if scene.get("show_recap") and summary["outcome"] == "completed":
            self.after(1500, self.show_recap)            # let the DONE panel be seen first

    # --- SUGGESTIONS AND RECAP ---

    def check_triggers(self):
        """Runs every TRIGGER_CHECK_MS: look at the front app, idle time and clock, and suggest a scene if one is due."""
        try:
            self._run_trigger_check()
        except Exception as error:                       # a problem here must never stop the loop or the app
            print("trigger check failed:", error)
        finally:
            self.after(TRIGGER_CHECK_MS, self.check_triggers)

    def _bring_to_front(self):
        """Suggestions are drawn inside this window, so make sure it is actually in front of other apps."""
        try:
            if self.state() == "iconic":
                self.deiconify()
            self.lift()
            self.attributes("-topmost", True)                          # jump above other windows...
            self.after(400, lambda: self.attributes("-topmost", False))  # ...then stop forcing it to stay there
            self.focus_force()
        except Exception as error:
            print("could not bring the window to the front:", error)

    def _debug(self, text):
        """Print a trigger status line, but only when it changes (so the terminal doesn't fill up)."""
        if DEBUG_TRIGGERS and text != getattr(self, "_last_debug", None):
            self._last_debug = text
            print("[triggers]", text)

    def _run_trigger_check(self):
        if not self.winfo_viewable():                    # the splash screen is still up
            self._debug("waiting: main window not visible yet")
            return
        now = time.time()
        self._refresh_trigger_scenes(now)
        self.history.flush_if_due()

        app_awareness_on = bool(self.app_awareness_switch.get())
        front_app = get_frontmost_app() if app_awareness_on else None   # the app NAME only
        idle_seconds = get_idle_seconds()

        # Time per app for the daily recap, counted only while the computer is actually being used
        if front_app and (idle_seconds is None or idle_seconds < ACTIVE_IDLE_LIMIT_SECONDS):
            self.history.add_app_seconds(front_app, TRIGGER_CHECK_MS / 1000, now)

        if not self.suggestions_switch.get():
            self._debug("blocked: SUGGEST SCENES is switched off in Settings")
            return
        if self.scene_runner.is_running or self.automation_overlay.is_showing:
            self._debug(f"blocked: scene running={self.scene_runner.is_running}, panel showing={self.automation_overlay.is_showing}")
            return                                       # one thing on screen at a time
        if self.grid_manager.drag.editing:
            self._debug("blocked: edit mode is on")
            return
        self._debug(f"watching: front app={front_app!r}, APP AWARENESS={'on' if app_awareness_on else 'OFF'}, "
                    f"idle time readable={idle_seconds is not None}")
        suggestion = self.trigger_engine.check(now, front_app, idle_seconds)
        if suggestion is not None:
            self._debug(f"SUGGESTING {suggestion['scene'].get('name')}: {suggestion['reason']}")
            self._bring_to_front()
            self.hide_menus()
            self.close_settings()
            self.grid_manager.drag.cancel()
            self.automation_overlay.show_suggestion(suggestion, self._suggestion_run, self._suggestion_dismissed)

    def _refresh_trigger_scenes(self, now):
        """Keep the trigger engine's scenes current: re-read scenes.json when it changes."""
        try:
            modified_time = os.path.getmtime(SCENES_FILE)
        except OSError:
            modified_time = None
        scenes_changed = modified_time != self._scenes_modified_time
        if scenes_changed:
            self._scenes_modified_time = modified_time
            self.trigger_engine.set_scenes(load_scenes())
            if DEBUG_TRIGGERS:
                counts = ", ".join(f"{s.get('name')}={len(s.get('triggers') or [])}" for s in self.trigger_engine.scenes)
                print(f"[triggers] scenes read: {len(self.trigger_engine.scenes)} scenes, triggers per scene: {counts}")

    def _suggestion_run(self, suggestion):
        """RUN was pressed on a suggestion."""
        self.run_scene(suggestion["scene"])

    def _suggestion_dismissed(self, suggestion, mute_today):
        """NOT NOW, NOT TODAY, or the suggestion timed out."""
        self.trigger_engine.dismissed(suggestion, mute_today)

    def show_recap(self):
        """Show today's recap: scenes run, and time per kind of app."""
        if self.scene_runner.is_running:
            return
        self.close_settings()
        self.hide_menus()
        self.grid_manager.drag.cancel()
        recap = day_recap(self.history, day_key(time.time()))
        lines = recap_lines(recap, bool(self.app_awareness_switch.get()))
        self.automation_overlay.show_recap("TODAY", lines)
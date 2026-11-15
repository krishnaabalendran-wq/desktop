"""Shared look for the dashboard: sharp corners, thin borders, monospace caps."""
import tkinter.font as tkfont

# Format: ("Light Mode Hex", "Dark Mode Hex")
BG = ("#f5f5f7", "#121212")          
SURFACE = ("#ffffff", "#171717")     
SURFACE_ALT = ("#ebebf0", "#1c1c1c")
BORDER = ("#d1d1d6", "#2a2a2a")      
BORDER_HOVER = ("#aeb1b6", "#4a4a4a")
TEXT = ("#111111", "#e8e8e8")
DIM = ("#8e8e93", "#8a8a8a")
BTN = ("#ffffff", "#1c1c1c")
BTN_HOVER = ("#e5e5ea", "#2a2a2a")

_MONO_FAMILY = None

def mono(size=11, bold=False):
    """Monospace font tuple. The family is picked once, after the Tk root exists."""
    global _MONO_FAMILY
    if _MONO_FAMILY is None:
        available = set(tkfont.families())
        for name in ("Menlo", "SF Mono", "Consolas", "DejaVu Sans Mono",
                     "Liberation Mono", "Courier New"):
            if name in available:
                _MONO_FAMILY = name
                break
        else:
            _MONO_FAMILY = "Courier"
    return (_MONO_FAMILY, size, "bold" if bold else "normal")

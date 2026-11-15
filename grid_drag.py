import time
import math
import tkinter as tk
import customtkinter as ctk


def inside(w, x, y):
    """True if screen point (x, y) is over widget w."""
    if not w.winfo_ismapped():
        return False
    return (w.winfo_rootx() <= x < w.winfo_rootx() + w.winfo_width()
            and w.winfo_rooty() <= y < w.winfo_rooty() + w.winfo_height())


def find_widget(widget, table):
    """Walk up from the clicked widget until one is in table."""
    while widget is not None:
        if widget in table:
            return table[widget]
        widget = getattr(widget, "master", None)
    return None


class Outline:
    """Green/red pulsing rectangle made of 4 bars."""

    def __init__(self, parent):
        self.bars = [ctk.CTkFrame(parent, corner_radius=0) for _ in range(4)]
        self.is_visible = False
        self.is_valid = True
        self._animate()

    def show(self, x, y, width, height, valid, s=1.0, t=3):
        # x, y = screen pixels. width, height, t = CTk units. s = display scale.
        top, bottom, left, right = self.bars
        pw, ph, pt = int(width * s), int(height * s), int(t * s)
        self.is_valid = valid
        self.is_visible = True

        top.configure(width=width, height=t)
        bottom.configure(width=width, height=t)
        left.configure(width=t, height=height)
        right.configure(width=t, height=height)

        # tk's own place() so CTk doesn't scale x, y a second time
        tk.Place.place_configure(top, x=x, y=y)
        tk.Place.place_configure(bottom, x=x, y=y + ph - pt)
        tk.Place.place_configure(left, x=x, y=y)
        tk.Place.place_configure(right, x=x + pw - pt, y=y)
        for bar in self.bars:
            bar.lift()

    def hide(self):
        self.is_visible = False
        for bar in self.bars:
            bar.place_forget()

    def _animate(self):
        # Pulse the color while visible
        if self.is_visible:
            v = max(0, min(255, int(math.sin(time.time() * 6) * 75 + 180)))
            color = f"#00{v:02x}00" if self.is_valid else f"#{v:02x}0000"
            for bar in self.bars:
                try:
                    bar.configure(fg_color=color)
                except Exception:
                    pass
        self.bars[0].after(30, self._animate)


class GridDragger:
    """Drag and drop for a GridManager (palette -> grid, move/swap tiles, remove zone)."""

    DRAG_THRESHOLD = 8  # px of movement before a press becomes a drag

    def __init__(self, grid):
        self.grid = grid
        self.editing = False
        self._palette = {}
        self._remove_zone = None
        self._src = None
        self._origin = (0, 0)
        self._grab = (0, 0)         # where inside the tile you grabbed it (screen px)
        self._size = (1, 1)
        self._dragging = False

        self._top = grid.winfo_toplevel()

        # The ghost is its own small window. A widget moved with place()
        # leaves trails on Windows, a separate window doesn't.
        self._ghost = tk.Toplevel(self._top)
        self._ghost.withdraw()
        self._ghost.overrideredirect(True)
        self._ghost.attributes("-topmost", True)
        self._ghost.attributes("-alpha", 0.85)
        self._ghost_label = tk.Label(self._ghost, bg="#1f6aa5", fg="#ffffff",
                                     font=("Arial", 12))
        self._ghost_label.pack(fill="both", expand=True)
        self._ghost_px = (0, 0)
        self._last_move = 0.0
        self._outline = Outline(grid)
        self._last_outline = None

        self._top.bind("<ButtonPress-1>", self._on_press, add="+")
        self._top.bind("<B1-Motion>", self._on_motion, add="+")
        self._top.bind("<ButtonRelease-1>", self._on_release, add="+")

    def set_editing(self, on):
        self.editing = on
        if not on:
            self.cancel()

    def attach_palette(self, widget, widget_type, size="1x1", backgnd="#22242a",
                       font_color="#ffffff", on_tap=None):
        self._palette[widget] = {"type": widget_type, "size": size, "bg": backgnd,
                                 "fg": font_color, "on_tap": on_tap}

    def set_remove_zone(self, widget):
        self._remove_zone = widget

    def cancel(self):
        self._src = None
        self._dragging = False
        self._ghost.withdraw()
        self._outline.hide()
        self._last_outline = None

    def _on_press(self, e):
        self._src = None
        self._dragging = False
        self._origin = (e.x_root, e.y_root)
        g = self.grid

        spec = find_widget(e.widget, self._palette)
        if spec is not None:
            cols, rows = map(int, spec["size"].split("x"))
            width, height = g.tile_size(cols, rows)
            s = g._get_widget_scaling()
            self._src = ("new", spec)
            self._size = (cols, rows)
            self._grab = (int(width * s) // 2, int(height * s) // 2)  # CTk units -> screen px
            return

        if not self.editing:
            return
        item = find_widget(e.widget, g.tiles)
        if item is not None and item["page_idx"] == g.current_page_idx:
            tile = item["widget"]
            self._src = ("move", item)
            self._grab = (e.x_root - tile.winfo_rootx(), e.y_root - tile.winfo_rooty())
            self._size = (item["cols"], item["rows"])

    def _on_motion(self, e):
        if self._src is None:
            return
        if not self._dragging:
            moved = abs(e.x_root - self._origin[0]) + abs(e.y_root - self._origin[1])
            if moved < self.DRAG_THRESHOLD:
                return
            self._dragging = True
            width, height = self.grid.tile_size(*self._size)
            s = self.grid._get_widget_scaling()
            self._ghost_px = (int(width * s), int(height * s))
            self._ghost_label.configure(text=self._src[1]["type"])
            self._ghost.deiconify()

        # Limit to ~60 updates a second so fast mouse moves don't pile up
        now = time.time()
        if now - self._last_move < 0.016:
            return
        self._last_move = now

        self._ghost.geometry(
            f"{self._ghost_px[0]}x{self._ghost_px[1]}"
            f"+{e.x_root - self._grab[0]}+{e.y_root - self._grab[1]}")
        self._show_outline(self._hit(e))

    def _on_release(self, e):
        if self._src is None:
            return
        kind, src = self._src
        was_dragging = self._dragging
        hit = self._hit(e) if was_dragging else None
        plan = self._plan(hit[1], hit[2]) if hit and hit[0] == "grid" else None
        self.cancel()

        if not was_dragging:
            if kind == "new" and src.get("on_tap"):
                src["on_tap"]()
            return
        if hit is None:
            return

        g = self.grid
        if hit[0] == "remove":
            g.remove_widget(src)
        elif plan is not None:
            _, r, c = hit
            action, other = plan
            if kind == "move":
                if action == "swap":
                    g.swap_widgets(src, other)
                else:
                    g.move_widget(src, r, c)
            else:
                if action == "replace":
                    g.remove_widget(other)
                g.add_widget(src["type"], src["size"], src["bg"], src["fg"], at=(r, c))

    def _hit(self, e):
        if self._remove_zone is not None and inside(self._remove_zone, e.x_root, e.y_root):
            return ("remove",) if self._src[0] == "move" else None
        if inside(self.grid, e.x_root, e.y_root):
            r, c = self._nearest_cell(e.x_root - self._grab[0], e.y_root - self._grab[1])
            return ("grid", r, c)
        return None

    def _nearest_cell(self, left, top):
        g = self.grid
        cols, rows = self._size
        best, best_d = (0, 0), None
        for r in range(g.MAX_ROWS - rows + 1):
            for c in range(g.MAX_COLS - cols + 1):
                x, y = g.cell_origin(r, c)
                d = (x - left) ** 2 + (y - top) ** 2
                if best_d is None or d < best_d:
                    best, best_d = (r, c), d
        return best

    def _plan(self, r, c):
        g = self.grid
        kind, src = self._src
        cols, rows = self._size
        mine = (src,) if kind == "move" else ()
        hits = g.items_overlapping(g.current_page_idx, r, c, cols, rows, ignore=mine)

        if not hits:
            return ("place", None)
        other = hits[0]
        if (len(hits) == 1 and (other["row"], other["col"]) == (r, c)
                and (other["cols"], other["rows"]) == (cols, rows)):
            return ("swap" if kind == "move" else "replace", other)
        return None

    def _show_outline(self, hit):
        if hit is None or hit[0] != "grid":
            self._outline.hide()
            self._last_outline = None
            return
        g = self.grid
        s = g._get_widget_scaling()
        _, r, c = hit
        valid = self._plan(r, c) is not None
        if self._last_outline == (r, c, valid):   # nothing changed, skip redraw
            return
        self._last_outline = (r, c, valid)

        ox, oy = g.cell_origin(r, c)
        pad = int((g.PADDING // 2) * s)           # tile padding in screen px
        x = ox - g.winfo_rootx() + pad
        y = oy - g.winfo_rooty() + pad
        width, height = g.tile_size(*self._size)
        self._outline.show(x, y, width, height, valid, s=s)
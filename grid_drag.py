import customtkinter as ctk

from widget import Widget


def inside(w, x, y):
    """True if screen point (x, y) is over widget w (and w is visible)."""
    if not w.winfo_ismapped():
        return False
    return (w.winfo_rootx() <= x < w.winfo_rootx() + w.winfo_width() and w.winfo_rooty() <= y < w.winfo_rooty() + w.winfo_height())

def find_widget(widget, table):
    """Walk up from the tk widget that got the click until one is a key in table."""
    while widget is not None:
        if widget in table:
            return table[widget]
        widget = getattr(widget, "master", None)
    return None

class Outline:
    """Rectangle made of 4 bars. A 'transparent' CTkFrame would paint
    over whatever is under it so a real frame outline can't be used."""

    def __init__(self, parent):
        self.bars = [ctk.CTkFrame(parent, corner_radius=0) for _ in range(4)]

    def show(self, x, y, width, height, color, t=3):
        top, bottom, left, right = self.bars
        for bar in self.bars:
            bar.configure(fg_color=color)
        top.configure(width=width, height=t)
        top.place(x=x, y=y)
        bottom.configure(width=width, height=t)
        bottom.place(x=x, y=y + height - t)
        left.configure(width=t, height=height)
        left.place(x=x, y=y)
        right.configure(width=t, height=height)
        right.place(x=x + width - t, y=y)
        for bar in self.bars:
            bar.lift()

    def hide(self):
        for bar in self.bars:
            bar.place_forget()

class GridDragger:
    """Drag and drop for a GridManager.
    
    - Palette widgets (attach_palette): drag one onto the grid to add a widget, 
    or just tap it to run its on_tap callback. Works anytime the widget is visible.
    - Placed tiles: drag to move or swap. Only while editing is True.
    - Remove zone (set_remove_zone): drop a placed tile on it to delete the tile.
    """

    DRAG_THRESHOLD = 8 #px of movement before a press becomes a drag

    def __init__(self, grid):
        self.grid = grid
        self.editing = False
        self._palette = {} # menu widget -> spec of the widget it creates
        self._remove_zone = None # drop a tile here to delete it
        self._src = None # ('move', item) or ('new', spec)
        self._origin = (0, 0) # where the press started (screen coords)
        self._grab = (0, 0) # pointer offset inside the dragged tile
        self._size = (1, 1) # (cols, rows) of whatever is being dragged
        self._dragging = False

        self._top = grid.winfo_toplevel()
        self._ghost = ctk.CTkLabel(self._top, text="", corner_radius=Widget.CORNER_RADIUS, fg_color="#1f6aa5")
        self._outline = Outline(grid)

        #Bound on the window, so presses on any tile (or its inner labels) are caught
        self._top.bind("<ButtonPress-1>", self._on_press, add="+")
        self._top.bind("<B1-Motion>", self._on_motion, add="+")
        self._top.bind("<ButtonRelease-1>", self._on_release, add="+")

    def set_editing(self, on):
        self.editing = on
        if not on:
            self.cancel()

    def attach_palette(self, widget, widget_type, size="1x1", backgnd="#22242a", font_color="#ffffff", on_tap=None):
        """Make a menu widget a source: drag it onto the grid to add a widget, or just tap it to run on_tap."""
        self._palette[widget] = {"type": widget_type, "size": size, "bg": backgnd, "fg": font_color, "on_tap": on_tap}

    def set_remove_zone(self, widget):
        """Dropping a placed tile on this widget on this widget (e.g. the Add menu) deletes it."""
        self._remove_zone = widget

    def cancel(self):
        """Stop any drag in progress."""
        self._src = None
        self._dragging = False
        self._ghost.place_forget()
        self._outline.hide()

    def _on_press(self, e):
        self._src = None
        self._dragging = False
        self._origin = (e.x_root, e.y_root)
        g = self.grid

        spec = find_widget(e.widget, self._palette)
        if spec is not None:
            cols, rows = map(int, spec["size"].split("x"))
            width, height = g.tile_size(cols, rows)
            self._src = ("new", spec)
            self._size = (cols, rows)
            self._grab = (width // 2, height // 2)
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
            self._ghost.configure(text=self._src[1]["type"], width=width, height=height)

        self._ghost.place(x=e.x_root - self._top.winfo_rootx() - self._grab[0], y=e.y_root - self._top.winfo_rooty() - self._grab[1])
        self._ghost.lift()
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
        """Where would a drop land? -> ('grid', r, c), ('remove',) or None."""
        if self._remove_zone is not None and inside(self._remove_zone, e.x_root, e.y_root):
            return ("remove",) if self._src[0] == "move" else None
        if inside(self.grid, e.x_root, e.y_root):
            r, c = self._nearest_cell(e.x_root - self._grab[0], e.y_root - self._grab[1])
            return ("grid", r, c)
        return None

    def _nearest_cell(self, left, top):
        """Snap the dragged tile's top-left corner to the closest cell where it fits."""
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
        """What would dropping at (r, c) do? -> ("place", None), ("swap"/"replace", other) or None."""
        g = self.grid
        kind, src = self._src
        cols, rows = self._size
        mine = (src,) if kind == "move" else ()
        hits = g.items_overlapping(g.current_page_idx, r, c, cols, rows, ignore=mine)

        if not hits:
            return ("place", None)
        other = hits[0]
        if (len(hits) == 1 and (other["row"], other["col"]) == (r, c) and (other["cols"], other["rows"]) == (cols, rows)):
            return ("swap" if kind == "move" else "replace", other)
        return None

    def _show_outline(self, hit):
        if hit is None or hit[0] != "grid":
            self._outline.hide()
            return
        g = self.grid
        _, r, c = hit
        ox, oy = g.cell_origin(r, c)
        x = ox - g.winfo_rootx() + g.PADDING // 2
        y = oy - g.winfo_rooty() + g.PADDING // 2
        width, height = g.tile_size(*self._size)
        self._outline.show(x, y, width, height, "lime" if self._plan(r, c) else "red")
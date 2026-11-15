import customtkinter as ctk

from widget import Widget
from grid_drag import GridDragger


class GridManager(ctk.CTkFrame):
    PADDING = 12
    MAX_COLS = 6
    MAX_ROWS = 3

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        # Create 3 frames (pages) to stack on top of each other
        self.pages = [ctk.CTkFrame(self, fg_color="transparent") for _ in range(3)]
        self.current_page_idx = 0

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Display the first page
        self.pages[0].grid(row=0, column=0, sticky="nsew")

        self.occupied_cells = [set(), set(), set()]
        self.widgets_list = []
        self.tiles = {}

        self.current_base_w = 90
        self.current_base_h = 90
        self._configure_page_grids()

        self.drag = GridDragger(self)
        # Wait until Tk has finished resizing before measuring
        self.bind("<Configure>", lambda e: self.after_idle(self.on_configure))

    def switch_page(self, index):
        self.drag.cancel()
        self.pages[self.current_page_idx].grid_forget()
        self.current_page_idx = index
        self.pages[self.current_page_idx].grid(row=0, column=0, sticky="nsew")

    def _configure_page_grids(self):
        # Equal-sized cells. Fixes uneven gaps and the layout shifting.
        for page in self.pages:
            for c in range(self.MAX_COLS):
                page.grid_columnconfigure(c, weight=1, uniform="cell_col")
            for r in range(self.MAX_ROWS):
                page.grid_rowconfigure(r, weight=1, uniform="cell_row")

    def on_configure(self):
        s = self._get_widget_scaling()
        width = self.winfo_width() / s     # screen pixels -> CTk units
        height = self.winfo_height() / s

        if width <= 1 or height <= 1:
            return

        # tile size = cell size - padding
        new_w = max(30, width / self.MAX_COLS - self.PADDING)
        new_h = max(30, height / self.MAX_ROWS - self.PADDING)

        if abs(self.current_base_w - new_w) > 1 or abs(self.current_base_h - new_h) > 1:
            self.current_base_w = new_w
            self.current_base_h = new_h
            self.update_all_widgets()

    def tile_size(self, cols, rows):
        w = (self.current_base_w * cols) + (self.PADDING * (cols - 1))
        h = (self.current_base_h * rows) + (self.PADDING * (rows - 1))
        return int(w), int(h)   # whole numbers only, PIL crashes on floats

    def tile_size(self, cols, rows):
        w = (self.current_base_w * cols) + (self.PADDING * (cols - 1))
        h = (self.current_base_h * rows) + (self.PADDING * (rows - 1))
        return int(w), int(h)

    def update_all_widgets(self):
        self._configure_page_grids()
        for item in self.widgets_list:
            w, h = self.tile_size(item["cols"], item["rows"])
            item["widget"].configure(width=w, height=h, corner_radius=Widget.CORNER_RADIUS)

    # layout helpers

    @staticmethod
    def cells(r, c, cols, rows):
        return {(r + i, c + j) for i in range(rows) for j in range(cols)}

    def items_overlapping(self, page_idx, r, c, cols, rows, ignore=()):
        """Widgets on that page that overlap this area (skipping any in ignore)."""
        target = self.cells(r, c, cols, rows)
        return [it for it in self.widgets_list
                if it["page_idx"] == page_idx
                and not any(it is x for x in ignore)
                and self.cells(it["row"], it["col"], it["cols"], it["rows"]) & target]

    def _find_free_slot(self, page_idx, cols, rows):
        for r in range(self.MAX_ROWS - rows + 1):
            for c in range(self.MAX_COLS - cols + 1):
                if not self.items_overlapping(page_idx, r, c, cols, rows):
                    return r, c
        return None

    def _sync_occupied(self):
        self.occupied_cells = [set() for _ in self.pages]
        for it in self.widgets_list:
            self.occupied_cells[it["page_idx"]] |= self.cells(it["row"], it["col"], it["cols"], it["rows"])

    def _grid_item(self, item):
        item["widget"].grid(row=item["row"], column=item["col"], rowspan=item["rows"], columnspan=item["cols"], padx=self.PADDING // 2, pady=self.PADDING //2, sticky="nw")

    def cell_origin(self, r, c):
        """Screen coordinates of the top-left of cell (r, c) on the current page."""
        page = self.pages[self.current_page_idx]
        x, y, _, _ = page.grid_bbox(c, r)
        return page.winfo_rootx() + x, page.winfo_rooty() + y

    # changing the layout

    def add_widget(self, widget_type="Widget", size="1x1", backgnd="#22242a",
                   font_color="#ffffff", at=None):
        """at=(row, col) places it there; at=None uses the first free slot."""
        cols, rows = map(int, size.split("x"))
        page_idx = self.current_page_idx
 
        if at is None:
            slot = self._find_free_slot(page_idx, cols, rows)
        else:
            free = not self.items_overlapping(page_idx, at[0], at[1], cols, rows)
            slot = at if free else None
 
        if slot is None:
            print(f"No space available on page {page_idx + 1} for a {size} widget.")
            return None
        r, c = slot
 
        w, h = self.tile_size(cols, rows)
        tile = Widget(self.pages[page_idx], widget_type, size, width=w, height=h,
                      bg=backgnd, fg=font_color)
        item = {
            "widget": tile, "cols": cols, "rows": rows, "page_idx": page_idx,
            "row": r, "col": c,
            "type": widget_type, "size": size, "bg": backgnd, "fg": font_color,
        }
        self.widgets_list.append(item)
        self.tiles[tile] = item
        self._grid_item(item)
        self._sync_occupied()
        return item
 
    def remove_widget(self, item):
        self.widgets_list.remove(item)
        self.tiles.pop(item["widget"], None)
        self._sync_occupied()
        self.after(1, item["widget"].destroy)       # after the current event finishes
 
    def move_widget(self, item, r, c):
        item["row"], item["col"] = r, c
        self._grid_item(item)
        self._sync_occupied()
 
    def swap_widgets(self, a, b):
        a["row"], a["col"], b["row"], b["col"] = b["row"], b["col"], a["row"], a["col"]
        self._grid_item(a)
        self._grid_item(b)
        self._sync_occupied()
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

    def switch_page(self, index):
        self.drag.cancel()
        self.pages[self.current_page_idx].grid_forget()
        self.current_page_idx = index
        self.pages[self.current_page_idx].grid(row=0, column=0, sticky="nsew")

    def _configure_page_grids(self):
        """Fixed row/column sizes, so empty cells keep their space.
        Without this an empty column collapses to 0 px and tiles can't sit in a chosen spot."""
        for page in self.pages:
            for c in range(self.MAX_COLS):
                page.grid_columnconfigure(c, minsize=self.current_base_w + self.PADDING)
            for r in range(self.MAX_ROWS):
                page.grid_rowconfigure(r, minsize=self.current_base_h + self.PADDING)

    def on_configure(self):
        width = self.winfo_width()
        height = self.winfo_height()

        if width <= 1 or height <= 1:
            return

        usable_w = width - (self.PADDING * 2)
        usable_h = height - (self.PADDING * 2)

        # Dynamically calculate the stretching cell width/height based on the window size
        new_w = max(30, (usable_w - (self.PADDING * (self.MAX_COLS - 1))) // self.MAX_COLS)
        new_h = max(30, (usable_h - (self.PADDING * (self.MAX_ROWS - 1))) // self.MAX_ROWS)

        if abs(self.current_base_w - new_w) > 2 or abs(self.current_base_h - new_h) > 2:
            self.current_base_w = new_w
            self.current_base_h = new_h
            self.update_all_widgets()

    def tile_size(self, cols, rows):
        w = (self.current_base_w * cols) + (self.PADDING * (cols - 1))
        h = (self.current_base_h * rows) + (self.PADDING * (rows - 1))
        return w, h

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
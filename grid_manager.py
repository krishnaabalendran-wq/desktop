import customtkinter as ctk
import tkinter as tk
import time
import math
import random

from widget import Widget
from grid_drag import GridDragger
from style import mono


class GridManager(ctk.CTkFrame):
    PADDING = 12
    MAX_COLS = 6
    MAX_ROWS = 3

    SLIDE_DURATION = 240
    SLIDE_FRAME_DELAY = 16 # wait between animation frames

    JIGGLE_FRAME_MS = 40 # time between shake frames
    JIGGLE_AMPLITUDE_PX = 2 # how far a tile moves from its resting spot
    JIGGLE_SPEED = 14 # how fast it shakes

    SIZES = [(1, 1), (2, 1), (2, 2)]

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        # Create 3 frames (pages) to stack on top of each other
        self.pages = [ctk.CTkFrame(self, fg_color="transparent") for _ in range(3)]
        self.current_page_idx = 0 # the page the rest of the code treats as "current"
        self._shown_idx = 0 # the page on screen
        self._slide = None # slide in progress or None when not animating
        self._slide_timer_id = None # the id returned by after() for the next animation frame

        # Pages are positioned with place() instead of grid() so they can slide sideways
        # relwidth/relheight=1 makes each page fill the whole GridManager, same as stick="nsew"
        self.pages[0].place(relx=0, rely=0, relwidth=1, relheight=1)

        self.occupied_cells = [set(), set(), set()]
        self.widgets_list = []
        self.tiles = {}

        self.jiggling = False
        self._jiggle_timer_id = None
        self._jiggle_start_time = 0

        self.resize_handles = {}

        self.current_base_w = 90
        self.current_base_h = 90
        self._configure_page_grids()

        self.drag = GridDragger(self)

    def switch_page(self, index, animate):
        self.drag.cancel()
        self._finish_slide() # if a slide is running, jump it to its end first

        leaving_idx = self._shown_idx
        entering_idx = index

        # update before the return below, because the layout sets current_page_idx directly then calls switch_page(0)
        self.current_page_idx = entering_idx
        if entering_idx == leaving_idx:
            return
        self._shown_idx = entering_idx

        if not animate:
            # instant swap (at startup so the app doesn't slide)
            self.pages[leaving_idx].place_forget()
            self.pages[entering_idx].place(relx=0, rely=0, relwidth=1, relheight=1)
            return

        # direction +1: new page from right / direction: -1: new page from left
        direction = 1 if entering_idx > leaving_idx else -1

        # new page just off-screen, on the entering slide, on top of the old one
        self.pages[entering_idx].place(relx=direction, rely=0, relwidth=1, relheight=1)
        self.pages[entering_idx].lift()

        self._slide = {
            "leaving": leaving_idx,
            "entering": entering_idx,
            "direction": direction,
            "start": time.perf_counter(),
        }
        self._advance_slide()

    def _advance_slide(self):
        animation = self._slide
        if animation is None:
            return

        # progress comes from real clock, so slow frame makes the slide skip ahead instead of taking longer
        elapsed = (time.perf_counter() - animation["start"]) * 1000
        progress = min(1.0, elapsed / self.SLIDE_DURATION)

        # ease out: starts fast and slows to a stop
        ease = 1 - (1 - progress) ** 3

        direction = animation["direction"]
        # the old pages slides out the opposite way the new pages comes in
        self.pages[animation["leaving"]].place(relx=-direction * ease, rely=0, relwidth=1, relheight=1)
        self.pages[animation["entering"]].place(relx=direction * (1 - ease), rely=0, relwidth=1, relheight=1)

        if progress >= 1.0:
            self._finish_slide()
        else:
            self._slide_timer_id = self.after(self.SLIDE_FRAME_DELAY, self._advance_slide)

    def _finish_slide(self):
        """End a slide immediately by stopping timer, hiding the old page, and pin the new."""
        animation = self._slide
        if animation is None:
            return
        if self._slide_timer_id is not None:
            self.after_cancel(self._slide_timer_id)
        self._slide = None
        self._slide_timer_id = None

        self.pages[animation["leaving"]].place_forget()
        self.pages[animation["entering"]].place(relx=0, rely=0, relwidth=1, relheight=1)

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

    def _grid_item(self, item, offset_x=0, offset_y=0):
        """Place a tile in its grid cell, optionally nudged by a few pixels."""
        half_padding = self.PADDING // 2
        item["widget"].grid(row=item["row"], column=item["col"], rowspan=item["rows"], columnspan=item["cols"], padx=(half_padding + offset_x, half_padding - offset_x), pady=(half_padding + offset_y, half_padding - offset_y), sticky="nw")
        item["offset"] = (offset_x, offset_y)

    def cell_origin(self, r, c):
        """Screen coordinates of the top-left of cell (r, c) on the current page."""
        page = self.pages[self.current_page_idx]
        x, y, _, _ = page.grid_bbox(c, r)
        return page.winfo_rootx() + x, page.winfo_rooty() + y

    def snapshot(self):
            """The current layout as data."""
            return [{"type": it["type"], "size": it["size"], "bg": it["bg"], "fg": it["fg"], "page": it["page_idx"], "r": it["row"], "c": it["col"]} for it in self.widgets_list]

    def clear_all(self):
        for item in list(self.widgets_list):
            self.remove_widget(item)

    def apply_snapshot(self, layout):
        """Replace every widget with the ones in layout. Entries that are malformed, off the grid or overlapping are skipped."""
        self.drag.cancel()
        self.clear_all()
        shown_page = self.current_page_idx
        skipped = 0
        try:
            for entry in layout:
                placed = None
                try:
                    page = int(entry.get("page", 0))
                    row, col = int(entry["r"]), int(entry["c"])
                    cols, rows = map(int, entry["size"].split("x"))
                    if (0 <= page < len(self.pages) and row >= 0 and col >= 0 and row + rows <= self.MAX_ROWS and col + cols <= self.MAX_COLS):
                        self.current_page_idx = page
                        placed = self.add_widget(entry["type"], entry["size"], entry["fg"], at=(row, col))
                except (KeyError, ValueError, TypeError, AttributeError):
                    pass
                if placed is None:
                    skipped += 1
        finally:
            self.current_page_idx = shown_page
        return skipped

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
            "offset": (0,0), "jiggle_phase": random.uniform(0, 2 * math.pi),
            "badge": None,
            "resize_handle": None,
        }
        self.widgets_list.append(item)
        self.tiles[tile] = item
        self._grid_item(item)
        self._create_delete_badge(item)
        self._create_resize_handle(item)
        if self.jiggling:
            self._set_badge_visible(item, True)
            self._set_handle_visible(item, True)
        self._sync_occupied()
        return item
 
    def remove_widget(self, item):
        self.widgets_list.remove(item)
        self.tiles.pop(item["widget"], None)
        self.resize_handles.pop(item.get("resize_handle"), None)
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

    def set_jiggle(self, on):
        """Start or stop the shake and show or hide the delete."""
        self.jiggling = on
        for item in self.widgets_list:
            self._set_badge_visible(item, on)
            self._set_handle_visible(item, on)

        if on:
            self._jiggle_start_time = time.perf_counter()
            if self._jiggle_timer_id is None:
                self._jiggle_frame()
        else:
            if self._jiggle_timer_id is not None:
                self.after_cancel(self._jiggle_timer_id)
                self._jiggle_timer_id = None
            for item in self.widgets_list:
                if item["offset"] != (0, 0):
                    self._grid_item(item)

    def _jiggle_frame(self):
        """Move all visible tiles a little, the schedule the next frame."""
        if not self.jiggling:
            self._jiggle_timer_id = None
            return

        seconds = time.perf_counter() - self._jiggle_start_time
        for item in self.widgets_list:
            if item["page_idx"] != self.current_page_idx:
                continue
            phase = item["jiggle_phase"]
            # two sine waves at different speeds make the movement wander instead of sliding back and forth along a line.
            offset_x = round(self.JIGGLE_AMPLITUDE_PX * math.sin(seconds * self.JIGGLE_SPEED + phase))
            offset_y = round(self.JIGGLE_AMPLITUDE_PX * math.sin(seconds * self.JIGGLE_SPEED * 1.3 + phase * 1.7))
            if (offset_x, offset_y) != item["offset"]:
                self._grid_item(item, offset_x, offset_y)

        self._jiggle_timer_id = self.after(self.JIGGLE_FRAME_MS, self._jiggle_frame)

    def _create_delete_badge(self, item):
        item["badge"] = ctk.CTkButton(
            item["widget"], text="\u00d7", width=16, height=16, corner_radius=0, border_width=0,
            fg_color="#d64545", hover_color="#ff6b6b", text_color="#ffffff",
            font=mono(12, True), command=lambda: self.remove_widget(item)
        )

    def _set_badge_visible(self, item, visible):
        badge = item["badge"]
        if visible:
            badge.place(x=4, y=4, anchor="nw")
            badge.lift()
        else:
            badge.place_forget()

    def can_resize(self, item, cols, rows):
        """True if item could become cols x rows where it is (inside the grid and not touching another tile)."""
        fits = (item["row"] + rows <= self.MAX_ROWS and item["col"] + cols <= self.MAX_COLS)
        return fits and not self.items_overlapping(item["page_idx"], item["row"], item["col"], cols, rows, ignore=(item,))

    def resize_widget(self, item, cols, rows):
        """Rebuild a tile at a new size. Tile gets built again from scratch."""
        old_tile = item["widget"]
        size = f"{cols}x{rows}"
        width, height = self.tile_size(cols, rows)
        new_tile = Widget(self.pages[item["page_idx"]], item["type"], size, width=width, height=height, bg=item["bg"], fg=item["fg"])

        self.tiles.pop(old_tile, None)
        self.resize_handles.pop(item.get("resize_handle"), None)
        old_tile.grid_forget()

        item.update(widget=new_tile, cols=cols, rows=rows, size=size, badge=None, resize_handle=None)
        self.tiles[new_tile] = item
        self._grid_item(item)
        self._create_delete_badge(item)
        self._create_resize_handle(item)
        if self.jiggling:
            self._set_badge_visible(item, True)
            self._set_handle_visible(item, True)
        self._sync_occupied()
        self.after(1, old_tile.destroy)

    def _create_resize_handle(self, item):
        handle = tk.Canvas(item["widget"], width=18, height=18, bg="#e8e8e8", highlightthickness=0)
        handle.create_polygon(16, 2, 16, 16, 2, 16, fill="#121212", outline="")
        item["resize_handle"] = handle
        self.resize_handles[handle] = item # lets GridDragger find which tile a press belongs to

    def _set_handle_visible(self, item, visible):
        handle = item["resize_handle"]
        if visible:
            handle.place(relx=1.0, rely=1.0, x=-3, y=-3, anchor="se")
        else:
            handle.place_forget()

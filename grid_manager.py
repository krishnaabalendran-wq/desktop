import customtkinter as ctk

from widget import Widget


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

        self.current_base_w = 90
        self.current_base_h = 90

    def switch_page(self, index):
        self.pages[self.current_page_idx].grid_forget()
        self.current_page_idx = index
        self.pages[self.current_page_idx].grid(row=0, column=0, sticky="nsew")

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
        for item in self.widgets_list:
            w, h = self.tile_size(item["cols"], item["rows"])
            item["widget"].configure(width=w, height=h, corner_radius=Widget.CORNER_RADIUS)

    def add_widget(self, widget_type="Widget", size="1x1", backgnd="#22242a", font_color="#ffffff"):
        cols, rows = map(int, size.split("x"))
        page = self.pages[self.current_page_idx]

        found_slot = False
        start_r, start_c = 0, 0

        for r in range(self.MAX_ROWS - rows + 1):
            if found_slot:
                break
            for c in range(self.MAX_COLS - cols + 1):
                is_free = True
                for i in range(rows):
                    for j in range(cols):
                        if (r + i, c + j) in self.occupied_cells[self.current_page_idx]:
                            is_free = False
                            break
                    if not is_free:
                        break

                if is_free:
                    start_r, start_c = r, c
                    found_slot = True
                    break

        if not found_slot:
            print(f"No space available on page {self.current_page_idx + 1} for a {size} widget.")
            return

        for i in range(rows):
            for j in range(cols):
                self.occupied_cells[self.current_page_idx].add((start_r + i, start_c + j))

        w, h = self.tile_size(cols, rows)

        tile = Widget(page, widget_type, size, width=w, height=h,
                      bg=backgnd, fg=font_color)
        tile.grid(row=start_r, column=start_c, rowspan=rows, columnspan=cols,
                  padx=self.PADDING // 2, pady=self.PADDING // 2, sticky="nw")

        self.widgets_list.append({
            "widget": tile,
            "cols": cols,
            "rows": rows,
            "page_idx": self.current_page_idx
        })
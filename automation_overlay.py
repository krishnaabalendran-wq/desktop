import customtkinter as ctk

from style import BORDER_HOVER, BTN, BTN_HOVER, DIM, SURFACE, TEXT, mono

BACKDROP_COLOR = ("#c9c9ce", "#0a0a0a")
STOP_COLOR = "#c0392b"
STOP_HOVER_COLOR = "#e04a3a"

# How each step state is drawn
STATE_MARKERS = {
    "pending": "[ ]",
    "running": "[>]",
    "done": "[x]",
    "failed": "[!]",
    "stopped": "[-]",
    "skipped": "[-]"
}
STATE_COLORS = {
    "pending": DIM,
    "running": TEXT,
    "done": ("#1f7a3d", "#7ee787"),
    "failed": ("#b42318", "#ff6b6b"),
    "stopped": ("#b42318", "#ff6b6b"),
    "skipped": DIM,
}

AUTO_CLOSE_SECONDS = 4


class AutomationOverlay(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, corner_radius=0, fg_color=BACKDROP_COLOR)

        self.runner = None # the SceneRunner being shown
        self.is_showing = False
        self.covered = []
        self._row_labels = []               
        self._auto_close_id = None # id from after(), so the automatic close can be cancelled

        self.panel = ctk.CTkFrame(self, corner_radius=0, fg_color=SURFACE, border_width=1, border_color=BORDER_HOVER)
        self.panel.place(relx=0.5, rely=0.5, relwidth=0.84, relheight=0.84, anchor="center")

        self.title_label = ctk.CTkLabel(self.panel, text="", anchor="w", font=mono(26, True), text_color=TEXT, fg_color=SURFACE)
        self.title_label.pack(anchor="w", padx=24, pady=(20, 0))

        self.status_label = ctk.CTkLabel(self.panel, text="", anchor="w", font=mono(13, True), text_color=DIM, fg_color=SURFACE)
        self.status_label.pack(anchor="w", padx=24, pady=(4, 12))

        self.rows_frame = ctk.CTkFrame(self.panel, corner_radius=0, fg_color=SURFACE)
        self.rows_frame.pack(fill="x", padx=24)

        self.note_label = ctk.CTkLabel(self.panel, text="", font=mono(11),
                                       text_color=DIM, fg_color=SURFACE)
        self.note_label.place(relx=0.5, rely=1.0, y=-84, anchor="s")

        self.action_button = ctk.CTkButton(self.panel, text="STOP", height=44, corner_radius=0, font=mono(14, True), command=self._on_action_button)
        self.action_button.place(relx=0.5, rely=1.0, y=-24, anchor="s", relwidth=0.5)

    def show(self, runner):
        """Open the panel for 'runner'."""
        self.runner = runner
        self._cancel_auto_close()
        self._clear_rows()
        self.is_showing = True
        for widget in self.covered:
            widget.grid_remove()           
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self.refresh()

    def hide(self):
        self._cancel_auto_close()
        self.is_showing = False
        self.place_forget()
        for widget in self.covered:
            widget.grid()

    def refresh(self):
        """Redraw the panel from the runner's current state."""
        runner = self.runner
        if runner is None or not self.is_showing:
            return
        self.lift()
        if len(self._row_labels) != len(runner.steps):
            self._rebuild_rows()

        self.title_label.configure(text=runner.scene.get("name", "") if runner.scene else "")

        for row_label, entry in zip(self._row_labels, runner.steps):
            state = entry["state"]
            text = f"{STATE_MARKERS[state]} {entry['label']}"
            if state == "failed" and entry["message"]:
                text += f"({entry['message']})"
            row_label.configure(text=text, text_color=STATE_COLORS[state], font=mono(15, state == "running"))

        self._update_status_and_button(runner)

    def _update_status_and_button(self, runner):
        step_count = len(runner.steps)
        dot = "  \u00b7  "

        if runner.is_running:
            current_step = min(runner.current_index + 1, step_count)
            self.status_label.configure(text=f"RUNNING{dot}STEP {current_step} OF {step_count}")
            self.note_label.configure(text="Press STOP to end this scene. Steps that already ran are not undone.")
            self.action_button.configure(text="STOP", fg_color=STOP_COLOR, hover_color=STOP_HOVER_COLOR, text_color="#ffffff")
            return

        self.action_button.configure(text="CLOSE", fg_color=BTN, hover_color=BTN_HOVER, text_color=TEXT)
        problems = runner.count_in_state("failed")

        if runner.outcome == "stopped":
            steps_run = runner.count_in_state("done")
            self.status_label.configure(text=f"STOPPED{dot}{steps_run} OF {step_count} STEPS RAN")
            self.note_label.configure(text="Steps that already ran were not undone.")
        elif problems:
            self.status_label.configure(text=f"DONE WITH PROBLEMS{dot}{problems} OF {step_count} STEPS FAILED")
            self.note_label.configure(text="Steps marked [!] did not work.")
        else:
            self.status_label.configure(
                text=f"DONE{dot}{step_count} STEPS IN {runner.seconds_taken:.1f} S")
            self.note_label.configure(text="Closing automatically.")
            if self._auto_close_id is None:
                self._auto_close_id = self.after(AUTO_CLOSE_SECONDS * 1000, self._auto_close)

    def _clear_rows(self):
        for row_label in self._row_labels:
            row_label.destroy()
        self._row_labels = []

    def _rebuild_rows(self):
        self._clear_rows()
        for _ in self.runner.steps:
            row_label = ctk.CTkLabel(self.rows_frame, text="", anchor="w", font=mono(15), text_color=DIM, fg_color=SURFACE)
            row_label.pack(anchor="w", pady=2)
            self._row_labels.append(row_label)

    def _on_action_button(self):
        if self.runner is not None and self.runner.is_running:
            self.runner.stop()        # the runner calls on_change, which redraws this panel
        else:
            self.hide()

    def _auto_close(self):
        self._auto_close_id = None
        if self.is_showing and self.runner is not None and not self.runner.is_running:
            self.hide()

    def _cancel_auto_close(self):
        if self._auto_close_id is not None:
            self.after_cancel(self._auto_close_id)
            self._auto_close_id = None
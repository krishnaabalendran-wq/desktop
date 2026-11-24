import time

import customtkinter as ctk

from style import BORDER, BORDER_HOVER, BTN, BTN_HOVER, DIM, SURFACE, TEXT, mono

BACKDROP_COLOR = ("#c9c9ce", "#0a0a0a")
STOP_COLOR = "#c0392b"
STOP_HOVER_COLOR = "#e04a3a"
RUN_COLOR = "#1f7a3d"
RUN_HOVER_COLOR = "#2a9a50"

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

AUTO_CLOSE_SECONDS = 4             # a clean run closes the panel after this long
SUGGESTION_SECONDS = 20            # a suggestion hides itself (like NOT NOW) after this long


class AutomationOverlay(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, corner_radius=0, fg_color=BACKDROP_COLOR)

        self.mode = "run"                   # "run", "suggest" or "recap"
        self.runner = None                  # the SceneRunner being shown (run mode)
        self.is_showing = False
        self.covered = []                   # frames hidden while the panel is up (the App fills this in)
        self._row_labels = []
        self._auto_close_id = None          # id from after(), so the automatic close can be cancelled

        # suggest mode
        self._suggestion = None             # the suggestion dictionary from TriggerEngine
        self._on_suggestion_run = None      # function(suggestion), called when RUN is pressed
        self._on_suggestion_dismissed = None   # function(suggestion, mute_today), called for NOT NOW / NOT TODAY / timeout
        self._countdown_end = 0.0           # time.monotonic() when the suggestion hides itself
        self._countdown_id = None           # id from after() for the countdown ticks

        self.panel = ctk.CTkFrame(self, corner_radius=0, fg_color=SURFACE, border_width=1, border_color=BORDER_HOVER)
        self.panel.place(relx=0.5, rely=0.5, relwidth=0.84, relheight=0.84, anchor="center")

        self.title_label = ctk.CTkLabel(self.panel, text="", anchor="w", font=mono(26, True), text_color=TEXT, fg_color=SURFACE)
        self.title_label.pack(anchor="w", padx=24, pady=(20, 0))

        self.status_label = ctk.CTkLabel(self.panel, text="", anchor="w", font=mono(13, True), text_color=DIM, fg_color=SURFACE)
        self.status_label.pack(anchor="w", padx=24, pady=(4, 12))

        self.rows_frame = ctk.CTkFrame(self.panel, corner_radius=0, fg_color=SURFACE)
        self.rows_frame.pack(fill="x", padx=24)

        self.note_label = ctk.CTkLabel(self.panel, text="", font=mono(11), text_color=DIM, fg_color=SURFACE)
        self.note_label.place(relx=0.5, rely=1.0, y=-84, anchor="s")

        # A thin bar that shrinks while a suggestion counts down (suggest mode only)
        self.countdown_bar = ctk.CTkProgressBar(self.panel, height=5, corner_radius=0,
                                                fg_color=BORDER, progress_color=RUN_COLOR)

        # The main button is STOP / CLOSE / RUN. The other two only exist in suggest mode.
        self.action_button = ctk.CTkButton(self.panel, text="STOP", height=44, corner_radius=0, font=mono(14, True), command=self._on_action_button)
        self.not_now_button = ctk.CTkButton(self.panel, text="NOT NOW", height=44, corner_radius=0, font=mono(14, True),
                                            border_width=1, border_color=BORDER, fg_color=BTN, hover_color=BTN_HOVER,
                                            text_color=TEXT, command=lambda: self._dismiss_suggestion(False))
        self.not_today_button = ctk.CTkButton(self.panel, text="NOT TODAY", height=44, corner_radius=0, font=mono(14, True),
                                              border_width=1, border_color=BORDER, fg_color=BTN, hover_color=BTN_HOVER,
                                              text_color=TEXT, command=lambda: self._dismiss_suggestion(True))
        self._place_buttons("run")

    # ---- opening the panel in each mode ----

    def show(self, runner):
        """Open the panel for a running scene ('run' mode)."""
        self.mode = "run"
        self.runner = runner
        self._stop_countdown()
        self._suggestion = None
        self._cancel_auto_close()
        self._clear_rows()
        self._place_buttons("run")
        self.countdown_bar.place_forget()
        self._cover_and_raise()
        self.refresh()

    def show_suggestion(self, suggestion, on_run, on_dismissed):
        """Offer a scene. on_run(suggestion) if RUN is pressed; on_dismissed(suggestion, mute_today) otherwise."""
        from actions import describe_step           # imported here so this file stays easy to test on its own

        self.mode = "suggest"
        self._suggestion = suggestion
        self._on_suggestion_run = on_run
        self._on_suggestion_dismissed = on_dismissed
        self._cancel_auto_close()
        scene = suggestion["scene"]

        self.title_label.configure(text=scene.get("name", ""))
        self.status_label.configure(text=f"SUGGESTED  \u00b7  {suggestion['reason']}")
        steps = scene.get("steps", [])
        self._ensure_row_count(len(steps))
        for row_label, step in zip(self._row_labels, steps):          # a preview of what RUN would do
            row_label.configure(text=f"{STATE_MARKERS['pending']} {describe_step(step)}",
                                text_color=STATE_COLORS["pending"], font=mono(15))

        self._place_buttons("suggest")
        self.action_button.configure(text="RUN", fg_color=RUN_COLOR, hover_color=RUN_HOVER_COLOR, text_color="#ffffff")
        self.countdown_bar.place(relx=0.5, rely=1.0, y=-112, anchor="s", relwidth=0.5)
        self._countdown_end = time.monotonic() + SUGGESTION_SECONDS
        self._cover_and_raise()
        self._tick_countdown()

    def show_recap(self, title, lines):
        """Show a list of text lines (the daily recap). One CLOSE button."""
        self.mode = "recap"
        self.runner = None
        self._stop_countdown()
        self._suggestion = None
        self._cancel_auto_close()
        self.countdown_bar.place_forget()

        self.title_label.configure(text=title)
        self.status_label.configure(text="RECAP")
        self.note_label.configure(text="")
        self._ensure_row_count(len(lines))
        for row_label, line in zip(self._row_labels, lines):
            # headings (lines that don't start with a space) are bold
            row_label.configure(text=line, text_color=TEXT, font=mono(14, not line.startswith(" ") and bool(line)))

        self._place_buttons("run")
        self.action_button.configure(text="CLOSE", fg_color=BTN, hover_color=BTN_HOVER, text_color=TEXT)
        self._cover_and_raise()

    def hide(self):
        self._cancel_auto_close()
        self._stop_countdown()
        self.is_showing = False
        self.place_forget()
        for widget in self.covered:
            widget.grid()

    def _cover_and_raise(self):
        self.is_showing = True
        for widget in self.covered:
            widget.grid_remove()
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()

    # ---- run mode ----

    def refresh(self):
        """Redraw the panel from the runner's current state."""
        runner = self.runner
        if self.mode != "run" or runner is None or not self.is_showing:
            return
        self.lift()
        self._ensure_row_count(len(runner.steps))

        self.title_label.configure(text=runner.scene.get("name", "") if runner.scene else "")

        for row_label, entry in zip(self._row_labels, runner.steps):
            state = entry["state"]
            text = f"{STATE_MARKERS[state]} {entry['label']}"
            if state == "failed" and entry["message"]:
                text += f" ({entry['message']})"
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

    # ---- suggest mode ----

    def _tick_countdown(self):
        """Shrink the bar and update the note once a fraction of a second. At zero the suggestion hides itself."""
        if self.mode != "suggest" or self._suggestion is None:
            return
        remaining = self._countdown_end - time.monotonic()
        if remaining <= 0:
            self._dismiss_suggestion(False)               # nobody answered: same as NOT NOW
            return
        self.countdown_bar.set(remaining / SUGGESTION_SECONDS)
        self.note_label.configure(text=f"Nothing runs unless you press RUN.  Hides in {int(remaining) + 1} s")
        self._countdown_id = self.after(200, self._tick_countdown)

    def _dismiss_suggestion(self, mute_today):
        suggestion, callback = self._suggestion, self._on_suggestion_dismissed
        self._suggestion = None
        self.hide()
        if suggestion is not None and callback is not None:
            callback(suggestion, mute_today)

    def _stop_countdown(self):
        if self._countdown_id is not None:
            self.after_cancel(self._countdown_id)
            self._countdown_id = None

    # ---- rows and buttons ----

    def _ensure_row_count(self, count):
        """Make exactly `count` text rows (adding or removing from the end)."""
        while len(self._row_labels) > count:
            self._row_labels.pop().destroy()
        while len(self._row_labels) < count:
            row_label = ctk.CTkLabel(self.rows_frame, text="", anchor="w", font=mono(15), text_color=DIM, fg_color=SURFACE)
            row_label.pack(anchor="w", pady=2)
            self._row_labels.append(row_label)

    def _clear_rows(self):
        self._ensure_row_count(0)

    def _place_buttons(self, layout):
        """'run': one centred button. 'suggest': RUN, NOT NOW and NOT TODAY side by side."""
        if layout == "suggest":
            self.action_button.place(relx=0.2, rely=1.0, y=-24, anchor="s", relwidth=0.27)
            self.not_now_button.place(relx=0.5, rely=1.0, y=-24, anchor="s", relwidth=0.27)
            self.not_today_button.place(relx=0.8, rely=1.0, y=-24, anchor="s", relwidth=0.27)
        else:
            self.action_button.place(relx=0.5, rely=1.0, y=-24, anchor="s", relwidth=0.5)
            self.not_now_button.place_forget()
            self.not_today_button.place_forget()

    def _on_action_button(self):
        if self.mode == "suggest":
            # RUN: hand over to the App without hiding first (the App calls show(), which keeps the
            # panel up, so the screen doesn't flicker between the suggestion and the run).
            suggestion, callback = self._suggestion, self._on_suggestion_run
            self._suggestion = None
            self._stop_countdown()
            if suggestion is not None and callback is not None:
                callback(suggestion)
            if self.mode == "suggest":        # the App didn't start the scene (e.g. one was already running)
                self.hide()
        elif self.mode == "run" and self.runner is not None and self.runner.is_running:
            self.runner.stop()        # the runner calls on_change, which redraws this panel
        else:
            self.hide()

    def _auto_close(self):
        self._auto_close_id = None
        if self.is_showing and self.mode == "run" and self.runner is not None and not self.runner.is_running:
            self.hide()

    def _cancel_auto_close(self):
        if self._auto_close_id is not None:
            self.after_cancel(self._auto_close_id)
            self._auto_close_id = None
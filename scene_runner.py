import time

from actions import InstantStep, describe_step, start_step


class SceneRunner:
    POLL_MS = 100 # how often a running step is checked
    STEP_GAP_MS = 350 # pause between steps, so you can SEE each one tick off

    def __init__(self, context, schedule, cancel_schedule, on_change, on_finished, apply_layout):
        self.context = context # what steps may ask of the app
        self.schedule = schedule # function(delay_ms, callback) -> id
        self.cancel_schedule = cancel_schedule # function(id)
        self.on_change = on_change # called whenever something changed, so screen can redraw
        self.on_finished = on_finished # called with a summary when scene ends
        self.apply_layout = apply_layout

        self.is_running = False
        self.scene = None
        self.steps = [] # one dictionary per step: step, label, state, message
        self.current_index = -1 # index of step in progress
        self.outcome = None # "completed" or "stopped"
        self.seconds_taken = 0.0
        
        self._running_step = None # the RunningStep being polled
        self._timer_id = None # id of the next schedule check, so STOP can cancel it
        self._started_at = 0.0 
        self._started_clock = 0.0

    def start(self, scene):
        if self.is_running:
            return False
        self.scene = scene
        self.steps = [{"step": step, "label": describe_step(step), "state": "pending", "message": ""} for step in scene.get("steps", [])]
        self.current_index = -1
        self.outcome = None
        self.seconds_taken = 0.0
        self.is_running = True
        self._started_at = time.time()
        self._started_clock = time.monotonic()
        self.on_change()
        self._begin_next_step()
        return True

    def stop(self):
        if not self.is_running:
            return
        if self._timer_id is not None:
            self.cancel_schedule(self._timer_id)
            self._timer_id = None
        if self._running_step is not None:
            self._running_step.cancel()
            self._running_step = None
            self.steps[self.current_index]["state"] = "stopped"
        self._finish("stopped")

    def _begin_next_step(self):
        self._timer_id = None
        self.current_index += 1
        if self.current_index >= len(self.steps):
            self._finish("completed")
            return

        entry = self.steps[self.current_index]
        entry["state"] = "running"
        self.on_change()
        try:
            self._running_step = start_step(entry["step"], self.context)
        except Exception as error:
            self._running_step = InstantStep(False, f"error: {error}")
        self._check_running_step()

    def _check_running_step(self):
        """Ask the running step if finished."""
        self._timer_id = None
        if not self.is_running or self._running_step is None:
            return
        try:
            step_outcome = self._running_step.poll()
        except Exception as error:
            step_outcome = InstantStep(False, f"error: {error}").outcome

        if step_outcome is None:
            self._timer_id = self.schedule(self.POLL_MS, self._check_running_step)
            return

        entry  = self.steps[self.current_index]
        entry["state"] = "done" if step_outcome.ok else "failed"
        entry["message"] = step_outcome.message
        self._running_step = None
        self.on_change()
        self._timer_id = self.schedule(self.STEP_GAP_MS, self._begin_next_step)

    def _finish(self, outcome):
        for entry in self.steps:
            if entry["state"] == "pending":
                entry["state"] = "skipped"
        self.outcome = outcome
        self.is_running = False
        self.seconds_taken = time.monotonic() - self._started_clock
        self.on_change()
        self.on_finished(self.summary())

    def count_in_state(self, state):
        return sum(1 for entry in self.steps if entry["state"] == state)

    def summary(self):
        return {
            "scene_id": self.scene.get("id"),
            "scene_name": self.scene.get("name"),
            "started_at": self._started_at,
            "seconds": self.seconds_taken,
            "outcome": self.outcome,
            "steps": [{"label": entry["label"], "state": entry["state"], "message": entry["message"]} for entry in self.steps]
        } 
            

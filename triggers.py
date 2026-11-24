import time

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]     # same order as time.localtime().tm_wday
WEEKDAYS = DAY_NAMES[:5]

DEFAULT_FOCUS_SECONDS = 5        # an app must stay in front this long, so a quick Alt-Tab doesn't trigger
COOLDOWN_SECONDS = 3600          # after suggesting, the same trigger stays quiet for an hour
TIME_WINDOW_MINUTES = 15         # a time trigger is still offered this many minutes after its time
IDLE_RETURN_SECONDS = 30         # idle less than this means the person is back, so idle triggers re-arm


def normalize_app_name(name):
    """Lower-case the macOS app name for comparison."""
    return str(name).strip().lower()


def app_names_match(first, second):
    return normalize_app_name(first) == normalize_app_name(second)


def parse_clock_time(text):
    """'09:30' -> 570 (minutes after midnight), or None if it isn't a valid HH:MM."""
    try:
        hours_text, minutes_text = text.split(":")
        hours, minutes = int(hours_text), int(minutes_text)
    except (AttributeError, ValueError):
        return None
    if 0 <= hours < 24 and 0 <= minutes < 60:
        return hours * 60 + minutes
    return None


def day_key(epoch_seconds):
    """'2026-11-23' for the local date of an epoch time."""
    return time.strftime("%Y-%m-%d", time.localtime(epoch_seconds))


class TriggerEngine:
    def __init__(self):
        self.scenes = []
        self.habit_triggers = []

        self._focus_started = {}
        self._quiet_until = {}
        self._muted_on_day = {}
        self._time_shown_on_day = {}
        self._idle_ready = {}

    def set_scenes(self, scenes):
        self.scenes = list(scenes)

    def set_habit_triggers(self, habit_triggers):
        self.habit_triggers = list(habit_triggers)

    def check(self, now, front_app, idle_seconds):
        """Return the first suggestion that is due, or None. Call this every couple of seconds.

        now: epoch seconds. front_app: name of the app in front, or None. idle_seconds: or None.
        A suggestion is a dictionary: {"key", "scene", "reason", "trigger_type"}.
        """
        today = day_key(now)
        if idle_seconds is not None and idle_seconds < IDLE_RETURN_SECONDS:
            for key in self._idle_ready:                 # the person is back: idle triggers may fire again
                self._idle_ready[key] = True

        for scene, trigger, key in self._all_triggers():
            scene_id = scene.get("id") or scene.get("name")
            if self._muted_on_day.get(scene_id) == today:
                continue
            if self._quiet_until.get(key, 0) > now:
                continue
            reason = self._due_reason(trigger, key, now, front_app, idle_seconds, today)
            if reason is None:
                continue
            self._quiet_until[key] = now + COOLDOWN_SECONDS
            return {"key": key, "scene": scene, "reason": reason, "trigger_type": trigger.get("type")}
        return None

    def dismissed(self, suggestion, mute_today, now=None):
        """The person said NOT NOW (it stays quiet for the cooldown anyway) or NOT TODAY (mute_today=True)."""
        if mute_today:
            scene = suggestion["scene"]
            self._muted_on_day[scene.get("id") or scene.get("name")] = day_key(now or time.time())

    # ---- internals ----

    def _all_triggers(self):
        """Every (scene, trigger, key) to look at: the scenes' own triggers, then the learned habits."""
        for scene in self.scenes:
            scene_id = scene.get("id") or scene.get("name")
            for index, trigger in enumerate(scene.get("triggers") or []):
                if isinstance(trigger, dict):
                    yield scene, trigger, (scene_id, index)
        scenes_by_id = {scene.get("id") or scene.get("name"): scene for scene in self.scenes}
        for habit in self.habit_triggers:
            scene = scenes_by_id.get(habit.get("scene_id"))
            if scene is not None:
                yield scene, habit, ("habit", habit["scene_id"], habit.get("at"))

    def _due_reason(self, trigger, key, now, front_app, idle_seconds, today):
        """Text explaining why the trigger fired, or None if it is not due."""
        kind = trigger.get("type")

        if kind == "app_focused":
            wanted_app = trigger.get("app")
            if not wanted_app or not front_app or not app_names_match(front_app, wanted_app):
                self._focus_started.pop(key, None)
                return None
            started = self._focus_started.setdefault(key, now)
            try:
                needed_seconds = float(trigger.get("seconds", DEFAULT_FOCUS_SECONDS))
            except (TypeError, ValueError):
                needed_seconds = DEFAULT_FOCUS_SECONDS
            if now - started < needed_seconds:
                return None
            self._focus_started.pop(key, None)
            return f"{front_app} is open"

        if kind == "time":
            if time.strftime("%a", time.localtime(now)) not in (trigger.get("days") or WEEKDAYS):
                return None
            target_minutes = parse_clock_time(trigger.get("at"))
            if target_minutes is None:
                return None
            local = time.localtime(now)
            minutes_now = local.tm_hour * 60 + local.tm_min
            try:
                window = float(trigger.get("window_minutes", TIME_WINDOW_MINUTES))
            except (TypeError, ValueError):
                window = TIME_WINDOW_MINUTES
            if not target_minutes <= minutes_now < target_minutes + window:
                return None
            if self._time_shown_on_day.get(key) == today:    # only once a day
                return None
            self._time_shown_on_day[key] = today
            return trigger.get("reason") or f"It's {trigger['at']}"

        if kind == "idle":
            if idle_seconds is None:
                return None
            try:
                minutes = float(trigger.get("minutes", 10))
            except (TypeError, ValueError):
                minutes = 10
            if idle_seconds >= minutes * 60 and self._idle_ready.get(key, True):
                self._idle_ready[key] = False                # once per stretch away
                return f"No activity for {minutes:g} minutes"
        return None
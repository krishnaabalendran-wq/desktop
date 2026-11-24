import json
import os
import time

HISTORY_FILE = "history.json"
KEEP_DAYS = 60                   # older entries are dropped
FLUSH_SECONDS = 60               # app time is kept in memory and written to disk this often

# Edit this table to change how apps are grouped in the recap. The first group whose words
# appear in the app's name wins; anything else is "Other".
APP_CATEGORIES = [
    ("Meetings", ("zoom", "teams", "webex", "meet", "facetime")),
    ("Coding", ("code", "pycharm", "terminal", "iterm", "xcode", "cursor", "powershell", "cmd",
                "windowsterminal", "intellij", "sublime", "idle")),
    ("Chat", ("slack", "discord", "messages", "whatsapp", "telegram", "outlook", "mail")),
    ("Docs", ("word", "winword", "excel", "powerpoint", "powerpnt", "keynote", "pages",
              "numbers", "notion", "onenote", "acrobat", "preview")),
    ("Browser", ("chrome", "safari", "firefox", "edge", "brave", "opera")),
]


def day_key(epoch_seconds):
    """'2026-11-23' for the local date of an epoch time."""
    return time.strftime("%Y-%m-%d", time.localtime(epoch_seconds))


class History:
    def __init__(self, path=HISTORY_FILE):
        self.path = path
        self.runs = []                   # one dictionary per scene run
        self.app_seconds = {}            # "2026-11-23" -> {"Keynote": 123.0, ...}
        self._dirty = False              # True when there is something not yet written to disk
        self._last_flush = time.monotonic()
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r") as history_file:
                data = json.load(history_file)
            self.runs = [run for run in data.get("runs", []) if isinstance(run, dict)]
            self.app_seconds = {day: apps for day, apps in data.get("app_seconds", {}).items()
                                if isinstance(apps, dict)}
        except (OSError, ValueError, AttributeError) as error:
            print("history.json could not be read:", error)        # carry on with an empty history

    def log_scene_run(self, summary):
        """Record one finished scene run. `summary` comes from SceneRunner.summary()."""
        states = [step["state"] for step in summary.get("steps", [])]
        self.runs.append({
            "scene_id": summary.get("scene_id"),
            "scene_name": summary.get("scene_name"),
            "at": summary.get("started_at"),
            "seconds": round(summary.get("seconds") or 0, 1),
            "outcome": summary.get("outcome"),
            "steps_total": len(states),
            "steps_done": states.count("done"),
            "steps_failed": states.count("failed"),
        })
        self._dirty = True
        self.flush()                     # runs are rare, so save straight away

    def add_app_seconds(self, app_name, seconds, now=None):
        """Add time to an app for today. Written to disk later by flush_if_due()."""
        day = day_key(now or time.time())
        apps = self.app_seconds.setdefault(day, {})
        apps[app_name] = apps.get(app_name, 0.0) + seconds
        self._dirty = True

    def flush_if_due(self):
        if self._dirty and time.monotonic() - self._last_flush >= FLUSH_SECONDS:
            self.flush()

    def flush(self):
        """Write to disk (to a temporary file first, so a crash can't leave a half-written file)."""
        if not self._dirty:
            return
        self._prune()
        temp_file_name = self.path + ".tmp"
        try:
            with open(temp_file_name, "w") as temp_file:
                json.dump({"runs": self.runs, "app_seconds": self.app_seconds}, temp_file)
            os.replace(temp_file_name, self.path)
        except OSError as error:
            print("history.json could not be saved:", error)
            return
        self._dirty = False
        self._last_flush = time.monotonic()

    def _prune(self):
        """Drop entries older than KEEP_DAYS."""
        cutoff = time.time() - KEEP_DAYS * 86400
        self.runs = [run for run in self.runs if (run.get("at") or 0) >= cutoff]
        oldest_day = day_key(cutoff)
        self.app_seconds = {day: apps for day, apps in self.app_seconds.items() if day >= oldest_day}


# ---- the daily recap ----

def categorize_app(app_name):
    """'Keynote' -> 'Docs', 'Google Chrome' -> 'Browser', anything unknown -> 'Other'."""
    lowered = str(app_name).lower()
    for category, words in APP_CATEGORIES:
        if any(word in lowered for word in words):
            return category
    return "Other"


def day_recap(history, date_key):
    """What happened on one day: {"runs": [...], "categories": [(category, seconds), ...]}."""
    runs = sorted((run for run in history.runs if run.get("at") and day_key(run["at"]) == date_key),
                  key=lambda run: run["at"])
    totals = {}
    for app_name, seconds in history.app_seconds.get(date_key, {}).items():
        category = categorize_app(app_name)
        totals[category] = totals.get(category, 0.0) + seconds
    categories = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    return {"runs": runs, "categories": categories}


def format_duration(seconds):
    """3725 -> '1h 02m', 720 -> '12m', 20 -> '<1m'."""
    minutes = int(seconds // 60)
    if minutes < 1:
        return "<1m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def recap_lines(recap, app_awareness_on):
    """The recap as a list of text lines for the full-screen panel (monospace, so columns line up)."""
    lines = []
    runs = recap["runs"]
    if not runs:
        lines.append("No scenes run today.")
    else:
        lines.append(f"SCENES RUN  {len(runs)}")
        for run in runs:
            clock = time.strftime("%H:%M", time.localtime(run["at"]))
            name = (run.get("scene_name") or "?")[:16].ljust(16)
            total, done, failed = run.get("steps_total", 0), run.get("steps_done", 0), run.get("steps_failed", 0)
            if run.get("outcome") == "stopped":
                result = "stopped"
            elif failed:
                result = f"{done}/{total} steps, {failed} failed"
            else:
                result = f"{done}/{total} steps  {run.get('seconds', 0):.1f} s"
            lines.append(f"  {clock}  {name}  {result}")

    lines.append("")
    if not app_awareness_on:
        lines.append("APP TIME  off (turn on APP AWARENESS in settings)")
    elif not recap["categories"]:
        lines.append("APP TIME  nothing recorded yet")
    else:
        lines.append("APP TIME")
        for category, seconds in recap["categories"]:
            lines.append(f"  {category.ljust(10)} {format_duration(seconds)}")
    return lines
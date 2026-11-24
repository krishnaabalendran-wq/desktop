import subprocess
import textwrap
import time
import webbrowser
import os
from datetime import datetime
from urllib.parse import quote_plus

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30
MAX_WAIT_SECONDS = 3600


class SceneContext:
    "The few things a step may need from the app window. The App fills these in."

    def __init__(self):
        pass


class StepOutcome:
    """How a finished step went."""

    def __init__(self, ok, message=""):
        self.ok = ok
        self.message = message


class RunningStep:
    """Something the runner checks on every 100 ms until it finishes."""

    def poll(self):
        """Return a StepOutcome once finished, or None while still running."""
        raise NotImplementedError

    def cancel(self):
        """Called when the user presses STOP while this step is running."""


class InstantStep(RunningStep):
    """A step that was already finished when it started."""

    def __init__(self, ok=True, message=""):
        self.outcome = StepOutcome(ok, message)

    def poll(self):
        return self.outcome


class WaitStep(RunningStep):
    """Does nothing for a number of seconds."""

    def __init__(self, seconds):
        self.end_time = time.monotonic() + seconds

    def poll(self):
        return StepOutcome(True) if time.monotonic() >= self.end_time else None


class ProcessStep(RunningStep):
    """A command running in the background. It is finished when the process exits."""

    def __init__(self, process, timeout_seconds):
        self.process = process
        self.deadline = time.monotonic() + timeout_seconds

    def poll(self):
        exit_code = self.process.poll()
        if exit_code is None:
            if time.monotonic() > self.deadline:
                self.cancel()
                return StepOutcome(False, "timed out")
            return None
        return StepOutcome(exit_code == 0, "" if exit_code == 0 else f"exit code {exit_code}")

    def cancel(self):
        if self.process.poll() is None:
            self.process.terminate()

def _start_process(command, use_shell, timeout_seconds):
    """Start a macOS program without waiting for it."""
    try:
        process = subprocess.Popen(command, shell=use_shell, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,)
    except OSError as error:
        return InstantStep(False, str(error))
    return ProcessStep(process, timeout_seconds)

def _step_run_command(step, context):
    command = str(step.get("command", "")).strip()
    if not command:
        return InstantStep(False, "no command set")
    try:
        timeout_seconds = float(step.get("timeout", DEFAULT_COMMAND_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_COMMAND_TIMEOUT_SECONDS
    return _start_process(command, True, timeout_seconds)

def _step_open_app(step, context):
    app_name = str(step.get("app", "")).strip()
    if not app_name:
        return InstantStep(False, "no app set")
    command = ["open", "-a", app_name]
    return _start_process(command, False, 10)

def _step_open_link(step, context):
    url = str(step.get("url", "")).strip()
    if not url:
        return InstantStep(False, "no link set")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    opened = webbrowser.open(url)
    return InstantStep(opened, "" if opened else "could not open the browser")

def _step_set_volume(step, context):
    try:
        percent = int(step.get("percent"))
    except (TypeError, ValueError):
        return InstantStep(False, "percent must be a number from 0 to 100")
    if not 0 <= percent <= 100:
        return InstantStep(False, "percent must be a number from 0 to 100")
    try:
        from volume import set_system_volume
    except ImportError:
        return InstantStep(False, "volume.py not found")
    set_system_volume(percent)
    return InstantStep(True)

def _step_send_notification(step, context):
    title = str(step.get("title", "Scene")).strip()
    text = str(step.get("text", "")).strip()

    if not text:
        return InstantStep(False, "no notification text set")
    try:
        import requests
    except ImportError:
        return InstantStep(False, "requests is not installed")
    try:
        response = requests.post(
            "https://ntfy.sh/thomass-deck",
            data=text.encode("utf-8"),
            headers={"Title": title},
            timeout=10,
        )
    except requests.RequestException as error:
        return InstantStep(False, f"notification failed: {error}")
    return InstantStep(response.ok, "" if response.ok else f"HTTP {response.status_code}")


def _step_open_path(step, context):
    path = os.path.expanduser(str(step.get("path", "")).strip())
    if not path:
        return InstantStep(False, "no path set")
    if not os.path.exists(path):
        return InstantStep(False, "path does not exist")
    return _start_process(["open", path], False, 10)


def _step_open_file(step, context):
    path = os.path.expanduser(str(step.get("path", "")).strip())
    if not path:
        return InstantStep(False, "no file set")
    if not os.path.isfile(path):
        return InstantStep(False, "file does not exist")
    return _start_process(["open", path], False, 10)


def _step_create_folder(step, context):
    name = str(step.get("name", "")).strip()
    parent = os.path.expanduser(str(step.get("parent", "~/Documents")).strip())
    if not name:
        return InstantStep(False, "no folder name set")
    name = name.replace("{date}", datetime.now().strftime("%Y-%m-%d"))
    name = name.replace("{time}", datetime.now().strftime("%H-%M-%S"))
    folder = os.path.join(parent, name)
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as error:
        return InstantStep(False, str(error))
    return _start_process(["open", folder], False, 10)


def _step_sleep_mac(step, context):
    return _start_process(["pmset", "sleepnow"], False, 5)


def _step_web_search(step, context):
    query = str(step.get("query", "")).strip()

    if not query:
        return InstantStep(False, "no search query set")

    query = query.replace("{date}", datetime.now().strftime("%Y-%m-%d"))
    url = f"https://www.google.com/search?q={quote_plus(query)}"

    opened = webbrowser.open(url)
    return InstantStep(opened, "" if opened else "could not open the browser")


def _step_wait(step, context):
    try:
        seconds = float(step.get("seconds"))
    except (TypeError, ValueError):
        return InstantStep(False, "seconds must be a number")
    return WaitStep(max(0.0, min(seconds, MAX_WAIT_SECONDS)))

def _step_message(step, context):
    return InstantStep(True)

STEP_STARTERS = {
    "run_command": _step_run_command,
    "open_app": _step_open_app,
    "open_link": _step_open_link,
    "set_volume": _step_set_volume,
    "wait": _step_wait,
    "message": _step_message,
    "send_notification": _step_send_notification,
    "open_path": _step_open_path,
    "open_file": _step_open_file,
    "create_folder": _step_create_folder,
    "sleep_mac": _step_sleep_mac,
    "web_search": _step_web_search,
}

def start_step(step, context):
    """Start one step and return the RunningStep to poll."""
    starter = STEP_STARTERS.get(step.get("type"))
    if starter is None:
        return InstantStep(False, f"unknown step type: {step.get('type')}")
    return starter(step, context)

def describe_step(step):
    """A short line describing a step, shown in the running panel."""
    kind = step.get("type")
    if kind == "run_command":
        text = "Run: " + str(step.get("command", "") or "(nothing set)")
    elif kind == "open_app":
        text = "Open app: " + str(step.get("app", "") or "(nothing set)")
    elif kind == "open_link":
        text = "Open link: " + str(step.get("url", "") or "(nothing set)")
    elif kind == "set_volume":
        text = f"Set volume to {step.get('percent')}%"
    elif kind == "wait":
        text = f"Wait {step.get('seconds')} s"
    elif kind == "message":
        text = str(step.get("text", ""))
    elif kind == "send_notification":
        text = f"Notify: {step.get('title', 'Scene')} — {step.get('text', '')}"
    elif kind == "open_path":
        text = "Open path: " + str(step.get("path", ""))
    elif kind == "open_file":
        text = "Open file: " + str(step.get("path", ""))
    elif kind == "create_folder":
        text = "Create folder: " + str(step.get("name", ""))
    elif kind == "sleep_mac":
        text = "Put the Mac to sleep"
    elif kind == "web_search":
        text = "Search: " + str(step.get("query", ""))
    else:
        text = f"Unknown step ({kind})"
    return textwrap.shorten(text, width=48, placeholder="...")
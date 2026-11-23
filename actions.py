import platform
import subprocess
import textwrap
import time
import webbrowser

SYSTEM = platform.system()
OS_KEYS = {"Darwin": "mac", "Windows": "windows", "Linux": "linux"}

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30
MAX_WAIT_SECONDS = 3600
PAGE_COUNT = 3


class SceneContext:
    "The few things a step may need from the app window. The App fills these in."

    def __init__(self, go_to_page=None, copy_to_clipboard=None, apply_layout=None):
        self.go_to_page = go_to_page
        self.copy_to_clipboard = copy_to_clipboard
        self.apply_layout = apply_layout

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


def pick_for_this_os(step, generic_key):
    """The value for this computer step["mac"] or step["windows"] if set, else step[generic_key]."""
    return step.get(OS_KEYS.get(SYSTEM, "")) or step.get(generic_key)

def _start_process(command, use_shell, timeout_seconds):
    """Start a program without waiting for it. Returns a ProcessStep (or a failed InstantStep)."""
    extra_options = {}
    if SYSTEM == "Windows":
        extra_options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(command, shell=use_shell, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra_options)
    except OSError as error:
        return InstantStep(False, str(error))
    return ProcessStep(process, timeout_seconds)

def _step_run_command(step, context):
    command = pick_for_this_os(step, "command")
    if not command:
        return InstantStep(False, "no command for this computer")
    try:
        timeout_seconds = float(step.get("timeout", DEFAULT_COMMAND_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_COMMAND_TIMEOUT_SECONDS
    return _start_process(command, True, timeout_seconds)

def _step_open_app(step, context):
    app_name = pick_for_this_os(step, "app")
    if not app_name:
        return InstantStep(False, "no app set for this computer")
    if SYSTEM == "Darwin":
        command = ["open", "-a", app_name]
    elif SYSTEM == "Windows":
        command = ["cmd", "/c", "start", "", app_name]
    else:
        command = [app_name]
    return _start_process(command, False, 10)

def _step_open_link(step, context):
    url = (pick_for_this_os(step, "url") or "").strip()
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

def _step_go_to_page(step, context):
    try:
        page_number = int(step.get("page"))
    except (TypeError, ValueError):
        return InstantStep(False, "page must be a number")
    if not 1 <= page_number <= PAGE_COUNT:
        return InstantStep(False, f"page must be 1 to {PAGE_COUNT}")
    if context is None or context.go_to_page is None:
        return InstantStep(False, "cannot change page here")
    context.go_to_page(page_number - 1)
    return InstantStep(True)

def _step_copy_text(step, context):
    text = str(step.get("text", ""))
    if context is None or context.copy_to_clipboard is None:
        return InstantStep(False, "clipboard not available")
    context.copy_to_clipboard(text)
    return InstantStep(True)

def _step_apply_layout(step, context):
    reference = str(step.get("layout", "")).strip()
    if not reference:
        return InstantStep(False, "no layout set")
    if context is None or context.apply_layout is None:
        return InstantStep(False, "cannot change layout here")
    try:
        skipped = context.apply_layout(reference)
    except LookupError as error:
        return InstantStep(False, str(error))
    if skipped:
        return InstantStep(False, f"{skipped} widget(s) could not be placed")
    return InstantStep(True)

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
    "go_to_page": _step_go_to_page,
    "copy_text": _step_copy_text,
    "wait": _step_wait,
    "message": _step_message,
    "apply_layout": _step_apply_layout
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
        text = "Run: " + (pick_for_this_os(step, "command") or "(nothing set for this computer)")
    elif kind == "open_app":
        text = "Open app: " + (pick_for_this_os(step, "app") or "(nothing set for this computer)")
    elif kind == "open_link":
        text = "Open link: " + (pick_for_this_os(step, "url") or "(nothing set)")
    elif kind == "set_volume":
        text = f"Set volume to {step.get('percent')}%"
    elif kind == "go_to_page":
        text = f"Go to page {step.get('page')}"
    elif kind == "copy_text":
        text = "Copy text: " + str(step.get("text", ""))
    elif kind == "wait":
        text = f"Wait {step.get('seconds')} s"
    elif kind == "message":
        text = str(step.get("text", ""))
    elif kind == "apply_layout":
        text = "Apply layout: " + (str(step.get("layout") or "") or "(nothing set)")
    else:
        text = f"Unknown step ({kind})"
    return textwrap.shorten(text, width=48, placeholder="...")
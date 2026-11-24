import ctypes
import platform
import re
import subprocess

SYSTEM = platform.system()
COMMAND_TIMEOUT_SECONDS = 2 # a system tool that takes longer than this is ignored

DECK_APP_NAMES = {"python", "python3", "pythonw", "python launcher"}


def _run(args):
    """Run a system tool and return what it printed."""
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=COMMAND_TIMEOUT_SECONDS).stdout


# ---- macOS ----

def parse_lsappinfo_name(text):
    """Pull the app name out of lsappinfo's output, e.g. '"LSDisplayName"="Safari"' -> 'Safari'."""
    match = re.search(r'=\s*"(.*)"', text)
    return match.group(1) if match else None


def parse_hid_idle_seconds(text):
    """Pull the idle time out of ioreg's output. It is given in nanoseconds: '"HIDIdleTime" = 4200000000'."""
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', text)
    return int(match.group(1)) / 1_000_000_000 if match else None


def _mac_frontmost_app():
    # lsappinfo is built into macOS: no install and no permission prompt.
    try:
        front = _run(["lsappinfo", "front"]).strip()               # e.g. "ASN:0x0-0x24024:"
        if not front:
            return None
        return parse_lsappinfo_name(_run(["lsappinfo", "info", "-only", "name", front]))
    except (OSError, subprocess.TimeoutExpired):
        return None


def _mac_idle_seconds():
    try:
        return parse_hid_idle_seconds(_run(["ioreg", "-c", "IOHIDSystem"]))
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---- Windows (plain ctypes, nothing to install) ----

class _LastInputInfo(ctypes.Structure):
    """The structure Windows fills in for GetLastInputInfo."""
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _windows_frontmost_app():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # Say exactly what each function takes and returns, so 64-bit handles aren't cut short
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    window = user32.GetForegroundWindow()
    if not window:
        return None
    process_id = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, process_id.value)
    if not process_handle:
        return None                          # e.g. a protected system window
    try:
        path_buffer = ctypes.create_unicode_buffer(1024)
        path_length = ctypes.c_ulong(len(path_buffer))
        if kernel32.QueryFullProcessImageNameW(process_handle, 0, path_buffer, ctypes.byref(path_length)):
            return path_buffer.value.replace("\\", "/").split("/")[-1]      # "C:\...\POWERPNT.EXE" -> "POWERPNT.EXE"
        return None
    finally:
        kernel32.CloseHandle(process_handle)


def _windows_idle_seconds():
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(_LastInputInfo)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    tick_count = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((tick_count - info.dwTime) & 0xFFFFFFFF) / 1000.0       # the mask handles the 49-day counter wrap


# ---- what the rest of the app calls ----

def get_frontmost_app():
    """Name of the app in front ("Keynote", "POWERPNT.EXE"), or None if unknown or it's the deck itself."""
    try:
        if SYSTEM == "Darwin":
            name = _mac_frontmost_app()
        elif SYSTEM == "Windows":
            name = _windows_frontmost_app()
        else:
            name = None
    except Exception:                        # a failed lookup must never break the app
        name = None
    if not name or name.strip().lower() in DECK_APP_NAMES:
        return None
    return name


def get_idle_seconds():
    """Seconds since the last keyboard, mouse or touch input anywhere on the computer, or None if unknown."""
    try:
        if SYSTEM == "Darwin":
            return _mac_idle_seconds()
        if SYSTEM == "Windows":
            return _windows_idle_seconds()
    except Exception:
        pass
    return None
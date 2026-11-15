"""Read and set the system output volume (macOS, Linux and Windows).

set_system_volume() never blocks the UI: requests are queued on a background
thread, and only the latest value is applied.
"""
import platform
import subprocess
import threading

SYSTEM = platform.system()


def _com_init():
    """Windows COM must be initialised on each thread that touches audio."""
    if SYSTEM == "Windows":
        try:
            import comtypes
            comtypes.CoInitialize()
        except ImportError:
            pass


def _run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=5)


def _windows_endpoint():
    # Needs: pip install pycaw
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def read_system_volume():
    """Current output volume 0-100, or None if it can't be read."""
    _com_init()
    try:
        if SYSTEM == "Darwin":
            out = _run(["osascript", "-e", "output volume of (get volume settings)"]).stdout
            return int(out.strip())
        if SYSTEM == "Linux":
            # e.g. "Volume: front-left: 32768 /  50% / -18.06 dB, ..."
            out = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]).stdout
            return int(out.split("/")[1].strip().rstrip("%"))
        if SYSTEM == "Windows":
            return round(_windows_endpoint().GetMasterVolumeLevelScalar() * 100)
    except (OSError, ValueError, IndexError, ImportError, subprocess.TimeoutExpired):
        pass
    return None


def _write_system_volume(percent):
    _com_init()
    try:
        if SYSTEM == "Darwin":
            _run(["osascript", "-e", f"set volume output volume {percent}"])
        elif SYSTEM == "Linux":
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        elif SYSTEM == "Windows":
            _windows_endpoint().SetMasterVolumeLevelScalar(percent / 100, None)
    except (OSError, ImportError, subprocess.TimeoutExpired):
        pass


class _VolumeWriter:
    """Applies the latest requested volume on one background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = None
        self._busy = False

    def set(self, percent):
        percent = max(0, min(100, int(round(percent))))
        with self._lock:
            self._pending = percent
            if self._busy:
                return          # the running worker will pick this value up
            self._busy = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        _com_init()
        while True:
            with self._lock:
                value = self._pending
                self._pending = None
                if value is None:
                    self._busy = False
                    return
            _write_system_volume(value)


_writer = _VolumeWriter()


def set_system_volume(percent):
    """Non-blocking: queue a new system volume (0-100)."""
    _writer.set(percent)
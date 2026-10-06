"""Small Windows-only helpers, with harmless stand-ins elsewhere so the app can be tested on any OS."""
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

IS_WIN = os.name == "nt"
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


class Hotkey:
    """Global shortcut through RegisterHotKey. Works while a game has focus."""

    def __init__(self, callback):
        self.callback = callback
        self.thread = None
        self.tid = None
        self.ok = False
        self.error = ""

    def set(self, mods, vk):
        self.clear()
        if not IS_WIN:
            self.ok = True
            return True
        ready = threading.Event()

        def loop():
            self.tid = kernel32.GetCurrentThreadId()
            self.ok = bool(user32.RegisterHotKey(None, 1, int(mods) | MOD_NOREPEAT, int(vk)))
            self.error = "" if self.ok else "That shortcut is already used by another app. Pick a different one."
            ready.set()
            if not self.ok:
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    threading.Thread(target=self.callback, daemon=True).start()
            user32.UnregisterHotKey(None, 1)

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()
        ready.wait(3)
        return self.ok

    def clear(self):
        if IS_WIN and self.thread and self.thread.is_alive() and self.tid:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
            self.thread.join(2)
        self.thread = None


OWN_TITLES = {"Rewind", ""}


def foreground_title():
    """Title of the window in front, used to name clips after the game."""
    if not IS_WIN:
        return os.environ.get("REWIND_FAKE_TITLE", "Desktop")
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    t = buf.value.strip()
    return "Desktop" if t in OWN_TITLES or t.lower() in ("program manager",) else t


def monitors():
    if not IS_WIN:
        return [{"index": 0, "label": "Display 1 (1920×1080)"}]
    out = []

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("rc", RECT), ("work", RECT), ("flags", ctypes.c_ulong)]

    found = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_double)

    def cb(hmon, hdc, rect, data):
        mi = MONITORINFO()
        mi.cb = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(mi))
        found.append((mi.rc.r - mi.rc.l, mi.rc.b - mi.rc.t, bool(mi.flags & 1)))
        return 1

    user32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    found.sort(key=lambda m: not m[2])  # primary first, matches the capture order on most PCs
    for i, (w, h, primary) in enumerate(found):
        out.append({"index": i, "label": f"Display {i + 1} ({w}×{h})" + (" · main" if primary else "")})
    return out or [{"index": 0, "label": "Display 1"}]


# ---------------------------------------------------------------- sounds
#
# Synthesised once into small wav files (48 kHz stereo), cached per sound and volume.
# Each is designed to be heard over game audio without being harsh:
#   chime   two glassy bell notes rising a fifth, with a short airy tail
#   shutter a soft camera shutter: two filtered clicks and a tiny whoosh
#   pop     a round bubble pop that bends upward
#   error   two low, soft notes falling (only when a save fails)

SOUND_RATE = 48000
VOLUMES = {"quiet": 0.35, "medium": 0.6, "loud": 0.9}


def _np():
    import numpy as np
    return np


def _env(np, n, attack, decay):
    t = np.arange(n) / SOUND_RATE
    a = np.minimum(1, t / max(attack, 1e-4))
    return a * np.exp(-t / decay)


def _bell(np, freq, dur, decay):
    n = int(SOUND_RATE * dur)
    t = np.arange(n) / SOUND_RATE
    # bell-like partials (slightly inharmonic), the higher ones fading faster
    out = np.zeros(n)
    for ratio, amp, dk in ((1.0, 1.0, 1.0), (2.0, 0.32, 0.55), (2.76, 0.18, 0.35), (4.07, 0.07, 0.2)):
        out += amp * np.sin(2 * np.pi * freq * ratio * t + ratio) * np.exp(-t / (decay * dk))
    return out * np.minimum(1, t / 0.003)


def _place(np, buf, sig, at):
    i = int(at * SOUND_RATE)
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def _space(np, mono, width=0.012, wet=0.18):
    """Tiny stereo room: offset echoes on each side so it feels placed, not beepy."""
    l, r = mono.copy(), mono.copy()
    for k, (dl, dr) in enumerate(((0.023, 0.031), (0.047, 0.041), (0.071, 0.083))):
        g = wet * (0.6 ** k)
        il, ir = int(dl * SOUND_RATE), int(dr * SOUND_RATE)
        l[il:] += g * mono[:-il]
        r[ir:] += g * mono[:-ir]
    d = int(width * SOUND_RATE / 4)
    r = np.concatenate([np.zeros(d), r[:-d]])
    return np.stack([l, r], axis=1)


def _lowpass(np, x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SOUND_RATE)
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def _synth(name):
    np = _np()
    rng = np.random.default_rng(7)
    if name == "chime":
        buf = np.zeros(int(SOUND_RATE * 0.9))
        _place(np, buf, 0.55 * _bell(np, 1174.7, 0.8, 0.22), 0.0)     # D6
        _place(np, buf, 0.75 * _bell(np, 1760.0, 0.8, 0.30), 0.085)   # A6, a fifth up
        sig = _space(np, buf)
    elif name == "shutter":
        buf = np.zeros(int(SOUND_RATE * 0.35))
        for at, amp, cut in ((0.0, 1.0, 5000), (0.075, 0.7, 3800)):
            n = int(SOUND_RATE * 0.035)
            click = rng.standard_normal(n) * _env(np, n, 0.0005, 0.006)
            click = _lowpass(np, click, cut) * 2.2
            body = 0.5 * np.sin(2 * np.pi * 180 * np.arange(n) / SOUND_RATE) * _env(np, n, 0.001, 0.012)
            _place(np, buf, amp * (click + body), at)
        n = int(SOUND_RATE * 0.12)
        whoosh = _lowpass(np, rng.standard_normal(n), 1800) * np.sin(np.linspace(0, np.pi, n)) * 0.12
        _place(np, buf, whoosh, 0.02)
        sig = _space(np, buf, wet=0.1)
    elif name == "pop":
        n = int(SOUND_RATE * 0.22)
        t = np.arange(n) / SOUND_RATE
        f = 380 + 900 * (1 - np.exp(-t / 0.03))                         # pitch bends upward
        ph = 2 * np.pi * np.cumsum(f) / SOUND_RATE
        buf = (np.sin(ph) + 0.15 * np.sin(2 * ph)) * _env(np, n, 0.002, 0.045)
        sig = _space(np, np.concatenate([buf, np.zeros(int(SOUND_RATE * 0.1))]), wet=0.12)
    else:  # error
        buf = np.zeros(int(SOUND_RATE * 0.5))
        for at, fr in ((0.0, 523.25), (0.13, 392.0)):                  # C5 then G4, falling
            n = int(SOUND_RATE * 0.3)
            t = np.arange(n) / SOUND_RATE
            tone = (np.sin(2 * np.pi * fr * t) + 0.2 * np.sin(4 * np.pi * fr * t)) * _env(np, n, 0.006, 0.09)
            _place(np, buf, tone, at)
        sig = _space(np, buf, wet=0.1)
    # fade the very end so nothing clicks, then normalise
    fade = min(len(sig), int(SOUND_RATE * 0.03))
    sig[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return sig / max(1e-9, np.abs(sig).max())


def sound_file(name, volume="medium"):
    name = name if name in ("chime", "shutter", "pop", "error") else "chime"
    p = Path(tempfile.gettempdir()) / f"rewind-{name}-{volume}-v2.wav"
    if not p.exists():
        np = _np()
        sig = _synth(name) * VOLUMES.get(volume, 0.6) * 0.95
        data = (np.clip(sig, -1, 1) * 32767).astype("<i2").tobytes()
        with wave.open(str(p), "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SOUND_RATE); w.writeframes(data)
    return p


def play_sound(name, volume="medium"):
    if not IS_WIN or name == "off":
        return
    try:
        import winsound
        winsound.PlaySound(str(sound_file(name, volume)), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def play_saved_sound(name="chime", volume="medium"):
    play_sound(name, volume)


def play_error_sound(volume="medium"):
    play_sound("error", volume)


def reveal(path):
    if IS_WIN:
        subprocess.Popen(["explorer", "/select,", str(path)])


def open_folder(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    if IS_WIN:
        os.startfile(str(path))


def default_clips_dir():
    if IS_WIN:
        try:
            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_MYVIDEO = 0x0E
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0E, None, 0, buf)
            if buf.value:
                return str(Path(buf.value) / "Rewind")
        except Exception:
            pass
    return str(Path.home() / "Videos" / "Rewind")


def to_recycle_bin(path):
    """Move a file to the Recycle Bin so a mistaken delete can be undone."""
    try:
        from send2trash import send2trash
        send2trash(str(path))
        return
    except ImportError:
        pass
    if IS_WIN:
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOps", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        op = SHFILEOPSTRUCTW(None, 3, str(path) + "\0", None, 0x40 | 0x10 | 0x400 | 0x4, False, None, None)
        if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0:
            return
    Path(path).unlink()

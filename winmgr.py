"""Moving, resizing and snapping Rewind's frameless window.

The page tells us when a drag or a resize starts, moves and ends, and everything else is worked out here from the real
cursor position in real screen pixels, so it behaves the same on scaled (125%, 150%) and multi-monitor setups.
Drag to the top of the screen to fill it, to a side to fill that half, grab any edge or corner to resize."""
import ctypes
import os
import threading
from ctypes import wintypes as w

IS_WIN = os.name == "nt"
MIN_W, MIN_H = 900, 600          # logical pixels, same as the window's min_size

if IS_WIN:
    # private copies, so argtypes here never change what other code in the app sees
    user32 = ctypes.WinDLL("user32")
    user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
    user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.MonitorFromPoint.argtypes = [w.POINT, w.DWORD]
    user32.MonitorFromPoint.restype = w.HANDLE
    user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
    user32.MonitorFromWindow.restype = w.HANDLE
    user32.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.c_void_p]
    user32.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
    user32.FindWindowW.restype = w.HWND
    user32.IsWindow.argtypes = [w.HWND]
    dwm = ctypes.WinDLL("dwmapi")
    dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
    user32.IsWindowVisible.argtypes = [w.HWND]
    user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("rc", w.RECT), ("work", w.RECT), ("flags", w.DWORD)]

SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10


class Manager:
    def __init__(self, get_window, on_change=None):
        self.get_window = get_window
        self.on_change = on_change
        self.hwnd = None
        self.lock = threading.Lock()
        self.restore_rect = None      # where the window was before it was maximized or snapped
        self.state = "normal"         # normal | max | half
        self.op = None

    # ---- helpers
    def _hwnd(self):
        if self.hwnd and user32.IsWindow(self.hwnd):
            return self.hwnd
        h = None
        try:
            h = int(self.get_window().native.Handle.ToInt64())
        except Exception:
            pass
        if not h:
            h = self._find_own_window()
        self.hwnd = h
        return h

    @staticmethod
    def _find_own_window():
        """The biggest visible window of this process (the tray icon has a hidden one with the same title)."""
        best = [0, 0]
        pid = os.getpid()
        PROC = ctypes.WINFUNCTYPE(ctypes.c_int, w.HWND, w.LPARAM)

        def cb(hwnd, _):
            p = w.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid and user32.IsWindowVisible(hwnd):
                r = w.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                area = (r.right - r.left) * (r.bottom - r.top)
                if area > best[0]:
                    best[0], best[1] = area, hwnd
            return 1
        user32.EnumWindows(PROC(cb), 0)
        return best[1]

    @staticmethod
    def _cursor():
        p = w.POINT()
        user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _rect(self):
        r = w.RECT()
        user32.GetWindowRect(self._hwnd(), ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    @staticmethod
    def _mon(handle):
        mi = MONITORINFO()
        mi.cb = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(handle, ctypes.byref(mi))
        return (mi.rc.left, mi.rc.top, mi.rc.right, mi.rc.bottom), (mi.work.left, mi.work.top, mi.work.right, mi.work.bottom)

    def _min(self):
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(self._hwnd()) / 96.0
        except Exception:
            dpi = 1.0
        return int(MIN_W * dpi), int(MIN_H * dpi)

    def _put(self, l, t, r, b):
        user32.SetWindowPos(self._hwnd(), None, int(l), int(t), int(r - l), int(b - t), SWP_NOZORDER | SWP_NOACTIVATE)

    def _put_pos(self, l, t):
        user32.SetWindowPos(self._hwnd(), None, int(l), int(t), 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

    # ---- remembering where the window was
    def geometry(self):
        r = self.restore_rect if self.state != "normal" and self.restore_rect else self._rect()
        return {"rect": list(r), "state": self.state}

    def _changed(self):
        if self.on_change:
            try:
                self.on_change(self.geometry())
            except Exception:
                pass

    def apply(self, geom):
        """Put the window back where it was last time, if that place still exists."""
        try:
            l, t, r, b = [int(v) for v in geom["rect"]]
            if r - l < 300 or b - t < 200:
                return
            mon = user32.MonitorFromPoint(w.POINT((l + r) // 2, t + 30), 0)       # 0: no monitor there any more
            if not mon:
                return
            _, work = self._mon(mon)
            ww, hh = min(r - l, work[2] - work[0]), min(b - t, work[3] - work[1])
            l = min(max(l, work[0]), work[2] - ww)
            t = min(max(t, work[1]), work[3] - hh)
            self._put(l, t, l + ww, t + hh)
            if geom.get("state") == "max":
                self.restore_rect = (l, t, l + ww, t + hh)
                self.maximize()
        except Exception:
            pass

    # ---- states
    def _flush(self, flush):
        """Windows 11 rounds a window's corners and draws a thin border around it. Filling the screen should look
        properly full, with nothing of the desktop behind showing at the sides, top or corners."""
        try:
            corner = ctypes.c_int(1 if flush else 0)                                   # 1: don't round, 0: Windows' default
            border = ctypes.c_uint(0xFFFFFFFE if flush else 0xFFFFFFFF)               # no border / the default one
            dwm.DwmSetWindowAttribute(self._hwnd(), 33, ctypes.byref(corner), 4)
            dwm.DwmSetWindowAttribute(self._hwnd(), 34, ctypes.byref(border), 4)
        except Exception:
            pass

    def maximize(self):
        with self.lock:
            if self.state == "normal":
                self.restore_rect = self._rect()
            _, work = self._mon(user32.MonitorFromWindow(self._hwnd(), 2))
            self._flush(True)
            self._put(*work)
            self.state = "max"

    def restore(self):
        with self.lock:
            self._restore_locked()

    def _restore_locked(self):
        r = self.restore_rect
        if r:
            # keep it on a screen that still exists
            _, work = self._mon(user32.MonitorFromPoint(w.POINT((r[0] + r[2]) // 2, (r[1] + r[3]) // 2), 2))
            ww, hh = r[2] - r[0], r[3] - r[1]
            l = min(max(r[0], work[0]), max(work[0], work[2] - ww))
            t = min(max(r[1], work[1]), max(work[1], work[3] - hh))
            self._put(l, t, l + ww, t + hh)
        self._flush(False)
        self.state = "normal"

    def toggle_maximize(self):
        if self.state == "normal":
            self.maximize()
        else:
            self.restore()
        self._changed()
        return self.state == "max"

    def snap_half(self, side):
        with self.lock:
            if self.state == "normal":
                self.restore_rect = self._rect()
            _, work = self._mon(user32.MonitorFromWindow(self._hwnd(), 2))
            mid = (work[0] + work[2]) // 2
            self._flush(True)
            self._put(*((work[0], work[1], mid, work[3]) if side == "left" else (mid, work[1], work[2], work[3])))
            self.state = "half"

    # ---- dragging
    def drag_start(self):
        with self.lock:
            cx, cy = self._cursor()
            l, t, r, b = self._rect()
            if self.state != "normal" and self.restore_rect:
                # pulling a maximized or snapped window away: it returns to its old size under the cursor
                rl, rt, rr, rb = self.restore_rect
                ww, hh = rr - rl, rb - rt
                frac = (cx - l) / max(1, r - l)
                nl = cx - int(frac * ww)
                nt = cy - min(cy - t, 24)
                self._put(nl, nt, nl + ww, nt + hh)
                self._flush(False)
                self.state = "normal"
                l, t, r, b = nl, nt, nl + ww, nt + hh
            self.op = ("drag", cx, cy, l, t)

    def drag_move(self):
        op = self.op
        if not op or op[0] != "drag":
            return
        cx, cy = self._cursor()
        self._put_pos(op[3] + cx - op[1], op[4] + cy - op[2])

    def drag_end(self):
        """Returns the state the window ended up in: normal, max or half."""
        op, self.op = self.op, None
        if not op or op[0] != "drag":
            return self.state
        cx, cy = self._cursor()
        mon, _ = self._mon(user32.MonitorFromPoint(w.POINT(cx, cy), 2))
        if cy <= mon[1] + 1:
            self.maximize()
        elif cx <= mon[0] + 1:
            self.snap_half("left")
        elif cx >= mon[2] - 2:
            self.snap_half("right")
        self._changed()
        return self.state

    # ---- resizing
    def resize_start(self, edge):
        with self.lock:
            if self.state != "normal":
                return
            cx, cy = self._cursor()
            self.op = ("resize", cx, cy, self._rect(), str(edge))

    def resize_move(self):
        op = self.op
        if not op or op[0] != "resize":
            return
        cx, cy = self._cursor()
        dx, dy = cx - op[1], cy - op[2]
        l, t, r, b = op[3]
        edge = op[4]
        mw, mh = self._min()
        if "e" in edge:
            r = max(l + mw, r + dx)
        if "w" in edge:
            l = min(r - mw, l + dx)
        if "s" in edge:
            b = max(t + mh, b + dy)
        if "n" in edge:
            t = min(b - mh, t + dy)
        self._put(l, t, r, b)

    def resize_end(self):
        self.op = None
        self._changed()

"""The "Clip captured" card that slides in at the top left of the screen being recorded.

It is a real Windows layered window with per-pixel transparency, drawn with Pillow, so the corners and the glow are
smooth. It never takes focus, lets mouse clicks pass through, and is hidden from screen capture where Windows
allows it, so it doesn't end up in the clips."""
import ctypes
import os
import threading
import time
from ctypes import wintypes as w

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

IS_WIN = os.name == "nt"
SHOW_FOR = 3.3          # seconds on screen
SLIDE = 0.38
FADE = 0.5

ACCENT_A = (61, 139, 255)
ACCENT_B = (139, 92, 246)

_lock = threading.Lock()
_cancel = threading.Event()
_class_ready = False
_wndproc = None

if IS_WIN:
    user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", w.HANDLE), ("hIcon", w.HANDLE), ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE),
                    ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD), ("biBitCount", w.WORD),
                    ("biCompression", w.DWORD), ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG),
                    ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]

    user32.DefWindowProcW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       w.HWND, w.HANDLE, w.HANDLE, ctypes.c_void_p]
    user32.CreateWindowExW.restype = w.HWND
    user32.GetDC.argtypes = [w.HWND]
    user32.GetDC.restype = w.HDC
    user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
    user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    user32.DestroyWindow.argtypes = [w.HWND]
    user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.UpdateLayeredWindow.argtypes = [w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE), w.HDC,
                                           ctypes.POINTER(w.POINT), w.COLORREF, ctypes.POINTER(BLENDFUNCTION), w.DWORD]
    user32.UpdateLayeredWindow.restype = w.BOOL
    user32.SetWindowDisplayAffinity.argtypes = [w.HWND, w.DWORD]
    gdi32.CreateCompatibleDC.argtypes = [w.HDC]
    gdi32.CreateCompatibleDC.restype = w.HDC
    gdi32.CreateDIBSection.argtypes = [w.HDC, ctypes.POINTER(BITMAPINFOHEADER), ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
    gdi32.CreateDIBSection.restype = w.HBITMAP
    gdi32.SelectObject.argtypes = [w.HDC, w.HANDLE]
    gdi32.SelectObject.restype = w.HANDLE
    gdi32.DeleteObject.argtypes = [w.HANDLE]
    gdi32.DeleteDC.argtypes = [w.HDC]
    kernel32.GetModuleHandleW.restype = w.HANDLE


def _font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(draw, text, font, width):
    if draw.textlength(text, font=font) <= width:
        return text
    while len(text) > 1 and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _gradient(size, c1, c2):
    gp = np.zeros((size, size, 4), np.uint8)
    t = (np.add.outer(np.arange(size), np.arange(size)) / (2.0 * size))[..., None]
    gp[..., :3] = (np.array(c1) * (1 - t) + np.array(c2) * t).astype(np.uint8)
    gp[..., 3] = 255
    return Image.fromarray(gp, "RGBA")


def render_card(title, sub, badge="", scale=1.0):
    """A slim capsule: a rewind icon inside a ring that counts down, the title, and the game. Returns the image
    and where the ring goes (cx, cy, radius) for the animation."""
    ss = 3
    k = scale * ss
    pad = 22                                  # room around the capsule for the shadow
    ch = 66
    f_title = _font(["segoeuib.ttf", "seguisb.ttf", "arialbd.ttf"], int(18 * k))
    f_sub = _font(["segoeui.ttf", "arial.ttf"], int(13 * k))
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    tw = max(probe.textlength(title, font=f_title), min(probe.textlength(sub, font=f_sub), 250 * k))
    icon = 44
    cw = int(16 + icon + 14 + tw / k + 26)
    W, H = int((cw + pad * 2) * k), int((ch + pad * 2) * k)
    X0, Y0, X1, Y1 = int(pad * k), int(pad * k), int((pad + cw) * k), int((pad + ch) * k)
    rad = (Y1 - Y0) // 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((X0, Y0 + int(6 * k), X1, Y1 + int(6 * k)), rad, fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(11 * k)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((X0, Y0, X1, Y1), rad, fill=(13, 15, 21, 244))
    # lit edge: a brighter rim that fades out toward the bottom
    rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle((X0, Y0, X1, Y1), rad, outline=(255, 255, 255, 255), width=max(1, int(1.4 * k)))
    ra = np.asarray(rim).copy()
    fade = np.clip(0.9 - (np.arange(H) - Y0) / max(1, (Y1 - Y0)) * 0.75, 0.1, 1)
    ra[..., 3] = (ra[..., 3] * fade[:, None] * 0.22).astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(ra, "RGBA"))
    d = ImageDraw.Draw(img)

    # icon disc with a rewind symbol
    dia = int(icon * k)
    ix, iy = X0 + int(16 * k), Y0 + (Y1 - Y0 - dia) // 2
    disc = _gradient(dia, ACCENT_A, ACCENT_B)
    dm = Image.new("L", (dia, dia), 0)
    ImageDraw.Draw(dm).ellipse((0, 0, dia - 1, dia - 1), fill=255)
    img.paste(disc, (ix, iy), dm)
    cx, cy = ix + dia / 2, iy + dia / 2
    u = dia / 44
    for dx in (-5.5, 6.5):                   # two triangles pointing left
        d.polygon([(cx + (dx + 6) * u, cy - 8.5 * u), (cx + (dx + 6) * u, cy + 8.5 * u), (cx + (dx - 6.5) * u, cy)], fill=(255, 255, 255, 255))
        d.rounded_rectangle((cx + (dx - 7.5) * u, cy - 8.5 * u, cx + (dx - 5.2) * u, cy + 8.5 * u), 1, fill=(255, 255, 255, 255)) if False else None

    tx = ix + dia + int(14 * k)
    d.text((tx, Y0 + int(11 * k)), title, font=f_title, fill=(255, 255, 255, 255))
    d.text((tx, Y0 + int(36 * k)), _fit(d, sub, f_sub, X1 - tx - 20 * k), font=f_sub, fill=(142, 150, 170, 255))

    img = img.resize((W // ss, H // ss), Image.LANCZOS)
    s = scale
    ring = ((ix + dia / 2) / ss, (iy + dia / 2) / ss, dia / ss / 2 + 3.2 * s)
    return img, ring


def _frame(base, ring, frac):
    """One animation frame: the card plus the ring around the icon, which empties as the card runs out."""
    im = base.copy()
    cx, cy, r = ring
    q = 4
    n = int(2 * (r + 4)) * q
    patch = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    pd = ImageDraw.Draw(patch)
    c, rr, wd = n / 2, r * q, max(2, int(2.2 * q))
    pd.ellipse((c - rr, c - rr, c + rr, c + rr), outline=(255, 255, 255, 30), width=wd)
    if frac > 0.004:
        pd.arc((c - rr, c - rr, c + rr, c + rr), -90, -90 + 360 * max(0.0, min(1.0, frac)), fill=ACCENT_A + (255,), width=wd)
    patch = patch.resize((n // q, n // q), Image.LANCZOS)
    im.alpha_composite(patch, (int(cx - n / q / 2), int(cy - n / q / 2)))
    return im


def _bgra_premultiplied(im):
    a = np.asarray(im, dtype=np.uint16)
    out = np.empty(a.shape, np.uint8)
    out[..., 0] = a[..., 2] * a[..., 3] // 255
    out[..., 1] = a[..., 1] * a[..., 3] // 255
    out[..., 2] = a[..., 0] * a[..., 3] // 255
    out[..., 3] = a[..., 3]
    return out


def _ease(t):
    return 1 - (1 - t) ** 3


def _ensure_class():
    global _class_ready, _wndproc
    if _class_ready:
        return
    _wndproc = WNDPROC(lambda h, m, wp, lp: user32.DefWindowProcW(h, m, wp, lp))
    wc = WNDCLASSW()
    wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = _wndproc, kernel32.GetModuleHandleW(None), "RewindClipToast"
    user32.RegisterClassW(ctypes.byref(wc))
    _class_ready = True


def _run(x, y, title, sub, badge, scale, cancel, duration):
    _ensure_class()
    base, bar = render_card(title, sub, badge, scale)
    W, H = base.size
    hwnd = user32.CreateWindowExW(0x80000 | 0x8 | 0x80 | 0x20 | 0x08000000, "RewindClipToast", "Rewind", 0x80000000, x, y, W, H,
                                  None, None, kernel32.GetModuleHandleW(None), None)
    if not hwnd:
        return
    if not os.environ.get("REWIND_OVERLAY_VISIBLE_TO_CAPTURE"):
        try:
            user32.SetWindowDisplayAffinity(hwnd, 0x11)      # WDA_EXCLUDEFROMCAPTURE: keep it out of the recording
        except Exception:
            pass
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(mem, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(mem, dib)
    size = w.SIZE(W, H)
    src = w.POINT(0, 0)
    shown = False
    t0 = time.monotonic()
    try:
        while not cancel.is_set():
            t = time.monotonic() - t0
            if t >= duration:
                break
            msg = w.MSG()
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))
            if t < SLIDE:
                p = _ease(t / SLIDE); alpha, dx = int(255 * p), int(-46 * scale * (1 - p))
            elif t > duration - FADE:
                p = (t - (duration - FADE)) / FADE; alpha, dx = int(255 * (1 - p)), int(-18 * scale * _ease(p))
            else:
                alpha, dx = 255, 0
            frac = 1.0 if t < SLIDE else 1 - (t - SLIDE) / max(0.1, duration - FADE - SLIDE)
            data = _bgra_premultiplied(_frame(base, bar, frac))
            ctypes.memmove(bits, data.ctypes.data, data.nbytes)
            pos = w.POINT(x + dx, y)
            blend = BLENDFUNCTION(0, 0, max(0, min(255, alpha)), 1)
            user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(pos), ctypes.byref(size), mem, ctypes.byref(src), 0, ctypes.byref(blend), 2)
            if not shown:
                user32.ShowWindow(hwnd, 4)                    # SW_SHOWNOACTIVATE
                user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
                shown = True
            time.sleep(0.016)
    finally:
        user32.ShowWindow(hwnd, 0)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(dib)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)
        user32.DestroyWindow(hwnd)


def show(rect, title="Clip captured", sub="", badge="", duration=SHOW_FOR):
    """Show the card at the top left of `rect` = (x, y, width, height) in real screen pixels. Never blocks."""
    if not IS_WIN:
        return
    global _cancel
    x, y, mw, mh = rect
    scale = max(0.9, min(2.5, mh / 1080.0))
    margin = -int(4 * scale)

    def go(cancel):
        with _lock:
            try:
                _run(x + margin, y + margin, title, sub, badge, scale, cancel, duration)
            except Exception:
                pass
    _cancel.set()                      # a newer card replaces one still showing
    _cancel = threading.Event()
    threading.Thread(target=go, args=(_cancel,), daemon=True).start()

"""Game detection.

Every 1.5 s Rewind looks at the window in front and decides whether it's a game:
  1. A known game exe (list below)            -> game, with a clean name
  2. Installed in a game library folder         -> game (Steam, Epic, Riot, Xbox, Battle.net, GOG, EA, Ubisoft)
  3. Covers a whole monitor (fullscreen or borderless) and isn't a browser,
     video player or other everyday app        -> game
Names come from the known list, then the library folder name, then the exe's own
product name, then the window title.

A detected game stays "current" while its process is alive, so alt-tabbing out to
save a clip still names it after the game.
"""
import ntpath
import os
import re
import threading
import time

IS_WIN = os.name == "nt"

KNOWN = {
    "robloxplayerbeta.exe": "Roblox",
    "fortniteclient-win64-shipping.exe": "Fortnite",
    "valorant-win64-shipping.exe": "Valorant",
    "rocketleague.exe": "Rocket League",
    "cs2.exe": "Counter-Strike 2",
    "r5apex.exe": "Apex Legends",
    "r5apex_dx12.exe": "Apex Legends",
    "overwatch.exe": "Overwatch 2",
    "league of legends.exe": "League of Legends",
    "minecraft.windows.exe": "Minecraft",
    "gta5.exe": "GTA V",
    "gta5_enhanced.exe": "GTA V",
    "rdr2.exe": "Red Dead Redemption 2",
    "cod.exe": "Call of Duty",
    "cod24-cod.exe": "Call of Duty",
    "destiny2.exe": "Destiny 2",
    "dota2.exe": "Dota 2",
    "rainbowsix.exe": "Rainbow Six Siege",
    "rainbowsix_vulkan.exe": "Rainbow Six Siege",
    "marvel-win64-shipping.exe": "Marvel Rivals",
    "project8.exe": "Deadlock",
    "eldenring.exe": "Elden Ring",
    "cyberpunk2077.exe": "Cyberpunk 2077",
    "fallguys_client_game.exe": "Fall Guys",
    "rustclient.exe": "Rust",
    "tslgame.exe": "PUBG",
    "deadbydaylight-win64-shipping.exe": "Dead by Daylight",
    "palworld-win64-shipping.exe": "Palworld",
    "helldivers2.exe": "Helldivers 2",
    "thefinals.exe": "The Finals",
    "bf2042.exe": "Battlefield 2042",
    "eafc25.exe": "EA FC 25",
    "eafc26.exe": "EA FC 26",
    "fifa23.exe": "FIFA 23",
    "nba2k25.exe": "NBA 2K25",
    "nba2k26.exe": "NBA 2K26",
    "terraria.exe": "Terraria",
    "stardew valley.exe": "Stardew Valley",
    "geometrydash.exe": "Geometry Dash",
    "osu!.exe": "osu!",
    "warframe.x64.exe": "Warframe",
    "pathofexile.exe": "Path of Exile",
    "pathofexile_x64steam.exe": "Path of Exile",
    "hogwartslegacy.exe": "Hogwarts Legacy",
    "starfield.exe": "Starfield",
    "bg3.exe": "Baldur's Gate 3",
    "bg3_dx11.exe": "Baldur's Gate 3",
    "among us.exe": "Among Us",
    "phasmophobia.exe": "Phasmophobia",
    "lethal company.exe": "Lethal Company",
    "repo.exe": "R.E.P.O.",
}

# Things that go fullscreen but aren't games.
NOT_GAMES = {
    "explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe",
    "vivaldi.exe", "arc.exe", "discord.exe", "spotify.exe", "vlc.exe", "mpc-hc64.exe", "mpv.exe",
    "potplayermini64.exe", "obs64.exe", "streamlabs obs.exe", "steamwebhelper.exe", "steam.exe",
    "epicgameslauncher.exe", "riotclientux.exe", "riotclientservices.exe", "battle.net.exe",
    "applicationframehost.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "lockapp.exe", "textinputhost.exe", "taskmgr.exe", "code.exe", "devenv.exe", "winword.exe",
    "excel.exe", "powerpnt.exe", "outlook.exe", "teams.exe", "ms-teams.exe", "zoom.exe", "slack.exe",
    "photos.exe", "microsoft.photos.exe", "video.ui.exe", "netflix.exe", "rewind.exe", "autoclip.exe",
    "python.exe", "pythonw.exe", "robloxstudiobeta.exe", "windowsterminal.exe", "cmd.exe",
    "powershell.exe", "notepad.exe", "mspaint.exe", "snippingtool.exe", "screenclippinghost.exe",
}
GENERIC_PRODUCTS = {"", "unreal engine", "unity", "unity player", "bootstrapper", "launcher", "game",
                    "microsoft® windows® operating system", "java(tm) platform se binary", "openjdk platform binary"}
LIBRARY = [
    re.compile(r"\\steamapps\\common\\([^\\]+)", re.I),
    re.compile(r"\\epic games\\([^\\]+)", re.I),
    re.compile(r"\\riot games\\([^\\]+)", re.I),
    re.compile(r"\\xboxgames\\([^\\]+)", re.I),
    re.compile(r"\\gog galaxy\\games\\([^\\]+)", re.I),
    re.compile(r"\\ubisoft game launcher\\games\\([^\\]+)", re.I),
    re.compile(r"\\ea games\\([^\\]+)", re.I),
    re.compile(r"\\battle\.net\\([^\\]+)", re.I),
    re.compile(r"\\games\\([^\\]+)", re.I),
]


def classify(exe_path, title, fullscreen, ignored=(), product=""):
    """Return (name, reason) if this window is a game, else (None, reason)."""
    exe = ntpath.basename(exe_path or "").lower()
    if not exe:
        return None, "no process"
    if exe in {e.lower() for e in ignored}:
        return None, "marked not a game"
    if exe in KNOWN:
        return KNOWN[exe], "known game"
    if exe == "javaw.exe" and "minecraft" in (title or "").lower():
        return "Minecraft", "known game"
    if exe in NOT_GAMES:
        return None, "everyday app"
    for pat in LIBRARY:
        m = pat.search(exe_path)
        if m:
            return nice_name(exe_path, title, product, folder=m.group(1)), "game library"
    if fullscreen:
        return nice_name(exe_path, title, product), "fullscreen app"
    return None, "not fullscreen"


def nice_name(exe_path, title, product, folder=""):
    if folder and folder.lower() not in ("games", "binaries", "bin", "win64"):
        return folder.strip()
    if product and product.strip().lower() not in GENERIC_PRODUCTS:
        return product.strip()
    if title and len(title) <= 40:
        return title.strip()
    stem = ntpath.splitext(ntpath.basename(exe_path))[0]
    stem = re.sub(r"(?i)[-_](win64|win32|x64|shipping|client|dx1[12]|vulkan)", "", stem)
    return stem.replace("_", " ").strip() or "Game"


# ---------------------------------------------------------------- Windows plumbing

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    version = ctypes.windll.version

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("rc", RECT), ("work", RECT), ("flags", ctypes.c_ulong)]

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE


def _exe_of(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def _alive(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


_product_cache = {}


def product_name(path):
    """ProductName from the exe's version info (e.g. "Rocket League")."""
    if not IS_WIN or not path:
        return ""
    if path in _product_cache:
        return _product_cache[path]
    name = ""
    try:
        size = version.GetFileVersionInfoSizeW(path, None)
        if size:
            data = ctypes.create_string_buffer(size)
            version.GetFileVersionInfoW(path, 0, size, data)
            ptr, ln = ctypes.c_void_p(), wintypes.UINT()
            if version.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(ln)) and ln.value:
                lang, cp = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
                for key in ("ProductName", "FileDescription"):
                    q = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\{key}"
                    if version.VerQueryValueW(data, q, ctypes.byref(ptr), ctypes.byref(ln)) and ln.value:
                        name = ctypes.wstring_at(ptr, ln.value - 1).strip()
                        if name.lower() not in GENERIC_PRODUCTS:
                            break
    except Exception:
        pass
    _product_cache[path] = name
    return name


def foreground():
    """Info about the window in front, or None."""
    if not IS_WIN:
        return _fake_foreground()
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    n = user32.GetWindowTextLengthW(hwnd)
    tb = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, tb, n + 1)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return None
    wr = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    mi = MONITORINFO()
    mi.cb = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    m = mi.rc
    full = wr.l <= m.l and wr.t <= m.t and wr.r >= m.r and wr.b >= m.b
    return {"hwnd": int(hwnd), "pid": pid.value, "exe_path": _exe_of(pid.value),
            "title": tb.value.strip(), "fullscreen": full}


def _fake_foreground():
    """Test stand-in: REWIND_FAKE_GAME_FILE holds 'exe path|title|fullscreen(0/1)|pid'."""
    f = os.environ.get("REWIND_FAKE_GAME_FILE")
    if not f or not os.path.exists(f):
        return None
    parts = (open(f).read().strip().split("|") + ["", "", "0", "1"])[:4]
    if not parts[0]:
        return None
    return {"hwnd": 4242, "pid": int(parts[3] or 1), "exe_path": parts[0], "title": parts[1],
            "fullscreen": parts[2] == "1"}


def process_alive(pid):
    if not IS_WIN:
        return _fake_foreground() is not None
    return _alive(pid)


def window_alive(hwnd):
    return bool(user32.IsWindow(hwnd)) if IS_WIN else True


class GameWatcher(threading.Thread):
    def __init__(self, get_ignored, on_change, log=print):
        super().__init__(daemon=True)
        self.get_ignored, self.on_change, self.log = get_ignored, on_change, log
        self.current = None      # {"name","exe","exe_path","pid","hwnd","focused","reason","since"}
        self.recent = {}         # exe -> {"name", "last_seen"}
        self.lock = threading.Lock()

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:
                self.log(f"game watch: {e}")
            time.sleep(1.5)

    def tick(self):
        fg = foreground()
        found = None
        if fg and fg["exe_path"]:
            name, reason = classify(fg["exe_path"], fg["title"], fg["fullscreen"], self.get_ignored(),
                                    product_name(fg["exe_path"]))
            if name:
                found = {"name": name, "exe": ntpath.basename(fg["exe_path"]), "exe_path": fg["exe_path"],
                         "pid": fg["pid"], "hwnd": fg["hwnd"], "focused": True, "reason": reason}
        with self.lock:
            old = self.current
            if found:
                if old and old["pid"] == found["pid"]:
                    found["since"] = old["since"]
                else:
                    found["since"] = time.time()
                self.current = found
                self.recent[found["exe"].lower()] = {"name": found["name"], "exe": found["exe"],
                                                     "last_seen": time.time()}
            elif old:
                ignored = {e.lower() for e in self.get_ignored()}
                if process_alive(old["pid"]) and window_alive(old["hwnd"]) and old["exe"].lower() not in ignored:
                    self.current = dict(old, focused=False)  # alt-tabbed out, still playing
                else:
                    self.current = None
            new = self.current
        if (old or {}).get("pid") != (new or {}).get("pid") or (old or {}).get("hwnd") != (new or {}).get("hwnd"):
            self.log(f"game: {old and old['name']} -> {new and new['name']}")
            self.on_change(old, new)

    def snapshot(self):
        with self.lock:
            cur = dict(self.current) if self.current else None
            rec = sorted(self.recent.values(), key=lambda r: -r["last_seen"])[:8]
        return cur, rec

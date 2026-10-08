"""Rewind: instant replay for your PC. Press a shortcut, get the last 30 seconds as a clip.

Run:  pythonw app.py   (or the exe)
"""
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import editor
import engine
import games
import sfx
import share
import winbits

VERSION = "1.6.15"
APP_DIR = engine.APP_DIR
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
UI_FILE = Path(os.environ.get("REWIND_UI_FILE") or RES_DIR / "ui" / "index.html")
# test runs keep their own settings and log, so they can never touch a real install's
DATA_DIR = Path(os.environ.get("REWIND_DATA_DIR") or
                Path(os.environ.get("APPDATA", Path.home() / ".config")) / ("Rewind-test" if engine.TEST else "Rewind"))
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "rewind.log"
UPDATE_DIR = DATA_DIR / "update"
TOKEN = secrets.token_urlsafe(16)


def repo_name():
    """GitHub "owner/name" this build was published from (written by publish.py)."""
    try:
        return json.loads((RES_DIR / "repo.json").read_text(encoding="utf-8")).get("repo", "")
    except Exception:
        return ""


REPO = repo_name()
WEBSITE = f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[1]}/" if "/" in REPO else ""


def version_tuple(v):
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())

DEFAULTS = {
    "length": 30, "fps": 60, "quality": "balanced", "performance": "balanced", "output_height": 0, "encoder": "auto", "monitor": 0,
    "desktop_audio": True, "mic": True, "mic_device": None, "output_device": None,
    "hotkey": {"mods": 1, "vk": 0x77, "label": "Alt + F8"},
    "hotkey_record": {"mods": 1, "vk": 0x76, "label": "Alt + F7"},
    "hotkey_bookmark": None, "share_ok": False,
    "clip_toast": True, "soft_decode": False, "sound": True, "sound_name": "clip", "sound_volume": "medium",
    "capture": "auto", "capture_input": "", "window_games": [], "game_only": False, "game_folders": True, "ignored_games": [],
    "close_to_tray": True, "start_with_windows": False, "long_guard": True, "auto_update": True, "skipped_version": "", "start_hidden": False,
    "clips_dir": winbits.default_clips_dir(),
}
HOTKEY_KEYS = {"clip": "hotkey", "record": "hotkey_record", "bookmark": "hotkey_bookmark"}
RESTART_KEYS = {"length", "fps", "quality", "performance", "output_height", "encoder", "monitor", "desktop_audio", "mic", "mic_device", "output_device", "capture", "capture_input"}


def log(msg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def load_settings():
    s = dict(DEFAULTS)
    for f in (SETTINGS_FILE, SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".bak")):
        try:
            s.update(json.loads(f.read_text(encoding="utf-8")))
            break
        except Exception:
            continue
    if s.get("capture_input") == "gdi" and not s.get("capture_reset_154"):
        # versions 1.4.1 to 1.5.3 could lock a PC into compatibility capture after one bad start, so start again from Automatic
        s["capture_input"], s["capture_reset_154"] = "", True
        try:
            save_settings(s)
        except OSError:
            pass
    if not s.get("sound", True):  # older settings files
        s["sound_name"], s["sound"] = "off", True
    return s


def set_autostart(on, name="Rewind"):
    """Start with Windows: a per-user entry that opens Rewind hidden in the tray at sign-in. Only for the installed exe."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        if on:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f'"{sys.executable}" --hidden')
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    finally:
        key.Close()
    return True


def trim_log(limit=1_000_000, keep=300_000):
    """The log only needs the recent past, so don't let it grow forever."""
    try:
        if LOG_FILE.stat().st_size > limit:
            data = LOG_FILE.read_bytes()[-keep:]
            data = data[data.find(b"\n") + 1:]
            LOG_FILE.write_bytes(data)
    except OSError:
        pass


_SAVE_LOCK = threading.Lock()


def save_settings(s):
    """Write to a temporary file and swap it in, so a crash or power cut can't leave half a settings file.
    One save at a time, and a short retry if Windows (or a virus scanner) has the file open for a moment."""
    with _SAVE_LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
        try:
            if SETTINGS_FILE.exists():
                shutil.copyfile(SETTINGS_FILE, SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".bak"))
        except OSError:
            pass
        for i in range(20):
            try:
                os.replace(tmp, SETTINGS_FILE)
                return
            except PermissionError:
                if i == 19:
                    raise
                time.sleep(0.05)


class App:
    def __init__(self):
        self.settings = load_settings()
        self.watcher = games.GameWatcher(lambda: self.settings.get("ignored_games", []), self.on_game_change, log)
        self.rec = engine.Recorder(self.settings, log=log, title_fn=winbits.foreground_title,
                                   game_fn=self.current_game, remember_window_game=self.remember_window_game)
        self.hotkeys = {"clip": winbits.Hotkey(self.save_replay), "record": winbits.Hotkey(self.toggle_long),
                        "bookmark": winbits.Hotkey(self.add_bookmark)}
        self.hotkey = self.hotkeys["clip"]
        self.rec.long_end_cb = self.stop_long
        self.rec.low_disk_cb = self.low_disk_stop
        self.rec.persist = lambda k, v: (self.settings.__setitem__(k, v), save_settings(self.settings))
        self.window = None
        self.winmgr = None
        self.tray = None
        self.events = []  # toasts for the UI: saved / failed
        self.monitors = winbits.monitors()
        self.mics = []
        self.outputs = []
        self.port = 0
        self.tray_hint_shown = False
        self.update = None  # {"version", "url", ...} when GitHub has a newer release
        self.update_status = {"state": "idle", "checked": None, "error": ""}
        self.ext_files = {}   # audio files picked in the editor: id -> path
        self.jobs = {}        # editor exports in progress
        self.sound_urls = set()   # online sounds the library search returned
        self.gpus = []
        self._durations = {}
        self._count, self._count_t = 0, 0.0
        self._waves = {}

    def check_update(self, manual=False):
        """Look for a newer GitHub release; when running as the exe, download it in the background."""
        if not REPO or self.update_status["state"] == "checking":
            return
        self.update_status.update(state="checking", error="")
        try:
            import urllib.request
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "Rewind"})
            with engine.urlopen(req, timeout=10) as r:
                rel = json.load(r)
            tag = rel.get("tag_name", "")
            self.update_status["checked"] = int(time.time())
            if version_tuple(tag) <= version_tuple(VERSION):
                self.update = None
                self.update_status["state"] = "latest"
                return
            asset = next((a["browser_download_url"] for a in rel.get("assets", []) if a.get("name") == "Rewind.exe"), None)
            sha = next((a["browser_download_url"] for a in rel.get("assets", []) if a.get("name") == "Rewind.exe.sha256"), None)
            if not (self.update and self.update.get("version") == tag.lstrip("v")):
                self.update = {"version": tag.lstrip("v"), "url": rel.get("html_url") or WEBSITE,
                               "notes": (rel.get("body") or "").strip()[:600],
                               "ready": False, "auto": bool(asset and sha and getattr(sys, "frozen", False)), "asset": asset, "sha": sha}
            self.update_status["state"] = "available"
            log(f"update available: {tag}")
            if (self.update["auto"] and not self.update["ready"] and not self.update.get("downloading")
                    and (manual or self.settings.get("auto_update", True))):
                self.download_update(asset)
        except Exception as e:
            log(f"update check failed: {e}")
            self.update_status.update(state="error", error="Couldn't reach GitHub. Check your internet and try again.")

    def update_loop(self):
        while True:
            self.check_update()
            time.sleep(6 * 3600)

    def download_update(self, url):
        import urllib.request
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        part = UPDATE_DIR / "Rewind-new.exe.part"
        self.update.update(downloading=True, progress=0)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Rewind"})
            with engine.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                total, got = int(r.headers.get("Content-Length") or 0), 0
                while True:
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        self.update["progress"] = int(got * 100 / total)
            if part.stat().st_size < 1_000_000:
                raise RuntimeError("downloaded file is too small")
            import hashlib
            want = ""
            try:
                with engine.urlopen(urllib.request.Request(self.update["sha"], headers={"User-Agent": "Rewind"}), timeout=30) as r:
                    want = r.read().decode("ascii", "replace").split()[0].strip().lower()
            except Exception as e:
                raise RuntimeError(f"couldn't fetch the checksum: {e}")
            h = hashlib.sha256()
            with open(part, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() != want:
                part.unlink(missing_ok=True)
                raise RuntimeError("the download doesn't match its checksum")
            part.replace(UPDATE_DIR / "Rewind-new.exe")
            self.update.update(ready=True, downloading=False, progress=100)
            log("update downloaded, ready to install")
        except Exception as e:
            log(f"update download failed: {e}")
            self.update.update(auto=False, downloading=False, error="The download didn't finish. Try again in a moment.")

    def update_now(self):
        """The banner's Update now: download if needed, then swap the exe and relaunch by itself."""
        u = self.update
        if not u:
            return False
        if not u.get("auto"):
            import webbrowser
            webbrowser.open(u["url"])
            return True

        def go():
            if not u["ready"]:
                if u.get("downloading"):
                    while u.get("downloading"):
                        time.sleep(0.3)
                else:
                    u.pop("error", None)
                    self.download_update(u["asset"])
            if u["ready"]:
                u["installing"] = True
                time.sleep(0.6)
                self.apply_update()

        threading.Thread(target=go, daemon=True).start()
        return True

    def apply_update(self):
        """Swap in the downloaded exe and relaunch. A tiny batch file does it after this process exits."""
        new = UPDATE_DIR / "Rewind-new.exe"
        if not (getattr(sys, "frozen", False) and new.exists()):
            return False
        exe = Path(sys.executable)
        bat = UPDATE_DIR / "apply.bat"
        lines = [
            "@echo off",
            "set n=0",
            ":retry",
            "set /a n+=1",
            "if %n% gtr 40 exit /b 1",
            "timeout /t 1 /nobreak >nul",
            f'move /Y "{new}" "{exe}" >nul 2>&1',
            "if errorlevel 1 goto retry",
            f'start "" "{exe}"',
        ]
        bat.write_text(chr(13).join(lines).replace(chr(13), chr(13) + chr(10)) + chr(13) + chr(10), encoding="utf-8", newline="")
        log("applying update")
        env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}  # let the new exe unpack fresh
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x08000000, close_fds=True, env=env)
        self.quit()
        return True

    # ---- games
    def current_game(self):
        return self.watcher.snapshot()[0]

    def remember_window_game(self, exe):
        wg = self.settings.setdefault("window_games", [])
        if exe.lower() not in {e.lower() for e in wg}:
            wg.append(exe)
            save_settings(self.settings)

    def on_game_change(self, old, new):
        if self.settings.get("game_only"):
            if new and not self.rec.wanted:
                log(f"{new['name']} started, starting the buffer")
                self.rec.start()
            elif not new and self.rec.wanted:
                log("game closed, waiting for the next one")
                self.rec.stop(waiting=True)
        else:
            self.rec.game_changed(new)
        self.refresh_tray()

    # ---- actions
    def save_replay(self):
        try:
            game = self.current_game()
            folder = self.target_folder(game)
            if self.rec.state == "buffering" and self.rec.order:
                winbits.play_saved_sound(self.settings.get("sound_name", "clip"), self.settings.get("sound_volume", "medium"))
            p = self.rec.save(folder, title=game["name"] if game else None)
            rel = p.relative_to(Path(self.settings["clips_dir"])).as_posix()
            self.events.append({"id": time.time(), "kind": "saved", "name": rel})
            self._count_t = 0
            self.show_toast(game["name"] if game else "Screen")
            return {"ok": True, "name": rel}
        except Exception as e:
            log("save failed: " + traceback.format_exc())
            if self.settings.get("sound_name") != "off":
                winbits.play_error_sound(self.settings.get("sound_volume", "medium"))
            self.events.append({"id": time.time(), "kind": "error", "message": str(e)})
            return {"ok": False, "error": str(e)}

    def show_toast(self, name, force=False):
        """The "Clip captured" card on the screen being recorded."""
        if not (force or self.settings.get("clip_toast", True)):
            return
        try:
            import overlay
            mons = winbits.monitors()
            idx = int(self.settings.get("monitor", 0) or 0)
            m = mons[idx] if 0 <= idx < len(mons) else mons[0]
            if "x" not in m:
                return
            n = int(self.settings.get("length", 30))
            span = f"{n // 60} min" if n >= 60 and n % 60 == 0 else f"{n}s"
            overlay.show((m["x"], m["y"], m["w"], m["h"]), "Clip captured", "", span)
        except Exception as e:
            log(f"pop-up failed: {e}")

    def toggle(self):
        if self.rec.wanted:
            if self.rec.long:
                self.stop_long()
            self.rec.stop()
        elif self.rec.state == "waiting":
            self.rec.start()  # "Record now" while waiting for a game
        else:
            if self.settings.get("game_only") and not self.current_game():
                self.rec.stop(waiting=True)
            else:
                self.rec.start()
        self.refresh_tray()

    def update_settings(self, patch):
        restart = any(k in RESTART_KEYS and patch[k] != self.settings.get(k) for k in patch)
        self.settings.update(patch)
        save_settings(self.settings)
        if "start_with_windows" in patch:
            try:
                set_autostart(bool(patch["start_with_windows"]))
            except OSError as e:
                log(f"couldn't change start with Windows: {e}")
        for w, k in HOTKEY_KEYS.items():
            if k in patch:
                self.apply_hotkey(w)
        if "game_only" in patch:
            if patch["game_only"] and not self.current_game() and self.rec.state != "paused":
                self.rec.stop(waiting=True)
            elif not patch["game_only"] and self.rec.state == "waiting":
                self.rec.start()
        if "ignored_games" in patch:
            self.watcher.tick()
        if restart:
            threading.Thread(target=self.rec.restart, daemon=True).start()

    def apply_hotkey(self, which, retries=0):
        hk, h = self.hotkeys[which], self.settings.get(HOTKEY_KEYS[which])
        if h:
            hk.set(h["mods"], h["vk"], retries, hold=2.0 if h.get("mode") == "long" else 0.0)
        else:
            hk.clear()
            hk.ok, hk.error = True, ""

    def target_folder(self, game):
        folder = Path(self.settings["clips_dir"])
        if game and self.settings.get("game_folders", True):
            folder = folder / engine.safe_name(game["name"])
        return folder

    def note(self, title, message=""):
        self.events.append({"id": time.time(), "kind": "note", "title": title, "message": message})

    def play(self, name):
        winbits.play_saved_sound(name, self.settings.get("sound_volume", "medium"))

    # ---- long recording + bookmarks
    def toggle_long(self):
        if self.rec.long:
            return self.stop_long()
        try:
            game = self.current_game()
            log("long recording: starting")
            self.rec.start_long(self.target_folder(game), game["name"] if game else (winbits.foreground_title() or "Desktop"),
                                self.settings.get("long_guard", True))
        except Exception as e:
            self.events.append({"id": time.time(), "kind": "error", "message": str(e)})
            return {"ok": False, "error": str(e)}
        if self.settings.get("sound_name") != "off":
            self.play("ping")
        self.note("Recording started", "Press the same key again to stop. Add bookmarks with your bookmark key.")
        log("long recording: started, notified")
        return {"ok": True}

    def stop_long(self):
        if not self.rec.long:
            return {"ok": False}
        game = self.current_game()
        try:
            self.note("Saving your recording…", "Long recordings take a moment to finish.")
            p, marks = self.rec.stop_long(self.target_folder(game), game["name"] if game else (winbits.foreground_title() or "Desktop"))
            if self.settings.get("sound_name") != "off":
                self.play(self.settings.get("sound_name", "clip"))
            rel = p.relative_to(Path(self.settings["clips_dir"])).as_posix()
            self.events.append({"id": time.time(), "kind": "saved", "name": rel, "long": True, "bookmarks": len(marks)})
            return {"ok": True, "name": rel}
        except Exception as e:
            log("long recording failed: " + traceback.format_exc())
            self.events.append({"id": time.time(), "kind": "error", "message": str(e)})
            return {"ok": False, "error": str(e)}

    def low_disk_stop(self):
        self.note("Recording stopped", "Your drive is almost full, so Rewind saved the recording while it still could.")
        self.stop_long()

    def add_bookmark(self):
        if not self.rec.long:
            self.note("No long recording yet", "Start one first, then bookmark the moments you want to find later.")
            return {"ok": False}
        t = int(self.rec.long.bookmark())
        if self.settings.get("sound_name") != "off":
            self.play("ping")
        self.note("Bookmark added", f"At {t // 60}:{t % 60:02d} in your recording.")
        return {"ok": True}

    def state(self):
        h = self.settings["hotkey"]
        game, recent = self.watcher.snapshot()
        return {
            "game": {k: game[k] for k in ("name", "exe", "focused", "reason", "since")} if game else None,
            "recent_games": recent,
            "version": VERSION,
            "status": self.rec.status(),
            "settings": self.settings,
            "hotkey_ok": self.hotkey.ok, "hotkey_error": self.hotkey.error, "hotkey_label": h["label"],
            "hotkeys": {w: {"label": (self.settings.get(k) or {}).get("label", ""), "ok": self.hotkeys[w].ok,
                            "error": self.hotkeys[w].error, "mode": (self.settings.get(k) or {}).get("mode", "tap")} for w, k in HOTKEY_KEYS.items()},
            "monitors": self.monitors, "mics": self.mics, "outputs": self.outputs,
            "events": self.events[-5:],
            "clip_count": self.clip_count(),
            "native_window": self.window is not None,
            "website": WEBSITE, "update": self.update, "update_status": self.update_status,
            "gpus": self.gpus, "encoder_notes": engine.PROBE_NOTES,
        }

    def find_gpus(self):
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' | driver ' + $_.DriverVersion }"],
                               capture_output=True, text=True, timeout=25, creationflags=0x08000000, stdin=subprocess.DEVNULL)
            self.gpus = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        except Exception as e:
            log(f"gpu lookup failed: {e}")

    def diagnostics(self):
        import platform
        st = self.rec.status()
        lines = [f"Rewind {VERSION}", f"Windows {platform.version()}", "Graphics: " + (" ; ".join(self.gpus) or "unknown"),
                 f"ffmpeg: {engine.FFMPEG}", "Encoders: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in (st.get("available") or {}).items()),
                 "Using encoder: " + str(st.get("encoder")), "Capture: " + str(st.get("capture_mode")) + f" (setting: {self.settings.get('capture_input') or 'automatic'})",
                 "State: " + str(st.get("state")), "Error: " + str(st.get("error") or "none"), "Audio: " + str(st.get("audio_note") or "ok"),
                 "Notice: " + str(st.get("notice") or "none")]
        for k, v in engine.PROBE_NOTES.items():
            if v:
                lines.append(f"Why {k} isn't available: {v}")
        try:
            tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
            lines += ["", "Recent log:"] + [t[:300] for t in tail]
        except Exception:
            pass
        return "\n".join(lines)

    def clip_count(self):
        """How many clips there are. Listing the folder this often (the page asks twice a second) is wasteful, so keep the answer for a few seconds."""
        now = time.monotonic()
        if now - self._count_t > 3.0:
            self._count, self._count_t = len(self.clip_files()), now
        return self._count

    def clip_files(self):
        d = Path(self.settings["clips_dir"])
        if not d.exists():
            return []
        return [p for p in list(d.glob("*.mp4")) + list(d.glob("*/*.mp4")) if not p.parent.name.startswith(".")]

    def clip_duration(self, p, st):
        key = (str(p), st.st_mtime, st.st_size)
        if key not in self._durations:
            try:
                self._durations[key] = round(engine.duration_of(p))
            except Exception:
                self._durations[key] = 0
        return self._durations[key]

    @staticmethod
    def clip_bookmarks(p):
        b = engine.bookmarks_path(p)
        if not b.exists():
            return []
        try:
            return json.loads(b.read_text(encoding="utf-8"))
        except Exception:
            return []

    def clips(self, limit=400):
        d = Path(self.settings["clips_dir"])
        out = []
        for p in sorted(self.clip_files(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            st = p.stat()
            out.append({"name": p.relative_to(d).as_posix(), "title": p.stem,
                        "game": p.parent.name if p.parent != d else "",
                        "size_mb": round(st.st_size / 1e6, 1), "mtime": st.st_mtime,
                        "duration": self.clip_duration(p, st), "bookmarks": self.clip_bookmarks(p)})
        return out

    @staticmethod
    def vertical_graph(fmt, fx, fy, zoom):
        """ffmpeg filters that turn a landscape clip into 1080x1920. Returns (kind, graph)."""
        fx = min(1.0, max(0.0, float(fx)))
        fy = min(1.0, max(0.0, float(fy)))
        z = min(4.0, max(1.0, float(zoom)))
        if fmt == "fill":
            return "vf", f"crop=w='ih*9/16':h=ih:x='(iw-ow)*{fx:.4f}':y=0,scale=1080:1920:flags=lanczos,format=yuv420p"
        if fmt == "zoom":
            return "vf", (f"crop=w='ih*9/16/{z:.3f}':h='ih/{z:.3f}':x='(iw-ow)*{fx:.4f}':y='(ih-oh)*{fy:.4f}',"
                          "scale=1080:1920:flags=lanczos,format=yuv420p")
        return "fc", ("split[a][b];[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,gblur=sigma=10,"
                      "scale=1080:1920[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")

    def trim_clip(self, b):
        """Cut a clip to [start, end]. mode "copy" saves a new clip next to it, "replace" overwrites the original."""
        src = self.clip_path(b["name"])
        fmt = b.get("format") if b.get("format") in ("fill", "fit", "zoom") else ""
        start, end = max(0.0, float(b["start"])), float(b["end"])
        total = engine.duration_of(src)
        end = min(end, total) if total else end
        if end - start < 0.5:
            return {"ok": False, "error": "Pick at least half a second to keep."}
        if not fmt and start < 0.05 and total and end > total - 0.05:
            return {"ok": False, "error": "That's the whole clip. Drag the handles to cut it first."}
        tmp = src.with_name(f"trim-{secrets.token_hex(4)}.part")
        s = self.settings

        def attempt(enc):
            cmd = [engine.FFMPEG, "-hide_banner", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src),
                   "-t", f"{end - start:.3f}"]
            if fmt:
                kind, graph = self.vertical_graph(fmt, b.get("fx", .5), b.get("fy", .5), b.get("zoom", 1.6))
                cmd += ["-filter_complex", graph, "-map", "[v]"] if kind == "fc" else ["-vf", graph, "-map", "0:v:0"]
                cmd += ["-map", "0:a?"]
            else:
                cmd += ["-map", "0:v:0", "-map", "0:a?"]
            cmd += engine.video_args(enc, s.get("quality", "balanced"), int(s.get("fps", 60)))
            cmd += ["-c:a", "copy", "-movflags", "+faststart", "-f", "mp4", str(tmp)]
            return engine.run(cmd, timeout=300)

        try:
            r = attempt(self.rec.encoder)
            if r.returncode != 0 and self.rec.encoder != "cpu":
                r = attempt("cpu")
            if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
                log(f"trim failed: {r.stderr[-300:]}")
                return {"ok": False, "error": "Couldn't cut that clip. See rewind.log for details."}
            why = engine.clip_problem(tmp, end - start + 5)
            if why:
                log(f"trim result rejected ({why})")
                tmp.unlink(missing_ok=True)
                return {"ok": False, "error": "The cut came out damaged, so nothing was changed. Your original is safe."}
            if b.get("mode") == "replace" and not fmt:
                st = src.stat()
                for i in range(10):  # the player may still be letting go of the file
                    try:
                        os.replace(tmp, src)
                        break
                    except PermissionError:
                        if i == 9:
                            raise
                        time.sleep(0.3)
                os.utime(src, (st.st_atime, st.st_mtime))
                t = engine.thumb_path(src)
                if t.exists():
                    t.unlink()
                dest = src
            else:
                base = src.stem + (" (vertical)" if fmt else " (trimmed)")
                dest, n = src.with_name(base + ".mp4"), 2
                while dest.exists():
                    dest, n = src.with_name(f"{base} {n}.mp4"), n + 1
                os.replace(tmp, dest)
            log(f"trimmed {src.name} {start:.1f}-{end:.1f}s ({b.get('mode')})")
            return {"ok": True, "name": dest.relative_to(Path(s["clips_dir"]).resolve()).as_posix()}
        except Exception as e:
            log(f"trim error: {e}")
            return {"ok": False, "error": "Couldn't cut that clip: " + str(e)}
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    # ---- video editor
    def resolve_src(self, src):
        if str(src).startswith("ext:"):
            p = self.ext_files.get(src[4:])
            if not p or not Path(p).exists():
                raise ValueError("That audio file isn't available any more.")
            return Path(p)
        return self.clip_path(src)

    def waveform(self, src):
        """Loudness of a clip or sound, 20 values per second (0 to 255), for drawing on the editor timeline."""
        import numpy as np
        p = self.resolve_src(src)
        key = (str(p), p.stat().st_mtime)
        if key not in self._waves:
            r = subprocess.run([engine.FFMPEG, "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "2000", "-f", "s16le", "-"],
                               capture_output=True, timeout=180, creationflags=0x08000000, stdin=subprocess.DEVNULL)
            a = np.frombuffer(r.stdout[: len(r.stdout) // 2 * 2], np.int16).astype(np.float32) / 32768.0
            n = len(a) // 100
            peaks = np.abs(a[: n * 100]).reshape(n, 100).max(axis=1) if n else np.zeros(0, np.float32)
            self._waves[key] = [int(v) for v in np.clip(np.sqrt(peaks) * 255, 0, 255)]
            if len(self._waves) > 60:
                self._waves.pop(next(iter(self._waves)))
        return {"ok": True, "rate": 20, "peaks": self._waves[key]}

    def filmstrip(self, p, n):
        """One picture of n small frames, evenly spread through a clip, for the trim bar. Made with ffmpeg and kept next
        to the thumbnail, so the player doesn't need a second copy of the video decoding while the clip plays."""
        import io
        from concurrent.futures import ThreadPoolExecutor
        from PIL import Image
        n = max(4, min(int(n), 40))
        out = engine.thumb_path(p).with_name(p.stem + f".strip{n}.jpg")
        try:
            if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
                return out.read_bytes()
        except OSError:
            pass
        dur = engine.duration_of(p) or 1.0

        def grab(i):
            t = max(0.0, min(dur - 0.1, (i + 0.5) / n * dur))
            r = subprocess.run([engine.FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-noaccurate_seek", "-i", str(p), "-frames:v", "1",
                                "-vf", "scale=160:90:force_original_aspect_ratio=increase,crop=160:90", "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "5", "-"],
                               capture_output=True, creationflags=0x08000000 | 0x4000, stdin=subprocess.DEVNULL, timeout=60)
            return i, r.stdout
        sheet = Image.new("RGB", (160 * n, 90), (16, 16, 18))
        with ThreadPoolExecutor(4) as ex:
            for i, data in ex.map(grab, range(n)):
                if data:
                    try:
                        sheet.paste(Image.open(io.BytesIO(data)).convert("RGB"), (160 * i, 0))
                    except Exception:
                        pass
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=78)
        try:
            out.parent.mkdir(exist_ok=True)
            out.write_bytes(buf.getvalue())
        except OSError:
            pass
        return buf.getvalue()

    def pick_audio(self):
        types = ("Audio and video (*.mp3;*.wav;*.m4a;*.aac;*.ogg;*.flac;*.opus;*.mp4;*.mov;*.mkv;*.webm)", "All files (*.*)")
        try:
            if self.window:
                import webview
                r = self.window.create_file_dialog(webview.OPEN_DIALOG, file_types=types)
                path = r[0] if r else None
            else:
                import tkinter
                from tkinter import filedialog
                root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
                path = filedialog.askopenfilename(title="Choose music or a sound",
                                                  filetypes=[("Audio and video", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.opus *.mp4 *.mov *.mkv *.webm"), ("All files", "*.*")])
                root.destroy()
        except Exception as e:
            log(f"audio dialog failed: {e}")
            path = None
        if not path:
            return {"ok": False}
        fid = secrets.token_hex(6)
        self.ext_files[fid] = str(path)
        return {"ok": True, "id": "ext:" + fid, "name": Path(path).stem}

    PROJECT_FILE = "editor_project.json"

    def save_project(self, body):
        """Keep the edit in progress on disk so it survives closing Rewind and updates."""
        proj = body.get("project")
        if not isinstance(proj, dict):
            return {"ok": False}
        ext = {}
        for key in ("video", "overlay", "audio"):
            for it in proj.get(key) or []:
                s = str((it or {}).get("src", ""))
                if s.startswith("ext:") and s[4:] in self.ext_files:
                    ext[s[4:]] = self.ext_files[s[4:]]
        data = {"v": 1, "name": str(body.get("name", ""))[:120], "project": proj, "ext": ext, "labels": body.get("labels") or {}, "saved": time.time()}
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = DATA_DIR / (self.PROJECT_FILE + ".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, DATA_DIR / self.PROJECT_FILE)
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def load_project(self):
        f = DATA_DIR / self.PROJECT_FILE
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"ok": False}
        for fid, path in (data.get("ext") or {}).items():
            if path and Path(path).exists():
                self.ext_files[fid] = path
        return {"ok": True, "project": data.get("project"), "name": data.get("name", ""), "labels": data.get("labels") or {}}

    def clear_project(self):
        try:
            (DATA_DIR / self.PROJECT_FILE).unlink()
        except OSError:
            pass
        return {"ok": True}

    def register_ext(self, path):
        path = str(path)
        for fid, p in self.ext_files.items():
            if p == path:
                return "ext:" + fid
        fid = secrets.token_hex(6)
        self.ext_files[fid] = path
        return "ext:" + fid

    def search_sounds(self, q, kind, page):
        """Free (CC0 / public domain) sounds from Openverse. No account or key needed."""
        import urllib.request
        q = (q or "").strip() or ("music" if kind == "music" else "sound effect")
        params = {"q": q, "license": "cc0,pdm", "page_size": 20, "page": max(1, int(page or 1)), "extension": "mp3"}
        req = urllib.request.Request("https://api.openverse.org/v1/audio/?" + urlencode(params),
                                     headers={"User-Agent": "Rewind/1.0 (video editor)", "Accept": "application/json"})
        try:
            with engine.urlopen(req, timeout=15) as r:
                data = json.load(r)
        except Exception as e:
            log(f"sound search failed: {e}")
            return {"ok": False, "error": "Couldn't reach the free sound library. Check your internet and try again."}
        out = []
        for it in data.get("results", []):
            dur = (it.get("duration") or 0) / 1000
            url = it.get("url") or ""
            if not url.startswith("https://") or not dur:
                continue
            if (kind == "music" and dur < 20) or (kind != "music" and dur > 20):
                continue
            self.sound_urls.add(url)
            out.append({"title": it.get("title") or "Untitled", "creator": it.get("creator") or "", "source": it.get("source") or "",
                        "duration": round(dur, 1), "url": url, "license": (it.get("license") or "").upper()})
        return {"ok": True, "results": out, "more": (data.get("page_count") or 1) > int(page or 1)}

    def fetch_sound(self, url, title):
        import hashlib
        import urllib.request
        if url not in self.sound_urls:
            return {"ok": False, "error": "Search for the sound first."}
        folder = DATA_DIR / "sounds"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".mp3")
        if not dest.exists():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Rewind/1.0"})
                with engine.urlopen(req, timeout=30) as r, open(str(dest) + ".part", "wb") as f:
                    size = 0
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > 40 * 1024 * 1024:
                            raise RuntimeError("That sound is too big.")
                        f.write(chunk)
                os.replace(str(dest) + ".part", dest)
            except Exception as e:
                log(f"sound download failed: {e}")
                try:
                    Path(str(dest) + ".part").unlink()
                except OSError:
                    pass
                return {"ok": False, "error": "Couldn't download that sound."}
        return {"ok": True, "id": self.register_ext(dest), "name": (title or "Sound")[:60]}

    def start_export(self, body):
        project = body.get("project") or {}
        try:
            for c in (project.get("video") or []) + (project.get("audio") or []):
                self.resolve_src(c["src"])
        except (ValueError, KeyError) as e:
            return {"ok": False, "error": str(e) or "One of the clips is missing."}
        if not project.get("video"):
            return {"ok": False, "error": "Add a clip to the timeline first."}
        out_dir = Path(self.settings["clips_dir"]) / "Edits"
        out_dir.mkdir(parents=True, exist_ok=True)
        base = engine.safe_name(body.get("title") or "Edit")
        out, n = out_dir / f"{base}.mp4", 2
        while out.exists():
            out, n = out_dir / f"{base} {n}.mp4", n + 1
        q = editor.QUALITY.get(body.get("quality"), "balanced")
        cap = 720 if int(body.get("res") or 1080) <= 720 else 1080

        def enc_for():
            tries = [engine.video_args(self.rec.encoder, q, 30)]
            if self.rec.encoder != "cpu":
                tries.append(engine.video_args("cpu", q, 30))
            return tries

        job = editor.Job()
        job.name = ""
        self.jobs[job.id] = job
        threading.Thread(target=editor.run_job, args=(job, project, self.resolve_src, out, enc_for, cap, log), daemon=True).start()
        return {"ok": True, "job": job.id}

    def job_state(self, jid):
        job = self.jobs.get(jid)
        if not job:
            return {"pct": 0, "done": True, "error": "That export isn't running."}
        rel = ""
        if job.done and job.name and not job.error:
            try:
                rel = Path(job.name).relative_to(Path(self.settings["clips_dir"])).as_posix()
            except ValueError:
                rel = Path(job.name).name
        return {"pct": round(job.pct, 1), "done": job.done, "error": job.error, "rel": rel}

    def cancel_export(self, jid):
        job = self.jobs.get(jid)
        if job and not job.done:
            job.cancelled = True
            try:
                if job.proc:
                    job.proc.kill()
            except Exception:
                pass

    def clip_path(self, name):
        """A clip in the clips folder or one game folder below it. Nothing else."""
        d = Path(self.settings["clips_dir"]).resolve()
        p = (d / name).resolve()
        if p.suffix.lower() != ".mp4" or p.parent.name.startswith(".") or not (
                p.parent == d or p.parent.parent == d):
            raise ValueError("Unknown clip")
        return p

    def pick_folder(self):
        cur = self.settings["clips_dir"]
        try:
            if self.window:
                import webview
                r = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=cur)
                return r[0] if r else None
            import tkinter
            from tkinter import filedialog
            root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
            r = filedialog.askdirectory(initialdir=cur, title="Choose where Rewind saves clips")
            root.destroy()
            return r or None
        except Exception as e:
            log(f"folder dialog failed: {e}")
            return None

    # ---- window + tray
    def show(self):
        if self.window:
            self.window.show()
            self.window.restore()
        else:
            open_browser_window(self.port)

    def quit(self):
        log("quit")
        if self.rec.long:
            self.rec.long_end_cb = None
            self.stop_long()
        self.rec.stop(paused=False)
        for hk in self.hotkeys.values():
            hk.clear()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
        os._exit(0)

    def refresh_tray(self):
        if self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass

    def start_tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            log("pystray/Pillow not installed, no tray icon")
            return
        icon_file = RES_DIR / "rewind.ico"
        img = Image.open(icon_file) if icon_file.exists() else Image.new("RGB", (64, 64), (31, 193, 240))
        M = pystray.MenuItem
        menu = pystray.Menu(
            M("Open Rewind", lambda: self.show(), default=True),
            M("Save replay", lambda: threading.Thread(target=self.save_replay, daemon=True).start()),
            M(lambda item: "Stop long recording" if self.rec.long else "Start long recording",
              lambda: threading.Thread(target=self.toggle_long, daemon=True).start()),
            M(lambda item: "Pause buffer" if self.rec.wanted else "Resume buffer", lambda: self.toggle()),
            pystray.Menu.SEPARATOR,
            M("Quit Rewind", lambda: self.quit()),
        )
        self.tray = pystray.Icon("Rewind", img, "Rewind", menu)
        self.tray.run_detached()

    def on_closing(self):
        if self.settings["close_to_tray"] and self.tray:
            self.window.hide()
            if not self.tray_hint_shown:
                self.tray_hint_shown = True
                try:
                    self.tray.notify("Still recording. Press " + self.settings["hotkey"]["label"] +
                                     " to save a replay. Right-click the tray icon to quit.", "Rewind")
                except Exception:
                    pass
            return False
        self.quit()


APP = None


# ---------------------------------------------------------------- local server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _local(self):
        host = self.headers.get("Host", "")
        return host in (f"127.0.0.1:{APP.port}", f"localhost:{APP.port}")

    def _authed(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "rw" and secrets.compare_digest(v, TOKEN):
                return True
        return False

    def _send(self, code, body, ctype="application/json", cookie=False):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        if cookie:
            self.send_header("Set-Cookie", f"rw={TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._local():
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                html = UI_FILE.read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
                return self._send(200, html.encode(), "text/html; charset=utf-8", cookie=True)
            if path == "/logo.png" and (RES_DIR / "logo.png").exists():
                return self._send(200, (RES_DIR / "logo.png").read_bytes(), "image/png")
            if path in ("/editor.js", "/editor.css"):
                f = UI_FILE.parent / path[1:]
                return self._send(200, f.read_bytes(), "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
            if path not in ("/logo.png", "/editor.js", "/editor.css") and not self._authed():
                return self._send(403, {"error": "forbidden"})
            if path == "/api/editor/sounds":
                q = parse_qs(urlparse(self.path).query)
                return self._send(200, APP.search_sounds(q.get("q", [""])[0], q.get("kind", ["sfx"])[0], q.get("page", ["1"])[0]))
            if path == "/api/editor/project":
                return self._send(200, APP.load_project())
            if path == "/api/editor/wave":
                try:
                    return self._send(200, APP.waveform(unquote(parse_qs(urlparse(self.path).query).get("src", [""])[0])))
                except Exception:
                    return self._send(200, {"ok": False, "peaks": []})
            if path == "/api/editor/job":
                return self._send(200, APP.job_state(parse_qs(urlparse(self.path).query).get("id", [""])[0]))
            if path.startswith("/ext/"):
                p = APP.ext_files.get(unquote(path[5:]))
                if p and Path(p).exists():
                    return self._media(Path(p))
                return self._send(404, {"error": "not found"})
            if path == "/api/state":
                return self._send(200, APP.state())
            if path == "/api/clips":
                try:
                    n = int(parse_qs(urlparse(self.path).query).get("n", ["400"])[0])
                except ValueError:
                    n = 400
                return self._send(200, APP.clips(max(50, min(n, 10000))))
            if path.startswith("/strip/"):
                n = int(parse_qs(urlparse(self.path).query).get("n", ["14"])[0])
                return self._send(200, APP.filmstrip(APP.clip_path(unquote(path[7:])), n), "image/jpeg")
            if path.startswith("/thumb/"):
                p = engine.thumb_path(APP.clip_path(unquote(path[7:])))
                if not p.exists():
                    engine.make_thumb(APP.clip_path(unquote(path[7:])))
                return self._send(200, p.read_bytes(), "image/jpeg")
            if path.startswith("/media/"):
                return self._media(APP.clip_path(unquote(path[7:])))
        except (ValueError, FileNotFoundError):
            return self._send(404, {"error": "not found"})
        self._send(404, {"error": "not found"})

    def _media(self, p):
        size = p.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = min(int(b), size - 1) if b else size - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionError, OSError):
                pass

    def do_POST(self):
        if not self._local() or self.headers.get("X-Rewind") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if not path.startswith("/api/window/"):
            APP._count_t = 0                              # anything that might add or remove clips: count again next time
        try:
            if path == "/api/save":
                return self._send(200, APP.save_replay())
            if path == "/api/update/check":
                threading.Thread(target=APP.check_update, kwargs={"manual": True}, daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/update/now":
                return self._send(200, {"ok": APP.update_now()})
            if path == "/api/update/skip":
                APP.update_settings({"skipped_version": str(body.get("version", ""))})
                return self._send(200, {"ok": True})
            if path == "/api/update/apply":
                return self._send(200, {"ok": APP.apply_update()})
            if path == "/api/toggle":
                APP.toggle()
                return self._send(200, {"ok": True})
            if path == "/api/settings":
                APP.update_settings(body)
                return self._send(200, {"ok": True})
            if path == "/api/hotkey":
                w = body.pop("which", "clip")
                key = HOTKEY_KEYS[w]
                if body.get("clear"):
                    if w == "clip":
                        return self._send(200, {"ok": False, "error": "The clip shortcut can't be empty."})
                    APP.update_settings({key: None})
                    return self._send(200, {"ok": True})
                old = APP.settings.get(key)
                if "mode" in body and "vk" not in body:      # only changing tap / long press
                    if old:
                        APP.update_settings({key: {**old, "mode": "long" if body["mode"] == "long" else "tap"}})
                    return self._send(200, {"ok": True})
                mode = body.get("mode") or (old or {}).get("mode", "tap")
                APP.update_settings({key: {"mods": body["mods"], "vk": body["vk"], "label": body["label"], "mode": mode}})
                if not APP.hotkeys[w].ok:  # taken: keep the old one working
                    err = APP.hotkeys[w].error
                    APP.update_settings({key: old})
                    APP.hotkeys[w].error = err
                    return self._send(200, {"ok": False, "error": err})
                return self._send(200, {"ok": True})
            if path == "/api/editor/pick-audio":
                return self._send(200, APP.pick_audio())
            if path == "/api/editor/sound-fetch":
                return self._send(200, APP.fetch_sound(body.get("url", ""), body.get("title", "")))
            if path == "/api/editor/sfx":
                try:
                    p = sfx.ensure(body.get("name", ""), DATA_DIR / "sfx")
                    return self._send(200, {"ok": True, "id": APP.register_ext(p), "name": sfx.NAMES[body["name"]]})
                except ValueError:
                    return self._send(200, {"ok": False, "error": "Unknown sound."})
            if path == "/api/editor/project/save":
                return self._send(200, APP.save_project(body))
            if path == "/api/editor/project/clear":
                return self._send(200, APP.clear_project())
            if path == "/api/editor/export":
                return self._send(200, APP.start_export(body))
            if path == "/api/editor/cancel":
                APP.cancel_export(body.get("id", ""))
                return self._send(200, {"ok": True})
            if path == "/api/diagnostics":
                text = APP.diagnostics()
                return self._send(200, {"ok": share.copy_text_to_clipboard(text), "text": text})
            if path == "/api/open-log":
                winbits.reveal(LOG_FILE)
                return self._send(200, {"ok": True})
            if path == "/api/long/toggle":
                threading.Thread(target=APP.toggle_long, daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/bookmark":
                return self._send(200, APP.add_bookmark())
            if path == "/api/share/copy":
                return self._send(200, {"ok": share.copy_file_to_clipboard(APP.clip_path(body["name"]))})
            if path == "/api/share/discord":
                try:
                    dest = share.make_discord_copy(APP.clip_path(body["name"]), int(body.get("mb", 10)))
                    copied = share.copy_file_to_clipboard(dest)
                    return self._send(200, {"ok": True, "copied": copied, "size_mb": round(dest.stat().st_size / 1e6, 1),
                                            "name": dest.relative_to(Path(APP.settings["clips_dir"]).resolve()).as_posix()})
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/share/consent":
                APP.update_settings({"share_ok": True})
                return self._send(200, {"ok": True})
            if path == "/api/share/link":
                if not APP.settings.get("share_ok"):
                    return self._send(200, {"ok": False, "need_consent": True})
                try:
                    src = APP.clip_path(body["name"])
                    share.check_length(src)
                    tmp = None
                    if body.get("hours") == "forever" and src.stat().st_size > share.PERMANENT_MAX_MB * 1024 * 1024:
                        tmp = share.make_discord_copy(src, share.PERMANENT_MAX_MB - 12)   # the link gets a smaller copy
                        src = tmp
                    try:
                        url = share.upload_for_link(src, body.get("hours", "72h"))
                    finally:
                        if tmp and tmp.exists():
                            tmp.unlink()
                    share.copy_text_to_clipboard(url)
                    return self._send(200, {"ok": True, "url": url})
                except Exception as e:
                    log(f"upload failed: {e}")
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/pick-folder":
                r = APP.pick_folder()
                log(f"clips folder dialog returned: {r!r}")
                if r:
                    APP.update_settings({"clips_dir": str(Path(r))})
                return self._send(200, {"ok": bool(r), "path": APP.settings["clips_dir"]})
            if path == "/api/set-folder":                     # a folder typed or pasted into Settings
                try:
                    p = Path(str(body.get("path", "")).strip().strip('"')).expanduser()
                    if not str(p) or str(p) == ".":
                        raise OSError("Type or paste a folder path first.")
                    p.mkdir(parents=True, exist_ok=True)
                    probe = p / ".rewind-write-test"
                    probe.write_text("ok")
                    probe.unlink()
                except OSError as e:
                    return self._send(200, {"ok": False, "error": f"Rewind can't save to that folder: {e}"})
                APP.update_settings({"clips_dir": str(p.resolve())})
                log(f"clips folder set to {p}")
                return self._send(200, {"ok": True, "path": APP.settings["clips_dir"]})
            if path == "/api/open-folder":
                winbits.open_folder(APP.settings["clips_dir"])
                return self._send(200, {"ok": True})
            if path == "/api/clips/check":
                try:
                    return self._send(200, engine.clip_health(APP.clip_path(body["name"])))
                except Exception as e:
                    log(f"clip check failed: {e}")
                    return self._send(200, {"ok": False, "verdict": "Couldn't check this clip: " + str(e)})
            if path == "/api/clips/reveal":
                winbits.reveal(APP.clip_path(body["name"]))
                return self._send(200, {"ok": True})
            if path == "/api/clips/delete":
                p = APP.clip_path(body["name"])
                winbits.to_recycle_bin(p)
                for t in (engine.thumb_path(p), engine.bookmarks_path(p)):
                    if t.exists():
                        t.unlink()
                return self._send(200, {"ok": True})
            if path == "/api/clips/trim":
                return self._send(200, APP.trim_clip(body))
            if path == "/api/clips/rename":
                p = APP.clip_path(body["name"])
                q = p.parent / (engine.safe_name(body["title"]) + ".mp4")
                if q.exists() and q != p:
                    return self._send(200, {"ok": False, "error": "A clip with that name already exists."})
                for i in range(24):                      # the player or the thumbnail maker may still hold the file for a moment
                    try:
                        p.rename(q)
                        break
                    except PermissionError:
                        if i == 23:
                            return self._send(200, {"ok": False, "error": "That clip is still in use. Close the player and try again in a moment."})
                        time.sleep(0.25)
                for old, new in ((engine.thumb_path(p), engine.thumb_path(q)), (engine.bookmarks_path(p), engine.bookmarks_path(q))):
                    try:
                        if old.exists():
                            old.rename(new)
                    except OSError:
                        pass
                return self._send(200, {"ok": True, "name": q.relative_to(Path(APP.settings["clips_dir"]).resolve()).as_posix()})
            if path == "/api/open-url":
                url = body.get("url", "")
                allowed = [u for u in (WEBSITE, (APP.update or {}).get("url")) if u]
                if url in allowed:
                    import webbrowser
                    webbrowser.open(url)
                return self._send(200, {"ok": url in allowed})
            if path == "/api/overlay/preview":
                APP.show_toast("Preview", force=True)
                return self._send(200, {"ok": True})
            if path == "/api/sound/preview":
                winbits.play_sound(body.get("name", "chime"), body.get("volume", "medium"))
                return self._send(200, {"ok": True})
            if path in ("/api/games/ignore", "/api/games/unignore"):
                exe = str(body.get("exe", ""))
                ig = [e for e in APP.settings.get("ignored_games", []) if e.lower() != exe.lower()]
                if path.endswith("/ignore") and exe:
                    ig.append(exe)
                APP.update_settings({"ignored_games": ig})
                return self._send(200, {"ok": True})
            if path == "/api/games/window":
                exe = str(body.get("exe", ""))
                wg = [e for e in APP.settings.get("window_games", []) if e.lower() != exe.lower()]
                APP.update_settings({"window_games": wg})
                threading.Thread(target=APP.rec.restart, daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/outputs":
                APP.outputs = engine.output_devices()
                return self._send(200, APP.outputs)
            if path == "/api/mics":
                APP.mics = engine.audio_devices()
                return self._send(200, APP.mics)
            if path.startswith("/api/window/") and APP.window:
                w, act = APP.window, path.rsplit("/", 1)[1]
                mgr = APP.winmgr
                if mgr and act in ("drag-start", "drag-move", "drag-end", "resize-start", "resize-move", "resize-end", "state", "maximize"):
                    if act == "drag-start":
                        mgr.drag_start()
                    elif act == "drag-move":
                        mgr.drag_move()
                    elif act == "drag-end":
                        mgr.drag_end()
                    elif act == "resize-start":
                        mgr.resize_start(body.get("edge", ""))
                    elif act == "resize-move":
                        mgr.resize_move()
                    elif act == "resize-end":
                        mgr.resize_end()
                    elif act == "maximize":
                        mgr.toggle_maximize()
                    return self._send(200, {"ok": True, "state": mgr.state})
                if act == "minimize":
                    w.minimize()
                elif act == "maximize":
                    maxed = getattr(APP, "maxed", False)
                    w.restore() if maxed else w.maximize()
                    APP.maxed = not maxed
                elif act == "close":
                    threading.Thread(target=APP.on_closing, daemon=True).start()
                elif act == "pin":
                    w.on_top = bool(body.get("on"))
                return self._send(200, {"ok": True})
        except Exception as e:
            log("api error: " + traceback.format_exc())
            return self._send(200, {"ok": False, "error": str(e)})
        self._send(404, {"error": "not found"})


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("REWIND_PORT", 0))), Handler)
    srv.daemon_threads = True
    APP.port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def open_browser_window(port):
    url = f"http://127.0.0.1:{port}/"
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(exe):
            subprocess.Popen([exe, f"--app={url}", "--window-size=1260,800"])
            return
    import webbrowser
    webbrowser.open(url)


def main():
    global APP
    if os.name == "nt" and not engine.TEST and os.environ.get("REWIND_HEADLESS") != "1":
        import ctypes
        ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\RewindSingleInstance")
        if ctypes.windll.kernel32.GetLastError() == 183:  # already running: two copies would share one buffer
            ctypes.windll.user32.MessageBoxW(0, "Rewind is already running. Look for its icon in the system tray.", "Rewind", 0x40)
            return
    try:                                                       # if Rewind ever crashes natively, this says where
        import faulthandler
        faulthandler.enable(open(DATA_DIR / "crash.log", "a", buffering=1), all_threads=True)
    except Exception:
        pass
    APP = App()
    log(f"Rewind {VERSION} starting")
    engine.LOG_FILE = str(LOG_FILE)
    if APP.settings.get("start_with_windows"):
        try:
            set_autostart(True)                      # keeps the entry pointing at the exe's current place
        except OSError:
            pass
    engine.kill_stale_ffmpeg(log)
    start_server()
    h = APP.settings["hotkey"]
    for w in HOTKEY_KEYS:
        APP.apply_hotkey(w, retries=20)
    APP.watcher.tick()
    APP.watcher.start()
    def begin_buffer():
        if APP.settings.get("game_only") and not APP.current_game():
            APP.rec.stop(waiting=True)
        else:
            APP.rec.start()

    def ffmpeg_urls():
        urls = [engine.FFMPEG_URL]
        if REPO:
            urls.insert(0, f"https://github.com/{REPO}/releases/download/{engine.FFMPEG_TAG}/ffmpeg-win64.zip")
        return list(dict.fromkeys(urls))

    if engine.have_ffmpeg() and not engine.needs_pinned():
        begin_buffer()
    else:
        def first_run_setup():
            had = engine.have_ffmpeg()
            APP.rec.state = "starting"
            try:
                log("downloading the pinned ffmpeg" if not had else "switching to the pinned ffmpeg")
                word = "Updating" if had else "First run: downloading"
                engine.download_ffmpeg(lambda p: setattr(APP.rec, "notice", f"{word} video tools ({p}%). Rewind starts by itself when it's done."), ffmpeg_urls())
                APP.rec.notice = ""
                begin_buffer()
            except Exception as e:
                log(f"ffmpeg download failed: {e}")
                APP.rec.notice = ""
                if had:                      # keep recording with what's already there
                    begin_buffer()
                else:
                    APP.rec.state = "error"
                    APP.rec.error = "Couldn't download the video tools. Check your internet and restart Rewind."
        threading.Thread(target=first_run_setup, daemon=True).start()
    threading.Thread(target=lambda: setattr(APP, "mics", engine.audio_devices()), daemon=True).start()
    threading.Thread(target=lambda: setattr(APP, "outputs", engine.output_devices()), daemon=True).start()
    threading.Thread(target=APP.find_gpus, daemon=True).start()
    threading.Thread(target=APP.update_loop, daemon=True).start()
    def tidy_clips():
        engine.recover_orphans(log)
        engine.clean_temp()
        trim_log()
        folder = APP.settings["clips_dir"]
        engine.clean_stale_parts(folder)
        n = engine.repair_library(folder, log)
        if n:
            log(f"repaired {n} clip(s)")
    threading.Thread(target=tidy_clips, daemon=True).start()
    APP.start_tray()
    hidden = APP.settings.get("start_hidden") or "--hidden" in sys.argv
    if os.environ.get("REWIND_HEADLESS") == "1":
        print(f"http://127.0.0.1:{APP.port}/", flush=True)
        while True:
            time.sleep(3600)
    try:
        import webview
    except ImportError:
        if not hidden:
            open_browser_window(APP.port)
        while True:
            time.sleep(3600)
    APP.window = webview.create_window(
        "Rewind", f"http://127.0.0.1:{APP.port}/", width=1260, height=800, min_size=(900, 600),
        frameless=True, easy_drag=False, background_color="#0E1219", hidden=hidden)
    APP.window.events.closing += APP.on_closing
    if os.name == "nt":
        import winmgr
        def remember(geom):
            APP.settings["window"] = geom
            save_settings(APP.settings)
        APP.winmgr = winmgr.Manager(lambda: APP.window, remember)
        saved_geom = APP.settings.get("window")
        if saved_geom:
            APP.window.events.shown += lambda: threading.Timer(0.5, lambda: APP.winmgr.apply(saved_geom)).start()
    if APP.settings.get("soft_decode"):
        # play clips with the processor instead of the graphics card's video decoder, which can stall on long videos
        extra = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (extra + " --disable-accelerated-video-decode").strip()
    webview.start(private_mode=False)
    APP.quit()


if __name__ == "__main__":
    if "--guard" in sys.argv:                       # the helper that saves a long recording if Rewind stops unexpectedly
        engine.guardian_main(sys.argv[sys.argv.index("--guard") + 1])
        sys.exit(0)
    try:
        main()
    except Exception:
        log("crash: " + traceback.format_exc())
        raise

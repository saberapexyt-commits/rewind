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
from urllib.parse import unquote, urlparse

import engine
import games
import winbits

VERSION = "1.0.8"
APP_DIR = engine.APP_DIR
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
UI_FILE = RES_DIR / "ui" / "index.html"
DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "Rewind"
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
    "length": 30, "fps": 60, "quality": "balanced", "encoder": "auto", "monitor": 0,
    "desktop_audio": True, "mic": True, "mic_device": None,
    "hotkey": {"mods": 1, "vk": 0x77, "label": "Alt + F8"},
    "sound": True, "sound_name": "clip", "sound_volume": "medium",
    "capture": "auto", "window_games": [], "game_only": False, "game_folders": True, "ignored_games": [],
    "close_to_tray": True, "auto_update": True, "skipped_version": "", "start_hidden": False,
    "clips_dir": winbits.default_clips_dir(),
}
RESTART_KEYS = {"length", "fps", "quality", "encoder", "monitor", "desktop_audio", "mic", "mic_device", "capture"}


def log(msg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def load_settings():
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    if not s.get("sound", True):  # older settings files
        s["sound_name"], s["sound"] = "off", True
    return s


def save_settings(s):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


class App:
    def __init__(self):
        self.settings = load_settings()
        self.watcher = games.GameWatcher(lambda: self.settings.get("ignored_games", []), self.on_game_change, log)
        self.rec = engine.Recorder(self.settings, log=log, title_fn=winbits.foreground_title,
                                   game_fn=self.current_game, remember_window_game=self.remember_window_game)
        self.hotkey = winbits.Hotkey(self.save_replay)
        self.window = None
        self.tray = None
        self.events = []  # toasts for the UI: saved / failed
        self.monitors = winbits.monitors()
        self.mics = []
        self.port = 0
        self.tray_hint_shown = False
        self.update = None  # {"version", "url", ...} when GitHub has a newer release
        self.update_status = {"state": "idle", "checked": None, "error": ""}
        self._durations = {}

    def check_update(self, manual=False):
        """Look for a newer GitHub release; when running as the exe, download it in the background."""
        if not REPO or self.update_status["state"] == "checking":
            return
        self.update_status.update(state="checking", error="")
        try:
            import urllib.request
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "Rewind"})
            with urllib.request.urlopen(req, timeout=10) as r:
                rel = json.load(r)
            tag = rel.get("tag_name", "")
            self.update_status["checked"] = int(time.time())
            if version_tuple(tag) <= version_tuple(VERSION):
                self.update = None
                self.update_status["state"] = "latest"
                return
            asset = next((a["browser_download_url"] for a in rel.get("assets", []) if a.get("name") == "Rewind.exe"), None)
            if not (self.update and self.update.get("version") == tag.lstrip("v")):
                self.update = {"version": tag.lstrip("v"), "url": rel.get("html_url") or WEBSITE,
                               "notes": (rel.get("body") or "").strip()[:600],
                               "ready": False, "auto": bool(asset and getattr(sys, "frozen", False)), "asset": asset}
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
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
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
            folder = Path(self.settings["clips_dir"])
            if game and self.settings.get("game_folders", True):
                folder = folder / engine.safe_name(game["name"])
            if self.rec.state == "buffering" and self.rec.order:
                winbits.play_saved_sound(self.settings.get("sound_name", "clip"), self.settings.get("sound_volume", "medium"))
            p = self.rec.save(folder, title=game["name"] if game else None)
            rel = p.relative_to(Path(self.settings["clips_dir"])).as_posix()
            self.events.append({"id": time.time(), "kind": "saved", "name": rel})
            return {"ok": True, "name": rel}
        except Exception as e:
            log("save failed: " + traceback.format_exc())
            if self.settings.get("sound_name") != "off":
                winbits.play_error_sound(self.settings.get("sound_volume", "medium"))
            self.events.append({"id": time.time(), "kind": "error", "message": str(e)})
            return {"ok": False, "error": str(e)}

    def toggle(self):
        if self.rec.wanted:
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
        if "hotkey" in patch:
            h = self.settings["hotkey"]
            self.hotkey.set(h["mods"], h["vk"])
        if "game_only" in patch:
            if patch["game_only"] and not self.current_game() and self.rec.state != "paused":
                self.rec.stop(waiting=True)
            elif not patch["game_only"] and self.rec.state == "waiting":
                self.rec.start()
        if "ignored_games" in patch:
            self.watcher.tick()
        if restart:
            threading.Thread(target=self.rec.restart, daemon=True).start()

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
            "monitors": self.monitors, "mics": self.mics,
            "events": self.events[-5:],
            "clip_count": len(self.clip_files()),
            "native_window": self.window is not None,
            "website": WEBSITE, "update": self.update, "update_status": self.update_status,
        }

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

    def clips(self):
        d = Path(self.settings["clips_dir"])
        out = []
        for p in sorted(self.clip_files(), key=lambda p: p.stat().st_mtime, reverse=True)[:400]:
            st = p.stat()
            out.append({"name": p.relative_to(d).as_posix(), "title": p.stem,
                        "game": p.parent.name if p.parent != d else "",
                        "size_mb": round(st.st_size / 1e6, 1), "mtime": st.st_mtime,
                        "duration": self.clip_duration(p, st)})
        return out

    def trim_clip(self, b):
        """Cut a clip to [start, end]. mode "copy" saves a new clip next to it, "replace" overwrites the original."""
        src = self.clip_path(b["name"])
        start, end = max(0.0, float(b["start"])), float(b["end"])
        total = engine.duration_of(src)
        end = min(end, total) if total else end
        if end - start < 0.5:
            return {"ok": False, "error": "Pick at least half a second to keep."}
        if start < 0.05 and total and end > total - 0.05:
            return {"ok": False, "error": "That's the whole clip. Drag the handles to cut it first."}
        tmp = src.with_name(f"trim-{secrets.token_hex(4)}.part")
        s = self.settings

        def attempt(enc):
            cmd = [engine.FFMPEG, "-hide_banner", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src),
                   "-t", f"{end - start:.3f}", "-map", "0:v:0", "-map", "0:a?"]
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
            if b.get("mode") == "replace":
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
                base = src.stem + " (trimmed)"
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
        self.rec.stop(paused=False)
        self.hotkey.clear()
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

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
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
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if path == "/logo.png" and (RES_DIR / "logo.png").exists():
                return self._send(200, (RES_DIR / "logo.png").read_bytes(), "image/png")
            if path == "/api/state":
                return self._send(200, APP.state())
            if path == "/api/clips":
                return self._send(200, APP.clips())
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
                old = dict(APP.settings["hotkey"])
                APP.update_settings({"hotkey": body})
                if not APP.hotkey.ok:  # taken: keep the old one working
                    err = APP.hotkey.error
                    APP.update_settings({"hotkey": old})
                    APP.hotkey.error = err
                    return self._send(200, {"ok": False, "error": err})
                return self._send(200, {"ok": True})
            if path == "/api/pick-folder":
                r = APP.pick_folder()
                if r:
                    APP.update_settings({"clips_dir": r})
                return self._send(200, {"ok": bool(r), "path": APP.settings["clips_dir"]})
            if path == "/api/open-folder":
                winbits.open_folder(APP.settings["clips_dir"])
                return self._send(200, {"ok": True})
            if path == "/api/clips/reveal":
                winbits.reveal(APP.clip_path(body["name"]))
                return self._send(200, {"ok": True})
            if path == "/api/clips/delete":
                p = APP.clip_path(body["name"])
                winbits.to_recycle_bin(p)
                t = engine.thumb_path(p)
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
                p.rename(q)
                t = engine.thumb_path(p)
                if t.exists():
                    t.rename(engine.thumb_path(q))
                return self._send(200, {"ok": True, "name": q.relative_to(Path(APP.settings["clips_dir"]).resolve()).as_posix()})
            if path == "/api/open-url":
                url = body.get("url", "")
                allowed = [u for u in (WEBSITE, (APP.update or {}).get("url")) if u]
                if url in allowed:
                    import webbrowser
                    webbrowser.open(url)
                return self._send(200, {"ok": url in allowed})
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
            if path == "/api/mics":
                APP.mics = engine.audio_devices()
                return self._send(200, APP.mics)
            if path.startswith("/api/window/") and APP.window:
                w, act = APP.window, path.rsplit("/", 1)[1]
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
    APP = App()
    log(f"Rewind {VERSION} starting")
    start_server()
    h = APP.settings["hotkey"]
    APP.hotkey.set(h["mods"], h["vk"], retries=20)
    APP.watcher.tick()
    APP.watcher.start()
    def begin_buffer():
        if APP.settings.get("game_only") and not APP.current_game():
            APP.rec.stop(waiting=True)
        else:
            APP.rec.start()

    if engine.have_ffmpeg():
        begin_buffer()
    else:
        def first_run_setup():
            APP.rec.state = "starting"
            try:
                log("ffmpeg missing, downloading")
                engine.download_ffmpeg(lambda p: setattr(APP.rec, "notice", f"First run: downloading video tools ({p}%). Rewind starts by itself when it's done."))
                APP.rec.notice = ""
                begin_buffer()
            except Exception as e:
                log(f"ffmpeg download failed: {e}")
                APP.rec.state = "error"
                APP.rec.error = "Couldn't download the video tools. Check your internet and restart Rewind."
        threading.Thread(target=first_run_setup, daemon=True).start()
    threading.Thread(target=lambda: setattr(APP, "mics", engine.audio_devices()), daemon=True).start()
    threading.Thread(target=APP.update_loop, daemon=True).start()
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
    webview.start(private_mode=False)
    APP.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("crash: " + traceback.format_exc())
        raise

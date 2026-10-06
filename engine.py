"""Rewind engine: keeps the last N seconds of your screen + audio on disk and saves them on demand.

How it works
- ffmpeg captures the screen (Windows Desktop Duplication, `ddagrab`) and encodes on the GPU.
- Output goes to a ring of short .ts segments that overwrite themselves (the "buffer").
- Desktop audio (WASAPI loopback) and the mic are mixed in Python and piped into the same ffmpeg.
- Saving copies the newest segments into one .mp4 with no re-encode, so it takes about a second.
"""
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import json
import queue
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np

IS_WIN = os.name == "nt"
TEST = os.environ.get("REWIND_TEST") == "1"  # fake screen + audio, for testing off Windows
NO_WINDOW = 0x08000000 if IS_WIN else 0
SEG = 2  # seconds per buffer segment
RATE = 48000

APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


BIN_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "Rewind" / "bin"
# The exact ffmpeg build Rewind is tested with. It is mirrored on Rewind's own GitHub release and checked against this
# SHA-256, so a newer ffmpeg (or a changed download page) can never break an install.
FFMPEG_BUILD = "N-125875-g5d4d3bdc61"
FFMPEG_TAG = "ffmpeg-n125875"
FFMPEG_SHA256 = "36c73f5526793f3d4fe06846cfbd42d34d9a6c117afe10f2056cfd8d35a05b64"
FFMPEG_URL = f"https://github.com/saberapexyt-commits/rewind/releases/download/{FFMPEG_TAG}/ffmpeg-win64.zip"


def ffbin(name):
    for c in (APP_DIR / f"{name}.exe", APP_DIR / name, BIN_DIR / f"{name}.exe"):
        if c.exists():
            return str(c)
    return shutil.which(name) or name


FFMPEG, FFPROBE = ffbin("ffmpeg"), ffbin("ffprobe")


_queue_ok = {}


def input_queue_args():
    """-thread_queue_size 1024 for the audio pipe, but only if this ffmpeg still accepts it on an input.

    Some newer builds treat it as an output-only option and refuse to start with 'Invalid argument'."""
    if TEST:
        return ["-thread_queue_size", "1024"]
    if FFMPEG not in _queue_ok:
        try:
            r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-thread_queue_size", "64", "-f", "s16le", "-ar", "48000", "-ac", "2",
                                "-i", "pipe:0", "-t", "0.05", "-f", "null", "-"], input=b"\0" * 40000, capture_output=True,
                               timeout=20, creationflags=NO_WINDOW)
            _queue_ok[FFMPEG] = r.returncode == 0
        except Exception:
            _queue_ok[FFMPEG] = False
    return ["-thread_queue_size", "1024"] if _queue_ok[FFMPEG] else []


def have_ffmpeg():
    return TEST or (Path(FFMPEG).exists() and Path(FFPROBE).exists()) or bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def needs_pinned():
    """True when the ffmpeg Rewind downloaded earlier isn't the pinned build (it was fetched from a moving download)."""
    try:
        if Path(FFMPEG).resolve().parent != BIN_DIR.resolve():
            return False                 # the user's own ffmpeg, or one next to the exe: leave it alone
        return (BIN_DIR / "ffmpeg.build").read_text().strip() != FFMPEG_BUILD
    except Exception:
        return True


def download_ffmpeg(progress=lambda pct: None, urls=None):
    """Fetch the pinned ffmpeg + ffprobe into the Rewind data folder, checking the SHA-256 before using anything."""
    global FFMPEG, FFPROBE
    import hashlib
    import urllib.request
    import zipfile
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BIN_DIR / "ffmpeg.zip.part"
    last = None
    for url in (urls or [FFMPEG_URL]):
        try:
            h = hashlib.sha256()
            req = urllib.request.Request(url, headers={"User-Agent": "Rewind"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                total, got = int(r.headers.get("Content-Length") or 0), 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if total:
                        progress(int(got * 100 / total))
            if h.hexdigest() != FFMPEG_SHA256:
                raise RuntimeError("The video tools download didn't match what Rewind expects, so it was thrown away.")
            break
        except Exception as e:
            last = e
            tmp.unlink(missing_ok=True)
    else:
        raise last or RuntimeError("Couldn't download the video tools.")
    with zipfile.ZipFile(tmp) as z:
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            with z.open(name) as src, open(BIN_DIR / (name + ".part"), "wb") as dst:
                shutil.copyfileobj(src, dst)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        (BIN_DIR / (name + ".part")).replace(BIN_DIR / name)
    (BIN_DIR / "ffmpeg.build").write_text(FFMPEG_BUILD)
    tmp.unlink(missing_ok=True)
    FFMPEG, FFPROBE = ffbin("ffmpeg"), ffbin("ffprobe")


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)


def duration_of(path):
    r = run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- encoders

ENCODERS = {
    "nvidia": ("h264_nvenc", "NVIDIA NVENC"),
    "amd": ("h264_amf", "AMD AMF"),
    "intel": ("h264_qsv", "Intel Quick Sync"),
    "cpu": ("libx264", "CPU (x264)"),
}
QUALITY = {"small": 30, "balanced": 25, "best": 20}


PROBE_NOTES = {}


def _probe_one(key, codec):
    """Try a few ways of starting an encoder. Returns True/False and records ffmpeg's reason."""
    base = [FFMPEG, "-hide_banner", "-v", "error"]
    src = ["-f", "lavfi", "-i", "color=black:s=1280x720:d=0.4:r=30"]
    tries = [src + ["-pix_fmt", "nv12", "-c:v", codec, "-f", "null", "-"],
             src + ["-pix_fmt", "yuv420p", "-c:v", codec, "-f", "null", "-"]]
    if key == "intel":
        tries.append(["-init_hw_device", "qsv=hw", "-filter_hw_device", "hw"] + src +
                     ["-vf", "format=nv12,hwupload=extra_hw_frames=64,format=qsv", "-c:v", codec, "-f", "null", "-"])
    elif key == "amd":
        tries.append(src + ["-pix_fmt", "nv12", "-c:v", codec, "-usage", "lowlatency", "-f", "null", "-"])
    last = first = ""
    for args in tries:
        try:
            r = run(base + args, timeout=30)
        except Exception as e:
            last = str(e)
            continue
        if r.returncode == 0:
            PROBE_NOTES[key] = ""
            return True
        if not first:
            first = (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1]
    PROBE_NOTES[key] = first or last
    return False


def probe_encoders(log=lambda m: None):
    ok = {}
    for key, (codec, _) in ENCODERS.items():
        if key == "cpu" or TEST:
            ok[key] = key == "cpu"
            continue
        ok[key] = _probe_one(key, codec)
        log(f"encoder {key} ({codec}): {'works' if ok[key] else 'not available: ' + PROBE_NOTES.get(key, '')}")
    return ok


def pick_encoder(choice, available):
    if choice != "auto" and available.get(choice):
        return choice
    for k in ("nvidia", "amd", "intel"):
        if available.get(k):
            return k
    return "cpu"


def video_args(enc, quality, fps):
    q = QUALITY.get(quality, 25)
    gop = ["-g", str(fps * SEG), "-force_key_frames", f"expr:gte(t,n_forced*{SEG})"]
    if enc == "nvidia":
        a = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", str(q), "-b:v", "0"]
    elif enc == "amd":
        a = ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q + 2)]
    elif enc == "intel":
        a = ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(q)]
    else:
        a = ["-c:v", "libx264", "-preset", "ultrafast" if fps > 30 else "veryfast", "-crf", str(q),
             "-pix_fmt", "yuv420p"]
    return a + gop


_filter_opts = {}


def filter_options(name):
    """Option names a filter supports in the bundled ffmpeg (empty set if the filter is missing)."""
    if name not in _filter_opts:
        opts = set()
        try:
            r = run([FFMPEG, "-hide_banner", "-h", f"filter={name}"], timeout=15)
            if "Unknown filter" not in r.stdout + r.stderr:
                opts = set(re.findall(r"^\s{2,4}([a-z_0-9]+)\s+<", r.stdout, re.M)) or {"_present"}
        except Exception:
            pass
        _filter_opts[name] = opts
    return _filter_opts[name]


def window_capture_supported():
    return TEST or bool(filter_options("gfxcapture"))


def _gpu_tail(enc):
    if enc == "intel":
        return ",hwmap=derive_device=qsv,format=qsv"
    if enc == "cpu":
        return ",hwdownload,format=bgra"
    return ""  # NVENC and AMF take the GPU frames directly


def capture_graph(enc, monitor, fps, window=None):
    """Screen capture (Desktop Duplication), or one game's window (Windows Graphics Capture).

    Window capture is the fix for black clips: some fullscreen games and laptops with two
    graphics chips block Desktop Duplication, but still allow capturing the game's window."""
    if TEST:
        src = os.environ.get("REWIND_TEST_WINDOW_SRC" if window else "REWIND_TEST_SRC", "testsrc2=size=1280x720")
        return f"{src}:rate={fps}" if "rate=" not in src else src
    if window:
        o = filter_options("gfxcapture")
        parts = []
        if "hwnd" in o:
            parts.append(f"hwnd={int(window['hwnd'])}")
        elif "window_exe" in o:
            parts.append(f"window_exe={re.escape(window['exe'])}")
        for key, val in (("max_framerate", fps), ("capture_cursor", 1), ("display_border", 0),
                         ("capture_border", 0), ("resize_mode", "scale")):
            if key in o:
                parts.append(f"{key}={val}")
        g = "gfxcapture=" + ":".join(parts)
        g += f",fps={fps}"  # windows only send frames when they change; keep a steady rate
        return g + _gpu_tail(enc)
    o = filter_options("ddagrab")
    g = f"ddagrab=output_idx={monitor}:framerate={fps}:draw_mouse=1"
    if "output_fmt" in o:
        g += ":output_fmt=bgra"  # 8-bit: HDR desktops otherwise come out washed out or black
    return g + _gpu_tail(enc)


# ---------------------------------------------------------------- audio

class Capture:
    """One audio input, resampled to 48 kHz stereo float. Holds a small queue of frames."""

    def __init__(self, gain=1.0):
        self.q = deque()
        self.n = 0
        self.lock = threading.Lock()
        self.gain = gain

    def push(self, frames):  # float32 (n, 2) at RATE
        with self.lock:
            self.q.append(frames)
            self.n += len(frames)

    def take(self, n):
        out = np.zeros((n, 2), np.float32)
        with self.lock:
            # if we fell behind (or the device runs fast), drop the oldest audio to stay in sync
            excess = self.n - n - int(0.25 * RATE)
            while excess > 0 and self.q:
                c = self.q[0]
                if len(c) <= excess:
                    self.q.popleft(); self.n -= len(c); excess -= len(c)
                else:
                    self.q[0] = c[excess:]; self.n -= excess; excess = 0
            got = 0
            while got < n and self.q:
                c = self.q[0]
                k = min(n - got, len(c))
                out[got:got + k] = c[:k]
                if k == len(c):
                    self.q.popleft()
                else:
                    self.q[0] = c[k:]
                self.n -= k
                got += k
        return out * self.gain

    def close(self):
        pass


class Resampler:
    """Continuous linear resampler. Keeps its position between chunks, so chunk edges
    don't click (resampling each chunk on its own causes tiny crackles)."""

    def __init__(self, src, dst=RATE):
        self.step = src / dst
        self.pos = 0.0
        self.prev = None

    def __call__(self, a):
        if self.step == 1.0 or not len(a):
            return a
        buf = a if self.prev is None else np.vstack([self.prev, a])
        last = len(buf) - 1
        if last < 1:
            self.prev = buf
            return np.zeros((0, 2), np.float32)
        idx = np.arange(self.pos, last, self.step)
        i0 = idx.astype(np.int64)
        frac = (idx - i0)[:, None].astype(np.float32)
        out = buf[i0] * (1 - frac) + buf[i0 + 1] * frac
        self.pos = (idx[-1] + self.step) - last if len(idx) else self.pos - last
        self.prev = buf[-1:]
        return out.astype(np.float32)


def to_stereo(raw, channels):
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    a = a.reshape(-1, channels)
    if channels == 1:
        return np.repeat(a, 2, axis=1)
    if channels >= 6:  # 5.1 / 7.1: fold centre and surrounds into stereo instead of dropping them
        l = a[:, 0] + 0.707 * a[:, 2] + 0.5 * a[:, 4]
        r = a[:, 1] + 0.707 * a[:, 2] + 0.5 * a[:, 5]
        return (np.stack([l, r], axis=1) / 1.6).astype(np.float32)
    return a[:, :2]


def soft_limit(x, knee=0.85):
    """Gentle limiter: leaves normal audio alone and rounds off peaks instead of hard clipping."""
    ax = np.abs(x)
    over = ax > knee
    if over.any():
        x[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((ax[over] - knee) / (1 - knee)))
    return x


class WasapiCapture(Capture):
    def __init__(self, pa_mod, pa, info, gain=1.0):
        super().__init__(gain)
        reported = max(1, min(int(info["maxInputChannels"]), 8))
        rate0 = int(info["defaultSampleRate"])
        last = None
        # some devices (virtual mixers, spatial audio, headsets) report more channels than Windows will open
        # in shared mode, so try the likely ones until one works
        for ch in dict.fromkeys([reported, 2, 1, 6, 8, 4]):
            for rate in dict.fromkeys([rate0, 48000, 44100]):
                resample = Resampler(rate)

                def cb(data, frames, t, status, ch=ch, resample=resample):
                    self.push(resample(to_stereo(data, ch)))
                    return (None, pa_mod.paContinue)

                try:
                    self.stream = pa.open(format=pa_mod.paInt16, channels=ch, rate=rate, input=True,
                                          input_device_index=info["index"], frames_per_buffer=int(rate / 50),
                                          stream_callback=cb)
                    self.stream.start_stream()
                    return
                except Exception as e:
                    last = e
        raise last or RuntimeError("couldn't open the device")

    def close(self):
        try:
            self.stream.stop_stream(); self.stream.close()
        except Exception:
            pass


class ToneCapture(Capture):
    """Test stand-in: a beep every second, so saved clips have audible, checkable audio."""

    def __init__(self):
        super().__init__()
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        t = 0
        while self.alive:
            n = RATE // 50
            idx = np.arange(t, t + n)
            sec = idx / RATE
            env = 0.12 + 0.5 * np.abs(np.sin(sec * 1.3) * np.sin(sec * 3.7 + 1)) ** 3
            s = (env * np.sin(2 * np.pi * 220 * sec) * (0.6 + 0.4 * np.sin(sec * 9))).astype(np.float32)
            self.push(np.stack([s, s], axis=1))
            t += n
            time.sleep(0.02)

    def close(self):
        self.alive = False


def audio_devices():
    """Microphones the user can pick. Empty list if the audio library isn't installed."""
    if TEST:
        return [{"id": "test-mic", "name": "Test microphone"}]
    try:
        import pyaudiowpatch as pa_mod
    except ImportError:
        return []
    pa = pa_mod.PyAudio()
    try:
        api = pa.get_host_api_info_by_type(pa_mod.paWASAPI)
        out = []
        for i in range(api["deviceCount"]):
            d = pa.get_device_info_by_host_api_device_index(api["index"], i)
            if d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice"):
                out.append({"id": d["name"], "name": d["name"]})
        return out
    finally:
        pa.terminate()


def is_virtual_mic(name):
    n = name.lower()
    return any(k in n for k in ("voicemeeter", "virtual", "stereo mix", "vb-audio", "cable output"))


class AudioPump(threading.Thread):
    """Writes a steady real-time 48 kHz stream to ffmpeg, filling silence with zeros.

    Loopback capture goes quiet when nothing is playing, so without this pump
    the audio would drift out of sync with the video."""

    def __init__(self, write, desktop, mic, mic_name, on_error):
        super().__init__(daemon=True)
        self.write, self.on_error = write, on_error
        self.alive = True
        self.levels = deque(maxlen=300 * 4)  # one peak value per 0.25 s
        self.sources, self.pa, self.mic_error = [], None, ""
        if TEST:
            if desktop:
                self.sources.append(ToneCapture())
            return
        import pyaudiowpatch as pa_mod
        self.pa = pa_mod.PyAudio()
        api = self.pa.get_host_api_info_by_type(pa_mod.paWASAPI)
        if desktop:
            spk = self.pa.get_device_info_by_index(api["defaultOutputDevice"])
            if not spk.get("isLoopbackDevice"):
                for lb in self.pa.get_loopback_device_info_generator():
                    if spk["name"] in lb["name"]:
                        spk = lb
                        break
            self.sources.append(WasapiCapture(pa_mod, self.pa, spk))
        self.mic_error = ""
        if mic:
          try:
            dev = None
            mics = []
            for i in range(api["deviceCount"]):
                d = self.pa.get_device_info_by_host_api_device_index(api["index"], i)
                if d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice"):
                    mics.append(d)
                    if d["name"] == mic_name:
                        dev = d
            if dev is None:
                dev = self.pa.get_device_info_by_index(api["defaultInputDevice"])
                # Windows' default input is often a silent virtual device (Voicemeeter, Oculus, Stereo Mix): prefer a real mic
                if is_virtual_mic(dev["name"]):
                    dev = next((m for m in mics if not is_virtual_mic(m["name"])), dev)
            self.sources.append(WasapiCapture(pa_mod, self.pa, dev, gain=1.2))
          except Exception as e:  # no mic, or Windows is blocking it: keep recording game sound
            self.mic_error = ("Couldn't use the microphone. Check Windows Settings > Privacy > Microphone "
                              f"and that a mic is plugged in. ({e})")

    def run(self):
        t0, written, acc_peak, acc_n = time.monotonic(), 0, 0.0, 0
        try:
            while self.alive:
                time.sleep(0.01)
                n = int((time.monotonic() - t0) * RATE) - written
                if n <= 0:
                    continue
                if n > RATE:
                    # The PC slept, or this thread was frozen for a while. Writing the whole gap as silence is what
                    # once put hours of audio into a short clip, so skip it and carry on in real time.
                    written += n - RATE // 50
                    for s in self.sources:
                        with s.lock:
                            s.q.clear(); s.n = 0
                    continue
                mix = np.zeros((n, 2), np.float32)
                for s in self.sources:
                    mix += s.take(n)
                soft_limit(mix)
                acc_peak = max(acc_peak, float(np.abs(mix).max()) if n else 0.0)
                acc_n += n
                if acc_n >= RATE // 4:
                    self.levels.append(round(acc_peak, 3))
                    acc_peak, acc_n = 0.0, 0
                self.write((mix * 32767).astype(np.int16).tobytes())
                written += n
        except (BrokenPipeError, OSError, ValueError):
            pass
        except Exception as e:
            self.on_error(f"Audio stopped: {e}")

    def stop(self):
        self.alive = False
        for s in self.sources:
            s.close()
        if self.pa:
            try:
                self.pa.terminate()
            except Exception:
                pass


# ---------------------------------------------------------------- recorder

def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip(" .")
    return s[:60] or "Desktop"


def frame_stats(path):
    """(mean, spread) brightness of one tiny grey frame from a buffer piece, or None."""
    try:
        r = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-frames:v", "1",
                            "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"],
                           capture_output=True, timeout=20, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        a = np.frombuffer(r.stdout, np.uint8)
        if a.size < 64 * 36:
            return None
        return float(a.mean()), float(a.std())
    except Exception:
        return None


def is_black(stats):
    # a flat, dark frame. Real dark scenes still have a HUD, text or noise, so they have spread.
    return stats is not None and stats[1] < 2.5 and stats[0] < 40


class LongRecording:
    """A full-length recording made from the same buffer: each 2 second piece is copied aside as soon as
    ffmpeg finishes it, and the pieces are joined (no re-encode) when the recording stops."""

    def __init__(self, started_at, log):
        self.dir = Path(tempfile.mkdtemp(prefix="rewind-long-"))
        self.t0 = started_at
        self.log = log
        self.n = 0
        self.bookmarks = []
        self.q = queue.Queue()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _run(self):
        while True:
            src = self.q.get()
            if src is None:
                return
            try:
                if src.exists() and src.stat().st_size > 0:
                    shutil.copyfile(src, self.dir / f"{self.n:06d}.ts")
                    self.n += 1
            except OSError as e:
                self.log(f"long recording: couldn't keep {src.name}: {e}")

    def piece_done(self, path):
        self.q.put(path)

    def elapsed(self):
        return max(0.0, time.monotonic() - self.t0)

    def bookmark(self):
        t = round(self.elapsed(), 1)
        self.bookmarks.append(t)
        return t

    def finish(self, last_piece, final):
        """Join everything into `final` (an .mp4 path). Returns the bookmark list."""
        if last_piece:
            self.q.put(last_piece)
        self.q.put(None)
        self.worker.join(60)
        pieces = sorted(self.dir.glob("*.ts"))
        try:
            if not pieces:
                raise RuntimeError("Nothing was recorded.")
            lst = self.dir / "list.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
            part = final.with_name(final.stem + ".part")
            final.parent.mkdir(parents=True, exist_ok=True)
            r = run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                     "-c", "copy", "-avoid_negative_ts", "make_zero", "-f", "mp4", str(part)], timeout=7200)
            if r.returncode != 0 or not part.exists() or part.stat().st_size < 1000:
                raise RuntimeError("Couldn't join the recording: " + (r.stderr.strip().splitlines() or ["unknown"])[-1])
            seal(part, final, self.elapsed() + 60, self.log)
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)
            try:
                part.unlink()
            except (OSError, UnboundLocalError):
                pass
        return self.bookmarks

    def discard(self):
        self.q.put(None)
        shutil.rmtree(self.dir, ignore_errors=True)


def bookmarks_path(video):
    return video.parent / ".thumbs" / (video.stem + ".bookmarks.json")


class Recorder:
    def __init__(self, settings, log=print, title_fn=lambda: "Desktop", game_fn=lambda: None,
                 remember_window_game=lambda exe: None):
        self.settings = settings
        self.log, self.title_fn = log, title_fn
        self.game_fn, self.remember_window_game = game_fn, remember_window_game
        self.window_target = None
        self.capture_kind = "screen"
        self.notice = ""
        self.dark_streak = 0
        self.last_check = None
        self.buf = Path(tempfile.gettempdir()) / ("rewind-buffer-test" if TEST else "rewind-buffer")
        self.proc = None
        self.pump = None
        self.order = deque(maxlen=400)  # segment names in the order ffmpeg opened them
        self.lock = threading.RLock()
        self.save_lock = threading.Lock()
        self.state, self.error = "starting", ""
        self.started_at = 0.0
        self.encoder = "cpu"
        self.available = {}
        self.stderr_tail = deque(maxlen=30)
        self.last_saved = None
        self.saving = False
        self.wanted = False
        self.fails = 0
        self.has_audio = False
        self.auto_gdi = False
        self.audio_note = ""
        self.capture_mode = "dda"
        self.long = None
        self.persist = lambda key, value: None      # the app saves a working capture method here
        self.long_end_cb = None  # called when the buffer stops under a running long recording
        threading.Thread(target=self._watchdog, daemon=True).start()
        threading.Thread(target=self._health, daemon=True).start()

    # ---- lifecycle
    def start(self):
        with self.lock:
            self.wanted = True
            self._launch()

    def wants_window(self, game):
        """Should this game be recorded through its window instead of the screen?"""
        s = self.settings
        if not game or not window_capture_supported():
            return False
        mode = s.get("capture", "auto")
        if mode == "window":
            return True
        return mode == "auto" and game["exe"].lower() in {e.lower() for e in s.get("window_games", [])}

    def game_changed(self, game):
        """Called by the game watcher. Retargets window capture when the game starts or stops."""
        with self.lock:
            if not self.wanted:
                return
            if self.auto_gdi:                       # a temporary fallback: try the fast capture again for the new game
                self.auto_gdi, self.notice, self.fails = False, "", 0
                self.log("trying the fast capture again")
                self._kill(); self._launch()
                return
            if not game:
                self.notice = ""
            if self.capture_kind == "window":
                if not game or game["hwnd"] != self.window_target["hwnd"]:
                    self.log("game window gone or changed, retargeting capture")
                    self._kill(); self._launch()
            elif self.wants_window(game):
                self.log(f"switching to window capture for {game['name']}")
                self._kill(); self._launch()

    def _launch(self):
        s = self.settings
        game = self.game_fn()
        self.window_target = game if self.wants_window(game) else None
        self.capture_kind = "window" if self.window_target else "screen"
        self.dark_streak = 0
        if not self.available:
            self.available = probe_encoders(self.log)
        self.encoder = pick_encoder(s["encoder"], self.available)
        if self.fails >= 5 and self.encoder != "cpu":  # GPU path keeps failing: fall back
            self.log(f"{self.encoder} failed twice, falling back to CPU")
            self.encoder = "cpu"
        shutil.rmtree(self.buf, ignore_errors=True)
        self.buf.mkdir(parents=True, exist_ok=True)
        self.order.clear()
        fps, length = int(s["fps"]), int(s["length"])
        wrap = math.ceil(length / SEG) + 4
        want_audio = bool(s["desktop_audio"] or s["mic"])
        self.has_audio = False
        self.audio_note = ""
        if want_audio and not TEST:
            try:
                import pyaudiowpatch  # noqa: F401
                self.has_audio = True
            except ImportError:
                self.error = "Audio library missing (pip install PyAudioWPatch). Recording video only."
        elif want_audio:
            self.has_audio = True

        cmd = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "info"]
        if TEST:
            cmd += ["-re"]
        mode = self.input_mode()
        self.capture_mode = mode
        if mode == "gdi" and not self.window_target and not TEST:
            # compatibility capture: Windows' classic screen grab. Slower than Desktop Duplication, but it works on
            # every PC, including laptops with two graphics chips and drivers that refuse the fast path
            gfps = min(fps, 30) if self.encoder == "cpu" else fps
            cmd += ["-f", "gdigrab", "-framerate", str(gfps), "-draw_mouse", "1"]
            try:
                import winbits
                mons = winbits.monitors()
                m = mons[int(s["monitor"])] if int(s["monitor"]) < len(mons) else mons[0]
                if m.get("w"):
                    cmd += ["-offset_x", str(m["x"]), "-offset_y", str(m["y"]), "-video_size", f"{m['w']}x{m['h']}"]
            except Exception:
                pass
            cmd += ["-i", "desktop"]
        else:
            cmd += ["-f", "lavfi", "-i", capture_graph(self.encoder, int(s["monitor"]), fps, self.window_target)]
        if self.has_audio:
            cmd += input_queue_args() + ["-f", "s16le", "-ar", str(RATE), "-ac", "2", "-i", "pipe:0"]
        cmd += ["-map", "0:v"] + (["-map", "1:a", "-c:a", "aac", "-b:a", "192k"] if self.has_audio else [])
        cmd += video_args(self.encoder, s["quality"], fps)
        cmd += ["-f", "segment", "-segment_time", str(SEG), "-segment_wrap", str(wrap),
                "-segment_format", "mpegts", "-reset_timestamps", "1", str(self.buf / "seg%03d.ts")]
        self.log("ffmpeg: " + " ".join(cmd))
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if self.has_audio else subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     creationflags=NO_WINDOW, bufsize=0)
        self.started_at = time.monotonic()
        self.state = "buffering"
        if not self.has_audio or "Audio library" not in self.error:
            self.error = ""
        threading.Thread(target=self._read_stderr, args=(self.proc,), daemon=True).start()
        if self.has_audio:
            try:
                self.pump = AudioPump(self.proc.stdin.write, s["desktop_audio"], s["mic"], s.get("mic_device"),
                                      on_error=self._set_error)
                self.pump.start()
                if self.pump.mic_error:
                    self.notice = self.pump.mic_error
            except Exception as e:
                self.pump = None
                self.audio_note = f"Couldn't open audio, so Rewind is recording video only: {e}"
                self.log(self.audio_note)
                # keep ffmpeg fed with silence so video still records
                self.pump = AudioPump(self.proc.stdin.write, False, False, None, on_error=self._set_error)
                self.pump.start()

    def input_mode(self):
        """"dda" = fast Desktop Duplication, "gdi" = compatibility capture. Automatic starts fast and falls back."""
        pick = self.settings.get("capture_input", "")
        if pick in ("dda", "gdi"):
            return pick
        return "gdi" if self.auto_gdi else "dda"

    def _set_error(self, msg):
        self.error = msg
        self.log(msg)

    def _read_stderr(self, proc):
        pat = re.compile(r"Opening '(.+?)' for writing")
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            m = pat.search(line)
            if m:
                prev = self.order[-1][0] if self.order else None
                self.order.append((Path(m.group(1)).name, time.monotonic()))
                self.fails = 0
                if self.long and prev:
                    self.long.piece_done(self.buf / prev)
            elif line:
                self.stderr_tail.append(line)

    def _kill(self):
        if self.pump:
            self.pump.stop()
            self.pump = None
        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    # ---- long recording
    def start_long(self):
        with self.lock:
            if self.long:
                return False
            if self.state != "buffering" or not self.order:
                raise RuntimeError("Rewind isn't recording yet. Wait a moment and try again.")
            self.long = LongRecording(self.order[-1][1], self.log)
            self.log("long recording started")
            return True

    def stop_long(self, folder, title):
        """Finish the long recording and return (path, bookmarks)."""
        with self.lock:
            lr, self.long = self.long, None
            last = self.buf / self.order[-1][0] if self.order else None
        if not lr:
            raise RuntimeError("No long recording is running.")
        folder = Path(folder)
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        final = folder / f"{safe_name(title)} recording {stamp}.mp4"
        marks = lr.finish(last, final)
        if marks:
            b = bookmarks_path(final)
            b.parent.mkdir(exist_ok=True)
            b.write_text(json.dumps(marks), encoding="utf-8")
        threading.Thread(target=make_thumb, args=(final,), daemon=True).start()
        self.log(f"long recording saved {final}")
        return final, marks

    def stop(self, paused=True, waiting=False):
        if self.long and self.long_end_cb:
            threading.Thread(target=self.long_end_cb, daemon=True).start()
        with self.lock:
            self.wanted = False
            self._kill()
            self.state = "waiting" if waiting else "paused" if paused else "stopped"
            self.notice = ""

    def _health(self):
        """Every few seconds, look at the newest finished piece of the buffer. If it's solid
        black while a game is in front, the game is blocking screen capture: switch to
        recording that game's window, and remember to do so next time."""
        while True:
            time.sleep(4)
            try:
                if self.state != "buffering" or len(self.order) < 2:
                    continue
                seg = self.buf / self.order[-2][0]
                stats = frame_stats(seg)
                if stats is None:
                    continue
                self.last_check = {"mean": round(stats[0], 1), "spread": round(stats[1], 2), "black": is_black(stats)}
                game = self.game_fn()
                if not is_black(stats) or not game or not game.get("focused", True):
                    self.dark_streak = 0
                    if self.notice.startswith("Clips are coming out black"):
                        self.notice = ""
                    continue
                self.dark_streak += 1
                if self.dark_streak < 3:
                    continue
                if self.capture_kind == "screen" and self.settings.get("capture", "auto") == "auto":
                    if window_capture_supported():
                        self.remember_window_game(game["exe"])
                        self.notice = (f"{game['name']} blocked screen capture, so Rewind records its window "
                                       "instead. Rewind will remember this for next time.")
                        self.log(f"black capture in {game['name']}, switching to window capture")
                        with self.lock:
                            if self.wanted:
                                self._kill(); self._launch()
                        continue
                if self.dark_streak == 3:
                    self.notice = ("Clips are coming out black. Set the game to borderless or windowed "
                                   "fullscreen" + ("" if window_capture_supported() else
                                                    ", or update ffmpeg so Rewind can record the game window") + ".")
            except Exception as e:
                self.log(f"health check: {e}")

    def restart(self):
        with self.lock:
            self._kill()
            self.fails = 0
            if self.wanted:
                self._launch()

    def _watchdog(self):
        while True:
            time.sleep(1.5)
            with self.lock:
                # ffmpeg can also sit there alive but silent (a capture method that never produces a frame)
                stalled = (self.wanted and self.proc and self.proc.poll() is None and not self.order and self.state == "buffering"
                           and time.monotonic() - self.started_at > 14 and not TEST)
                if stalled:
                    self.stderr_tail.append("ffmpeg started but no video came out in 14 seconds")
                    self._kill()
                if self.wanted and (stalled or (self.proc and self.proc.poll() is not None)):
                    tail = [l for l in self.stderr_tail if "rror" in l or "ailed" in l or "no video" in l] or list(self.stderr_tail)
                    self.fails += 1
                    self.log("ffmpeg output: " + " | ".join(list(self.stderr_tail)[-8:]))
                    self._set_error("Capture stopped: " + (tail[-1] if tail else "ffmpeg exited"))
                    if self.fails == 3 and self.input_mode() == "dda" and self.settings.get("capture_input", "") == "" and not self.window_target:
                        self.auto_gdi = True
                        self.notice = "The fast screen capture didn't work on this PC, so Rewind is trying compatibility capture."
                        self.log("switching to gdigrab")
                    self.state = "error"
                    self._kill()
                    if self.fails <= 7:
                        # Desktop Duplication can say no for a moment (right after an update restart, a screen switch,
                        # a game going fullscreen), so give it a little longer each time before switching methods
                        time.sleep(min(1 + 2 * self.fails, 7))
                        self._launch()
                        self.state = "buffering"

    # ---- status
    def buffered(self):
        if self.state != "buffering" or not self.order:
            return 0.0
        return min(time.monotonic() - self.order[0][1], float(self.settings["length"]))

    def status(self):
        size = sum(f.stat().st_size for f in self.buf.glob("seg*.ts")) if self.buf.exists() else 0
        levels = list(self.pump.levels)[-int(self.settings["length"]) * 4:] if self.pump else []
        return {
            "state": "saving" if self.saving else self.state,
            "error": self.error,
            "buffered": round(self.buffered(), 1),
            "length": int(self.settings["length"]),
            "disk_mb": round(size / 1e6, 1),
            "encoder": self.encoder,
            "encoder_label": ENCODERS[self.encoder][1],
            "available": self.available,
            "fps": int(self.settings["fps"]),
            "audio": self.has_audio,
            "levels": levels,
            "last_saved": self.last_saved,
            "capture": self.capture_kind,
            "capture_mode": self.capture_mode,
            "audio_note": self.audio_note,
            "capture_label": f"{self.window_target['name']} window" if self.window_target else "Whole screen",
            "window_capture": window_capture_supported(),
            "notice": self.notice,
            "check": self.last_check,
            "long": {"active": bool(self.long), "elapsed": round(self.long.elapsed()) if self.long else 0,
                     "bookmarks": len(self.long.bookmarks) if self.long else 0},
        }

    # ---- save
    def save(self, clips_dir, title=None):
        if self.state != "buffering" or not self.order:
            raise RuntimeError("Nothing to save yet. The buffer is empty.")
        with self.save_lock:
            self.saving = True
            try:
                return self._save(Path(clips_dir), title)
            finally:
                self.saving = False

    def _save(self, clips_dir, title=None):
        length = int(self.settings["length"])
        need = math.ceil(length / SEG) + 1
        names, seen = [], set()
        for name, _ in reversed(self.order):  # newest first, skip names the ring already reused
            if name in seen:
                break
            seen.add(name)
            names.append(name)
            if len(names) >= need:
                break
        names.reverse()
        files = [self.buf / n for n in names if (self.buf / n).exists() and (self.buf / n).stat().st_size > 0]
        if not files:
            raise RuntimeError("Nothing to save yet. The buffer is empty.")

        clips_dir.mkdir(parents=True, exist_ok=True)
        title = safe_name(title or self.title_fn())
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        final = clips_dir / f"{title} {stamp}.mp4"
        n = 2
        while final.exists():
            final = clips_dir / f"{title} {stamp} ({n}).mp4"
            n += 1
        work = Path(tempfile.mkdtemp(prefix="rewind-save-"))
        part = final.with_name(final.stem + ".part")
        try:
            # One pass, straight from the buffer: the ring keeps a few spare pieces so nothing we read is reused
            # while we copy. Every piece starts on a keyframe, so dropping whole pieces is the trim.
            lst = work / "list.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in files), encoding="utf-8")
            r = run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                     "-c", "copy", "-avoid_negative_ts", "make_zero", "-f", "mp4", str(part)], timeout=300)
            if r.returncode != 0 or not part.exists() or part.stat().st_size < 1000:
                raise RuntimeError("Couldn't save the clip: " + (r.stderr.strip().splitlines() or ["unknown"])[-1])
            seal(part, final, length + 4 * SEG + 10, self.log)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            if part.exists():
                try:
                    part.unlink()
                except OSError:
                    pass
        threading.Thread(target=make_thumb, args=(final,), daemon=True).start()
        self.last_saved = final.name
        self.log(f"saved {final}")
        return final


def keyframe_at_or_before(path, t):
    """Latest video keyframe time <= t (reads packet flags only, no decoding)."""
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
             "-of", "csv=p=0", str(path)], timeout=60)
    best = 0.0
    for line in r.stdout.splitlines():
        parts = line.split(",")
        try:
            pts = float(parts[0])
        except (ValueError, IndexError):
            continue
        if "K" in (parts[1] if len(parts) > 1 else "") and pts <= t:
            best = max(best, pts)
    return best


def clip_problem(path, max_len=None):
    """None when the file is sound, otherwise a short reason. A clip that fails this is never kept."""
    try:
        r = run([FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration", "-of", "json", str(path)], timeout=120)
        info = json.loads(r.stdout or "{}")
    except Exception:
        return "can't be read"
    if r.returncode != 0 or not info.get("streams"):
        return "can't be read"

    def dur(kind):
        out = []
        for s in info["streams"]:
            if s.get("codec_type") == kind:
                try:
                    out.append(float(s.get("duration")))
                except (TypeError, ValueError):
                    pass
        return out
    v, a = dur("video"), dur("audio")
    try:
        fmt = float(info.get("format", {}).get("duration") or 0)
    except ValueError:
        fmt = 0.0
    if not v or v[0] <= 0:
        return "has no picture"
    if a and abs(a[0] - v[0]) > 3:
        return f"sound is {a[0]:.0f}s but picture is {v[0]:.0f}s"
    if max_len and fmt > max_len:
        return f"is {fmt:.0f}s long, expected at most {max_len:.0f}s"
    return None


def repair_clip(path):
    """Cut sound that runs past the picture. True when the file was fixed (or already fine)."""
    path = Path(path)
    if clip_problem(path) is None:
        return True
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)], timeout=120)
    try:
        vdur = float(r.stdout.strip())
    except ValueError:
        return False
    part = path.with_name(path.stem + ".repair.part")
    try:
        r = run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0?", "-t", f"{vdur:.3f}",
                 "-c", "copy", "-f", "mp4", str(part)], timeout=900)
        if r.returncode == 0 and part.exists() and part.stat().st_size > 1000 and clip_problem(part) is None:
            os.replace(part, path)
            return True
        return False
    finally:
        try:
            part.unlink()
        except OSError:
            pass


def seal(part, final, max_len=None, log=print):
    """Turn a finished .part file into the real clip, but only if it checks out. A bad file is fixed if it can
    be, and otherwise deleted, so a broken clip never appears in the library."""
    part, final = Path(part), Path(final)
    why = clip_problem(part, max_len)
    if why:
        log(f"clip check failed ({why}), trying to repair")
        fixed = part.with_name(part.stem + ".fixed.part")
        ok = False
        try:
            r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(part)], timeout=120)
            vdur = float(r.stdout.strip())
            r = run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", str(part), "-map", "0:v:0", "-map", "0:a:0?", "-t", f"{vdur:.3f}",
                     "-c", "copy", "-f", "mp4", str(fixed)], timeout=900)
            ok = r.returncode == 0 and fixed.exists() and clip_problem(fixed, max_len) is None
        except Exception:
            ok = False
        if not ok:
            for f in (fixed, part):
                try:
                    f.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"The clip came out damaged ({why}), so it wasn't kept. Nothing was lost from the buffer.")
        os.replace(fixed, part)
    os.replace(part, final)


def clean_stale_parts(folder):
    """Half-written files left behind by a crash or a power cut."""
    try:
        for f in Path(folder).rglob("*.part"):
            try:
                if time.time() - f.stat().st_mtime > 120:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass


def repair_library(folder, log=print):
    """Fix older clips whose sound runs past their picture."""
    fixed = 0
    try:
        files = [f for f in Path(folder).rglob("*.mp4") if not f.name.endswith(".part") and time.time() - f.stat().st_mtime > 30]
    except OSError:
        return 0
    for f in files:
        try:
            if clip_problem(f) and repair_clip(f):
                make_thumb(f)
                log(f"repaired {f.name}")
                fixed += 1
        except Exception as e:
            log(f"couldn't check {f.name}: {e}")
    return fixed


def thumb_path(video):
    return video.parent / ".thumbs" / (video.stem + ".jpg")


def make_thumb(video):
    t = thumb_path(video)
    t.parent.mkdir(exist_ok=True)
    if IS_WIN:
        try:  # hide the thumbnails folder
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(t.parent), 0x02)
        except Exception:
            pass
    d = duration_of(video)
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-ss", f"{max(0, d * 0.6):.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(t)], timeout=60)
    return t

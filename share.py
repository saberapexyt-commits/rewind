"""Sharing helpers: put a clip on the clipboard, shrink it to fit Discord, or upload it for a link.

Nothing here runs unless the user presses a Share button.
"""
import http.client
import os
import re
import ssl
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import engine

NO_WINDOW = engine.NO_WINDOW

# Sizes people actually run into on Discord. Rewind aims a little under each one.
DISCORD_SIZES = {"10": 10, "50": 50, "500": 500}

# Temporary file host. Files are removed by the host after the chosen time, no account needed.
UPLOAD_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
UPLOAD_TIMES = ("1h", "12h", "24h", "72h")
# "Forever": the same host's permanent side. No expiry, but it only takes files up to 200 MB.
PERMANENT_URL = "https://catbox.moe/user/api.php"
PERMANENT_MAX_MB = 200


def copy_file_to_clipboard(path):
    """Put the file itself on the clipboard, so Ctrl+V in Discord attaches it."""
    if os.name != "nt":
        return False
    p = str(Path(path)).replace("'", "''")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", f"Set-Clipboard -LiteralPath '{p}'"],
                       capture_output=True, timeout=20, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    return r.returncode == 0


def copy_text_to_clipboard(text):
    if os.name != "nt":
        return False
    t = text.replace("'", "''")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", f"Set-Clipboard -Value '{t}'"],
                       capture_output=True, timeout=20, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    return r.returncode == 0


def plan_for_size(duration, target_mb, src_w, src_h):
    """Pick video bitrate (kbit/s) and height so the result lands under target_mb."""
    audio_k = 96 if target_mb <= 10 else 128
    total_k = target_mb * 8 * 1024 * 0.90          # keep 10% spare for container overhead
    video_k = int(total_k / max(duration, 1.0) - audio_k)
    if video_k < 120:
        return None
    # fewer pixels when the budget is small, so it doesn't turn to mush
    if video_k < 700:
        height = 360
    elif video_k < 1500:
        height = 540
    elif video_k < 3000:
        height = 720
    else:
        height = min(src_h or 1080, 1080)
    height = min(height, src_h or height)
    return video_k, audio_k, height - (height % 2)


def make_discord_copy(src, target_mb):
    """Re-encode `src` next to itself so it is under target_mb. Returns the new path."""
    src = Path(src)
    dur = engine.duration_of(src)
    r = engine.run([engine.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                    "-of", "csv=p=0", str(src)])
    try:
        w, h = [int(x) for x in r.stdout.strip().split(",")[:2]]
    except ValueError:
        w, h = 1920, 1080
    plan = plan_for_size(dur, target_mb, w, h)
    if not plan:
        raise RuntimeError(f"This clip is {int(dur)} seconds long, too long to squeeze under {target_mb} MB. Trim it first.")
    vk, ak, height = plan
    base = src.stem + f" (Discord {target_mb} MB)"
    dest = src.with_name(base + ".mp4")
    n = 2
    while dest.exists():
        dest = src.with_name(f"{base} {n}.mp4")
        n += 1
    part = dest.with_name(dest.stem + ".part")
    cmd = [engine.FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a?",
           "-vf", f"scale=-2:{height},fps=30,format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{vk}k", "-maxrate", f"{int(vk * 1.1)}k",
           "-bufsize", f"{vk * 2}k", "-c:a", "aac", "-b:a", f"{ak}k", "-ac", "2", "-movflags", "+faststart",
           "-f", "mp4", str(part)]
    res = engine.run(cmd, timeout=1800)
    try:
        if res.returncode != 0 or not part.exists():
            raise RuntimeError("Couldn't shrink the clip: " + (res.stderr.strip().splitlines() or ["unknown"])[-1])
        # if the encoder overshot, take one more pass with a smaller budget
        if part.stat().st_size > target_mb * 1024 * 1024:
            vk2 = int(vk * (target_mb * 1024 * 1024) / part.stat().st_size * 0.9)
            cmd[cmd.index("-b:v") + 1] = f"{vk2}k"
            cmd[cmd.index("-maxrate") + 1] = f"{int(vk2 * 1.1)}k"
            cmd[cmd.index("-bufsize") + 1] = f"{vk2 * 2}k"
            res = engine.run(cmd, timeout=1800)
            if res.returncode != 0:
                raise RuntimeError("Couldn't shrink the clip small enough.")
        os.replace(part, dest)
    finally:
        if part.exists():
            try:
                part.unlink()
            except OSError:
                pass
    return dest


def upload_for_link(path, hours="72h", url=None, progress=lambda pct: None):
    """Upload and return the link the host gives back. hours is 1h/12h/24h/72h, or "forever"."""
    path = Path(path)
    if hours == "forever":
        if path.stat().st_size > PERMANENT_MAX_MB * 1024 * 1024:
            raise RuntimeError(f"Permanent links take files up to {PERMANENT_MAX_MB} MB. Use Shrink for Discord first, or pick a shorter link.")
        url = url or PERMANENT_URL
        fields = {"reqtype": "fileupload", "userhash": ""}
    else:
        if hours not in UPLOAD_TIMES:
            hours = "72h"
        url = url or UPLOAD_URL
        fields = {"reqtype": "fileupload", "time": hours}
    boundary = uuid.uuid4().hex
    head = b""
    for k, v in fields.items():
        head += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    safe = re.sub(r'[^A-Za-z0-9._-]+', "_", path.name)
    head += (f'--{boundary}\r\nContent-Disposition: form-data; name="fileToUpload"; filename="{safe}"\r\n'
             f"Content-Type: video/mp4\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    size = path.stat().st_size
    u = urlparse(url)
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(u.netloc, timeout=120, context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(u.netloc, timeout=120)
    try:
        conn.putrequest("POST", u.path + (("?" + u.query) if u.query else ""))
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(len(head) + size + len(tail)))
        conn.putheader("User-Agent", "Rewind")
        conn.endheaders()
        conn.send(head)
        sent = 0
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                conn.send(chunk)
                sent += len(chunk)
                progress(int(sent * 100 / max(size, 1)))
        conn.send(tail)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace").strip()
    finally:
        conn.close()
    if resp.status != 200 or not body.startswith("http"):
        raise RuntimeError("The upload service said no: " + (body[:120] or f"HTTP {resp.status}"))
    return body.splitlines()[0].strip()

"""Rewind's video editor: turns the editor's project (clips, text, music) into one ffmpeg render.

The editor in the app previews the same project live; this module renders it to an mp4.
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import engine

FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
# preview names -> font files (all ship with Windows)
FONTS = {
    "segoe": ("segoeui.ttf", "segoeuib.ttf"),
    "arial": ("arial.ttf", "arialbd.ttf"),
    "impact": ("impact.ttf", "impact.ttf"),
    "black": ("ariblk.ttf", "ariblk.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf"),
    "consolas": ("consola.ttf", "consolab.ttf"),
    "comic": ("comic.ttf", "comicbd.ttf"),
}
SIZES = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
QUALITY = {"draft": "small", "standard": "balanced", "high": "best"}


class EditorError(Exception):
    pass


def output_size(aspect, height_cap):
    """Pixel size for an aspect ratio. height_cap is the 'short side' budget: 720 or 1080."""
    aw, ah = SIZES.get(aspect, (16, 9))
    short = height_cap
    if aw >= ah:
        h = short
        w = round(short * aw / ah)
    else:
        w = short
        h = round(short * ah / aw)
    return w - w % 2, h - h % 2


def probe(path):
    """(has_audio, width, height, duration)"""
    r = engine.run([engine.FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,width,height",
                    "-show_entries", "format=duration", "-of", "json", str(path)])
    try:
        j = json.loads(r.stdout)
    except ValueError:
        return False, 0, 0, 0.0
    streams = j.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    vid = next((s for s in streams if s.get("codec_type") == "video"), {})
    try:
        dur = float(j.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        dur = 0.0
    return has_audio, int(vid.get("width", 0) or 0), int(vid.get("height", 0) or 0), dur


def atempo(speed):
    """atempo only takes 0.5 to 2 per stage, so chain stages for the rest."""
    parts, s = [], float(speed)
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.5f}")
    return ",".join(parts)


def clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def fit_chain(label_in, label_out, mode, W, H, tag):
    """Filters that fit one clip onto the W x H canvas. Returns a list of graph pieces."""
    if mode == "fill":
        return [f"[{label_in}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[{label_out}]"]
    if mode == "blur":
        return [
            f"[{label_in}]split[s{tag}a][s{tag}b]",
            f"[s{tag}a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},gblur=sigma=8,scale={W}:{H}[bg{tag}]",
            f"[s{tag}b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg{tag}]",
            f"[bg{tag}][fg{tag}]overlay=(W-w)/2:(H-h)/2[{label_out}]",
        ]
    return [f"[{label_in}]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black[{label_out}]"]


def build(project, resolve, out_path, enc_args, height_cap=1080, workdir=None):
    """Return (cmd, total_seconds). `resolve(src)` maps a source id to a file path."""
    vids = project.get("video") or []
    if not vids:
        raise EditorError("Add at least one clip to the timeline first.")
    aspect = project.get("aspect", "16:9")
    mode = project.get("fit", "fit")
    W, H = output_size(aspect, height_cap)
    fps = 30
    workdir = Path(workdir or tempfile.mkdtemp(prefix="rewind-edit-"))

    inputs, graph = [], []
    durations = []
    for i, c in enumerate(vids):
        path = resolve(c["src"])
        has_audio, _, _, src_dur = probe(path)
        cin = clamp(c.get("in", 0), 0, 1e6, 0)
        cout = clamp(c.get("out", src_dur), cin + 0.05, 1e6, cin + 1)
        if src_dur:
            cout = min(cout, src_dur)
            cin = min(cin, max(0, cout - 0.05))
        speed = clamp(c.get("speed", 1), 0.25, 4, 1)
        D = (cout - cin) / speed
        durations.append(D)
        inputs += ["-ss", f"{cin:.3f}", "-t", f"{cout - cin:.3f}", "-i", str(path)]

        flt = c.get("filter") or {}
        b = clamp(flt.get("b", 0), -100, 100, 0)
        ct = clamp(flt.get("c", 0), -100, 100, 0)
        sa = clamp(flt.get("s", 0), -100, 100, 0)
        fi = clamp(c.get("fadeIn", 0), 0, D / 2, 0)
        fo = clamp(c.get("fadeOut", 0), 0, D / 2, 0)

        graph.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{speed:.5f},fps={fps},format=yuv420p[r{i}]")
        graph += fit_chain(f"r{i}", f"f{i}", mode, W, H, i)
        post = ["setsar=1"]
        if b or ct or sa:
            post.append(f"eq=brightness={b / 250:.4f}:contrast={1 + ct / 100:.4f}:saturation={1 + sa / 100:.4f}")
        if fi:
            post.append(f"fade=t=in:st=0:d={fi:.3f}")
        if fo:
            post.append(f"fade=t=out:st={D - fo:.3f}:d={fo:.3f}")
        post.append("format=yuv420p")
        graph.append(f"[f{i}]{','.join(post)}[v{i}]")

        vol = 0.0 if c.get("mute") else clamp(c.get("volume", 1), 0, 3, 1)
        if has_audio:
            ap = [atempo(speed)] if abs(speed - 1) > 1e-3 else []
            ap.append(f"volume={vol:.3f}")
            if fi:
                ap.append(f"afade=t=in:st=0:d={fi:.3f}")
            if fo:
                ap.append(f"afade=t=out:st={D - fo:.3f}:d={fo:.3f}")
            ap += ["aresample=48000", "aformat=channel_layouts=stereo", "asetpts=PTS-STARTPTS"]
            graph.append(f"[{i}:a]{','.join(ap)}[a{i}]")
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{D:.3f},asetpts=PTS-STARTPTS[a{i}]")

    n = len(vids)
    total = sum(durations)
    graph.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")

    # text overlays
    last = "vc"
    for k, t in enumerate(project.get("text") or []):
        text = str(t.get("text", "")).strip("\n")
        if not text:
            continue
        s = clamp(t.get("start", 0), 0, total, 0)
        e = min(total, s + clamp(t.get("dur", 2), 0.1, 3600, 2))
        size = clamp(t.get("size", 7), 1, 40, 7) / 100 * H
        reg, bold = FONTS.get(t.get("font", "segoe"), FONTS["segoe"])
        font = FONTS_DIR / (bold if t.get("bold", True) else reg)
        if not font.exists():
            font = FONTS_DIR / "arial.ttf"
        tf = workdir / f"text{k}.txt"
        tf.write_text(text, encoding="utf-8")
        color = str(t.get("color", "#ffffff")).lstrip("#")
        if len(color) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in color):
            color = "ffffff"
        x, y = clamp(t.get("x", 50), 0, 100, 50), clamp(t.get("y", 80), 0, 100, 80)

        def esc(p):  # filtergraph path escaping
            return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

        opts = [f"fontfile='{esc(font)}'", f"textfile='{esc(tf)}'", f"fontsize={size:.1f}", f"fontcolor=0x{color}",
                f"x=(w*{x:.2f}/100)-(text_w/2)", f"y=(h*{y:.2f}/100)-(text_h/2)",
                f"enable='between(t,{s:.3f},{e:.3f})'"]
        if t.get("outline", True):
            opts += [f"borderw={max(1, round(size / 14))}", "bordercolor=black@0.9"]
        if t.get("box"):
            opts += ["box=1", "boxcolor=black@0.55", f"boxborderw={round(size * 0.3)}"]
        nxt = f"vt{k}"
        graph.append(f"[{last}]drawtext={':'.join(opts)}[{nxt}]")
        last = nxt

    # music / extra audio
    mixes = []
    for k, a in enumerate(project.get("audio") or []):
        path = resolve(a["src"])
        _, _, _, adur = probe(path)
        ain = clamp(a.get("in", 0), 0, 1e6, 0)
        aout = clamp(a.get("out", adur), ain + 0.05, 1e6, ain + 1)
        if adur:
            aout = min(aout, adur)
            ain = min(ain, max(0, aout - 0.05))
        start = clamp(a.get("start", 0), 0, total, 0)
        length = min(aout - ain, max(0.05, total - start))
        mixes.append((path, ain, length, start, a))
    base_inputs = n
    for k, (path, ain, length, start, a) in enumerate(mixes):
        inputs += ["-ss", f"{ain:.3f}", "-t", f"{length:.3f}", "-i", str(path)]
        idx = base_inputs + k
        vol = clamp(a.get("volume", 1), 0, 3, 1)
        fi = clamp(a.get("fadeIn", 0), 0, length / 2, 0)
        fo = clamp(a.get("fadeOut", 0), 0, length / 2, 0)
        ap = [f"volume={vol:.3f}"]
        if fi:
            ap.append(f"afade=t=in:st=0:d={fi:.3f}")
        if fo:
            ap.append(f"afade=t=out:st={length - fo:.3f}:d={fo:.3f}")
        ms = int(start * 1000)
        ap += [f"adelay={ms}|{ms}", "aresample=48000", "aformat=channel_layouts=stereo"]
        graph.append(f"[{idx}:a]{','.join(ap)}[m{k}]")
    if mixes:
        labels = "[ac]" + "".join(f"[m{k}]" for k in range(len(mixes)))
        graph.append(f"{labels}amix=inputs={1 + len(mixes)}:duration=first:normalize=0:dropout_transition=0[aout]")
        alabel = "aout"
    else:
        alabel = "ac"

    graph_text = ";".join(graph)
    gfile = workdir / "graph.txt"
    gfile.write_text(";\n".join(graph), encoding="utf-8")
    # a very long edit would overflow Windows' command line, so hand ffmpeg the graph as a file instead
    fc = ["-/filter_complex", str(gfile)] if len(graph_text) > 20000 else ["-filter_complex", graph_text]
    cmd = [engine.FFMPEG, "-hide_banner", "-v", "error", "-y", "-progress", "pipe:1", "-nostats"] + inputs + fc + [
        "-map", f"[{last}]", "-map", f"[{alabel}]"] + enc_args + [
        "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
        "-movflags", "+faststart", "-f", "mp4", str(out_path)]
    return cmd, total, workdir


class Job:
    def __init__(self):
        self.id = uuid.uuid4().hex[:10]
        self.pct = 0.0
        self.done = False
        self.error = ""
        self.name = ""
        self.proc = None
        self.cancelled = False
        self.started = time.time()


def run_job(job, project, resolve, out_path, enc_for, height_cap, log=print):
    """Render in the current thread. enc_for(name) -> ffmpeg video args for 'gpu' then 'cpu' tries."""
    workdir = None
    part = Path(str(out_path) + ".part")
    try:
        tries = enc_for()
        last_err = ""
        for enc_args in tries:
            cmd, total, workdir = build(project, resolve, part, enc_args, height_cap)
            job.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        creationflags=engine.NO_WINDOW, stdin=subprocess.DEVNULL)
            errs = []

            def drain():
                for line in job.proc.stderr:
                    errs.append(line)
            threading.Thread(target=drain, daemon=True).start()
            for line in job.proc.stdout:
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        job.pct = min(99.0, int(line.split("=")[1]) / 1e6 / max(total, 0.1) * 100)
                    except ValueError:
                        pass
            job.proc.wait()
            if job.cancelled:
                raise EditorError("Cancelled.")
            if job.proc.returncode == 0 and part.exists() and part.stat().st_size > 1000:
                os.replace(part, out_path)
                job.pct, job.done, job.name = 100.0, True, str(out_path)
                return
            last_err = "".join(errs)[-600:]
            log(f"editor render failed: {last_err}")
            if part.exists():
                part.unlink()
            shutil.rmtree(workdir, ignore_errors=True)
        raise EditorError("Couldn't render the video. " + (last_err.strip().splitlines() or ["See rewind.log."])[-1])
    except EditorError as e:
        job.error = str(e)
    except Exception as e:  # noqa: BLE001
        log(f"editor error: {e}")
        job.error = f"Couldn't render the video: {e}"
    finally:
        job.done = True
        try:
            if part.exists() and not job.name:
                part.unlink()
        except OSError:
            pass
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)

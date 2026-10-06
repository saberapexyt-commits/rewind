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


TRANSITIONS = {"fade", "fadeblack", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright",
               "circleopen", "circleclose", "zoomin"}

# Looks ("filters"): colour treatments that run over a stretch of the timeline, with an intensity
FILTERS = {
    "bw": "hue=s=0",
    "noir": "hue=s=0,eq=contrast=1.45:brightness=-0.03",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "vivid": "eq=saturation=1.55:contrast=1.1",
    "pop": "eq=contrast=1.2:saturation=1.5",
    "cool": "colorchannelmixer=rr=0.92:bb=1.12",
    "warm": "colorchannelmixer=rr=1.12:bb=0.88",
    "fade": "eq=contrast=0.86:brightness=0.05:saturation=0.75",
    "cinematic": "colorbalance=rs=-.1:gs=-.02:bs=.14:bm=.06:rh=.08:bh=-.06,eq=contrast=1.1:saturation=1.1",
    "retro": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,eq=contrast=0.9:brightness=0.03,vignette=PI/5",
    "neon": "eq=saturation=1.9:contrast=1.15,hue=h=12",
    "dusk": "colorbalance=rs=.12:bs=.12:rm=.05:bm=.1,eq=brightness=-0.04:saturation=1.15",
}


def effect_chain(kind, s, W, H, i):
    """Filter chain for a timed effect. `s` is where it starts on the timeline, `i` is intensity 0..1."""
    if kind == "flash":
        return f"eq=brightness='{0.9 * i:.3f}*exp(-6*max(0,t-{s:.3f}))':eval=frame"
    if kind == "shake":
        k = 1 - 0.09 * i
        return (f"crop=w=iw*{k:.3f}:h=ih*{k:.3f}:x='(iw-ow)/2+iw*{0.035 * i:.3f}*sin(t*45)':y='(ih-oh)/2+ih*{0.035 * i:.3f}*cos(t*51)',"
                f"scale={W}:{H}")
    if kind == "glitch":
        return f"rgbashift=rh={-int(16 * i)}:bh={int(16 * i)}:gv={int(6 * i)},noise=alls={int(24 * i)}:allf=t"
    if kind == "blur":
        return f"gblur=sigma={max(0.5, 20 * i):.1f}"
    if kind == "zoom":
        z = 0.16 * i
        return (f"scale=w='{W}*(1+{z:.3f}*abs(sin((t-{s:.3f})*6)))':h='{H}*(1+{z:.3f}*abs(sin((t-{s:.3f})*6)))':eval=frame,"
                f"crop={W}:{H}")
    if kind == "vhs":
        return f"noise=alls={int(28 * i)}:allf=t+u,rgbashift=rh=-3:bh=3,eq=saturation=1.25:contrast=1.06"
    if kind == "bars":
        return "drawbox=x=0:y=0:w=iw:h=ih*0.11:color=black:t=fill,drawbox=x=0:y=ih*0.89:w=iw:h=ih*0.11:color=black:t=fill"
    if kind == "vignette":
        return "vignette=PI/4"
    if kind == "grain":
        return f"noise=alls={int(10 + 28 * i)}:allf=t"
    if kind == "mirror":
        return "hflip"
    if kind == "negative":
        return "negate"
    if kind == "pulse":
        return (f"eq=saturation='1+{0.9 * i:.2f}*abs(sin((t-{s:.3f})*6))':brightness='{0.07 * i:.3f}*abs(sin((t-{s:.3f})*6))':eval=frame")
    if kind == "pixel":
        n = max(6, int(8 + 26 * i))
        return f"scale=iw/{n}:ih/{n}:flags=neighbor,scale={W}:{H}:flags=neighbor"
    return None


EFFECT_KINDS = {"flash", "shake", "glitch", "blur", "zoom", "vhs", "bars", "vignette", "grain", "mirror", "negative", "pulse", "pixel"}


def lane_flag(project, key, flag):
    return bool(((project.get("lanes") or {}).get(key) or {}).get(flag))


def fg_chain(src_label, dst_label, mode, W, H, tag, tf, bg_dur):
    """Fit a clip onto the canvas, with an optional scale / move / rotate / opacity (CapCut-style transform)."""
    scale = clamp(tf.get("scale", 100), 10, 400, 100) / 100
    px = clamp(tf.get("x", 0), -150, 150, 0)
    py = clamp(tf.get("y", 0), -150, 150, 0)
    rot = clamp(tf.get("rot", 0), -360, 360, 0)
    opac = clamp(tf.get("opacity", 100), 0, 100, 100) / 100
    plain = abs(scale - 1) < 1e-3 and abs(px) < 0.05 and abs(py) < 0.05 and abs(rot) < 0.05 and opac > 0.999
    if plain:
        if mode == "fill":
            return [f"[{src_label}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[{dst_label}]"]
        if mode == "blur":
            return [
                f"[{src_label}]split[s{tag}a][s{tag}b]",
                f"[s{tag}a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},gblur=sigma=8,scale={W}:{H}[bg{tag}]",
                f"[s{tag}b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg{tag}]",
                f"[bg{tag}][fg{tag}]overlay=(W-w)/2:(H-h)/2[{dst_label}]",
            ]
        return [f"[{src_label}]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black[{dst_label}]"]
    out = []
    if mode == "blur":
        out += [f"[{src_label}]split[s{tag}a][s{tag}b]",
                f"[s{tag}a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},gblur=sigma=8,scale={W}:{H}[bg{tag}]"]
        fsrc = f"s{tag}b"
    else:
        out.append(f"color=c=black:s={W}x{H}:r=30:d={bg_dur:.3f}[bg{tag}]")
        fsrc = src_label
    fit = "increase" if mode == "fill" else "decrease"
    steps = [f"scale={W}:{H}:force_original_aspect_ratio={fit}"]
    if mode == "fill":
        steps.append(f"crop={W}:{H}")
    if abs(scale - 1) > 1e-3:
        steps.append(f"scale=trunc(iw*{scale:.4f}/2)*2:trunc(ih*{scale:.4f}/2)*2")
    steps.append("format=rgba")
    if abs(rot) > 0.05:
        a = rot * 3.14159265 / 180
        steps.append(f"rotate=a={a:.5f}:ow=rotw({a:.5f}):oh=roth({a:.5f}):c=none")
    if opac < 0.999:
        steps.append(f"colorchannelmixer=aa={opac:.3f}")
    out.append(f"[{fsrc}]{','.join(steps)}[fg{tag}]")
    out.append(f"[bg{tag}][fg{tag}]overlay=x=(W-w)/2+W*{px:.3f}/100:y=(H-h)/2+H*{py:.3f}/100:format=auto[{dst_label}]")
    return out


def build(project, resolve, out_path, enc_args, height_cap=1080, workdir=None):
    """Return (cmd, total_seconds, workdir). `resolve(src)` maps a source id to a file path."""
    vids = project.get("video") or []
    if not vids:
        raise EditorError("Add at least one clip to the timeline first.")
    aspect = project.get("aspect", "16:9")
    mode = project.get("fit", "fit")
    W, H = output_size(aspect, height_cap)
    fps = 30
    workdir = Path(workdir or tempfile.mkdtemp(prefix="rewind-edit-"))

    inputs, graph = [], []
    lens, ovs = [], []
    n = len(vids)
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
        lens.append(D)
        inputs += ["-ss", f"{cin:.3f}", "-t", f"{cout - cin:.3f}", "-i", str(path)]

        # the transition INTO this clip overlaps it with the one before
        tr = c.get("transition") or {}
        ov = 0.0
        if i > 0 and tr.get("type") in TRANSITIONS:
            ov = clamp(tr.get("dur", 0.6), 0.1, 3, 0.6)
            ov = min(ov, lens[i - 1] - ovs[i - 1] - 0.05, D * 0.9)
            ov = max(0.0, ov)
        ovs.append(ov)

        flt = c.get("filter") or {}
        b = clamp(flt.get("b", 0), -100, 100, 0)
        ct = clamp(flt.get("c", 0), -100, 100, 0)
        sa = clamp(flt.get("s", 0), -100, 100, 0)
        fi = clamp(c.get("fadeIn", 0), 0, D / 2, 0)
        fo = clamp(c.get("fadeOut", 0), 0, D / 2, 0)

        graph.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{speed:.5f},fps={fps},trim=end={D:.3f},setpts=PTS-STARTPTS,format=yuv420p[r{i}]")
        graph += fg_chain(f"r{i}", f"f{i}", mode, W, H, i, c.get("transform") or {}, D)
        post = ["setsar=1"]
        if b or ct or sa:
            post.append(f"eq=brightness={b / 250:.4f}:contrast={1 + ct / 100:.4f}:saturation={1 + sa / 100:.4f}")
        if fi:
            post.append(f"fade=t=in:st=0:d={fi:.3f}")
        if fo:
            post.append(f"fade=t=out:st={D - fo:.3f}:d={fo:.3f}")
        post += ["format=yuv420p", "settb=1/90000"]
        graph.append(f"[f{i}]{','.join(post)}[v{i}]")

        vol = 0.0 if (c.get("mute") or lane_flag(project, "main", "muted")) else clamp(c.get("volume", 1), 0, 3, 1)
        if has_audio:
            ap = [atempo(speed)] if abs(speed - 1) > 1e-3 else []
            ap.append(f"volume={vol:.3f}")
            if fi:
                ap.append(f"afade=t=in:st=0:d={fi:.3f}")
            if fo:
                ap.append(f"afade=t=out:st={D - fo:.3f}:d={fo:.3f}")
            ap += ["aresample=48000", "aformat=channel_layouts=stereo", f"apad=whole_dur={D:.3f}", f"atrim=end={D:.3f}", "asetpts=PTS-STARTPTS"]
            graph.append(f"[{i}:a]{','.join(ap)}[a{i}]")
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{D:.3f},asetpts=PTS-STARTPTS[a{i}]")

    # join the main track: cuts are concats, transitions are xfade + acrossfade
    cv, ca, acc = "v0", "a0", lens[0]
    for k in range(1, n):
        tr = (vids[k].get("transition") or {}).get("type")
        nv, na = f"jv{k}", f"ja{k}"
        if ovs[k] > 0:
            graph.append(f"[{cv}][v{k}]xfade=transition={tr}:duration={ovs[k]:.3f}:offset={acc - ovs[k]:.3f}[{nv}]")
            graph.append(f"[{ca}][a{k}]acrossfade=d={ovs[k]:.3f}:c1=tri:c2=tri[{na}]")
        else:
            graph.append(f"[{cv}][v{k}]concat=n=2:v=1:a=0[{nv}]")
            graph.append(f"[{ca}][a{k}]concat=n=2:v=0:a=1[{na}]")
        acc += lens[k] - ovs[k]
        cv, ca = nv, na
    total = acc
    if lane_flag(project, "main", "hidden"):
        graph.append(f"[{cv}]colorchannelmixer=0:0:0:0:0:0:0:0:0:0:0:0[vc]")
    else:
        graph.append(f"[{cv}]null[vc]")
    graph.append(f"[{ca}]anull[ac]")
    last = "vc"

    # extra inputs (overlays and music) come after the main clips
    next_in = n
    extra_audio = []                      # labels of delayed audio streams to mix in

    # overlay (picture-in-picture) clips, drawn in lane order
    overlays = [o for o in (project.get("overlay") or []) if not lane_flag(project, f"o{int(o.get('lane', 0))}", "hidden")]
    for k, o in enumerate(sorted(overlays, key=lambda x: (x.get("lane", 0), x.get("start", 0)))):
        path = resolve(o["src"])
        has_audio, ow, oh, odur = probe(path)
        oin = clamp(o.get("in", 0), 0, 1e6, 0)
        oout = clamp(o.get("out", odur), oin + 0.05, 1e6, oin + 1)
        if odur:
            oout = min(oout, odur)
            oin = min(oin, max(0, oout - 0.05))
        sp = clamp(o.get("speed", 1), 0.25, 4, 1)
        L = (oout - oin) / sp
        start = clamp(o.get("start", 0), 0, total, 0)
        L = min(L, max(0.1, total - start))
        inputs += ["-ss", f"{oin:.3f}", "-t", f"{L * sp:.3f}", "-i", str(path)]
        idx = next_in
        next_in += 1
        sc = clamp(o.get("scale", 35), 5, 100, 35)
        w = max(16, int(W * sc / 100) // 2 * 2)
        opac = clamp(o.get("opacity", 1), 0.05, 1, 1)
        rot = clamp(o.get("rot", 0), -360, 360, 0)
        fi = clamp(o.get("fadeIn", 0), 0, L / 2, 0)
        fo = clamp(o.get("fadeOut", 0), 0, L / 2, 0)
        flt = o.get("filter") or {}
        b = clamp(flt.get("b", 0), -100, 100, 0)
        ct = clamp(flt.get("c", 0), -100, 100, 0)
        sa = clamp(flt.get("s", 0), -100, 100, 0)
        ch = [f"setpts=(PTS-STARTPTS)/{sp:.5f}+{start:.3f}/TB", f"fps={fps}", f"scale={w}:-2", "format=yuva420p"]
        if b or ct or sa:
            ch.append(f"eq=brightness={b / 250:.4f}:contrast={1 + ct / 100:.4f}:saturation={1 + sa / 100:.4f}")
        if abs(rot) > 0.05:
            a = rot * 3.14159265 / 180
            ch += ["format=rgba", f"rotate=a={a:.5f}:ow=rotw({a:.5f}):oh=roth({a:.5f}):c=none", "format=yuva420p"]
        if opac < 0.999:
            ch.append(f"colorchannelmixer=aa={opac:.3f}")
        if fi:
            ch.append(f"fade=t=in:st={start:.3f}:d={fi:.3f}:alpha=1")
        if fo:
            ch.append(f"fade=t=out:st={start + L - fo:.3f}:d={fo:.3f}:alpha=1")
        graph.append(f"[{idx}:v]{','.join(ch)}[ov{k}]")
        x, y = clamp(o.get("x", 70), 0, 100, 70), clamp(o.get("y", 30), 0, 100, 30)
        nxt = f"vo{k}"
        graph.append(f"[{last}][ov{k}]overlay=x=(W*{x:.2f}/100)-(w/2):y=(H*{y:.2f}/100)-(h/2):"
                     f"enable='between(t,{start:.3f},{start + L:.3f})':eof_action=pass[{nxt}]")
        last = nxt
        if has_audio and not o.get("mute") and not lane_flag(project, f"o{int(o.get('lane', 0))}", "muted"):
            vol = clamp(o.get("volume", 1), 0, 3, 1)
            ap = [atempo(sp)] if abs(sp - 1) > 1e-3 else []
            ap += [f"volume={vol:.3f}", "aresample=48000", "aformat=channel_layouts=stereo",
                   f"adelay={int(start * 1000)}|{int(start * 1000)}"]
            graph.append(f"[{idx}:a]{','.join(ap)}[oa{k}]")
            extra_audio.append(f"oa{k}")

    # looks and effects: each one runs on a copy of the picture and is laid back over just its stretch of time
    timed = [("l", f) for f in (project.get("look") or [])] + [("e", e) for e in (project.get("effect") or [])]
    timed = [(kind, it) for kind, it in timed if not lane_flag(project, f"{kind}{int(it.get('lane', 0))}", "hidden")]
    timed.sort(key=lambda kv: (kv[0] != "l", kv[1].get("lane", 0), kv[1].get("start", 0)))
    for k, (kind, it) in enumerate(timed):
        s0 = clamp(it.get("start", 0), 0, total, 0)
        e0 = min(total, s0 + clamp(it.get("dur", 2), 0.1, 3600, 2))
        inten = clamp(it.get("intensity", 100), 0, 100, 100) / 100
        t = it.get("type")
        chain = FILTERS.get(t) if kind == "l" else (effect_chain(t, s0, W, H, inten) if t in EFFECT_KINDS else None)
        if not chain or e0 <= s0:
            continue
        a_, b_, c_, nxt = f"tm{k}a", f"tm{k}b", f"tm{k}f", f"tm{k}"
        graph.append(f"[{last}]split[{a_}][{b_}]")
        mix = ""
        if kind == "l" and inten < 0.995:
            mix = f",format=rgba,colorchannelmixer=aa={inten:.3f}"
        graph.append(f"[{b_}]{chain}{mix}[{c_}]")
        graph.append(f"[{a_}][{c_}]overlay=enable='between(t,{s0:.3f},{e0:.3f})':format=auto[{nxt}]")
        last = nxt

    # text overlays
    for k, t in enumerate(project.get("text") or []):
        if lane_flag(project, f"t{int(t.get('lane', 0))}", "hidden"):
            continue
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
    for k, a in enumerate(project.get("audio") or []):
        if lane_flag(project, f"a{int(a.get('lane', 0))}", "muted"):
            continue
        path = resolve(a["src"])
        _, _, _, adur = probe(path)
        ain = clamp(a.get("in", 0), 0, 1e6, 0)
        aout = clamp(a.get("out", adur), ain + 0.05, 1e6, ain + 1)
        if adur:
            aout = min(aout, adur)
            ain = min(ain, max(0, aout - 0.05))
        start = clamp(a.get("start", 0), 0, total, 0)
        length = min(aout - ain, max(0.05, total - start))
        inputs += ["-ss", f"{ain:.3f}", "-t", f"{length:.3f}", "-i", str(path)]
        idx = next_in
        next_in += 1
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
        extra_audio.append(f"m{k}")
    if extra_audio:
        labels = "[ac]" + "".join(f"[{x}]" for x in extra_audio)
        graph.append(f"{labels}amix=inputs={1 + len(extra_audio)}:duration=first:normalize=0:dropout_transition=0[aout]")
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

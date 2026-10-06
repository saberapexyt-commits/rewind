/* Rewind video editor: multi-track timeline, transitions, effects, text, free sounds, export. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const ASPECTS = { "16:9": [960, 540], "9:16": [540, 960], "1:1": [720, 720], "4:5": [640, 800] };
const FONTS = { segoe: "'Segoe UI', sans-serif", arial: "Arial, sans-serif", impact: "Impact, sans-serif", black: "'Arial Black', sans-serif",
  georgia: "Georgia, serif", consolas: "Consolas, monospace", comic: "'Comic Sans MS', cursive" };
const FONT_NAMES = { segoe: "Segoe UI", arial: "Arial", impact: "Impact", black: "Arial Black", georgia: "Georgia", consolas: "Consolas", comic: "Comic Sans" };
const TRANSITIONS = [["fade", "Fade"], ["dissolve", "Dissolve"], ["fadeblack", "Dip to black"], ["wipeleft", "Wipe left"], ["wiperight", "Wipe right"],
  ["wipeup", "Wipe up"], ["wipedown", "Wipe down"], ["slideleft", "Slide left"], ["slideright", "Slide right"], ["circleopen", "Circle open"],
  ["circleclose", "Circle close"], ["zoomin", "Zoom in"]];
const EFFECTS = [["bw", "Black & white", "grayscale(1)"], ["sepia", "Sepia", "sepia(1)"], ["vivid", "Vivid", "saturate(1.55) contrast(1.1)"],
  ["cool", "Cool", "hue-rotate(-12deg) saturate(1.1)"], ["warm", "Warm", "sepia(.35) saturate(1.3)"], ["fade", "Faded film", "contrast(.86) brightness(1.05) saturate(.75)"],
  ["blur", "Blur", "blur(3px)"], ["sharpen", "Sharpen", "contrast(1.12)"], ["negative", "Negative", "invert(1)"], ["vignette", "Vignette", ""],
  ["grain", "Film grain", ""], ["mirror", "Mirror", ""], ["flipv", "Flip upside down", ""]];
const SFX = [["whoosh", "Whoosh"], ["swish", "Swish"], ["riser", "Riser"], ["boom", "Boom"], ["impact", "Impact"], ["pop", "Pop"], ["ding", "Ding"],
  ["click", "Click"], ["success", "Success"], ["buzz", "Error buzz"], ["laser", "Laser"], ["glitch", "Glitch"]];
const ICON = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l12-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/></svg>',
  split: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M7 8L3 12l4 4M17 8l4 4-4 4"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>',
  undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3"/></svg>',
  redo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 14l5-5-5-5M20 9H10a6 6 0 0 0 0 12h3"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  pip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><rect x="12" y="11" width="7" height="6" rx="1" fill="currentColor"/></svg>',
};

const E = { P: null, sel: null, t: 0, total: 0, playing: false, zoom: 60, hist: [], hi: -1, meta: {}, name: "", tab: "media",
  cur: 0, curI: -1, outI: -1, token: 0, busy: false, exported: false, audio: {}, ov: {}, ctx: null, gains: new WeakMap(), drag: null, seekReq: null,
  built: false, snd: { q: "", kind: "music", page: 1, results: [], more: false, loading: false, error: "", playing: -1, searched: false }, sfxIds: {}, prev: null };
const V = [document.createElement("video"), document.createElement("video")];
V.forEach((v) => { v.playsInline = true; v.preload = "auto"; });

const uid = () => Math.random().toString(36).slice(2, 9);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (t) => { t = Math.max(0, t); const m = Math.floor(t / 60); return `${m}:${(t % 60).toFixed(1).padStart(4, "0")}`; };
const srcUrl = (s) => s.startsWith("ext:") ? "/ext/" + s.slice(4) : "/media/" + encodeURIComponent(s);
const cleanTitle = (c) => c.title.replace(/ \d{4}-\d\d-\d\d \d\d-\d\d-\d\d.*$/, "") || c.title;
const niceName = (s) => s.startsWith("ext:") ? (E.meta[s] && E.meta[s].label) || "Audio file" : s.split("/").pop().replace(/\.mp4$/i, "").replace(/ \d{4}-\d\d-\d\d \d\d-\d\d-\d\d.*$/, "");

/* ------------------------------------------------------------ model */
function layout() {
  const v = E.P.video; let acc = 0;
  v.forEach((c, i) => {
    c.len = (c.out - c.in) / c.speed;
    let ov = 0;
    if (i > 0 && c.transition && c.transition.type && c.transition.type !== "none") {
      ov = Math.min(c.transition.dur || 0.6, v[i - 1].len - v[i - 1].ov - 0.05, c.len * 0.9);
      ov = Math.max(0, ov);
    }
    c.ov = ov;
    c.start = i === 0 ? 0 : acc - ov;
    acc = c.start + c.len;
  });
  E.total = v.length ? acc : 0;
  for (const o of E.P.overlay) o.len = (o.out - o.in) / o.speed;
}
const newFilter = () => ({ b: 0, c: 0, s: 0 });
function newClip(src, inn, out) {
  return { id: uid(), src, in: inn, out, speed: 1, volume: 1, mute: false, filter: newFilter(), fx: [], fadeIn: 0, fadeOut: 0, transition: { type: "none", dur: 0.6 } };
}
function newOverlay(src, inn, out, start) {
  return { id: uid(), src, in: inn, out, start, speed: 1, volume: 1, mute: false, x: 72, y: 28, scale: 36, opacity: 1, filter: newFilter(), fx: [], fadeIn: 0, fadeOut: 0 };
}
function locate(t) {
  const v = E.P.video; let i = 0;
  for (let k = 0; k < v.length; k++) if (v[k].start <= t + 1e-6) i = k;
  let j = -1, p = 1;
  const c = v[i];
  if (c && i > 0 && c.ov > 0 && t < c.start + c.ov) { j = i - 1; p = clamp((t - c.start) / c.ov, 0, 1); }
  return { i, j, p };
}
const listOf = (k) => k === "v" ? E.P.video : k === "o" ? E.P.overlay : k === "t" ? E.P.text : E.P.audio;
function find(kind, id) { return listOf(kind).find((x) => x.id === id); }
function selItem() { return E.sel ? find(E.sel.kind, E.sel.id) : null; }
function commit() {
  layout();
  E.hist = E.hist.slice(0, E.hi + 1);
  E.hist.push(JSON.stringify(E.P));
  if (E.hist.length > 80) E.hist.shift();
  E.hi = E.hist.length - 1;
  E.exported = false;
  refreshAll();
}
function restore(i) {
  E.hi = i; E.P = JSON.parse(E.hist[i]); layout();
  if (E.sel && !selItem()) E.sel = null;
  E.t = clamp(E.t, 0, E.total);
  refreshAll(); seek(E.t);
}
const undo = () => { if (E.hi > 0) restore(E.hi - 1); };
const redo = () => { if (E.hi < E.hist.length - 1) restore(E.hi + 1); };

/* ------------------------------------------------------------ media metadata */
function loadMeta(src) {
  if (E.meta[src] && E.meta[src].dur) return Promise.resolve(E.meta[src]);
  return new Promise((res, rej) => {
    const el = document.createElement("video");
    el.preload = "metadata"; el.muted = true;
    el.onloadedmetadata = () => { E.meta[src] = { ...(E.meta[src] || {}), dur: el.duration, w: el.videoWidth, h: el.videoHeight }; el.removeAttribute("src"); el.load(); res(E.meta[src]); };
    el.onerror = () => rej(new Error("Couldn't open that file."));
    el.src = srcUrl(src);
  });
}

/* ------------------------------------------------------------ audio graph */
function audioCtx() {
  if (!E.ctx) { try { E.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { E.ctx = null; } }
  if (E.ctx && E.ctx.state === "suspended") E.ctx.resume();
  return E.ctx;
}
function gainFor(el) {
  if (E.gains.has(el)) return E.gains.get(el);
  const ac = audioCtx(); let g = null;
  if (ac) { try { const s = ac.createMediaElementSource(el); g = ac.createGain(); s.connect(g); g.connect(ac.destination); } catch (e) { g = null; } }
  E.gains.set(el, g);
  return g;
}
function setVol(el, v) {
  const g = gainFor(el);
  if (g) { g.gain.value = Math.max(0, v); el.volume = 1; } else el.volume = clamp(v, 0, 1);
}

/* ------------------------------------------------------------ main-track playback */
function ensureSrc(v, src) {
  const u = srcUrl(src);
  if (v.dataset.src === u) return v.readyState >= 1 ? Promise.resolve() : new Promise((r) => v.addEventListener("loadedmetadata", r, { once: true }));
  v.dataset.src = u; v.src = u;
  return new Promise((r) => v.addEventListener("loadedmetadata", r, { once: true }));
}
const localTime = (c, t) => c.in + clamp(t - c.start, 0, c.len) * c.speed;
const waitSeek = (v) => new Promise((r) => { if (!v.seeking && v.readyState >= 2) r(); else v.addEventListener("seeked", r, { once: true }); setTimeout(r, 1500); });
async function startAt(t, autoplay) {
  if (!E.P.video.length) { E.curI = -1; E.outI = -1; return; }
  const my = ++E.token; E.busy = true;
  const L = locate(t), c = E.P.video[L.i], v = V[E.cur], o = V[1 - E.cur];
  v.pause(); o.pause();
  await ensureSrc(v, c.src);
  if (my !== E.token) return;
  v.playbackRate = c.speed; v.currentTime = localTime(c, t);
  let oc = null;
  if (L.j >= 0) {
    oc = E.P.video[L.j];
    await ensureSrc(o, oc.src);
    if (my !== E.token) return;
    o.playbackRate = oc.speed; o.currentTime = localTime(oc, t);
  }
  await Promise.all([waitSeek(v), oc ? waitSeek(o) : Promise.resolve()]);
  if (my !== E.token) return;
  E.curI = L.i; E.outI = L.j; E.busy = false;
  applyVolume();
  if (autoplay && E.playing) { v.play().catch(() => {}); if (oc) o.play().catch(() => {}); }
  preloadNext(L.i);
}
const continuous = (a, b) => b && b.ov === 0 && a.src === b.src && Math.abs(b.in - a.out) < 0.06 && a.speed === b.speed;
function preloadNext(i) {
  const c = E.P.video[i], n = E.P.video[i + 1];
  if (!n || continuous(c, n) || E.outI >= 0) return;
  const o = V[1 - E.cur];
  ensureSrc(o, n.src).then(() => { if (E.curI === i && E.outI < 0) { o.pause(); o.currentTime = n.in; } });
}
function applyVolume() {
  const L = locate(E.t), c = E.P.video[L.i]; if (!c) return;
  const gainOf = (cl, extra) => {
    let g = cl.mute ? 0 : cl.volume; const local = E.t - cl.start;
    if (cl.fadeIn > 0 && local < cl.fadeIn) g *= clamp(local / cl.fadeIn, 0, 1);
    if (cl.fadeOut > 0 && cl.len - local < cl.fadeOut) g *= clamp((cl.len - local) / cl.fadeOut, 0, 1);
    return g * extra;
  };
  setVol(V[E.cur], gainOf(c, L.j >= 0 ? L.p : 1));
  if (L.j >= 0 && E.outI === L.j) setVol(V[1 - E.cur], gainOf(E.P.video[L.j], 1 - L.p)); else setVol(V[1 - E.cur], 0);
}
function play() {
  if (E.playing || !E.P.video.length) return;
  audioCtx();
  if (E.t >= E.total - 0.03) E.t = 0;
  E.playing = true; syncTransport();
  startAt(E.t, true);
}
function pause() {
  E.playing = false; E.token++; E.busy = false;
  V.forEach((v) => v.pause());
  Object.values(E.audio).forEach((a) => a.el.pause());
  Object.values(E.ov).forEach((o) => o.pause());
  syncTransport();
}
const toggle = () => E.playing ? pause() : play();
function seek(t) { E.t = clamp(t, 0, E.total); startAt(E.t, E.playing); updatePlayhead(); syncTransport(); }
function beginNext() {
  const i = E.curI, c = E.P.video[i], n = E.P.video[i + 1];
  if (!n) { E.t = E.total; pause(); return; }
  const v = V[E.cur], o = V[1 - E.cur];
  if (continuous(c, n)) { E.curI = i + 1; v.playbackRate = n.speed; preloadNext(i + 1); return; }
  if (o.dataset.src === srcUrl(n.src) && o.readyState >= 2 && Math.abs(o.currentTime - n.in) < 0.3) {
    E.cur = 1 - E.cur; E.curI = i + 1;
    o.playbackRate = n.speed; o.play().catch(() => {});
    if (n.ov > 0) { E.outI = i; }        // the old element keeps playing underneath the transition
    else { v.pause(); E.outI = -1; preloadNext(i + 1); }
    return;
  }
  startAt(n.start, true);
}

/* ------------------------------------------------------------ overlay + music tracks */
function ovEl(o) {
  if (!E.ov[o.id]) { const el = document.createElement("video"); el.playsInline = true; el.preload = "auto"; el.dataset.src = srcUrl(o.src); el.src = srcUrl(o.src); E.ov[o.id] = el; }
  return E.ov[o.id];
}
function syncOverlays() {
  const live = new Set();
  for (const o of E.P.overlay) {
    live.add(o.id);
    const el = ovEl(o), t = E.t, inside = t >= o.start && t < o.start + o.len;
    if (!inside) { if (!el.paused) el.pause(); continue; }
    const want = o.in + (t - o.start) * o.speed;
    let g = o.mute ? 0 : o.volume; const local = t - o.start;
    if (o.fadeIn > 0 && local < o.fadeIn) g *= local / o.fadeIn;
    if (o.fadeOut > 0 && o.len - local < o.fadeOut) g *= (o.len - local) / o.fadeOut;
    setVol(el, g);
    el.playbackRate = o.speed;
    if (E.playing) {
      if (el.paused) { el.currentTime = want; el.play().catch(() => {}); }
      else if (Math.abs(el.currentTime - want) > 0.3) el.currentTime = want;
    } else {
      if (!el.paused) el.pause();
      if (!el.seeking && Math.abs(el.currentTime - want) > 0.04) el.currentTime = want;
    }
  }
  for (const id of Object.keys(E.ov)) if (!live.has(id)) { E.ov[id].pause(); E.ov[id].removeAttribute("src"); delete E.ov[id]; }
}
function audioEl(a) {
  if (!E.audio[a.id]) { const el = new Audio(); el.preload = "auto"; el.src = srcUrl(a.src); E.audio[a.id] = { el }; }
  return E.audio[a.id].el;
}
function syncAudio() {
  const live = new Set();
  for (const a of E.P.audio) {
    live.add(a.id);
    const el = audioEl(a), len = a.out - a.in, t = E.t;
    const inside = E.playing && t >= a.start && t < a.start + len;
    if (inside) {
      const want = a.in + (t - a.start);
      let g = a.volume; const local = t - a.start;
      if (a.fadeIn > 0 && local < a.fadeIn) g *= local / a.fadeIn;
      if (a.fadeOut > 0 && len - local < a.fadeOut) g *= (len - local) / a.fadeOut;
      setVol(el, g);
      if (el.paused) { el.currentTime = want; el.play().catch(() => {}); }
      else if (Math.abs(el.currentTime - want) > 0.3) el.currentTime = want;
    } else if (!el.paused) el.pause();
  }
  for (const id of Object.keys(E.audio)) if (!live.has(id)) { E.audio[id].el.pause(); delete E.audio[id]; }
}

/* ------------------------------------------------------------ drawing */
const cv = document.createElement("canvas"); cv.id = "ed-cv";
const cx = cv.getContext("2d");
const bgc = document.createElement("canvas"); const bgx = bgc.getContext("2d");
const grain = document.createElement("canvas"); grain.width = grain.height = 160;
(() => { const g = grain.getContext("2d"), d = g.createImageData(160, 160); for (let i = 0; i < d.data.length; i += 4) { const v = Math.random() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; } g.putImageData(d, 0, 0); })();
function sizeCanvas() {
  const [w, h] = ASPECTS[E.P.aspect] || ASPECTS["16:9"];
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  bgc.width = Math.round(w / 12); bgc.height = Math.round(h / 12);
}
function cssFilter(item, W) {
  const f = item.filter || newFilter();
  let s = `brightness(${1 + f.b / 125}) contrast(${1 + f.c / 100}) saturate(${1 + f.s / 100})`;
  for (const id of item.fx || []) {
    const e = EFFECTS.find((x) => x[0] === id);
    if (!e) continue;
    s += " " + (id === "blur" ? `blur(${Math.max(1, W / 160)}px)` : e[2]);
  }
  return s;
}
const hasFx = (item, id) => (item.fx || []).includes(id);
function fadeAlpha(item, local, len) {
  let a = 1;
  if (item.fadeIn > 0 && local < item.fadeIn) a = clamp(local / item.fadeIn, 0, 1);
  if (item.fadeOut > 0 && len - local < item.fadeOut) a = Math.min(a, clamp((len - local) / item.fadeOut, 0, 1));
  return a;
}
function finishFx(item, x, y, w, h) {
  if (hasFx(item, "vignette")) {
    const gr = cx.createRadialGradient(x + w / 2, y + h / 2, Math.min(w, h) * 0.3, x + w / 2, y + h / 2, Math.max(w, h) * 0.75);
    gr.addColorStop(0, "rgba(0,0,0,0)"); gr.addColorStop(1, "rgba(0,0,0,.6)");
    cx.fillStyle = gr; cx.fillRect(x, y, w, h);
  }
  if (hasFx(item, "grain")) {
    cx.save(); cx.globalAlpha *= 0.14; cx.globalCompositeOperation = "overlay";
    cx.beginPath(); cx.rect(x, y, w, h); cx.clip();
    const ox = -Math.random() * 120, oy = -Math.random() * 120;
    for (let gx = x + ox; gx < x + w; gx += 160) for (let gy = y + oy; gy < y + h; gy += 160) cx.drawImage(grain, gx, gy);
    cx.restore();
  }
}
/* one main-track clip, optionally clipped / moved for a transition */
function drawMain(c, el, o) {
  const W = cv.width, H = cv.height, vw = el.videoWidth, vh = el.videoHeight;
  if (!vw || el.readyState < 2) return;
  o = o || {};
  const local = E.t - c.start;
  cx.save();
  if (o.clip) {
    cx.beginPath();
    if (o.clip.circle) cx.arc(W / 2, H / 2, o.clip.r, 0, Math.PI * 2); else cx.rect(o.clip.x, o.clip.y, o.clip.w, o.clip.h);
    cx.clip();
  }
  cx.globalAlpha = (o.a == null ? 1 : o.a) * fadeAlpha(c, local, c.len);
  if (o.dx || o.dy) cx.translate(o.dx || 0, o.dy || 0);
  if (o.sc && o.sc !== 1) { cx.translate(W / 2, H / 2); cx.scale(o.sc, o.sc); cx.translate(-W / 2, -H / 2); }
  const flt = cssFilter(c, W);
  if (hasFx(c, "mirror")) { cx.translate(W, 0); cx.scale(-1, 1); }
  if (hasFx(c, "flipv")) { cx.translate(0, H); cx.scale(1, -1); }
  if (E.P.fit === "blur") {
    const s = Math.max(bgc.width / vw, bgc.height / vh);
    bgx.filter = "blur(2px)";
    bgx.drawImage(el, (bgc.width - vw * s) / 2, (bgc.height - vh * s) / 2, vw * s, vh * s);
    cx.imageSmoothingQuality = "high"; cx.filter = flt;
    cx.drawImage(bgc, 0, 0, W, H);
  }
  cx.filter = flt;
  const s = E.P.fit === "fill" ? Math.max(W / vw, H / vh) : Math.min(W / vw, H / vh);
  cx.drawImage(el, (W - vw * s) / 2, (H - vh * s) / 2, vw * s, vh * s);
  cx.filter = "none";
  finishFx(c, 0, 0, W, H);
  cx.restore();
}
function drawTransition(out, outEl, inn, inEl, p, type) {
  const W = cv.width, H = cv.height;
  switch (type) {
    case "fadeblack":
      if (p < 0.5) drawMain(out, outEl, { a: 1 - p * 2 }); else drawMain(inn, inEl, { a: (p - 0.5) * 2 });
      break;
    case "wipeleft": drawMain(out, outEl); drawMain(inn, inEl, { clip: { x: W * (1 - p), y: 0, w: W * p, h: H } }); break;
    case "wiperight": drawMain(out, outEl); drawMain(inn, inEl, { clip: { x: 0, y: 0, w: W * p, h: H } }); break;
    case "wipeup": drawMain(out, outEl); drawMain(inn, inEl, { clip: { x: 0, y: H * (1 - p), w: W, h: H * p } }); break;
    case "wipedown": drawMain(out, outEl); drawMain(inn, inEl, { clip: { x: 0, y: 0, w: W, h: H * p } }); break;
    case "slideleft": drawMain(out, outEl, { dx: -W * p }); drawMain(inn, inEl, { dx: W * (1 - p) }); break;
    case "slideright": drawMain(out, outEl, { dx: W * p }); drawMain(inn, inEl, { dx: -W * (1 - p) }); break;
    case "circleopen": drawMain(out, outEl); drawMain(inn, inEl, { clip: { circle: true, r: p * Math.hypot(W, H) / 2 } }); break;
    case "circleclose": drawMain(inn, inEl); drawMain(out, outEl, { clip: { circle: true, r: (1 - p) * Math.hypot(W, H) / 2 } }); break;
    case "zoomin": drawMain(inn, inEl); drawMain(out, outEl, { sc: 1 + p * 0.7, a: 1 - p }); break;
    default: drawMain(out, outEl); drawMain(inn, inEl, { a: p });      // fade, dissolve
  }
}
function drawOverlays() {
  const W = cv.width, H = cv.height;
  const items = [...E.P.overlay].sort((a, b) => (a._lane || 0) - (b._lane || 0));
  for (const o of items) {
    o._bb = null;
    if (E.t < o.start || E.t >= o.start + o.len) continue;
    const el = E.ov[o.id]; if (!el || !el.videoWidth || el.readyState < 2) continue;
    const w = W * o.scale / 100, h = w * el.videoHeight / el.videoWidth, x = W * o.x / 100 - w / 2, y = H * o.y / 100 - h / 2;
    cx.save();
    cx.globalAlpha = o.opacity * fadeAlpha(o, E.t - o.start, o.len);
    cx.filter = cssFilter(o, W);
    if (hasFx(o, "mirror")) { cx.translate(x * 2 + w, 0); cx.scale(-1, 1); }
    cx.drawImage(el, x, y, w, h);
    cx.filter = "none";
    finishFx(o, x, y, w, h);
    cx.restore();
    o._bb = { x, y, w, h };
    if (E.sel && E.sel.kind === "o" && E.sel.id === o.id && !E.playing) {
      cx.save(); cx.setLineDash([6, 4]); cx.lineWidth = 2; cx.strokeStyle = "#3d8bff"; cx.strokeRect(x, y, w, h); cx.restore();
    }
  }
}
function drawText(t, selected) {
  const W = cv.width, H = cv.height, px = t.size / 100 * H;
  cx.save();
  cx.font = `${t.bold ? "700" : "400"} ${px}px ${FONTS[t.font] || FONTS.segoe}`;
  cx.textAlign = "center"; cx.textBaseline = "middle"; cx.lineJoin = "round";
  const lines = String(t.text).split("\n"), lh = px * 1.2;
  const y0 = H * t.y / 100 - (lines.length - 1) * lh / 2, x = W * t.x / 100;
  const tw = Math.max(...lines.map((l) => cx.measureText(l).width), 1);
  if (t.box) { cx.fillStyle = "rgba(0,0,0,.55)"; const pad = px * 0.3; cx.fillRect(x - tw / 2 - pad, y0 - lh / 2 - pad / 2, tw + pad * 2, lines.length * lh + pad); }
  lines.forEach((l, i) => {
    const y = y0 + i * lh;
    if (t.outline) { cx.lineWidth = Math.max(2, px / 7); cx.strokeStyle = "rgba(0,0,0,.9)"; cx.strokeText(l, x, y); }
    cx.fillStyle = t.color; cx.fillText(l, x, y);
  });
  t._bb = { x: x - tw / 2, y: y0 - lh / 2, w: tw, h: lines.length * lh };
  if (selected) { cx.setLineDash([6, 4]); cx.lineWidth = 2; cx.strokeStyle = "#3d8bff"; cx.strokeRect(t._bb.x - 6, t._bb.y - 4, t._bb.w + 12, t._bb.h + 8); }
  cx.restore();
}
function draw() {
  if (!E.P || (E.busy && !E.playing)) return;
  sizeCanvas();
  cx.fillStyle = "#000"; cx.fillRect(0, 0, cv.width, cv.height);
  if (E.P.video.length) {
    const L = locate(E.t), c = E.P.video[L.i];
    if (L.j >= 0 && E.outI === L.j) drawTransition(E.P.video[L.j], V[1 - E.cur], c, V[E.cur], L.p, c.transition.type);
    else drawMain(c, V[E.cur]);
  }
  drawOverlays();
  for (const t of E.P.text) {
    const on = E.t >= t.start && E.t < t.start + t.dur;
    if (on) drawText(t, E.sel && E.sel.kind === "t" && E.sel.id === t.id && !E.playing); else t._bb = null;
  }
}
function tick() {
  if (!$("ed").classList.contains("on")) return;
  if (E.playing && E.curI >= 0 && !E.busy) {
    const c = E.P.video[E.curI], v = V[E.cur];
    if (c && v.readyState >= 2 && !v.seeking && !v.paused) {
      if (v.playbackRate !== c.speed) v.playbackRate = c.speed;
      E.t = c.start + (v.currentTime - c.in) / c.speed;
      if (E.outI >= 0) {
        const oc = E.P.video[E.outI];
        if (oc && E.t >= oc.start + oc.len - 1e-3) { V[1 - E.cur].pause(); E.outI = -1; preloadNext(E.curI); }
      }
      const n = E.P.video[E.curI + 1];
      if (n) { if (n.ov > 0 ? E.t >= n.start : (v.currentTime >= c.out - 0.03 || v.ended)) beginNext(); }
      else if (v.currentTime >= c.out - 0.03 || v.ended) { E.t = E.total; pause(); }
      applyVolume();
    }
  }
  if (E.seekReq != null) { const t = E.seekReq; E.seekReq = null; seek(t); }
  syncOverlays(); syncAudio(); draw(); updatePlayhead();
  requestAnimationFrame(tick);
}

/* ------------------------------------------------------------ editing operations */
function splitAt(t) {
  const it = selItem(), k = E.sel && E.sel.kind;
  if (it && (k === "t" || k === "o" || k === "a")) {
    const len = k === "t" ? it.dur : k === "o" ? it.len : it.out - it.in;
    if (t > it.start + 0.2 && t < it.start + len - 0.2) {
      const b = JSON.parse(JSON.stringify(it)); b.id = uid(); b.start = t;
      if (k === "t") { b.dur = it.start + it.dur - t; it.dur = t - it.start; }
      else if (k === "o") { const sp = it.in + (t - it.start) * it.speed; b.in = sp; it.out = sp; b.fadeIn = 0; it.fadeOut = 0; }
      else { const sp = it.in + (t - it.start); b.in = sp; it.out = sp; b.fadeIn = 0; it.fadeOut = 0; }
      listOf(k).push(b); E.sel = { kind: k, id: b.id }; return commit();
    }
  }
  const i = locate(t).i, c = E.P.video[i]; if (!c) return;
  const sp = c.in + (t - c.start) * c.speed;
  if (sp < c.in + 0.1 || sp > c.out - 0.1) return;
  const b = JSON.parse(JSON.stringify(c)); b.id = uid(); b.in = sp; b.fadeIn = 0; b.transition = { type: "none", dur: 0.6 };
  c.out = sp; c.fadeOut = 0;
  E.P.video.splice(i + 1, 0, b);
  E.sel = { kind: "v", id: b.id };
  commit();
}
function removeSel() {
  if (!E.sel) return;
  const list = listOf(E.sel.kind), i = list.findIndex((x) => x.id === E.sel.id);
  if (i < 0) return;
  list.splice(i, 1); E.sel = null; commit();
  E.t = clamp(E.t, 0, E.total); seek(E.t);
}
function duplicateSel() {
  const it = selItem(); if (!it) return;
  const b = JSON.parse(JSON.stringify(it)); b.id = uid(); const k = E.sel.kind;
  if (k === "v") { E.P.video.splice(E.P.video.indexOf(it) + 1, 0, b); b.transition = { type: "none", dur: 0.6 }; }
  else { b.start = it.start + (k === "t" ? it.dur : k === "o" ? it.len : it.out - it.in); listOf(k).push(b); }
  E.sel = { kind: k, id: b.id }; commit();
}
async function addClip(name) {
  try {
    const m = await loadMeta(name);
    const c = newClip(name, 0, m.dur); E.P.video.push(c); E.sel = { kind: "v", id: c.id };
    commit(); E.t = c.start; seek(E.t); scrollToPlayhead();
  } catch (e) { toast({ kind: "error", message: e.message }); }
}
async function addOverlay(name) {
  if (!E.P.video.length) { toast({ kind: "error", message: "Add a main clip first, then layer this on top." }); return; }
  try {
    const m = await loadMeta(name);
    const o = newOverlay(name, 0, Math.min(m.dur, Math.max(1, E.total - E.t)), E.t);
    E.P.overlay.push(o); E.sel = { kind: "o", id: o.id }; commit();
  } catch (e) { toast({ kind: "error", message: e.message }); }
}
function addText(preset) {
  const base = { id: uid(), text: "Your text", start: E.t, dur: Math.min(3, Math.max(1, E.total - E.t || 3)), x: 50, y: 80, size: 7, color: "#ffffff", font: "segoe", bold: true, outline: true, box: false };
  const t = Object.assign(base, preset || {});
  E.P.text.push(t); E.sel = { kind: "t", id: t.id }; commit(); setTab("text");
}
async function addAudio(src, label) {
  if (label) E.meta[src] = { ...(E.meta[src] || {}), label };
  const m = await loadMeta(src);
  const room = E.total > 0 ? Math.max(1, E.total - E.t) : m.dur;
  const a = { id: uid(), src, in: 0, out: Math.min(m.dur, room), start: E.t, volume: 0.8, fadeIn: 0, fadeOut: 0 };
  E.P.audio.push(a); E.sel = { kind: "a", id: a.id }; commit();
}
async function addAudioFile() {
  const r = await api("/api/editor/pick-audio");
  if (!r.ok) return;
  try { await addAudio(r.id, r.name); } catch (e) { toast({ kind: "error", message: e.message }); }
}
function toggleEffect(id) {
  let it = selItem();
  if (!it || !(E.sel.kind === "v" || E.sel.kind === "o")) {
    const c = E.P.video[locate(E.t).i];
    if (!c) { toast({ kind: "error", message: "Add a clip first." }); return; }
    E.sel = { kind: "v", id: c.id }; it = c;
  }
  it.fx = it.fx || [];
  const i = it.fx.indexOf(id);
  if (i >= 0) it.fx.splice(i, 1); else it.fx.push(id);
  commit();
}
function applyTransition(type) {
  let i = E.sel && E.sel.kind === "v" ? E.P.video.findIndex((c) => c.id === E.sel.id) : locate(E.t).i;
  if (i < 0) return;
  if (i === 0) i = 1;                                   // a transition joins a clip to the one before it
  const c = E.P.video[i];
  if (!c) { toast({ kind: "error", message: "A transition needs two clips on the main track. Add another clip first." }); return; }
  c.transition = { type, dur: (c.transition && c.transition.dur) || 0.6 };
  E.sel = { kind: "v", id: c.id };
  commit();
  seek(Math.max(0, c.start - 0.4));
}

/* ------------------------------------------------------------ UI: skeleton */
function build() {
  if (E.built) return;
  E.built = true;
  const root = document.createElement("div"); root.id = "ed";
  root.innerHTML = `
    <div class="ed-top pywebview-drag-region">
      <button class="ed-btn" id="ed-back">${ICON.back}Back</button>
      <input class="title" id="ed-title" spellcheck="false" aria-label="Project name">
      <span class="grow"></span>
      <button class="ed-btn ico" id="ed-undo" title="Undo (Ctrl+Z)">${ICON.undo}</button>
      <button class="ed-btn ico" id="ed-redo" title="Redo (Ctrl+Y)">${ICON.redo}</button>
      <button class="ed-btn primary" id="ed-export">Export</button>
      <div class="ed-win" id="ed-win" hidden>
        <button data-w="minimize" aria-label="Minimize"><svg viewBox="0 0 16 16" stroke="currentColor"><path d="M3 8.5h10"/></svg></button>
        <button data-w="maximize" aria-label="Maximize"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><rect x="3.5" y="3.5" width="9" height="9" rx="1"/></svg></button>
        <button data-w="close" class="close" aria-label="Close"><svg viewBox="0 0 16 16" stroke="currentColor" stroke-width="1.2"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></svg></button>
      </div>
    </div>
    <div class="ed-left">
      <div class="ed-tabs"><button data-tab="media">Media</button><button data-tab="audio">Audio</button><button data-tab="text">Text</button><button data-tab="effects">Effects</button><button data-tab="trans">Transitions</button></div>
      <div class="ed-pane" id="ed-pane"></div>
    </div>
    <div class="ed-mid">
      <div class="ed-stage" id="ed-stage"></div>
      <div class="ed-trans">
        <button class="ed-btn ico" id="ed-play" aria-label="Play or pause"></button>
        <span class="ed-time" id="ed-time"></span>
        <span class="grow"></span>
        <span class="ed-small" id="ed-fmt"></span>
      </div>
    </div>
    <div class="ed-right" id="ed-insp"></div>
    <div class="ed-tl">
      <div class="ed-tlbar">
        <button class="ed-btn" id="ed-split" title="Split at the playhead (S)">${ICON.split}Split</button>
        <button class="ed-btn" id="ed-dup" title="Duplicate (Ctrl+D)">${ICON.copy}Duplicate</button>
        <button class="ed-btn danger" id="ed-del" title="Delete (Del)">${ICON.trash}Delete</button>
        <span class="sep"></span>
        <span class="ed-small">Zoom</span><input type="range" id="ed-zoom" min="8" max="400" step="1"><button class="ed-btn" id="ed-fit" title="Fit the whole timeline">Fit</button>
        <span class="grow"></span>
        <span class="ed-small">Space plays &middot; S splits &middot; Del removes &middot; Ctrl+Z undoes</span>
      </div>
      <div class="ed-scroll" id="ed-scroll"><div class="ed-inner" id="ed-inner"></div></div>
    </div>
    <div class="ed-vids" id="ed-vids"></div>
    <div class="ed-modal" id="ed-modal"><div class="ed-card" id="ed-card"></div></div>`;
  document.body.appendChild(root);
  $("ed-stage").appendChild(cv);
  $("ed-vids").append(V[0], V[1]);
  $("ed-back").onclick = () => close();
  $("ed-undo").onclick = undo; $("ed-redo").onclick = redo;
  $("ed-play").onclick = toggle;
  $("ed-split").onclick = () => splitAt(E.t);
  $("ed-dup").onclick = duplicateSel; $("ed-del").onclick = removeSel;
  $("ed-export").onclick = exportDialog;
  $("ed-title").oninput = (e) => { E.name = e.target.value; };
  $("ed-zoom").oninput = (e) => { E.zoom = Number(e.target.value); renderTimeline(); };
  $("ed-fit").onclick = fitZoom;
  root.querySelectorAll(".ed-tabs button").forEach((b) => b.onclick = () => setTab(b.dataset.tab));
  root.querySelectorAll("#ed-win [data-w]").forEach((b) => b.onclick = () => api("/api/window/" + b.dataset.w));
  $("ed-scroll").addEventListener("pointerdown", scrollDown);
  addEventListener("pointermove", dragMove); addEventListener("pointerup", dragEnd);
  cv.addEventListener("pointerdown", canvasDown);
  addEventListener("keydown", keys);
  addEventListener("resize", () => { if (root.classList.contains("on")) renderTimeline(); });
  $("ed-scroll").addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); E.zoom = clamp(E.zoom * (e.deltaY < 0 ? 1.15 : 0.87), 8, 400); renderTimeline(); } }, { passive: false });
}

/* ------------------------------------------------------------ UI: refresh */
function refreshAll() { layout(); renderTimeline(); renderInspector(); renderPane(); syncTransport(); }
function syncTransport() {
  $("ed-play").innerHTML = E.playing ? ICON.pause : ICON.play;
  $("ed-time").innerHTML = `${fmt(E.t)} <span>/ ${fmt(E.total)}</span>`;
  $("ed-undo").disabled = E.hi <= 0; $("ed-redo").disabled = E.hi >= E.hist.length - 1;
  $("ed-fmt").textContent = `${E.P.aspect} · ${{ fit: "Fit", fill: "Fill", blur: "Fit + blur" }[E.P.fit]}`;
  $("ed-split").disabled = !E.P.video.length; $("ed-del").disabled = !E.sel; $("ed-dup").disabled = !E.sel;
  $("ed-win").hidden = !(typeof S !== "undefined" && S && S.native_window);
}
function updatePlayhead() {
  const ph = $("ed-ph"); if (!ph) return;
  ph.style.left = (E.t * E.zoom) + "px";
  $("ed-time").innerHTML = `${fmt(E.t)} <span>/ ${fmt(E.total)}</span>`;
  if (E.playing) { const s = $("ed-scroll"), x = E.t * E.zoom; if (x > s.scrollLeft + s.clientWidth - 40 || x < s.scrollLeft) s.scrollLeft = Math.max(0, x - 80); }
}
function fitZoom() { const s = $("ed-scroll"); E.zoom = clamp((s.clientWidth - 90) / Math.max(E.total, 8), 8, 400); renderTimeline(); s.scrollLeft = 0; }
function scrollToPlayhead() { const s = $("ed-scroll"), x = E.t * E.zoom; if (x > s.scrollLeft + s.clientWidth - 40 || x < s.scrollLeft) s.scrollLeft = Math.max(0, x - 80); }

function lanes(items, startOf, endOf) {
  const ends = [];
  for (const it of [...items].sort((a, b) => startOf(a) - startOf(b))) {
    let l = ends.findIndex((e) => e <= startOf(it) + 1e-6);
    if (l < 0) { l = ends.length; ends.push(0); }
    ends[l] = endOf(it); it._lane = l;
  }
  return Math.max(1, ends.length);
}
const thumbOf = (src) => src.startsWith("ext:") ? "" : `/thumb/${encodeURIComponent(src)}`;
function renderTimeline() {
  const s = $("ed-scroll"), inner = $("ed-inner"), z = E.zoom;
  $("ed-zoom").value = z;
  const ends = [E.total, ...E.P.text.map((t) => t.start + t.dur), ...E.P.audio.map((a) => a.start + a.out - a.in), ...E.P.overlay.map((o) => o.start + o.len)];
  const width = Math.max(s.clientWidth, (Math.max(...ends) + 6) * z);
  inner.style.width = width + "px";
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600], step = steps.find((x) => x * z >= 70) || 600;
  let ruler = "";
  for (let t = 0; t * z < width; t += step / 5) {
    const big = Math.abs(t / step - Math.round(t / step)) < 1e-6;
    ruler += big ? `<span style="left:${t * z}px">${fmt(t).replace(/\.0$/, "")}</span><i class="big" style="left:${t * z}px"></i>` : `<i style="left:${t * z}px"></i>`;
  }
  const ol = lanes(E.P.overlay, (o) => o.start, (o) => o.start + o.len);
  const tl = lanes(E.P.text, (t) => t.start, (t) => t.start + t.dur);
  const al = lanes(E.P.audio, (a) => a.start, (a) => a.start + a.out - a.in);
  const selc = (id) => E.sel && E.sel.id === id ? " sel" : "";
  let h = `<div class="ed-ruler" id="ed-ruler" style="width:${width}px">${ruler}</div>`;
  // overlay lanes sit above the main track, topmost lane first
  h += `<div class="ed-track o" data-track="o" style="width:${width}px;height:${ol * 46}px"><div class="ed-bg"></div>`;
  if (!E.P.overlay.length) h += `<div class="ed-empty">Layers appear here. Use the layer button on a clip in Media</div>`;
  for (const o of E.P.overlay) h += `<div class="ed-item ov${selc(o.id)}" data-kind="o" data-id="${o.id}" style="left:${o.start * z}px;width:${Math.max(8, o.len * z)}px;top:${(ol - 1 - o._lane) * 46}px;height:44px;bottom:auto;background-image:url('${thumbOf(o.src)}')">
      <span class="hd l" data-h="l"></span><span class="lb">${esc(niceName(o.src))}</span><span class="hd r" data-h="r"></span></div>`;
  h += `</div>`;
  h += `<div class="ed-track v" data-track="v" style="width:${width}px"><div class="ed-bg"></div>`;
  if (!E.P.video.length) h += `<div class="ed-empty">Add a clip from the Media tab</div>`;
  for (const c of E.P.video) {
    h += `<div class="ed-item vc${selc(c.id)}" data-kind="v" data-id="${c.id}" style="left:${c.start * z}px;width:${Math.max(6, c.len * z)}px;background-image:url('${thumbOf(c.src)}')">
      <span class="hd l" data-h="l"></span><span class="lb">${esc(niceName(c.src))}<small>${fmt(c.len)}${c.speed !== 1 ? " · " + c.speed + "x" : ""}${(c.fx || []).length ? " · fx" : ""}</small></span><span class="hd r" data-h="r"></span></div>`;
    if (c.ov > 0) h += `<div class="ed-tmark" style="left:${c.start * z}px;width:${Math.max(10, c.ov * z)}px" title="${esc((TRANSITIONS.find((x) => x[0] === c.transition.type) || [0, "Transition"])[1])}"><b>◇</b></div>`;
  }
  h += `</div>`;
  h += `<div class="ed-track t" data-track="t" style="width:${width}px;height:${tl * 40}px"><div class="ed-bg"></div>`;
  if (!E.P.text.length) h += `<div class="ed-empty">Text appears here</div>`;
  for (const t of E.P.text) h += `<div class="ed-item tx${selc(t.id)}" data-kind="t" data-id="${t.id}" style="left:${t.start * z}px;width:${Math.max(8, t.dur * z)}px;top:${t._lane * 40}px;height:38px;bottom:auto">
      <span class="hd l" data-h="l"></span><span class="lb">${esc(String(t.text).split("\n")[0])}</span><span class="hd r" data-h="r"></span></div>`;
  h += `</div>`;
  h += `<div class="ed-track a" data-track="a" style="width:${width}px;height:${al * 40}px"><div class="ed-bg"></div>`;
  if (!E.P.audio.length) h += `<div class="ed-empty">Music and sounds appear here</div>`;
  for (const a of E.P.audio) h += `<div class="ed-item au${selc(a.id)}" data-kind="a" data-id="${a.id}" style="left:${a.start * z}px;width:${Math.max(8, (a.out - a.in) * z)}px;top:${a._lane * 40}px;height:38px;bottom:auto">
      <span class="hd l" data-h="l"></span><span class="lb">${esc(niceName(a.src))}</span><span class="hd r" data-h="r"></span></div>`;
  h += `</div><div class="ed-playhead" id="ed-ph" style="height:100%"></div>`;
  inner.innerHTML = h;
  updatePlayhead();
}

/* timeline pointer handling */
function xToT(e) { const r = $("ed-inner").getBoundingClientRect(); return clamp((e.clientX - r.left) / E.zoom, 0, 36000); }
function scrollDown(e) {
  if (e.button !== 0) return;
  const item = e.target.closest(".ed-item");
  if (item) {
    const kind = item.dataset.kind, id = item.dataset.id, it = find(kind, id);
    E.sel = { kind, id }; renderInspector(); renderTimelineSel(); renderPane();
    const h = e.target.dataset.h;
    E.drag = { type: h ? "trim" + h : "move", kind, id, x0: e.clientX, snap: JSON.parse(JSON.stringify(it)), moved: false };
    e.preventDefault(); return;
  }
  if (e.target.closest(".ed-ruler") || e.target.closest(".ed-track")) {
    E.sel = null; renderInspector(); renderTimelineSel(); renderPane();
    E.drag = { type: "seek" };
    if (E.playing) pause();
    E.seekReq = xToT(e);
    e.preventDefault();
  }
}
function renderTimelineSel() {
  document.querySelectorAll("#ed-inner .ed-item").forEach((el) => el.classList.toggle("sel", !!E.sel && el.dataset.id === E.sel.id));
  syncTransport();
}
function dragMove(e) {
  const d = E.drag; if (!d) return;
  if (d.type === "seek") { E.seekReq = xToT(e); return; }
  const dx = e.clientX - d.x0, dt = dx / E.zoom;
  if (Math.abs(dx) > 2) d.moved = true;
  const it = find(d.kind, d.id); if (!it) return;
  const s = d.snap, src = (E.meta[it.src] || {}).dur || 1e9;
  if (d.kind === "v") {
    if (d.type === "trimr") it.out = clamp(s.out + dt * s.speed, s.in + 0.1, src);
    else if (d.type === "triml") it.in = clamp(s.in + dt * s.speed, 0, s.out - 0.1);
    else if (d.type === "move" && d.moved) {
      layout();
      const left = $("ed-inner").getBoundingClientRect().left;
      const grab = (d.x0 - left) / E.zoom - s.start;
      const centre = (e.clientX - left) / E.zoom - grab + it.len / 2;
      const others = E.P.video.filter((c) => c.id !== it.id);
      let idx = 0; for (const c of others) if (centre > c.start + c.len / 2) idx++;
      const cur = E.P.video.indexOf(it);
      if (idx !== cur) { E.P.video.splice(cur, 1); E.P.video.splice(idx, 0, it); }
    }
    layout();
  } else if (d.kind === "t") {
    if (d.type === "move") it.start = Math.max(0, s.start + dt);
    else if (d.type === "trimr") it.dur = Math.max(0.2, s.dur + dt);
    else if (d.type === "triml") { const ns = clamp(s.start + dt, 0, s.start + s.dur - 0.2); it.dur = s.dur - (ns - s.start); it.start = ns; }
  } else if (d.kind === "o") {
    if (d.type === "move") it.start = Math.max(0, s.start + dt);
    else if (d.type === "trimr") it.out = clamp(s.out + dt * s.speed, s.in + 0.1, src);
    else if (d.type === "triml") { const ni = clamp(s.in + dt * s.speed, 0, s.out - 0.1); it.start = Math.max(0, s.start + (ni - s.in) / s.speed); it.in = ni; }
    layout();
  } else {
    if (d.type === "move") it.start = Math.max(0, s.start + dt);
    else if (d.type === "trimr") it.out = clamp(s.out + dt, s.in + 0.1, src);
    else if (d.type === "triml") { const ni = clamp(s.in + dt, 0, s.out - 0.1); it.start = Math.max(0, s.start + (ni - s.in)); it.in = ni; }
  }
  renderTimeline(); renderInspector(true);
}
function dragEnd() {
  const d = E.drag; if (!d) return;
  E.drag = null;
  if (d.type === "seek") return;
  const it = find(d.kind, d.id);
  if (d.moved && it) { commit(); if (d.kind === "v") seek(E.t); }
}
function hitTest(x, y) {
  for (const t of [...E.P.text].reverse()) { const b = t._bb; if (b && x >= b.x - 10 && x <= b.x + b.w + 10 && y >= b.y - 10 && y <= b.y + b.h + 10) return { kind: "t", it: t }; }
  const ovs = [...E.P.overlay].sort((a, b) => (b._lane || 0) - (a._lane || 0));
  for (const o of ovs) { const b = o._bb; if (b && x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) return { kind: "o", it: o }; }
  return null;
}
function canvasDown(e) {
  const r = cv.getBoundingClientRect(), sx = cv.width / r.width;
  const x = (e.clientX - r.left) * sx, y = (e.clientY - r.top) * sx;
  const hit = hitTest(x, y); if (!hit) return;
  const it = hit.it;
  E.sel = { kind: hit.kind, id: it.id }; renderInspector(); renderTimelineSel();
  const ox = it.x - (x / cv.width * 100), oy = it.y - (y / cv.height * 100);
  const move = (ev) => {
    it.x = clamp(((ev.clientX - r.left) * sx) / cv.width * 100 + ox, 0, 100);
    it.y = clamp(((ev.clientY - r.top) * sx) / cv.height * 100 + oy, 0, 100);
    renderInspector(true);
  };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); commit(); };
  addEventListener("pointermove", move); addEventListener("pointerup", up);
  e.preventDefault();
}

/* ------------------------------------------------------------ left pane */
function setTab(t) { E.tab = t; renderPane(); }
const mediaCard = (c, extra) => `<button class="ed-mi" data-name="${esc(c.name)}" title="Add to the main track"><div class="th" style="background-image:url('/thumb/${encodeURIComponent(c.name)}')"><i>+</i>${c.duration ? `<span>${clock(c.duration)}</span>` : ""}${extra || ""}</div><b>${esc(cleanTitle(c))}</b></button>`;
const libClips = () => (typeof clips !== "undefined" ? clips : []);
function renderPane() {
  document.querySelectorAll("#ed .ed-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === E.tab));
  const p = $("ed-pane");
  if (E.tab === "media") {
    p.innerHTML = `<h4>Your clips</h4><div class="ed-media">${libClips().map((c) => mediaCard(c, `<em class="pip" data-pip title="Add as a layer on top of the main clip">${ICON.pip}</em>`)).join("") || '<p class="ed-hint">No clips yet.</p>'}</div>
      <p class="ed-hint" style="margin-top:12px">Click a clip to add it to the main track. Use the layer button to put it on top as a picture-in-picture.</p>`;
    p.querySelectorAll(".ed-mi").forEach((b) => b.onclick = (ev) => { if (ev.target.closest("[data-pip]")) addOverlay(b.dataset.name); else addClip(b.dataset.name); });
  } else if (E.tab === "text") {
    p.innerHTML = `<h4>Add text</h4><div class="ed-tpl">
      <button data-p="title"><b>Title</b><small>Big and centred</small></button>
      <button data-p="lower"><b>Lower third</b><small>Name or caption near the bottom</small></button>
      <button data-p="caption"><b>Caption box</b><small>White text on a dark box</small></button>
      <button data-p="meme"><b>Meme text</b><small>Impact with a black outline</small></button>
      <button data-p="gold"><b>Gold callout</b><small>Yellow impact for big moments</small></button></div>
      <p class="ed-hint" style="margin-top:14px">Text is added at the playhead. Drag it in the preview to place it, and drag its edges on the timeline to change how long it shows.</p>`;
    const pre = { title: { text: "Title", y: 50, size: 12 }, lower: { text: "Your name", y: 84, size: 6 }, caption: { text: "Caption", y: 88, size: 5, box: true, outline: false },
      meme: { text: "TOP TEXT", y: 12, size: 10, font: "impact", bold: false }, gold: { text: "CLUTCH!", y: 20, size: 11, font: "impact", bold: false, color: "#ffcc00" } };
    p.querySelectorAll("[data-p]").forEach((b) => b.onclick = () => addText(pre[b.dataset.p]));
  } else if (E.tab === "effects") {
    const it = selItem(), tgt = it && (E.sel.kind === "v" || E.sel.kind === "o") ? it : E.P.video[locate(E.t).i];
    const src = tgt ? thumbOf(tgt.src) : "";
    p.innerHTML = `<h4>Effects</h4><div class="ed-media">${EFFECTS.map(([id, name, css]) => `<button class="ed-fx${tgt && (tgt.fx || []).includes(id) ? " on" : ""}" data-fx="${id}">
      <div class="th" style="background-image:url('${src}');${css ? "filter:" + css : ""}${id === "mirror" ? ";transform:scaleX(-1)" : ""}${id === "flipv" ? ";transform:scaleY(-1)" : ""}"></div><b>${name}</b></button>`).join("")}</div>
      <p class="ed-hint" style="margin-top:12px">Click an effect to turn it on or off for the selected clip. You can stack several.</p>`;
    p.querySelectorAll("[data-fx]").forEach((b) => b.onclick = () => toggleEffect(b.dataset.fx));
  } else if (E.tab === "trans") {
    const c = E.sel && E.sel.kind === "v" ? find("v", E.sel.id) : null;
    const cur = c && c.transition ? c.transition.type : "none";
    p.innerHTML = `<h4>Transitions</h4><div class="ed-trgrid">${TRANSITIONS.map(([id, name]) => `<button class="ed-tr${cur === id ? " on" : ""}" data-tr="${id}"><span class="tp tp-${id}"></span><b>${name}</b></button>`).join("")}</div>
      <p class="ed-hint" style="margin-top:12px">A transition joins a clip to the one before it. Select the second clip (or park the playhead on it) and pick one. Change its length in the clip's settings.</p>`;
    p.querySelectorAll("[data-tr]").forEach((b) => b.onclick = () => applyTransition(b.dataset.tr));
  } else {
    renderAudioPane(p);
  }
}
function renderAudioPane(p) {
  const s = E.snd;
  const results = s.loading ? '<p class="ed-hint">Searching…</p>' : s.error ? `<p class="ed-err">${esc(s.error)}</p>`
    : (s.results.map((r, i) => `<div class="ed-snd" data-i="${i}"><button class="pl${s.playing === i ? " on" : ""}" data-rpv title="Preview">${s.playing === i ? "■" : "▶"}</button><b title="${esc(r.title)}">${esc(r.title)}<small>${r.duration >= 60 ? Math.floor(r.duration / 60) + "m " + Math.round(r.duration % 60) + "s" : r.duration + "s"} · ${esc(r.creator || r.source)}</small></b><button class="ad" data-radd title="Add to the timeline">+</button></div>`).join("")
      || (s.searched ? '<p class="ed-hint">Nothing found. Try another word.</p>' : ""));
  p.innerHTML = `<h4>Sound effects</h4><div class="ed-sfx">${SFX.map(([id, name]) => `<div class="ed-snd" data-sfx="${id}"><button class="pl" data-pv title="Preview">▶</button><b>${name}</b><button class="ad" data-add title="Add to the timeline">+</button></div>`).join("")}</div>
    <h4>Free music and sounds online</h4>
    <div class="ed-search"><input id="ed-q" type="text" placeholder="Search, like epic, whoosh, crowd" value="${esc(s.q)}" spellcheck="false">
      <div class="ed-chips" style="margin:8px 0"><button class="ed-chip${s.kind === "music" ? " on" : ""}" data-kind="music">Music</button><button class="ed-chip${s.kind === "sfx" ? " on" : ""}" data-kind="sfx">Sound effects</button><button class="ed-btn primary" id="ed-qgo" style="margin-left:auto">Search</button></div></div>
    <div id="ed-results">${results}${s.more && !s.loading ? '<button class="ed-btn" id="ed-more" style="margin-top:8px;width:100%;justify-content:center">Load more</button>' : ""}</div>
    <p class="ed-hint" style="margin-top:10px">Free to use with no credit needed (public domain or CC0). Searched through Openverse.</p>
    <h4>Your files</h4><button class="ed-btn" id="ed-addaudio">Add an audio file…</button>
    <h4>Sound from your clips</h4><div class="ed-media">${libClips().map((c) => `<button class="ed-mi" data-name="${esc(c.name)}" title="Use this clip's sound"><div class="th" style="background-image:url('/thumb/${encodeURIComponent(c.name)}')"><i>♪</i></div><b>${esc(cleanTitle(c))}</b></button>`).join("")}</div>`;
  $("ed-addaudio").onclick = addAudioFile;
  p.querySelectorAll(".ed-media .ed-mi").forEach((b) => b.onclick = () => addAudio(b.dataset.name).catch((e) => toast({ kind: "error", message: e.message })));
  p.querySelectorAll("[data-sfx]").forEach((row) => {
    row.querySelector("[data-add]").onclick = async () => { const id = await sfxId(row.dataset.sfx); if (id) addAudio(id.id, id.name).catch((e) => toast({ kind: "error", message: e.message })); };
    row.querySelector("[data-pv]").onclick = async () => { const id = await sfxId(row.dataset.sfx); if (id) previewUrl("/ext/" + id.id.slice(4), -1); };
  });
  const q = $("ed-q");
  q.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") searchSounds(true); });
  q.addEventListener("input", () => { s.q = q.value; });
  $("ed-qgo").onclick = () => searchSounds(true);
  p.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => { s.kind = b.dataset.kind; searchSounds(true); });
  const more = $("ed-more"); if (more) more.onclick = () => searchSounds(false);
  p.querySelectorAll("[data-i]").forEach((row) => {
    const i = Number(row.dataset.i), r = s.results[i];
    row.querySelector("[data-rpv]").onclick = () => previewUrl(r.url, i);
    row.querySelector("[data-radd]").onclick = async () => {
      const btn = row.querySelector("[data-radd]"); btn.textContent = "…"; btn.disabled = true;
      const res = await api("/api/editor/sound-fetch", { url: r.url, title: r.title });
      btn.textContent = "+"; btn.disabled = false;
      if (!res.ok) { toast({ kind: "error", message: res.error }); return; }
      addAudio(res.id, res.name).catch((e) => toast({ kind: "error", message: e.message }));
    };
  });
}
async function sfxId(name) {
  if (E.sfxIds[name]) return E.sfxIds[name];
  const r = await api("/api/editor/sfx", { name });
  if (!r.ok) { toast({ kind: "error", message: r.error }); return null; }
  return (E.sfxIds[name] = r);
}
function previewUrl(url, idx) {
  if (E.prev) { E.prev.pause(); E.prev = null; }
  const was = E.snd.playing;
  E.snd.playing = -1;
  if (idx >= 0 && was === idx) { renderPane(); return; }
  const a = new Audio(url); a.volume = 0.8; E.prev = a;
  a.onended = () => { E.snd.playing = -1; if (E.tab === "audio") renderPane(); };
  a.play().catch(() => {});
  E.snd.playing = idx;
  if (E.tab === "audio") renderPane();
}
async function searchSounds(fresh) {
  const s = E.snd;
  if (fresh) { s.page = 1; s.results = []; } else s.page += 1;
  s.loading = true; s.error = ""; s.searched = true; renderPane();
  try {
    const r = await get(`/api/editor/sounds?q=${encodeURIComponent(s.q)}&kind=${s.kind}&page=${s.page}`);
    if (!r.ok) s.error = r.error; else { s.results = s.results.concat(r.results); s.more = r.more; }
  } catch (e) { s.error = "Couldn't reach the free sound library."; }
  s.loading = false; renderPane();
}

/* ------------------------------------------------------------ inspector */
function row(label, key, min, max, step, val, out) {
  return `<div class="ed-row"><label>${label}</label><input type="range" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${val}"><output>${out}</output></div>`;
}
const fxChips = (it) => `<div class="ed-chips">${EFFECTS.map(([id, name]) => `<button class="ed-chip${(it.fx || []).includes(id) ? " on" : ""}" data-fxc="${id}">${name}</button>`).join("")}</div>`;
function renderInspector(light) {
  const el = $("ed-insp");
  const it = selItem();
  if (light && el.dataset.sel === (E.sel ? E.sel.id : "none")) { updateInspectorValues(); return; }
  el.dataset.sel = E.sel ? E.sel.id : "none";
  if (!it) {
    el.innerHTML = `<h3>Project</h3>
      <div class="ed-field"><label>Canvas shape</label><div class="ed-chips" id="i-aspect">${Object.keys(ASPECTS).map((a) => `<button class="ed-chip${E.P.aspect === a ? " on" : ""}" data-a="${a}">${a}</button>`).join("")}</div></div>
      <div class="ed-field"><label>When a clip doesn't match the canvas</label><div class="ed-chips" id="i-fit">${[["fit", "Fit"], ["fill", "Fill"], ["blur", "Fit + blur"]].map(([k, l]) => `<button class="ed-chip${E.P.fit === k ? " on" : ""}" data-f="${k}">${l}</button>`).join("")}</div></div>
      <p class="ed-hint" style="margin-top:14px">Pick a clip, layer, text or sound on the timeline to edit it. Use <b>9:16</b> for Shorts, Reels and TikTok.</p>`;
    el.querySelectorAll("[data-a]").forEach((b) => b.onclick = () => { E.P.aspect = b.dataset.a; commit(); });
    el.querySelectorAll("[data-f]").forEach((b) => b.onclick = () => { E.P.fit = b.dataset.f; commit(); });
    return;
  }
  const k = E.sel.kind;
  const colour = (f) => `<h4>Colour</h4>${row("Brightness", "filter.b", -100, 100, 1, f.b, f.b)}${row("Contrast", "filter.c", -100, 100, 1, f.c, f.c)}${row("Saturation", "filter.s", -100, 100, 1, f.s, f.s)}`;
  const speed = (it) => `<h4>Speed</h4><div class="ed-chips" id="i-speed">${[0.25, 0.5, 1, 1.5, 2, 4].map((s) => `<button class="ed-chip${it.speed === s ? " on" : ""}" data-s="${s}">${s}x</button>`).join("")}</div>${row("Custom", "speed", 0.25, 4, 0.05, it.speed, it.speed.toFixed(2) + "x")}`;
  const sound = (it) => `<h4>Sound</h4>${row("Volume", "volume", 0, 2, 0.05, it.volume, Math.round(it.volume * 100) + "%")}<label class="ed-check"><input type="checkbox" data-k="mute" ${it.mute ? "checked" : ""}> Mute</label>`;
  const fades = (it) => `<h4>Fades</h4>${row("Fade in", "fadeIn", 0, 3, 0.1, it.fadeIn, it.fadeIn.toFixed(1) + "s")}${row("Fade out", "fadeOut", 0, 3, 0.1, it.fadeOut, it.fadeOut.toFixed(1) + "s")}`;
  if (k === "v") {
    const idx = E.P.video.indexOf(it), tr = it.transition || { type: "none", dur: 0.6 };
    el.innerHTML = `<h3>${esc(niceName(it.src))}</h3>
      ${speed(it)}${sound(it)}${colour(it.filter)}${fades(it)}
      <h4>Transition in</h4>${idx === 0 ? '<p class="ed-hint">The first clip has nothing before it. Pick the second clip to add a transition.</p>' : `<div class="ed-chips" id="i-tr"><button class="ed-chip${tr.type === "none" ? " on" : ""}" data-t="none">None</button>${TRANSITIONS.map(([id, n]) => `<button class="ed-chip${tr.type === id ? " on" : ""}" data-t="${id}">${n}</button>`).join("")}</div>${tr.type !== "none" ? row("Length", "transition.dur", 0.2, 2.5, 0.1, tr.dur, tr.dur.toFixed(1) + "s") : ""}`}
      <h4>Effects</h4>${fxChips(it)}
      <div class="ed-actions"><button class="ed-btn" id="i-reset">Reset colour</button><button class="ed-btn" id="i-split">${ICON.split}Split here</button></div>`;
  } else if (k === "o") {
    el.innerHTML = `<h3>Layer: ${esc(niceName(it.src))}</h3>
      <h4>Position and size</h4>${row("Across", "x", 0, 100, 1, it.x, Math.round(it.x) + "%")}${row("Down", "y", 0, 100, 1, it.y, Math.round(it.y) + "%")}${row("Size", "scale", 8, 100, 1, it.scale, Math.round(it.scale) + "%")}${row("Opacity", "opacity", 0.1, 1, 0.05, it.opacity, Math.round(it.opacity * 100) + "%")}
      <p class="ed-hint">You can also drag the layer in the preview.</p>
      ${speed(it)}${sound(it)}${colour(it.filter)}${fades(it)}
      <h4>Effects</h4>${fxChips(it)}
      <div class="ed-2" style="margin-top:12px"><div class="ed-field"><label>Starts at (s)</label><input type="number" step="0.1" min="0" data-k="start" value="${it.start.toFixed(1)}"></div>
      <div class="ed-field"><label>Plays from (s)</label><input type="number" step="0.1" min="0" data-k="in" value="${it.in.toFixed(1)}"></div></div>`;
  } else if (k === "t") {
    el.innerHTML = `<h3>Text</h3>
      <div class="ed-field"><label>Text</label><textarea data-k="text">${esc(it.text)}</textarea></div>
      <div class="ed-2"><div class="ed-field"><label>Font</label><select data-k="font">${Object.entries(FONT_NAMES).map(([v, n]) => `<option value="${v}" ${it.font === v ? "selected" : ""}>${n}</option>`).join("")}</select></div>
      <div class="ed-field"><label>Colour</label><input type="color" data-k="color" value="${it.color}"></div></div>
      ${row("Size", "size", 2, 30, 0.5, it.size, it.size)}${row("Across", "x", 0, 100, 1, it.x, Math.round(it.x) + "%")}${row("Down", "y", 0, 100, 1, it.y, Math.round(it.y) + "%")}
      <label class="ed-check"><input type="checkbox" data-k="bold" ${it.bold ? "checked" : ""}> Bold</label>
      <label class="ed-check"><input type="checkbox" data-k="outline" ${it.outline ? "checked" : ""}> Outline</label>
      <label class="ed-check"><input type="checkbox" data-k="box" ${it.box ? "checked" : ""}> Dark box behind</label>
      <div class="ed-2"><div class="ed-field"><label>Starts at (s)</label><input type="number" step="0.1" min="0" data-k="start" value="${it.start.toFixed(1)}"></div>
      <div class="ed-field"><label>Shows for (s)</label><input type="number" step="0.1" min="0.2" data-k="dur" value="${it.dur.toFixed(1)}"></div></div>`;
  } else {
    el.innerHTML = `<h3>${esc(niceName(it.src))}</h3>
      ${row("Volume", "volume", 0, 2, 0.05, it.volume, Math.round(it.volume * 100) + "%")}
      ${row("Fade in", "fadeIn", 0, 5, 0.1, it.fadeIn, it.fadeIn.toFixed(1) + "s")}${row("Fade out", "fadeOut", 0, 5, 0.1, it.fadeOut, it.fadeOut.toFixed(1) + "s")}
      <div class="ed-2"><div class="ed-field"><label>Starts at (s)</label><input type="number" step="0.1" min="0" data-k="start" value="${it.start.toFixed(1)}"></div>
      <div class="ed-field"><label>Plays from (s)</label><input type="number" step="0.1" min="0" data-k="in" value="${it.in.toFixed(1)}"></div></div>`;
  }
  el.querySelectorAll("[data-k]").forEach(bindField);
  el.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => { it.speed = Number(b.dataset.s); commit(); seek(E.t); });
  el.querySelectorAll("[data-t]").forEach((b) => b.onclick = () => { it.transition = { type: b.dataset.t, dur: (it.transition && it.transition.dur) || 0.6 }; commit(); seek(Math.max(0, it.start - 0.4)); });
  el.querySelectorAll("[data-fxc]").forEach((b) => b.onclick = () => { it.fx = it.fx || []; const i = it.fx.indexOf(b.dataset.fxc); if (i >= 0) it.fx.splice(i, 1); else it.fx.push(b.dataset.fxc); commit(); });
  const rs = $("i-reset"); if (rs) rs.onclick = () => { it.filter = newFilter(); commit(); };
  const sp = $("i-split"); if (sp) sp.onclick = () => splitAt(E.t);
}
function setPath(o, path, v) { const p = path.split("."); let t = o; while (p.length > 1) t = t[p.shift()]; t[p[0]] = v; }
function getPath(o, path) { return path.split(".").reduce((t, k) => t[k], o); }
function bindField(f) {
  const key = f.dataset.k;
  const apply = () => {
    const it = selItem(); if (!it) return;
    let v = f.type === "checkbox" ? f.checked : f.type === "range" || f.type === "number" ? Number(f.value) : f.value;
    if (key === "start" || key === "dur" || key === "in") v = Math.max(key === "dur" ? 0.2 : 0, v);
    setPath(it, key, v);
    layout();
    const out = f.parentElement.querySelector("output");
    if (out) out.textContent = key === "speed" ? Number(v).toFixed(2) + "x" : ["volume", "opacity"].includes(key) ? Math.round(v * 100) + "%" : ["fadeIn", "fadeOut", "transition.dur"].includes(key) ? Number(v).toFixed(1) + "s" : ["x", "y", "scale"].includes(key) ? Math.round(v) + "%" : v;
    renderTimeline();
  };
  f.addEventListener("input", () => { apply(); if (E.sel && ["volume", "mute"].includes(key)) applyVolume(); });
  f.addEventListener("change", () => { apply(); commit(); if (key === "speed" || key === "mute" || key === "transition.dur") seek(E.t); });
}
function updateInspectorValues() {
  const it = selItem(); if (!it) return;
  document.querySelectorAll("#ed-insp [data-k]").forEach((f) => {
    if (document.activeElement === f) return;
    let v; try { v = getPath(it, f.dataset.k); } catch (e) { return; }
    if (f.type === "checkbox") f.checked = !!v; else if (f.type === "number") f.value = Number(v).toFixed(1); else f.value = v;
  });
}

/* ------------------------------------------------------------ export */
function modal(html) { $("ed-card").innerHTML = html; $("ed-modal").classList.add("on"); }
function closeModal() { $("ed-modal").classList.remove("on"); }
function cleanProject() {
  const strip = (o) => { const c = JSON.parse(JSON.stringify(o)); delete c._bb; delete c.len; return c; };
  return { aspect: E.P.aspect, fit: E.P.fit,
    video: E.P.video.map((o) => { const c = strip(o); delete c.start; delete c.ov; delete c._lane; return c; }),
    overlay: E.P.overlay.map((o) => { const c = strip(o); c._lane = o._lane || 0; return c; }),
    text: E.P.text.map((o) => { const c = strip(o); delete c._lane; return c; }),
    audio: E.P.audio.map((o) => { const c = strip(o); delete c._lane; return c; }) };
}
function exportDialog() {
  if (!E.P.video.length) { toast({ kind: "error", message: "Add a clip to the timeline first." }); return; }
  pause();
  modal(`<h3>Export video</h3>
    <div class="ed-field"><label>Name</label><input type="text" id="x-name" value="${esc(E.name)}" spellcheck="false"></div>
    <div class="ed-2"><div class="ed-field"><label>Quality</label><select id="x-res"><option value="1080">Full HD (1080)</option><option value="720">HD (720)</option></select></div>
    <div class="ed-field"><label>File size</label><select id="x-q"><option value="standard">Balanced</option><option value="high">Best looking</option><option value="draft">Smallest</option></select></div></div>
    <p class="ed-small">${E.P.aspect}, ${fmt(E.total)} long. It saves to your clips folder under <b>Edits</b>.</p>
    <div class="ed-foot"><button class="ed-btn" id="x-cancel">Cancel</button><button class="ed-btn primary" id="x-go">Export</button></div>`);
  $("x-cancel").onclick = closeModal;
  $("x-go").onclick = startExport;
}
async function startExport() {
  const title = $("x-name").value.trim() || "Edit", res = Number($("x-res").value), quality = $("x-q").value;
  modal(`<h3>Exporting…</h3><div class="ed-bar"><i id="x-bar"></i></div><div class="ed-small" id="x-pct">Starting…</div>
    <div class="ed-foot"><button class="ed-btn" id="x-stop">Cancel export</button></div>`);
  const r = await api("/api/editor/export", { project: cleanProject(), title, res, quality });
  if (!r.ok) { modal(`<h3>Couldn't export</h3><div class="ed-err">${esc(r.error)}</div><div class="ed-foot"><button class="ed-btn" id="x-ok">OK</button></div>`); $("x-ok").onclick = closeModal; return; }
  $("x-stop").onclick = () => api("/api/editor/cancel", { id: r.job });
  for (;;) {
    await new Promise((res2) => setTimeout(res2, 400));
    let j; try { j = await get("/api/editor/job?id=" + r.job); } catch (e) { continue; }
    if ($("x-bar")) { $("x-bar").style.width = j.pct + "%"; $("x-pct").textContent = Math.round(j.pct) + "%"; }
    if (j.done) {
      if (j.error) { modal(`<h3>Export stopped</h3><div class="ed-err">${esc(j.error)}</div><div class="ed-foot"><button class="ed-btn" id="x-ok">OK</button></div>`); $("x-ok").onclick = closeModal; return; }
      E.exported = true;
      modal(`<h3>Your video is ready</h3><p class="ed-small">${esc(j.rel.split("/").pop())}</p>
        <div class="ed-foot"><button class="ed-btn" id="x-keep">Keep editing</button><button class="ed-btn" id="x-show">Show in folder</button><button class="ed-btn primary" id="x-watch">Watch it</button></div>`);
      $("x-keep").onclick = closeModal;
      $("x-show").onclick = () => api("/api/clips/reveal", { name: j.rel });
      $("x-watch").onclick = async () => { closeModal(); close(true); await loadClips(); openPlayer(j.rel); };
      loadClips();
      return;
    }
  }
}

/* ------------------------------------------------------------ keys + open/close */
function keys(e) {
  if (!$("ed").classList.contains("on")) return;
  if ($("ed-modal").classList.contains("on")) { if (e.key === "Escape") closeModal(); return; }
  const tag = e.target.tagName;
  if (tag === "INPUT" && e.target.type !== "range" && e.target.type !== "checkbox" || tag === "TEXTAREA" || tag === "SELECT") { if (e.key === "Escape") e.target.blur(); return; }
  const k = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && k === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  else if ((e.ctrlKey || e.metaKey) && k === "y") { e.preventDefault(); redo(); }
  else if ((e.ctrlKey || e.metaKey) && k === "d") { e.preventDefault(); duplicateSel(); }
  else if (e.key === " ") { e.preventDefault(); toggle(); }
  else if (k === "s" && !e.ctrlKey) { splitAt(E.t); }
  else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); removeSel(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); if (E.playing) pause(); E.seekReq = E.t - (e.shiftKey ? 1 : 1 / 30); }
  else if (e.key === "ArrowRight") { e.preventDefault(); if (E.playing) pause(); E.seekReq = E.t + (e.shiftKey ? 1 : 1 / 30); }
  else if (e.key === "Home") { seek(0); }
  else if (e.key === "End") { seek(E.total); }
  else if (e.key === "Escape") { close(); }
}
async function open(name, range) {
  build();
  let m;
  try { m = await loadMeta(name); } catch (e) { toast({ kind: "error", message: "Couldn't open that clip in the editor." }); return; }
  const inn = range && range.start > 0.05 ? range.start : 0, out = range && range.end && range.end < m.dur - 0.05 ? range.end : m.dur;
  E.P = { aspect: "16:9", fit: "fit", video: [newClip(name, inn, out)], overlay: [], text: [], audio: [] };
  E.name = niceName(name) + " edit"; E.sel = null; E.t = 0; E.playing = false; E.hist = []; E.hi = -1; E.exported = false; E.curI = -1; E.outI = -1; E.busy = false;
  if (m.h > m.w) E.P.aspect = "9:16";
  layout();
  E.hist.push(JSON.stringify(E.P)); E.hi = 0;
  $("ed-title").value = E.name;
  $("ed").classList.add("on");
  E.tab = "media";
  const w = $("ed-scroll").clientWidth || 900;
  E.zoom = clamp((w - 80) / Math.max(E.total, 8), 10, 200);
  refreshAll(); setTimeout(() => { renderTimeline(); }, 50);
  seek(0);
  requestAnimationFrame(tick);
}
function close(force) {
  if (!force && E.hi > 0 && !E.exported && !confirmClose()) return;
  pause(); $("ed").classList.remove("on"); closeModal();
  V.forEach((v) => { v.removeAttribute("src"); delete v.dataset.src; v.load(); });
  Object.values(E.audio).forEach((a) => a.el.pause()); E.audio = {};
  Object.values(E.ov).forEach((o) => { o.pause(); o.removeAttribute("src"); }); E.ov = {};
  if (E.prev) { E.prev.pause(); E.prev = null; }
  E.curI = -1; E.outI = -1;
}
function confirmClose() {
  pause();
  modal(`<h3>Leave the editor?</h3><p class="ed-small">Your edits haven't been exported yet and will be lost.</p>
    <div class="ed-foot"><button class="ed-btn" id="c-stay">Keep editing</button><button class="ed-btn danger" id="c-leave">Leave</button></div>`);
  $("c-stay").onclick = closeModal; $("c-leave").onclick = () => { closeModal(); close(true); };
  return false;
}

window.Editor = { open, close, state: E, addClip, addOverlay, splitAt, applyTransition, toggleEffect, addText };
})();

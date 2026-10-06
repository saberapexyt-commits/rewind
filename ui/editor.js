/* Rewind video editor (CapCut-style): tracks, transitions, timed effects and filters, text, free sounds, export. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const ASPECTS = { "16:9": [960, 540], "9:16": [540, 960], "1:1": [720, 720], "4:5": [640, 800] };
const FONTS = { segoe: "'Segoe UI', sans-serif", arial: "Arial, sans-serif", impact: "Impact, sans-serif", black: "'Arial Black', sans-serif",
  georgia: "Georgia, serif", consolas: "Consolas, monospace", comic: "'Comic Sans MS', cursive" };
const FONT_NAMES = { segoe: "Segoe UI", arial: "Arial", impact: "Impact", black: "Arial Black", georgia: "Georgia", consolas: "Consolas", comic: "Comic Sans" };
/* [id, label, category] */
const TRANSITIONS = [["fade", "Fade", "basic"], ["dissolve", "Dissolve", "basic"], ["fadeblack", "Dip to black", "basic"], ["wipeleft", "Wipe left", "wipe"],
  ["wiperight", "Wipe right", "wipe"], ["wipeup", "Wipe up", "wipe"], ["wipedown", "Wipe down", "wipe"], ["slideleft", "Slide left", "slide"],
  ["slideright", "Slide right", "slide"], ["circleopen", "Circle open", "shape"], ["circleclose", "Circle close", "shape"], ["zoomin", "Zoom in", "shape"]];
const TR_CATS = [["all", "All"], ["basic", "Basic"], ["wipe", "Wipe"], ["slide", "Slide"], ["shape", "Shape"]];
/* [id, label, category, glyph] */
const EFFECTS = [["flash", "Flash", "basic", "⚡"], ["blur", "Blur", "basic", "◌"], ["vignette", "Vignette", "basic", "◎"], ["grain", "Film grain", "basic", "▒"],
  ["bars", "Cinema bars", "basic", "▬"], ["mirror", "Mirror", "basic", "◧"], ["negative", "Negative", "basic", "◐"],
  ["glitch", "Glitch", "glitch", "▞"], ["vhs", "VHS", "glitch", "▤"], ["pixel", "Pixelate", "glitch", "▦"],
  ["shake", "Shake", "motion", "≋"], ["zoom", "Zoom pulse", "motion", "⊕"], ["pulse", "Heartbeat", "motion", "♥"]];
const EF_CATS = [["all", "All"], ["basic", "Basic"], ["glitch", "Glitch"], ["motion", "Motion"]];
/* [id, label, category, css filter for preview and tiles] */
const LOOKS = [["vivid", "Vivid", "basic", "saturate(1.55) contrast(1.1)"], ["pop", "Pop", "basic", "contrast(1.2) saturate(1.5)"], ["warm", "Warm", "basic", "sepia(.35) saturate(1.3)"],
  ["cool", "Cool", "basic", "hue-rotate(-12deg) saturate(1.1)"], ["fade", "Faded", "basic", "contrast(.86) brightness(1.05) saturate(.75)"],
  ["bw", "Black & white", "mono", "grayscale(1)"], ["noir", "Noir", "mono", "grayscale(1) contrast(1.45) brightness(.97)"], ["sepia", "Sepia", "mono", "sepia(1)"],
  ["cinematic", "Cinematic", "film", "contrast(1.1) saturate(1.1) hue-rotate(-8deg) sepia(.12)"], ["retro", "Retro", "film", "sepia(.8) contrast(.9) brightness(1.03)"],
  ["neon", "Neon", "film", "saturate(1.9) contrast(1.15) hue-rotate(12deg)"], ["dusk", "Dusk", "film", "saturate(1.15) brightness(.96) hue-rotate(-10deg) sepia(.15)"]];
const LK_CATS = [["all", "All"], ["basic", "Basic"], ["mono", "Mono"], ["film", "Film"]];
const SFX = [["whoosh", "Whoosh"], ["swish", "Swish"], ["riser", "Riser"], ["boom", "Boom"], ["impact", "Impact"], ["pop", "Pop"], ["ding", "Ding"],
  ["click", "Click"], ["success", "Success"], ["buzz", "Error buzz"], ["laser", "Laser"], ["glitch", "Glitch"]];
const TEXT_PRESETS = [["title", "Title", "Big and centred", "basic", { text: "Title", y: 50, size: 12 }],
  ["lower", "Lower third", "Name or caption near the bottom", "basic", { text: "Your name", y: 84, size: 6 }],
  ["caption", "Caption box", "White text on a dark box", "basic", { text: "Caption", y: 88, size: 5, box: true, outline: false }],
  ["meme", "Meme text", "Impact with a black outline", "gaming", { text: "TOP TEXT", y: 12, size: 10, font: "impact", bold: false }],
  ["gold", "Gold callout", "Yellow impact for big moments", "gaming", { text: "CLUTCH!", y: 20, size: 11, font: "impact", bold: false, color: "#ffcc00" }]];
const KIND_NAMES = { e: "Effect", l: "Filter", t: "Text", o: "Video", v: "Main", a: "Audio" };
const ADD_NAMES = { o: "Video", t: "Text", e: "Effect", l: "Filter", a: "Audio" };
const KEY_OF = { v: "video", o: "overlay", t: "text", e: "effect", l: "look", a: "audio" };
const LANE_H = { e: 30, l: 30, t: 34, o: 54, v: 76, a: 38 };
const GUT = 142;
const I = (d, extra) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${extra || ""}>${d}</svg>`;
const ICON = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l12-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/></svg>',
  split: I('<path d="M12 3v18M7 8L3 12l4 4M17 8l4 4-4 4"/>'), trash: I('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
  copy: I('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>'), undo: I('<path d="M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3"/>'),
  redo: I('<path d="M15 14l5-5-5-5M20 9H10a6 6 0 0 0 0 12h3"/>'), back: I('<path d="M15 5l-7 7 7 7"/>'),
  pip: I('<rect x="3" y="5" width="18" height="14" rx="2"/><rect x="12" y="11" width="7" height="6" rx="1" fill="currentColor"/>'),
  media: I('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M10 9l5 3-5 3z" fill="currentColor"/>'), audio: I('<path d="M9 18V5l11-2v13M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zM20 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z"/>'),
  text: I('<path d="M5 6V4h14v2M12 4v16M9 20h6"/>'), effects: I('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>'),
  trans: I('<path d="M3 5l8 7-8 7zM21 5l-8 7 8 7z"/>'), filters: I('<circle cx="9" cy="10" r="5"/><circle cx="15" cy="10" r="5"/><circle cx="12" cy="15" r="5"/>'),
  eye: I('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'), spk: I('<path d="M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7"/>'),
  join: I('<path d="M8 4v16M16 4v16M4 8l4-4M20 16l-4 4"/>'), cursor: I('<path d="M5 3l14 8-6 2-2 6z"/>'), kbd: I('<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>'),
};

const DEF_TF = () => ({ scale: 100, x: 0, y: 0, rot: 0, opacity: 100 });
const E = { P: null, sel: null, t: 0, total: 0, playing: false, zoom: 60, hist: [], hi: -1, meta: {}, name: "", tab: "media", cats: {}, itab: "video",
  pv: null, cur: 0, curI: -1, outI: -1, token: 0, busy: false, exported: false, audio: {}, ov: {}, ctx: null, gains: new WeakMap(), drag: null, seekReq: null,
  built: false, snd: { q: "", kind: "music", page: 1, results: [], more: false, loading: false, error: "", playing: -1, searched: false }, sfxIds: {}, prev: null, dnd: null, savedAt: null };
const V = [document.createElement("video"), document.createElement("video")];
V.forEach((v) => { v.playsInline = true; v.preload = "auto"; });

const uid = () => Math.random().toString(36).slice(2, 9);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (t) => { t = Math.max(0, t); const m = Math.floor(t / 60); return `${m}:${(t % 60).toFixed(1).padStart(4, "0")}`; };
const fmtFull = (t) => { t = Math.max(0, t); const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = Math.floor(t % 60), f = Math.floor((t % 1) * 30); const p = (n) => String(n).padStart(2, "0"); return `${p(h)}:${p(m)}:${p(s)}:${p(f)}`; };
const srcUrl = (s) => s.startsWith("ext:") ? "/ext/" + s.slice(4) : "/media/" + encodeURIComponent(s);
const cleanTitle = (c) => c.title.replace(/ \d{4}-\d\d-\d\d \d\d-\d\d-\d\d.*$/, "") || c.title;
const niceName = (s) => s.startsWith("ext:") ? (E.meta[s] && E.meta[s].label) || "Audio file" : s.split("/").pop().replace(/\.mp4$/i, "").replace(/ \d{4}-\d\d-\d\d \d\d-\d\d-\d\d.*$/, "");
const lookOf = (id) => LOOKS.find((x) => x[0] === id), effOf = (id) => EFFECTS.find((x) => x[0] === id), trOf = (id) => TRANSITIONS.find((x) => x[0] === id);
const laneFlag = (key, flag) => !!(E.P.lanes[key] && E.P.lanes[key][flag]);

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
const itemSpan = (k, it) => k === "o" ? it.len : k === "a" ? it.out - it.in : it.dur;
const newFilter = () => ({ b: 0, c: 0, s: 0 });
function newClip(src, inn, out) {
  return { id: uid(), src, in: inn, out, speed: 1, volume: 1, mute: false, filter: newFilter(), transform: DEF_TF(), fadeIn: 0, fadeOut: 0, transition: { type: "none", dur: 0.6 } };
}
function newOverlay(src, inn, out, start) {
  return { id: uid(), src, in: inn, out, start, lane: 0, speed: 1, volume: 1, mute: false, x: 50, y: 50, scale: 100, rot: 0, opacity: 1, filter: newFilter(), fadeIn: 0, fadeOut: 0 };
}
/* Tracks are made on purpose with the Add track buttons. Items only ever go onto a track that exists. */
function pickLane(kind, start, end, want, skipId) {
  const n = E.P.tracks[kind] || 0, nm = ADD_NAMES[kind].toLowerCase();
  if (!n) { toast({ kind: "error", message: `There's no ${nm} track yet. Press + ${ADD_NAMES[kind]} under the timeline to add one.` }); return null; }
  if (want != null) return want;
  const used = listOf(kind).filter((x) => x.id !== skipId && x.start < end - 1e-6 && x.start + itemSpan(kind, x) > start + 1e-6).map((x) => x.lane || 0);
  for (let l = 0; l < n; l++) if (!used.includes(l)) return l;
  toast({ kind: "error", message: `Every ${nm} track is busy at that point. Press + ${ADD_NAMES[kind]} to add another one.` });
  return null;
}
function trackHint(kind) {
  return (E.P.tracks[kind] || 0) ? "" : `<p class="ed-hint warn">You need a ${ADD_NAMES[kind].toLowerCase()} track first. Press <b>+ ${ADD_NAMES[kind]}</b> under the timeline.</p>`;
}
function addTrack(kind) { E.P.tracks[kind] = (E.P.tracks[kind] || 0) + 1; commit(); const s = $("ed-scroll"); s.scrollTop = 0; }
function removeTrack(kind, lane) {
  const key = KEY_OF[kind];
  E.P[key] = E.P[key].filter((x) => (x.lane || 0) !== lane);
  E.P[key].forEach((x) => { if ((x.lane || 0) > lane) x.lane -= 1; });
  for (const k of Object.keys(E.P.lanes)) if (k.startsWith(kind) && /^\d+$/.test(k.slice(1))) delete E.P.lanes[k];
  E.P.tracks[kind] = Math.max(0, (E.P.tracks[kind] || 1) - 1);
  if (E.sel && !selItem()) E.sel = null;
  commit(); seek(E.t);
}
function locate(t) {
  const v = E.P.video; let i = 0;
  for (let k = 0; k < v.length; k++) if (v[k].start <= t + 1e-6) i = k;
  let j = -1, p = 1;
  const c = v[i];
  if (c && i > 0 && c.ov > 0 && t < c.start + c.ov) { j = i - 1; p = clamp((t - c.start) / c.ov, 0, 1); }
  return { i, j, p };
}
const listOf = (k) => E.P[KEY_OF[k]];
function find(kind, id) { return kind === "j" ? E.P.video.find((x) => x.id === id) : listOf(kind).find((x) => x.id === id); }
function selItem() { return E.sel ? find(E.sel.kind, E.sel.id) : null; }
function commit() {
  layout();
  E.hist = E.hist.slice(0, E.hi + 1);
  E.hist.push(JSON.stringify(E.P));
  if (E.hist.length > 80) E.hist.shift();
  E.hi = E.hist.length - 1;
  E.exported = false; E.savedAt = new Date();
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
  const mainMuted = laneFlag("main", "muted");
  const gainOf = (cl, extra) => {
    let g = cl.mute || mainMuted ? 0 : cl.volume; const local = E.t - cl.start;
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
    const el = ovEl(o), t = E.t, inside = t >= o.start && t < o.start + o.len && !laneFlag("o" + o.lane, "hidden");
    if (!inside) { if (!el.paused) el.pause(); continue; }
    const want = o.in + (t - o.start) * o.speed;
    let g = o.mute || laneFlag("o" + o.lane, "muted") ? 0 : o.volume; const local = t - o.start;
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
    const inside = E.playing && t >= a.start && t < a.start + len && !laneFlag("a" + a.lane, "muted");
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
const tmp = document.createElement("canvas"); const tx = tmp.getContext("2d");
const grain = document.createElement("canvas"); grain.width = grain.height = 160;
(() => { const g = grain.getContext("2d"), d = g.createImageData(160, 160); for (let i = 0; i < d.data.length; i += 4) { const v = Math.random() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; } g.putImageData(d, 0, 0); })();
function sizeCanvas() {
  const [w, h] = ASPECTS[E.P.aspect] || ASPECTS["16:9"];
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; tmp.width = w; tmp.height = h; }
  bgc.width = Math.round(w / 12); bgc.height = Math.round(h / 12);
}
function adjustFilter(item) {
  const f = item.filter || newFilter();
  return `brightness(${1 + f.b / 125}) contrast(${1 + f.c / 100}) saturate(${1 + f.s / 100})`;
}
function fadeAlpha(item, local, len) {
  let a = 1;
  if (item.fadeIn > 0 && local < item.fadeIn) a = clamp(local / item.fadeIn, 0, 1);
  if (item.fadeOut > 0 && len - local < item.fadeOut) a = Math.min(a, clamp((len - local) / item.fadeOut, 0, 1));
  return a;
}
/* one main-track clip, optionally clipped / moved for a transition */
function drawMain(c, el, o) {
  const W = cv.width, H = cv.height, vw = el.videoWidth;
  if (!vw || el.readyState < 2) return;
  o = o || {};
  const vh = el.videoHeight, local = E.t - c.start, tf = c.transform || DEF_TF();
  cx.save();
  if (o.clip) {
    cx.beginPath();
    if (o.clip.circle) cx.arc(W / 2, H / 2, o.clip.r, 0, Math.PI * 2); else cx.rect(o.clip.x, o.clip.y, o.clip.w, o.clip.h);
    cx.clip();
  }
  cx.globalAlpha = (o.a == null ? 1 : o.a) * fadeAlpha(c, local, c.len);
  if (o.dx || o.dy) cx.translate(o.dx || 0, o.dy || 0);
  if (o.sc && o.sc !== 1) { cx.translate(W / 2, H / 2); cx.scale(o.sc, o.sc); cx.translate(-W / 2, -H / 2); }
  const flt = adjustFilter(c);
  if (E.P.fit === "blur") {
    const s = Math.max(bgc.width / vw, bgc.height / vh);
    bgx.filter = "blur(2px)";
    bgx.drawImage(el, (bgc.width - vw * s) / 2, (bgc.height - vh * s) / 2, vw * s, vh * s);
    cx.imageSmoothingQuality = "high"; cx.filter = flt;
    cx.drawImage(bgc, 0, 0, W, H);
  }
  cx.globalAlpha *= clamp(tf.opacity / 100, 0, 1);
  cx.translate(W / 2 + W * tf.x / 100, H / 2 + H * tf.y / 100);
  if (tf.rot) cx.rotate(tf.rot * Math.PI / 180);
  if (tf.scale !== 100) cx.scale(tf.scale / 100, tf.scale / 100);
  cx.translate(-W / 2, -H / 2);
  cx.filter = flt;
  const s = E.P.fit === "fill" ? Math.max(W / vw, H / vh) : Math.min(W / vw, H / vh);
  cx.drawImage(el, (W - vw * s) / 2, (H - vh * s) / 2, vw * s, vh * s);
  cx.filter = "none";
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
  const items = [...E.P.overlay].sort((a, b) => (a.lane || 0) - (b.lane || 0));
  for (const o of items) {
    o._bb = null;
    if (E.t < o.start || E.t >= o.start + o.len || laneFlag("o" + o.lane, "hidden")) continue;
    const el = E.ov[o.id]; if (!el || !el.videoWidth || el.readyState < 2) continue;
    const w = W * o.scale / 100, h = w * el.videoHeight / el.videoWidth, x = W * o.x / 100, y = H * o.y / 100;
    cx.save();
    cx.globalAlpha = o.opacity * fadeAlpha(o, E.t - o.start, o.len);
    cx.filter = adjustFilter(o);
    cx.translate(x, y); if (o.rot) cx.rotate(o.rot * Math.PI / 180);
    cx.drawImage(el, -w / 2, -h / 2, w, h);
    cx.restore();
    o._bb = { x: x - w / 2, y: y - h / 2, w, h };
    if (E.sel && E.sel.kind === "o" && E.sel.id === o.id && !E.playing) {
      cx.save(); cx.translate(x, y); if (o.rot) cx.rotate(o.rot * Math.PI / 180);
      cx.setLineDash([6, 4]); cx.lineWidth = 2; cx.strokeStyle = "#3d8bff"; cx.strokeRect(-w / 2, -h / 2, w, h); cx.restore();
    }
  }
}
/* looks and effects only touch the stretch of the timeline they sit on */
function applyTimed() {
  const W = cv.width, H = cv.height;
  const active = (it, kind) => E.t >= it.start && E.t < it.start + it.dur && !laneFlag(kind + (it.lane || 0), "hidden");
  const ordered = [...E.P.look.filter((x) => active(x, "l")).map((x) => ["l", x]), ...E.P.effect.filter((x) => active(x, "e")).map((x) => ["e", x])];
  if (E.pv) { const el = ((performance.now() - E.pv.t0) / 1000) % 1.6; ordered.push([E.pv.kind, { type: E.pv.type, intensity: 100, start: E.t - el, dur: 1e9, lane: 0 }]); }
  for (const [kind, it] of ordered) {
    const inten = clamp(it.intensity / 100, 0, 1), r = E.t - it.start;
    tx.clearRect(0, 0, W, H); tx.drawImage(cv, 0, 0);
    if (kind === "l") {
      const l = lookOf(it.type); if (!l) continue;
      cx.save(); cx.globalAlpha = inten; cx.filter = l[3]; cx.drawImage(tmp, 0, 0); cx.restore();
      continue;
    }
    switch (it.type) {
      case "flash": cx.fillStyle = `rgba(255,255,255,${clamp(0.9 * inten * Math.exp(-6 * Math.max(0, r)), 0, 1)})`; cx.fillRect(0, 0, W, H); break;
      case "blur": cx.save(); cx.filter = `blur(${Math.max(1, 20 * inten * W / 960)}px)`; cx.drawImage(tmp, 0, 0); cx.restore(); break;
      case "vignette": { const g = cx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.3, W / 2, H / 2, Math.max(W, H) * 0.75); g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,.65)"); cx.fillStyle = g; cx.fillRect(0, 0, W, H); break; }
      case "grain": cx.save(); cx.globalAlpha = 0.1 + 0.15 * inten; cx.globalCompositeOperation = "overlay";
        for (let gx = -Math.random() * 120; gx < W; gx += 160) for (let gy = -Math.random() * 120; gy < H; gy += 160) cx.drawImage(grain, gx, gy);
        cx.restore(); break;
      case "bars": cx.fillStyle = "#000"; cx.fillRect(0, 0, W, H * 0.11); cx.fillRect(0, H * 0.89, W, H * 0.11); break;
      case "mirror": cx.save(); cx.translate(W, 0); cx.scale(-1, 1); cx.drawImage(tmp, 0, 0); cx.restore(); break;
      case "negative": cx.save(); cx.filter = "invert(1)"; cx.drawImage(tmp, 0, 0); cx.restore(); break;
      case "glitch": {
        const d = 16 * inten * W / 960;
        cx.save(); cx.globalCompositeOperation = "lighter"; cx.globalAlpha = 0.45;
        cx.filter = "sepia(1) saturate(6) hue-rotate(-50deg)"; cx.drawImage(tmp, -d, 0);
        cx.filter = "sepia(1) saturate(6) hue-rotate(150deg)"; cx.drawImage(tmp, d, 0); cx.restore();
        for (let k = 0; k < 3; k++) { const y = Math.random() * H, h = H * (0.02 + Math.random() * 0.05), dx = (Math.random() - 0.5) * 60 * inten; cx.drawImage(tmp, 0, y, W, h, dx, y, W, h); }
        break;
      }
      case "vhs": {
        const d = 3 * W / 960;
        cx.save(); cx.globalCompositeOperation = "lighter"; cx.globalAlpha = 0.3; cx.filter = "sepia(1) saturate(6) hue-rotate(-50deg)"; cx.drawImage(tmp, -d, 0);
        cx.filter = "sepia(1) saturate(6) hue-rotate(150deg)"; cx.drawImage(tmp, d, 0); cx.restore();
        cx.save(); cx.globalAlpha = 0.07; cx.fillStyle = "#000"; for (let y = 0; y < H; y += 4) cx.fillRect(0, y, W, 1.5); cx.restore();
        cx.save(); cx.globalAlpha = 0.12 * inten + 0.05; cx.globalCompositeOperation = "overlay"; cx.drawImage(grain, Math.random() * -100, Math.random() * -100, W + 100, H + 100); cx.restore(); break;
      }
      case "pixel": {
        const n = Math.max(6, 8 + 26 * inten), sw = Math.max(1, Math.round(W / n)), sh = Math.max(1, Math.round(H / n));
        bgc.width = sw; bgc.height = sh; bgx.imageSmoothingEnabled = false; bgx.drawImage(tmp, 0, 0, sw, sh);
        cx.save(); cx.imageSmoothingEnabled = false; cx.drawImage(bgc, 0, 0, sw, sh, 0, 0, W, H); cx.restore(); break;
      }
      case "shake": {
        const k = 1 / (1 - 0.09 * inten), dx = W * 0.035 * inten * Math.sin(E.t * 45), dy = H * 0.035 * inten * Math.cos(E.t * 51);
        cx.save(); cx.fillStyle = "#000"; cx.fillRect(0, 0, W, H); cx.translate(W / 2 + dx, H / 2 + dy); cx.scale(k, k); cx.translate(-W / 2, -H / 2); cx.drawImage(tmp, 0, 0); cx.restore(); break;
      }
      case "zoom": {
        const s = 1 + 0.16 * inten * Math.abs(Math.sin(r * 6));
        cx.save(); cx.translate(W / 2, H / 2); cx.scale(s, s); cx.translate(-W / 2, -H / 2); cx.drawImage(tmp, 0, 0); cx.restore(); break;
      }
      case "pulse": {
        const a = Math.abs(Math.sin(r * 6));
        cx.save(); cx.filter = `saturate(${1 + 0.9 * inten * a}) brightness(${1 + 0.35 * inten * a})`; cx.drawImage(tmp, 0, 0); cx.restore(); break;
      }
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
  if (E.P.video.length && !laneFlag("main", "hidden")) {
    const L = locate(E.t), c = E.P.video[L.i];
    if (L.j >= 0 && E.outI === L.j) drawTransition(E.P.video[L.j], V[1 - E.cur], c, V[E.cur], L.p, c.transition.type);
    else drawMain(c, V[E.cur]);
  }
  drawOverlays();
  applyTimed();
  for (const t of E.P.text) {
    const on = E.t >= t.start && E.t < t.start + t.dur && !laneFlag("t" + t.lane, "hidden");
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
  if (it && ["t", "o", "a", "e", "l"].includes(k)) {
    const len = itemSpan(k, it);
    if (t > it.start + 0.2 && t < it.start + len - 0.2) {
      const b = JSON.parse(JSON.stringify(it)); b.id = uid(); b.start = t;
      if (k === "t" || k === "e" || k === "l") { b.dur = it.start + it.dur - t; it.dur = t - it.start; }
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
  if (E.sel.kind === "j") { const c = selItem(); if (c) c.transition = { type: "none", dur: 0.6 }; E.sel = null; commit(); seek(E.t); return; }
  const list = listOf(E.sel.kind), i = list.findIndex((x) => x.id === E.sel.id);
  if (i < 0) return;
  list.splice(i, 1); E.sel = null; commit();
  E.t = clamp(E.t, 0, E.total); seek(E.t);
}
function duplicateSel() {
  const it = selItem(); if (!it || E.sel.kind === "j") return;
  const k = E.sel.kind, b = JSON.parse(JSON.stringify(it)); b.id = uid();
  if (k === "v") { E.P.video.splice(E.P.video.indexOf(it) + 1, 0, b); b.transition = { type: "none", dur: 0.6 }; }
  else { b.start = it.start + itemSpan(k, it); b.lane = pickLane(k, b.start, b.start + itemSpan(k, it)); if (b.lane == null) return; listOf(k).push(b); }
  E.sel = { kind: k, id: b.id }; commit();
}
async function addClip(name, at) {
  try {
    const m = await loadMeta(name);
    const c = newClip(name, 0, m.dur);
    if (at != null && at >= 0 && at <= E.P.video.length) E.P.video.splice(at, 0, c); else E.P.video.push(c);
    E.sel = { kind: "v", id: c.id };
    layout(); commit(); E.t = c.start; seek(E.t); scrollToPlayhead();
  } catch (e) { toast({ kind: "error", message: e.message }); }
}
async function addOverlay(name, start, lane) {
  if (!E.P.video.length) { toast({ kind: "error", message: "Add a main clip first, then layer this on top." }); return; }
  if (!(E.P.tracks.o || 0)) { pickLane("o", 0, 1); return; }
  try {
    const m = await loadMeta(name);
    const s0 = start != null ? start : E.t, o = newOverlay(name, 0, Math.min(m.dur, Math.max(1, E.total - s0)), s0);
    o.len = o.out - o.in;
    const l = pickLane("o", o.start, o.start + o.len, lane); if (l == null) return;
    o.lane = l;
    const [W, H] = ASPECTS[E.P.aspect] || ASPECTS["16:9"];
    o.scale = m.w && m.h ? clamp(Math.round(Math.min(100, 100 * H * m.w / (m.h * W))), 8, 100) : 100;     // full screen unless you change it
    E.P.overlay.push(o); E.sel = { kind: "o", id: o.id }; E.itab = "video"; commit();
  } catch (e) { toast({ kind: "error", message: e.message }); }
}
function addText(preset, start, lane) {
  const s0 = start != null ? start : E.t;
  const t = Object.assign({ id: uid(), text: "Your text", start: s0, dur: Math.min(3, Math.max(1, E.total - s0 || 3)), lane: 0, x: 50, y: 80, size: 7, color: "#ffffff", font: "segoe", bold: true, outline: true, box: false }, preset || {});
  const l = pickLane("t", t.start, t.start + t.dur, lane); if (l == null) return;
  t.lane = l;
  E.P.text.push(t); E.sel = { kind: "t", id: t.id }; commit();
}
function addTimed(kind, type, start, lane) {
  if (!E.P.video.length) { toast({ kind: "error", message: "Add a clip first, then put effects on it." }); return; }
  const s0 = start != null ? start : E.t, dur = Math.min(3, Math.max(0.8, E.total - s0));
  const it = { id: uid(), type, start: s0, dur, intensity: 100, lane: 0 };
  const l = pickLane(kind, it.start, it.start + it.dur, lane); if (l == null) return;
  it.lane = l; E.pv = null; phLabel();
  listOf(kind).push(it); E.sel = { kind, id: it.id }; commit();
}
async function addAudio(src, label, start, lane) {
  if (!(E.P.tracks.a || 0)) { pickLane("a", 0, 1); return; }
  if (label) E.meta[src] = { ...(E.meta[src] || {}), label };
  const m = await loadMeta(src);
  const s0 = start != null ? start : E.t, room = E.total > 0 ? Math.max(1, E.total - s0) : m.dur;
  const a = { id: uid(), src, in: 0, out: Math.min(m.dur, room), start: s0, lane: 0, volume: 0.8, fadeIn: 0, fadeOut: 0 };
  const l = pickLane("a", a.start, a.start + (a.out - a.in), lane); if (l == null) return;
  a.lane = l;
  E.P.audio.push(a); E.sel = { kind: "a", id: a.id }; commit();
}
async function addAudioFile() {
  const r = await api("/api/editor/pick-audio");
  if (!r.ok) return;
  try { await addAudio(r.id, r.name); } catch (e) { toast({ kind: "error", message: e.message }); }
}
/* a transition joins a clip to the one before it */
function joinTarget() {
  const v = E.P.video;
  if (E.sel && (E.sel.kind === "j" || E.sel.kind === "v")) { let i = v.findIndex((c) => c.id === E.sel.id); if (i === 0) i = 1; return v[i] || null; }
  let i = locate(E.t).i; if (i === 0) i = 1;
  return v[i] || null;
}
function applyTransition(type, clipId) {
  if (E.P.video.length < 2) { toast({ kind: "error", message: "A transition goes between two clips. Add another clip to the main track first." }); return; }
  const c = clipId ? E.P.video.find((x) => x.id === clipId) : joinTarget();
  if (!c || E.P.video.indexOf(c) === 0) { toast({ kind: "error", message: "Pick the join between two clips." }); return; }
  c.transition = { type, dur: (c.transition && c.transition.dur) || 0.6 };
  E.sel = { kind: "j", id: c.id }; E.itab = "video";
  commit();
  seek(Math.max(0, c.start - 0.3));
  if (!E.playing) setTimeout(play, 500);
}

/* ------------------------------------------------------------ UI: skeleton */
function build() {
  if (E.built) return;
  E.built = true;
  const root = document.createElement("div"); root.id = "ed";
  root.innerHTML = `
    <div class="ed-top pywebview-drag-region">
      <button class="ed-btn" id="ed-back" title="Your edit is kept. Open Editor from the sidebar to come back.">${ICON.back}Home</button>
      <span class="ed-saved" id="ed-saved"></span>
      <input class="title" id="ed-title" spellcheck="false" aria-label="Project name">
      <span class="grow"></span>
      <button class="ed-btn" id="ed-keys">${ICON.kbd}Shortcuts</button>
      <button class="ed-btn primary" id="ed-export">Export</button>
      <div class="ed-win" id="ed-win" hidden>
        <button data-w="minimize" aria-label="Minimize"><svg viewBox="0 0 16 16" stroke="currentColor"><path d="M3 8.5h10"/></svg></button>
        <button data-w="maximize" aria-label="Maximize"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><rect x="3.5" y="3.5" width="9" height="9" rx="1"/></svg></button>
        <button data-w="close" class="close" aria-label="Close"><svg viewBox="0 0 16 16" stroke="currentColor" stroke-width="1.2"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></svg></button>
      </div>
    </div>
    <div class="ed-left">
      <div class="ed-tabs" id="ed-tabs">${[["media", "Media"], ["audio", "Audio"], ["text", "Text"], ["effects", "Effects"], ["trans", "Transitions"], ["filters", "Filters"]].map(([k, n]) => `<button data-tab="${k}">${ICON[k]}${n}</button>`).join("")}</div>
      <div class="ed-body"><div class="ed-cats" id="ed-cats"></div><div class="ed-pane" id="ed-pane"></div></div>
    </div>
    <div class="ed-mid">
      <div class="ed-ph">Player</div>
      <div class="ed-stage" id="ed-stage"></div>
      <div class="ed-trans">
        <span class="ed-time" id="ed-time"></span>
        <button class="ed-btn ico mid" id="ed-play" aria-label="Play or pause"></button>
        <span class="grow"></span>
        <button class="ed-btn" id="ed-ratio">Ratio</button>
        <div class="ed-pop" id="ed-pop"></div>
      </div>
    </div>
    <div class="ed-right" id="ed-insp"></div>
    <div class="ed-tl">
      <div class="ed-tlbar">
        <button class="tb" id="ed-undo" title="Undo (Ctrl+Z)">${ICON.undo}</button><button class="tb" id="ed-redo" title="Redo (Ctrl+Y)">${ICON.redo}</button><span class="sep"></span>
        <button class="tb" id="ed-split" title="Split at the playhead (S)">${ICON.split}</button>
        <button class="tb" id="ed-dup" title="Duplicate (Ctrl+D)">${ICON.copy}</button>
        <button class="tb" id="ed-del" title="Delete (Del)">${ICON.trash}</button><span class="sep"></span>
        <span class="ed-small">Add track</span>${Object.entries(ADD_NAMES).map(([k, n]) => `<button class="ed-btn addtrack" data-addtrack="${k}" title="Add a ${n.toLowerCase()} track">+ ${n}</button>`).join("")}
        <span class="grow"></span>
        <span class="ed-small">Zoom</span><input type="range" id="ed-zoom" min="8" max="400" step="1"><button class="ed-btn" id="ed-fit" title="Fit the whole timeline">Fit</button>
      </div>
      <div class="ed-scroll" id="ed-scroll"><div class="ed-inner" id="ed-inner"></div></div>
    </div>
    <div class="ed-vids" id="ed-vids"></div>
    <div class="ed-modal" id="ed-modal"><div class="ed-card" id="ed-card"></div></div>`;
  document.body.appendChild(root);
  $("ed-stage").appendChild(cv);
  $("ed-vids").append(V[0], V[1]);
  $("ed-back").onclick = hide;
  $("ed-undo").onclick = undo; $("ed-redo").onclick = redo;
  $("ed-play").onclick = toggle;
  $("ed-split").onclick = () => splitAt(E.t);
  $("ed-dup").onclick = duplicateSel; $("ed-del").onclick = removeSel;
  $("ed-export").onclick = exportDialog;
  $("ed-keys").onclick = shortcuts;
  $("ed-title").oninput = (e) => { E.name = e.target.value; };
  $("ed-zoom").oninput = (e) => { E.zoom = Number(e.target.value); renderTimeline(); };
  $("ed-fit").onclick = fitZoom;
  root.querySelectorAll("[data-addtrack]").forEach((b) => b.onclick = () => addTrack(b.dataset.addtrack));
  $("ed-ratio").onclick = (e) => { e.stopPropagation(); $("ed-pop").innerHTML = Object.keys(ASPECTS).map((a) => `<button data-a="${a}" class="${E.P.aspect === a ? "on" : ""}">${a}${a === "16:9" ? "  (landscape)" : a === "9:16" ? "  (Shorts, Reels, TikTok)" : a === "1:1" ? "  (square)" : "  (portrait)"}</button>`).join(""); $("ed-pop").classList.toggle("on");
    $("ed-pop").querySelectorAll("button").forEach((b) => b.onclick = () => { E.P.aspect = b.dataset.a; $("ed-pop").classList.remove("on"); commit(); }); };
  root.addEventListener("click", () => $("ed-pop").classList.remove("on"));
  root.querySelectorAll("#ed-tabs button").forEach((b) => b.onclick = () => setTab(b.dataset.tab));
  root.querySelectorAll("#ed-win [data-w]").forEach((b) => b.onclick = () => api("/api/window/" + b.dataset.w));
  $("ed-scroll").addEventListener("pointerdown", scrollDown);
  $("ed-scroll").addEventListener("contextmenu", (e) => e.preventDefault());
  $("ed-inner").addEventListener("click", innerClick);
  addEventListener("pointermove", dragMove); addEventListener("pointerup", dragEnd);
  cv.addEventListener("pointerdown", canvasDown);
  addEventListener("keydown", keys);
  addEventListener("resize", () => { if (root.classList.contains("on")) renderTimeline(); });
  $("ed-scroll").addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); E.zoom = clamp(E.zoom * (e.deltaY < 0 ? 1.15 : 0.87), 8, 400); renderTimeline(); } }, { passive: false });
  setInterval(() => { if (E.savedAt && $("ed-saved")) $("ed-saved").textContent = "Kept in memory " + E.savedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }, 1000);
  // drag and drop from the library onto the timeline
  const inner = $("ed-inner");
  inner.addEventListener("dragover", (e) => { if (!E.dnd) return; const t = dropTarget(e); if (t) { e.preventDefault(); markDrop(t); } else markDrop(null); });
  inner.addEventListener("dragleave", (e) => { if (!e.relatedTarget || !inner.contains(e.relatedTarget)) markDrop(null); });
  inner.addEventListener("drop", (e) => { if (!E.dnd) return; const t = dropTarget(e); markDrop(null); if (t) { e.preventDefault(); handleDrop(t, E.dnd); } E.dnd = null; });
  addEventListener("dragend", () => { E.dnd = null; markDrop(null); });
}
function hide() { pause(); $("ed").classList.remove("on"); closeModal(); toast({ kind: "note", title: "Edit kept", message: "Open Editor in the sidebar to carry on." }); loadClips(); }

/* ------------------------------------------------------------ UI: refresh */
function refreshAll() { layout(); renderTimeline(); renderInspector(); renderLeft(); syncTransport(); }
function syncTransport() {
  $("ed-play").innerHTML = E.playing ? ICON.pause : ICON.play;
  $("ed-time").innerHTML = `${fmtFull(E.t)} <span>| ${fmtFull(E.total)}</span>`;
  $("ed-undo").disabled = E.hi <= 0; $("ed-redo").disabled = E.hi >= E.hist.length - 1;
  $("ed-ratio").textContent = `Ratio ${E.P.aspect}`;
  $("ed-split").disabled = !E.P.video.length; $("ed-del").disabled = !E.sel; $("ed-dup").disabled = !E.sel || E.sel.kind === "j";
  $("ed-win").hidden = !(typeof S !== "undefined" && S && S.native_window);
  if (document.activeElement !== $("ed-title")) $("ed-title").value = E.name;
}
function updatePlayhead() {
  const ph = $("ed-ph"); if (!ph) return;
  ph.style.left = (GUT + E.t * E.zoom) + "px";
  $("ed-time").innerHTML = `${fmtFull(E.t)} <span>| ${fmtFull(E.total)}</span>`;
  if (E.playing) { const s = $("ed-scroll"), x = E.t * E.zoom; if (x > s.scrollLeft + s.clientWidth - GUT - 40 || x < s.scrollLeft) s.scrollLeft = Math.max(0, x - 80); }
}
function fitZoom() { const s = $("ed-scroll"); E.zoom = clamp((s.clientWidth - GUT - 70) / Math.max(E.total, 8), 8, 400); renderTimeline(); s.scrollLeft = 0; }
function scrollToPlayhead() { const s = $("ed-scroll"), x = E.t * E.zoom; if (x > s.scrollLeft + s.clientWidth - GUT - 40 || x < s.scrollLeft) s.scrollLeft = Math.max(0, x - 80); }

const thumbOf = (src) => src.startsWith("ext:") ? "" : `/thumb/${encodeURIComponent(src)}`;
function renderTimeline() {
  const s = $("ed-scroll"), inner = $("ed-inner"), z = E.zoom;
  $("ed-zoom").value = z;
  const ends = [E.total, ...E.P.text.map((t) => t.start + t.dur), ...E.P.audio.map((a) => a.start + a.out - a.in), ...E.P.overlay.map((o) => o.start + o.len),
    ...E.P.effect.map((t) => t.start + t.dur), ...E.P.look.map((t) => t.start + t.dur)];
  const width = Math.max(s.clientWidth - GUT, (Math.max(...ends) + 6) * z);
  inner.style.width = (GUT + width) + "px";
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600], step = steps.find((x) => x * z >= 70) || 600;
  let ruler = "";
  for (let t = 0; t * z < width; t += step / 5) {
    const big = Math.abs(t / step - Math.round(t / step)) < 1e-6;
    ruler += big ? `<span style="left:${GUT + t * z}px">${fmt(t).replace(/\.0$/, "")}</span><i class="big" style="left:${GUT + t * z}px"></i>` : `<i style="left:${GUT + t * z}px"></i>`;
  }
  const selc = (id) => E.sel && E.sel.id === id ? " sel" : "";
  let h = `<div class="ed-ruler" id="ed-ruler" style="width:${GUT + width}px"><span class="corner"></span>${ruler}</div>`;
  const gut = (kind, lane, label) => {
    const key = kind === "v" ? "main" : kind + lane;
    const hid = laneFlag(key, "hidden"), mut = laneFlag(key, "muted");
    const eye = kind !== "a", spk = kind === "v" || kind === "o" || kind === "a";
    const rm = kind !== "v" ? `<button data-rmtrack="${kind}" data-lane="${lane}" title="Remove this track${listOf(kind).some((x) => (x.lane || 0) === lane) ? " and what's on it" : ""}">${ICON.trash}</button>` : "";
    return `<div class="ed-gut"><span>${label}</span><span class="gt">${eye ? `<button data-tg="hidden" data-key="${key}" class="${hid ? "off" : ""}" title="${hid ? "Show" : "Hide"} this track">${ICON.eye}</button>` : ""}${spk ? `<button data-tg="muted" data-key="${key}" class="${mut ? "off" : ""}" title="${mut ? "Unmute" : "Mute"} this track">${ICON.spk}</button>` : ""}${rm}</span></div>`;
  };
  const groupRows = (kind) => {
    const items = listOf(kind), n = E.P.tracks[kind] || 0;
    let out = "";
    for (let lane = n - 1; lane >= 0; lane--) {
      const label = n === 1 ? KIND_NAMES[kind] : `${KIND_NAMES[kind]} ${lane + 1}`;
      out += `<div class="ed-lane" data-kind="${kind}" data-lane="${lane}" style="width:${GUT + width}px;height:${LANE_H[kind]}px">${gut(kind, lane, label)}<div class="ed-bg"></div>`;
      for (const it of items.filter((x) => (x.lane || 0) === lane)) out += itemHtml(kind, it, z, selc(it.id));
      out += `</div>`;
    }
    return out;
  };
  h += groupRows("e");
  h += groupRows("l");
  h += groupRows("t");
  h += groupRows("o");
  h += `<div class="ed-lane" data-kind="v" data-lane="0" style="width:${GUT + width}px;height:${LANE_H.v}px">${gut("v", 0, "Main")}<div class="ed-bg"></div>`;
  if (!E.P.video.length) h += `<div class="ed-empty">Add a clip from the Media tab</div>`;
  E.P.video.forEach((c, i) => {
    h += itemHtml("v", c, z, selc(c.id));
    if (c.ov > 0) h += `<div class="ed-tmark" style="left:${GUT + c.start * z}px;width:${Math.max(10, c.ov * z)}px"></div>`;
    if (i > 0) {
      const x = GUT + (c.start + (c.ov > 0 ? c.ov / 2 : 0)) * z;
      const sj = E.sel && E.sel.kind === "j" && E.sel.id === c.id;
      h += `<button class="ed-join${c.ov > 0 ? " has" : ""}${sj ? " sel" : ""}" data-join="${c.id}" style="left:${x}px" title="${c.ov > 0 ? esc((trOf(c.transition.type) || [0, "Transition"])[1]) : "Add a transition"}">${ICON.join}</button>`;
    }
  });
  h += `</div>`;
  h += groupRows("a");
  h += `<div class="ed-playhead" id="ed-ph" style="height:100%"></div>`;
  inner.innerHTML = h;
  inner.querySelectorAll("[data-rmtrack]").forEach((b) => b.onclick = (e) => { e.stopPropagation(); removeTrack(b.dataset.rmtrack, Number(b.dataset.lane)); });
  inner.querySelectorAll("[data-tg]").forEach((b) => b.onclick = (e) => { e.stopPropagation(); const k = b.dataset.key; E.P.lanes[k] = E.P.lanes[k] || {}; E.P.lanes[k][b.dataset.tg] = !E.P.lanes[k][b.dataset.tg]; commit(); });
  updatePlayhead();
}
function itemHtml(kind, it, z, sel) {
  const off = laneFlag(kind === "v" ? "main" : kind + (it.lane || 0), "hidden") || (kind === "a" && laneFlag("a" + (it.lane || 0), "muted")) ? " off" : "";
  const left = GUT + (kind === "v" ? it.start : it.start) * z;
  const dur = kind === "v" ? it.len : itemSpan(kind, it), wid = Math.max(kind === "v" ? 6 : 8, dur * z);
  const cls = { v: "vc", o: "ov", t: "tx", e: "ef", l: "lk", a: "au" }[kind];
  let label = "", style = `left:${left}px;width:${wid}px;`;
  if (kind === "v") { label = `${esc(niceName(it.src))}<small>${fmt(it.len)}${it.speed !== 1 ? " · " + it.speed + "x" : ""}</small>`; style += `background-image:url('${thumbOf(it.src)}')`; }
  else if (kind === "o") { label = esc(niceName(it.src)); style += `background-image:url('${thumbOf(it.src)}')`; }
  else if (kind === "t") label = esc(String(it.text).split("\n")[0]);
  else if (kind === "e") label = esc((effOf(it.type) || [0, it.type])[1]);
  else if (kind === "l") label = esc((lookOf(it.type) || [0, it.type])[1]);
  else label = esc(niceName(it.src));
  return `<div class="ed-item ${cls}${sel}${off}" data-kind="${kind}" data-id="${it.id}" style="${style}"><span class="hd l" data-h="l"></span><span class="lb">${label}</span><span class="hd r" data-h="r"></span></div>`;
}

/* timeline pointer handling */
function xToT(e) { const r = $("ed-inner").getBoundingClientRect(); return clamp((e.clientX - r.left - GUT) / E.zoom, 0, 36000); }
function innerClick(e) {
  const j = e.target.closest("[data-join]");
  if (j) { E.sel = { kind: "j", id: j.dataset.join }; E.tab = "trans"; refreshAll(); const c = find("j", j.dataset.join); if (c) seek(Math.max(0, c.start - 0.3)); }
}
function scrollDown(e) {
  if (e.button === 2) {                                  // right click or right drag anywhere on the timeline moves the playhead
    if (e.target.closest(".ed-gut")) return;
    E.drag = { type: "seek" };
    if (E.playing) pause();
    E.seekReq = xToT(e);
    e.preventDefault(); return;
  }
  if (e.button !== 0 || e.target.closest("[data-tg]") || e.target.closest("[data-join]") || e.target.closest(".ed-gut")) return;
  const item = e.target.closest(".ed-item");
  if (item) {
    const kind = item.dataset.kind, id = item.dataset.id, it = find(kind, id);
    E.sel = { kind, id }; E.itab = "video"; renderInspector(); renderTimelineSel(); renderLeft();
    const h = e.target.dataset.h;
    E.drag = { type: h ? "trim" + h : "move", kind, id, x0: e.clientX, snap: JSON.parse(JSON.stringify(it)), moved: false };
    e.preventDefault(); return;
  }
  if (e.target.closest(".ed-ruler")) {                  // only the ruler moves the playhead, so grabbing a clip never does
    E.drag = { type: "seek" };
    if (E.playing) pause();
    E.seekReq = xToT(e);
    e.preventDefault();
  } else if (e.target.closest(".ed-lane")) {
    E.sel = null; renderInspector(); renderTimelineSel(); renderLeft();
  }
}
function renderTimelineSel() {
  document.querySelectorAll("#ed-inner .ed-item").forEach((el) => el.classList.toggle("sel", !!E.sel && el.dataset.id === E.sel.id));
  document.querySelectorAll("#ed-inner .ed-join").forEach((el) => el.classList.toggle("sel", !!E.sel && E.sel.kind === "j" && el.dataset.join === E.sel.id));
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
      const left = $("ed-inner").getBoundingClientRect().left + GUT;
      const grab = (d.x0 - left) / E.zoom - s.start;
      const centre = (e.clientX - left) / E.zoom - grab + it.len / 2;
      const others = E.P.video.filter((c) => c.id !== it.id);
      let idx = 0; for (const c of others) if (centre > c.start + c.len / 2) idx++;
      const cur = E.P.video.indexOf(it);
      if (idx !== cur) { E.P.video.splice(cur, 1); E.P.video.splice(idx, 0, it); }
    }
    layout();
  } else {
    const k = d.kind;
    if (k === "t" || k === "e" || k === "l") {
      if (d.type === "move") it.start = Math.max(0, s.start + dt);
      else if (d.type === "trimr") it.dur = Math.max(0.2, s.dur + dt);
      else if (d.type === "triml") { const ns = clamp(s.start + dt, 0, s.start + s.dur - 0.2); it.dur = s.dur - (ns - s.start); it.start = ns; }
    } else if (k === "o") {
      if (d.type === "move") it.start = Math.max(0, s.start + dt);
      else if (d.type === "trimr") it.out = clamp(s.out + dt * s.speed, s.in + 0.1, src);
      else if (d.type === "triml") { const ni = clamp(s.in + dt * s.speed, 0, s.out - 0.1); it.start = Math.max(0, s.start + (ni - s.in) / s.speed); it.in = ni; }
      layout();
    } else {
      if (d.type === "move") it.start = Math.max(0, s.start + dt);
      else if (d.type === "trimr") it.out = clamp(s.out + dt, s.in + 0.1, src);
      else if (d.type === "triml") { const ni = clamp(s.in + dt, 0, s.out - 0.1); it.start = Math.max(0, s.start + (ni - s.in)); it.in = ni; }
    }
    if (d.type === "move" && d.moved) {          // dragging up or down moves it to another track of the same kind
      const row = document.elementsFromPoint(e.clientX, e.clientY).find((n) => n.classList && n.classList.contains("ed-lane") && n.dataset.kind === k);
      if (row) it.lane = Number(row.dataset.lane);
    }
  }
  renderTimeline(); renderInspector(true);
}
function dragEnd() {
  const d = E.drag; if (!d) return;
  E.drag = null;
  if (d.type === "seek") return;
  const it = find(d.kind, d.id);
  if (d.moved && it) { commit(); if (d.kind === "v") seek(E.t); }
  else renderTimeline();
}
function hitTest(x, y) {
  for (const t of [...E.P.text].reverse()) { const b = t._bb; if (b && x >= b.x - 10 && x <= b.x + b.w + 10 && y >= b.y - 10 && y <= b.y + b.h + 10) return { kind: "t", it: t }; }
  const ovs = [...E.P.overlay].sort((a, b) => (b.lane || 0) - (a.lane || 0));
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

/* drag and drop from the library */
function dropTarget(e) {
  const dnd = E.dnd; if (!dnd) return null;
  const join = e.target.closest && e.target.closest("[data-join]");
  if (dnd.kind === "trans") { if (join) return { type: "join", id: join.dataset.join, el: join }; const it = e.target.closest && e.target.closest(".ed-item.vc"); return it ? { type: "join-clip", id: it.dataset.id, el: it } : null; }
  const lane = e.target.closest && e.target.closest(".ed-lane");
  if (!lane) return null;
  const want = { media: ["v", "o"], sfx: ["a"], sound: ["a"], effect: ["e"], look: ["l"], text: ["t"], clipaudio: ["a"] }[dnd.kind] || [];
  if (!want.includes(lane.dataset.kind)) return null;
  return { type: "lane", kind: lane.dataset.kind, lane: Number(lane.dataset.lane), el: lane, t: xToT(e) };
}
let dropEl = null;
function markDrop(t) { if (dropEl) dropEl.classList.remove("drop"); dropEl = t && t.el; if (dropEl) dropEl.classList.add("drop"); }
async function handleDrop(t, dnd) {
  if (t.type === "join") return applyTransition(dnd.type, t.id);
  if (t.type === "join-clip") { const i = E.P.video.findIndex((c) => c.id === t.id); return applyTransition(dnd.type, (E.P.video[i === 0 ? 1 : i] || {}).id); }
  const at = Math.max(0, t.t);
  if (dnd.kind === "media") {
    if (t.kind === "v") { let idx = E.P.video.length; for (let i = 0; i < E.P.video.length; i++) if (at < E.P.video[i].start + E.P.video[i].len / 2) { idx = i; break; } return addClip(dnd.name, idx); }
    return addOverlay(dnd.name, at, t.lane);
  }
  if (dnd.kind === "effect") return addTimed("e", dnd.type, at, t.lane);
  if (dnd.kind === "look") return addTimed("l", dnd.type, at, t.lane);
  if (dnd.kind === "text") return addText(dnd.preset, at, t.lane);
  if (dnd.kind === "sfx") { const r = await sfxId(dnd.name); if (r) addAudio(r.id, r.name, at, t.lane).catch((e) => toast({ kind: "error", message: e.message })); return; }
  if (dnd.kind === "sound") { const res = await api("/api/editor/sound-fetch", { url: dnd.url, title: dnd.title }); if (!res.ok) return toast({ kind: "error", message: res.error }); return addAudio(res.id, res.name, at, t.lane); }
  if (dnd.kind === "clipaudio") return addAudio(dnd.name, null, at, t.lane);
}
function makeDraggable(el, payload) {
  el.draggable = true;
  el.addEventListener("dragstart", (e) => { E.dnd = payload; e.dataTransfer.setData("text/plain", payload.kind); e.dataTransfer.effectAllowed = "copy"; setTimeout(renderTimeline, 0); });
  el.addEventListener("dragend", () => { E.dnd = null; markDrop(null); renderTimeline(); });
}

/* ------------------------------------------------------------ left panel */
function phLabel() {
  const ph = document.querySelector("#ed .ed-ph"); if (!ph) return;
  const l = E.pv && (E.pv.kind === "e" ? effOf : lookOf)(E.pv.type);
  ph.textContent = l ? `Previewing ${l[1]}. Drag it down onto the ${E.pv.kind === "e" ? "Effect" : "Filter"} track to add it.` : "Player";
  ph.classList.toggle("pv", !!l);
}
function setPreview(kind, type) {
  E.pv = E.pv && E.pv.kind === kind && E.pv.type === type ? null : { kind, type, t0: performance.now() };
  phLabel(); renderLeft();
}
function setTab(t) { if (E.pv) { E.pv = null; phLabel(); } E.tab = t; renderLeft(); }
const CATS = { media: [["all", "All clips"], ["rec", "Recordings"], ["edits", "Your edits"]], audio: [["sfx", "Sound effects"], ["music", "Free music"], ["online", "Free sounds"], ["files", "Your files"], ["clips", "From clips"]],
  text: [["all", "All"], ["basic", "Basic"], ["gaming", "Gaming"]], effects: EF_CATS, trans: TR_CATS, filters: LK_CATS };
const libClips = () => (typeof clips !== "undefined" ? clips : []);
function renderLeft() {
  document.querySelectorAll("#ed-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === E.tab));
  const cats = CATS[E.tab], cur = E.cats[E.tab] || cats[0][0];
  $("ed-cats").innerHTML = cats.map(([k, n]) => `<button data-c="${k}" class="${cur === k ? "on" : ""}">${n}</button>`).join("");
  $("ed-cats").querySelectorAll("button").forEach((b) => b.onclick = () => { E.cats[E.tab] = b.dataset.c; if (E.tab === "audio" && b.dataset.c === "music") E.snd.kind = "music"; if (E.tab === "audio" && b.dataset.c === "online") E.snd.kind = "sfx"; renderLeft(); });
  renderPane(cur);
}
const tileMedia = (c) => `<button class="ed-mi" data-name="${esc(c.name)}" title="Click to add. Drag to the timeline."><div class="th" style="background-image:url('/thumb/${encodeURIComponent(c.name)}')"><em class="add">+</em><em class="pip" data-pip title="Add as a layer on top">${ICON.pip}</em>${c.duration ? `<span>${clock(c.duration)}</span>` : ""}</div><b>${esc(cleanTitle(c))}</b></button>`;
function renderPane(cat) {
  const p = $("ed-pane");
  const first = E.P.video[locate(E.t).i], src = first ? thumbOf(first.src) : "";
  if (E.tab === "media") {
    let list = libClips();
    if (cat === "rec") list = list.filter((c) => /recording/i.test(c.title)); else if (cat === "edits") list = list.filter((c) => c.name.startsWith("Edits/"));
    p.innerHTML = `${(E.P.tracks.o || 0) ? "" : '<p class="ed-hint" style="margin:0 0 8px">Clips you click go on the Main track. For picture-in-picture or stacked video, press <b>+ Video</b> under the timeline, then use the layer button on a clip.</p>'}<div class="ed-media">${list.map(tileMedia).join("") || '<p class="ed-hint">Nothing here yet.</p>'}</div>
      <p class="ed-hint">Click a clip to add it, or drag it onto the timeline. The layer button puts it on top as a picture-in-picture.</p>`;
    p.querySelectorAll(".ed-mi").forEach((b) => { b.onclick = (ev) => { if (ev.target.closest("[data-pip]")) addOverlay(b.dataset.name); else addClip(b.dataset.name); }; makeDraggable(b, { kind: "media", name: b.dataset.name }); });
  } else if (E.tab === "text") {
    p.innerHTML = `${trackHint("t")}<div class="ed-tpl">${TEXT_PRESETS.filter((x) => cat === "all" || x[3] === cat).map(([id, n, d]) => `<button data-p="${id}"><b>${n}</b><small>${d}</small></button>`).join("")}</div>
      <p class="ed-hint">Click to add at the playhead, or drag onto the Text track. Drag the text in the preview to place it.</p>`;
    p.querySelectorAll("[data-p]").forEach((b) => { const pr = TEXT_PRESETS.find((x) => x[0] === b.dataset.p)[4]; b.onclick = () => addText({ ...pr }); makeDraggable(b, { kind: "text", preset: { ...pr } }); });
  } else if (E.tab === "effects") {
    const pv = E.pv && E.pv.kind === "e" ? E.pv.type : null;
    p.innerHTML = `${trackHint("e")}<div class="ed-media">${EFFECTS.filter((x) => cat === "all" || x[2] === cat).map(([id, n, , g]) => `<button class="ed-fx${pv === id ? " on" : ""}" data-fx="${id}"><div class="th" style="background-image:url('${src}')"><em class="add" data-add title="Add at the playhead">+</em><i>${g}</i></div><b>${n}</b></button>`).join("")}</div>
      <p class="ed-hint">Click an effect to preview it on the player. Drag it down onto an Effect track to add it, then drag the bar left or right to move it, or pull its edges to set how long it lasts.</p>`;
    p.querySelectorAll("[data-fx]").forEach((b) => { b.onclick = (ev) => { if (ev.target.closest("[data-add]")) addTimed("e", b.dataset.fx); else setPreview("e", b.dataset.fx); }; makeDraggable(b, { kind: "effect", type: b.dataset.fx }); });
  } else if (E.tab === "filters") {
    const pv = E.pv && E.pv.kind === "l" ? E.pv.type : null;
    p.innerHTML = `${trackHint("l")}<div class="ed-media">${LOOKS.filter((x) => cat === "all" || x[2] === cat).map(([id, n, , css]) => `<button class="ed-fx${pv === id ? " on" : ""}" data-lk="${id}"><div class="th" style="background-image:url('${src}');filter:${css}"><em class="add" data-add title="Add at the playhead">+</em></div><b>${n}</b></button>`).join("")}</div>
      <p class="ed-hint">Click a filter to preview it on the player. Drag it down onto a Filter track to add it, then drag the bar left or right to move it, or pull its edges to set how long it lasts.</p>`;
    p.querySelectorAll("[data-lk]").forEach((b) => { b.onclick = (ev) => { if (ev.target.closest("[data-add]")) addTimed("l", b.dataset.lk); else setPreview("l", b.dataset.lk); }; makeDraggable(b, { kind: "look", type: b.dataset.lk }); });
  } else if (E.tab === "trans") {
    const c = E.sel && (E.sel.kind === "j" || E.sel.kind === "v") ? find("v", E.sel.id) : null;
    const cur = c && c.transition ? c.transition.type : "none";
    const two = E.P.video.length > 1;
    p.innerHTML = `${two ? "" : '<p class="ed-hint" style="margin:0 0 10px;color:#f2b84b">Add a second clip to the main track first. A transition goes between two clips.</p>'}<div class="ed-trgrid">${TRANSITIONS.filter((x) => cat === "all" || x[2] === cat).map(([id, n]) => `<button class="ed-tr${cur === id ? " on" : ""}" data-tr="${id}"><span class="tp tp-${id}"></span><b>${n}</b></button>`).join("")}</div>
      <p class="ed-hint">Click the small button between two clips on the timeline, then pick a transition. Or drag one onto it. The two clips overlap by the transition's length.</p>`;
    p.querySelectorAll("[data-tr]").forEach((b) => { b.onclick = () => applyTransition(b.dataset.tr); makeDraggable(b, { kind: "trans", type: b.dataset.tr }); });
  } else renderAudioPane(p, cat);
}
function renderAudioPane(p, cat) {
  const s = E.snd;
  if (cat === "sfx") {
    p.innerHTML = `${trackHint("a")}<div class="ed-sfx">${SFX.map(([id, name]) => `<div class="ed-snd" data-sfx="${id}"><button class="pl" data-pv title="Preview">▶</button><b>${name}</b><button class="ad" data-add title="Add to the timeline">+</button></div>`).join("")}</div>
      <p class="ed-hint">Built in and free. Click + to add at the playhead, or drag onto an Audio track.</p>`;
    p.querySelectorAll("[data-sfx]").forEach((row) => {
      row.querySelector("[data-add]").onclick = async () => { const id = await sfxId(row.dataset.sfx); if (id) addAudio(id.id, id.name).catch((e) => toast({ kind: "error", message: e.message })); };
      row.querySelector("[data-pv]").onclick = async () => { const id = await sfxId(row.dataset.sfx); if (id) previewUrl("/ext/" + id.id.slice(4), -1); };
      makeDraggable(row, { kind: "sfx", name: row.dataset.sfx });
    });
  } else if (cat === "music" || cat === "online") {
    const results = s.loading ? '<p class="ed-hint">Searching…</p>' : s.error ? `<p class="ed-err">${esc(s.error)}</p>`
      : (s.results.map((r, i) => `<div class="ed-snd" data-i="${i}"><button class="pl${s.playing === i ? " on" : ""}" data-rpv title="Preview">${s.playing === i ? "■" : "▶"}</button><b title="${esc(r.title)}">${esc(r.title)}<small>${r.duration >= 60 ? Math.floor(r.duration / 60) + "m " + Math.round(r.duration % 60) + "s" : r.duration + "s"} · ${esc(r.creator || r.source)}</small></b><button class="ad" data-radd title="Add to the timeline">+</button></div>`).join("")
        || (s.searched ? '<p class="ed-hint">Nothing found. Try another word.</p>' : ""));
    p.innerHTML = `<div class="ed-search"><input id="ed-q" type="text" placeholder="${cat === "music" ? "Search music, like epic, chill, lofi" : "Search sounds, like whoosh, crowd, laser"}" value="${esc(s.q)}" spellcheck="false">
      <div style="margin:8px 0"><button class="ed-btn primary" id="ed-qgo">Search</button></div></div>
      <div id="ed-results">${results}${s.more && !s.loading ? '<button class="ed-btn" id="ed-more" style="margin-top:8px;width:100%;justify-content:center">Load more</button>' : ""}</div>
      <p class="ed-hint">Free to use with no credit needed (public domain or CC0), searched through Openverse.</p>`;
    const q = $("ed-q");
    q.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") searchSounds(true); });
    q.addEventListener("input", () => { s.q = q.value; });
    $("ed-qgo").onclick = () => searchSounds(true);
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
      makeDraggable(row, { kind: "sound", url: r.url, title: r.title });
    });
  } else if (cat === "files") {
    p.innerHTML = `<button class="ed-btn primary" id="ed-addaudio">Add an audio file…</button>
      <p class="ed-hint">MP3, WAV, M4A, OGG or any video file. It plays alongside your clips. You can move it, trim it and set its volume.</p>`;
    $("ed-addaudio").onclick = addAudioFile;
  } else {
    p.innerHTML = `<div class="ed-media">${libClips().map((c) => `<button class="ed-mi" data-name="${esc(c.name)}" title="Use this clip's sound"><div class="th" style="background-image:url('/thumb/${encodeURIComponent(c.name)}')"><em class="add">♪</em></div><b>${esc(cleanTitle(c))}</b></button>`).join("")}</div>`;
    p.querySelectorAll(".ed-mi").forEach((b) => { b.onclick = () => addAudio(b.dataset.name).catch((e) => toast({ kind: "error", message: e.message })); makeDraggable(b, { kind: "clipaudio", name: b.dataset.name }); });
  }
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
  if (idx >= 0 && was === idx) { renderLeft(); return; }
  const a = new Audio(url); a.volume = 0.8; E.prev = a;
  a.onended = () => { E.snd.playing = -1; if (E.tab === "audio") renderLeft(); };
  a.play().catch(() => {});
  E.snd.playing = idx;
  if (E.tab === "audio") renderLeft();
}
async function searchSounds(fresh) {
  const s = E.snd;
  if (fresh) { s.page = 1; s.results = []; } else s.page += 1;
  s.loading = true; s.error = ""; s.searched = true; renderLeft();
  try {
    const r = await get(`/api/editor/sounds?q=${encodeURIComponent(s.q)}&kind=${s.kind}&page=${s.page}`);
    if (!r.ok) s.error = r.error; else { s.results = s.results.concat(r.results); s.more = r.more; }
  } catch (e) { s.error = "Couldn't reach the free sound library."; }
  s.loading = false; renderLeft();
}

/* ------------------------------------------------------------ inspector */
function row(label, key, min, max, step, val, out) {
  return `<div class="ed-row"><label>${label}</label><input type="range" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${val}"><output>${out}</output></div>`;
}
const ITABS = { v: [["video", "Video"], ["audio", "Audio"], ["speed", "Speed"], ["anim", "Animation"], ["adjust", "Adjustment"]], o: [["video", "Video"], ["audio", "Audio"], ["speed", "Speed"], ["anim", "Animation"], ["adjust", "Adjustment"]] };
function renderInspector(light) {
  const el = $("ed-insp");
  const it = selItem();
  const sig = (E.sel ? E.sel.kind + E.sel.id : "none") + E.itab;
  if (light && el.dataset.sel === sig) { updateInspectorValues(); return; }
  el.dataset.sel = sig;
  if (!it) {
    el.innerHTML = `<h3>Project</h3>
      <div class="ed-field"><label>Ratio</label><div class="ed-chips">${Object.keys(ASPECTS).map((a) => `<button class="ed-chip${E.P.aspect === a ? " on" : ""}" data-a="${a}">${a}</button>`).join("")}</div></div>
      <div class="ed-field"><label>When a clip doesn't match the ratio</label><div class="ed-chips">${[["fit", "Fit"], ["fill", "Fill"], ["blur", "Fit + blur"]].map(([k, l]) => `<button class="ed-chip${E.P.fit === k ? " on" : ""}" data-f="${k}">${l}</button>`).join("")}</div></div>
      <p class="ed-hint" style="margin-top:14px">Pick a clip, layer, text, effect or sound on the timeline to edit it. Use <b>9:16</b> for Shorts, Reels and TikTok.</p>`;
    el.querySelectorAll("[data-a]").forEach((b) => b.onclick = () => { E.P.aspect = b.dataset.a; commit(); });
    el.querySelectorAll("[data-f]").forEach((b) => b.onclick = () => { E.P.fit = b.dataset.f; commit(); });
    return;
  }
  const k = E.sel.kind;
  const tabs = (list) => `<div class="ed-itabs">${list.map(([id, n]) => `<button data-it="${id}" class="${E.itab === id ? "on" : ""}">${n}</button>`).join("")}</div>`;
  const speed = (it) => `<h4>Speed</h4><div class="ed-chips">${[0.25, 0.5, 1, 1.5, 2, 4].map((s) => `<button class="ed-chip${it.speed === s ? " on" : ""}" data-s="${s}">${s}x</button>`).join("")}</div>${row("Custom", "speed", 0.25, 4, 0.05, it.speed, it.speed.toFixed(2) + "x")}`;
  let html = "";
  if (k === "v" || k === "o") {
    const f = it.filter;
    html = tabs(ITABS[k]);
    if (E.itab === "video") {
      if (k === "v") { const tf = it.transform; html += `<h4>Transform</h4>${row("Scale", "transform.scale", 10, 300, 1, tf.scale, Math.round(tf.scale) + "%")}${row("Position X", "transform.x", -100, 100, 1, tf.x, Math.round(tf.x))}${row("Position Y", "transform.y", -100, 100, 1, tf.y, Math.round(tf.y))}${row("Rotate", "transform.rot", -180, 180, 1, tf.rot, Math.round(tf.rot) + "°")}<h4>Blend</h4>${row("Opacity", "transform.opacity", 0, 100, 1, tf.opacity, Math.round(tf.opacity) + "%")}<div class="ed-actions"><button class="ed-btn" id="i-tf">Reset</button><button class="ed-btn" id="i-split">${ICON.split}Split here</button></div>`; }
      else html += `<h4>Transform</h4>${row("Size", "scale", 8, 100, 1, it.scale, Math.round(it.scale) + "%")}${row("Position X", "x", 0, 100, 1, it.x, Math.round(it.x) + "%")}${row("Position Y", "y", 0, 100, 1, it.y, Math.round(it.y) + "%")}${row("Rotate", "rot", -180, 180, 1, it.rot, Math.round(it.rot) + "°")}<h4>Blend</h4>${row("Opacity", "opacity", 0.1, 1, 0.05, it.opacity, Math.round(it.opacity * 100) + "%")}<p class="ed-hint">You can also drag the layer in the preview.</p><div class="ed-2" style="margin-top:12px"><div class="ed-field"><label>Starts at (s)</label><input type="number" step="0.1" min="0" data-k="start" value="${it.start.toFixed(1)}"></div><div class="ed-field"><label>Plays from (s)</label><input type="number" step="0.1" min="0" data-k="in" value="${it.in.toFixed(1)}"></div></div>`;
    } else if (E.itab === "audio") html += `<h4>Volume</h4>${row("Volume", "volume", 0, 2, 0.05, it.volume, Math.round(it.volume * 100) + "%")}<label class="ed-check"><input type="checkbox" data-k="mute" ${it.mute ? "checked" : ""}> Mute this clip</label>`;
    else if (E.itab === "speed") html += speed(it);
    else if (E.itab === "anim") html += `<h4>Fades</h4>${row("Fade in", "fadeIn", 0, 3, 0.1, it.fadeIn, it.fadeIn.toFixed(1) + "s")}${row("Fade out", "fadeOut", 0, 3, 0.1, it.fadeOut, it.fadeOut.toFixed(1) + "s")}<p class="ed-hint">Fade in and out from black, and fade the sound with it. Use the Transitions tab to blend between two clips.</p>`;
    else html += `<h4>Basic</h4>${row("Brightness", "filter.b", -100, 100, 1, f.b, f.b)}${row("Contrast", "filter.c", -100, 100, 1, f.c, f.c)}${row("Saturation", "filter.s", -100, 100, 1, f.s, f.s)}<div class="ed-actions"><button class="ed-btn" id="i-reset">Reset</button></div><p class="ed-hint">Want a look over a stretch of the video instead? Add a filter from the Filters tab.</p>`;
  } else if (k === "j") {
    const tr = it.transition || { type: "none", dur: 0.6 };
    html = `<h3>Transition</h3><p class="ed-hint" style="margin:0 0 8px">${tr.type === "none" ? "No transition between these clips yet. Pick one from the Transitions tab." : esc((trOf(tr.type) || [0, tr.type])[1])}</p>
      ${tr.type !== "none" ? row("Duration", "transition.dur", 0.2, 2.5, 0.1, tr.dur, tr.dur.toFixed(1) + "s") : ""}
      <div class="ed-chips">${TRANSITIONS.map(([id, n]) => `<button class="ed-chip${tr.type === id ? " on" : ""}" data-t="${id}">${n}</button>`).join("")}</div>
      <div class="ed-actions"><button class="ed-btn" id="i-applyall">Apply to all joins</button><button class="ed-btn danger" id="i-rmtr">Remove</button></div>`;
  } else if (k === "e" || k === "l") {
    const list = k === "e" ? EFFECTS : LOOKS;
    html = `<h3>${k === "e" ? "Effect" : "Filter"}</h3>${row("Intensity", "intensity", 0, 100, 1, it.intensity, Math.round(it.intensity))}
      <div class="ed-chips">${list.map(([id, n]) => `<button class="ed-chip${it.type === id ? " on" : ""}" data-ty="${id}">${n}</button>`).join("")}</div>
      <div class="ed-2"><div class="ed-field"><label>Starts at (s)</label><input type="number" step="0.1" min="0" data-k="start" value="${it.start.toFixed(1)}"></div>
      <div class="ed-field"><label>Lasts (s)</label><input type="number" step="0.1" min="0.2" data-k="dur" value="${it.dur.toFixed(1)}"></div></div>
      <p class="ed-hint">It only changes the part of the video under this bar. Drag the bar's edges to make it shorter or longer.</p>`;
  } else if (k === "t") {
    html = `<h3>Text</h3>
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
    html = `<h3>${esc(niceName(it.src))}</h3>
      ${row("Volume", "volume", 0, 2, 0.05, it.volume, Math.round(it.volume * 100) + "%")}
      ${row("Fade in", "fadeIn", 0, 5, 0.1, it.fadeIn, it.fadeIn.toFixed(1) + "s")}${row("Fade out", "fadeOut", 0, 5, 0.1, it.fadeOut, it.fadeOut.toFixed(1) + "s")}
      <div class="ed-2"><div class="ed-field"><label>Starts at (s)</label><input type="number" step="0.1" min="0" data-k="start" value="${it.start.toFixed(1)}"></div>
      <div class="ed-field"><label>Plays from (s)</label><input type="number" step="0.1" min="0" data-k="in" value="${it.in.toFixed(1)}"></div></div>`;
  }
  el.innerHTML = html;
  el.querySelectorAll("[data-it]").forEach((b) => b.onclick = () => { E.itab = b.dataset.it; renderInspector(); });
  el.querySelectorAll("[data-k]").forEach(bindField);
  el.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => { it.speed = Number(b.dataset.s); commit(); seek(E.t); });
  el.querySelectorAll("[data-ty]").forEach((b) => b.onclick = () => { it.type = b.dataset.ty; commit(); });
  el.querySelectorAll("[data-t]").forEach((b) => b.onclick = () => { it.transition = { type: b.dataset.t, dur: (it.transition && it.transition.dur) || 0.6 }; commit(); seek(Math.max(0, it.start - 0.3)); });
  const q = (id) => $(id);
  if (q("i-reset")) q("i-reset").onclick = () => { it.filter = newFilter(); commit(); };
  if (q("i-tf")) q("i-tf").onclick = () => { it.transform = DEF_TF(); commit(); };
  if (q("i-split")) q("i-split").onclick = () => splitAt(E.t);
  if (q("i-rmtr")) q("i-rmtr").onclick = () => { it.transition = { type: "none", dur: 0.6 }; commit(); seek(E.t); };
  if (q("i-applyall")) q("i-applyall").onclick = () => { const tr = it.transition; E.P.video.forEach((c, i) => { if (i > 0) c.transition = { ...tr }; }); commit(); seek(E.t); };
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
    if (out) out.textContent = key === "speed" ? Number(v).toFixed(2) + "x" : ["volume", "opacity"].includes(key) ? Math.round(v * 100) + "%" : key === "transform.opacity" || key === "transform.scale" || key === "intensity" ? Math.round(v) + (key === "intensity" ? "" : "%") : ["fadeIn", "fadeOut", "transition.dur"].includes(key) ? Number(v).toFixed(1) + "s" : ["x", "y", "scale"].includes(key) ? Math.round(v) + "%" : key.endsWith("rot") ? Math.round(v) + "°" : v;
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

/* ------------------------------------------------------------ export + dialogs */
function modal(html) { $("ed-card").innerHTML = html; $("ed-modal").classList.add("on"); }
function closeModal() { $("ed-modal").classList.remove("on"); }
function shortcuts() {
  modal(`<h3>Keyboard shortcuts</h3><div class="ed-keys"><kbd>Space</kbd>Play or pause<kbd>S</kbd>Split at the playhead<kbd>Del</kbd>Delete the selected item<kbd>Ctrl + Z</kbd>Undo<kbd>Ctrl + Y</kbd>Redo<kbd>Ctrl + D</kbd>Duplicate
    <kbd>← →</kbd>Step one frame<kbd>Shift + ← →</kbd>Step one second<kbd>Home / End</kbd>Jump to the start or end<kbd>Ctrl + wheel</kbd>Zoom the timeline<kbd>Right click</kbd>Move the playhead to the cursor (drag to scrub)</div>
    <div class="ed-foot"><button class="ed-btn primary" id="k-ok">Got it</button></div>`);
  $("k-ok").onclick = closeModal;
}
function cleanProject() {
  const strip = (o) => { const c = JSON.parse(JSON.stringify(o)); delete c._bb; delete c.len; return c; };
  const P = E.P;
  return { aspect: P.aspect, fit: P.fit, lanes: P.lanes, tracks: P.tracks,
    video: P.video.map((o) => { const c = strip(o); delete c.start; delete c.ov; return c; }),
    overlay: P.overlay.map(strip), text: P.text.map(strip), effect: P.effect.map(strip), look: P.look.map(strip), audio: P.audio.map(strip) };
}
function exportDialog() {
  if (!E.P.video.length) { toast({ kind: "error", message: "Add a clip to the timeline first." }); return; }
  pause();
  modal(`<h3>Export video</h3>
    <div class="ed-field"><label>Name</label><input type="text" id="x-name" value="${esc(E.name)}" spellcheck="false"></div>
    <div class="ed-2"><div class="ed-field"><label>Quality</label><select id="x-res"><option value="1080">Full HD (1080)</option><option value="720">HD (720)</option></select></div>
    <div class="ed-field"><label>File size</label><select id="x-q"><option value="standard">Balanced</option><option value="high">Best looking</option><option value="draft">Smallest</option></select></div></div>
    <p class="ed-hint">${E.P.aspect}, ${fmt(E.total)} long. It saves to your clips folder under <b>Edits</b>.</p>
    <div class="ed-foot"><button class="ed-btn" id="x-cancel">Cancel</button><button class="ed-btn primary" id="x-go">Export</button></div>`);
  $("x-cancel").onclick = closeModal;
  $("x-go").onclick = startExport;
}
async function startExport() {
  const title = $("x-name").value.trim() || "Edit", res = Number($("x-res").value), quality = $("x-q").value;
  modal(`<h3>Exporting…</h3><div class="ed-bar"><i id="x-bar"></i></div><div class="ed-hint" id="x-pct">Starting…</div>
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
      modal(`<h3>Your video is ready</h3><p class="ed-hint">${esc(j.rel.split("/").pop())}</p>
        <div class="ed-foot"><button class="ed-btn" id="x-keep">Keep editing</button><button class="ed-btn" id="x-show">Show in folder</button><button class="ed-btn primary" id="x-watch">Watch it</button></div>`);
      $("x-keep").onclick = closeModal;
      $("x-show").onclick = () => api("/api/clips/reveal", { name: j.rel });
      $("x-watch").onclick = async () => { closeModal(); hideQuiet(); await loadClips(); openPlayer(j.rel); };
      loadClips();
      return;
    }
  }
}
function hideQuiet() { pause(); $("ed").classList.remove("on"); closeModal(); }

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
  else if (e.key === "Escape") { hide(); }
}
function freshProject() { return { aspect: "16:9", fit: "fit", video: [], overlay: [], text: [], effect: [], look: [], audio: [], lanes: {}, tracks: { o: 0, t: 0, e: 0, l: 0, a: 0 } }; }
function normalise(P) { for (const k of ["video", "overlay", "text", "effect", "look", "audio"]) P[k] = P[k] || []; P.lanes = P.lanes || {}; return P; }
function show() {
  build();
  $("ed").classList.add("on");
  const w = $("ed-scroll").clientWidth || 900;
  if (!E.zoomSet) { E.zoom = clamp((w - GUT - 80) / Math.max(E.total, 8), 10, 200); E.zoomSet = true; }
  refreshAll(); setTimeout(renderTimeline, 50);
  seek(E.t);
  requestAnimationFrame(tick);
}
/* open(name, range): from the player. Without arguments: carry on with the edit in progress, or start an empty one. */
async function open(name, range) {
  build();
  if (!name) {
    if (!E.P) { E.P = freshProject(); E.name = "My edit"; E.t = 0; E.hist = [JSON.stringify(E.P)]; E.hi = 0; layout(); }
    return show();
  }
  let m;
  try { m = await loadMeta(name); } catch (e) { toast({ kind: "error", message: "Couldn't open that clip in the editor." }); return; }
  const inn = range && range.start > 0.05 ? range.start : 0, out = range && range.end && range.end < m.dur - 0.05 ? range.end : m.dur;
  const clip = newClip(name, inn, out);
  if (E.P && E.hi > 0 && !E.exported && E.P.video.length) {            // an edit is already in progress
    modal(`<h3>You have an edit in progress</h3><p class="ed-hint">Add this clip to it, or start a new edit?</p>
      <div class="ed-foot"><button class="ed-btn" id="o-new">Start a new edit</button><button class="ed-btn primary" id="o-add">Add to this edit</button></div>`);
    $("ed").classList.add("on");
    $("o-add").onclick = () => { closeModal(); E.P.video.push(clip); E.sel = { kind: "v", id: clip.id }; layout(); E.t = clip.start; commit(); show(); };
    $("o-new").onclick = () => { closeModal(); startNew(name, m, clip); };
    return;
  }
  startNew(name, m, clip);
}
function startNew(name, m, clip) {
  E.P = freshProject(); E.P.video.push(clip);
  if (m.h > m.w) E.P.aspect = "9:16";
  E.name = niceName(name) + " edit"; E.sel = null; E.t = 0; E.playing = false; E.hist = []; E.hi = -1; E.exported = false; E.curI = -1; E.outI = -1; E.busy = false; E.zoomSet = false;
  layout(); E.hist.push(JSON.stringify(E.P)); E.hi = 0; E.tab = "media";
  show();
}
function close() { hide(); }

window.Editor = { open, close, hide, state: E, addClip, addOverlay, splitAt, applyTransition, addTimed, addText, show };
})();

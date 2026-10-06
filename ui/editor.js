/* Rewind video editor: multi-clip timeline, text, music, speed, filters, export. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const ASPECTS = { "16:9": [960, 540], "9:16": [540, 960], "1:1": [720, 720], "4:5": [640, 800] };
const FONTS = { segoe: "'Segoe UI', sans-serif", arial: "Arial, sans-serif", impact: "Impact, sans-serif", black: "'Arial Black', sans-serif",
  georgia: "Georgia, serif", consolas: "Consolas, monospace", comic: "'Comic Sans MS', cursive" };
const FONT_NAMES = { segoe: "Segoe UI", arial: "Arial", impact: "Impact", black: "Arial Black", georgia: "Georgia", consolas: "Consolas", comic: "Comic Sans" };
const ICON = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l12-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/></svg>',
  split: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M7 8L3 12l4 4M17 8l4 4-4 4"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>',
  undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3"/></svg>',
  redo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 14l5-5-5-5M20 9H10a6 6 0 0 0 0 12h3"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
};

const E = { P: null, sel: null, t: 0, total: 0, playing: false, zoom: 60, hist: [], hi: -1, meta: {}, name: "", tab: "media",
  cur: 0, active: null, activeIdx: -1, token: 0, exported: false, audio: {}, ctx: null, gains: new WeakMap(), drag: null, seekReq: null, built: false };
const V = [document.createElement("video"), document.createElement("video")];
V.forEach((v) => { v.playsInline = true; v.preload = "auto"; });

const uid = () => Math.random().toString(36).slice(2, 9);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (t) => { t = Math.max(0, t); const m = Math.floor(t / 60); return `${m}:${(t % 60).toFixed(1).padStart(4, "0")}`; };
const srcUrl = (s) => s.startsWith("ext:") ? "/ext/" + s.slice(4) : "/media/" + encodeURIComponent(s);
const niceName = (s) => s.startsWith("ext:") ? (E.meta[s] && E.meta[s].label) || "Audio file" : s.split("/").pop().replace(/\.mp4$/i, "");

/* ------------------------------------------------------------ model */
function layout() {
  let acc = 0;
  for (const c of E.P.video) { c.len = (c.out - c.in) / c.speed; c.start = acc; acc += c.len; }
  E.total = acc;
}
function newClip(src, inn, out) {
  return { id: uid(), src, in: inn, out, speed: 1, volume: 1, mute: false, filter: { b: 0, c: 0, s: 0 }, fadeIn: 0, fadeOut: 0 };
}
function clipIndexAt(t) {
  const v = E.P.video;
  for (let i = 0; i < v.length; i++) if (t < v[i].start + v[i].len - 1e-6) return i;
  return v.length - 1;
}
function find(kind, id) { return (kind === "v" ? E.P.video : kind === "t" ? E.P.text : E.P.audio).find((x) => x.id === id); }
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

/* ------------------------------------------------------------ playback */
function ensureSrc(v, src) {
  const u = srcUrl(src);
  if (v.dataset.src === u) return v.readyState >= 1 ? Promise.resolve() : new Promise((r) => v.addEventListener("loadedmetadata", r, { once: true }));
  v.dataset.src = u; v.src = u;
  return new Promise((r) => v.addEventListener("loadedmetadata", r, { once: true }));
}
function localTime(c, t) { return c.in + clamp(t - c.start, 0, c.len) * c.speed; }
async function startClip(t, autoplay) {
  if (!E.P.video.length) { E.active = null; return; }
  const my = ++E.token;
  const i = clipIndexAt(t), c = E.P.video[i];
  const v = V[E.cur];
  V[1 - E.cur].pause();
  await ensureSrc(v, c.src);
  if (my !== E.token) return;
  E.active = c; E.activeIdx = i;
  v.playbackRate = c.speed;
  v.currentTime = localTime(c, t);
  await new Promise((r) => { if (!v.seeking && v.readyState >= 2) r(); else v.addEventListener("seeked", r, { once: true }); setTimeout(r, 1200); });
  if (my !== E.token) return;
  applyVolume();
  if (autoplay && E.playing) v.play().catch(() => {});
  preloadNext(i);
}
function continuous(a, b) { return b && a.src === b.src && Math.abs(b.in - a.out) < 0.06 && a.speed === b.speed; }
function preloadNext(i) {
  const c = E.P.video[i], n = E.P.video[i + 1];
  if (!n || continuous(c, n)) return;
  const o = V[1 - E.cur];
  ensureSrc(o, n.src).then(() => { if (E.activeIdx === i) { o.pause(); o.currentTime = n.in; } });
}
function applyVolume() {
  const c = E.active; if (!c) return;
  const v = V[E.cur], local = E.t - c.start;
  let g = c.mute ? 0 : c.volume;
  if (c.fadeIn > 0 && local < c.fadeIn) g *= clamp(local / c.fadeIn, 0, 1);
  if (c.fadeOut > 0 && c.len - local < c.fadeOut) g *= clamp((c.len - local) / c.fadeOut, 0, 1);
  setVol(v, g); setVol(V[1 - E.cur], 0);
}
function play() {
  if (E.playing || !E.P.video.length) return;
  audioCtx();
  if (E.t >= E.total - 0.03) E.t = 0;
  E.playing = true; syncTransport();
  startClip(E.t, true);
}
function pause() {
  E.playing = false; E.token++;
  V.forEach((v) => v.pause());
  Object.values(E.audio).forEach((a) => a.el.pause());
  syncTransport();
}
function toggle() { E.playing ? pause() : play(); }
function seek(t) {
  E.t = clamp(t, 0, E.total);
  if (E.playing) startClip(E.t, true); else startClip(E.t, false);
  updatePlayhead(); syncTransport();
}
function advance() {
  const i = E.activeIdx, c = E.active, n = E.P.video[i + 1];
  if (!n) { E.t = E.total; pause(); return; }
  E.t = n.start;
  const v = V[E.cur];
  if (continuous(c, n)) { E.active = n; E.activeIdx = i + 1; v.playbackRate = n.speed; preloadNext(i + 1); return; }
  const o = V[1 - E.cur];
  if (o.dataset.src === srcUrl(n.src) && o.readyState >= 2 && Math.abs(o.currentTime - n.in) < 0.2) {
    v.pause(); E.cur = 1 - E.cur; E.active = n; E.activeIdx = i + 1;
    o.playbackRate = n.speed; o.play().catch(() => {}); preloadNext(i + 1);
  } else startClip(n.start, true);
}

/* music tracks */
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
function sizeCanvas() {
  const [w, h] = ASPECTS[E.P.aspect] || ASPECTS["16:9"];
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  bgc.width = Math.round(w / 12); bgc.height = Math.round(h / 12);
}
function drawVideo(c, v) {
  const W = cv.width, H = cv.height, vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || v.readyState < 2) return false;
  const f = c.filter || {};
  const local = E.t - c.start; let a = 1;
  if (c.fadeIn > 0 && local < c.fadeIn) a = clamp(local / c.fadeIn, 0, 1);
  if (c.fadeOut > 0 && c.len - local < c.fadeOut) a = Math.min(a, clamp((c.len - local) / c.fadeOut, 0, 1));
  const mode = E.P.fit;
  cx.save(); cx.globalAlpha = a;
  const flt = `brightness(${1 + f.b / 125}) contrast(${1 + f.c / 100}) saturate(${1 + f.s / 100})`;
  if (mode === "blur") {
    const s = Math.max(bgc.width / vw, bgc.height / vh);
    bgx.filter = "blur(2px)";
    bgx.drawImage(v, (bgc.width - vw * s) / 2, (bgc.height - vh * s) / 2, vw * s, vh * s);
    cx.imageSmoothingQuality = "high"; cx.filter = flt;
    cx.drawImage(bgc, 0, 0, W, H);
  }
  cx.filter = flt;
  if (mode === "fill") { const s = Math.max(W / vw, H / vh); cx.drawImage(v, (W - vw * s) / 2, (H - vh * s) / 2, vw * s, vh * s); }
  else { const s = Math.min(W / vw, H / vh); cx.drawImage(v, (W - vw * s) / 2, (H - vh * s) / 2, vw * s, vh * s); }
  cx.restore();
  return true;
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
  if (!E.P) return;
  sizeCanvas();
  cx.fillStyle = "#000"; cx.fillRect(0, 0, cv.width, cv.height);
  const c = E.P.video.length ? (E.active && E.active === E.P.video[E.activeIdx] ? E.active : E.P.video[clipIndexAt(E.t)]) : null;
  if (c) drawVideo(c, V[E.cur]);
  for (const t of E.P.text) {
    const on = E.t >= t.start && E.t < t.start + t.dur;
    const isSel = E.sel && E.sel.kind === "t" && E.sel.id === t.id;
    if (on) drawText(t, isSel && !E.playing); else t._bb = null;
  }
}
function tick() {
  if (!$("ed").classList.contains("on")) return;
  if (E.playing && E.active) {
    const v = V[E.cur], c = E.active;
    if (v.readyState >= 2 && !v.seeking && !v.paused) {
      if (v.playbackRate !== c.speed) v.playbackRate = c.speed;
      E.t = c.start + (v.currentTime - c.in) / c.speed;
      if (v.currentTime >= c.out - 0.03 || v.ended) advance();
      applyVolume();
    }
  }
  if (E.seekReq != null) { const t = E.seekReq; E.seekReq = null; seek(t); }
  syncAudio(); draw(); updatePlayhead();
  requestAnimationFrame(tick);
}

/* ------------------------------------------------------------ editing operations */
function splitAt(t) {
  const it = selItem();
  if (E.sel && E.sel.kind === "t" && it && t > it.start + 0.2 && t < it.start + it.dur - 0.2) {
    const b = { ...it, id: uid(), start: t, dur: it.start + it.dur - t }; it.dur = t - it.start;
    E.P.text.push(b); return commit();
  }
  const i = clipIndexAt(t), c = E.P.video[i]; if (!c) return;
  const sp = c.in + (t - c.start) * c.speed;
  if (sp < c.in + 0.1 || sp > c.out - 0.1) return;
  const b = JSON.parse(JSON.stringify(c)); b.id = uid(); b.in = sp; b.fadeIn = 0;
  c.out = sp; c.fadeOut = 0;
  E.P.video.splice(i + 1, 0, b);
  E.sel = { kind: "v", id: b.id };
  commit();
}
function removeSel() {
  if (!E.sel) return;
  const list = E.sel.kind === "v" ? E.P.video : E.sel.kind === "t" ? E.P.text : E.P.audio;
  const i = list.findIndex((x) => x.id === E.sel.id);
  if (i < 0) return;
  list.splice(i, 1); E.sel = null; commit();
  E.t = clamp(E.t, 0, E.total); seek(E.t);
}
function duplicateSel() {
  const it = selItem(); if (!it) return;
  const b = JSON.parse(JSON.stringify(it)); b.id = uid();
  if (E.sel.kind === "v") { const i = E.P.video.indexOf(it); E.P.video.splice(i + 1, 0, b); }
  else { b.start = it.start + (E.sel.kind === "t" ? it.dur : it.out - it.in); (E.sel.kind === "t" ? E.P.text : E.P.audio).push(b); }
  E.sel = { kind: E.sel.kind, id: b.id }; commit();
}
async function addClip(name) {
  try {
    const m = await loadMeta(name);
    const c = newClip(name, 0, m.dur); E.P.video.push(c); E.sel = { kind: "v", id: c.id };
    commit(); E.t = c.start; seek(E.t); scrollToPlayhead();
  } catch (e) { toast({ kind: "error", message: e.message }); }
}
function addText(preset) {
  const base = { id: uid(), text: "Your text", start: E.t, dur: Math.min(3, Math.max(1, E.total - E.t || 3)), x: 50, y: 80, size: 7, color: "#ffffff", font: "segoe", bold: true, outline: true, box: false };
  const t = Object.assign(base, preset || {});
  E.P.text.push(t); E.sel = { kind: "t", id: t.id }; commit(); setTab("text");
}
async function addAudioFile() {
  const r = await api("/api/editor/pick-audio");
  if (!r.ok) return;
  E.meta[r.id] = { label: r.name };
  try { await addAudio(r.id); } catch (e) { toast({ kind: "error", message: e.message }); }
}
async function addAudio(src) {
  const m = await loadMeta(src);
  const a = { id: uid(), src, in: 0, out: Math.min(m.dur, Math.max(1, E.total || m.dur)), start: E.t, volume: 0.8, fadeIn: 0, fadeOut: 0 };
  E.P.audio.push(a); E.sel = { kind: "a", id: a.id }; commit();
}

/* ------------------------------------------------------------ UI: skeleton */
function build() {
  if (E.built) return;
  E.built = true;
  const root = document.createElement("div"); root.id = "ed";
  root.innerHTML = `
    <div class="ed-top">
      <button class="ed-btn" id="ed-back">${ICON.back}Back</button>
      <input class="title" id="ed-title" spellcheck="false" aria-label="Project name">
      <span class="grow"></span>
      <button class="ed-btn ico" id="ed-undo" title="Undo (Ctrl+Z)">${ICON.undo}</button>
      <button class="ed-btn ico" id="ed-redo" title="Redo (Ctrl+Y)">${ICON.redo}</button>
      <button class="ed-btn primary" id="ed-export">Export</button>
    </div>
    <div class="ed-left">
      <div class="ed-tabs"><button data-tab="media">Media</button><button data-tab="text">Text</button><button data-tab="audio">Audio</button></div>
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
function renderTimeline() {
  const s = $("ed-scroll"), inner = $("ed-inner"), z = E.zoom;
  $("ed-zoom").value = z;
  const width = Math.max(s.clientWidth, (Math.max(E.total, ...E.P.text.map((t) => t.start + t.dur), ...E.P.audio.map((a) => a.start + a.out - a.in)) + 6) * z);
  inner.style.width = width + "px";
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600], step = steps.find((x) => x * z >= 70) || 600;
  let ruler = "";
  for (let t = 0; t * z < width; t += step / 5) {
    const big = Math.abs(t / step - Math.round(t / step)) < 1e-6;
    ruler += big ? `<span style="left:${t * z}px">${fmt(t).replace(/\.0$/, "")}</span><i class="big" style="left:${t * z}px"></i>` : `<i style="left:${t * z}px"></i>`;
  }
  const tl = lanes(E.P.text, (t) => t.start, (t) => t.start + t.dur), al = lanes(E.P.audio, (a) => a.start, (a) => a.start + a.out - a.in);
  let h = `<div class="ed-ruler" id="ed-ruler" style="width:${width}px">${ruler}</div>`;
  h += `<div class="ed-track v" data-track="v" style="width:${width}px"><div class="ed-bg"></div>`;
  if (!E.P.video.length) h += `<div class="ed-empty">Add a clip from the Media tab</div>`;
  for (const c of E.P.video) {
    const th = `/thumb/${encodeURIComponent(c.src.startsWith("ext:") ? "" : c.src)}`;
    h += `<div class="ed-item vc${E.sel && E.sel.id === c.id ? " sel" : ""}" data-kind="v" data-id="${c.id}" style="left:${c.start * z}px;width:${Math.max(6, c.len * z)}px;background-image:url('${th}')">
      <span class="hd l" data-h="l"></span><span class="lb">${esc(niceName(c.src))}<small>${fmt(c.len)}${c.speed !== 1 ? " · " + c.speed + "x" : ""}</small></span><span class="hd r" data-h="r"></span></div>`;
  }
  h += `</div>`;
  h += `<div class="ed-track t" data-track="t" style="width:${width}px;height:${tl * 40}px"><div class="ed-bg"></div>`;
  if (!E.P.text.length) h += `<div class="ed-empty">Text appears here</div>`;
  for (const t of E.P.text) h += `<div class="ed-item tx${E.sel && E.sel.id === t.id ? " sel" : ""}" data-kind="t" data-id="${t.id}" style="left:${t.start * z}px;width:${Math.max(8, t.dur * z)}px;top:${t._lane * 40}px;height:38px;bottom:auto">
      <span class="hd l" data-h="l"></span><span class="lb">${esc(String(t.text).split("\n")[0])}</span><span class="hd r" data-h="r"></span></div>`;
  h += `</div>`;
  h += `<div class="ed-track a" data-track="a" style="width:${width}px;height:${al * 40}px"><div class="ed-bg"></div>`;
  if (!E.P.audio.length) h += `<div class="ed-empty">Music and sounds appear here</div>`;
  for (const a of E.P.audio) h += `<div class="ed-item au${E.sel && E.sel.id === a.id ? " sel" : ""}" data-kind="a" data-id="${a.id}" style="left:${a.start * z}px;width:${Math.max(8, (a.out - a.in) * z)}px;top:${a._lane * 40}px;height:38px;bottom:auto">
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
    E.sel = { kind, id }; renderInspector(); renderTimelineSel();
    const h = e.target.dataset.h;
    E.drag = { type: h ? "trim" + h : "move", kind, id, x0: e.clientX, snap: JSON.parse(JSON.stringify(it)), order0: E.P.video.map((c) => c.id), moved: false };
    e.preventDefault(); return;
  }
  if (e.target.closest(".ed-ruler") || e.target.closest(".ed-track")) {
    if (!e.target.closest(".ed-item")) { E.sel = null; renderInspector(); renderTimelineSel(); }
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
      const grab = (d.x0 - left) / E.zoom - s.start;                 // where inside the clip it was picked up
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
  else if (!d.moved && d.kind === "v" && it) { E.t = clamp(E.t, 0, E.total); }
  if (!d.moved && it && d.type === "move") { /* a plain click selects; the playhead stays put */ }
}
function canvasDown(e) {
  const it = selItem();
  if (!it || E.sel.kind !== "t" || !it._bb) return;
  const r = cv.getBoundingClientRect(), sx = cv.width / r.width;
  const x = (e.clientX - r.left) * sx, y = (e.clientY - r.top) * sx, b = it._bb;
  if (x < b.x - 10 || x > b.x + b.w + 10 || y < b.y - 10 || y > b.y + b.h + 10) return;
  const move = (ev) => { it.x = clamp(((ev.clientX - r.left) * sx) / cv.width * 100, 0, 100); it.y = clamp(((ev.clientY - r.top) * sx) / cv.height * 100, 0, 100); renderInspector(true); };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); commit(); };
  addEventListener("pointermove", move); addEventListener("pointerup", up);
  e.preventDefault();
}

/* ------------------------------------------------------------ left pane */
function setTab(t) { E.tab = t; renderPane(); }
function renderPane() {
  document.querySelectorAll("#ed .ed-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === E.tab));
  const p = $("ed-pane");
  if (E.tab === "media") {
    const list = (typeof clips !== "undefined" ? clips : []);
    p.innerHTML = `<h4>Your clips</h4><div class="ed-media">${list.map((c) => `<button class="ed-mi" data-name="${esc(c.name)}" title="Add to the timeline"><div class="th" style="background-image:url('/thumb/${encodeURIComponent(c.name)}')"><i>+</i>${c.duration ? `<span>${clock(c.duration)}</span>` : ""}</div><b>${esc(c.title.replace(/ \d{4}-\d\d-\d\d \d\d-\d\d-\d\d.*$/, "") || c.title)}</b></button>`).join("") || '<p class="ed-hint">No clips yet.</p>'}</div>`;
    p.querySelectorAll(".ed-mi").forEach((b) => b.onclick = () => addClip(b.dataset.name));
  } else if (E.tab === "text") {
    p.innerHTML = `<h4>Add text</h4><div class="ed-tpl">
      <button data-p="title"><b>Title</b><small>Big and centred</small></button>
      <button data-p="lower"><b>Lower third</b><small>Name or caption near the bottom</small></button>
      <button data-p="caption"><b>Caption box</b><small>White text on a dark box</small></button>
      <button data-p="meme"><b>Meme text</b><small>Impact with a black outline</small></button></div>
      <p class="ed-hint" style="margin-top:14px">Text is added at the playhead. Drag it in the preview to place it, and drag its edges on the timeline to change how long it shows.</p>`;
    const pre = { title: { text: "Title", y: 50, size: 12 }, lower: { text: "Your name", y: 84, size: 6 }, caption: { text: "Caption", y: 88, size: 5, box: true, outline: false },
      meme: { text: "TOP TEXT", y: 12, size: 10, font: "impact", bold: false } };
    p.querySelectorAll("[data-p]").forEach((b) => b.onclick = () => addText(pre[b.dataset.p]));
  } else {
    p.innerHTML = `<h4>Music and sounds</h4><button class="ed-btn primary" id="ed-addaudio">Add an audio file…</button>
      <p class="ed-hint" style="margin-top:12px">MP3, WAV, M4A, OGG or any video file. It plays alongside your clips, and you can move it, trim it and set its volume.</p>
      <h4>From your clips</h4><div class="ed-media">${(typeof clips !== "undefined" ? clips : []).map((c) => `<button class="ed-mi" data-name="${esc(c.name)}" title="Use this clip's sound"><div class="th" style="background-image:url('/thumb/${encodeURIComponent(c.name)}')"><i>♪</i></div><b>${esc(c.title.replace(/ \d{4}-\d\d-\d\d \d\d-\d\d-\d\d.*$/, "") || c.title)}</b></button>`).join("")}</div>`;
    $("ed-addaudio").onclick = addAudioFile;
    p.querySelectorAll(".ed-mi").forEach((b) => b.onclick = () => addAudio(b.dataset.name).catch((e) => toast({ kind: "error", message: e.message })));
  }
}

/* ------------------------------------------------------------ inspector */
function row(label, key, min, max, step, val, out) {
  return `<div class="ed-row"><label>${label}</label><input type="range" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${val}"><output>${out}</output></div>`;
}
function renderInspector(light) {
  const el = $("ed-insp");
  const it = selItem();
  if (light && el.dataset.sel === (E.sel ? E.sel.id : "none")) { updateInspectorValues(); return; }
  el.dataset.sel = E.sel ? E.sel.id : "none";
  if (!it) {
    el.innerHTML = `<h3>Project</h3>
      <div class="ed-field"><label>Canvas shape</label><div class="ed-chips" id="i-aspect">${Object.keys(ASPECTS).map((a) => `<button class="ed-chip${E.P.aspect === a ? " on" : ""}" data-a="${a}">${a}</button>`).join("")}</div></div>
      <div class="ed-field"><label>When a clip doesn't match the canvas</label><div class="ed-chips" id="i-fit">${[["fit", "Fit"], ["fill", "Fill"], ["blur", "Fit + blur"]].map(([k, l]) => `<button class="ed-chip${E.P.fit === k ? " on" : ""}" data-f="${k}">${l}</button>`).join("")}</div></div>
      <p class="ed-hint" style="margin-top:14px">Pick a clip, text or sound on the timeline to edit it. Use <b>9:16</b> for Shorts, Reels and TikTok.</p>`;
    el.querySelectorAll("[data-a]").forEach((b) => b.onclick = () => { E.P.aspect = b.dataset.a; commit(); });
    el.querySelectorAll("[data-f]").forEach((b) => b.onclick = () => { E.P.fit = b.dataset.f; commit(); });
    return;
  }
  const k = E.sel.kind;
  if (k === "v") {
    const f = it.filter;
    el.innerHTML = `<h3>${esc(niceName(it.src))}</h3>
      <h4>Speed</h4><div class="ed-chips" id="i-speed">${[0.25, 0.5, 1, 1.5, 2, 4].map((s) => `<button class="ed-chip${it.speed === s ? " on" : ""}" data-s="${s}">${s}x</button>`).join("")}</div>
      ${row("Custom", "speed", 0.25, 4, 0.05, it.speed, it.speed.toFixed(2) + "x")}
      <h4>Sound</h4>${row("Volume", "volume", 0, 2, 0.05, it.volume, Math.round(it.volume * 100) + "%")}
      <label class="ed-check"><input type="checkbox" data-k="mute" ${it.mute ? "checked" : ""}> Mute this clip</label>
      <h4>Colour</h4>${row("Brightness", "filter.b", -100, 100, 1, f.b, f.b)}${row("Contrast", "filter.c", -100, 100, 1, f.c, f.c)}${row("Saturation", "filter.s", -100, 100, 1, f.s, f.s)}
      <h4>Fades</h4>${row("Fade in", "fadeIn", 0, 3, 0.1, it.fadeIn, it.fadeIn.toFixed(1) + "s")}${row("Fade out", "fadeOut", 0, 3, 0.1, it.fadeOut, it.fadeOut.toFixed(1) + "s")}
      <div class="ed-actions"><button class="ed-btn" id="i-reset">Reset colour</button><button class="ed-btn" id="i-split">${ICON.split}Split here</button></div>`;
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
  const rs = $("i-reset"); if (rs) rs.onclick = () => { it.filter = { b: 0, c: 0, s: 0 }; commit(); };
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
    if (key === "speed" || key === "in") layout();
    const out = f.parentElement.querySelector("output");
    if (out) out.textContent = key === "speed" ? Number(v).toFixed(2) + "x" : ["volume"].includes(key) ? Math.round(v * 100) + "%" : ["fadeIn", "fadeOut"].includes(key) ? Number(v).toFixed(1) + "s" : ["x", "y"].includes(key) ? Math.round(v) + "%" : v;
    renderTimeline();
  };
  f.addEventListener("input", () => { apply(); if (E.sel && E.sel.kind === "v" && ["volume", "mute"].includes(key)) applyVolume(); });
  f.addEventListener("change", () => { apply(); commit(); if (key === "speed" || key === "mute") { seek(E.t); } });
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
  const strip = (o) => { const c = JSON.parse(JSON.stringify(o)); delete c._lane; delete c._bb; return c; };
  return { aspect: E.P.aspect, fit: E.P.fit, video: E.P.video.map(strip), text: E.P.text.map(strip), audio: E.P.audio.map(strip) };
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
  E.P = { aspect: "16:9", fit: "fit", video: [newClip(name, inn, out)], text: [], audio: [] };
  E.name = niceName(name) + " edit"; E.sel = null; E.t = 0; E.playing = false; E.hist = []; E.hi = -1; E.exported = false; E.active = null; E.activeIdx = -1;
  if (m.h > m.w) { E.P.aspect = "9:16"; }
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
  E.active = null;
}
function confirmClose() {
  pause();
  modal(`<h3>Leave the editor?</h3><p class="ed-small">Your edits haven't been exported yet and will be lost.</p>
    <div class="ed-foot"><button class="ed-btn" id="c-stay">Keep editing</button><button class="ed-btn danger" id="c-leave">Leave</button></div>`);
  $("c-stay").onclick = closeModal; $("c-leave").onclick = () => { closeModal(); close(true); };
  return false;
}

window.Editor = { open, close, state: E, addClip, splitAt };
})();

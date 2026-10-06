"""Built-in sound effects for the video editor. Generated on demand, so they cost nothing to ship and are free to use."""
import wave
from pathlib import Path

RATE = 48000

NAMES = {
    "whoosh": "Whoosh", "swish": "Swish", "riser": "Riser", "boom": "Boom", "impact": "Impact", "pop": "Pop",
    "ding": "Ding", "click": "Click", "success": "Success", "buzz": "Error buzz", "laser": "Laser", "glitch": "Glitch",
}


def _np():
    import numpy as np
    return np


def _env(np, n, attack, decay):
    t = np.arange(n) / RATE
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _smooth_noise(np, rng, n, cutoff_hz):
    """White noise low-passed with a moving average (cheap and good enough for whooshes)."""
    k = max(1, int(RATE / max(cutoff_hz, 50)))
    x = rng.standard_normal(n + k)
    c = np.cumsum(x)
    y = (c[k:] - c[:-k]) / k
    return y / (np.abs(y).max() + 1e-9)


def _bell(np, f, dur, decay):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for ratio, amp, dk in ((1.0, 1.0, 1.0), (2.0, 0.35, 0.55), (2.76, 0.2, 0.35), (4.07, 0.08, 0.2)):
        out += amp * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t / (decay * dk))
    return out * np.minimum(1, t / 0.003)


def synth(name):
    np = _np()
    rng = np.random.default_rng(11)
    if name == "whoosh":
        n = int(RATE * 1.0)
        t = np.arange(n) / RATE
        noise = _smooth_noise(np, rng, n, 1800)
        env = np.sin(np.pi * np.clip(t / 1.0, 0, 1)) ** 2
        sig = noise * env
        sig += 0.25 * _smooth_noise(np, rng, n, 5000) * env * np.linspace(0.2, 1, n)
    elif name == "swish":
        n = int(RATE * 0.38)
        t = np.arange(n) / RATE
        sig = (_smooth_noise(np, rng, n, 4500) * np.sin(np.pi * t / 0.38) ** 1.5)
    elif name == "riser":
        n = int(RATE * 2.4)
        t = np.arange(n) / RATE
        f = 180 * (2400 / 180) ** (t / t[-1])
        tone = np.sin(2 * np.pi * np.cumsum(f) / RATE) * 0.5
        noise = _smooth_noise(np, rng, n, 3000) * np.linspace(0.05, 0.8, n)
        sig = (tone + noise) * np.linspace(0.05, 1, n) ** 1.6
        sig[-int(RATE * 0.04):] *= np.linspace(1, 0, int(RATE * 0.04))
    elif name == "boom":
        n = int(RATE * 1.6)
        t = np.arange(n) / RATE
        f = 95 * np.exp(-t / 0.35) + 28
        body = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / 0.55)
        rumble = _smooth_noise(np, rng, n, 220) * np.exp(-t / 0.5)
        crack = _smooth_noise(np, rng, n, 3500) * np.exp(-t / 0.05)
        sig = body + 0.6 * rumble + 0.5 * crack
    elif name == "impact":
        n = int(RATE * 0.55)
        t = np.arange(n) / RATE
        f = 140 * np.exp(-t / 0.08) + 45
        sig = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / 0.16) + 0.5 * _smooth_noise(np, rng, n, 2500) * np.exp(-t / 0.03)
    elif name == "pop":
        n = int(RATE * 0.2)
        t = np.arange(n) / RATE
        f = 320 + 900 * (1 - np.exp(-t / 0.025))
        sig = np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(np, n, 0.002, 0.04)
    elif name == "ding":
        sig = _bell(np, 1318.5, 1.1, 0.35)
    elif name == "click":
        n = int(RATE * 0.06)
        sig = _smooth_noise(np, rng, n, 6000) * _env(np, n, 0.0004, 0.006) * 2.0
        sig += np.sin(2 * np.pi * 1800 * np.arange(n) / RATE) * _env(np, n, 0.0004, 0.004)
    elif name == "success":
        sig = np.zeros(int(RATE * 1.1))
        for at, f in ((0.0, 523.25), (0.1, 659.25), (0.2, 783.99), (0.32, 1046.5)):
            b = _bell(np, f, 0.7, 0.18)
            i = int(at * RATE)
            sig[i:i + len(b)] += b[: len(sig) - i]
    elif name == "buzz":
        n = int(RATE * 0.45)
        t = np.arange(n) / RATE
        sig = (np.sign(np.sin(2 * np.pi * 110 * t)) * 0.5 + np.sin(2 * np.pi * 155 * t) * 0.5) * _env(np, n, 0.005, 0.25)
    elif name == "laser":
        n = int(RATE * 0.32)
        t = np.arange(n) / RATE
        f = 2400 * np.exp(-t / 0.09) + 280
        sig = np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(np, n, 0.002, 0.18)
    elif name == "glitch":
        n = int(RATE * 0.55)
        sig = np.zeros(n)
        pos = 0
        while pos < n:
            ln = int(RATE * rng.uniform(0.01, 0.05))
            f = rng.choice([220, 440, 880, 1760, 3520])
            seg = np.sign(np.sin(2 * np.pi * f * np.arange(ln) / RATE)) * 0.6
            if rng.random() < 0.4:
                seg = rng.standard_normal(ln) * 0.5
            sig[pos:pos + ln] += seg[: n - pos]
            pos += ln + int(RATE * rng.uniform(0.0, 0.03))
        sig *= np.linspace(1, 0.2, n)
    else:
        raise ValueError(name)
    fade = min(len(sig), int(RATE * 0.01))
    sig[-fade:] *= np.linspace(1, 0, fade)
    sig = sig / (np.abs(sig).max() + 1e-9) * 0.85
    return np.stack([sig, sig], axis=1)


def ensure(name, folder):
    """Write <folder>/<name>.wav if it isn't there yet and return its path."""
    if name not in NAMES:
        raise ValueError("Unknown sound")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{name}.wav"
    if not p.exists():
        np = _np()
        data = (np.clip(synth(name), -1, 1) * 32767).astype("<i2").tobytes()
        with wave.open(str(p), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(data)
    return p

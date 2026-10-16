#!/usr/bin/env python3
"""
Original guide track for the Reel — synthesized from scratch (no samples, no
copyrighted material). Baile-funk-inspired groove at 120 BPM, locked to the
same beat grid as the cuts (1 beat = 0.5 s = 15 frames).

Writes:
  build/music.wav   groove + SFX (guide mix, loops cleanly at 18 s)
  build/sfx.wav     SFX hits only (to keep under the music you pick in Instagram)
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
BPM = 120
SPB = 60 / BPM                     # seconds per beat
STEP = SPB / 4                     # 16th note
DUR = 18.0
N = int(SR * DUR)
TAIL = int(SR * 2)
FPS = 30
BUILD = Path(__file__).resolve().parent / "build"
rng = np.random.default_rng(7)


def buf():
    return np.zeros((N + TAIL, 2), np.float32)

def add(dst, sig, t, gain=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= len(dst):
        return
    sig = sig[: len(dst) - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    dst[i:i + len(sig), 0] += sig * gain * l * 1.414
    dst[i:i + len(sig), 1] += sig * gain * r * 1.414

def env(n, attack=0.002, decay=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / attack) * np.exp(-t / decay)

def onepole_hp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(x); prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x); prev_x = v; y[i] = prev_y
    return y

def lowpass(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(x); p = 0.0
    for i, v in enumerate(x):
        p = (1 - a) * v + a * p; y[i] = p
    return y

# ------------------------------------------------------------- instruments
def kick(dur=0.42, f0=140, f1=46):
    n = int(SR * dur); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * env(n, 0.001, 0.16)
    s += 0.35 * rng.normal(0, 1, n) * env(n, 0.0005, 0.004)          # click
    return np.tanh(s * 2.2) * 0.8

def bass808(freq, dur=0.45):
    n = int(SR * dur); t = np.arange(n) / SR
    f = freq * (1 + 0.6 * np.exp(-t / 0.02))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.28)
    return np.tanh(s * 3.0) * 0.55                                   # saturation = audible on phones

_noise = rng.normal(0, 1, SR * 2).astype(np.float32)
_hp_noise = onepole_hp(_noise[:SR].copy(), 6000)
_mid_noise = lowpass(onepole_hp(_noise[SR:].copy(), 900), 5000)

def clap():
    n = int(SR * 0.22); s = np.zeros(n, np.float32)
    for k, off in enumerate((0, 0.011, 0.022)):
        i = int(off * SR); m = n - i
        s[i:] += _mid_noise[:m] * env(m, 0.0005, 0.012 if k < 2 else 0.09)
    return s * 0.9

def hat(open_=False):
    n = int(SR * (0.18 if open_ else 0.045))
    return _hp_noise[:n] * env(n, 0.0005, 0.06 if open_ else 0.012) * 0.6

def tambor(freq=210, dur=0.18):
    """Atabaque-ish tom for the tamborzão feel."""
    n = int(SR * dur); t = np.arange(n) / SR
    f = freq * (1 + 0.25 * np.exp(-t / 0.015))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.07)
    s += 0.25 * _mid_noise[:n] * env(n, 0.0005, 0.01)
    return s * 0.7

def pluck(freq, dur=0.22):
    n = int(SR * dur); t = np.arange(n) / SR
    s = np.sign(np.sin(2 * np.pi * freq * t)) * 0.5 + np.sin(2 * np.pi * freq * 2 * t) * 0.3
    return lowpass(s * env(n, 0.002, 0.07), 3200) * 0.35

def impact():
    n = int(SR * 0.9); t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 90 * np.exp(-t / 0.05)) / SR) * env(n, 0.001, 0.35)
    crack = _mid_noise[:n] * env(n, 0.0005, 0.03)
    return np.tanh((boom * 1.2 + crack * 0.7) * 1.8) * 0.8

def whoosh(dur=0.32):
    n = int(SR * dur); t = np.linspace(0, 1, n)
    s = _noise[:n] * np.sin(np.pi * t) ** 2
    out = np.zeros(n, np.float32); p = 0.0
    for i in range(n):                                               # sweeping one-pole
        a = np.exp(-2 * np.pi * (400 + 5000 * t[i] ** 2) / SR)
        p = (1 - a) * s[i] + a * p; out[i] = p
    return out * 1.6

def riser(dur):
    n = int(SR * dur); t = np.linspace(0, 1, n)
    out = np.zeros(n, np.float32); p = 0.0
    for i in range(n):
        a = np.exp(-2 * np.pi * (300 + 7000 * t[i] ** 3) / SR)
        p = (1 - a) * _noise[i % len(_noise)] + a * p; out[i] = p
    return out * t ** 2 * 0.9

def pop():
    n = int(SR * 0.08); t = np.arange(n) / SR
    return np.sin(2 * np.pi * (900 - 5000 * t) * t) * env(n, 0.0005, 0.02) * 0.6

def marker():
    n = int(SR * 0.16); t = np.linspace(0, 1, n)
    s = _hp_noise[:n] * (0.6 + 0.4 * np.sin(2 * np.pi * 38 * t)) * np.sin(np.pi * t)
    return s * 0.5


# ------------------------------------------------------------------ groove
def note(n):          # midi -> Hz
    return 440 * 2 ** ((n - 69) / 12)

ROOTS = [40, 36, 38, 35]      # E2 C2 D2 B1 — one per bar, loops every 4 bars
RIFF = {0: 76, 3: 74, 6: 71, 8: 69, 10: 71, 14: 67,           # 2-bar funk-melody riff (E minor pent.)
        16: 76, 19: 74, 22: 71, 24: 74, 26: 76, 29: 79}
KICK = (0, 3, 8, 11)
TAMB = {2: 230, 6: 200, 7: 200, 13: 230, 15: 180}
GROOVE_FROM = 6 * SPB         # full groove drops on "BORN HERE." (0:03)


def groove(mus):
    steps = int(DUR / STEP)
    for s in range(steps):
        t = s * STEP
        bar, st = divmod(s, 16)
        beat_pos = t / SPB
        if t < GROOVE_FROM:
            # hook: just a 4-on-floor pulse under the slams + a snare build
            if st % 4 == 0:
                add(mus, kick(), t, 0.55)
            if beat_pos >= 4 and st % 2 == 0:                   # 8ths -> build
                add(mus, clap(), t, 0.18 + 0.25 * (beat_pos - 4) / 2, 0.2)
            continue
        root = note(ROOTS[bar % 4])
        if st in KICK or (bar % 2 and st == 14):
            add(mus, kick(), t, 0.9)
            add(mus, bass808(root), t, 0.75)
        if st in (4, 12):
            add(mus, clap(), t, 0.7, 0.05)
        if st in TAMB:
            add(mus, tambor(TAMB[st]), t, 0.55, -0.35 if st % 2 else 0.35)
        if st % 2 == 0:
            add(mus, hat(st == 10), t, 0.35 if st % 4 == 2 else 0.22, 0.4)
        else:
            add(mus, hat(), t, 0.1, 0.4)
        # riff from 0:04 on, rests in the "NO ..." section (0:14-0:16) to give the strikes room
        if t >= 8 * SPB and not (28 * SPB <= t < 32 * SPB):
            k = s % 32
            if k in RIFF:
                add(mus, pluck(note(RIFF[k])), t, 0.5, -0.2)


# ------------------------------------------------------------------- SFX
SFX = (
    [("impact", f) for f in (0, 8, 15, 30, 38, 45, 53)] +
    [("whoosh_short", 60), ("impact", 90), ("pop", 96), ("impact", 120), ("impact", 150), ("marker", 68 + 90)] +
    [("whoosh", b) for b in (90, 180, 300, 420, 480, 270)] +
    [("pop", f) for f in (182, 184, 212, 242, 254, 272)] +
    [("impact", f) for f in (210, 240)] +
    [("pop", f) for f in (300, 330, 360, 390)] +
    [("impact", f) for f in (420, 435, 450)] + [("marker", f) for f in (427, 442, 457)] +
    [("riser", 450), ("impact", 480), ("marker", 485), ("pop", 495), ("pop", 502)]
)


def sfx(fx):
    for kind, f in SFX:
        t = f / FPS
        if kind == "impact":
            add(fx, impact(), t, 0.6)
        elif kind == "pop":
            add(fx, pop(), t, 0.5, 0.1)
        elif kind == "marker":
            add(fx, marker(), t, 0.6, -0.1)
        elif kind == "whoosh":
            w = whoosh(); add(fx, w, t - len(w) / SR * 0.8, 0.55)        # peaks into the cut
        elif kind == "whoosh_short":
            w = whoosh(0.2); add(fx, w, t - 0.05, 0.35)
        elif kind == "riser":
            r = riser(1.0); add(fx, r, t, 0.35)


def fold_loop(x):
    """Wrap the tail past 18 s onto the start so the file loops seamlessly."""
    y = x[:N].copy(); y[:TAIL] += x[N:N + TAIL]; return y

def master(x, peak=0.89):
    x = np.tanh(x * 1.1) / np.tanh(1.1)
    return x / (np.abs(x).max() + 1e-9) * peak

def write(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    BUILD.mkdir(exist_ok=True)
    mus, fx = buf(), buf()
    groove(mus); sfx(fx)
    mus, fx = fold_loop(mus), fold_loop(fx)
    write(BUILD / "music.wav", master(mus * 0.8 + fx * 0.75))
    write(BUILD / "sfx.wav", master(fx, 0.7))
    print("audio ->", BUILD / "music.wav", BUILD / "sfx.wav")

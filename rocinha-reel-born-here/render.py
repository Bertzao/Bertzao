#!/usr/bin/env python3
"""
@rocinhacousins — "BORN HERE" Reel
1080x1920 · 30 fps · 18 s · 120 BPM (1 beat = 15 frames, 1 bar = 60 frames)

Usage:
  python3 render.py              # full render -> out/
  python3 render.py --stills     # contact sheet + key stills only (fast check)
  python3 render.py --cover      # cover frame only

Drop your own media in media/ (see media/README.md). Missing slots render
as poster-style placeholder frames tagged with the file name to swap in.
"""
import json, math, os, random, subprocess, sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
FONTS, MEDIA, BUILD, OUT = ROOT / "fonts", ROOT / "media", ROOT / "build", ROOT / "out"

W, H, FPS = 1080, 1920, 30
BEAT = 15                      # 120 BPM at 30 fps
N = 18 * FPS                   # 540 frames
SAFE_TOP, SAFE_BOT, SIDE = 250, H - 340, 70

BG = (11, 11, 14)
YELLOW = (255, 222, 0)
GREEN = (0, 214, 104)
BLUE = (34, 78, 255)
ORANGE = (255, 106, 20)
WHITE = (255, 252, 244)
INK = (12, 12, 14)

HEAD = str(FONTS / "Anton-Regular.ttf")
ROUND = str(FONTS / "nunito-latin-900-normal.woff")
ROUND8 = str(FONTS / "nunito-latin-800-normal.woff")
MARKER = str(FONTS / "permanent-marker-latin-400-normal.woff")


# ----------------------------------------------------------------- easing
def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x

def prog(f, start, dur):
    return clamp01((f - start) / float(dur))

def e_out_back(t, s=2.2):
    t = clamp01(t) - 1
    return t * t * ((s + 1) * t + s) + 1

def e_out_cubic(t):
    return 1 - (1 - clamp01(t)) ** 3

def e_out_expo(t):
    t = clamp01(t)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)

def e_in_expo(t):
    t = clamp01(t)
    return 0.0 if t <= 0 else 2 ** (10 * t - 10)

def e_in_out(t):
    t = clamp01(t)
    return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2

def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------- text
@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, int(size))

def fit_size(text, path, width, ref=200):
    return ref * width / font(path, ref).getlength(text)

@lru_cache(maxsize=None)
def text_img(text, path, size, fill=WHITE, shadow=None, shadow_off=(0, 0), pad=6):
    """Tightly cropped RGBA text with optional hard poster shadow."""
    f = font(path, size)
    x0, y0, x1, y1 = f.getbbox(text)
    sx, sy = shadow_off
    w = x1 - x0 + 2 * pad + abs(sx)
    h = y1 - y0 + 2 * pad + abs(sy)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ox, oy = pad - x0 + max(0, -sx), pad - y0 + max(0, -sy)
    if shadow:
        d.text((ox + sx, oy + sy), text, font=f, fill=shadow)
    d.text((ox, oy), text, font=f, fill=fill)
    return im

def paste(canvas, img, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    """Composite RGBA img centred at (cx, cy), safely clipped."""
    if img is None or alpha <= 0 or scale <= 0.01:
        return
    if abs(scale - 1) > 1e-3:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
    if abs(rot) > 0.05:
        img = img.rotate(rot, Image.BICUBIC, expand=True)
    if alpha < 1:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img = img.copy(); img.putalpha(a)
    x, y = int(round(cx - img.width / 2)), int(round(cy - img.height / 2))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(img.width, canvas.width - x), min(img.height, canvas.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    canvas.alpha_composite(img.crop((sx0, sy0, sx1, sy1)), (x + sx0, y + sy0))

def slam(f, start, s0=1.75, r0=-7.0, r1=0.0, dur=7):
    """Overshoot slam-in. Returns (scale, rot) or None if not yet on screen."""
    if f < start:
        return None
    t = prog(f, start, dur)
    return lerp(s0, 1.0, e_out_back(t, 2.6)), lerp(r0, r1, e_out_cubic(t))


# ------------------------------------------------------------- textures
def _grain(seed):
    r = np.random.default_rng(seed)
    g = r.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
    g = np.repeat(np.repeat(g, 2, 0), 2, 1)
    return (g * 9).astype(np.int16)

GRAIN = None

def halftone_bg(base=BG, ink=(30, 30, 38), period=22, angle=30, vignette=0.45):
    """Near-black poster background with a halftone gradient + soft vignette."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    a = math.radians(angle)
    u = (xx * math.cos(a) + yy * math.sin(a)) * 2 * math.pi / period
    v = (-xx * math.sin(a) + yy * math.cos(a)) * 2 * math.pi / period
    screen = (np.cos(u) + np.cos(v)) / 4 + 0.5              # 0..1
    dens = np.clip(0.15 + 0.55 * (yy / H) ** 1.6 + 0.25 * np.exp(-((xx - W * .85) ** 2 + (yy - H * .2) ** 2) / (2 * 380 ** 2)), 0, 1)
    dot = (screen < dens * 0.55).astype(np.float32)
    img = np.empty((H, W, 3), np.float32)
    for c in range(3):
        img[..., c] = base[c] + (ink[c] - base[c]) * dot
    vig = 1 - vignette * np.clip(((xx - W / 2) / (W * .75)) ** 2 + ((yy - H / 2) / (H * .7)) ** 2, 0, 1)
    img *= vig[..., None]
    return Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")

_SCREEN = None

def halftone_photo(img, amount=0.35, period=9):
    """Poster halftone in the shadows of a photo (keeps it real, adds print feel)."""
    global _SCREEN
    if _SCREEN is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        a = math.radians(45)
        u = (xx * math.cos(a) + yy * math.sin(a)) * 2 * math.pi / period
        v = (-xx * math.sin(a) + yy * math.cos(a)) * 2 * math.pi / period
        _SCREEN = (np.cos(u) + np.cos(v)) / 4 + 0.5
    a = np.asarray(img.convert("RGB"), np.float32)
    lum = (a @ np.array([.299, .587, .114], np.float32)) / 255
    ink = (_SCREEN > lum * 1.1 + 0.08).astype(np.float32) * amount
    a = a * (1 - ink[..., None] * 0.85)
    return Image.fromarray(a.clip(0, 255).astype(np.uint8)).convert("RGBA")

def duotone(img, dark=(6, 8, 30), light=BLUE, gain=1.0):
    a = np.asarray(img.convert("L"), np.float32)[..., None] / 255 * gain
    d, l = np.array(dark, np.float32), np.array(light, np.float32)
    return Image.fromarray((d + (l - d) * a.clip(0, 1)).astype(np.uint8)).convert("RGBA")

def scrim(img, top=0.55, bottom=0.8, mid=0.15):
    """Darken top/bottom for legibility on photos."""
    y = np.linspace(0, 1, H, dtype=np.float32)
    k = np.maximum(top * np.clip(1 - y / 0.25, 0, 1) ** 1.5, bottom * np.clip((y - 0.45) / 0.55, 0, 1) ** 1.3) + mid
    a = np.asarray(img.convert("RGB"), np.float32) * (1 - k[:, None, None])
    return Image.fromarray(a.clip(0, 255).astype(np.uint8)).convert("RGBA")


# ---------------------------------------------------------- marker stuff
def marker_stroke(draw, pts, width, color, progress=1.0, seed=1, samples=90):
    """Hand-drawn marker stroke along a polyline, drawn up to `progress`."""
    if progress <= 0:
        return
    rnd = random.Random(seed)
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg)
    n = max(2, int(samples * progress))
    jit = [rnd.uniform(-1, 1) for _ in range(samples + 2)]
    for k in range(n):
        dist = total * progress * k / (n - 1)
        acc, i = 0, 0
        while i < len(seg) - 1 and acc + seg[i] < dist:
            acc += seg[i]; i += 1
        t = (dist - acc) / seg[i] if seg[i] else 0
        x = lerp(pts[i][0], pts[i + 1][0], t)
        y = lerp(pts[i][1], pts[i + 1][1], t) + jit[k] * width * 0.06
        r = width / 2 * (0.9 + 0.12 * jit[k + 1])
        draw.ellipse((x - r, y - r * 0.82, x + r, y + r * 0.82), fill=color)

def rough_rect(w, h, color, seed=3, jag=7):
    """Rectangle with torn / hand-cut edges, as an RGBA image."""
    rnd = random.Random(seed)
    im = Image.new("RGBA", (w + 2 * jag, h + 2 * jag), (0, 0, 0, 0))
    pts = []
    steps = max(4, w // 40)
    for i in range(steps + 1):
        pts.append((jag + w * i / steps, jag + rnd.uniform(-jag, jag)))
    for i in range(1, 5):
        pts.append((jag + w + rnd.uniform(-jag, jag) * .6, jag + h * i / 5))
    for i in range(steps, -1, -1):
        pts.append((jag + w * i / steps, jag + h + rnd.uniform(-jag, jag)))
    for i in range(4, 0, -1):
        pts.append((jag + rnd.uniform(-jag, jag) * .6, jag + h * i / 5))
    ImageDraw.Draw(im).polygon(pts, fill=color)
    return im


# ------------------------------------------------------------------ media
SLOTS = {
    # name: (label shown on placeholder, palette, needed frames)
    "cousins":  ("the two cousins (photo)",      (BLUE, ORANGE),   100),
    "moto":     ("moto-taxi ride clip",          (ORANGE, YELLOW), 40),
    "capoeira": ("capoeira roda clip",           (GREEN, YELLOW),  40),
    "streets":  ("streets / people clip",        (YELLOW, ORANGE), 40),
    "rooftop":  ("rooftop view clip",            (BLUE, YELLOW),   40),
    "tour":     ("tour with guests clip",        (GREEN, BLUE),    130),
}
EXTS_IMG = (".jpg", ".jpeg", ".png", ".webp")
EXTS_VID = (".mp4", ".mov", ".m4v", ".webm")

def slot_cfg():
    p = MEDIA / "slots.json"
    return json.loads(p.read_text()) if p.exists() else {}

def find_media(name):
    for ext in EXTS_IMG + EXTS_VID:
        for cand in (MEDIA / f"{name}{ext}", MEDIA / f"{name}{ext.upper()}"):
            if cand.exists():
                return cand
    return None

def cover_crop(img, w, h, fx=0.5, fy=0.5):
    s = max(w / img.width, h / img.height)
    im = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    x = int((im.width - w) * fx); y = int((im.height - h) * fy)
    return im.crop((x, y, x + w, y + h))

def placeholder_art(name, w=W, h=H):
    """Poster-style placeholder: hillside of stacked houses under a halftone sun."""
    label, (c1, c2), _ = SLOTS[name]
    rnd = random.Random(hash(name) & 0xffff)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    top = np.array(c1, np.float32) * 0.55; bot = np.array(BG, np.float32)
    arr = np.broadcast_to(top + (bot - top) * yy ** 0.8, (h, w, 3)).copy()
    im = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(im)
    # halftone sun
    cx, cy, R = w * rnd.uniform(.3, .7), h * .30, 300
    for gy in range(int(cy - R), int(cy + R), 22):
        for gx in range(int(cx - R), int(cx + R), 22):
            dd = math.hypot(gx - cx, gy - cy) / R
            if dd < 1:
                r = 9 * (1 - dd ** 3)
                d.ellipse((gx - r, gy - r, gx + r, gy + r), fill=c2)
    # hill of houses (back to front)
    for layer in range(3):
        base = h * (0.52 + 0.12 * layer)
        shade = [0.30, 0.18, 0.08][layer]
        x = -40
        while x < w + 40:
            bw = rnd.randint(70, 150)
            slope = (w / 2 - x) / w * 220 * (1 - layer * .3)
            bh = rnd.randint(110, 260)
            ytop = base - bh + slope * 0.6 + rnd.randint(-30, 30)
            col = tuple(int(lerp(BG[i], rnd.choice([c1, c2, WHITE, GREEN, BLUE, ORANGE])[i], shade)) for i in range(3))
            d.rectangle((x, ytop, x + bw, h), fill=col)
            for wy in range(int(ytop + 22), int(min(h, ytop + bh + 200)), 46):
                for wx in range(x + 16, x + bw - 24, 38):
                    if rnd.random() < 0.35:
                        d.rectangle((wx, wy, wx + 16, wy + 20), fill=(255, 214, 90) if layer < 2 else (60, 60, 70))
            x += bw + rnd.randint(-6, 4)
    if name == "cousins":                     # two silhouettes front & centre
        for i, ox in enumerate((-170, 170)):
            hx, hy = w / 2 + ox, h * .42 + (20 if i else 0)
            d.rounded_rectangle((hx - 150, hy + 120, hx + 150, h * .78), 120, fill=INK, outline=WHITE, width=6)
            d.ellipse((hx - 92, hy - 92, hx + 92, hy + 92), fill=INK, outline=WHITE, width=6)
    # slot tag
    tag = f"PLACEHOLDER  ·  media/{name}.jpg|mp4  ·  {label}"
    f = font(ROUND8, 28)
    tw = f.getlength(tag)
    d.rounded_rectangle((w / 2 - tw / 2 - 22, SAFE_TOP + 140, w / 2 + tw / 2 + 22, SAFE_TOP + 192), 26, fill=(0, 0, 0, 200))
    d.text((w / 2, SAFE_TOP + 166), tag, font=f, fill=(255, 255, 255, 230), anchor="mm")
    return im.convert("RGB")


class Media:
    """One media slot -> frame(i) returns an RGB 1080x1920 image."""

    def __init__(self, name):
        self.name = name
        cfg = slot_cfg().get(name, {})
        self.fx, self.fy = cfg.get("focus", [0.5, 0.5])
        self.start = float(cfg.get("in", 0))
        self.path = find_media(name)
        self.kind = None if self.path is None else ("video" if self.path.suffix.lower() in EXTS_VID else "image")
        self.cache = BUILD / "media" / name
        self._still = None

    def prepare(self):
        need = SLOTS[self.name][2]
        if self.kind == "video":
            self.cache.mkdir(parents=True, exist_ok=True)
            for old in self.cache.glob("*.jpg"):
                old.unlink()
            vf = (f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H}:(iw-{W})*{self.fx}:(ih-{H})*{self.fy}")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(self.start), "-i", str(self.path),
                            "-t", str(need / FPS + 0.2), "-vf", vf, "-an", "-q:v", "2",
                            str(self.cache / "%04d.jpg")], check=True)

    def frame(self, i):
        if self.kind == "video":
            files = sorted(self.cache.glob("*.jpg"))
            if files:
                return Image.open(files[min(max(i, 0), len(files) - 1)]).convert("RGB")
        if self._still is None:
            if self.kind == "image":
                from PIL import ImageOps
                self._still = cover_crop(ImageOps.exif_transpose(Image.open(self.path)).convert("RGB"), W, H, self.fx, self.fy)
            else:
                self._still = placeholder_art(self.name)
        return self._still

    def view(self, i, zoom=1.0, dx=0.0, dy=0.0):
        """Ken-Burns view: zoom >= 1 crops in; dx/dy pan in px of output."""
        im = self.frame(i)
        if zoom <= 1.0005 and not dx and not dy:
            return im.copy()
        cw, ch = W / zoom, H / zoom
        x0 = (W - cw) / 2 - dx / zoom; y0 = (H - ch) / 2 - dy / zoom
        x0 = min(max(x0, 0), W - cw); y0 = min(max(y0, 0), H - ch)
        return im.transform((W, H), Image.EXTENT, (x0, y0, x0 + cw, y0 + ch), Image.BICUBIC)


M = {k: Media(k) for k in SLOTS}

def logo_img():
    p = find_media("logo")
    return Image.open(p).convert("RGBA") if p and p.suffix.lower() in EXTS_IMG else None


# ----------------------------------------------------------------- camera
# (frame, zoom punch, shake) — every hit sits on the 120 BPM grid
HITS = [
    (0, .07, 14), (8, .03, 6), (15, .05, 10), (30, .05, 10), (38, .03, 6), (45, .04, 8), (53, .07, 14),
    (60, .03, 8), (75, .02, 5),
    (90, .09, 18), (120, .08, 14), (150, .10, 18),
    (180, .04, 8), (210, .05, 10), (240, .03, 6), (270, .04, 8),
    (300, .05, 10), (330, .05, 10), (360, .05, 10), (390, .02, 4),
    (420, .05, 10), (435, .05, 10), (450, .06, 12), (465, .03, 8),
    (480, .08, 14), (495, .05, 8),
]
HOLD_FROM = 510          # final 1 s is perfectly still (screenshot-friendly)

def camera(f):
    if f >= HOLD_FROM:
        return 1.0, 0.0, 0.0, 0.0
    z, sx, sy, r = 1.025, 0.0, 0.0, 0.0
    for hf, punch, shake in HITS:
        t = f - hf
        if 0 <= t < 16:
            z += punch * math.exp(-t / 3.2)
            k = math.exp(-t / 3.0)
            rnd = random.Random(hf * 31 + t)
            sx += rnd.uniform(-1, 1) * shake * k
            sy += rnd.uniform(-1, 1) * shake * k
            r += rnd.uniform(-1, 1) * 0.5 * k
    # constant hand-held drift
    sx += 2.2 * math.sin(f * 0.37); sy += 2.2 * math.cos(f * 0.29)
    return z, sx, sy, r

def apply_camera(img, f):
    z, tx, ty, rot = camera(f)
    if z == 1.0 and not tx and not ty and not rot:
        return img
    a = math.radians(rot); c, s = math.cos(a) / z, math.sin(a) / z
    cx, cy = W / 2, H / 2
    # inverse map: input = R(-rot)/z * (out - C - T) + C
    ox, oy = -cx - tx, -cy - ty
    coeffs = (c, s, c * ox + s * oy + cx, -s, c, -s * ox + c * oy + cy)
    return img.transform((W, H), Image.AFFINE, coeffs, Image.BICUBIC)


# ------------------------------------------------------------- particles
def confetti(seed, n, cx, cy):
    rnd = random.Random(seed)
    cols = [YELLOW, GREEN, BLUE, ORANGE, WHITE]
    parts = []
    for _ in range(n):
        a = rnd.uniform(-math.pi * 0.95, -math.pi * 0.05)
        sp = rnd.uniform(20, 58)
        parts.append(dict(x=cx + rnd.uniform(-300, 300), y=cy + rnd.uniform(-40, 40),
                          vx=math.cos(a) * sp * 1.2, vy=math.sin(a) * sp, rot=rnd.uniform(0, 360),
                          vr=rnd.uniform(-25, 25), s=rnd.uniform(10, 26), kind=rnd.choice("rrrcl"),
                          col=rnd.choice(cols), life=rnd.uniform(22, 34)))
    return parts

def draw_confetti(canvas, parts, t):
    if t < 0:
        return
    d = ImageDraw.Draw(canvas)
    for p in parts:
        if t > p["life"]:
            continue
        drag = (1 - 0.86 ** t) / (1 - 0.86)            # air drag on velocity
        x = p["x"] + p["vx"] * drag
        y = p["y"] + p["vy"] * drag + 1.5 * t * t * 0.5
        s = p["s"] * (1 - (t / p["life"]) ** 3)
        a = math.radians(p["rot"] + p["vr"] * t)
        if p["kind"] == "c":
            d.ellipse((x - s / 2, y - s / 2, x + s / 2, y + s / 2), fill=p["col"])
        elif p["kind"] == "l":
            dx, dy = math.cos(a) * s, math.sin(a) * s
            d.line((x - dx, y - dy, x + dx, y + dy), fill=p["col"], width=6)
        else:
            w2, h2 = s / 2, s / 4 * (1 + abs(math.sin(a * 2)))
            pts = [(-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2)]
            d.polygon([(x + px * math.cos(a) - py * math.sin(a), y + px * math.sin(a) + py * math.cos(a)) for px, py in pts], fill=p["col"])


# ================================================================ SCENES
_BG = None
def bg():
    global _BG
    if _BG is None:
        _BG = halftone_bg()
    return _BG.copy()

# ---- 0:00-0:03  HOOK -------------------------------------------------
HOOK_LINES = [("NOT A TOUR", [("NOT", 0), ("A", 8), ("TOUR", 15)]),
              ("BY SOMEONE", [("BY", 30), ("SOMEONE", 38)]),
              ("FROM OUTSIDE.", [("FROM", 45), ("OUTSIDE.", 53)])]
HOOK_W = W - 2 * SIDE + 10

def hook_layout():
    rows, y = [], 0
    for line, words in HOOK_LINES:
        size = fit_size(line, HEAD, HOOK_W)
        f = font(HEAD, size)
        x0, y0, x1, y1 = f.getbbox(line)
        rows.append((line, words, size, y, y1 - y0))
        y += (y1 - y0) + 44
    total = y - 44
    top = (SAFE_TOP + SAFE_BOT) / 2 - total / 2 - 30
    return [(l, w, s, top + yy, hh) for l, w, s, yy, hh in rows]

def scene_hook(lf, still=False):
    c = bg()
    for li, (line, words, size, ytop, hh) in enumerate(hook_layout()):
        f = font(HEAD, size)
        x_line = (W - f.getlength(line)) / 2
        cy = ytop + hh / 2
        last = li == 2
        # yellow highlight swipe behind the last line (beat 4)
        if last:
            sw = e_out_expo(prog(lf, 60, 7))
            if sw > 0:
                bar = rough_rect(int(HOOK_W + 40), int(hh + 56), YELLOW, seed=11, jag=9)
                cut = bar.crop((0, 0, max(1, int(bar.width * sw)), bar.height))
                paste(c, cut, x_line - 20 + cut.width / 2 - 9, cy + 2, rot=0)
        for word, start in words:
            st = slam(lf, start, s0=1.3 if start == 0 else 1.75, r0=random.Random(start).choice([-9, 8, -6, 7]), r1=0)
            if st is None:
                continue
            sc, rot = st
            prefix = line[: line.index(word)]
            wx = x_line + f.getlength(prefix) + f.getlength(word) / 2
            if start == 0:            # frame 1 lands dead centre, then settles into the line
                wx = lerp(W / 2, wx, e_out_cubic(prog(lf, 2, 6)))
            on_yellow = last and lf >= 62
            col = INK if on_yellow else WHITE
            sh = None if on_yellow else (0, 0, 0, 255)
            im = text_img(word, HEAD, round(size), col, sh, (0, 9) if sh else (0, 0))
            paste(c, im, wx, cy, sc, rot)
    # tiny marker scribble under "NOT" on the hit before the whip
    if lf >= 66:
        l0 = hook_layout()[0]
        f = font(HEAD, l0[2]); x0 = (W - f.getlength(l0[0])) / 2
        d = ImageDraw.Draw(c)
        p = e_out_cubic(prog(lf, 66, 6))
        yb = l0[3] + l0[4] + 16
        marker_stroke(d, [(x0, yb), (x0 + f.getlength("NOT") * .5, yb + 8), (x0 + f.getlength("NOT"), yb - 4)], 16, GREEN, p, seed=5)
    return c

# ---- 0:03-0:06  BORN / RAISED / STILL HERE ---------------------------
BORN = [("BORN HERE.", 0), ("RAISED HERE.", 30), ("STILL HERE.", 60)]
BIG_W = W - 2 * SIDE
BIG = fit_size("RAISED HERE.", HEAD, BIG_W)
SMALL = 0.56
BIG_CY = 1300           # big slot centre (inside 3:4 grid crop & safe zone)
_CONF = None

def born_positions(lf):
    """Return [(text, scale, cy, alpha)] for the stacking animation."""
    big_h = font(HEAD, BIG).getbbox("H")[3] - font(HEAD, BIG).getbbox("H")[1]
    small_h = big_h * SMALL
    gap = 22
    out = []
    for i, (t, start) in enumerate(BORN):
        if lf < start:
            continue
        # how many phrases arrived after this one
        steps = []
        for j in range(i + 1, len(BORN)):
            steps.append(e_out_expo(prog(lf, BORN[j][1], 6)))
        sc = 1.0; cy = BIG_CY
        if steps:
            sc = lerp(1.0, SMALL, steps[0])
            # position stack: each later phrase pushes this one up
            depth = sum(steps)
            cy = BIG_CY - big_h / 2 - gap - small_h / 2 - (small_h + gap) * max(0, depth - 1)
            cy = lerp(BIG_CY, cy, min(1, steps[0])) if depth < 1 else cy
        out.append((t, sc, cy, i))
    return out

def scene_born(lf, cover=False):
    global _CONF
    z = 1.06 + 0.06 * (lf / 90)
    photo = M["cousins"].view(lf, zoom=z, dy=-10 * lf / 90)
    c = scrim(halftone_photo(photo, 0.22), top=0.45, bottom=0.82, mid=0.05)
    # location pin
    p = 1.0 if cover else e_out_back(prog(lf, 4, 7))
    if p > 0:
        pin = pin_img("ROCINHA · RIO DE JANEIRO")
        paste(c, pin, SIDE + pin.width / 2 * p, SAFE_TOP + 70, p, -2 * (1 - p) - 1.5)
    for text, sc, cy, i in born_positions(lf):
        start = BORN[i][1]
        st = (1.0, 0.0) if cover else slam(lf, start, s0=1.9, r0=[-6, 6, -5][i], r1=[-2, 0, -1.5][i])
        if st is None:
            continue
        s2, rot = st
        col = YELLOW if text.startswith("STILL") else WHITE
        im = text_img(text, HEAD, round(BIG), col, (0, 0, 0, 255), (0, 12))
        paste(c, im, W / 2, cy, sc * s2, rot if sc > .99 else 0)
        if text.startswith("STILL") and lf >= 68:
            d = ImageDraw.Draw(c)
            hw = im.width / 2 - 20
            pe = e_out_cubic(prog(lf, 68, 7))
            yb = cy + im.height / 2 + 8
            marker_stroke(d, [(W / 2 - hw, yb + 6), (W / 2, yb - 4), (W / 2 + hw, yb + 2)], 22, GREEN, pe, seed=9)
    if _CONF is None:
        _CONF = confetti(7, 110, W / 2, BIG_CY - 80)
    draw_confetti(c, _CONF, 17 if cover else lf)
    return c

@lru_cache(maxsize=None)
def pin_img(text, fill=GREEN, color=INK):
    f = font(ROUND, 40)
    tw = int(f.getlength(text))
    im = Image.new("RGBA", (tw + 100, 74), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, 73), 37, fill=fill)
    # pin glyph
    d.ellipse((22, 14, 50, 42), fill=color); d.polygon([(24, 34), (48, 34), (36, 60)], fill=color)
    d.ellipse((31, 23, 41, 33), fill=fill)
    d.text((66, 37), text, font=f, fill=color, anchor="lm")
    return im

# ---- 0:06-0:10  MONTAGE ----------------------------------------------
LABELS = [("MOTO-TAXI", "UP THE HILL", YELLOW, INK),
          ("CAPOEIRA WITH", "MESTRE MANEL", GREEN, INK),
          ("REAL STREETS,", "REAL PEOPLE", ORANGE, INK),
          ("ROOFTOP", "VIEWS", BLUE, WHITE)]

@lru_cache(maxsize=None)
def tape_label(text, fill, color, size=96):
    t = text_img(text, HEAD, size, color)
    tape = rough_rect(t.width + 44, t.height + 26, fill, seed=len(text), jag=6)
    tape.alpha_composite(t, (28, 19))
    return tape

def draw_label(c, k, lf, y=1330):
    """Two-line tape label sliding in from the left, wiping out at the end."""
    l1, l2, fill, col = LABELS[k]
    for j, line in enumerate((l1, l2)):
        im = tape_label(line, fill, col)
        t_in = e_out_back(prog(lf, 2 + 2 * j, 7), 1.8)
        t_out = e_in_expo(prog(lf, 26, 4))
        x = lerp(-im.width, SIDE + im.width / 2 - 10, t_in) + t_out * W
        rot = [-3, 1.5][j]
        paste(c, im, x + j * 30, y + j * 128, 1.0, rot)

def montage_clip(k, lf):
    """Render clip k at local frame lf (0..29)."""
    if k == 0:                                            # MOTO — full bleed, push in
        c = halftone_photo(M["moto"].view(lf, zoom=1.04 + lf * .004, dy=-lf * 2), 0.12)
        c = scrim(c, top=.3, bottom=.55, mid=0)
    elif k == 1:                                          # CAPOEIRA — poster card slam
        c = bg()
        cw, ch = 880, 1220
        clip = cover_crop(M["capoeira"].frame(lf), cw, ch)
        card = Image.new("RGBA", (cw + 36, ch + 36), WHITE + (255,))
        card.paste(clip, (18, 18))
        shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rectangle((0, 0, *card.size), fill=GREEN)
        st = slam(lf, 0, s0=1.35, r0=9, r1=-2.5, dur=8)
        s, r = st
        paste(c, shadow, W / 2 + 22, 900 + 26, s, r)
        paste(c, card, W / 2, 900, s, r)
    elif k == 2:                                          # STREETS — inside the letters, then zoom through
        clip = halftone_photo(M["streets"].view(lf, zoom=1.06), 0.12)
        mask = real_mask_at(lf)
        if mask is None:
            c = scrim(clip, top=.3, bottom=.55, mid=0)
        else:
            c = Image.new("RGBA", (W, H), YELLOW + (255,))
            c.paste(clip, (0, 0), mask)
            if lf < 10:
                # small hand-written tag while it's still lettering
                d = ImageDraw.Draw(c)
                d.text((W / 2, 1290), "rocinha · vidigal", font=font(MARKER, 64), fill=INK, anchor="mm")
    else:                                                 # ROOFTOP — slow pan
        c = halftone_photo(M["rooftop"].view(lf, zoom=1.12, dx=40 - lf * 2.6), 0.12)
        c = scrim(c, top=.3, bottom=.55, mid=0)
    if k != 2:
        draw_label(c, k, lf)
    elif lf >= 8:
        draw_label(c, k, lf - 8)
    return c

_REAL = None
def real_mask_at(lf):
    """'REAL' lettering mask, zooming through the E's stem from lf 7."""
    global _REAL
    if _REAL is None:
        size = fit_size("REAL", HEAD, W - 2 * SIDE + 30)
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        d.text((W / 2, 860), "REAL", font=font(HEAD, size), fill=255, anchor="mm")
        # zoom anchor = deepest interior point of the letters (iterated erosion)
        er = m.copy()
        for _ in range(30):
            nxt = er.filter(ImageFilter.MinFilter(9))
            if not nxt.getbbox():
                break
            er = nxt
        a = np.asarray(er)
        ys, xs = np.nonzero(a)
        i = np.argmin(np.abs(xs - W * 0.38) + np.abs(ys - 860) * .2)
        _REAL = (m, (float(xs[i]), float(ys[i])))
    m, (ax, ay) = _REAL
    t = e_in_expo(prog(lf, 6, 7))
    if t >= 1:
        return None
    s = 1 + t * 40
    # zoom about anchor, sliding the anchor to screen centre
    cx, cy = lerp(ax, W / 2, t), lerp(ay, H / 2, t)
    inv = (1 / s, 0, ax - cx / s, 0, 1 / s, ay - cy / s)
    if s < 1.001:
        return m
    return m.transform((W, H), Image.AFFINE, inv, Image.BILINEAR)

def scene_montage(lf):
    k, l = min(lf // 30, 3), lf - min(lf // 30, 3) * 30
    # whip (horizontal) from STREETS into ROOFTOP across the 0:09 beat
    if 86 <= lf < 90:
        return whip(montage_clip(2, l), montage_clip(3, 0), lf - 86, "left")
    img = montage_clip(k, l)
    if l == 0 and k in (1, 2):        # one-frame flash on the hard cuts
        img = Image.blend(img, Image.new("RGBA", (W, H), WHITE + (255,)), 0.55)
    return img

# ---- 0:10-0:14  DIFERENCIAIS CARDS -----------------------------------
CARDS = [(["100% PRIVATE"], YELLOW, "lock", -2.0, 0),
         (["SMALL GROUPS,", "JUST YOU"], GREEN, "group", 1.5, 30),
         (["ALL-INCLUSIVE"], ORANGE, "check", -1.2, 60)]

def icon(kind, col, size=118):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=INK)
    c = size / 2
    if kind == "lock":
        d.rounded_rectangle((c - 30, c - 4, c + 30, c + 36), 8, fill=col)
        d.arc((c - 21, c - 40, c + 21, c + 8), 180, 360, fill=col, width=10)
        d.line((c - 21, c - 16, c - 21, c - 2), fill=col, width=10)
        d.line((c + 21, c - 16, c + 21, c - 2), fill=col, width=10)
        d.ellipse((c - 6, c + 8, c + 6, c + 20), fill=INK)
    elif kind == "group":
        for ox, oy, r in ((-27, 6, 13), (27, 6, 13), (0, -2, 17)):
            d.ellipse((c + ox - r, c + oy - r - 14, c + ox + r, c + oy + r - 14), fill=col)
            d.pieslice((c + ox - r * 1.9, c + oy + 6, c + ox + r * 1.9, c + oy + 6 + r * 3.6), 180, 360, fill=col)
    else:
        d.line((c - 30, c + 2, c - 8, c + 26, c + 32, c - 24), fill=col, width=16, joint="curve")
    return im

@lru_cache(maxsize=None)
def card_img(i):
    lines, col, ic, _, _ = CARDS[i]
    size = 104
    texts = [text_img(t, HEAD, size, INK) for t in lines]
    cw = W - 2 * SIDE
    th = sum(t.height for t in texts) + 6 * (len(texts) - 1)
    ch = max(170, th + 50)
    card = Image.new("RGBA", (cw + 16, ch + 18), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((14, 16, cw + 14, ch + 16), 30, fill=INK)        # hard shadow
    d.rounded_rectangle((0, 0, cw, ch), 30, fill=col)
    ico = icon(ic, col)
    card.alpha_composite(ico, (34, (ch - ico.height) // 2))
    y = (ch - th) // 2
    for t in texts:
        card.alpha_composite(t, (182, y)); y += t.height + 6
    return card

def speed_lines(c, cx, cy, t, col, seed):
    if not 0 <= t < 1:
        return
    d = ImageDraw.Draw(c); rnd = random.Random(seed)
    for _ in range(10):
        a = rnd.uniform(0, math.tau); r0 = 300 + 220 * e_out_cubic(t); ln = 70 * (1 - t)
        x0, y0 = cx + math.cos(a) * r0 * 1.6, cy + math.sin(a) * r0 * .55
        d.line((x0, y0, x0 + math.cos(a) * ln * 1.6, y0 + math.sin(a) * ln * .55), fill=col, width=8)

def scene_cards(lf):
    clip = M["tour"].view(lf, zoom=1.15 - lf * 0.0008)
    c = duotone(clip.filter(ImageFilter.GaussianBlur(3)), dark=(4, 6, 22), light=(30, 66, 210), gain=0.75)
    c = halftone_photo(c, 0.3, period=12)
    ys = []
    y = 560
    for i in range(3):
        im = card_img(i); ys.append(y + im.height / 2); y += im.height + 36
    for i, (lines, col, ic, rot, start) in enumerate(CARDS):
        if lf < start:
            continue
        t = prog(lf, start, 8)
        s = lerp(0.25, 1.0, e_out_back(t, 2.4))
        r = lerp([14, -12, 10][i], rot, e_out_cubic(t))
        speed_lines(c, W / 2, ys[i], (lf - start) / 8, col, i)
        paste(c, card_img(i), W / 2, ys[i], s, r)
    # languages line
    if lf >= 90:
        t = e_out_back(prog(lf, 90, 7))
        lang = lang_img()
        paste(c, lang, W / 2, lerp(ys[-1] + 230, ys[-1] + 170, t), 1, 0, clamp01(t * 1.5))
    return c

@lru_cache(maxsize=None)
def lang_img():
    f = font(ROUND, 50)
    parts = [("English", WHITE), ("  ·  ", YELLOW), ("Español", WHITE), ("  ·  ", YELLOW), ("Português", WHITE)]
    tw = int(sum(f.getlength(p) for p, _ in parts))
    im = Image.new("RGBA", (tw + 130, 92), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, 91), 46, fill=(0, 0, 0, 205), outline=WHITE, width=3)
    # speech bubble glyph
    d.rounded_rectangle((26, 22, 76, 60), 12, fill=YELLOW); d.polygon([(36, 58), (50, 58), (34, 72)], fill=YELLOW)
    x = 98
    for p, col in parts:
        d.text((x, 46), p, font=f, fill=col, anchor="lm"); x += f.getlength(p)
    return im

# ---- 0:14-0:16  NO BIG BUS. NO STRANGERS. NO SCRIPT. --------------------
NO_LINES = [("NO ", "BIG BUS.", 0), ("NO ", "STRANGERS.", 15), ("NO ", "SCRIPT.", 30)]
_YBG = None

def yellow_bg():
    global _YBG
    if _YBG is None:
        _YBG = halftone_bg(base=YELLOW, ink=(236, 190, 0), period=26, angle=15, vignette=0.12)
    return _YBG.copy()

def scene_contrast(lf):
    c = yellow_bg()
    size = fit_size("NO STRANGERS.", HEAD, W - 2 * SIDE)
    f = font(HEAD, size)
    hh = f.getbbox("H")[3] - f.getbbox("H")[1]
    gap = 70
    top = (SAFE_TOP + SAFE_BOT) / 2 - (3 * hh + 2 * gap) / 2 - 20
    d = ImageDraw.Draw(c)
    for i, (no, word, start) in enumerate(NO_LINES):
        st = slam(lf, start, s0=1.6, r0=[-8, 7, -6][i], r1=0, dur=6)
        if st is None:
            continue
        s, r = st
        line = no + word
        cy = top + i * (hh + gap) + hh / 2
        x0 = (W - f.getlength(line)) / 2
        im = text_img(line, HEAD, round(size), INK)
        paste(c, im, W / 2, cy, s, r)
        # marker strike-through over the noun
        p = e_out_cubic(prog(lf, start + 7, 5))
        if p > 0:
            wx0 = x0 + f.getlength(no) - 10
            wx1 = x0 + f.getlength(line) + 12
            col = [BLUE, ORANGE, BLUE][i]
            if i == 0:
                pts = [(wx0, cy + 10), (wx1, cy - 14)]
            elif i == 1:
                pts = [(wx0, cy - 18), (wx1, cy - 30), (wx1 - 30, cy + 22), (wx0 + 10, cy + 18)]
            else:
                n = 7; pts = [(lerp(wx0, wx1, j / n), cy + (-36 if j % 2 else 30)) for j in range(n + 1)]
            marker_stroke(d, pts, 30 if i != 2 else 22, col, p, seed=20 + i, samples=140)
    return c

# ---- 0:16-0:18  CTA --------------------------------------------------
def scene_cta(lf):
    c = bg()
    logo = logo_img()
    # wordmark / logo
    st = slam(lf, 0, s0=1.8, r0=-6, r1=0)
    if logo is not None:
        sc = min(860 / logo.width, 520 / logo.height)
        paste(c, logo, W / 2, 640, sc * st[0], st[1])
    else:
        size = fit_size("ROCINHA", HEAD, W - 2 * SIDE - 40)
        im = text_img("ROCINHA", HEAD, round(size), WHITE, (0, 0, 0, 255), (0, 10))
        paste(c, im, W / 2, 560, *st)
        p = e_out_cubic(prog(lf, 5, 7))
        if p > 0:
            cz = text_img("Cousins", MARKER, 190, YELLOW, (0, 0, 0, 255), (6, 8))
            crop = cz.crop((0, 0, max(1, int(cz.width * p)), cz.height))
            paste(c, crop, W / 2 + 70 - cz.width / 2 + crop.width / 2, 790, 1, -6)
        if lf >= 10:
            sub = sub_img()
            paste(c, sub, W / 2, 935, 1, 0, clamp01((lf - 10) / 4))
    # DM TO BOOK
    st = slam(lf, 15, s0=1.7, r0=5, r1=-1.5)
    if st:
        dm = dm_img()
        paste(c, dm, W / 2, 1110, *st)
    # arrow bouncing on the beat, then resting for the hold
    if lf >= 18:
        t = prog(lf, 18, 5)
        b = abs(math.sin(math.pi * (lf - 15) / 15)) * 26 if lf < 30 else 0
        paste(c, arrow_img(), W / 2, 1300 + b - 40 * (1 - e_out_back(t)), 1, 0, clamp01(t * 2))
    if lf >= 22:
        t = e_out_back(prog(lf, 22, 6))
        paste(c, handle_img(), W / 2, 1468, lerp(.6, 1, t), 0, clamp01(t * 2))
    return c

@lru_cache(maxsize=None)
def sub_img():
    f = font(ROUND8, 40)
    t = "PRIVATE TOURS  ·  ROCINHA & VIDIGAL"
    im = Image.new("RGBA", (int(f.getlength(t)) + 10, 60), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((5, 30), t, font=f, fill=(225, 225, 225), anchor="lm")
    return im

@lru_cache(maxsize=None)
def dm_img():
    t = text_img("DM TO BOOK", HEAD, 150, INK)
    tape = rough_rect(t.width + 70, t.height + 44, GREEN, seed=42, jag=8)
    out = Image.new("RGBA", (tape.width + 14, tape.height + 14), (0, 0, 0, 0))
    sh = Image.new("RGBA", tape.size, (0, 0, 0, 0)); sh.putalpha(tape.getchannel("A"))
    out.alpha_composite(sh, (14, 14)); out.alpha_composite(tape, (0, 0))
    out.alpha_composite(t, (43, 30))
    return out

@lru_cache(maxsize=None)
def arrow_img():
    im = Image.new("RGBA", (180, 190), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    marker_stroke(d, [(90, 10), (86, 70), (92, 128)], 34, YELLOW, 1, seed=3, samples=60)
    marker_stroke(d, [(28, 100), (90, 168), (152, 98)], 34, YELLOW, 1, seed=4, samples=80)
    return im

@lru_cache(maxsize=None)
def handle_img():
    f = font(ROUND, 66)
    t = "@rocinhacousins"
    tw = int(f.getlength(t))
    im = Image.new("RGBA", (tw + 80, 110), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((3, 3, im.width - 4, 106), 53, outline=WHITE, width=5)
    d.text((im.width / 2, 55), t, font=f, fill=WHITE, anchor="mm")
    return im


# ------------------------------------------------------------ transitions
def whip(a, b, i, direction="up", n=4):
    """Whip-pan from image a to image b. i = 0..n-1 frames before the cut."""
    p = [0.06, 0.24, 0.55, 0.86][i]
    dp = [0.10, 0.20, 0.31, 0.31][i]
    A = np.asarray(a.convert("RGB"), np.float32)
    B = np.asarray(b.convert("RGB"), np.float32)
    axis = 0 if direction == "up" else 1
    strip = np.concatenate([A, B], axis=axis)
    L = (H if axis == 0 else W)
    blur = dp * L * 0.55
    acc = np.zeros_like(A)
    K = 28
    for k in range(K):
        o = int(np.clip(p * L + (k / (K - 1) - 0.5) * blur, 0, L))
        acc += strip[o:o + L] if axis == 0 else strip[:, o:o + L]
    return Image.fromarray((acc / K).astype(np.uint8)).convert("RGBA")


SCENES = [(0, 90, scene_hook), (90, 180, scene_born), (180, 300, scene_montage),
          (300, 420, scene_cards), (420, 480, scene_contrast), (480, 540, scene_cta)]
WHIPS = {90: "up", 180: "up", 300: "left", 420: "up", 480: "left"}

def scene_at(f):
    for s, e, fn in SCENES:
        if s <= f < e:
            return s, e, fn
    return SCENES[-1]

def raw_frame(f):
    for b, direction in WHIPS.items():
        if b - 4 <= f < b:
            s, e, fn = scene_at(b - 1)
            s2, e2, fn2 = scene_at(b)
            return whip(fn(f - s), fn2(0), f - (b - 4), direction)
    s, e, fn = scene_at(f)
    return fn(f - s)

def render_frame(f):
    global GRAIN
    if GRAIN is None:
        GRAIN = [_grain(i) for i in range(4)]
    img = apply_camera(raw_frame(f), f).convert("RGB")
    a = np.asarray(img, np.int16)
    g = GRAIN[0 if f >= HOLD_FROM else (f // 2) % 4]
    a = (a + g[..., None]).clip(0, 255).astype(np.uint8)
    return a.tobytes()


# ------------------------------------------------------------------- cover
def render_cover(path):
    img = scene_born(20, cover=True).convert("RGB")
    a = (np.asarray(img, np.int16) + _grain(9)[..., None] // 2).clip(0, 255).astype(np.uint8)
    Image.fromarray(a).save(path, quality=95)


# -------------------------------------------------------------------- main
def prepare_media():
    BUILD.mkdir(exist_ok=True)
    for m in M.values():
        m.prepare()
    status = {k: (str(m.path.name) if m.path else "PLACEHOLDER") for k, m in M.items()}
    status["logo"] = find_media("logo").name if find_media("logo") else "wordmark (no media/logo.png)"
    return status

def contact_sheet(frames, path, cols=6):
    th_w, th_h = 270, 480
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * th_w, rows * (th_h + 30)), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(frames):
        im = Image.frombytes("RGB", (W, H), render_frame(f)).resize((th_w, th_h), Image.BILINEAR)
        x, y = (i % cols) * th_w, (i // cols) * (th_h + 30)
        sheet.paste(im, (x, y + 30))
        d.text((x + 6, y + 6), f"f{f}  {f / FPS:.2f}s", fill=(255, 255, 255), font=font(ROUND8, 20))
    sheet.save(path)

def main():
    OUT.mkdir(exist_ok=True)
    status = prepare_media()
    print("media:", json.dumps(status, indent=1))
    if "--cover" in sys.argv:
        render_cover(OUT / "cover_born-here.jpg"); return
    if "--stills" in sys.argv:
        frames = [int(x) for x in sys.argv[sys.argv.index("--stills") + 1].split(",")] if len(sys.argv) > sys.argv.index("--stills") + 1 else \
            [0, 4, 10, 20, 40, 58, 66, 87, 92, 105, 125, 160, 178, 186, 200, 214, 242, 250, 258, 275, 288, 304, 340, 380, 405, 422, 432, 447, 470, 482, 500, 539]
        contact_sheet(frames, BUILD / "contact.jpg"); print("contact sheet ->", BUILD / "contact.jpg"); return
    render_cover(OUT / "cover_born-here.jpg")
    silent = BUILD / "video_silent.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "18M", "-bufsize", "36M", "-profile:v", "high", "-level", "4.2",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for i, buf in enumerate(pool.imap(render_frame, range(N), chunksize=4)):
            ff.stdin.write(buf)
            if i % 60 == 0:
                print(f"  frame {i}/{N}", flush=True)
    ff.stdin.close(); ff.wait()
    print("video ->", silent)

if __name__ == "__main__":
    main()

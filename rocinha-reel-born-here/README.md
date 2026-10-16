# @rocinhacousins · "BORN HERE" Reel

1080×1920 · 9:16 · 30 fps · 18 s · H.264 · 120 BPM beat grid

## Files in `out/`
- `rocinhacousins_born-here_guide-music.mp4`: full piece with an original groove (made from scratch here, no samples, nothing copyrighted) + SFX. Use it to preview the timing.
- `rocinhacousins_born-here_sfx-only.mp4`: just the hits/whooshes. **Post this one** and add a trending track in Instagram's music picker, keeping the original audio at ~20–30%.
- `rocinhacousins_born-here_no-audio.mp4`: silent.
- `cover_born-here.jpg`: clean cover frame (no shake/blur), text inside the 3:4 profile-grid crop.

## Rebuild after adding your photos/clips
```bash
./build.sh            # ~2–3 min: audio, frames, all exports, cover
python3 render.py --stills   # fast contact sheet -> build/contact.jpg
```
Requirements: Python 3 + Pillow + NumPy, ffmpeg. See `media/README.md` for file names.

## Cue sheet (1 beat = 0.5 s = 15 frames · bar = 2 s)
| Time | Beat | Scene | Hits |
|---|---|---|---|
| 0:00.0 | 0 | HOOK: black, "NOT" slams centre | impact |
| 0:00.27 / 0:00.5 | ½ / 1 | "A" · "TOUR" | impact |
| 0:01.0 / 0:01.27 | 2 / 2½ | "BY" · "SOMEONE" | impact |
| 0:01.5 / 0:01.77 | 3 / 3½ | "FROM" · "OUTSIDE." | impact |
| 0:02.0 | 4 | yellow highlight swipe on "FROM OUTSIDE." | snare build starts |
| 0:02.87 → 0:03.0 | 6 | whip up into the cousins photo | groove drops |
| 0:03.0 | 6 | "BORN HERE." + confetti + pin "ROCINHA · RIO DE JANEIRO" | impact |
| 0:04.0 | 8 | "RAISED HERE." (previous line shrinks up) | impact |
| 0:05.0 | 10 | "STILL HERE." in yellow + green marker underline | impact |
| 0:06 / 0:07 / 0:08 / 0:09 | 12/14/16/18 | MOTO · CAPOEIRA (poster card) · REAL (clip inside letters → zoom-through) · ROOFTOP | cut every 2 beats |
| 0:10 / 0:11 / 0:12 | 20/22/24 | cards: 100% PRIVATE · SMALL GROUPS, JUST YOU · ALL-INCLUSIVE | pop |
| 0:13 | 26 | "English · Español · Português" | pop |
| 0:14 / 0:14.5 / 0:15 | 28/29/30 | NO BIG BUS. · NO STRANGERS. · NO SCRIPT. (yellow screen), marker strike ¼ beat later | impact + marker |
| 0:16 | 32 | CTA: ROCINHA + "Cousins", DM TO BOOK, arrow, @rocinhacousins | impact |
| 0:17–0:18 | 34–36 | final frame frozen 1 s (screenshot) → loops on the downbeat into frame 1 | — |

Safe zones respected: nothing important above y=250 or below y=1580.

Fonts: Anton (OFL), Nunito (OFL), Permanent Marker (Apache 2.0); licenses in `fonts/`.

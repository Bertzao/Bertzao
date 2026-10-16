#!/usr/bin/env bash
# One command: audio + frames + the three exports + cover.
set -euo pipefail
cd "$(dirname "$0")"
python3 music.py
python3 render.py
V=build/video_silent.mp4
mux() { ffmpeg -v error -y -i "$V" -i "$1" -map 0:v -map 1:a -c:v copy -af loudnorm=I=-14:TP=-1.5:LRA=11 -ar 48000 -c:a aac -b:a 192k -shortest -movflags +faststart "$2"; }
mux build/music.wav out/rocinhacousins_born-here_guide-music.mp4
mux build/sfx.wav   out/rocinhacousins_born-here_sfx-only.mp4
cp "$V" out/rocinhacousins_born-here_no-audio.mp4
echo "done -> out/"

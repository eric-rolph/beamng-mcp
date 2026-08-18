#!/usr/bin/env bash
# Match-start countdown: KSHMR "3, 2, 1, Let's Go" (player-supplied,
# 2026-08-13), 1.875 s stereo 44.1k. One-shot faked on a loop profile the
# proven CHIEF way: 2.5 s of silent tail appended, the GE runtime stops the
# source at countdown_stop_seconds (2.6) inside the pad so the loop can never
# wrap audibly. The ring goes LIVE at countdown_go_seconds (1.65) - tune that
# spec knob, not this file, if GO lands early or late in play.
#
# Derived-lua law reminder: the vehicle-side player ships from spec.py
# VEHICLE_LUA_EXTRA at build time; this script only bakes the ogg.
set -euo pipefail
cd "$(dirname "$0")"
ffmpeg -y -v error \
  -i "C:/Users/ericr/Downloads/KSHMR_Numbers_321_Let_s_Go.wav" \
  -af "volume=0.9,apad=pad_dur=2.5,alimiter=limit=0.891:level=false" \
  -ar 44100 -ac 2 -c:a libvorbis -q:a 5 \
  "../mod/vehicles/ericrolph_sumo_gyro_platform/sound/ericrolph_sumo_gyro_platform_countdown.ogg"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 \
  "../mod/vehicles/ericrolph_sumo_gyro_platform/sound/ericrolph_sumo_gyro_platform_countdown.ogg"

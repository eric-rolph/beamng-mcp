#!/usr/bin/env bash
# Shutdown one-shot mix (player 2026-08-12): "if the E-Stop is pressed
# or when the sequence ends, play these sounds (mix it so one lays over
# the other)". Two personal-library one-shots from ~/Downloads (NOT
# committed), layered from sample zero:
#
#   FF_FM_foley_mechanical_machine_processing_shut_down.wav
#                                                   5.93 s  44.1k/24 stereo
#   SciFiPowerDown_S08SF.403.wav                   10.89 s  96k/24 stereo
#
# The mechanical clunk-and-coast carries the first ~6 s, the sci-fi
# power-down whine underneath runs the full ~10.9 s and lands the tail.
# Same policy as the spinup mix: trimmed unity-ish gains, amix
# normalize=0, brickwall at -1 dBFS, short tail fade for a clean end.
#
# 2.5 s SILENT PAD (apad): the only proven-audible SFX path is the
# LOOP profile (see VEHICLE_LUA_EXTRA in spec.py), so the runtime fakes
# a one-shot by stopping the source at 11.2 s - inside this pad, after
# the 0.45 s tail fade has already ended the audible clip at ~10.9 s.
# The stop clock runs on GE dtSim while the audio plays in real time,
# so the pad is generous: the 13.39 s wrap is 2.2 s of clock drift
# away, wide enough for slow-motion play.
#
# GE trigger: the spin-FX falling edge in the LUA_BEHAVIOR template
# (E-Stop press, sequence complete, eject done/timeout, or the 191.0 s
# end-of-clip handoff) queues playShutdown() on the vehicle side, then
# stopShutdown() 11.2 s later. BOTH LUA FILES UNDER mod/ ARE DERIVED -
# edit the spec.py templates, never mod/lua (b145 lesson: a whole
# shutdown wiring pass vanished in the next build).
set -euo pipefail
SRC="$HOME/Downloads"
DST="$(dirname "$0")/../mod/vehicles/ericrolph_gforce_centrifuge/sound"
mkdir -p "$DST"
ffmpeg -y \
  -i "$SRC/FF_FM_foley_mechanical_machine_processing_shut_down.wav" \
  -i "$SRC/SciFiPowerDown_S08SF.403.wav" \
  -filter_complex "\
[0:a]volume=0.85[a0];\
[1:a]aresample=44100,volume=0.85[a1];\
[a0][a1]amix=inputs=2:duration=longest:normalize=0,\
afade=t=out:st=10.45:d=0.45,apad=pad_dur=2.5,\
alimiter=limit=0.891:level=false[mix]" \
  -map "[mix]" -ac 2 -ar 44100 -c:a libvorbis -q:a 6 \
  "$DST/ericrolph_gforce_centrifuge_shutdown.ogg"
ffprobe -v error -show_entries format=duration -show_entries stream=channels,sample_rate \
  -of default=noprint_wrappers=1 "$DST/ericrolph_gforce_centrifuge_shutdown.ogg"

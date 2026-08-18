#!/usr/bin/env bash
# Spin-up soundtrack mix (player 2026-08-09): three ~63 s stereo FX stems
# played "in unison ... mixed into a single stereo sound file". Sources are
# personal-library one-shots living in ~/Downloads (NOT committed); re-run
# this from repo root if they move. Output lands directly in the mod tree
# and ships with the zip.
#
#   PMMTH_Fx_Loop_122bpm_07.wav                    62.95 s  44.1k/24 stereo
#   T_UHT7_126_fx_oneshot_riser_galaxy_clock.wav   62.86 s  44.1k/24 stereo
#   T_TSDR2_128_fx_oneshot_riser_ahhhhhh.wav       63.75 s  44.1k/24 stereo
#
# Mix policy: unity-ish gains trimmed to leave limiter headroom, sum with
# amix normalize=0 (preserve the stems' own dynamics - two of them ARE
# risers), brickwall at -1 dBFS, 1.5 s tail fade so a natural end never
# cliffs. Stereo is preserved end to end.
#
# 3x TIME-STRETCH (player 2026-08-09d: "stretch out the audio clip 3X
# since it seems to take roughly 3 minutes to get up to speed"): the live
# ladder runs ~3 real minutes (the old ~60 s numbers were stepped-rig sim
# time), so the build now spans ~191 s. atempo only accepts 0.5..2.0 per
# stage - chained 0.5 x 0.66667 = 1/3, tempo-only, pitch preserved.
#
# HELICOPTER HEAD (2026-08-11): "have this sound start as soon as the
# centrifuge starts spinning and then the sound that's currently attached
# comes up in volume to full sound 5 seconds in". So the rotor one-shot
# is a FOURTH stem at natural speed (NOT stretched - it is the machine
# audibly winding up, and stretching a 70 s rotor start to 3.5 minutes
# would turn the whole gesture to mush), full level from sample zero,
# while the 191 s riser bed fades in across 0..5 s and takes over as the
# rotor dissolves. The rotor's own 6 s tail fade hands off to a bed that
# is already at full, so there is no hole in the middle.
#
# ROTOR EXIT AT 17 s (player 2026-08-12): "keep the sound layered in the
# same way, but fade out the helicopter sound at 17 seconds for it being
# layered over the other longer sound". The rotor is now strictly the
# opening gesture: full from sample zero, fade begins at 17 s and is gone
# by 21 s, leaving the stretched riser bed (at full since 5 s) to carry
# the remaining ~3 minutes alone.
#
#   SPLC-0831_FX-Oneshot-Propeller-Helicopter-Start-Accelerating.wav
#                                                  70.40 s  48k/16 stereo
#
# The 3.5 s soundtrack start delay in spec.py went to 0.0 in the same
# round: the delay existed so "the drum audibly winds up first, then the
# music enters", and the rotor head now IS that wind-up. Leaving both
# would have started the rotor 3.5 s late and pushed the bed's arrival
# out to 8.5 s.
#
# NOTE the rotor wav carries an embedded cover-art (mjpeg) stream and is
# 48 kHz against the stems' 44.1 kHz - hence the explicit [3:a] audio
# selector and the aresample before it meets the bed.
set -euo pipefail
SRC="$HOME/Downloads"
DST="$(dirname "$0")/../mod/vehicles/ericrolph_gforce_centrifuge/sound"
mkdir -p "$DST"
ffmpeg -y \
  -i "$SRC/PMMTH_Fx_Loop_122bpm_07.wav" \
  -i "$SRC/T_UHT7_126_fx_oneshot_riser_galaxy_clock.wav" \
  -i "$SRC/T_TSDR2_128_fx_oneshot_riser_ahhhhhh.wav" \
  -i "$SRC/SPLC-0831_FX-Oneshot-Propeller-Helicopter-Start-Accelerating.wav" \
  -filter_complex "\
[0:a]volume=0.80[a0];\
[1:a]volume=0.85[a1];\
[2:a]volume=0.85[a2];\
[a0][a1][a2]amix=inputs=3:duration=longest:normalize=0,\
atempo=0.5,atempo=0.66667,\
afade=t=in:st=0:d=5,afade=t=out:st=189.7:d=1.5[bed];\
[3:a]aresample=44100,volume=0.90,\
afade=t=in:st=0:d=0.03,afade=t=out:st=17:d=4[heli];\
[bed][heli]amix=inputs=2:duration=longest:normalize=0,\
alimiter=limit=0.891:level=false[mix]" \
  -map "[mix]" -ac 2 -ar 44100 -c:a libvorbis -q:a 6 \
  "$DST/ericrolph_gforce_centrifuge_spinup.ogg"
ffprobe -v error -show_entries format=duration -show_entries stream=channels,sample_rate \
  -of default=noprint_wrappers=1 "$DST/ericrolph_gforce_centrifuge_spinup.ogg"

#!/usr/bin/env bash
# Announcer calls: three takes per corner of each kind (player-supplied).
#   welcome_<side>_<take>  as a car claims that corner and lights the board
#   back_<side>_<take>     as that same car re-enters for the next round
#   win_<side>_<take>      as that corner takes the match
# The runtime rolls a take at random each time, so the same event never
# sounds canned twice running.
#
# LEVEL LIVES IN THE FILE. The takes arrive 5-10 dB down with several dB of
# spread between them, so a flat gain would both waste headroom and leave one
# take quieter than its siblings. Each is measured and lifted to -1 dBFS:
# every call lands at the same loudness, as loud as the format allows without
# clipping (2026-08-14 player round: "twice as loud").
#
# One-shots are faked the proven CHIEF way: the only audible path in this pack
# is a LOOP profile, so silence is appended and the GE runtime stops each
# source at call_stop_seconds. ONE stop time serves every clip, which means
# the pad has to satisfy the LONGEST take and the SHORTEST clip at once: the
# 3.70 s stop must be past the longest take (3.40 s, a welcome-back) and
# still inside the shortest clip's pad. The shortest take is 0.48 s, so the
# pad is 4.0 s - it was 2.5 s, which the welcome-backs would have overrun.
# Silence costs almost nothing in vorbis.
#
# Derived-lua law reminder: the vehicle-side player ships from spec.py
# VEHICLE_LUA_EXTRA at build time; this script only bakes the oggs.
set -euo pipefail
cd "$(dirname "$0")"
out="../mod/vehicles/ericrolph_sumo_gyro_platform/sound"
src_dir="C:/Users/ericr/Downloads"
mkdir -p "$out"

bake() {  # $1 = source wav, $2 = output tag
  local src="$1" tag="$2" peak gain
  peak=$(ffmpeg -hide_banner -i "$src" -af volumedetect -f null NUL 2>&1 \
    | sed -n 's/.*max_volume: \(-\?[0-9.]*\) dB.*/\1/p')
  gain=$(awk -v p="$peak" 'BEGIN { printf "%.2f", -1.0 - p }')
  ffmpeg -y -v error -i "$src" \
    -af "volume=${gain}dB,apad=pad_dur=4.0,alimiter=limit=0.95:level=false" \
    -ar 44100 -ac 2 -c:a libvorbis -q:a 5 \
    "$out/ericrolph_sumo_gyro_platform_${tag}.ogg"
  printf '%-18s peak %6s dB  gain %+6s dB  ->  %s s\n' "$tag" "$peak" "$gain" \
    "$(ffprobe -v error -show_entries format=duration \
       -of default=noprint_wrappers=1:nokey=1 \
       "$out/ericrolph_sumo_gyro_platform_${tag}.ogg")"
}

for side in east west; do
  case "$side" in
    east) title="East"; caps="EAST" ;;
    west) title="West"; caps="WEST" ;;
  esac
  for take in 1 2 3; do
    bake "$(ls "$src_dir/${title}_Wins_take${take}_"*.wav)" "win_${side}_${take}"
    bake "$(ls "$src_dir/Welcome_competitor_from_The_${caps}_take${take}_"*.wav)" \
      "welcome_${side}_${take}"
  done
  # Welcome-BACK, six takes. Take 6 is round-two only - the runtime narrows
  # the roll outside round two - but it is baked like any other.
  for take in 1 2 3 4 5 6; do
    bake "$src_dir/${title}_Welcome_Back_0${take}.wav" "back_${side}_${take}"
  done
done

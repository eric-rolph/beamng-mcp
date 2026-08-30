"""Synthesize the fuse tick. Deterministic, from source, like everything else.

The tick is the mod's heartbeat: the whole fuse reads through it, because the
design ships no numeric countdown anywhere. It is authored as a LOOP and the
GE runtime drives ``obj:setVolumePitch`` on the carrier's own VM, so pitch
scales playback rate and tone together — one knob gives the accelerating,
rising cue the blueprint wanted, on the only playback path this pack has ever
proven audible (obj:createSFXSource + AudioDefaultLoop3D, centrifuge audio
mechanism v3). v1 drove ``Engine.Audio.playOnce`` with the game's REVERSE
BEEP — a looping FMOD event with no stop handle — and every tick leaked one
immortal beeper: the player filmed beeps at 0.45–1.1 s spacing against an
authored 1.55 s interval, and they were still beeping after the mod was gone.

Tick v2 (2026-08-29, the "utterly wow" audio-critic round). The v1 loop was
a clinical kitchen timer: sine beep + octave at t=0, stationary hiss under
it. Three measured findings drove this cut:

- The sizzle band (2400–7800 Hz) transposes ABOVE HEARING at panic pitch —
  at the 3.4 ceiling it sits at 8.2–26.5 kHz, so the fuse layer vanished
  exactly when it should sound angriest. A second band at 700–2000 Hz stays
  present across the whole 0.6→5.0 transposition span.
- One event per loop makes urgency pure tempo. The TOCK at t=0.65 — the
  same voice a falling minor third down (950→800 Hz) — turns the loop into
  a two-note motif: grandfather clock at slow pitch, a 5 Hz two-note alarm
  trill at panic pitch. Two notes is the MAXIMUM motif that survives three
  octaves of transposition without going chipmunk; this IS the hot potato
  song.
- Nothing lived below 570 Hz, so full throttle masked the whole cue. The
  thock (190 Hz damped body knock) and the 70 Hz sub pulse give the beat a
  chest channel that reads through engine roar.

Layer map (all transients fully decayed inside [0, 1.20] s; the noise beds
are periodic by construction, so the loop seam cannot pop):

  thock    t=0     190 Hz damped sine (tau 28 ms) + 5 ms click — the
                   potato's own woody voice under the tick.
  sub      t=0     one 70 Hz cycle under a 55 ms Hann — subwoofer-only at
                   min pitch, a thump at panic pitch.
  tick     t=0     950 Hz partial stack (1, 2, 3, 4.2x — the inharmonic
                   4.2 adds a faint metallic bell edge) with an organic
                   950→930 Hz droop over its first 80 ms.
  tock     t=0.65  the same stack at 800 Hz, -5.5 dB — the minor third.
  sizzle   bed     2400–7800 Hz + the 700–2000 Hz presence band.
  snaps    10x     Poisson-seeded 6 ms crackle bursts, 3–5 kHz centres —
                   the fuse SPITS instead of hissing.

Loop length 1.3 s: at pitch 0.85 the interval is the authored slow tick
(1.53 s) with the tone still warm; at the 3.4 pitch ceiling it is a 2.6 Hz
alarm shriek. The runtime maps interval -> pitch = LOOP / interval, clamped.

Output: assets/sound/ericrolph_hot_potato_tick.ogg (shipped via SHIP_ASSETS).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 44100
LOOP_SECONDS = 1.3
TICK_HZ = 950.0
TOCK_HZ = 800.0
TOCK_AT = 0.65


def _env(n: int, attack_s: float, decay_s: float) -> np.ndarray:
    t = np.arange(n) / RATE
    attack = np.clip(t / max(attack_s, 1e-4), 0.0, 1.0)
    decay = np.exp(-np.maximum(t - attack_s, 0.0) / max(decay_s, 1e-4))
    return attack * decay


def _periodic_bandnoise(rng, n: int, low: float, high: float) -> np.ndarray:
    """Band-limited noise that tiles seamlessly (built from a periodic basis)."""

    spectrum = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    shoulder = np.exp(
        -(((freqs - np.clip(freqs, low, high)) / (0.25 * (high - low) + 1e-9)) ** 2)
    )
    out = np.fft.irfft(spectrum * shoulder, n)
    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out


def _stack(rng, hz: float, seconds: float, decay_s: float, chirp: float) -> np.ndarray:
    """The tick voice: partials 1/2/3/4.2x with a linear droop over 80 ms."""

    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    # Instantaneous frequency droops `chirp` Hz over the first 80 ms, then
    # holds — integrate for phase so the droop is a glide, not a step.
    droop = np.where(t < 0.08, t / 0.08, 1.0) * chirp
    inst = hz - droop
    phase = 2.0 * np.pi * np.cumsum(inst) / RATE
    voice = (
        np.sin(phase)
        + 0.32 * np.sin(2.0 * phase)
        + 0.12 * np.sin(3.0 * phase)
        + 0.07 * np.sin(4.2 * phase)
    )
    return voice * _env(n, 0.003, decay_s)


def main() -> None:
    rng = np.random.default_rng(0xF0053)  # FUSE
    n_total = int(LOOP_SECONDS * RATE)
    mix = np.zeros(n_total)

    # -- thock: the potato's body, a woody knock under the tick ------------
    n_thock = int(0.12 * RATE)
    t = np.arange(n_thock) / RATE
    thock = np.sin(2.0 * np.pi * 190.0 * t) * np.exp(-t / 0.028)
    mix[:n_thock] += thock * 0.50
    n_click = int(0.005 * RATE)
    click = _periodic_bandnoise(rng, n_click, 1200.0, 3000.0)
    mix[:n_click] += click * 0.20

    # -- sub pulse: the chest channel that survives engine roar ------------
    n_sub = int(0.055 * RATE)
    t = np.arange(n_sub) / RATE
    sub = np.sin(2.0 * np.pi * 70.0 * t) * np.hanning(n_sub)
    mix[:n_sub] += sub * 0.35

    # -- tick and tock: the two-note song ----------------------------------
    tick = _stack(rng, TICK_HZ, 0.30, 0.045, 20.0)
    mix[: len(tick)] += tick * 0.85
    tock = _stack(rng, TOCK_HZ, 0.30, 0.038, 14.0)
    start = int(TOCK_AT * RATE)
    mix[start : start + len(tock)] += tock * 0.45

    # -- sizzle: the lit fuse, in two bands so it never goes ultrasonic ----
    sizzle_hi = _periodic_bandnoise(rng, n_total, 2400.0, 7800.0)
    sizzle_mid = _periodic_bandnoise(rng, n_total, 700.0, 2000.0)
    # Slow amplitude wander (integer number of cycles, so it loops too).
    wander = 0.75 + 0.25 * np.sin(
        2.0 * np.pi * 3.0 * np.arange(n_total) / n_total
    )
    mix += (sizzle_hi * 0.055 + sizzle_mid * 0.035) * wander

    # -- crackle snaps: the fuse spits — all inside [0.05, 1.20] s so the
    # -- seam needs no wrap handling ---------------------------------------
    for _ in range(10):
        at = rng.uniform(0.05, 1.20)
        centre = rng.uniform(3000.0, 5000.0)
        amp = rng.uniform(0.03, 0.09)
        n_snap = int(0.030 * RATE)
        snap = _periodic_bandnoise(rng, n_snap, centre - 500.0, centre + 500.0)
        snap *= np.exp(-np.arange(n_snap) / (0.010 * RATE))
        offset = int(at * RATE)
        mix[offset : offset + n_snap] += snap * amp

    # -- glue: soft clip, normalize to -1 dB -------------------------------
    mix = np.tanh(mix * 1.1)
    mix *= 10 ** (-1.0 / 20.0) / np.max(np.abs(mix))

    out = Path(__file__).resolve().parents[1] / "assets" / "sound"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "ericrolph_hot_potato_tick.ogg"
    sf.write(target, mix.astype(np.float32), RATE, format="OGG", subtype="VORBIS")
    print(f"wrote {target} ({target.stat().st_size} bytes, {LOOP_SECONDS}s loop)")


if __name__ == "__main__":
    main()

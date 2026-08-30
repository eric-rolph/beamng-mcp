"""Synthesize the potato's steam whistle. Deterministic, from source.

v2.5, the acoustic brief (2026-08-30): the carried potato is a microwave
potato venting through a slit in its skin — an aerodynamic orifice whistle,
acoustically a miniature tea kettle with organic tissue for a body. The
brief's measured character, layer by layer:

- High-frequency and piercing: fundamental at 2150 Hz — inside the
  1.5–4 kHz band where human hearing is most sensitive, and it STAYS inside
  that band across the runtime's whole live pitch span (the glissando floor
  0.72 puts it at 1548 Hz).
- Fluttering organic vibrato: the skin flap. A 27 Hz flutter modulates both
  frequency (±2%) and amplitude (±15%), with a slower 0.9 Hz wander so the
  warble never reads as a test tone. Harmonics at 2x/3x plus a faint
  INHARMONIC 2.7x partial — flexible tissue, not machined brass.
- Wet, sputtering undertone: a 3–7 kHz hiss bed breathing with the flutter,
  a 300–800 Hz boiling murmur, and a handful of brief droplet dropouts.
- Temporal dynamics live in the RUNTIME, not the file: the loop begins
  abruptly at peak on pickup, obj:setVolumePitch glides it down as the fuse
  runs out (the downward glissando of subsiding pressure), and the baked
  SPUTTER one-shot below is the staccato finish — the whistle collapsing
  into rhythmic chirps and wheezes before falling silent.

Both files ride the pack's only proven raw-ogg channel: sources created in
the carrier's vehicle VM (obj:createSFXSource — AudioDefaultLoop3D for the
loop, AudioDefault3D for the one-shot; the latter is the stock NON-looping
description the game's own crash and glass one-shots use).

Loop seams: the carrier frequency (2150 * 2.2 s = 4730 cycles) and every
modulator run an INTEGER number of cycles over the loop, and the noise beds
are periodic by construction, so the wrap cannot pop.

Output: assets/sound/ericrolph_hot_potato_whistle.ogg (2.2 s loop) and
assets/sound/ericrolph_hot_potato_sputter.ogg (2.8 s one-shot), shipped via
SHIP_ASSETS.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 44100
LOOP_SECONDS = 2.2
SPUTTER_SECONDS = 2.8
F0 = 2150.0  # 2150 * 2.2 = 4730 exact cycles: the seam is phase-clean
FLUTTER_CYCLES = 60  # 60 / 2.2 s = 27.3 Hz — the skin flap
WANDER_CYCLES = 2  # 0.9 Hz drift under the flutter


def _periodic_bandnoise(rng, n: int, low: float, high: float) -> np.ndarray:
    """Band-limited noise that tiles seamlessly (periodic basis)."""

    spectrum = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    shoulder = np.exp(
        -(((freqs - np.clip(freqs, low, high)) / (0.25 * (high - low) + 1e-9)) ** 2)
    )
    out = np.fft.irfft(spectrum * shoulder, n)
    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out


def _whistle_voice(t: np.ndarray, f0: float, flutter_hz: float, wander_hz: float,
                   fm_depth: float, glide: np.ndarray | None = None) -> np.ndarray:
    """The orifice tone: flutter-FM fundamental + harmonics + inharmonic 2.7x."""

    wobble = (np.sin(2.0 * np.pi * flutter_hz * t)
              + 0.4 * np.sin(2.0 * np.pi * wander_hz * t))
    inst = f0 * (1.0 + fm_depth * wobble)
    if glide is not None:
        inst = inst * glide
    phase = 2.0 * np.pi * np.cumsum(inst) / RATE
    return (
        np.sin(phase)
        + 0.22 * np.sin(2.0 * phase)
        + 0.07 * np.sin(3.0 * phase)
        + 0.05 * np.sin(2.7 * phase)
    )


def make_loop(rng) -> np.ndarray:
    n = int(LOOP_SECONDS * RATE)
    t = np.arange(n) / RATE
    flutter_hz = FLUTTER_CYCLES / LOOP_SECONDS
    wander_hz = WANDER_CYCLES / LOOP_SECONDS

    voice = _whistle_voice(t, F0, flutter_hz, wander_hz, 0.02)
    # The flap also gates LOUDNESS: ±15% at flutter rate, breathing at the
    # wander rate underneath.
    tremolo = (0.85 + 0.15 * np.sin(2.0 * np.pi * flutter_hz * t + 1.1)) * (
        0.92 + 0.08 * np.sin(2.0 * np.pi * wander_hz * t + 0.4)
    )
    mix = voice * tremolo * 0.62

    # Wet steam: the hiss breathes WITH the flap — same valve, same air.
    hiss = _periodic_bandnoise(rng, n, 3000.0, 7000.0)
    mix += hiss * 0.09 * tremolo
    # Boiling murmur under everything.
    murmur = _periodic_bandnoise(rng, n, 300.0, 800.0)
    mix += murmur * 0.05 * (0.8 + 0.2 * np.sin(2.0 * np.pi * wander_hz * t + 2.0))

    # Droplet sputters: brief dips where a starch droplet chokes the slit —
    # all strictly inside the loop so the seam needs no wrap handling.
    for _ in range(4):
        at = rng.uniform(0.15, LOOP_SECONDS - 0.15)
        width = rng.uniform(0.012, 0.030)
        depth = rng.uniform(0.35, 0.6)
        centre = int(at * RATE)
        half = int(width * RATE)
        window = np.hanning(2 * half)
        mix[centre - half : centre + half] *= 1.0 - depth * window

    mix = np.tanh(mix * 1.1)
    return mix * (10 ** (-1.5 / 20.0) / np.max(np.abs(mix)))


def make_sputter(rng) -> np.ndarray:
    n = int(SPUTTER_SECONDS * RATE)
    t = np.arange(n) / RATE
    mix = np.zeros(n)

    # Phase 1 (0–1.1 s): the whistle failing — pitch glides 1.0 -> 0.8 as
    # the exit velocity drops below resonance, flutter deepening.
    n1 = int(1.1 * RATE)
    t1 = t[:n1]
    glide = 1.0 - 0.2 * (t1 / 1.1) ** 1.4
    voice = _whistle_voice(t1, F0, 27.0, 3.0, 0.028 + 0.02 * (t1 / 1.1), glide)
    tremolo = 0.8 + 0.2 * np.sin(2.0 * np.pi * 27.0 * t1)
    fade = 1.0 - 0.35 * (t1 / 1.1)
    mix[:n1] += voice * tremolo * fade * 0.6

    # Phase 2 (1.1–2.4 s): continuous resonance is gone — intermittent
    # rhythmic chirps and wheezes, each weaker, lower and further apart.
    at = 1.1
    pitch_frac = 0.78
    amp = 0.55
    gap = 0.09
    while at < 2.35:
        dur = rng.uniform(0.05, 0.13)
        n_chirp = int(dur * RATE)
        tc = np.arange(n_chirp) / RATE
        # Each chirp bends slightly UP then dies: a wheeze, not a beep.
        bend = 1.0 + 0.06 * np.sin(np.pi * tc / dur)
        chirp = _whistle_voice(tc, F0 * pitch_frac, 30.0, 5.0, 0.04, bend)
        env = np.sin(np.pi * np.clip(tc / dur, 0.0, 1.0)) ** 0.7
        breath = _periodic_bandnoise(rng, n_chirp, 2000.0, 6000.0)
        offset = int(at * RATE)
        end = min(offset + n_chirp, n)
        mix[offset:end] += (chirp * 0.75 + breath * 0.4)[: end - offset] * env[: end - offset] * amp
        at += dur + gap
        gap *= rng.uniform(1.35, 1.75)
        pitch_frac *= rng.uniform(0.93, 0.98)
        amp *= rng.uniform(0.62, 0.8)

    # Phase 3: the last wet breath — hiss decaying to true silence.
    n3 = n - int(2.3 * RATE)
    tail = _periodic_bandnoise(rng, n3, 1500.0, 5000.0)
    mix[int(2.3 * RATE) :] += tail * 0.12 * np.exp(-np.arange(n3) / (0.14 * RATE))

    # A hard-zero landing: the staccato finish must END, not loop or click.
    n_out = int(0.03 * RATE)
    mix[-n_out:] *= np.linspace(1.0, 0.0, n_out)

    mix = np.tanh(mix * 1.1)
    return mix * (10 ** (-1.5 / 20.0) / np.max(np.abs(mix)))


def main() -> None:
    rng = np.random.default_rng(0x57EA0)  # STEAM
    out = Path(__file__).resolve().parents[1] / "assets" / "sound"
    out.mkdir(parents=True, exist_ok=True)

    loop = make_loop(rng)
    target = out / "ericrolph_hot_potato_whistle.ogg"
    sf.write(target, loop.astype(np.float32), RATE, format="OGG", subtype="VORBIS")
    print(f"wrote {target} ({target.stat().st_size} bytes, {LOOP_SECONDS}s loop)")

    sputter = make_sputter(rng)
    target = out / "ericrolph_hot_potato_sputter.ogg"
    sf.write(target, sputter.astype(np.float32), RATE, format="OGG", subtype="VORBIS")
    print(f"wrote {target} ({target.stat().st_size} bytes, {SPUTTER_SECONDS}s one-shot)")


if __name__ == "__main__":
    main()

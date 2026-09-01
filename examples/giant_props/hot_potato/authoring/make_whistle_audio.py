"""Synthesize the potato's steam vent. Deterministic, from source.

v2.6, re-voiced (2026-08-30, player report: "the noise is annoying now and
doesn't sound like a potato in a microwave releasing steam, let's tone it
down in its annoyance and make it sound more realistic"). The v2.5 build
took the acoustic brief's "high-frequency and piercing" literally: a 2150 Hz
sine stack with FM flutter — a smoke-alarm of a kettle. A real microwave
potato venting through a slit in its skin is not a tone at all: it is
NARROWBAND NOISE — turbulent air shaped by a soft fleshy orifice — over a
broadband hiss, with wet sputtering. The re-voice inverts the mix:

- The steam hiss bed is now the PRIMARY voice: broadband 1.2–9 kHz noise
  with a falling spectral tilt (energy lives low-mid, not up at the pain
  band).
- The "whistle" is a soft FORMANT, not a tone: the same periodic noise
  through a gentle resonance near 2.6 kHz. It reads as pitched — so the
  runtime's downward glissando still lands as subsiding pressure — without
  a sine anywhere near the foreground.
- A barely-there tonal ghost (a quiet flutter-FM fundamental at the formant
  centre) keeps the pitch trajectory legible under the noise. It sits ~18 dB
  below the old voice.
- Flutter is gentler and slower: ~19 Hz amplitude breathing at ±8%, organic
  wander underneath — the skin flap as texture, not vibrato shriek.
- Wet body: a 150–500 Hz simmering murmur with slow bubbling AM, sparse
  droplet POPS (millisecond noise bursts) and choke dropouts.
- Level: the loop peaks at -9 dBFS (v2.5 peaked at -1.5) and the runtime
  drive gain came down with it — quieter in the mix by design, not just
  by knob.

Temporal dynamics still live in the RUNTIME: the loop starts at pickup,
obj:setVolumePitch glides it down as the fuse runs out, and the baked
SPUTTER one-shot is the finish — now a wet die-off of intermittent steam
puffs rather than tonal chirps.

Both files ride the pack's only proven raw-ogg channel (createSFXSource in
the carrier's VM; AudioDefaultLoop3D for the loop, AudioDefault3D for the
one-shot). Loop seams: every noise bed is periodic by construction and
every LFO runs an integer number of cycles over the loop, so the wrap
cannot pop.

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
FORMANT_HZ = 2600.0  # the vent's soft resonance centre
GHOST_HZ = 2600.0  # 2600 * 2.2 = 5720 exact cycles: the seam is phase-clean
FLUTTER_CYCLES = 42  # 42 / 2.2 s = 19.1 Hz — the skin flap, as breathing
WANDER_CYCLES = 2  # 0.9 Hz drift under the flutter
PEAK_DB = -9.0  # the tone-down half of "tone it down"


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


def _tilted_hiss(rng, n: int) -> np.ndarray:
    """The steam bed: 1.2–9 kHz noise with a falling tilt (~ -6 dB/oct).

    Pink-ish shaping keeps the energy in the low-mids where escaping steam
    actually lives, instead of piling it at the 2–4 kHz sensitivity peak
    that made v2.5 read as an alarm.
    """

    spectrum = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    band = np.exp(-(((freqs - np.clip(freqs, 1200.0, 9000.0)) / 900.0) ** 2))
    tilt = 1.0 / np.sqrt(np.maximum(freqs, 1200.0) / 1200.0)
    out = np.fft.irfft(spectrum * band * tilt, n)
    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out


def _ghost_tone(t: np.ndarray, f0: float, flutter_hz: float, wander_hz: float,
                glide: np.ndarray | None = None) -> np.ndarray:
    """The faint pitch anchor: one soft flutter-FM partial, no harmonic stack."""

    wobble = (np.sin(2.0 * np.pi * flutter_hz * t)
              + 0.4 * np.sin(2.0 * np.pi * wander_hz * t))
    inst = f0 * (1.0 + 0.012 * wobble)
    if glide is not None:
        inst = inst * glide
    phase = 2.0 * np.pi * np.cumsum(inst) / RATE
    return np.sin(phase) + 0.10 * np.sin(2.0 * phase)


def _droplet_pops(rng, mix: np.ndarray, count: int, level: float,
                  lo_s: float, hi_s: float) -> None:
    """Sparse millisecond noise bursts: moisture spitting through the slit."""

    n = len(mix)
    for _ in range(count):
        at = rng.uniform(lo_s, hi_s)
        dur = rng.uniform(0.002, 0.006)
        n_pop = max(8, int(dur * RATE))
        burst = rng.standard_normal(n_pop) * np.hanning(n_pop)
        offset = int(at * RATE)
        end = min(offset + n_pop, n)
        mix[offset:end] += burst[: end - offset] * level * rng.uniform(0.5, 1.0)


def make_loop(rng) -> np.ndarray:
    n = int(LOOP_SECONDS * RATE)
    t = np.arange(n) / RATE
    flutter_hz = FLUTTER_CYCLES / LOOP_SECONDS
    wander_hz = WANDER_CYCLES / LOOP_SECONDS

    # The flap gates loudness gently: ±8% breathing, slower wander under it.
    tremolo = (0.92 + 0.08 * np.sin(2.0 * np.pi * flutter_hz * t + 1.1)) * (
        0.94 + 0.06 * np.sin(2.0 * np.pi * wander_hz * t + 0.4)
    )

    # Primary voice: the steam bed.
    mix = _tilted_hiss(rng, n) * 0.85 * tremolo
    # The vent formant: narrow noise around the resonance — the "whistle"
    # a listener names, without a tone to grate on.
    formant = _periodic_bandnoise(rng, n, 2300.0, 3000.0)
    mix += formant * 0.34 * tremolo
    # The pitch anchor, buried: ~18 dB under where the v2.5 voice sat.
    mix += _ghost_tone(t, GHOST_HZ, flutter_hz, wander_hz) * 0.07 * tremolo
    # Simmering body: the water in the tuber, bubbling slowly.
    murmur = _periodic_bandnoise(rng, n, 150.0, 500.0)
    bubble = 0.75 + 0.25 * np.sin(2.0 * np.pi * (3.0 / LOOP_SECONDS) * t + 2.0)
    mix += murmur * 0.22 * bubble

    # Moisture: droplet pops and choke dropouts, strictly inside the loop so
    # the seam needs no wrap handling.
    _droplet_pops(rng, mix, 5, 0.16, 0.10, LOOP_SECONDS - 0.10)
    for _ in range(3):
        at = rng.uniform(0.15, LOOP_SECONDS - 0.15)
        width = rng.uniform(0.015, 0.035)
        depth = rng.uniform(0.30, 0.5)
        centre = int(at * RATE)
        half = int(width * RATE)
        window = np.hanning(2 * half)
        mix[centre - half : centre + half] *= 1.0 - depth * window

    mix = np.tanh(mix * 1.05)
    return mix * (10 ** (PEAK_DB / 20.0) / np.max(np.abs(mix)))


def make_sputter(rng) -> np.ndarray:
    n = int(SPUTTER_SECONDS * RATE)
    t = np.arange(n) / RATE
    mix = np.zeros(n)

    # Phase 1 (0–1.1 s): the vent failing — the formant slides down as the
    # exit velocity drops, the bed thinning with it.
    n1 = int(1.1 * RATE)
    t1 = t[:n1]
    fade = 1.0 - 0.45 * (t1 / 1.1)
    bed = _tilted_hiss(rng, n1)
    formant = _periodic_bandnoise(rng, n1, 1900.0, 2700.0)
    glide = 1.0 - 0.2 * (t1 / 1.1) ** 1.4
    ghost = _ghost_tone(t1, GHOST_HZ, 19.0, 3.0, glide)
    tremolo = 0.88 + 0.12 * np.sin(2.0 * np.pi * 19.0 * t1)
    mix[:n1] += (bed * 0.7 + formant * 0.3 + ghost * 0.06) * tremolo * fade

    # Phase 2 (1.1–2.4 s): continuous flow is gone — intermittent wet puffs,
    # each weaker, lower and further apart. Noise breaths, not beeps.
    at = 1.1
    band_lo, band_hi = 1700.0, 2600.0
    amp = 0.55
    gap = 0.10
    while at < 2.35:
        dur = rng.uniform(0.06, 0.14)
        n_puff = int(dur * RATE)
        tp = np.arange(n_puff) / RATE
        puff = _periodic_bandnoise(rng, n_puff, band_lo, band_hi)
        body = _tilted_hiss(rng, n_puff)
        env = np.sin(np.pi * np.clip(tp / dur, 0.0, 1.0)) ** 0.7
        offset = int(at * RATE)
        end = min(offset + n_puff, n)
        mix[offset:end] += (puff * 0.5 + body * 0.5)[: end - offset] * env[: end - offset] * amp
        at += dur + gap
        gap *= rng.uniform(1.35, 1.75)
        band_lo *= rng.uniform(0.90, 0.96)
        band_hi *= rng.uniform(0.90, 0.96)
        amp *= rng.uniform(0.60, 0.78)

    # A last few droplets spitting out between the puffs.
    _droplet_pops(rng, mix, 4, 0.12, 1.2, 2.5)

    # Phase 3: the last wet breath — hiss decaying to true silence.
    n3 = n - int(2.3 * RATE)
    tail = _periodic_bandnoise(rng, n3, 900.0, 3500.0)
    mix[int(2.3 * RATE) :] += tail * 0.10 * np.exp(-np.arange(n3) / (0.16 * RATE))

    # A hard-zero landing: the staccato finish must END, not loop or click.
    n_out = int(0.03 * RATE)
    mix[-n_out:] *= np.linspace(1.0, 0.0, n_out)

    mix = np.tanh(mix * 1.05)
    return mix * (10 ** (PEAK_DB / 20.0) / np.max(np.abs(mix)))


def main() -> None:
    rng = np.random.default_rng(0x57EA1)  # STEAM, re-voiced
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

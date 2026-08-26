"""Synthesize the slap. Deterministic, from source, like everything else here.

An 8.6 m foam-latex palm arriving at 115 m/s is not a skin crack — it is a
pressure event. Four layers, all seeded:

  whoosh   0.25 s of rising band-passed noise, the palm displacing air on
           the way in (the stroke is 0.28 s; the sound leads the hit the
           way the real Doppler ramp would)
  thump    a 90 -> 45 Hz pitch-dropping sine, the ground and mast taking
           the reaction — the note a five-storey object makes
  whomp    180-320 Hz noise burst with a 5 ms attack, the foam itself
  crack    a short 1.2-3 kHz burst at modest level: latex, not skin

Then 1.2 s of SILENT TAIL. The pack's only proven-audible playback path is
obj:createSFXSource with the loop profile (see gforce_centrifuge's spec,
2026-08-09c) and a one-shot on a loop profile must be defused: the GE
runtime queues the stop while the cursor is inside this pad, so the cut is
never audible and the wrap is never reached.

Output: assets/sound/ericrolph_high_five_slap.ogg (shipped via SHIP_ASSETS).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 44100
IMPACT = 0.25            # seconds of whoosh before the hit lands
TAIL = 1.2               # silent pad the queued stop hides inside
TOTAL = 2.2


def _env(n: int, attack_s: float, decay_s: float) -> np.ndarray:
    t = np.arange(n) / RATE
    attack = np.clip(t / max(attack_s, 1e-4), 0.0, 1.0)
    decay = np.exp(-np.maximum(t - attack_s, 0.0) / max(decay_s, 1e-4))
    return attack * decay


def _bandnoise(rng, n: int, low: float, high: float) -> np.ndarray:
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    mask = ((freqs >= low) & (freqs <= high)).astype(float)
    # soft shoulders so the band does not ring
    shoulder = np.exp(-((freqs - np.clip(freqs, low, high)) / (0.25 * (high - low) + 1e-9)) ** 2)
    out = np.fft.irfft(spectrum * mask * shoulder, n)
    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out


def main() -> None:
    rng = np.random.default_rng(0x51A9)  # SLAP
    n_total = int(TOTAL * RATE)
    mix = np.zeros(n_total)

    # -- whoosh: rising band, rising level, ends exactly at the impact -----
    n_wh = int(IMPACT * RATE)
    t = np.arange(n_wh) / n_wh
    whoosh = _bandnoise(rng, n_wh, 180.0, 900.0) * (t ** 2.2) * 0.5
    mix[:n_wh] += whoosh

    hit = n_wh
    n_after = n_total - hit

    # -- thump: pitch-dropping sine, the deep note -------------------------
    tt = np.arange(n_after) / RATE
    freq = 45.0 + 45.0 * np.exp(-tt / 0.12)
    phase = 2.0 * np.pi * np.cumsum(freq) / RATE
    mix[hit:] += np.sin(phase) * _env(n_after, 0.004, 0.24) * 1.0

    # -- whomp: the foam body ---------------------------------------------
    mix[hit:] += _bandnoise(rng, n_after, 180.0, 320.0) * _env(n_after, 0.005, 0.11) * 0.75

    # -- crack: latex, kept polite ----------------------------------------
    mix[hit:] += _bandnoise(rng, n_after, 1200.0, 3000.0) * _env(n_after, 0.002, 0.04) * 0.28

    # -- glue: soft clip, normalize to -1 dB ------------------------------
    mix = np.tanh(mix * 1.6)
    mix *= 10 ** (-1.0 / 20.0) / np.max(np.abs(mix))
    # the tail must be genuinely silent, not just quiet
    fade_start = int((TOTAL - TAIL) * RATE)
    fade = int(0.08 * RATE)
    mix[fade_start:fade_start + fade] *= np.linspace(1.0, 0.0, fade)
    mix[fade_start + fade:] = 0.0

    stereo = np.stack([mix, mix], axis=1)
    out = Path(__file__).resolve().parents[1] / "assets" / "sound"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "ericrolph_high_five_slap.ogg"
    sf.write(target, stereo, RATE, format="OGG", subtype="VORBIS")
    print(f"wrote {target} ({target.stat().st_size} bytes, {TOTAL:.1f} s, "
          f"impact at {IMPACT:.2f} s, silent from {TOTAL - TAIL:.2f} s)")


if __name__ == "__main__":
    main()

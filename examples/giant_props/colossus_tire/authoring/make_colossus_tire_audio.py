"""Synthesise the COLOSSUS cue set. Deterministic, seeded, no recordings.

RUN BY HAND, NOT BY build.py:

    .venv/Scripts/python.exe \
        examples/giant_props/colossus_tire/authoring/make_colossus_tire_audio.py

Three cues, the minimum round 5's chair ordered and rounds 3 and 4 asked for
before it (spin_launch's sixteen-cue pipeline is the precedent for every rule
here - see its own header for the long-form reasoning):

  release_crack   one-shot: forty tie-downs parting, the winch whirring, and
                  four wedges skidding clear. Fired from cutChocks.
  roll_loop       loop: the rolling bed. Pitch and volume are pushed by the
                  GE runtime from the same b.speed the HUD shows, so the
                  sound cannot disagree with the needle - and inside the
                  pitch-black cavity it IS the speedometer.
  capsize_boom    one-shot: a giant lying down. Fired at the tipped beat.

THE RULES INHERITED FROM spin_launch, unchanged because they were measured:
Ogg bytes are never reproducible (libvorbis stamps a random bitstream serial),
so the reproducibility gate hashes DECODED PCM; seeds come from sha256, never
hash(); loops are periodic BY CONSTRUCTION (every tonal component an integer
number of cycles, every noise component a circular inverse-rFFT draw), and
periodic is still not seamless, so the loop's local RMS is flattened and the
wrap step is measured and recorded in the manifest. Mono 48 kHz, matching the
pack's other manifests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
MOD_ID = "ericrolph_colossus_tire"
SOUND_DIR = HERE.parent / "assets" / "sound"
MANIFEST = HERE / "colossus_tire_audio_manifest.json"
SR = 48000


def rng(name: str) -> np.random.Generator:
    seed = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big")
    return np.random.default_rng(seed)


def circular_noise(name: str, seconds: float, lo_hz: float, hi_hz: float,
                   slope: float = 0.0) -> np.ndarray:
    """Band-limited noise that is CIRCULAR by construction: random-phase
    inverse rFFT of exactly n bins. slope tilts the band (dB/octave-ish,
    negative = darker)."""

    n = int(round(seconds * SR))
    bins = n // 2 + 1
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    spectrum = np.zeros(bins, dtype=complex)
    band = (freqs >= lo_hz) & (freqs <= hi_hz)
    generator = rng(name)
    phases = generator.uniform(0.0, 2.0 * np.pi, bins)
    magnitude = np.zeros(bins)
    with np.errstate(divide="ignore"):
        tilt = np.where(freqs > 0, (freqs / max(lo_hz, 1.0)) ** (slope / 6.0), 0.0)
    magnitude[band] = tilt[band]
    spectrum[:] = magnitude * np.exp(1j * phases)
    out = np.fft.irfft(spectrum, n)
    peak = np.max(np.abs(out)) or 1.0
    return (out / peak).astype(np.float64)


def envelope(n: int, attack_s: float, decay_tau_s: float, start_s: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    env = np.zeros(n)
    live = t >= start_s
    local = t[live] - start_s
    rise = np.clip(local / max(attack_s, 1e-4), 0.0, 1.0)
    env[live] = rise * np.exp(-np.maximum(local - attack_s, 0.0) / decay_tau_s)
    return env


def level_lock(x: np.ndarray, windows: int = 16) -> np.ndarray:
    """Flatten the loop's local RMS so the wrap is not a level step."""

    n = len(x)
    hop = n // windows
    local = np.array([
        np.sqrt(np.mean(np.square(x[i * hop:(i + 1) * hop])) + 1e-12)
        for i in range(windows)
    ])
    target = float(np.median(local))
    gains = target / local
    # Circular smooth interpolation of the gain track.
    positions = (np.arange(n) / hop) % windows
    lo = np.floor(positions).astype(int) % windows
    hi = (lo + 1) % windows
    frac = positions - np.floor(positions)
    gain = gains[lo] * (1.0 - frac) + gains[hi] * frac
    return x * gain


def wrap_step_ratio(x: np.ndarray) -> float:
    steps = np.abs(np.diff(x))
    rms_step = float(np.sqrt(np.mean(np.square(steps))) + 1e-12)
    seam = float(abs(x[0] - x[-1]))
    return seam / rms_step


def normalise(x: np.ndarray, peak: float = 0.891) -> np.ndarray:
    top = float(np.max(np.abs(x))) or 1.0
    return (x / top * peak).astype(np.float64)


def release_crack() -> np.ndarray:
    seconds = 2.4
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)

    # The webbing parting: two broadband cracks, the second the far pair.
    for start, level, tag in ((0.0, 1.0, "a"), (0.16, 0.62, "b")):
        crack = circular_noise(f"crack_{tag}", seconds, 900.0, 9500.0, slope=-2.0)
        out += crack * envelope(n, 0.004, 0.085, start) * level

    # The winch: a hard electric whirr, pitch sagging under load then freed.
    whirr_f = 92.0 * (1.0 + 0.06 * np.exp(-t / 0.5))
    phase = np.cumsum(2.0 * np.pi * whirr_f / SR)
    whirr = np.zeros(n)
    for harmonic, level in ((1, 1.0), (2, 0.55), (3, 0.33), (5, 0.14)):
        whirr += np.sin(phase * harmonic) * level
    out += whirr / 2.0 * envelope(n, 0.05, 0.55, 0.05) * 0.30

    # Four wedges skidding: mid noise with a gravel gate.
    skid = circular_noise("skid", seconds, 130.0, 950.0, slope=-1.0)
    gate = np.clip(circular_noise("gravel", seconds, 6.0, 38.0), 0.0, None)
    out += skid * (0.45 + 0.55 * gate) * envelope(n, 0.12, 0.85, 0.10) * 0.62
    return normalise(out)


def roll_loop() -> np.ndarray:
    seconds = 4.0
    n = int(seconds * SR)
    t = np.arange(n) / SR

    bed = circular_noise("roll_bed", seconds, 26.0, 1500.0, slope=-4.5)
    # Lug thrum: EIGHT cycles per loop, so it wraps exactly - read in game as
    # tread pitches passing, sped up and down by the runtime's pitch push.
    thrum = 1.0 + 0.32 * np.cos(2.0 * np.pi * 8.0 * t / seconds)
    # Carcass drone: integer-cycle low partials (30 and 37.5 Hz).
    drone = (
        0.22 * np.sin(2.0 * np.pi * 120.0 * t / seconds)
        + 0.15 * np.sin(2.0 * np.pi * 150.0 * t / seconds + 1.1)
    )
    out = level_lock(bed * thrum + drone)
    return normalise(out, peak=0.708)


def capsize_boom() -> np.ndarray:
    seconds = 3.6
    n = int(seconds * SR)
    t = np.arange(n) / SR

    sweep_f = 34.0 * np.exp(-t / 1.6) + 21.0
    phase = np.cumsum(2.0 * np.pi * sweep_f / SR)
    boom = np.sin(phase) * envelope(n, 0.012, 1.05)

    body = circular_noise("boom_body", seconds, 40.0, 260.0, slope=-2.0)
    thump = body * envelope(n, 0.008, 0.28) * 0.8

    debris = circular_noise("debris", seconds, 300.0, 2600.0, slope=-3.0)
    rattle = np.clip(circular_noise("debris_gate", seconds, 4.0, 22.0), 0.0, None)
    tail = debris * rattle * envelope(n, 0.25, 1.1, 0.30) * 0.35
    return normalise(boom * 0.9 + thump + tail)


CUES = (
    ("release_crack", release_crack, False),
    ("roll_loop", roll_loop, True),
    ("capsize_boom", capsize_boom, False),
)


def main() -> None:
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"samplerate": SR, "channels": 1, "codec": "ogg/vorbis", "cues": []}
    for name, build, is_loop in CUES:
        pcm = build()
        path = SOUND_DIR / f"{MOD_ID}_{name}.ogg"
        sf.write(path, pcm, SR, format="OGG", subtype="VORBIS")
        decoded, rate = sf.read(path, dtype="float64")
        assert rate == SR
        quantised = np.round(np.asarray(decoded) * 32767.0).astype(np.int16)
        entry = {
            "name": name,
            "seconds": round(len(pcm) / SR, 3),
            "loop": is_loop,
            "pcm_sha256": hashlib.sha256(quantised.tobytes()).hexdigest(),
            "peak_dbfs": round(20.0 * np.log10(np.max(np.abs(decoded)) + 1e-12), 2),
            "momentary_dbfs": round(
                20.0 * np.log10(np.sqrt(np.mean(np.square(decoded))) + 1e-12), 2
            ),
        }
        if is_loop:
            entry["loop_wrap_ratio"] = round(wrap_step_ratio(pcm), 3)
        manifest["cues"].append(entry)
        print(f"{name}: {entry['seconds']} s, peak {entry['peak_dbfs']} dBFS"
              + (f", wrap {entry['loop_wrap_ratio']}" if is_loop else ""))
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {MANIFEST.name}")


if __name__ == "__main__":
    main()

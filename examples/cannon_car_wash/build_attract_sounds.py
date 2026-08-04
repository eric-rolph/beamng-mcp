"""Synthesize the sign-cannon volley sounds deterministically.

Bottle-rocket audio: a rising whistle with vibrato for the launch and a
noise-burst report for the apex pop. Pure numpy synthesis - no recorded
material - written as 44.1 kHz 16-bit mono WAVs into the mod tree.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np

EXAMPLE_ROOT = Path(__file__).resolve().parent
SOUND_ROOT = EXAMPLE_ROOT / "mod" / "art" / "sound"
SAMPLE_RATE = 44100


def _write_wav(path: Path, samples: np.ndarray) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    data = (clipped * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(data.tobytes())


def build_whistle() -> np.ndarray:
    """Rising bottle-rocket whistle: 1.4 s swept sine with vibrato and air."""

    duration = 1.4
    t = np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE
    # Sweep 1.8 kHz -> 3.6 kHz with a slight settle at the top.
    sweep = 1800.0 + 1800.0 * (t / duration) ** 0.8
    vibrato = 60.0 * np.sin(2.0 * np.pi * 22.0 * t)
    phase = 2.0 * np.pi * np.cumsum(sweep + vibrato) / SAMPLE_RATE
    tone = np.sin(phase)
    # Breathy air band: deterministic pseudo-noise, high-passed by differencing.
    rng = np.random.default_rng(20260804)
    air = rng.standard_normal(t.shape)
    air = np.diff(air, prepend=air[0]) * 0.18
    envelope = np.minimum(t / 0.06, 1.0) * np.exp(
        -1.6 * np.maximum(t - duration + 0.35, 0.0) / 0.35
    )
    fade = np.clip((duration - t) / 0.12, 0.0, 1.0)
    return (tone * 0.55 + air) * envelope * fade * 0.7


def build_report() -> np.ndarray:
    """Apex report: a sharp crack with a boomy tail, like a distant firework."""

    duration = 0.9
    t = np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE
    rng = np.random.default_rng(19840704)
    noise = rng.standard_normal(t.shape)
    # Crack: fast-decay wideband burst.
    crack = noise * np.exp(-t / 0.035)
    # Boom: low-passed rumble via cumulative smoothing, slower decay.
    kernel = np.ones(96) / 96.0
    rumble = np.convolve(noise, kernel, mode="same") * np.exp(-t / 0.28) * 2.2
    attack = np.minimum(t / 0.002, 1.0)
    return (crack * 0.85 + rumble) * attack * 0.8


def main() -> None:
    _write_wav(SOUND_ROOT / "ericrolph_cannon_car_wash_whistle.wav", build_whistle())
    _write_wav(SOUND_ROOT / "ericrolph_cannon_car_wash_report.wav", build_report())
    names = sorted(p.name for p in SOUND_ROOT.glob("*.wav"))
    print(struct.calcsize("h") and f"sounds written: {names}")


if __name__ == "__main__":
    main()

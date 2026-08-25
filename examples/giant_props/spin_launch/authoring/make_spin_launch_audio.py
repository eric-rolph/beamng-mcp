"""Synthesise the spin_launch cue set. Deterministic, seeded, no recordings.

RUN BY HAND, NOT BY build.py:

    .venv/Scripts/python.exe \
        examples/giant_props/spin_launch/authoring/make_spin_launch_audio.py

The output is a COMMITTED ARTEFACT, like every other prop's baked textures.
There are no source recordings for this machine and there cannot be - nothing
that exists sounds like a stadium-sized vacuum chamber whipping a pickup truck
around on a tether - so every cue is built from a physical model the way
``proplib/texture_kit.py`` builds every surface in the pack from a noise basis.

WHY IT IS NOT A BUILD STEP - THE OGG SERIAL (measured 2026-08-25). An Ogg file
can never be byte-reproducible: libvorbis stamps a RANDOM bitstream serial
number into the first page header at offset 14 and every page CRC covers it.
Two runs of this script under different PYTHONHASHSEED produce files that
differ in a few dozen bytes, all of them that serial and its CRCs - while the
DECODED PCM is bit-identical. So:

  * the reproducibility gate hashes DECODED PCM, never file bytes
    (tests/test_spin_launch_audio.py);
  * regenerating on every build.py run would churn the release lock on every
    run for no change in sound, which is exactly the trap
    dist/ericrolph_spin_launch.lock.json exists to catch.

SEEDING. ``hashlib.sha256``, not ``hash()`` - the same fix and the same reason
as ``texture_kit._rng``: PYTHONHASHSEED randomises str hashing per process, so
a hash()-seeded generator draws a different instance every run and no
reproducibility gate downstream of it can ever hold.
(``test_texture_seeds_are_stable_across_processes`` gates exactly this class
of bug for the textures; ``test_decoded_pcm_is_reproducible`` does it here.)

FORMAT. Mono 48 kHz Ogg/Vorbis, matching ``pachinko_audio_manifest.json``
("samplerate": 48000, "channels": 1, "codec": "ogg/vorbis"). Mono because FMOD
downmixes 3D sources to mono anyway - nothing is lost and the bytes are
halved. libsndfile 1.2.2 via soundfile 0.14.0 writes this natively; ffmpeg is
on PATH but is deliberately NOT used, because a build input that is a system
binary is a build input that breaks on someone else's machine.

LOOPS ARE PERIODIC BY CONSTRUCTION, not by crossfade. Tonal content uses
frequencies whose cycle count over the buffer is an integer; swept or switched
tones run through ``closed_phase``, which rescales the frequency track so the
accumulated phase closes on an exact number of turns; noise is a random-phase
inverse rFFT of exactly n bins, which is circular by definition; filtering is
spectral multiplication; reverb is CIRCULAR convolution. The wrap
discontinuity of every loop is measured against its own RMS sample step and
printed, and the gate is 3.0.

...AND PERIODIC IS NOT THE SAME AS SEAMLESS. A loop can be exactly periodic
in phase and still STEP IN LEVEL at the wrap, because band-limited noise has
a couple of dB of local RMS wobble everywhere and the seam is one draw from
it. The sample-step ratio is structurally blind to that. ``level_lock`` and
``seam_align`` below are the two halves of the fix and ``loop_wrap_db`` in
the manifest is the measurement.

THE MIX IS DERIVED FROM A LOUDNESS MEASUREMENT, NOT FROM PEAKS. Every cue is
peak-normalised LAST and loudness-normalised FIRST; ``momentary_dbfs`` in the
manifest is what ``spec.AUDIO_CUE_TABLE`` solves each cue's ``vol`` against,
so the ladder the design states is the ladder the player is delivered. See
the LOUDNESS block below for why the shipped peak-normalised set put the
release bang tenth of sixteen.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib

import numpy as np
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "assets" / "sound"
MANIFEST_PATH = HERE / "spin_launch_audio_manifest.json"
MOD_ID = "ericrolph_spin_launch"

SR = 48000
# Seed. Arbitrary but FIXED and recorded in the manifest; changing it
# reshuffles every noise phase and every modal detune, i.e. it is a re-record
# of the whole set, not a tweak.
SEED = "spin_launch:4310"
# Vorbis VBR quality. libsndfile's compression_level is INVERTED relative to
# oggenc's -q (0.0 = best, 1.0 = worst). 0.4 measured ~330 KiB across the
# 16-cue set; 0.2 bought ~40% more bytes for no audible gain on material this
# band-limited.
QUALITY = 0.4

# EVERY ONE-SHOT IS A LOOP WEARING A STOP CLOCK, because AudioDefaultLoop3D is
# the only sound description this pack has ever proven audible (AGENTS.md,
# "audio mechanism v3 after fileName-SFXEmitter and Engine.Audio.playOnce both
# proved unprovable/silent"). So a one-shot needs a silent tail to stop INSIDE.
# Both numbers are read off pachinko_audio_manifest.json, which is the pack's
# only shipped precedent: pin_soft_01 audible_end 0.595 / recommended_stop
# 0.82, pin_soft_02 0.74 / 0.965 - a 0.75 s pad with the stop 0.225 s into it.
PAD_SECONDS = 0.75
STOP_OFFSET = 0.225
# The last of the audible span is faded to true zero over this window. Not
# cosmetic: several cues are modal banks whose taus deliberately outlive the
# cue (release_bang's longest shell mode is 2.60 s inside a 4.20 s audible
# span, so it is still at exp(-4.2/2.6) = 0.198 of full when the pad starts).
# Truncating that to zero is a step of a fifth of full scale - a click at the
# exact moment the room is supposed to be ringing away. 0.15 s of raised
# cosine is long enough to be inaudible as an edit and short enough that it
# reads as the tail arriving rather than as a fade.
FADE_OUT_SECONDS = 0.15
# ...and the first millisecond is ramped up from true zero, for a reason that
# is about failure rather than taste. A one-shot here is a LOOP with a stop
# clock, and the clock runs in the vehicle VM. If that clock ever stops
# running - a pcall that swallowed something, an updateGFX chain that got
# re-wrapped - the cue wraps forever, and a cue whose first sample is 0.34 of
# full scale (measured: door_slam) wraps with a click 79x its own RMS sample
# step, every 3.15 s, for as long as the prop exists. Starting at zero makes
# that failure SILENT instead of a machine-gun. 1 ms is 48 samples: it softens
# nothing above about a kilohertz that env_ad's own 0.6 ms attack had not
# already softened.
ONSET_RAMP_SECONDS = 0.001

# THE FINAL PEAK, and it moved 0.89 -> 0.83 when the limiter landed. Vorbis
# is a lapped transform, so a decoded peak always overshoots the encoded one,
# and the overshoot scales with how DENSE the waveform is. Peak-normalised at
# 0.89 the shipped set decoded 0.863-0.900 (+0.1 dB worst); loudness
# normalised through a limiter the same 0.89 decoded 0.880-1.003 - repress
# came back CLIPPED, at +1.04 dB of overshoot, and five cues broke the
# 0.80-0.95 gate. At 0.83 repress came back at 0.948 against a 0.95 ceiling,
# which passes and is two millibels of margin; 0.82 x 1.142 = 0.937 measured,
# with the quietest peak at 0.827 against a 0.80 floor - margin at both ends.
# The 0.7 dB this costs is uniform across the set, so it moves the whole mix
# down together and changes no relationship inside it.
MASTER_PEAK = 0.82

# The spin loop's partial ceiling. FMOD pitch is a playback-RATE change, i.e.
# resampling, so anything above Nyquist / PITCH_MAX folds back as an audible
# metallic buzz at exactly the moment the machine is loudest:
#     (48000/2) / (182.0/82.0) = 24000 / 2.2195 = 10813.2 Hz
# rounded DOWN to 10800 for 29 Hz of margin (10800 * 2.2195 = 23970.7).
# 182/82 is not a chosen number - it is POWER_STEPS_MPS[-1] over the nominal
# rung, the ladder's own top-to-nominal ratio. Mirrored in spec.py as
# SPIN_PARTIAL_CAP_HZ and republished in the manifest so the two cannot drift
# apart silently (tests/test_spin_launch_audio.py compares them).
SPIN_PARTIAL_CAP_HZ = 10800.0

# The chamber's own reverberation time, Sabine, from the authored interior:
#     V = pi * CHAMBER_R^2 * (2*HALF_X) = pi * 20.4^2 * 8.4      = 10982 m^3
#     S = 2*pi*CHAMBER_R^2 + 2*pi*CHAMBER_R*(2*HALF_X)           = 3691.6 m^2
#     alpha(bare steel) ~ 0.05
#     RT60 = 0.161 * V / (S * alpha) = 0.161*10982/(3691.6*0.05) = 9.58 s
# That is the honest number and it is unusable: a 9.6 s tail on every cue is
# mud and ten times the bytes. The SLOPE shipped below is the real one; the
# TRUNCATION at 1.2 s is a deliberate lie, named here so nobody later "fixes"
# it back to nine and a half seconds.
REVERB_RT60_S = 9.58
REVERB_IR_SECONDS = 1.2


# ---------------------------------------------------------------------------
# Basis. One function per job, seeded, and periodic wherever a loop needs it.
# ---------------------------------------------------------------------------

def rng(tag: str) -> np.random.Generator:
    """Per-cue seed that is the same number on every run, forever.

    sha256 has no per-process salt (``hash()`` does), so this is stable across
    runs, machines and Python versions - the same reasoning, verbatim, as
    ``proplib/texture_kit._rng``.
    """

    digest = hashlib.sha256(f"{SEED}:{tag}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def L(seconds: float) -> int:
    return int(round(seconds * SR))


def norm(x: np.ndarray, peak: float = 0.89) -> np.ndarray:
    """Scale to a target absolute peak. 0.89 leaves 1.0 dB of headroom for the
    codec: a lapped transform overshoots on transients, and a cue authored at
    1.0 decodes clipped even though the file never was.

    PEAK IS THE LAST STEP, NEVER THE MIX. See momentary_dbfs below: peak
    normalisation says nothing about how loud a cue is, and this set used to
    be normalised on peak alone.
    """

    magnitude = float(np.max(np.abs(x)))
    return x * (peak / magnitude) if magnitude > 0 else x


# ---------------------------------------------------------------------------
# LOUDNESS. The one number the mix is built on.
# ---------------------------------------------------------------------------
# Measured in game at 11.5 m, the shipped set delivered 28.4 dB of spread
# across sixteen cues whose vol table spanned 6.0 dB - because the clips were
# PEAK normalised (0.863-0.900) while their RMS spanned 0.0447 to 0.4552, a
# 20 dB range that nothing in the mix knew about. The consequences were not
# subtle: release_bang, the whole point of the machine, landed TENTH of
# sixteen and 11.3 dB under abort_klaxon; spin_loop buried stage_tick by
# 26.8 dB while the ticks fire during the ride; and arm_charge, clamp_close,
# hard_vacuum and stage_tick all sat under an idling ETK800.
#
# So the mix is derived from a LOUDNESS measurement now, and this is it:
# MOMENTARY LOUDNESS, the peak of a 400 ms sliding energy window. 400 ms is
# the broadcast momentary window and it is the right one here for a specific
# reason - it is roughly the integration time of the ear for "did that read",
# so it scores a 30 ms clack against a continuous bed the way a listener
# does. A whole-file RMS would score a 4.95 s bang by its 3 s of tail; a peak
# would score everything the same, which is the defect.
#
# Unweighted, deliberately. K-weighting exists to model a loudspeaker in a
# living room and it de-emphasises everything under 100 Hz; this machine's
# beds ARE under 100 Hz (a 31 Hz hydraulic stack, a 42 Hz Roots lobe, a 29 Hz
# shell mode) and weighting them down would mix them up to compensate.
MOMENTARY_WINDOW_S = 0.400
MOMENTARY_HOP_S = 0.100


def momentary_dbfs(x: np.ndarray) -> float:
    """Loudest 400 ms of a cue, in dB relative to full scale."""

    window = int(MOMENTARY_WINDOW_S * SR)
    if len(x) <= window:
        return 10.0 * math.log10(float(np.mean(x.astype(np.float64) ** 2)) + 1e-20)
    cumulative = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    hop = max(1, int(MOMENTARY_HOP_S * SR))
    energies = (cumulative[window::hop] - cumulative[:-window:hop]) / window
    return 10.0 * math.log10(float(np.max(energies)) + 1e-20)


# The soft knee: below it nothing is touched, above it the curve bends
# asymptotically to the ceiling. tanh rather than a hard clip because a hard
# clip on a 55 Hz stack is a buzz, and because the derivative is continuous -
# a kink is its own harmonic generator.
LIMIT_KNEE = 0.55


def soft_limit(x: np.ndarray, ceiling: float = 1.0) -> np.ndarray:
    """Waveshaping limiter. Memoryless, so a loop stays exactly periodic."""

    knee = LIMIT_KNEE * ceiling
    span = ceiling - knee
    magnitude = np.abs(x)
    over = magnitude > knee
    out = np.array(x, dtype=np.float64)
    out[over] = np.sign(x[over]) * (knee + span * np.tanh((magnitude[over] - knee) / span))
    return out


# How far a cue may be driven into that limiter to reach the loudness target.
# 6.0 dB is the number this set needs and no more: the deepest user is
# release_bang at 5.2 dB, which is what turns an 11.0 dB crest factor into
# something nearer abort_klaxon's 5.7 and is exactly what mastering a bang
# is. Past about 8 dB a modal bank stops sounding struck and starts sounding
# square, so the cap is a real limit and not a formality - a cue that cannot
# reach the target inside it has a SHAPE problem and gets fixed in its
# builder (see stage_tick).
MAX_DRIVE_DB = 6.0
# The target every cue is driven toward. Set by the loudest thing that has to
# reach it: release_bang measures -12.18 dBFS momentary as synthesised, so
# -7.0 is 5.2 dB of drive - inside the cap, with room left for the codec.
LOUDNESS_TARGET_DBFS = -7.0


def loud_norm(x: np.ndarray):
    """Drive toward LOUDNESS_TARGET_DBFS through the limiter. Never attenuates.

    Attenuating here would be pointless: the final ``norm`` is a peak scale
    and would undo it. A cue that is already louder than the target keeps its
    own dynamics and is brought down by its mix volume instead, which is what
    a fader is for.
    """

    x = norm(x, 1.0)
    drive = min(MAX_DRIVE_DB, max(0.0, LOUDNESS_TARGET_DBFS - momentary_dbfs(x)))
    if drive <= 0.0:
        return x, 0.0
    return soft_limit(x * (10.0 ** (drive / 20.0)), 1.0), drive


def level_lock(x: np.ndarray, window: float = 0.050, max_db: float = 4.0):
    """Flatten a stationary bed's short-term level, CIRCULARLY.

    THE WRAP IS A LEVEL STEP AND THE SEAM TEST CANNOT SEE IT.
    ``test_loops_wrap_without_a_click`` measures |s[0] - s[-1]| / RMS step,
    which is a SAMPLE-step test: it catches a phase discontinuity and is blind
    to an ENERGY discontinuity. Measured on 20 ms windows head against tail,
    the shipped set stepped -4.4 dB on door_travel (which wraps once, 0.6 s
    before the door slam), +2.1 dB on deck_retract (twice) and -1.3 dB on
    pump_down. Nothing is wrong with the synthesis - band-limited noise simply
    has a +/-2 dB local RMS wobble everywhere, and the seam is one draw from
    that distribution - but the seam is the ONE place in a loop where a
    2 dB draw lands at a fixed time and repeats.

    So the fix is not at the seam, it is everywhere: divide out the circular
    short-term envelope so a stationary bed is actually stationary. Applied
    only to the beds that ARE stationary. arm_charge ramps, spin_loop
    breathes at 1 Hz, release_alarm is gated at 3 Hz and abort_klaxon switches
    at 1.25 Hz - a 50 ms detector would track and cancel every one of those
    deliberate modulations, so those four keep their own envelope and are
    measured rather than flattened.
    """

    width = max(8, int(window * SR))
    energy = circ_smooth(x.astype(np.float64) ** 2, width)
    envelope = np.sqrt(np.maximum(energy, 1e-12))
    limit = 10.0 ** (max_db / 20.0)
    gain = np.clip(float(envelope.mean()) / envelope, 1.0 / limit, limit)
    # Smoothed again so the correction cannot introduce steps of its own.
    return x * circ_smooth(gain, width)


def seam_align(x: np.ndarray, window: float = 0.020, exclude: float = 0.05):
    """Rotate a loop so its wrap lands where the level is already continuous.

    A LOOP HAS NO CANONICAL START. Rotating a periodic buffer is the one
    correction available here that costs nothing at all: it is a relabelling,
    the sound is bit-for-bit the same sound, and there is no gain, no filter
    and no distortion involved. What it buys is the choice of WHERE the one
    unavoidable discontinuity in the player's experience of the loop lands.

    level_lock flattens the bed at 50 ms, which is as fine as it can go
    without chasing a 31 Hz hydraulic stack's own cycle and turning it into a
    tremolo. What is left is the 20 ms wobble, and the seam is one draw from
    it. So: measure the head-against-tail step at every candidate rotation and
    take the smallest. Combined, the two take door_travel's -4.4 dB step to
    inside a tenth of a dB.

    ``exclude`` skips rotations that would start the loop inside the first or
    last 50 ms of the original, which is only bookkeeping: those are the
    rotations where head and tail windows overlap the same samples and the
    measurement stops meaning anything.
    """

    n = len(x)
    width = max(8, int(window * SR))
    skip = max(1, int(exclude * SR))
    doubled = np.concatenate((x, x)).astype(np.float64)
    squared = np.concatenate(([0.0], np.cumsum(doubled ** 2)))

    def rms_at(start):
        return math.sqrt(max((squared[start + width] - squared[start]) / width, 1e-24))

    best, best_step = 0, None
    for start in range(skip, n - skip, max(1, width // 4)):
        step = abs(20.0 * math.log10(rms_at(start) / rms_at(start + n - width)))
        if best_step is None or step < best_step:
            best, best_step = start, step
    return np.roll(x, -best)


def wrap_level_db(x: np.ndarray, window: float = 0.020) -> float:
    """Level step across the wrap, head against tail, in dB. 0.0 is seamless."""

    width = max(8, int(window * SR))
    head = float(np.sqrt(np.mean(x[:width].astype(np.float64) ** 2)))
    tail = float(np.sqrt(np.mean(x[-width:].astype(np.float64) ** 2)))
    if head <= 0.0 or tail <= 0.0:
        return 0.0
    return 20.0 * math.log10(head / tail)


def circ_noise(n, r, lo, hi, tilt=0.0):
    """Band-limited noise, PERIODIC IN n BY CONSTRUCTION.

    Built in the frequency domain: |X| is the band shape, arg(X) is uniform
    random, and an inverse rFFT of exactly n bins can only produce a signal
    whose period is n. This is the whole reason the loops do not click, and it
    is why filtering here is spectral multiplication rather than an IIR (which
    would have a transient at sample 0 and none at sample n).

    THE SKIRTS ARE CONTINUOUS WITH THE BAND, which is not a detail. Written
    the obvious way - band shape inside, ``(hi/f)**4`` outside - the magnitude
    JUMPS back to 1.0 at ``hi`` on any cue with a negative tilt, because the
    band has already fallen to ``(hi/lo)**tilt`` by then. On spin_loop's wash
    (lo 180, hi 5200, tilt -0.55) that step is 0.157 -> 1.0, and the resulting
    bump puts 5.3% of peak magnitude at 10.8 kHz, straight through the
    anti-aliasing ceiling this whole file is built around. Anchoring each
    skirt to the band's own edge value keeps the shape monotone.
    """

    bins = n // 2 + 1
    f = np.fft.rfftfreq(n, 1.0 / SR)
    mag = np.zeros(bins)
    lo = max(lo, 1.0)
    band = (f >= lo) & (f <= hi)
    mag[band] = (f[band] / lo) ** tilt
    edge_hi = (hi / lo) ** tilt
    below = (f > 0) & (f < lo)
    mag[below] = (f[below] / lo) ** 4          # 24 dB/oct below, anchored at 1
    above = f > hi
    mag[above] = edge_hi * (hi / f[above]) ** 4  # 24 dB/oct above, anchored
    phase = r.uniform(0, 2 * np.pi, bins)
    phase[0] = 0.0                              # no DC: a DC-offset cue eats
    if n % 2 == 0:                              # headroom and thumps on start
        phase[-1] = 0.0
    return np.fft.irfft(mag * np.exp(1j * phase), n)


def brickwall(x, cutoff_hz):
    """Zero every bin above ``cutoff_hz``. Circular, so a loop stays a loop.

    Used on spin_loop only, and used because a cap enforced partial-by-partial
    is not a cap: the noise layers and the reverb tail both put energy above it
    that no ``if f > cap: break`` can see.
    """

    spectrum = np.fft.rfft(x)
    spectrum[np.fft.rfftfreq(len(x), 1.0 / SR) > cutoff_hz] = 0.0
    return np.fft.irfft(spectrum, len(x))


def env_ad(n, attack, decay, curve=2.5):
    """Attack-decay envelope. ``curve`` is how many time constants the decay
    spans, so a bigger number is a sharper cue."""

    t = np.arange(n) / SR
    return np.clip(t / max(attack, 1e-6), 0, 1) * np.exp(
        -curve * np.clip((t - attack) / max(decay, 1e-6), 0, None))


def modal(n, freqs, taus, amps, r):
    """A bank of exponentially decaying sinusoids: impulse plus body.

    This is what a struck steel plate IS. A slam built as a filtered noise
    burst reads as a whoosh; a slam built as modes reads as MASS, and the mode
    frequencies are what carry the size of the thing that was hit. Phases are
    randomised per mode so two cues built from the same bank do not stack into
    an artificial-sounding chord.
    """

    t = np.arange(n) / SR
    out = np.zeros(n)
    for frequency, tau, amplitude in zip(freqs, taus, amps):
        out += amplitude * np.exp(-t / tau) * np.sin(
            2 * np.pi * frequency * t + r.uniform(0, 2 * np.pi))
    return out


def harm_stack(n, f0, partials, r, tilt=-1.15, jitter=0.0, cap=SPIN_PARTIAL_CAP_HZ):
    """Harmonic stack. Periodic in n when ``f0 * n / SR`` is an integer.

    ``tilt`` is the spectral slope in partial index: -1.0 is a sawtooth, more
    negative is duller and more like something heard through a wall. ``cap``
    stops the stack before Nyquist-after-pitch-up; see SPIN_PARTIAL_CAP_HZ.
    """

    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, partials + 1):
        frequency = f0 * k
        if frequency > cap:
            break
        amplitude = float(k) ** tilt
        if jitter:
            amplitude *= 1.0 + jitter * r.standard_normal()
        out += amplitude * np.sin(2 * np.pi * frequency * t + r.uniform(0, 2 * np.pi))
    return out


def closed_phase(frequency_track):
    """Integrate an instantaneous-frequency track so it CLOSES over the buffer.

    Two bugs live here and both are silent. The first: ``sin(2*pi*f(t)*t)`` is
    NOT a phase integral - it is a quadratic chirp wearing an FM costume, and
    it lands on an arbitrary phase at the wrap. The second: even a correctly
    integrated switched or swept track ends wherever it ends, which on a tonal
    loop is a click you can hear. Rescaling the whole track so the accumulated
    phase is an exact integer number of turns fixes it for a frequency error of
    a couple of cents, which is nothing.

    Note the phase starts at 0 and the total is taken over n samples, not
    n-1: the wrap happens BETWEEN the last sample and the first, so it is the
    n-sample total that has to be a whole number of turns.
    """

    turns = float(np.sum(frequency_track)) / SR
    scale = max(1.0, round(turns)) / turns
    phase = np.concatenate(([0.0], np.cumsum(frequency_track)[:-1]))
    return 2 * np.pi * scale * phase / SR


def circ_smooth(x, width):
    """Moving-average smoothing done circularly, so a loop stays a loop.

    The straight ``np.convolve(..., "same")`` tapers both ends against the
    zero-padding, which on a gate that is open at both ends of the buffer
    invents a dip that is not in the signal.
    """

    kernel = np.hanning(width)
    padded = np.zeros(len(x))
    padded[:width] = kernel / kernel.sum()
    padded = np.roll(padded, -(width // 2))
    return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(padded), len(x))


def chamber_ir(seconds, rt60, r):
    """One room for the whole set, so the cues sound like the same machine.

    Exponentially decaying noise on the Sabine slope derived above, with four
    discrete early reflections for the lid plates and the hub housing. The
    early reflection delays are the real round trips: 0.0121 s is 4.15 m, one
    interior width (2 * HALF_X = 8.4 m) there and back at 343 m/s minus the
    source offset; the rest walk out to the shell and back.
    """

    n = int(seconds * SR)
    t = np.arange(n) / SR
    tail = r.standard_normal(n) * 10.0 ** (-3.0 * t / rt60)
    ramp = int(0.004 * SR)
    tail[:ramp] *= np.linspace(0, 1, ramp)
    impulse = tail.copy()
    impulse[0] += 1.0
    for delay, gain in ((0.0121, 0.52), (0.0247, -0.41),
                        (0.0388, 0.33), (0.0613, -0.26)):
        impulse[int(delay * SR)] += gain
    return impulse / np.max(np.abs(impulse))


def _fft_convolve(x, ir):
    """Linear convolution via FFT. numpy's convolve is direct, i.e. O(n*m):
    release_bang against a 57,600-tap IR would be 1.4e10 multiply-adds."""

    size = 1 << (len(x) + len(ir) - 2).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)


def conv_lin(x, ir, wet):
    """Reverb for a ONE-SHOT. The tail is allowed to run past the dry signal
    and is simply truncated with it, which is what a one-shot's own fade-out
    then hides."""

    wet_signal = _fft_convolve(x, ir)[: len(x)]
    return (1 - wet) * x + wet * norm(wet_signal, float(np.max(np.abs(x))) or 1.0)


def conv_circ(x, ir, wet):
    """Reverb for a LOOP. Circular convolution is the only kind that keeps a
    loop a loop: a linear one wraps a 1.2 s tail into silence at sample 0."""

    n = len(x)
    padded = np.zeros(n)
    taps = min(len(ir), n)
    padded[:taps] = ir[:taps]
    wet_signal = np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(padded), n)
    return (1 - wet) * x + wet * norm(wet_signal, float(np.max(np.abs(x))) or 1.0)


IR = chamber_ir(REVERB_IR_SECONDS, REVERB_RT60_S, rng("ir"))


def pad(x, audible):
    """Ramp in from zero, fade the tail to zero, then hang PAD_SECONDS of true
    silence off it.

    The stop clock lands STOP_OFFSET into that silence: after the content,
    well before the wrap, with 0.525 s of clock drift room on the far side.
    """

    total = L(audible + PAD_SECONDS)
    out = np.zeros(total)
    taps = min(len(x), L(audible))
    out[:taps] = x[:taps]
    rise = min(L(ONSET_RAMP_SECONDS), taps)
    out[:rise] *= 0.5 * (1 - np.cos(np.pi * np.arange(rise) / rise))
    fade = min(L(FADE_OUT_SECONDS), taps)
    out[taps - fade:taps] *= 0.5 * (1 + np.cos(np.pi * np.arange(fade) / fade))
    return out


def scatter_circ(target, block, start_seconds):
    """Add a block into a LOOP at a start time, wrapping round the end.

    A loop has no end to fall off. Truncating a click that starts 26 ms before
    the wrap leaves a step exactly where the seam is, which is the one place a
    step is guaranteed to be heard.
    """

    n = len(target)
    start = int(start_seconds * SR) % n
    for offset in range(0, len(block), n):
        chunk = block[offset:offset + n]
        end = start + len(chunk)
        if end <= n:
            target[start:end] += chunk
        else:
            target[start:] += chunk[: n - start]
            target[: end - n] += chunk[n - start:]
    return target


# ---------------------------------------------------------------------------
# LOOPS. Six of them, each stopped by a STATE and never by a clock.
# ---------------------------------------------------------------------------

def arm_charge():
    """THE THREE-SECOND ARM COUNTDOWN, which used to be dead air.

    Twelve relay clicks accelerating GEOMETRICALLY into the arm instant over a
    rising charge whine, so holding still on the cradle stops feeling like
    waiting for a progress bar and starts feeling like a capacitor bank
    filling up behind you. 3.000 s exactly, which is BEHAVIOR's arm_delay_s -
    the cue is the phase, so the twelfth click lands on the frame the machine
    commits.

    The click times are ``3 - 3*x**1.9`` over x = 1 .. 1/12, i.e. spaced by a
    1.9-power: 0.000, 0.514, 0.930, ... 2.911, 2.974. The exponent is the only
    free number here and it is set by the ear-test on paper - at 1.0 the
    clicks are a metronome and carry no urgency; much above 2 the last four
    collapse into a buzz.
    """

    n = L(3.0)
    r = rng("arm_charge")
    x = np.zeros(n)
    times = 3.0 - 3.0 * (np.linspace(1.0, 0.0, 13)[:-1] ** 1.9)
    for index, start in enumerate(times):
        span = L(0.09)
        click = modal(
            span, [1180 + 90 * index, 2470 + 140 * index, 3910],
            [0.010, 0.006, 0.004], [1.0, 0.5, 0.25], r) * env_ad(span, 0.0004, 0.020)
        scatter_circ(x, norm(click, 1.0), start)
    # The charge whine: 140 Hz rising to 330 Hz on a squared curve, amplitude
    # following a 1.5-power so it is barely there at the start of the hold.
    # closed_phase because the sweep must land on a whole turn at the wrap.
    t = np.arange(n) / SR
    whine = np.sin(closed_phase(140.0 + 190.0 * (t / 3.0) ** 2)) * (t / 3.0) ** 1.5
    return conv_circ(norm(x) + 0.30 * whine, IR, 0.12)


def door_travel():
    """BLAST DOOR ON ITS RAILS, 2.6 s of travel covered by a 2.0 s loop.

    Rail rumble (broadband, tilted down) plus a 31 Hz hydraulic stack - 62
    whole cycles in 2.0 s, so it is periodic by construction - plus a thin
    grind on top so the door sounds LOADED rather than motorised. 31 Hz is
    below the fundamental of anything the player's car makes, which is what
    keeps it legible under an engine.
    """

    n = L(2.0)
    r = rng("door_travel")
    rail = circ_noise(n, r, 55.0, 900.0, tilt=-0.9)
    hydraulic = harm_stack(n, 31.0, 30, r, tilt=-1.3)
    grind = circ_noise(n, r, 1400.0, 6000.0, tilt=-1.1)
    # level_lock: a rail bed is stationary, so it must not step at the wrap.
    # Shipped, this one dropped 4.4 dB across the seam - 0.6 s before the
    # door slam, which is the worst possible half second to have a hole in.
    return level_lock(conv_circ(0.62 * norm(rail) + 0.50 * norm(hydraulic)
                                + 0.20 * norm(grind), IR, 0.14))


def pump_down():
    """THE SEVEN-SECOND EVACUATION, which used to be dead air.

    A Roots-blower bed: a 42 Hz lobe tone (147 whole cycles in 3.5 s) plus
    broadband gas hiss plus foundation rumble. THE DESCENT IS NOT IN THE FILE
    and cannot be - a loop that monotonically falls is not a loop. The runtime
    pushes pitch and volume from ``b.vac`` instead (AUDIO_PUMP_* in spec.py),
    so the bed thins and rises as the chamber empties and the seven seconds
    become a countdown you can hear reach zero.
    """

    n = L(3.5)
    r = rng("pump_down")
    lobes = harm_stack(n, 42.0, 40, r, tilt=-1.0)
    hiss = circ_noise(n, r, 420.0, 9000.0, tilt=-0.7)
    rumble = circ_noise(n, r, 28.0, 150.0, tilt=-0.3)
    return level_lock(conv_circ(0.55 * norm(lobes) + 0.42 * norm(hiss)
                                + 0.40 * norm(rumble), IR, 0.10))


def deck_retract():
    """SCREW JACKS TAKING A SLAB OUT FROM UNDER THE CAR, 2.4 s of travel on a
    1.2 s loop. A 100 Hz stack (120 whole cycles in 1.2 s) over low slab
    rumble. The stack is deliberately BUZZY (tilt -1.25 with 60 partials) -
    a screw jack is a threaded rod under load, not a motor."""

    n = L(1.2)
    r = rng("deck_retract")
    screw = harm_stack(n, 100.0, 60, r, tilt=-1.25)
    slab = circ_noise(n, r, 34.0, 260.0, tilt=-0.4)
    return level_lock(conv_circ(0.58 * norm(screw) + 0.55 * norm(slab), IR, 0.13))


def spin_loop():
    """THE CENTREPIECE, and the cue the whole mod was missing.

    A 55 Hz harmonic stack (110 whole cycles in 2.0 s) with per-partial
    detune, a 165 Hz drive whine three times over it, and a filtered-noise
    wash for the tether passing the observation ring, beating twice per loop.

    LOW ON PURPOSE, AND STRUCTURE-BORNE ON PURPOSE. The chamber is at hard
    vacuum: there is no air in there to make an air sound. What reaches the
    player is the drive and the shell, CONDUCTED, which is why this is a heavy
    stack rather than a whoosh - and why it is believable that you can hear it
    at all through 1.2 m of wall while the blast door keeps every photon out.

    Brickwalled at SPIN_PARTIAL_CAP_HZ, because the runtime pitches this up to
    182/82 = 2.2195 and everything above (48000/2)/2.2195 folds. The stack's
    own cap is not enough on its own: the wash and the reverb tail both put
    energy above it.
    """

    n = L(2.0)
    r = rng("spin_loop")
    tone = harm_stack(n, 55.0, 200, r, tilt=-1.15, jitter=0.06)
    tone += 0.45 * harm_stack(n, 165.0, 60, r, tilt=-1.4)
    wash = circ_noise(n, r, 180.0, 5200.0, tilt=-0.55)
    breathing = 1.0 + 0.12 * np.sin(2 * np.pi * 1.0 * np.arange(n) / SR)
    mixed = conv_circ(0.72 * norm(tone) + 0.34 * norm(wash) * breathing, IR, 0.12)
    return brickwall(mixed, SPIN_PARTIAL_CAP_HZ)


def release_alarm():
    """MUZZLE INTERLOCK ARMED: the "you cannot stop this now" warble.

    Gated FM at 3 Hz - 3 whole cycles in 1.0 s - phase-INTEGRATED and closed.
    The naive ``sin(2*pi*f(t)*t)`` form is a chirp, not an FM, and it lands on
    an arbitrary phase at the wrap; this is why closed_phase exists.
    """

    n = L(1.0)
    r = rng("release_alarm")
    t = np.arange(n) / SR
    phase = closed_phase(620.0 + 180.0 * np.sin(2 * np.pi * 3.0 * t))
    gate = circ_smooth((np.sin(2 * np.pi * 3.0 * t) > -0.3).astype(float), 240)
    tone = norm(np.sin(phase) * gate)
    return conv_circ(tone + 0.25 * norm(harm_stack(n, 310.0, 8, r, tilt=-1.6)),
                     IR, 0.16)


def repress():
    """AIR COMING BACK IN through the vents, on the same ``venting`` predicate
    the vent_blast plume already rides. A broad rush over body noise - the
    inverse of hard_vacuum, and the only cue in the set that means it is safe
    to get out."""

    n = L(2.5)
    r = rng("repress")
    rush = circ_noise(n, r, 300.0, 11000.0, tilt=-0.45)
    body = circ_noise(n, r, 45.0, 320.0, tilt=-0.2)
    return level_lock(conv_circ(0.70 * norm(rush) + 0.42 * norm(body), IR, 0.15))


def abort_klaxon():
    """TWO-TONE ABORT. G4 / D#4 - a minor third DOWN, the interval every
    industrial alarm on earth uses because it reads as wrong. Switches at
    1.25 Hz (2 whole cycles in 1.6 s) and the phase is closed, which on a
    switched track is the difference between a warble and a click per
    switch."""

    n = L(1.6)
    r = rng("abort_klaxon")
    t = np.arange(n) / SR
    high = np.where(np.sin(2 * np.pi * 1.25 * t) > 0, 1.0, 0.0)
    phase = closed_phase(392.0 * high + 311.0 * (1 - high))
    tone = (np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.28 * np.sin(3 * phase))
    return conv_circ(norm(tone), IR, 0.16)


# ---------------------------------------------------------------------------
# ONE-SHOTS. Ten of them, each a loop with a silent tail and a stop clock.
# ---------------------------------------------------------------------------

def detect_klaxon():
    """PAYLOAD DETECTED. Bb4 / F4 alternating at 2 Hz and decaying over 1.60 s
    - an ANNOUNCEMENT, not an alarm. The machine has noticed you and is
    pleased about it; abort_klaxon is what it sounds like when it is not."""

    audible = 1.60
    n = L(audible)
    t = np.arange(n) / SR
    high = np.where(np.sin(2 * np.pi * 2.0 * t) > 0, 1.0, 0.0)
    phase = closed_phase(466.0 * high + 349.0 * (1 - high))
    tone = (np.sin(phase) + 0.45 * np.sin(2 * phase)) * np.clip(
        1.0 - (t / audible) ** 3, 0, 1)
    return pad(conv_lin(norm(tone), IR, 0.18), audible)


def door_slam():
    """YOU ARE SHUT IN.

    The single most important one-shot in the mod: it is the last thing you
    hear before the world outside stops existing. Eight modes from 41 Hz up
    with taus out to 1.30 s - a big, slow, heavy plate - and a broadband
    impulse on top for the strike itself. The wettest cue in the set at 0.26,
    because this is the moment the chamber's size becomes the player's
    problem.
    """

    audible = 2.40
    n = L(audible)
    r = rng("door_slam")
    body = modal(n, [41, 63, 97, 148, 213, 331, 470, 688],
                 [1.30, 1.05, 0.82, 0.61, 0.44, 0.28, 0.18, 0.11],
                 [1.0, .82, .64, .47, .34, .24, .16, .10], r)
    strike = circ_noise(n, r, 60.0, 9000.0, tilt=-0.6) * env_ad(n, 0.0006, 0.055, 3.2)
    return pad(conv_lin(norm(body) + 0.75 * norm(strike), IR, 0.26), audible)


def hard_vacuum():
    """THE SOUND OF NO SOUND.

    Three very low modes, a swallowed low thud, and a whole-cue fade to
    nothing - and the DRIEST cue in the set at 0.08 while every other cue sits
    between 0.10 and 0.34. That inversion is the entire point: there is no gas
    left to carry a reverb tail, so the room audibly stops existing at the
    exact moment ``b.vac`` reaches zero.
    """

    audible = 1.80
    n = L(audible)
    r = rng("hard_vacuum")
    thud = modal(n, [33, 52, 79], [0.55, 0.40, 0.26], [1.0, 0.6, 0.3], r)
    swallow = circ_noise(n, r, 40.0, 900.0, tilt=-1.6) * env_ad(n, 0.004, 0.28, 4.0)
    body = (norm(thud) + 0.5 * norm(swallow)) * np.clip(
        1.0 - (np.arange(n) / n) ** 1.4, 0, 1)
    return pad(conv_lin(body, IR, 0.08), audible)


def clamp_close():
    """CRADLE CLAMPS TAKING YOUR WEIGHT.

    Fired when the clamps START moving, not when they finish, so the two
    hydraulic strokes (0.00, 0.72) and the latch (1.42) all sit INSIDE
    ``clamp_seconds`` = 1.6 and the latch lands 0.18 s before the pose
    settles. On the finished edge the latch would be heard a second and a half
    after the clamps were visibly already shut - which is why this cue is
    1.75 s audible rather than the 1.35 s a naive fit to the two strokes would
    give.
    """

    audible = 1.75
    n = L(audible)
    r = rng("clamp_close")
    x = np.zeros(n)
    for start, gain in ((0.00, 0.72), (0.72, 0.86)):
        first = int(start * SR)
        span = n - first
        x[first:] += gain * norm(circ_noise(span, r, 90.0, 2600.0, tilt=-1.0)
                                 * env_ad(span, 0.02, 0.30, 2.2))
    first = int(1.42 * SR)
    span = n - first
    x[first:] += norm(modal(span, [610, 1180, 2340], [0.09, 0.055, 0.03],
                            [1, .6, .3], r) * env_ad(span, 0.0005, 0.045, 3.0))
    return pad(conv_lin(norm(x), IR, 0.20), audible)


def stage_tick():
    """ONE CONTACTOR PER RUNG OF STAGE_FRACS - a clack AND the ring after it.

    ONE file, eight pitches: the runtime pushes a semitone per rung
    (AUDIO_STAGE_TICK_PITCH), so the eight console announcements are audibly a
    rising scale that resolves a perfect fifth up on the last one. Eight
    separate files would be eight things to keep in step with a list that
    lives in Lua.

    Partials at 880/1760/3520/5280 - octaves and a fifth of A5 - so the whole
    ladder stays consonant with itself when it is transposed.

    IT USED TO BE 10 MILLISECONDS LONG AND IT FIRED UNDER THE RIDE BED.
    Measured in game: spin_loop buried it by 26.8 dB, which for the one cue
    that exists to ANNOUNCE something is a total failure. The cause was in the
    shape, not the mix, and the mix could not have rescued it: the modal bank
    was multiplied by env_ad(0.0004, 0.030, curve 3.0), i.e. exp(-100t), so
    the 55/34/20/12 ms mode taus were irrelevant and every one of them was
    dead in a tenth of a time constant. A 30 ms blip has almost no energy in
    a 400 ms window no matter what its peak is, and there is no fader setting
    that makes one audible under a continuous bed.
    -22.34 dBFS momentary, against a set targeting -7.0.
    So the strike keeps its 10 ms envelope - that is the CLACK, and it is
    right - and a RING is added underneath it: the same partial family with
    real decay and no shaping envelope over the top, which is what a
    contactor the size of a car door actually does. Audible span 0.42 -> 0.70 s
    so the 340 ms ring is not truncated into a click by its own pad.
    Measured after the change: -13.0 dBFS momentary, +9.4 dB, which the 6 dB
    drive cap can finish.
    THE LADDER STILL FITS: the fastest rung spacing is the bottom power rung,
    4.40 s of ramp over 8 stages = 0.55 s, so two ticks overlap by 0.15 s.
    They are the same source, so the second play restarts the first - a relay
    bank interrupted mid-ring is what that sounds like, and it is correct.
    """

    audible = 0.70
    n = L(audible)
    r = rng("stage_tick")
    t = np.arange(n) / SR
    strike = modal(n, [880, 1760, 3520, 5280], [0.055, 0.034, 0.020, 0.012],
                   [1, .6, .34, .18], r) * env_ad(n, 0.0004, 0.030, 3.0)
    # The ring. Same octave-and-fifth family so the transposed ladder stays
    # consonant; taus are the real decay of the thing that was struck, and
    # nothing multiplies them away. 0.6 ms of attack so the onset is still a
    # strike and not a swell.
    ring = modal(n, [880, 1320, 1760, 2640, 3520],
                 [0.46, 0.36, 0.28, 0.18, 0.12],
                 [1, .65, .55, .32, .18], r) * np.clip(t / 0.0006, 0.0, 1.0)
    x = norm(strike) + 1.15 * norm(ring)
    x += 0.35 * norm(circ_noise(n, r, 1800, 8000, tilt=-0.8)
                     * env_ad(n, 0.0003, 0.010, 4.0))
    return pad(conv_lin(norm(x), IR, 0.22), audible)


def muzzle_open():
    """THE HATCH CRACKING while you are already at release velocity.

    Five modes for the crack, then a slide that FADES rather than lands - the
    cue deliberately has no resolution, because neither does the moment.
    1.55 s audible against ``muzzle_seconds`` = 1.4, so it outlives the
    travel by 0.15 s and the silence that follows is the beat before the
    throw.
    """

    audible = 1.55
    n = L(audible)
    r = rng("muzzle_open")
    crack = modal(n, [128, 197, 302, 455, 690],
                  [0.30, 0.24, 0.18, 0.12, 0.08],
                  [1, .7, .5, .34, .2], r) * env_ad(n, 0.001, 0.10, 3.0)
    t = np.arange(n) / SR
    slide = circ_noise(n, r, 200.0, 7000.0, tilt=-0.8)
    slide *= np.clip((t - 0.06) / 0.20, 0, 1) * np.clip(1.0 - (t / audible) ** 2.2, 0, 1)
    return pad(conv_lin(norm(crack) + 0.66 * norm(slide), IR, 0.24), audible)


def release_bang():
    """SEPARATION.

    The loudest event in the mod (mix volume 1.00) and the longest tail: a
    wideband crack, nine shell modes from 29 Hz with taus out to 2.60 s, and a
    tube resonance decaying at 0.85 s. The wettest cue of all at 0.34, so the
    chamber rings for a full second after you have left it - which is the only
    way a player who is now doing 182 m/s down a tube gets to hear the room
    they just came out of.
    """

    audible = 4.20
    n = L(audible)
    r = rng("release_bang")
    t = np.arange(n) / SR
    crack = circ_noise(n, r, 45.0, 14000.0, tilt=-0.35) * env_ad(n, 0.0004, 0.070, 3.4)
    shell = modal(n, [29, 44, 68, 101, 152, 226, 338, 505, 742],
                  [2.60, 2.10, 1.70, 1.32, 1.00, 0.72, 0.50, 0.33, 0.21],
                  [1, .86, .70, .55, .42, .30, .21, .14, .09], r)
    tube = circ_noise(n, r, 90.0, 3200.0, tilt=-0.9) * np.clip(
        (t - 0.02) / 0.05, 0, 1) * np.exp(-t / 0.85)
    return pad(conv_lin(norm(crack) + 0.80 * norm(shell)
                        + 0.62 * norm(tube), IR, 0.34), audible)


def shutdown():
    """POWER-DOWN, on the falling edge of EVERY way the spin can end.

    A drive whine falling 234 Hz -> 24 Hz with a 2.30 s time constant, nine
    clatters spaced by a 1.5-power so they thin out as things come to rest,
    and a settling bed. 6.60 s audible: the real spin-down from the top rung
    is 11.4465 / 1.10 = 10.4 s, so this is a COMPRESSION, not a match - the
    cue covers the dramatic end of the spin and ``repress`` covers the rest.
    """

    audible = 6.60
    n = L(audible)
    r = rng("shutdown")
    t = np.arange(n) / SR
    phase = 2 * np.pi * np.cumsum(210.0 * np.exp(-t / 2.30) + 24.0) / SR
    whine = (np.sin(phase) + 0.52 * np.sin(2 * phase)
             + 0.26 * np.sin(3 * phase)) * np.exp(-t / 3.1)
    clatter = np.zeros(n)
    for k in range(9):
        first = int((0.35 + 4.9 * (k / 8.0) ** 1.5) * SR)
        span = min(L(0.30), n - first)
        if span <= 0:
            continue
        clatter[first:first + span] += (0.9 - 0.07 * k) * norm(
            modal(span, [150 + 40 * k, 380 + 70 * k, 910], [0.05, 0.03, 0.02],
                  [1, .55, .3], r) * env_ad(span, 0.0006, 0.040, 3.0))
    settle = circ_noise(n, r, 40.0, 700.0, tilt=-1.1) * np.exp(-t / 1.7)
    return pad(conv_lin(0.90 * norm(whine) + 0.60 * norm(clatter)
                        + 0.4 * norm(settle), IR, 0.22), audible)


# name, builder, audible seconds (None = a loop, stopped by state)
CUES = [
    ("arm_charge", arm_charge, None),
    ("detect_klaxon", detect_klaxon, 1.60),
    ("door_travel", door_travel, None),
    ("door_slam", door_slam, 2.40),
    ("pump_down", pump_down, None),
    ("hard_vacuum", hard_vacuum, 1.80),
    ("deck_retract", deck_retract, None),
    ("clamp_close", clamp_close, 1.75),
    ("spin_loop", spin_loop, None),
    ("stage_tick", stage_tick, 0.70),
    ("muzzle_open", muzzle_open, 1.55),
    ("release_alarm", release_alarm, None),
    ("release_bang", release_bang, 4.20),
    ("shutdown", shutdown, 6.60),
    ("repress", repress, None),
    ("abort_klaxon", abort_klaxon, None),
]

# Cues the runtime RE-PITCHES, and the ceiling their content has to stay
# under so that a playback-rate change does not fold it back.
#
# THIS IS APPLIED AFTER THE LIMITER, NOT INSIDE THE BUILDER. Soft clipping is
# a harmonic generator, so brickwalling spin_loop at 10800 Hz in its own
# builder and then driving it 3.3 dB into a limiter puts new energy straight
# back over the ceiling. Measured before this moved: spin_loop's worst bin
# above 10813 Hz went from 0.014 percent of peak to 1.9 percent, which is
# twice the gate. The ceiling has to be the LAST thing that touches the
# waveform.
# The one loop whose START MEANS SOMETHING, and therefore the one that may
# not be rotated: arm_charge's clicks accelerate INTO the arm instant, and
# its clip length is pinned to BEHAVIOR["arm_delay_s"] so the twelfth click
# lands on the frame the machine commits (spec.py asserts that coupling at
# import). Rotating it would move the countdown's start into the middle of
# its own acceleration. Its own wrap is -3.8 dB and is never reached, because
# the cue is stopped on the same frame it would wrap.
SEAM_ALIGN_EXEMPT = {"arm_charge"}

PITCH_CEILING_HZ = {
    "spin_loop": SPIN_PARTIAL_CAP_HZ,
    # stage_tick is transposed up a perfect fifth at the top rung, so its own
    # ceiling is (48000/2) / 1.4983 = 16018 Hz. Rounded down for margin.
    "stage_tick": 16000.0,
}

# What each cue is, in one line, for the manifest. Kept here rather than
# scraped from the docstrings so the shipped record stays readable when the
# docstrings grow.
NOTES = {
    "arm_charge": "12 modal clicks on a 1.9-power ramp + closed-phase 140->330 Hz whine",
    "detect_klaxon": "Bb4/F4 alternating at 2 Hz, closed phase, cubic decay",
    "door_travel": "rail noise 55-900 Hz + 31 Hz hydraulic stack + 1.4-6 kHz grind",
    "door_slam": "8 plate modes 41-688 Hz, tau to 1.30 s, + broadband strike",
    "pump_down": "42 Hz Roots lobe stack + 420-9k gas hiss + 28-150 Hz rumble",
    "hard_vacuum": "3 modes 33/52/79 Hz + swallowed thud, driest reverb in the set",
    "deck_retract": "100 Hz screw stack (60 partials) + 34-260 Hz slab rumble",
    "clamp_close": "2 hydraulic strokes at 0.00/0.72 + latch modal at 1.42",
    "spin_loop": "55 Hz stack (jitter 0.06) + 165 Hz drive + wash, brickwalled 10800 Hz",
    "stage_tick": "10 ms clack (880-5280 Hz) over a 340 ms contactor ring, re-pitched per rung",
    "muzzle_open": "5 crack modes 128-690 Hz + unresolved 200-7k slide",
    "release_alarm": "3 Hz gated FM about 620 Hz, closed phase, +310 Hz stack",
    "release_bang": "wideband crack + 9 shell modes 29-742 Hz (tau 2.60 s) + tube",
    "shutdown": "234->24 Hz whine (tau 2.30 s) + 9 clatters on a 1.5-power + settle",
    "repress": "300-11k rush + 45-320 Hz body, the inverse of hard_vacuum",
    "abort_klaxon": "G4/D#4 switched at 1.25 Hz, closed phase, 3 harmonics",
}


def seam_ratio(x):
    """Wrap discontinuity as a multiple of the signal's own RMS sample step.

    Near 1 is inaudible - it is the size of a normal sample-to-sample move.
    The gate is 3.0. Measured pre-encode against post-decode, the Vorbis
    lapped transform contributes about 0.2, so anything above 3.0 is a
    synthesis bug and not the codec.
    """

    step = np.diff(x)
    rms = float(np.sqrt(np.mean(step ** 2)))
    return abs(float(x[0]) - float(x[-1])) / rms if rms else 0.0


def _finish(name, raw, audible):
    """Loudness, then ceiling, then peak - in that order and no other.

    ``pad`` has already zeroed everything past ``audible``; the limiter is
    memoryless so it cannot disturb that, but the brickwall is a circular
    convolution and WILL ring a few samples of the tail back round into the
    pad. Re-zeroing afterwards is what keeps
    ``test_stop_clock_lands_inside_a_silent_pad`` honest, and it is one
    multiply.
    """

    x, drive = loud_norm(raw)
    ceiling = PITCH_CEILING_HZ.get(name)
    if ceiling is not None:
        x = brickwall(x, ceiling)
        if audible is not None:
            keep = L(audible)
            fade = min(L(FADE_OUT_SECONDS), keep)
            x[keep - fade:keep] *= 0.5 * (1 + np.cos(np.pi * np.arange(fade) / fade))
            x[keep:] = 0.0
            rise = min(L(ONSET_RAMP_SECONDS), keep)
            x[:rise] *= 0.5 * (1 - np.cos(np.pi * np.arange(rise) / rise))
    if audible is None and name not in SEAM_ALIGN_EXEMPT:
        x = seam_align(x)
    return norm(x, MASTER_PEAK).astype(np.float32), drive


def render():
    """Every cue as float32 PCM, in table order. Importable for analysis."""

    out = []
    for name, build, audible in CUES:
        samples, drive = _finish(name, build(), audible)
        out.append((name, samples, audible, drive))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entries, total = [], 0
    for name, samples, audible, drive in render():
        path = OUT / f"{MOD_ID}_{name}.ogg"
        sf.write(path, samples, SR, format="OGG", subtype="VORBIS",
                 compression_level=QUALITY)
        size = path.stat().st_size
        total += size
        decoded, _rate = sf.read(path, dtype="float32")
        ratio = seam_ratio(decoded)
        if audible is None and ratio > 3.0:
            raise AssertionError(f"{name}: loop seam {ratio:.2f} > 3.0")
        wrap = wrap_level_db(decoded) if audible is None else None
        entries.append({
            "name": name,
            "file": f"{MOD_ID}_{name}.ogg",
            "loop": audible is None,
            "seconds": round(len(samples) / SR, 4),
            "audible_end_s": None if audible is None else round(audible, 4),
            "silent_pad_s": None if audible is None else PAD_SECONDS,
            "recommended_stop_s": (None if audible is None
                                   else round(audible + STOP_OFFSET, 4)),
            "loop_seam_ratio": round(ratio, 4) if audible is None else None,
            # The ENERGY step across the wrap, which the sample-step ratio
            # above is structurally blind to. dB, head against tail, 20 ms
            # windows. See level_lock.
            "loop_wrap_db": None if wrap is None else round(wrap, 4),
            "peak": round(float(np.max(np.abs(decoded))), 6),
            "rms": round(float(np.sqrt(np.mean(decoded.astype(np.float64) ** 2))), 6),
            # THE NUMBER THE MIX IS DERIVED FROM. spec.AUDIO_CUE_TABLE reads
            # this back out of the manifest and solves each cue's vol so the
            # DELIVERED ladder is what the design says it is - peak and rms
            # above are description, this is the measurement.
            "momentary_dbfs": round(momentary_dbfs(decoded.astype(np.float64)), 4),
            "limiter_drive_db": round(drive, 4),
            "bytes": size,
            "notes": NOTES[name],
            # File bytes are NOT reproducible (Ogg serial, offset 14); decoded
            # PCM is. This is the hash the gate compares.
            "pcm_sha256": hashlib.sha256(decoded.tobytes()).hexdigest(),
        })
        print(f"{name:<15} {len(samples) / SR:6.3f}s {size:8d} B  "
              f"peak {entries[-1]['peak']:.3f}  rms {entries[-1]['rms']:.4f}  "
              f"mom {entries[-1]['momentary_dbfs']:7.2f}  "
              f"drive {drive:4.1f}  seam {ratio:5.2f}"
              + (f"  wrap {wrap:+5.2f} dB" if wrap is not None else ""))
    MANIFEST_PATH.write_text(json.dumps({
        "seed": SEED,
        "samplerate": SR,
        "channels": 1,
        "codec": "ogg/vorbis",
        "compression_level": QUALITY,
        "silent_pad_s": PAD_SECONDS,
        "stop_offset_s": STOP_OFFSET,
        "fade_out_s": FADE_OUT_SECONDS,
        "reverb_rt60_s": REVERB_RT60_S,
        "reverb_ir_truncated_s": REVERB_IR_SECONDS,
        "spin_partial_cap_hz": SPIN_PARTIAL_CAP_HZ,
        "momentary_window_s": MOMENTARY_WINDOW_S,
        "loudness_target_dbfs": LOUDNESS_TARGET_DBFS,
        "max_drive_db": MAX_DRIVE_DB,
        # File bytes are NOT reproducible; decoded PCM is. See the module
        # docstring - this string is load-bearing documentation, not a note.
        "reproducible": "decoded PCM only",
        "total_bytes": total,
        "cues": entries,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"TOTAL {total} B = {total / 1024:.1f} KiB -> {OUT}")


if __name__ == "__main__":
    main()

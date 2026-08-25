"""Static gates for the spin_launch cue set.

Sixteen procedurally synthesised Ogg cues built by
``examples/giant_props/spin_launch/authoring/make_spin_launch_audio.py``. None
of what follows can prove the mod makes a NOISE - only a live run with a
loopback recording does that, and the risk ledger at the bottom of
``spec.py``'s cue block says which four silent-failure paths sit between here
and a speaker. What this file proves is everything that is decidable from the
artifacts, and in particular the four properties that would each fail silently
in game: an unreproducible bank, a loop that clicks, a spin loop that aliases
when the runtime pitches it up, and a stop clock that lands outside its pad.

REPRODUCIBILITY IS ON DECODED PCM, NOT FILE BYTES. Measured 2026-08-25: two
runs of the generator under different PYTHONHASHSEED produced .ogg files
differing in exactly 48 of 20736 bytes for spin_loop, the first at offset 14 -
the Ogg bitstream serial number libvorbis randomises per encode, plus the page
CRCs covering it. The decoded PCM was bit-identical, and so was the manifest.
Hashing file bytes here would fail on the first rerun and, worse, would make
dist/ericrolph_spin_launch.lock.json churn on every rebuild for no change in
sound - which is the exact trap that lock file exists to catch.
"""

from __future__ import annotations

import hashlib
import json
import re

import numpy as np
import pytest

from tests.test_giant_props_pack import PACK_ROOT, load_spec

sf = pytest.importorskip("soundfile")

MOD_KEY = "spin_launch"
SPEC = load_spec(MOD_KEY)
SOUND = PACK_ROOT / MOD_KEY / "assets" / "sound"
# THE FILES A PLAYER ACTUALLY HEARS. Everything above measures the AUTHORED
# bank in assets/, which is the generator's output; what ships is the staged
# copy under the vehicle folder, and nothing in this file used to look at it.
# They are byte-identical today. Nothing kept them so, and the two gates that
# matter most - the loudness the mix is solved from, and the mix itself - are
# now measured on THESE.
SHIPPED_SOUND = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID / "sound"
MANIFEST = json.loads(
    (PACK_ROOT / MOD_KEY / "authoring" / "spin_launch_audio_manifest.json")
    .read_text(encoding="utf-8"))
BY_NAME = {entry["name"]: entry for entry in MANIFEST["cues"]}

# The pack's own pad rule, read off pachinko_audio_manifest.json (pin_soft_01
# audible_end 0.595 / recommended_stop 0.82). Restated here rather than read
# from the manifest, so a generator that changed it has to change this too.
STOP_OFFSET = 0.225
LOOP_SEAM_LIMIT = 3.0
BUDGET_BYTES = 410_000


def _read(name):
    data, rate = sf.read(SOUND / f"{SPEC.MOD_ID}_{name}.ogg", dtype="float32")
    return data, rate


def _read_shipped(name):
    data, rate = sf.read(
        SHIPPED_SOUND / f"{SPEC.MOD_ID}_{name}.ogg", dtype="float32")
    return data, rate


# The momentary-loudness definition the generator solved the mix from,
# RE-DERIVED here rather than imported: the loudest 400 ms sliding energy
# window, unweighted, hopped every 100 ms. Restating it is the point - a
# generator that quietly changed its own window would otherwise move every
# manifest number and every fader together and nothing would notice.
MOMENTARY_WINDOW_S = 0.400
MOMENTARY_HOP_S = 0.100


def momentary_dbfs(samples, rate):
    x = np.asarray(samples, dtype=np.float64)
    window = int(MOMENTARY_WINDOW_S * rate)
    if len(x) <= window:
        return 10.0 * np.log10(float(np.mean(x ** 2)) + 1e-20)
    cumulative = np.concatenate(([0.0], np.cumsum(x ** 2)))
    hop = max(1, int(MOMENTARY_HOP_S * rate))
    energies = (cumulative[window::hop] - cumulative[:-window:hop]) / window
    return 10.0 * np.log10(float(np.max(energies)) + 1e-20)


def measured_momentary():
    """Every shipped cue's loudness, MEASURED off the .ogg on the way out."""

    out = {}
    for name in SPEC.AUDIO_CUE_NAMES:
        data, rate = _read_shipped(name)
        out[name] = momentary_dbfs(data, rate)
    return out


def test_manifest_and_cue_table_and_ship_assets_agree():
    """One name set, three places: the shipped table, the authoring manifest,
    and SHIP_ASSETS. spec.py's own import-time guard covers the fourth (the
    files actually on disk), but only when the directory exists."""

    assert set(BY_NAME) == set(SPEC.AUDIO_CUE_NAMES)
    assert set(SPEC.SHIP_ASSETS) == {
        f"sound/{SPEC.MOD_ID}_{name}.ogg" for name in SPEC.AUDIO_CUE_NAMES}
    assert len(SPEC.SHIP_ASSETS) == 16
    on_disk = {path.name for path in SOUND.glob("*.ogg")}
    assert on_disk == {f"{SPEC.MOD_ID}_{n}.ogg" for n in SPEC.AUDIO_CUE_NAMES}


def test_manifest_republishes_the_constants_spec_depends_on():
    """The generator and spec.py each hold their own copy of three numbers.
    The manifest is where they are compared: drift here is drift between a
    sound that was BAKED one way and a runtime that assumes another."""

    assert MANIFEST["samplerate"] == 48000
    assert MANIFEST["channels"] == 1
    assert MANIFEST["codec"] == "ogg/vorbis"
    assert MANIFEST["spin_partial_cap_hz"] == SPEC.SPIN_PARTIAL_CAP_HZ
    assert MANIFEST["stop_offset_s"] == STOP_OFFSET
    assert MANIFEST["reproducible"] == "decoded PCM only"


@pytest.mark.parametrize("name", SPEC.AUDIO_CUE_NAMES)
def test_cue_is_mono_48k(name):
    """FMOD downmixes 3D sources to mono, so stereo here would be bytes
    thrown away; 48 kHz matches the rest of the pack."""

    data, rate = _read(name)
    assert rate == 48000
    assert data.ndim == 1, f"{name} is not mono"
    assert len(data) > 0, f"{name} decoded empty"


@pytest.mark.parametrize("name", SPEC.AUDIO_CUE_NAMES)
def test_decoded_pcm_is_reproducible(name):
    """The bank is a committed artifact and the generator is deterministic;
    this is the assertion that keeps both true. See the module docstring for
    why it is the DECODED samples and never the file bytes."""

    data, _rate = _read(name)
    assert hashlib.sha256(data.tobytes()).hexdigest() == BY_NAME[name]["pcm_sha256"]


@pytest.mark.parametrize("name", SPEC.AUDIO_CUE_NAMES)
def test_cue_is_audible_and_unclipped(name):
    """A silent cue and a clipped cue are the two ways a bank can be wrong
    that no other gate here would notice. Every file is LOUDNESS normalised
    and then peak-scaled to MASTER_PEAK = 0.82, which is 1.7 dB of headroom
    for the codec's transient overshoot; measured decoded peaks land
    0.824-0.900 with zero samples at full scale. 0.82 and not the old 0.89
    because a limited waveform is denser and overshoots harder - at 0.89 the
    same set decoded up to 1.003, i.e. CLIPPED. The DC bound matters because
    a source with an offset wastes headroom and thumps when FMOD starts it."""

    data, _rate = _read(name)
    samples = data.astype(np.float64)
    peak = float(np.max(np.abs(samples)))
    assert 0.80 <= peak <= 0.95, f"{name}: peak {peak:.3f}"
    assert int(np.sum(np.abs(samples) >= 0.9999)) == 0, f"{name}: clipped"
    rms = float(np.sqrt(np.mean(samples ** 2)))
    assert rms > 0.02, f"{name}: rms {rms:.4f} - effectively silent"
    assert abs(float(np.mean(samples))) < 5e-3, f"{name}: DC offset"


@pytest.mark.parametrize("name,stop,_vol", SPEC.AUDIO_CUE_TABLE)
def test_stop_clock_lands_inside_a_silent_pad(name, stop, _vol):
    """EVERY ONE-SHOT IS A LOOP WEARING A STOP CLOCK: AudioDefaultLoop3D is
    the only description this pack has proven audible, so a one-shot wraps
    forever unless the clock stops it. The stop must land AFTER the content
    and BEFORE the wrap, or the player hears either a cut or a repeat."""

    data, rate = _read(name)
    entry = BY_NAME[name]
    if stop is None:
        assert entry["loop"], f"{name} has no stop clock but is not a loop"
        assert entry["audible_end_s"] is None
        return
    assert not entry["loop"], f"{name} has a stop clock but is marked a loop"
    total = len(data) / rate
    assert stop < total, f"{name}: stop {stop} >= length {total}"
    assert stop == entry["recommended_stop_s"], f"{name}: table vs manifest"
    audible = entry["audible_end_s"]
    assert abs((audible + STOP_OFFSET) - stop) < 1e-9, (
        f"{name}: stop is not audible_end + {STOP_OFFSET} (the pack's pad rule)")
    tail = data[int(stop * rate):]
    assert len(tail) > 0
    assert float(np.max(np.abs(tail))) < 1e-3, (
        f"{name}: audible content after the stop clock at {stop} s")
    # ...and the cue is not simply empty on the near side of it.
    body = data[: int(audible * rate)]
    assert float(np.max(np.abs(body))) > 0.5, f"{name}: nothing before the stop"


@pytest.mark.parametrize("name", [n for n, s, _v in SPEC.AUDIO_CUE_TABLE if s is None])
def test_loops_wrap_without_a_click(name):
    """Wrap discontinuity as a multiple of the signal's own RMS sample step.
    Near 1 is the size of a normal sample-to-sample move and is inaudible;
    the Vorbis lapped transform contributes about 0.2 of whatever is measured
    here, so anything above 3.0 is a synthesis bug and not the codec.

    Two real bugs were found by exactly this number and both would regress
    silently: a switched frequency track whose accumulated phase did not
    close over the buffer, and a ``sin(2*pi*f(t)*t)`` that was a quadratic
    chirp rather than an FM. The generator's ``closed_phase`` is the fix for
    both, and the worst loop in the shipped set now measures 2.05.

    NECESSARY AND NOT SUFFICIENT. This is a SAMPLE-step test and it is
    structurally blind to a LEVEL step at the same seam; see
    test_loops_hold_their_level_across_the_wrap, which is the other half."""

    data, _rate = _read(name)
    samples = data.astype(np.float64)
    step = float(np.sqrt(np.mean(np.diff(samples) ** 2)))
    ratio = abs(float(samples[0]) - float(samples[-1])) / step
    assert ratio <= LOOP_SEAM_LIMIT, f"{name}: loop seam {ratio:.2f}"
    assert ratio == pytest.approx(BY_NAME[name]["loop_seam_ratio"], abs=5e-3)


@pytest.mark.parametrize("name", [n for n, s, _v in SPEC.AUDIO_CUE_TABLE if s is not None])
def test_one_shots_start_from_silence(name):
    """A one-shot here is a loop with a stop clock, and the clock runs in the
    vehicle VM. If it ever fails - a pcall that swallowed something, an
    updateGFX chain that got re-wrapped - the cue wraps forever, and a cue
    whose first sample is a third of full scale wraps with a click 79x its
    own RMS sample step every period, for as long as the prop exists.
    Starting from zero makes that failure silent rather than a machine-gun,
    and it costs 1 ms of onset."""

    data, _rate = _read(name)
    peak = float(np.max(np.abs(data)))
    assert abs(float(data[0])) < 0.02 * peak, f"{name}: hard onset"
    assert abs(float(data[-1])) < 1e-4, f"{name}: does not end in silence"


def test_spin_loop_cannot_alias_when_the_runtime_pitches_it_up():
    """FMOD pitch is a playback-RATE change, i.e. resampling. The runtime
    pitches spin_loop to AUDIO_SPIN_PITCH_MAX = 182/82 = 2.2195, so any
    content above (48000/2)/2.2195 = 10813 Hz folds back as an audible
    metallic buzz at exactly the moment the machine is loudest - and it would
    only ever appear at full power, which is the setting nobody tests twice.
    Measured margin in the shipped file is 0.00014 against a 0.01 gate."""

    data, rate = _read("spin_loop")
    spectrum = np.abs(np.fft.rfft(data.astype(np.float64)))
    freqs = np.fft.rfftfreq(len(data), 1.0 / rate)
    ceiling = (rate / 2) / SPEC.AUDIO_SPIN_PITCH_MAX
    assert ceiling == pytest.approx(10813.2, abs=0.1)
    above = spectrum[freqs > ceiling]
    assert float(np.max(above)) < 0.01 * float(np.max(spectrum)), (
        f"spin_loop has energy above {ceiling:.0f} Hz and will alias")


def test_stage_tick_cannot_alias_across_its_ladder():
    """Same failure, other cue: stage_tick is re-pitched a semitone per rung
    up to a perfect fifth, so its own top partial has to clear Nyquist at
    1.4983x."""

    data, rate = _read("stage_tick")
    spectrum = np.abs(np.fft.rfft(data.astype(np.float64)))
    freqs = np.fft.rfftfreq(len(data), 1.0 / rate)
    ceiling = (rate / 2) / SPEC.AUDIO_STAGE_TICK_PITCH[-1]
    above = spectrum[freqs > ceiling]
    assert float(np.max(above)) < 0.01 * float(np.max(spectrum))


def test_the_shipped_runtime_carries_the_pitch_ladder_spec_solved():
    """THE AUTOMATION CONSTANTS, READ OFF THE ARTEFACT THAT USES THEM.

    What this test used to do was restate spec.py's own definitions back at
    it: AUDIO_SPIN_PITCH_MAX is DEFINED as POWER_STEPS_MPS[-1] / REF, and the
    assertion was that it equalled POWER_STEPS_MPS[-1] / REF. Same for MIN,
    same for the tick ladder's length and both ends, and
    `SPIN_PARTIAL_CAP_HZ * PITCH_MAX < 24000` was a verbatim copy of the
    import-time assert at spec.py:4545 - which raises at import, so pytest
    would report a COLLECTION ERROR and this line could never be the thing
    that went red.

    The genuine risk those lines were reaching for is real, and it is DRIFT:
    these constants are spliced into the shipped Lua, and behaviour code
    re-splices on a build.py run while behaviour PARAMS only move on a
    Blender run. So read the shipped runtime and hold it to the ladder the
    console prints. A stale splice fails here; a re-solved spec that never
    reached the artefact fails here.

    The aliasing claim is not restated at all: it is MEASURED, on the decoded
    spectrum, by test_spin_loop_cannot_alias_when_the_runtime_pitches_it_up.
    """

    runtime = (PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions"
               / SPEC.MOD_ID / "runtime.lua").read_text(encoding="utf-8")

    def shipped(name):
        match = re.search(rf"^local {name} = ([-\d.]+)$", runtime, re.MULTILINE)
        assert match, f"{name} is not in the shipped runtime"
        return float(match.group(1))

    # The ladder the console prints, re-derived from POWER_STEPS_MPS here and
    # compared against what a player's copy of the Lua actually holds.
    assert shipped("AUDIO_SPIN_PITCH_REF") == pytest.approx(
        SPEC.POWER_STEPS_MPS[SPEC.POWER_NOM_INDEX - 1], abs=1e-9)
    assert shipped("AUDIO_SPIN_PITCH_MAX") == pytest.approx(
        SPEC.POWER_STEPS_MPS[-1] / SPEC.POWER_STEPS_MPS[SPEC.POWER_NOM_INDEX - 1],
        abs=5e-5)
    assert shipped("AUDIO_SPIN_PITCH_MIN") == pytest.approx(
        SPEC.POWER_STEPS_MPS[0]
        / SPEC.POWER_STEPS_MPS[SPEC.POWER_NOM_INDEX - 1] / 2.0, abs=5e-5)
    assert shipped("AUDIO_SPIN_VOL_TOP_MPS") == pytest.approx(
        SPEC.POWER_STEPS_MPS[-1], abs=1e-9)

    # The tick ladder, likewise: one semitone per rung, resolving a perfect
    # fifth, and the shipped table has to have as many entries as the runtime
    # has rungs or the top rung silently replays pitch 1.0.
    match = re.search(r"^local AUDIO_TICK_PITCH = \{([^}]*)\}$",
                      runtime, re.MULTILINE)
    assert match, "the shipped runtime has no tick ladder"
    ticks = [float(token) for token in match.group(1).split(",")]
    rungs = runtime.split("local STAGE_FRACS = {")[1].split("}")[0].count(",") + 1
    assert len(ticks) == rungs, (len(ticks), rungs)
    assert ticks == pytest.approx(
        [2.0 ** (index / 12.0) for index in range(rungs)], abs=5e-5)
    assert ticks[-1] == pytest.approx(2.0 ** (7 / 12), abs=5e-5), (
        "the ladder no longer resolves on a perfect fifth")

    # ...and the volume law's ceiling stays under release_bang's 1.00, so the
    # throw is still the loudest single event in the mod.
    volumes = {name: volume for name, _stop, volume in SPEC.AUDIO_CUE_TABLE}
    assert shipped("AUDIO_SPIN_VOL_CEIL") < volumes["release_bang"] == 1.00
    assert shipped("AUDIO_SPIN_VOL_FLOOR") < shipped("AUDIO_SPIN_VOL_CEIL")
    assert all(0.0 < volume <= 1.0 for volume in volumes.values())


def test_the_audio_emitter_is_resolved_by_name_from_the_chamber():
    """THE EMITTER IS A NAME NOW, AND THIS GATE READS THE SHIPPED RUNTIME.

    ``obj:createSFXSource`` takes a node CID, and a CID IS NOT A JBEAM ROW
    INDEX: BeamNG renumbers fixed nodes ahead of free ones. The mod shipped
    the literal 0 on the strength of the jbeam's first ROW being
    ``bore_0_00_0``, and asked from inside the prop's own vehicle VM on
    2026-08-25, ``obj:getNodePosition(0)`` returned (-4.500, -50.600, 0.100)
    with 607 nodes in the cage - a plinth corner 0.10 m off the terrain, out
    on the apron. Every one of the sixteen cues was emitting from a kerb.

    THE OLD GATE COULD NOT SEE IT AND NO GATE OF ITS SHAPE COULD. It indexed
    the shipped jbeam's node list, which is AUTHORING order, so it proved a
    property of a text file and reported it as a property of the machine.
    Reading the handoff would have been the same mistake in another file.

    So this one reads the NAME out of the shipped runtime - both halves of
    it, because the GE side resolves and the vehicle side receives - and then
    looks that name up in the shipped jbeam. Everything it asserts is about
    the node the running mod will actually emit from.
    """

    import math

    name = SPEC.AUDIO_EMITTER_NODE_NAME
    vehicle_lua = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID
                   / "lua" / f"{SPEC.MOD_ID}_vehicle.lua").read_text(encoding="utf-8")
    runtime_lua = (PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions"
                   / SPEC.MOD_ID / "runtime.lua").read_text(encoding="utf-8")
    assert f'local AUDIO_NODE_NAME = "{name}"' in vehicle_lua
    assert f'local AUDIO_NODE_NAME = "{name}"' in runtime_lua
    # The GE side must resolve it the way the placement frame does, and push
    # the answer over. A resolve with no push is a cid nobody uses.
    assert "resolveNodeCid(state, AUDIO_NODE_NAME)" in runtime_lua
    assert "slAudioNode" in runtime_lua and "M.slAudioNode" in vehicle_lua
    # ...and the vehicle side must REFUSE to build a source without it,
    # loudly. Silently falling back to any index is the original defect.
    assert "if audioNode == nil then" in vehicle_lua
    assert "AUDIO_NODE_UNBOUND" in vehicle_lua
    # A reset re-numbers the cage, so a latched cid has to be dropped.
    assert "b.audioNodeCid = nil" in SPEC.LUA_BEHAVIOR
    assert "state.nodeCids = nil" in SPEC.LUA_BEHAVIOR

    jbeam = json.loads(
        (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID
         / f"{SPEC.MOD_ID}.jbeam").read_text(encoding="utf-8"))
    rows = [row for row in jbeam[SPEC.MOD_ID]["nodes"]
            if isinstance(row, list) and row[0] != "id"]
    matches = [row for row in rows if row[0] == name]
    assert len(matches) == 1, f"{name} appears {len(matches)}x in the cage"
    x, y, z = (float(value) for value in matches[0][1:4])

    # The tether turns in the y-z plane about the hub, which is at
    # (0, 0, HUB_Z) in the vehicle frame just as it is in the authored one.
    in_plane = math.hypot(y, z - SPEC.HUB_Z)
    assert in_plane <= SPEC.SHELL_R, (
        f"{name} is {in_plane:.2f} m from the spin axis - outside the shell,"
        " so every cue emits from off the machine")
    assert abs(x) <= SPEC.OUTER_HALF_X, f"{name} is {x:.2f} m off the disc"
    # ...and the throb the module docstring claims is a real consequence of
    # that position: the payload's distance from this emitter has to swing
    # across AudioDefaultLoop3D's 20 m reference distance, or there is no
    # per-revolution loudness change at all. Node 0 measured 18.5..50.0 m -
    # never inside 20 - which is the failure this number catches.
    distances = [
        math.dist((x, y, z),
                  (0.0, SPEC.PAYLOAD_R * math.cos(a),
                   SPEC.HUB_Z + SPEC.PAYLOAD_R * math.sin(a)))
        for a in (i * math.pi / 180.0 for i in range(360))]
    assert min(distances) < 20.0 < max(distances), (
        f"payload distance sweeps {min(distances):.2f}..{max(distances):.2f} m,"
        " which never crosses the 20 m rolloff reference")
    assert min(distances) == pytest.approx(6.12, abs=0.05)
    assert max(distances) == pytest.approx(36.49, abs=0.05)


def test_the_audio_emitter_index_is_never_authored():
    """No literal node index may come back into either half of the runtime.

    The defect this file exists to prevent recurring is one integer. A future
    edit that "simplifies" the resolution back to a constant would restore it
    exactly, and every other assertion here would still pass.
    """

    vehicle_lua = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID
                   / "lua" / f"{SPEC.MOD_ID}_vehicle.lua").read_text(encoding="utf-8")
    assert not re.search(r"AUDIO_NODE\s*=\s*-?\d", vehicle_lua), (
        "the emitter node is authored as a literal index again")
    assert not hasattr(SPEC, "AUDIO_EMITTER_NODE"), (
        "AUDIO_EMITTER_NODE is back; the emitter is a NAME")
    # createSFXSource must take the bound variable and nothing else.
    assert "audioNode)" in vehicle_lua


def test_the_staged_bank_is_the_bank_the_generator_made():
    """WHAT SHIPS IS NOT WHAT WAS AUTHORED UNTIL SOMETHING SAYS SO.

    prop_builder stages assets/sound into the vehicle folder, and every gate
    in this file measured the AUTHORED side. They are byte-identical today;
    nothing kept them so, and a staging step that silently dropped or
    truncated a cue would leave sixteen green tests and a machine that plays
    the wrong sound - or none. Compared on decoded PCM, which is the same
    identity the reproducibility gate uses and the only one that survives a
    re-encode.
    """

    assert sorted(path.name for path in SHIPPED_SOUND.glob("*.ogg")) == sorted(
        f"{SPEC.MOD_ID}_{name}.ogg" for name in SPEC.AUDIO_CUE_NAMES)
    for name in SPEC.AUDIO_CUE_NAMES:
        authored, authored_rate = _read(name)
        shipped, shipped_rate = _read_shipped(name)
        assert shipped_rate == authored_rate, name
        assert hashlib.sha256(
            np.ascontiguousarray(shipped).tobytes()).hexdigest() == hashlib.sha256(
            np.ascontiguousarray(authored).tobytes()).hexdigest(), name


@pytest.mark.parametrize("name", SPEC.AUDIO_CUE_NAMES)
def test_the_manifest_loudness_is_what_the_shipped_file_measures(name):
    """THE ONE THAT COULD ACTUALLY FAIL, and the reason the mix gate can.

    Every fader in AUDIO_CUE_TABLE is SOLVED from the manifest's
    momentary_dbfs. Nothing checked that the manifest still describes the
    files on disk, so re-synthesising a cue without re-running the generator's
    manifest step - or shipping a hand-edited .ogg - would leave the whole mix
    solved against a number that is no longer true, and every level gate would
    still pass because they all read the same stale figure.

    Measured here off the SHIPPED .ogg with the generator's own momentary
    definition, re-derived above rather than imported.
    """

    data, rate = _read_shipped(name)
    measured = momentary_dbfs(data, rate)
    assert measured == pytest.approx(BY_NAME[name]["momentary_dbfs"], abs=0.02), (
        f"{name}: the shipped file measures {measured:.4f} dBFS against a"
        f" manifest claiming {BY_NAME[name]['momentary_dbfs']:.4f}")


def test_the_delivered_mix_is_the_ladder_the_design_states():
    """THE MIX LEVELS, MEASURED OFF THE SHIPPED AUDIO.

    This gate used to be an identity. Delivered was computed as
    ``momentary + 20*log10(volume)`` from the MANIFEST, and spec.py solves
    ``volume = 10^((reference + rel - momentary)/20)`` from the SAME manifest
    figure, so the momentary term cancelled and what was left was
    ``rel == rel``. Every cue passed to 0.0007 dB - which was round(v, 4)
    noise, not agreement - and substituting any ladder at all still passed.

    The mix itself is good: it was proven in game by WASAPI loopback. What was
    missing was a way to falsify it. So the loudness term now comes from
    DECODING THE SHIPPED .ogg rather than from the table the fader was solved
    against, which makes the residual real: it is the drift between the bank
    on disk and the numbers the mix was derived from, and it is zero only
    while those agree.

    Measured in game at 11.5 m, the peak-normalised set delivered 28.4 dB of
    spread from a 6.0 dB fader table. The ladder is 6.0 dB and the delivered
    spread has to match it.
    """

    assert SPEC.AUDIO_MIX_IS_MEASURED, (
        "spec.py fell back to the un-measured ladder: the audio manifest is"
        " missing, so the shipped mix was never derived from anything")
    assert MANIFEST["momentary_window_s"] == MOMENTARY_WINDOW_S
    volumes = {name: volume for name, _stop, volume in SPEC.AUDIO_CUE_TABLE}
    loudness = measured_momentary()
    delivered = {name: loudness[name] + 20 * np.log10(volumes[name])
                 for name in volumes}
    reference = delivered["release_bang"]
    for name, rung in SPEC.AUDIO_MIX_LADDER_DB.items():
        assert delivered[name] - reference == pytest.approx(rung, abs=0.05), (
            f"{name} delivers {delivered[name] - reference:+.2f} dB against a"
            f" ladder rung of {rung:+.2f}")
    spread = max(delivered.values()) - min(delivered.values())
    assert spread == pytest.approx(6.0, abs=0.10), f"delivered spread {spread:.2f} dB"


def test_release_bang_is_the_loudest_thing_the_machine_does():
    """The money moment. It landed TENTH of sixteen and 11.3 dB under
    abort_klaxon in game, which is the design inverted: the whole sequence is
    a crescendo and this is its peak. Ordered on the MEASURED delivery, so a
    bank that drifted out from under the faders shows up here too."""

    volumes = {name: volume for name, _stop, volume in SPEC.AUDIO_CUE_TABLE}
    loudness = measured_momentary()
    delivered = {name: loudness[name] + 20 * np.log10(volumes[name])
                 for name in volumes}
    order = sorted(delivered, key=delivered.get, reverse=True)
    assert order[0] == "release_bang", f"loudest is {order[0]}, not the throw"
    assert volumes["release_bang"] == 1.00
    # ...and it is the loudest by a MARGIN, not by rounding: the runner-up
    # rung is -1.5 dB and the measurement has to see that gap.
    assert delivered[order[0]] - delivered[order[1]] >= 1.0, order[:3]
    # ...by a stated margin over the next thing, not by a rounding error.
    assert delivered["release_bang"] - delivered[order[1]] >= 1.9


def test_stage_tick_is_audible_over_the_ride_bed():
    """The eight console announcements fire DURING spin_loop. Measured in
    game the bed buried them by 26.8 dB, which for the one cue that exists to
    announce something is total failure - and no fader could have fixed it,
    because the cue was a 10 ms blip with no energy in a 400 ms window at
    any peak. It is a clack over a 340 ms contactor ring now."""

    volumes = {name: volume for name, _stop, volume in SPEC.AUDIO_CUE_TABLE}
    tick = BY_NAME["stage_tick"]["momentary_dbfs"] + 20 * np.log10(volumes["stage_tick"])
    bed = BY_NAME["spin_loop"]["momentary_dbfs"] + 20 * np.log10(SPEC.AUDIO_SPIN_VOL_CEIL)
    assert tick - bed >= 1.0, (
        f"stage_tick delivers {tick - bed:+.2f} dB against the ride bed at its"
        " ceiling; it fires on top of it")
    # ...and the bed's ceiling is the table's own fader, not a second copy.
    assert SPEC.AUDIO_SPIN_VOL_CEIL == volumes["spin_loop"]
    assert SPEC.AUDIO_PUMP_VOL_STRUCT + SPEC.AUDIO_PUMP_VOL_GAS == pytest.approx(
        volumes["pump_down"], abs=1e-4)


@pytest.mark.parametrize(
    "name", [n for n, s, _v in SPEC.AUDIO_CUE_TABLE
             if s is None and n != "arm_charge"])
def test_loops_hold_their_level_across_the_wrap(name):
    """THE SEAM TEST ABOVE IS A SAMPLE-STEP TEST AND IS BLIND TO THIS.

    |s[0] - s[-1]| / RMS step catches a phase discontinuity. It cannot see an
    ENERGY discontinuity, and three of the shipped loops had one: measuring
    20 ms windows head against tail, door_travel stepped -4.4 dB (once, 0.6 s
    before the door slam), deck_retract +2.1 dB (twice) and pump_down
    -1.3 dB. A 4.4 dB drop in a rail bed is a hole, and it lands at the same
    instant every time the loop goes round.

    0.8 to 1.25 is +/-1.9 dB, which is the size of the local RMS wobble that
    band-limited noise has anyway - so this asserts the seam is no worse than
    the middle of the buffer, which is the honest bar.

    arm_charge is exempt and is gated instead by
    test_arm_charge_exactly_fills_the_arm_countdown: it ramps by design, and
    its clip length is pinned to arm_delay_s so its wrap is never reached.
    """

    data, rate = _read(name)
    samples = data.astype(np.float64)
    width = int(0.020 * rate)
    head = float(np.sqrt(np.mean(samples[:width] ** 2)))
    tail = float(np.sqrt(np.mean(samples[-width:] ** 2)))
    assert 0.8 <= tail / head <= 1.25, (
        f"{name}: {20 * np.log10(head / tail):+.2f} dB level step at the wrap")
    assert 20 * np.log10(head / tail) == pytest.approx(
        BY_NAME[name]["loop_wrap_db"], abs=0.02)


def test_arm_charge_exactly_fills_the_arm_countdown():
    """A COUPLING NOTHING ELSE WOULD CATCH.

    arm_charge is twelve relay clicks accelerating geometrically into the arm
    instant, and it is a LOOP: the runtime starts it when arming starts and
    stops it when the machine commits. Its clip is 3.000 s and
    BEHAVIOR["arm_delay_s"] is 3.0, so the twelfth click lands on the
    committing frame and the loop's own -3.8 dB wrap is never reached.

    Both of those are consequences of the two numbers being EQUAL, and
    neither is written down anywhere the other can see. Change arm_delay_s to
    4.0 and the acceleration restarts from slow at t = 3.0 - the countdown
    audibly gets further from firing as it approaches it - with a 3.8 dB
    level drop at the same instant. spec.py asserts this at import; this is
    where a reader will look for it.
    """

    assert BY_NAME["arm_charge"]["seconds"] == pytest.approx(
        SPEC.BEHAVIOR["arm_delay_s"], abs=1e-9)
    assert BY_NAME["arm_charge"]["loop"]
    assert 'cueLoop(state, "arm_charge", b.phase == "arming")' in SPEC.LUA_BEHAVIOR


def test_vehicle_chunk_splices_and_exports():
    """The splice is a silent failure mode: an unreplaced marker leaves a
    syntactically valid but EMPTY Lua table, so every cue looks up nil and
    the mod is mute again with no error anywhere."""

    extra = SPEC.VEHICLE_LUA_EXTRA
    assert "--@AUDIO_" not in extra
    for entry in ("M.slAudioPlay", "M.slAudioStop", "M.slAudioSet",
                  "M.slAudioStopAll", "M.slAudioReport",
                  "M.updateGFX = audioUpdateGFX", "M.onReset = audioOnReset",
                  "M.onExtensionUnloaded = audioOnExtensionUnloaded"):
        assert entry in extra, entry
    for name, stop, volume in SPEC.AUDIO_CUE_TABLE:
        stop_lua = "nil" if stop is None else repr(stop)
        assert f"  {name} = {{stop = {stop_lua}, vol = {volume}}}," in extra
    assert "AudioDefaultLoop3D" in extra
    assert f'vehicles/{SPEC.MOD_ID}/sound/{SPEC.MOD_ID}_' in extra
    # The wrappers must capture the bootstrap's own locals, not globals.
    for capture in ("local audioBaseUpdateGFX = updateGFX",
                    "local audioBaseOnReset = onReset",
                    "local audioBaseOnExtensionUnloaded = onExtensionUnloaded"):
        assert capture in extra, capture


def test_ge_side_helpers_are_defined_before_use():
    """audioSend / cue / cueAt / cueLoop / cueTrack / cueRide must precede
    every caller. Lua will happily compile a call to a nil GLOBAL and only
    fail when that line first runs - which for fireLaunch would be at the
    exact moment of the throw. pachinko_tower shipped this bug once."""

    body = SPEC.LUA_BEHAVIOR
    definition = body.index("local function audioSend(")
    for helper in ("local function cue(", "local function cueAt(",
                   "local function cueLoop(", "local function cueTrack(",
                   "local function cueRide("):
        assert body.index(helper) > definition, helper
    last_helper = max(body.index(helper) for helper in (
        "local function cue(", "local function cueAt(",
        "local function cueLoop(", "local function cueTrack(",
        "local function cueRide("))
    for caller in ("local function armPayload", "local function enterRecover",
                   "local function fireLaunch", "behavior.init = function",
                   "behavior.update = function"):
        assert body.index(caller) > last_helper, f"{caller} precedes the helpers"


def test_every_phase_edge_dispatches_its_cue():
    """The cue set is worth nothing if a cue is never named. This walks the
    generated behaviour and asserts each of the sixteen is dispatched from
    somewhere, and that the two automated beds are TRACKED and not merely
    started - a spin loop that plays at a fixed pitch is the silence problem
    with extra steps."""

    body = SPEC.LUA_BEHAVIOR
    for name in SPEC.AUDIO_CUE_NAMES:
        assert f'"{name}"' in body, f"{name} is never dispatched"
    assert body.count('cueTrack(state, "pump_down"') == 1
    # Four phases ride the bed - spinup, hold, release, abort - plus the one
    # definition. All four say the same two lines, which is why they say it
    # once; a phase that forgot would leave the bed frozen at the previous
    # phase's pitch and nothing would look wrong.
    assert body.count("local function cueRide(state, dt)") == 1
    assert body.count("\n    cueRide(state, dt)") == 4
    # Every loop that is started outside enterRecover has a matching stop.
    for loop in ("arm_charge", "door_travel", "pump_down", "deck_retract",
                 "repress"):
        assert body.count(f'cueLoop(state, "{loop}"') >= 1, loop
    for latched_off in ("spin_loop", "release_alarm", "abort_klaxon"):
        assert f'cueLoop(state, "{latched_off}", false)' in body, latched_off


def test_audio_budget_is_declared():
    """The distribution zip is ZIP_STORED (test_giant_props_pack asserts it),
    so audio adds 1:1 to a ~28.3 MB archive. The set measures 378,694 B -
    up 10,772 B on the peak-normalised bank, almost all of it stage_tick
    growing a 340 ms ring so it can be heard over the ride bed."""

    total = sum(entry["bytes"] for entry in MANIFEST["cues"])
    assert total == MANIFEST["total_bytes"]
    assert total < BUDGET_BYTES, f"cue set grew to {total} B"
    on_disk = sum(path.stat().st_size for path in SOUND.glob("*.ogg"))
    assert on_disk == total, "assets/sound/ does not match the manifest sizes"

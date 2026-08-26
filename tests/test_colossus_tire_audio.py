"""Audio gates for the COLOSSUS cue set - measured on the shipped Oggs.

Inherited rules (spin_launch precedent): Ogg BYTES are never reproducible
(libvorbis stamps a random bitstream serial), so reproducibility is a hash of
DECODED PCM against the committed manifest; loops must be seamless, measured
as the wrap step against the loop's own RMS step; and the cue table, the
manifest and the files on disk may never disagree.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "giant_props" / "colossus_tire"
SOUND = EXAMPLE_ROOT / "assets" / "sound"
MANIFEST = EXAMPLE_ROOT / "authoring" / "colossus_tire_audio_manifest.json"


@pytest.fixture(scope="module")
def spec():
    path = EXAMPLE_ROOT / "spec.py"
    loader = importlib.util.spec_from_file_location("colossus_audio_spec", path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.is_file():
        pytest.skip("no audio manifest; run make_colossus_tire_audio.py")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_cue_table_manifest_and_disk_agree(spec, manifest):
    names = {cue["name"] for cue in manifest["cues"]}
    assert names == set(spec.AUDIO_CUE_NAMES)
    on_disk = {path.name for path in SOUND.glob("*.ogg")}
    assert on_disk == {f"{spec.MOD_ID}_{n}.ogg" for n in names}
    assert set(spec.SHIP_ASSETS) == {f"sound/{spec.MOD_ID}_{n}.ogg" for n in names}
    # Loop flags match the cue table's stop-clock convention.
    for cue in manifest["cues"]:
        stop = dict((name, stop) for name, stop, _v in spec.AUDIO_CUE_TABLE)[cue["name"]]
        assert cue["loop"] == (stop is None), cue["name"]
        if stop is not None:
            assert stop < cue["seconds"], (
                f"{cue['name']}: stop clock {stop} outlives the {cue['seconds']} s clip"
            )


def test_decoded_pcm_is_reproducible(spec, manifest):
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    for cue in manifest["cues"]:
        path = SOUND / f"{spec.MOD_ID}_{cue['name']}.ogg"
        decoded, rate = sf.read(path, dtype="float64")
        assert rate == manifest["samplerate"]
        quantised = np.round(np.asarray(decoded) * 32767.0).astype("int16")
        digest = hashlib.sha256(quantised.tobytes()).hexdigest()
        assert digest == cue["pcm_sha256"], (
            f"{cue['name']}: shipped PCM differs from the manifest - the file "
            "was regenerated without re-recording, or corrupted"
        )


def test_loops_are_seamless(manifest):
    for cue in manifest["cues"]:
        if not cue["loop"]:
            continue
        assert cue["loop_wrap_ratio"] < 3.0, (
            f"{cue['name']} steps at its own wrap: {cue['loop_wrap_ratio']}"
        )


def test_the_emitter_node_exists_in_the_cage(spec):
    """The 3D sources bind to AUDIO_EMITTER_NODE_NAME by GE-side name
    resolution; a renamed bead ring would leave every cue silently unmade
    (createSFXSource against a guessed cid is the failure that survives
    every spec-file gate - spin_launch's lesson, ported with the pipeline).
    """

    import json

    handoff = json.loads(
        (EXAMPLE_ROOT / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(encoding="utf-8")
    )
    names = {node["id"] for node in handoff["nodes"]}
    assert spec.AUDIO_EMITTER_NODE_NAME in names
    # And the runtime chunk carries the SAME name, interpolated - two copies
    # of one node name in one file is how the dead one goes stale.
    assert spec.AUDIO_EMITTER_NODE_NAME in spec.LUA_BEHAVIOR
    assert "@AUDIO_EMITTER_NODE@" not in spec.LUA_BEHAVIOR


def test_shipped_zip_carries_the_cues(spec, manifest):
    import zipfile

    dist = EXAMPLE_ROOT / "dist" / spec.ZIP_BASENAME
    if not dist.is_file():
        pytest.skip("no dist zip")
    with zipfile.ZipFile(dist) as archive:
        names = set(archive.namelist())
    for cue in manifest["cues"]:
        member = f"vehicles/{spec.MOD_ID}/sound/{spec.MOD_ID}_{cue['name']}.ogg"
        assert member in names, f"cue not shipped: {member}"

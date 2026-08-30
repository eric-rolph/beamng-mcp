"""D3 gate: the census reducer, and the wire contract it reduces.

WHY THIS FILE EXISTS. The census shipped as two event keys - ``census_class``
and ``census_counted`` - kept apart by a comment. A repo-wide grep for either
key returned spec.py and the runtime it generates and nothing else: no consumer
existed, so "the two keys are never averaged" was a property of prose, not of
software. This file is the consumer's gate, and it tests the property in the
two places it can break:

  * IN THE REDUCER - the arithmetic. `sensor_unknown` must never reach a class
    tally and must never reach the denominator of a fault rate.
  * ON THE WIRE - the generated runtime. A second emitter of ``census_class``
    is what made a naive reducer double-count conceded plays; the runtime is
    read here to prove there is exactly one, and that it is gated.

The wire tests read the SHIPPED ``runtime.lua`` as well as a fresh
regeneration, because those are two different claims: one is about the design,
the other is about the artifact a player would actually load.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO_ROOT / "examples" / "giant_props"
MOD_KEY = "pachinko_tower"
MOD_DIR = PACK_ROOT / MOD_KEY
SHIPPED_RUNTIME = (
    MOD_DIR / "mod" / "lua" / "ge" / "extensions" / "ericrolph_pachinko_tower" / "runtime.lua"
)


def _load(name: str, path: Path):
    loader = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(loader)
    # Registered before exec: @dataclass resolves its annotations through
    # sys.modules[cls.__module__], so a module loaded by path and never
    # registered blows up on the first dataclass it defines.
    sys.modules[name] = module
    loader.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reduce_mod():
    return _load("pachinko_census_reduce", MOD_DIR / "authoring" / "census_reduce.py")


@pytest.fixture(scope="module")
def spec():
    return _load("pachinko_spec_reduce", MOD_DIR / "spec.py")


def scored(**overrides):
    """A well-formed census line, as payout emits it."""

    record = {
        "event": "pachinko_scored",
        "session": 1,
        "subject_id": 7,
        "plays": overrides.pop("play", 1),
        "census_class": "clean",
        "census_counted": True,
        "census_source": "outcome",
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------
# The duplication guard. census_reduce.py restates the class lists so it can
# run with no spec.py on the path; that is only safe if drift is a test failure.
# --------------------------------------------------------------------------
def test_the_reducers_class_lists_match_the_spec(reduce_mod, spec):
    assert list(reduce_mod.CENSUS_CLASSES) == list(spec.CENSUS_CLASSES)
    assert list(reduce_mod.CENSUS_FAULT_CLASSES) == list(spec.CENSUS_FAULT_CLASSES)
    assert reduce_mod.CENSUS_SENSOR_UNKNOWN == spec.CENSUS_SENSOR_UNKNOWN
    assert reduce_mod.CENSUS_SENSOR_UNKNOWN not in reduce_mod.CENSUS_CLASSES


# --------------------------------------------------------------------------
# THE ARITHMETIC. The two keys, kept apart.
# --------------------------------------------------------------------------
def test_a_dropped_play_is_not_a_class_and_not_in_the_denominator(reduce_mod):
    """The whole metric in one assertion.

    Three plays: one clean, one throat_jam, one the sensor could not read. The
    fault rate is 1/2, not 1/3, and `sensor_unknown` appears in no class tally.
    """

    census = reduce_mod.reduce_records(
        [
            scored(play=1, census_class="clean"),
            scored(play=2, census_class="throat_jam", census_source="first_rap"),
            scored(
                play=3,
                census_class="sensor_unknown",
                census_counted=False,
                census_source="at_rest",
            ),
        ]
    )
    assert census.counted == {"clean": 1, "throat_jam": 1}
    assert "sensor_unknown" not in census.counted
    assert census.dropped == 1
    assert census.total_counted == 2
    assert census.faults == 1
    assert census.fault_rate == pytest.approx(0.5)
    assert census.coverage == pytest.approx(2 / 3)


def test_nothing_counted_reports_no_rate_rather_than_zero(reduce_mod):
    """A rate of 0.0 would read as "no faults" when it means "no data"."""

    census = reduce_mod.reduce_records(
        [scored(play=1, census_class="sensor_unknown", census_counted=False)]
    )
    assert census.total_counted == 0
    assert census.fault_rate is None
    assert census.coverage == pytest.approx(0.0)


def test_held_and_clean_are_counted_but_are_not_faults(reduce_mod):
    census = reduce_mod.reduce_records(
        [scored(play=1, census_class="held"), scored(play=2, census_class="clean")]
    )
    assert census.total_counted == 2
    assert census.faults == 0
    assert census.fault_rate == pytest.approx(0.0)


def test_unclassified_is_a_fault(reduce_mod):
    """It is a real play the metric cannot name - a failure, not a gap."""

    census = reduce_mod.reduce_records([scored(play=1, census_class="unclassified")])
    assert census.faults == 1


def test_a_play_is_counted_once_however_many_times_the_log_is_read(reduce_mod):
    lines = [scored(play=1), scored(play=2)]
    census = reduce_mod.reduce_records(lines + lines)
    assert census.total_counted == 2
    assert census.duplicates_ignored == 2


def test_records_with_no_census_keys_are_ignored_not_errors(reduce_mod):
    census = reduce_mod.reduce_records(
        [{"event": "pachinko_peg_restore"}, {"event": "pachinko_rearmed", "plays": 3}]
    )
    assert census.records_seen == 0
    assert census.total_plays == 0


# --------------------------------------------------------------------------
# THE STRICTNESS. Each of these is a defect that has actually shipped once.
# --------------------------------------------------------------------------
def test_an_ungated_class_is_a_hard_error(reduce_mod):
    """THE pachinko_gave_up DEFECT.

    `gave_up` used to emit `census_class` with no `census_counted`, for plays
    that ALSO reach payout. A reducer over "events with a census_class" would
    have double-counted every conceded play and read one copy ungated. If the
    key comes back, the reducer stops instead of producing a number.
    """

    with pytest.raises(reduce_mod.CensusError, match="no census_counted"):
        reduce_mod.reduce_records(
            [{"event": "pachinko_gave_up", "census_class": "throat_jam", "plays": 1}]
        )


def test_a_counted_flag_with_no_class_is_a_hard_error(reduce_mod):
    with pytest.raises(reduce_mod.CensusError, match="no census_class"):
        reduce_mod.reduce_records([{"event": "pachinko_scored", "census_counted": True}])


def test_a_census_line_on_a_second_emitter_is_a_hard_error(reduce_mod):
    """Payout is the one terminal site every play passes through."""

    with pytest.raises(reduce_mod.CensusError, match="only emitter"):
        reduce_mod.reduce_records([scored(event="pachinko_gave_up")])


def test_sensor_unknown_may_not_be_counted(reduce_mod):
    with pytest.raises(reduce_mod.CensusError, match="counted as a class"):
        reduce_mod.reduce_records([scored(census_class="sensor_unknown", census_counted=True)])


def test_a_real_class_may_not_be_uncounted(reduce_mod):
    with pytest.raises(reduce_mod.CensusError, match="census_counted=false"):
        reduce_mod.reduce_records([scored(census_class="throat_jam", census_counted=False)])


def test_an_unknown_class_name_is_a_hard_error(reduce_mod):
    with pytest.raises(reduce_mod.CensusError, match="not one of the eight"):
        reduce_mod.reduce_records([scored(census_class="yakumono_hang")])


def test_a_non_boolean_counted_flag_is_a_hard_error(reduce_mod):
    with pytest.raises(reduce_mod.CensusError, match="not a boolean"):
        reduce_mod.reduce_records([scored(census_counted=1)])


# --------------------------------------------------------------------------
# The log reader.
# --------------------------------------------------------------------------
def test_parse_log_reads_the_tagged_lines_and_skips_the_rest(reduce_mod, tmp_path):
    payload = json.dumps(scored(play=4))
    text = "\n".join(
        [
            "0.12|I|GELua.something|unrelated chatter",
            f"1.00|I|GELua.x|{reduce_mod.LOG_TAG} {payload}",
            f"1.01|I|GELua.x|{reduce_mod.LOG_TAG} not json at all",
            '1.02|I|GELua.x|no tag here {"event": "pachinko_scored"}',
        ]
    )
    records = reduce_mod.parse_log(text)
    assert len(records) == 1
    assert reduce_mod.reduce_records(records).total_counted == 1


def test_the_cli_runs_end_to_end(reduce_mod, tmp_path, capsys):
    log = tmp_path / "beamng.log"
    log.write_text(
        "\n".join(
            f"1.0|I|GELua.x|{reduce_mod.LOG_TAG} {json.dumps(r)}"
            for r in (
                scored(play=1, census_class="clean"),
                scored(play=2, census_class="throat_jam"),
                scored(play=3, census_class="sensor_unknown", census_counted=False),
            )
        ),
        encoding="utf-8",
    )
    assert reduce_mod.main([str(log), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["counted"]["throat_jam"] == 1
    # The JSON histogram is keyed over the EIGHT classes only - the dropped
    # plays have their own scalar and cannot be summed in by a reader who
    # iterates the table.
    assert "sensor_unknown" not in out["counted"]
    assert out["dropped"] == 1
    assert out["fault_rate"] == pytest.approx(0.5)
    assert out["coverage"] == pytest.approx(2 / 3)


def test_the_cli_exits_nonzero_on_a_corrupt_census(reduce_mod, tmp_path, capsys):
    log = tmp_path / "beamng.log"
    bad = {"event": "pachinko_gave_up", "census_class": "throat_jam"}
    log.write_text(f"1.0|I|GELua.x|{reduce_mod.LOG_TAG} {json.dumps(bad)}", encoding="utf-8")
    assert reduce_mod.main([str(log)]) == 2
    assert "CENSUS ERROR" in capsys.readouterr().err


def test_the_formatted_table_is_ascii(reduce_mod):
    census = reduce_mod.reduce_records([scored(play=1), scored(play=2, census_class="mouth_hang")])
    reduce_mod.format_census(census).encode("ascii")


# --------------------------------------------------------------------------
# THE WIRE CONTRACT. What the runtime actually emits.
# --------------------------------------------------------------------------
def _payload_of(source: str, event: str) -> str:
    """The literal table passed to emitEvent for `event`, brace-matched."""

    marker = f'"{event}", {{'
    start = source.index(marker) + len(marker) - 1
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unbalanced emitEvent payload for {event!r}")


def _code_only(source: str) -> str:
    """Drop whole-line Lua comments.

    This matters more than it looks: the D3 fix DOCUMENTS the removed
    ``census_class = b.censusStopClass`` line in a comment, so a naive
    substring count over the raw source finds three "emitters" and two of them
    are prose. The runtime contains no ``--[[`` long comments (checked below),
    so line-based stripping is exact here.
    """

    assert "--[[" not in source, "long comments present - this stripper is now wrong"
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def shipped_runtime_source():
    return SHIPPED_RUNTIME.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def shipped_runtime_code(shipped_runtime_source):
    return _code_only(shipped_runtime_source)


def test_the_shipped_runtime_has_exactly_one_census_emitter(shipped_runtime_code):
    """One class, one gate, one place. A second emitter is a second denominator."""

    assert shipped_runtime_code.count("census_class = ") == 1
    assert shipped_runtime_code.count("census_counted = ") == 1
    assert shipped_runtime_code.count("census_source = ") == 1


def test_the_census_line_lives_in_the_payout_event(shipped_runtime_code):
    payload = _payload_of(shipped_runtime_code, "pachinko_scored")
    assert "census_class = censusClass," in payload
    assert "census_counted = censusCounted," in payload
    assert "census_source = censusSource," in payload


def test_gave_up_carries_no_census_line(shipped_runtime_code):
    """D3. It used to carry an ungated `census_class = b.censusStopClass`, and
    every conceded play emits this event AND a pachinko_scored moments later."""

    payload = _payload_of(shipped_runtime_code, "pachinko_gave_up")
    assert "census_class" not in payload
    assert "census_counted" not in payload


def test_the_in_memory_histogram_is_split_too(shipped_runtime_code):
    """`stats.census` was the only aggregation the code performed and it put
    `sensor_unknown` in with the eight classes - merging exactly what the event
    keys separate. The discriminator must be `censusCounted`, the same value
    the event carries, so the tally and the stream cannot disagree."""

    assert "b.stats.census_dropped" in shipped_runtime_code
    index = shipped_runtime_code.index("b.stats.census[censusClass]")
    window = shipped_runtime_code[index - 400 : index]
    assert "if censusCounted then" in window


@pytest.mark.xfail(
    reason=(
        "lua_kit's cleanupInstallation gained the behavior.cleanup teardown "
        "hook on 2026-08-29 (hot_potato's immortal carrier-VM tick fix), so "
        "every runtime regenerated today carries a block pachinko_tower's "
        "SHIPPED runtime predates. The shipped file is exactly what its spec "
        "generated at its lock; the framework moved underneath it - the same "
        "shape as this mod's stale-harvest xfail below. The fix is pachinko's "
        "own regeneration and re-cut round, with its own hashes and zip lock, "
        "not a quiet runtime rewrite here."
    ),
    strict=True,
)
def test_the_shipped_runtime_is_the_regenerated_runtime(spec, shipped_runtime_source):
    """The runtime is generated text, so this is a real reproducibility check
    (unlike the DAE exporter, which stamps wall-clock time and cannot be
    hashed after the fact)."""

    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from proplib import lua_kit

    handoff = json.loads(
        (MOD_DIR / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(encoding="utf-8")
    )
    regenerated = lua_kit.generate_runtime(spec.MOD_ID, spec.DISPLAY_NAME, handoff, spec)
    assert regenerated == shipped_runtime_source, (
        "the shipped runtime.lua is not what spec.py generates - a spec change "
        "landed without the runtime being rewritten"
    )

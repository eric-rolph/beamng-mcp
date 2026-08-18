"""P0.4 gate: the lifted node-cloud sensor and the eight-class census metric.

The one line in this change that can corrupt a number without ever looking
wrong is ``cloudOccupied``'s failure semantics. The function it was lifted from
- ``fieldCloudOccupied`` - **fails closed**: if ``pcall(getAllVehicles)`` fails
it returns 1, meaning "occupied". That is exactly right for its own job (a
blocked peg restore costs a second, an unblocked one costs a car with a peg
through it) and exactly wrong for a classifier: a generic box sensor that
answers "occupied" on a roster hiccup reports the car resident in the shaft AND
the throat AND the yakumono on the same frame, and whichever branch the
classifier tests first fabricates a fault class out of a sensor that knew
nothing.

So the lifted primitive returns a THIRD state - unknown - and the classifier
drops the play from the census rather than classifying it. **This file exists
to exercise that path**, not to admire it in a comment.

It runs the REAL generated ``runtime.lua`` text under lupa against stubbed
engine globals. It cannot prove physics; it proves the sensor's contract.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "pachinko_tower"


@pytest.fixture(scope="module")
def spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("pachinko_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runtime_source(spec):
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from proplib import lua_kit

    handoff_path = PACK_ROOT / MOD_KEY / "authoring" / f"{spec.MOD_ID}.handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    return lua_kit.generate_runtime(spec.MOD_ID, "Pachinko Tower", handoff, spec)


def test_generated_runtime_parses(runtime_source):
    """A syntax error here is a mod that loads as nothing at all."""
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    loader = runtime.eval("function(s) local f, e = load(s) return f, e end")
    chunk, err = loader(runtime_source)
    assert chunk is not None, f"generated runtime does not parse: {err}"


def test_top_level_local_headroom(runtime_source):
    """Lua allows 200 locals per function and the main chunk is one function.

    Recorded as a number rather than trusted: Phase 2 adds yakumono machinery
    to this same chunk, and running out of local slots is a compile failure
    with a famously unhelpful message.
    """
    top = re.findall(r"^local (?:function )?([A-Za-z_][A-Za-z0-9_]*)", runtime_source, re.M)
    assert len(top) < 190, (
        f"{len(top)} top-level locals - fewer than 10 slots left before Lua's "
        "200-per-function limit. Phase 2 needs some of them."
    )


# The sensor block is contiguous in the generated source: cloudOccupied,
# FIELD_GUARD_BOX, fieldCloudOccupied, the class map, censusClassify,
# censusLatchStop. Slice it out and run it against stubs rather than driving
# the whole state machine, so a failure names the sensor and not the game.
SENSOR_HEAD = "local function cloudOccupied(state, box, onlyId)"
SENSOR_TAIL = "  if class then b.censusStopClass = class end\nend"

STUBS = r"""
local S = {roster = nil, rosterThrows = false}

local vecmt = {}
vecmt.__index = vecmt
function vecmt.__add(a, b) return vec3(a.x + b.x, a.y + b.y, a.z + b.z) end
function vec3(x, y, z) return setmetatable({x = x, y = y, z = z}, vecmt) end

-- The prop's authored frame is the world frame in this harness, so a node's
-- world position IS its local position. That keeps the test about the BOX
-- test and the roster contract, which is what is under test.
function localOf(state, p) return p.x, p.y, p.z end

function getAllVehicles()
  if S.rosterThrows then error("roster read failed") end
  return S.roster
end

-- `mode` injects a PER-VEHICLE failure, which is the failure the roster-level
-- stubs above cannot express and which therefore had no test at all until D2.
-- Every one of these is a documented engine reality: the sensor's own comment
-- says "getNodeCount can exist while getNodePosition throws".
local function makeVehicle(id, nodes, mode)
  return {
    getId = function(self)
      if mode == "idthrow" then error("getId failed") end
      return id
    end,
    getNodeCount = function(self)
      if mode == "counthrow" then error("getNodeCount failed") end
      return #nodes
    end,
    getPosition = function(self)
      if mode == "posthrow" then error("getPosition failed") end
      return vec3(0, 0, 0)
    end,
    getNodePosition = function(self, i)
      if mode == "nodethrow" then error("getNodePosition failed") end
      return nodes[i + 1]
    end,
  }
end

-- nodes arrive as a flat "id[!mode];x,y,z|x,y,z" string so nothing has to
-- cross the Python/Lua table boundary and pick up a wrapper on the way.
function setRoster(descriptor)
  S.rosterThrows = false
  if descriptor == "throw" then S.rosterThrows = true S.roster = nil return end
  if descriptor == "nottable" then S.roster = "not a table" return end
  S.roster = {}
  for entry in string.gmatch(descriptor, "[^&]+") do
    local id, mode, rest = string.match(entry, "^(%-?%d+)!?([a-z]*);(.*)$")
    local nodes = {}
    for triple in string.gmatch(rest, "[^|]+") do
      local x, y, z = string.match(triple, "^(%-?[%d%.]+),(%-?[%d%.]+),(%-?[%d%.]+)$")
      nodes[#nodes + 1] = vec3(tonumber(x), tonumber(y), tonumber(z))
    end
    S.roster[#S.roster + 1] = makeVehicle(tonumber(id), nodes, mode)
  end
end

local STATE = {propId = 999, behavior = {}}
function makeState(subjectId)
  STATE.behavior = {subjectId = subjectId}
  return STATE
end
"""

EXPORTS = r"""
return {
  cloudOccupied = function(state, boxName, onlyId)
    return cloudOccupied(state, B.census_boxes[boxName], onlyId)
  end,
  guardBox = function(state, onlyId) return cloudOccupied(state, FIELD_GUARD_BOX, onlyId) end,
  fieldCloudOccupied = fieldCloudOccupied,
  censusClassify = censusClassify,
  censusLatchStop = censusLatchStop,
  setRoster = setRoster,
  makeState = makeState,
  latched = function(state) return state.behavior.censusStopClass end,
  didRead = function(state) return state.behavior.censusRead and true or false end,
}
"""


def roster(*vehicles: tuple[int, list[tuple[float, float, float]]]) -> str:
    return "&".join(
        f"{vid};" + "|".join(f"{x},{y},{z}" for x, y, z in nodes) for vid, nodes in vehicles
    )


# D2: the same roster, with ONE vehicle's engine API rigged to throw. `mode` is
# the call that fails - the sensor pcalls the whole per-vehicle block, so any
# of these lands in the same branch that used to be swallowed.
NODE_FAILURE_MODES = ["nodethrow", "counthrow", "posthrow", "idthrow"]
IN_BOX = (0.0, 0.0, 20.0)


def broken(vid: int, mode: str, nodes: list[tuple[float, float, float]] | None = None) -> str:
    nodes = nodes if nodes is not None else [IN_BOX]
    return f"{vid}!{mode};" + "|".join(f"{x},{y},{z}" for x, y, z in nodes)


@pytest.fixture(scope="module")
def sensor(spec, runtime_source):
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from proplib import lua_kit

    head = runtime_source.index(SENSOR_HEAD)
    tail = runtime_source.index(SENSOR_TAIL, head) + len(SENSOR_TAIL)
    block = runtime_source[head:tail]
    assert "cloudOccupied" in block and "censusLatchStop" in block

    # B is built from the spec's own BEHAVIOR through the SAME serializer the
    # runtime uses, so the boxes under test are the boxes that ship.
    behavior = spec.BEHAVIOR
    wanted = (
        "field_hw",
        "depth_half",
        "peg_guard_z_lo",
        "peg_guard_z_hi",
        "census_boxes",
        "census_box_order",
    )
    b_lua = lua_kit.lua_value({key: behavior[key] for key in wanted})
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    return runtime.execute(STUBS + f"\nlocal B = {b_lua}\n" + block + EXPORTS)


# --------------------------------------------------------------------------
# The box test itself.
# --------------------------------------------------------------------------
def test_cloud_occupied_sees_a_node_in_the_box(sensor):
    sensor.setRoster(roster((1, [(0.0, 0.0, 20.0)])))
    assert sensor.cloudOccupied(sensor.makeState(1), "field") == (1, False)


def test_cloud_occupied_misses_a_node_outside_the_box(sensor):
    sensor.setRoster(roster((1, [(0.0, 0.0, 100.0)])))
    assert sensor.cloudOccupied(sensor.makeState(1), "field") == (0, False)


def test_cloud_occupied_ignores_the_prop_itself(sensor):
    sensor.setRoster(roster((999, [(0.0, 0.0, 20.0)])))
    assert sensor.cloudOccupied(sensor.makeState(1), "field") == (0, False)


def test_only_id_narrows_the_scan_not_the_roster(sensor):
    sensor.setRoster(roster((1, [(0.0, 0.0, 20.0)]), (2, [(1.0, 0.0, 20.0)])))
    state = sensor.makeState(1)
    assert sensor.cloudOccupied(state, "field") == (2, False)
    assert sensor.cloudOccupied(state, "field", 2) == (1, False)


# --------------------------------------------------------------------------
# THE PATH THIS FILE EXISTS FOR.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("failure", ["throw", "nottable"])
def test_unknown_is_reported_as_unknown_and_not_as_occupied(sensor, failure):
    """A roster that cannot be read must report UNKNOWN, never OCCUPIED.

    If this ever returns (1, False) again, every box in the classifier answers
    "the car is here" on the same frame and the census reports a fault class
    invented by a sensor failure.
    """
    sensor.setRoster(failure)
    hits, unknown = sensor.cloudOccupied(sensor.makeState(1), "field")
    assert unknown is True, "the sensor swallowed a roster failure"
    assert hits == 0, "an unreadable roster must not also report occupancy"


@pytest.mark.parametrize("failure", ["throw", "nottable"])
def test_the_peg_guard_still_fails_closed(sensor, failure):
    """The ONE fail-closed caller keeps its semantics, at its own call site.

    The lift must not make the peg restore optimistic: an unblocked restore
    costs a car with a peg through it.
    """
    sensor.setRoster(failure)
    assert sensor.fieldCloudOccupied(sensor.makeState(1)) == 1


def test_the_peg_guard_still_sees_a_car_in_the_field(sensor):
    """...and it is still a real sensor when the roster IS readable."""
    sensor.setRoster(roster((1, [(0.0, 0.0, 20.0)])))
    assert sensor.fieldCloudOccupied(sensor.makeState(1)) == 1
    sensor.setRoster(roster((1, [(0.0, 0.0, 100.0)])))
    assert sensor.fieldCloudOccupied(sensor.makeState(1)) == 0


@pytest.mark.parametrize("failure", ["throw", "nottable"])
def test_classifier_returns_unknown_rather_than_a_class(sensor, failure):
    sensor.setRoster(failure)
    assert sensor.censusClassify(sensor.makeState(1)) == "sensor_unknown"


@pytest.mark.parametrize("failure", ["throw", "nottable"])
def test_the_latch_stays_empty_on_an_unknown_read(sensor, failure):
    """An unknown read must leave the play unlatched AND unmarked-as-read.

    ``b.censusRead`` is what decides, at payout, between `unclassified` (a
    fault, in the denominator) and `sensor_unknown` (dropped). A latch that
    recorded a failed read as a read would push every sensor failure into the
    fault count.
    """
    sensor.setRoster(failure)
    state = sensor.makeState(1)
    sensor.censusLatchStop(state)
    assert sensor.latched(state) is None
    assert sensor.didRead(state) is False


def test_a_clean_read_with_the_car_nowhere_is_knowledge_not_ignorance(sensor):
    """Read cleanly, resident in no box -> nil, and the latch records the read.

    nil becomes `unclassified`, which is a FAULT by construction. That is the
    opposite of `sensor_unknown`, which is not a class at all, and the two
    must never collapse into one another.
    """
    sensor.setRoster(roster((1, [(0.0, 0.0, -50.0)])))
    state = sensor.makeState(1)
    assert sensor.censusClassify(state) is None
    sensor.censusLatchStop(state)
    assert sensor.latched(state) is None
    assert sensor.didRead(state) is True


def test_the_latch_retries_after_a_failed_read(sensor):
    """A recoverable hiccup must cost nothing: only an all-failed play drops."""
    state = sensor.makeState(1)
    sensor.setRoster("throw")
    sensor.censusLatchStop(state)
    assert sensor.didRead(state) is False
    sensor.setRoster(roster((1, [(0.0, 0.0, 20.0)])))
    sensor.censusLatchStop(state)
    assert sensor.latched(state) == "field_hang"


def test_the_latch_does_not_move_once_set(sensor):
    """The class is where the car FIRST stopped, not where 43 raps left it."""
    state = sensor.makeState(1)
    sensor.setRoster(roster((1, [(0.0, 0.0, 20.0)])))
    sensor.censusLatchStop(state)
    assert sensor.latched(state) == "field_hang"
    sensor.setRoster(roster((1, [(9.53, 0.0, 43.18)])))
    sensor.censusLatchStop(state)
    assert sensor.latched(state) == "field_hang"


# --------------------------------------------------------------------------
# D2 (2026-08-18). THE NODE PATH - the half of the tri-state that shipped
# broken and untested.
#
# Every test above injects its failure at ``getAllVehicles``, i.e. at the
# ROSTER. The sensor's per-vehicle block is wrapped in its own ``pcall`` whose
# return was DISCARDED, so a vehicle that could not be read came out of the
# loop as "read, and not in the box": ``hits`` unchanged, ``unknown`` false.
# The tri-state's safety property therefore held for the roster and not for
# the node path, in BOTH callers, and both failures are the ones the design
# says the tri-state exists to prevent:
#
#   * the peg guard restored the lattice into a car it could not read
#   * the classifier booked `unclassified` - a FAULT, IN THE DENOMINATOR -
#     from a sensor that knew nothing
#
# These tests fail against the pre-D2 sensor and pass after it. They are
# parametrized over every call in the per-vehicle block that can throw,
# because the fix is "capture the pcall", not "special-case getNodePosition".
# --------------------------------------------------------------------------
@pytest.mark.parametrize("mode", NODE_FAILURE_MODES)
def test_a_node_level_failure_is_unknown_not_empty(sensor, mode):
    """The sensor's own comment named this mode as real and then swallowed it."""

    sensor.setRoster(broken(1, mode))
    hits, unknown = sensor.cloudOccupied(sensor.makeState(1), "field")
    assert unknown is True, (
        f"a vehicle whose {mode} throws was counted as READ AND ABSENT - the "
        "per-vehicle pcall return is being discarded again"
    )
    assert hits == 0


@pytest.mark.parametrize("mode", NODE_FAILURE_MODES)
def test_the_peg_guard_fails_closed_on_a_node_level_failure(sensor, mode):
    """THE ONE THAT COSTS STEEL.

    A blocked restore costs a second; an unblocked one drives pegs through a
    car. Pre-D2 this returned 0 and the pegs went back in.
    """

    sensor.setRoster(broken(1, mode))
    assert sensor.fieldCloudOccupied(sensor.makeState(1)) == 1, (
        "the peg guard restored the lattice into a car the sensor could not "
        "read - the precise cost the fail-closed rule exists to prevent"
    )


@pytest.mark.parametrize("mode", NODE_FAILURE_MODES)
def test_the_classifier_drops_the_play_on_a_node_level_failure(sensor, mode):
    """THE ONE THAT CORRUPTS THE NUMBER.

    Pre-D2 every box answered (0, false), the classifier fell through to nil,
    and payout booked `unclassified` - a fault, in the denominator, fabricated
    by a sensor outage. That is verbatim the failure P0.4 exists to eliminate.
    """

    sensor.setRoster(broken(1, mode))
    assert sensor.censusClassify(sensor.makeState(1)) == "sensor_unknown"


@pytest.mark.parametrize("mode", NODE_FAILURE_MODES)
def test_the_latch_stays_empty_on_a_node_level_failure(sensor, mode):
    """...and the play is not marked as read, so a total outage drops it."""

    sensor.setRoster(broken(1, mode))
    state = sensor.makeState(1)
    sensor.censusLatchStop(state)
    assert sensor.latched(state) is None
    assert sensor.didRead(state) is False


def test_hits_counted_before_the_failure_survive_the_unknown(sensor):
    """`hits` is returned, not zeroed: what was counted is real.

    The flag carries the ignorance; the count carries the knowledge. A caller
    that wants to fail closed does it on the flag - which is why the guard is
    tested separately above rather than inferred from the count.
    """

    sensor.setRoster(roster((1, [IN_BOX])) + "&" + broken(2, "nodethrow"))
    hits, unknown = sensor.cloudOccupied(sensor.makeState(1), "field")
    assert (hits, unknown) == (1, True)


def test_a_broken_bystander_does_not_poison_a_narrowed_read(sensor):
    """The census asks about ONE car and must not be spoiled by another's fault.

    The id checks run before any node call, so a vehicle that is neither the
    machine nor the subject returns from the closure normally. Without this,
    any wrecked car anywhere on the map would drop every play in the session.
    """

    sensor.setRoster(roster((1, [IN_BOX])) + "&" + broken(2, "nodethrow"))
    assert sensor.cloudOccupied(sensor.makeState(1), "field", 1) == (1, False)


def test_an_unidentifiable_bystander_does_poison_a_narrowed_read(sensor):
    """...but a vehicle whose getId() throws MIGHT be the subject.

    The narrowing is by id, so ignorance of the id is ignorance about the
    subject. This is the case that keeps the previous test from being a hole.
    """

    sensor.setRoster(roster((1, [IN_BOX])) + "&" + broken(2, "idthrow"))
    # The subject IS found - hits is 1 - and the answer is still unknown,
    # because an unreadable id could have been a second copy of the subject.
    assert sensor.cloudOccupied(sensor.makeState(1), "field", 1) == (1, True)


def test_a_healthy_roster_is_still_read_cleanly(sensor):
    """The control: the failure injection must not itself make everything unknown."""

    sensor.setRoster(roster((1, [IN_BOX]), (2, [(1.0, 0.0, 20.0)])))
    assert sensor.cloudOccupied(sensor.makeState(1), "field") == (2, False)
    assert sensor.censusClassify(sensor.makeState(1)) == "field_hang"


# --------------------------------------------------------------------------
# The sheared box: the correction that keeps a peg drape out of `throat_jam`.
# --------------------------------------------------------------------------
def test_the_build36_jam_lands_in_the_throat(sensor):
    """spec.py's own live datum: build 36 play 9, car at rest z 43.18.

    The chute surface at x 9.53 is z 41.42 and the car came to rest 1.55 m
    higher than a car resting on the slab. If the throat sensor cannot see the
    one measured throat jam on the record, it cannot measure the class P0.6
    exists to remove.
    """
    sensor.setRoster(roster((1, [(9.53, 0.0, 43.18)])))
    assert sensor.censusClassify(sensor.makeState(1)) == "throat_jam"


def test_a_top_row_peg_drape_is_not_a_throat_jam(spec, sensor):
    """The reason the box is sheared.

    An axis-aligned box over the throat necessarily swallows the top peg row,
    because the throat's floor at x 6.00 is lower than the row's crest at
    x 11.40. A car draped on row 0 would then be reported as a throat jam - a
    fabricated fault class, in the exact place P0.6's effect is measured.
    """
    crest = spec.PEG_TOP_Z + spec.PEG_CROWN_MAX
    sensor.setRoster(roster((1, [(11.40, 0.0, crest + 0.3)])))
    assert sensor.censusClassify(sensor.makeState(1)) == "field_hang"


def test_class_order_puts_the_throat_before_the_field(spec, sensor):
    """A node in both boxes is a throat jam, not a field hang.

    The throat is not in the field - that is the whole reason `throat_jam` is
    a separate class, and it is why the order is data in BEHAVIOR rather than
    control flow in Lua.
    """
    order = list(spec.BEHAVIOR["census_box_order"])
    assert order.index("throat") < order.index("field")
    sensor.setRoster(roster((1, [(12.0, 0.0, 45.0)])))
    assert sensor.censusClassify(sensor.makeState(1)) == "throat_jam"


@pytest.mark.parametrize("rest_z", [3.17, 4.00, 4.73])
def test_a_mouth_straddle_is_a_mouth_hang(sensor, rest_z):
    """The serial-78 signature: five concessions at rest_z 3.17 to 4.73."""
    sensor.setRoster(roster((1, [(-9.6, -1.0, rest_z)])))
    assert sensor.censusClassify(sensor.makeState(1)) == "mouth_hang"


# --------------------------------------------------------------------------
# The class set itself.
# --------------------------------------------------------------------------
def test_class_set_is_eight_and_exhaustive(spec):
    assert len(spec.CENSUS_CLASSES) == 8
    assert set(spec.CENSUS_FAULT_CLASSES) == set(spec.CENSUS_CLASSES) - {"held", "clean"}
    assert "unclassified" in spec.CENSUS_FAULT_CLASSES, (
        "a car in a state the metric cannot name is a failure, not a gap"
    )
    assert spec.CENSUS_SENSOR_UNKNOWN not in spec.CENSUS_CLASSES


def test_every_ordered_box_name_maps_to_a_class(spec, runtime_source):
    """No box may exist that names no class, and no class may be unreachable
    except the three whose geometry Phase 2 builds."""
    mapping = runtime_source.split("local CENSUS_BOX_CLASS = {")[1].split("}")[0]
    for name in spec.BEHAVIOR["census_box_order"]:
        assert f"{name} =" in mapping, f"box {name!r} names no census class"
    named = {
        line.split("=")[1].strip().strip('",')
        for line in mapping.strip().splitlines()
        if "=" in line
    }
    assert named <= set(spec.CENSUS_CLASSES)
    unreachable = set(spec.CENSUS_CLASSES) - named - {"clean", "unclassified"}
    assert unreachable == set(), f"classes no box can produce: {unreachable}"


def test_exactly_three_classes_await_phase_two_geometry(spec):
    built = set(spec.BEHAVIOR["census_boxes"])
    unbuilt = [n for n in spec.BEHAVIOR["census_box_order"] if n not in built]
    assert unbuilt == ["yakumono_held", "yakumono", "shaft"]

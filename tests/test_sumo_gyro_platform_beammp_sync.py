"""Static and headless gates for the Sumo Gyro Platform BeamMP boundary.

The live match physics still needs BeamNG, but these tests pin the pieces that
make a two-client match safe: one exact protocol, canonical vehicle ids,
pending/follower simulation gates, owner-only vehicle mutation, complete
snapshots, and the root BeamMP adapter shipped by the prop build.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = ROOT / "examples" / "giant_props" / "sumo_gyro_platform"
ASSETS = MOD_ROOT / "assets" / "beammp"
CLIENT_DEST = MOD_ROOT / "mod" / "lua" / "ge" / "extensions" / "ericrolphSumoBeamMP.lua"
LOADER_DEST = MOD_ROOT / "mod" / "scripts" / "ericrolph_sumo_gyro_platform" / "modScript.lua"
RUNTIME_DEST = (
    MOD_ROOT / "mod" / "lua" / "ge" / "extensions" / "ericrolph_sumo_gyro_platform" / "runtime.lua"
)


def load_spec():
    spec_path = MOD_ROOT / "spec.py"
    loader_spec = importlib.util.spec_from_file_location("sumo_sync_spec", spec_path)
    module = importlib.util.module_from_spec(loader_spec)
    assert loader_spec.loader is not None
    loader_spec.loader.exec_module(module)
    return module


def test_root_assets_are_declared_and_stage_byte_for_byte():
    spec = load_spec()
    expected = {
        ("beammp/modScript.lua", "scripts/ericrolph_sumo_gyro_platform/modScript.lua"),
        ("beammp/client.lua", "lua/ge/extensions/ericrolphSumoBeamMP.lua"),
    }
    assert set(spec.SHIP_ROOT_ASSETS) == expected
    for source_rel, destination_rel in expected:
        source = MOD_ROOT / "assets" / source_rel
        destination = MOD_ROOT / "mod" / destination_rel
        assert source.is_file()
        assert destination.is_file()
        assert destination.read_bytes() == source.read_bytes()


def test_runtime_pins_protocol_authority_and_full_snapshot_contract():
    behavior = load_spec().LUA_BEHAVIOR

    # The wire identity and envelope are deliberately shared with Hot Potato.
    assert 'local NET_C2S = "ericrolph_games_c2s_v1"' in behavior
    for field in ("v", "game", "arena", "kind", "epoch", "seq", "revision", "body"):
        assert f"{field} =" in behavior
    assert 'local NET_GAME = "sumo"' in behavior
    assert "extensions.MPCoreNetwork" in behavior
    assert "getServerVehicleID" in behavior
    assert "getGameVehicleID" in behavior
    assert "localOwnsVehicle(state.propId)" in behavior

    # No BeamMP client simulates before the relay elects a role. Followers
    # leave before the original sweep/phase/integration/scoring path.
    update = behavior[behavior.index("behavior.update = function") :]
    follower_gate = update.index('networkMode(state) == "pending"')
    authority_sweep = update.index("sweepDeck(state, dt)")
    assert follower_gate < authority_sweep
    assert "networkFollowerUpdate(state, dt)\n    return" in update[:authority_sweep]
    assert 'net.mode ~= "authority"' in behavior
    assert "local NET_SNAPSHOT_SECONDS = 0.20" in behavior
    assert 'networkSend(state, "state", {state = networkSnapshot(state)})' in behavior

    # These are the minimum complete machine state needed to reproduce the
    # board, phase machine, committed collision pose, and drive animation.
    snapshot = behavior[
        behavior.index("local function networkSnapshot") : behavior.index(
            "local function networkApplySlot"
        )
    ]
    for field in (
        "phase",
        "phaseT",
        "slotE",
        "slotW",
        "scoreE",
        "scoreW",
        "resultE",
        "resultW",
        "setDone",
        "psiX",
        "psiY",
        "velX",
        "velY",
        "comX",
        "comY",
        "omega",
        "spinAngle",
        "driveAngle",
        "stageT",
        "roundT",
        "clearT",
        "decidedT",
        "relevelT",
        "cdStopT",
        "ringLive",
        "ringKo",
    ):
        assert f"{field} =" in snapshot

    # Local ids never cross the wire; mutations are limited to vehicles this
    # client owns, including follower spin and the post-round teleport.
    slot_snapshot = behavior[
        behavior.index("local function networkSlotSnapshot") : behavior.index(
            "local function networkSnapshot"
        )
    ]
    assert "id =" not in slot_snapshot
    assert "lastId =" not in slot_snapshot
    assert "canonical =" in slot_snapshot
    assert "networkCanMutateVehicle(state, vehicleId)" in behavior
    assert "vehicle and localOwnsVehicle(slot.id)" in behavior


def test_follower_reloads_collision_only_when_committed_pose_changes():
    behavior = load_spec().LUA_BEHAVIOR
    apply_snapshot = behavior[
        behavior.index("local function networkApplySnapshot") : behavior.index(
            "local function networkPublish"
        )
    ]
    assert "previousComX, previousComY" in apply_snapshot
    assert "math.abs(b.comX - previousComX) > 1e-9" in apply_snapshot
    assert "math.abs(b.comY - previousComY) > 1e-9" in apply_snapshot
    assert apply_snapshot.count("requestCollisionReload(state)") == 1
    assert apply_snapshot.index("poseAll(state, 0)") < apply_snapshot.index(
        "requestCollisionReload(state)"
    )


def test_relay_closed_and_reject_barriers_return_to_pending_before_filters():
    behavior = load_spec().LUA_BEHAVIOR
    receive = behavior[
        behavior.index("local function networkReceive") : behavior.index(
            "local function networkPostJoin"
        )
    ]
    barrier = receive.index('envelope.kind == "closed"')
    ordinary_filter = receive.index("networkAcceptEnvelope(state, envelope)")
    assert barrier < ordinary_filter
    assert "networkAwaitRelay(state, envelope)" in receive[barrier:ordinary_filter]

    await_relay = behavior[
        behavior.index("local function networkAwaitRelay") : behavior.index(
            "local function networkReceive"
        )
    ]
    assert 'net.mode = "pending"' in await_relay
    assert "net.inSeq = -1" in await_relay
    assert "net.inRevision = -1" in await_relay
    assert "net.helloT = NET_HELLO_SECONDS" in await_relay
    assert "b.omega = 0" in await_relay
    assert "b.ringLive, b.ringKo = false, false" in await_relay


def test_adapter_registers_exact_s2c_event_and_forwards_lifecycle():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        r"""
        TEST = {calls = {}, removed = {}}
        extensions = {
          ericrolph__sumo__gyro__platform_runtime = {
            onEricrolphSumoBeamMPMessage = function(payload)
              TEST.calls[#TEST.calls + 1] = {kind = "message", value = payload}
            end,
            onEricrolphSumoBeamMPPostJoin = function()
              TEST.calls[#TEST.calls + 1] = {kind = "join"}
            end,
            onEricrolphSumoBeamMPServerLeave = function()
              TEST.calls[#TEST.calls + 1] = {kind = "leave"}
            end,
          },
        }
        function AddEventHandler(eventName, callback, handlerName)
          TEST.eventName, TEST.callback, TEST.handlerName = eventName, callback, handlerName
        end
        function RemoveEventHandler(eventName, handlerName)
          TEST.removed = {eventName = eventName, handlerName = handlerName}
        end
        function setExtensionUnloadMode(module, mode) TEST.unloadMode = mode end
        function log() end
        """
    )
    module = lua.execute((ASSETS / "client.lua").read_text(encoding="utf-8"))
    module["onInit"]()
    test = lua.globals().TEST
    assert test["eventName"] == "ericrolph_games_s2c_v1"
    assert test["handlerName"] == "ericrolph_sumo_gyro_platform_beammp"
    assert test["unloadMode"] == "manual"

    test["callback"]("wire-packet")
    module["onBeamMPPostJoin"]()
    module["onBeamMPServerLeave"]()
    assert [(test["calls"][i]["kind"], test["calls"][i]["value"]) for i in range(1, 4)] == [
        ("message", "wire-packet"),
        ("join", None),
        ("leave", None),
    ]

    module["onExtensionUnloaded"]()
    assert test["removed"]["eventName"] == "ericrolph_games_s2c_v1"
    assert test["removed"]["handlerName"] == "ericrolph_sumo_gyro_platform_beammp"


def test_modscript_loads_adapter_once():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        r"""
        TEST = {loaded = false, calls = 0}
        extensions = {}
        function extensions.isExtensionLoaded(name)
          return TEST.loaded
        end
        function extensions.load(name)
          TEST.loaded = true
          TEST.calls = TEST.calls + 1
          TEST.name = name
        end
        """
    )
    source = (ASSETS / "modScript.lua").read_text(encoding="utf-8")
    assert lua.execute(source) is True
    assert lua.execute(source) is True
    test = lua.globals().TEST
    assert test["calls"] == 1
    assert test["name"] == "ericrolphSumoBeamMP"


def test_generated_runtime_contains_adapter_hooks():
    runtime = RUNTIME_DEST.read_text(encoding="utf-8")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    compiled = lua.eval(
        "function(source, name) local chunk, err = load(source, name); return chunk, err end"
    )(runtime, "@sumo-runtime.lua")
    chunk = compiled[0] if isinstance(compiled, tuple) else compiled
    assert chunk is not None, compiled
    for hook in (
        "onEricrolphSumoBeamMPMessage",
        "onEricrolphSumoBeamMPPostJoin",
        "onEricrolphSumoBeamMPServerLeave",
    ):
        assert hook in runtime
    assert CLIENT_DEST.is_file()
    assert LOADER_DEST.is_file()

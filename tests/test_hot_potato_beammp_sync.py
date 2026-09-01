"""Focused contract gates for Hot Potato's optional BeamMP synchronization.

These tests leave the existing single-client state-machine suite untouched.
They exercise both halves of the Client resource: the transport adapter's
wire envelope and the real generated gameplay runtime's authority/follower
mode switch.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parents[1]
HOT_ROOT = REPO_ROOT / "examples" / "giant_props" / "hot_potato"
ADAPTER_PATH = HOT_ROOT / "assets" / "beammp" / "client.lua"
MODSCRIPT_PATH = HOT_ROOT / "assets" / "beammp" / "modScript.lua"
RUNTIME_PATH = (
    HOT_ROOT / "mod" / "lua" / "ge" / "extensions" / "ericrolph_hot_potato" / "runtime.lua"
)


def _load_python(path: Path, name: str):
    module_spec = importlib.util.spec_from_file_location(name, path)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _lua_table(lua, value):
    if isinstance(value, dict):
        return lua.table_from({key: _lua_table(lua, item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return lua.table_from([_lua_table(lua, item) for item in value])
    return value


def _tick(state, module, seconds=0.05, steps=1):
    for _ in range(steps):
        state.clockMs = state.clockMs + seconds * 1000.0
        module.onPreRender(seconds, seconds, seconds)
    failures = [
        entry.message
        for entry in state.events.values()
        if entry.level == "E" and "behavior_update_failed" in str(entry.message)
    ]
    assert not failures, f"BeamMP behavior update failed: {failures[:2]}"


def test_client_resource_is_staged_at_beammp_paths():
    spec = _load_python(HOT_ROOT / "spec.py", "hot_potato_beammp_spec")
    root_assets = dict(spec.SHIP_ROOT_ASSETS)

    assert root_assets["beammp/modScript.lua"] == ("scripts/ericrolph_hot_potato/modScript.lua")
    assert root_assets["beammp/client.lua"] == ("lua/ge/extensions/ericrolphHotPotatoBeamMP.lua")
    assert (
        HOT_ROOT / "mod" / root_assets["beammp/modScript.lua"]
    ).read_bytes() == MODSCRIPT_PATH.read_bytes()
    assert (
        HOT_ROOT / "mod" / root_assets["beammp/client.lua"]
    ).read_bytes() == ADAPTER_PATH.read_bytes()

    adapter = ADAPTER_PATH.read_text(encoding="utf-8")
    assert '"ericrolph_games_c2s_v1"' in adapter
    assert '"ericrolph_games_s2c_v1"' in adapter
    assert 'local GAME = "hot_potato"' in adapter
    assert "MPCoreNetwork" in adapter
    assert "MPVehicleGE" in adapter
    assert 'send(record, "state", snapshot)' in adapter

    modscript = MODSCRIPT_PATH.read_text(encoding="utf-8")
    assert 'extensions.load("ericrolphHotPotatoBeamMP")' not in modscript
    assert "extensions.load(EXTENSION_NAME)" in modscript
    assert "hot_potato_runtime" not in modscript


def test_transport_emits_v1_envelopes_and_accepts_zero_revision_close():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    harness = lua.execute(
        r"""
local T = {
  mp = true,
  encoded = {},
  sent = {},
  runtimePackets = {},
  transport = {},
}
extensions = {
  MPCoreNetwork = {isMPSession = function() return T.mp end},
  MPVehicleGE = {
    getServerVehicleID = function(id) return "7-" .. tostring(id - 1) end,
    getGameVehicleID = function(sid)
      local value = tostring(sid):match("^7%-(%d+)$")
      return value and tonumber(value) + 1 or nil
    end,
    isOwn = function(id) return id == 1 end,
  },
  ericrolph__hot__potato_runtime = {
    hotPotatoBeamMPReceive = function(packet)
      T.runtimePackets[#T.runtimePackets + 1] = packet
      return true
    end,
    hotPotatoBeamMPTransport = function(info)
      T.transport[#T.transport + 1] = info
      return true
    end,
  },
}
function jsonEncode(value)
  T.encoded[#T.encoded + 1] = value
  return "encoded"
end
function jsonDecode() return nil end
function TriggerServerEvent(event, payload)
  T.sent[#T.sent + 1] = {event = event, payload = payload}
end
function AddEventHandler(event, callback, name)
  T.handlerEvent, T.handler, T.handlerName = event, callback, name
end
return T
"""
    )
    adapter = lua.execute(ADAPTER_PATH.read_text(encoding="utf-8"))
    adapter.onExtensionLoaded()
    assert harness.handlerEvent == "ericrolph_games_s2c_v1"

    assert adapter.registerProp(1) is True
    hello = harness.encoded[1]
    assert harness.sent[1].event == "ericrolph_games_c2s_v1"
    assert hello.v == 1
    assert hello.game == "hot_potato"
    assert hello.arena == "7-0"
    assert hello.kind == "hello"
    assert hello.epoch == 0
    assert hello.seq == 1
    assert hello.revision == 0
    assert hello.body.prop_sid == "7-0"
    assert hello.body.owner is True

    harness.handler(
        _lua_table(
            lua,
            {
                "v": 1,
                "game": "hot_potato",
                "arena": "7-0",
                "kind": "role",
                "epoch": 41,
                "seq": 3,
                "revision": 2,
                "body": {"role": "authority"},
            },
        )
    )
    assert harness.runtimePackets[1].kind == "role"

    # A late join receives the current role first, then an older cached state.
    # Higher S2C seq, not state revision, determines delivery order.
    harness.handler(
        _lua_table(
            lua,
            {
                "v": 1,
                "game": "hot_potato",
                "arena": "7-0",
                "kind": "state",
                "epoch": 41,
                "seq": 4,
                "revision": 1,
                "body": {"phase": "idle"},
            },
        )
    )
    assert harness.runtimePackets[2].kind == "state"

    assert adapter.publishState(1, _lua_table(lua, {"phase": "idle"})) is True
    state_envelope = harness.encoded[2]
    assert state_envelope.kind == "state"
    assert state_envelope.epoch == 41
    assert state_envelope.revision == 1
    assert state_envelope.body.phase == "idle"

    assert (
        adapter.publishCommand(
            1,
            _lua_table(lua, {"event_id": "7-0:41:1", "name": "impulse"}),
        )
        is True
    )
    assert harness.encoded[3].kind == "command"

    # Relay reset advances epoch but intentionally restarts revision at zero.
    # It must not be discarded as stale behind the earlier higher revision.
    harness.handler(
        _lua_table(
            lua,
            {
                "v": 1,
                "game": "hot_potato",
                "arena": "7-0",
                "kind": "closed",
                "epoch": 42,
                "seq": 1,
                "revision": 0,
                "body": {"reason": "relay_reset"},
            },
        )
    )
    assert harness.runtimePackets[3].kind == "closed"
    adapter.onUpdate(2.1)
    retry = harness.encoded[4]
    assert retry.kind == "hello"
    assert retry.epoch == 42
    assert retry.revision == 0


def test_runtime_fails_closed_then_follows_or_authorizes_prop_owner():
    logic = _load_python(
        REPO_ROOT / "tests" / "test_hot_potato_logic.py",
        "hot_potato_logic_for_beammp",
    )
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(logic.STUBS)
    lua.globals().HOT_MP_HARNESS = state
    lua.execute(
        r"""
local H = HOT_MP_HARNESS
H.mp = true
H.owned = {[1] = true, [2] = true, [3] = false}
H.netRegistered = {}
H.netUnregistered = {}
H.netStates = {}
H.netCommands = {}
extensions = {
  MPCoreNetwork = {isMPSession = function() return H.mp end},
  MPVehicleGE = {
    getServerVehicleID = function(id) return "7-" .. tostring(id - 1) end,
    getGameVehicleID = function(sid)
      local value = tostring(sid):match("^7%-(%d+)$")
      return value and tonumber(value) + 1 or nil
    end,
    isOwn = function(id) return H.owned[id] == true end,
  },
  ericrolphHotPotatoBeamMP = {
    registerProp = function(id)
      H.netRegistered[#H.netRegistered + 1] = id
      return true
    end,
    unregisterProp = function(id)
      H.netUnregistered[#H.netUnregistered + 1] = id
      return true
    end,
    publishState = function(id, snapshot)
      H.netStates[#H.netStates + 1] = {id = id, snapshot = snapshot}
      return true
    end,
    publishCommand = function(id, command)
      H.netCommands[#H.netCommands + 1] = {id = id, command = command}
      return true
    end,
  },
}
"""
    )
    module = lua.execute(RUNTIME_PATH.read_text(encoding="utf-8"))

    state.addVehicle(1, "ericrolph_hot_potato", 0, 0, 0, 15, 2, 15.6)
    state.addVehicle(2, "pickup", 0, 0, 0, 0.95, 2.3, 0.75)
    state.addVehicle(3, "remote", 8, 0, 0, 0.95, 2.3, 0.75)
    module.registerProp(1)
    _tick(state, module)

    stats = module.getSystemState(1).behavior_stats
    assert stats.sync_mode == "pending"
    assert stats.carrier == -1
    assert stats.options_writable is False
    assert module.hotPotatoSetOption("radius_m", 99) is False
    assert list(state.netStates.values()) == []

    follower_snapshot = {
        "phase": "live",
        "carrier_sid": "7-1",
        "fuse_remaining": 9.5,
        "held_elapsed": 1.25,
        "transfers": 2,
        "field_peak": 3,
        "out_count": 0,
        "pair_separated": True,
        "immune": {},
        "shield": {},
        "seen": {},
        "out": {},
        "quarantined": {},
        "wins": {},
        "score": {},
        "names": {"7-1": "pickup"},
        "options": {"radius_m": 42},
        "potato_at": [0, 0, 2.5],
        "cheer_remaining": 0,
    }
    assert (
        module.hotPotatoBeamMPReceive(
            _lua_table(
                lua,
                {
                    "v": 1,
                    "game": "hot_potato",
                    "arena": "7-0",
                    "kind": "role",
                    "epoch": 41,
                    "seq": 1,
                    "revision": 2,
                    "body": {"role": "follower"},
                },
            )
        )
        is True
    )
    # The relay's cached state may have an older state revision but a newer
    # outbound packet sequence than the role sent just before it.
    assert (
        module.hotPotatoBeamMPReceive(
            _lua_table(
                lua,
                {
                    "v": 1,
                    "game": "hot_potato",
                    "arena": "7-0",
                    "kind": "state",
                    "epoch": 41,
                    "seq": 2,
                    "revision": 1,
                    "body": follower_snapshot,
                },
            )
        )
        is True
    )
    _tick(state, module)
    stats = module.getSystemState(1).behavior_stats
    assert stats.sync_mode == "follower"
    assert stats.carrier == 2
    assert stats.carrier_sid == "7-1"
    assert stats.options_writable is False
    assert float(module.hotPotatoGetOptions().radius_m) == 42

    # A direct state body (rather than body.state) is also part of the relay
    # contract. The follower renders it but never runs local transfer logic.
    moved_snapshot = dict(follower_snapshot, carrier_sid="7-2", transfers=3)
    assert (
        module.hotPotatoBeamMPReceive(
            _lua_table(
                lua,
                {
                    "v": 1,
                    "game": "hot_potato",
                    "arena": "7-0",
                    "kind": "state",
                    "epoch": 41,
                    "seq": 3,
                    "revision": 2,
                    "body": moved_snapshot,
                },
            )
        )
        is True
    )
    _tick(state, module)
    assert module.getSystemState(1).behavior_stats.carrier == 3

    # Every client receives commands; only the target vehicle's owning client
    # is allowed to execute the destructive/physics mutation.
    before = len(state.velocities)
    impulse = {
        "v": 1,
        "game": "hot_potato",
        "arena": "7-0",
        "kind": "command",
        "epoch": 41,
        "seq": 4,
        "revision": 3,
        "body": {
            "event_id": "7-0:41:impulse-owned",
            "name": "impulse",
            "target_sid": "7-1",
            "delta": [1, 2, 3],
        },
    }
    assert module.hotPotatoBeamMPReceive(_lua_table(lua, impulse)) is True
    assert len(state.velocities) == before + 1
    assert state.velocities[len(state.velocities)].id == 2
    assert module.hotPotatoBeamMPReceive(_lua_table(lua, impulse)) is False
    assert len(state.velocities) == before + 1

    remote_impulse = dict(impulse, revision=4, seq=5)
    remote_impulse["body"] = dict(
        impulse["body"],
        event_id="7-0:41:impulse-remote",
        target_sid="7-2",
    )
    assert module.hotPotatoBeamMPReceive(_lua_table(lua, remote_impulse)) is True
    assert len(state.velocities) == before + 1

    # A reset close at revision zero supersedes revision four and returns the
    # runtime to fail-closed pending mode for the new epoch.
    assert (
        module.hotPotatoBeamMPReceive(
            _lua_table(
                lua,
                {
                    "v": 1,
                    "game": "hot_potato",
                    "arena": "7-0",
                    "kind": "closed",
                    "epoch": 42,
                    "seq": 1,
                    "revision": 0,
                    "body": {"reason": "relay_reset"},
                },
            )
        )
        is True
    )
    assert module.hotPotatoGetSyncStatus().mode == "pending"
    _tick(state, module)
    assert module.getSystemState(1).behavior_stats.carrier == -1

    # A client cannot self-promote from a relay role unless it owns the prop.
    state.owned[1] = False
    role_authority = {
        "v": 1,
        "game": "hot_potato",
        "arena": "7-0",
        "kind": "role",
        "epoch": 42,
        "seq": 2,
        "revision": 0,
        "body": {"role": "authority"},
    }
    assert module.hotPotatoBeamMPReceive(_lua_table(lua, role_authority)) is True
    assert module.hotPotatoGetSyncStatus().mode == "follower"

    state.owned[1] = True
    role_authority["revision"] = 1
    role_authority["seq"] = 3
    assert module.hotPotatoBeamMPReceive(_lua_table(lua, role_authority)) is True
    assert module.hotPotatoGetSyncStatus().mode == "authority"
    assert len(state.netStates) >= 1
    _tick(state, module, seconds=0.1, steps=24)
    final_stats = module.getSystemState(1).behavior_stats
    assert final_stats.sync_mode == "authority"
    assert final_stats.carrier in (2, 3)
    assert final_stats.options_writable is True

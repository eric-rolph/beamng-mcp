"""Protocol gate for the shared Hot Potato / Sumo BeamMP server relay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "examples" / "giant_props" / "beammp_server" / "ericrolph_games" / "main.lua"
C2S = "ericrolph_games_c2s_v1"
S2C = "ericrolph_games_s2c_v1"


def _to_lua(lua, value):
    if isinstance(value, dict):
        table = lua.table()
        for key, item in value.items():
            table[key] = _to_lua(lua, item)
        return table
    if isinstance(value, list):
        table = lua.table()
        for index, item in enumerate(value, 1):
            table[index] = _to_lua(lua, item)
        return table
    return value


def _from_lua(value):
    if lupa.lua_type(value) != "table":
        return value
    items = list(value.items())
    keys = [key for key, _ in items]
    if keys and all(isinstance(key, int) for key in keys):
        ordered = sorted(keys)
        if ordered == list(range(1, len(keys) + 1)):
            return [_from_lua(value[index]) for index in ordered]
    return {key: _from_lua(item) for key, item in items}


class RelayHarness:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)

        def json_decode(raw):
            return _to_lua(self.lua, json.loads(raw))

        self.lua.globals().py_json_decode = json_decode
        self.lua.execute(
            r"""
            TEST = {registered = {}, sent = {}}
            MP = {}
            function MP.RegisterEvent(eventName, handlerName)
              TEST.registered[eventName] = handlerName
            end
            function MP.TriggerClientEventJson(playerID, eventName, data)
              TEST.sent[#TEST.sent + 1] = {
                playerID = playerID,
                eventName = eventName,
                data = data,
              }
              return true, ""
            end
            Util = {}
            function Util.JsonDecode(raw)
              return py_json_decode(raw)
            end
            """
        )
        self.lua.execute(SERVER.read_text(encoding="utf-8"))
        self.lua.globals().onInit()

    @property
    def registered(self):
        return _from_lua(self.lua.globals().TEST["registered"])

    def drain(self):
        sent = _from_lua(self.lua.globals().TEST["sent"])
        self.lua.execute("TEST.sent = {}")
        return sent if isinstance(sent, list) else []

    def raw(self, player_id, raw):
        self.lua.globals().ericrolphGamesOnClientEvent(player_id, raw)
        return self.drain()

    def send(
        self,
        player_id,
        *,
        game="hot_potato",
        arena="7-2",
        kind="hello",
        seq=1,
        epoch=0,
        body=None,
        **extra,
    ):
        message = {
            "v": 1,
            "game": game,
            "arena": arena,
            "kind": kind,
            "seq": seq,
            "epoch": epoch,
            "body": {} if body is None else body,
        }
        message.update(extra)
        return self.raw(player_id, json.dumps(message, separators=(",", ":")))

    def disconnect(self, player_id):
        self.lua.globals().ericrolphGamesOnPlayerDisconnect(player_id)
        return self.drain()

    def delete_vehicle(self, player_id, vehicle_id):
        self.lua.globals().ericrolphGamesOnVehicleDeleted(player_id, vehicle_id)
        return self.drain()

    def reset_vehicle(self, player_id, vehicle_id):
        self.lua.globals().ericrolphGamesOnVehicleReset(player_id, vehicle_id)
        return self.drain()


@pytest.fixture
def relay():
    return RelayHarness()


def _data(message):
    assert message["eventName"] == S2C
    data = message["data"]
    assert isinstance(data["seq"], int)
    assert data["seq"] >= 1
    return data


def _reject_code(messages):
    assert len(messages) == 1
    data = _data(messages[0])
    assert data["kind"] == "reject"
    return data["body"]["code"]


def test_registers_exact_global_handlers(relay):
    assert relay.registered == {
        C2S: "ericrolphGamesOnClientEvent",
        "onPlayerDisconnect": "ericrolphGamesOnPlayerDisconnect",
        "onVehicleDeleted": "ericrolphGamesOnVehicleDeleted",
        "onVehicleReset": "ericrolphGamesOnVehicleReset",
    }


@pytest.mark.parametrize("game", ["hot_potato", "sumo"])
def test_prop_owner_is_authority_even_when_follower_arrives_first(relay, game):
    follower = relay.send(8, game=game, kind="hello", seq=1)
    assert len(follower) == 1
    assert follower[0]["playerID"] == 8
    follower_role = _data(follower[0])
    assert follower_role["kind"] == "role"
    assert follower_role["epoch"] == 1
    assert follower_role["body"] == {
        "role": "follower",
        "authority": False,
        "hostPid": 7,
        "ready": False,
    }

    host = relay.send(7, game=game, kind="hello", seq=1)
    assert len(host) == 1
    assert host[0]["playerID"] == 7
    host_role = _data(host[0])
    assert host_role["kind"] == "role"
    assert host_role["body"] == {
        "role": "authority",
        "authority": True,
        "hostPid": 7,
        "ready": True,
    }


@pytest.mark.parametrize("game", ["hot_potato", "sumo"])
def test_state_and_command_broadcast_but_intent_targets_only_host(relay, game):
    relay.send(7, game=game, kind="hello", seq=1)
    relay.send(8, game=game, kind="hello", seq=1)

    denied = relay.send(
        8,
        game=game,
        kind="state",
        seq=2,
        epoch=1,
        body={"phase": "forged"},
    )
    assert _reject_code(denied) == "not_authority"

    state = relay.send(
        7,
        game=game,
        kind="state",
        seq=2,
        epoch=1,
        body={"phase": "live", "players": ["7-4", "8-3"]},
    )
    assert len(state) == 1
    assert state[0]["playerID"] == -1
    state_data = _data(state[0])
    assert state_data["kind"] == "state"
    assert state_data["senderPid"] == 7
    assert state_data["revision"] == 1
    assert state_data["body"] == {
        "phase": "live",
        "players": ["7-4", "8-3"],
    }

    command = relay.send(
        7,
        game=game,
        kind="command",
        seq=3,
        epoch=1,
        body={"event_id": "round-1", "name": "start"},
    )
    assert len(command) == 1
    assert command[0]["playerID"] == -1
    command_data = _data(command[0])
    assert command_data["kind"] == "command"
    assert command_data["senderPid"] == 7
    assert command_data["revision"] == 2

    # The rejected follower state did not consume seq=2; a valid intent can
    # reuse it and is delivered only to the deterministic authority.
    intent = relay.send(
        8,
        game=game,
        kind="intent",
        seq=2,
        epoch=1,
        body={"name": "reset_request"},
    )
    assert len(intent) == 1
    assert intent[0]["playerID"] == 7
    intent_data = _data(intent[0])
    assert intent_data["kind"] == "intent"
    assert intent_data["senderPid"] == 8
    assert intent_data["revision"] == 2
    assert intent_data["body"] == {"name": "reset_request"}


def test_late_hello_and_resync_receive_role_and_cached_state(relay):
    host_role_message = relay.send(7, kind="hello", seq=1)[0]
    snapshot = {"phase": "live", "carrier_sid": "8-3", "fuse": 9.5}
    host_state_message = relay.send(7, kind="state", seq=2, epoch=1, body=snapshot)[0]
    host_command_message = relay.send(
        7,
        kind="command",
        seq=3,
        epoch=1,
        body={"event_id": "pass-1", "name": "pass"},
    )[0]

    late = relay.send(9, kind="hello", seq=1)
    assert [item["playerID"] for item in late] == [9, 9]
    role, state = map(_data, late)
    assert role["kind"] == "role"
    assert role["revision"] == 2
    assert role["body"]["role"] == "follower"
    assert state["kind"] == "state"
    assert state["revision"] == 1
    assert state["body"] == snapshot

    resync = relay.send(
        9,
        kind="resync",
        seq=2,
        epoch=1,
        body={"last_revision": 1},
    )
    assert [item["data"]["kind"] for item in resync] == ["role", "state"]
    assert _data(resync[1])["body"] == snapshot
    all_messages = [
        host_role_message,
        host_state_message,
        host_command_message,
        *late,
        *resync,
    ]
    assert [_data(item)["seq"] for item in all_messages] == list(range(1, 8))


def test_legacy_payload_is_accepted_but_outbound_uses_body(relay):
    relay.send(7, kind="hello", seq=1)
    message = {
        "v": 1,
        "game": "hot_potato",
        "arena": "7-2",
        "kind": "state",
        "seq": 2,
        "epoch": 1,
        "payload": {"phase": "legacy"},
    }
    sent = relay.raw(7, json.dumps(message))
    data = _data(sent[0])
    assert data["body"] == {"phase": "legacy"}
    assert "payload" not in data


def test_rejects_malformed_oversized_spoofed_and_replayed_messages(relay):
    assert _reject_code(relay.raw(7, "{")) == "invalid_json"
    assert _reject_code(relay.raw(7, "x" * (64 * 1024 + 1))) == "message_too_large"
    assert _reject_code(relay.send(7, arena="7:2")) == "invalid_arena"
    assert _reject_code(relay.send(7, senderPid=8)) == "sender_mismatch"

    relay.send(7, kind="hello", seq=1)
    assert _reject_code(relay.send(7, kind="heartbeat", seq=1, epoch=1)) == "stale_seq"
    assert (
        _reject_code(relay.send(7, kind="state", seq=2, epoch=99, body={"phase": "live"}))
        == "stale_epoch"
    )


def test_forged_state_cannot_allocate_an_authority_session(relay):
    forged = relay.send(
        8,
        arena="7-9",
        kind="state",
        seq=1,
        epoch=1,
        body={"phase": "forged"},
    )
    assert _reject_code(forged) == "not_authority"
    intent = relay.send(
        8,
        arena="7-9",
        kind="intent",
        seq=2,
        epoch=1,
        body={"action": "reset"},
    )
    assert _reject_code(intent) == "no_session"


def test_vehicle_reset_increments_epoch_and_invalidates_stale_state(relay):
    for game in ("hot_potato", "sumo"):
        relay.send(7, game=game, kind="hello", seq=1)
        relay.send(
            7,
            game=game,
            kind="state",
            seq=2,
            epoch=1,
            body={"phase": "live"},
        )

    closed = relay.reset_vehicle(7, 2)
    assert len(closed) == 2
    assert {item["data"]["game"] for item in closed} == {"hot_potato", "sumo"}
    for item in closed:
        assert item["playerID"] == -1
        data = _data(item)
        assert data["kind"] == "closed"
        assert data["epoch"] == 2
        assert data["revision"] == 0
        assert data["body"]["reason"] == "arena_reset"
        assert data["body"]["previousEpoch"] == 1
        assert data["body"]["nextEpoch"] == 2

    stale = relay.send(
        7,
        game="hot_potato",
        kind="state",
        seq=3,
        epoch=1,
        body={"phase": "stale"},
    )
    assert _reject_code(stale) == "stale_epoch"

    role = relay.send(7, game="hot_potato", kind="hello", seq=1, epoch=0)
    assert _data(role[0])["epoch"] == 2
    fresh = relay.send(
        7,
        game="hot_potato",
        kind="state",
        seq=2,
        epoch=2,
        body={"phase": "open"},
    )
    assert _data(fresh[0])["revision"] == 1


def test_delete_and_disconnect_close_only_matching_host_sessions(relay):
    for game in ("hot_potato", "sumo"):
        relay.send(7, game=game, arena="7-2", kind="hello", seq=1)
    relay.send(7, game="hot_potato", arena="7-3", kind="hello", seq=1)
    relay.send(8, game="sumo", arena="8-1", kind="hello", seq=1)

    deleted = relay.delete_vehicle(7, 2)
    assert len(deleted) == 2
    deleted_data = [_data(item) for item in deleted]
    assert {data["game"] for data in deleted_data} == {"hot_potato", "sumo"}
    assert all(data["body"]["reason"] == "arena_deleted" for data in deleted_data)

    disconnected = relay.disconnect(7)
    assert len(disconnected) == 1
    data = _data(disconnected[0])
    assert data["arena"] == "7-3"
    assert data["body"]["reason"] == "host_disconnected"

    # PID 8's independent authority session remains live.
    alive = relay.send(8, game="sumo", arena="8-1", kind="heartbeat", seq=2, epoch=1)
    assert _data(alive[0])["kind"] == "role"
    assert _data(alive[0])["body"]["authority"] is True

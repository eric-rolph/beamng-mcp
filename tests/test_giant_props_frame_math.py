"""Offline coverage for the shared placement-frame math.

The live slope gate proves the frame end to end, but it needs BeamNG and it can
only afford a couple of mods. This file re-implements the exact algorithm the
generator emits -- ``baselineBasis``, the best-pair score, ``basisQuat`` -- and
runs it against every mod's shipped ``FRAME_NODES``, deterministically and in
milliseconds.

It exists because three compounding convention bugs shipped in that math
(2026-08-24), every one of them exactly identity on a level unyawed spawn, and
because the pair-selection branch it now carries is exercised live for only the
mods the gate can afford to boot.

Parsing the GENERATED runtime rather than the handoff is deliberate: this
asserts on what actually ships.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"

FRAME_NODES_RE = re.compile(r"local FRAME_NODES = \{(.*?)\n\}", re.S)
ROLE_RE = re.compile(
    r'(\w+) = \{name = "([^"]+)", mesh = vec3\(([-\d.e+]+), ([-\d.e+]+), ([-\d.e+]+)\)\}'
)
# baselineBasis rejects a baseline shorter than this, and the runtime falls back
# to the stale object transform when no pair survives.
MIN_BASELINE_M = 0.05
# A cage whose best pair only just clears the runtime's floor would be one
# authoring tweak away from losing its frame entirely.
MIN_SELECTED_SCORE_M = 0.5

Vec3 = tuple[float, float, float]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _scale(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def baseline_basis(primary: Vec3, secondary: Vec3):
    """Transcription of the emitted Lua ``baselineBasis``."""

    if _norm(primary) < MIN_BASELINE_M:
        return None
    e1 = _scale(primary, 1.0 / _norm(primary))
    e2 = _sub(secondary, _scale(e1, _dot(secondary, e1)))
    if _norm(e2) < MIN_BASELINE_M:
        return None
    e2 = _scale(e2, 1.0 / _norm(e2))
    return e1, e2, _cross(e1, e2)


def basis_quat(ex: Vec3, ey: Vec3, ez: Vec3) -> tuple[float, float, float, float]:
    """Transcription of the emitted Lua ``basisQuat``, conjugate included."""

    trace = ex[0] + ey[1] + ez[2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        x, y, z, w = (ey[2] - ez[1]) / s, (ez[0] - ex[2]) / s, (ex[1] - ey[0]) / s, 0.25 * s
    elif ex[0] > ey[1] and ex[0] > ez[2]:
        s = math.sqrt(1.0 + ex[0] - ey[1] - ez[2]) * 2
        x, y, z, w = 0.25 * s, (ey[0] + ex[1]) / s, (ez[0] + ex[2]) / s, (ey[2] - ez[1]) / s
    elif ey[1] > ez[2]:
        s = math.sqrt(1.0 + ey[1] - ex[0] - ez[2]) * 2
        x, y, z, w = (ey[0] + ex[1]) / s, 0.25 * s, (ez[1] + ey[2]) / s, (ez[0] - ex[2]) / s
    else:
        s = math.sqrt(1.0 + ez[2] - ex[0] - ey[1]) * 2
        x, y, z, w = (ez[0] + ex[2]) / s, (ez[1] + ey[2]) / s, 0.25 * s, (ex[1] - ey[0]) / s
    return (-x, -y, -z, w)


def rotate_textbook(q: tuple[float, float, float, float], v: Vec3) -> Vec3:
    """Standard q*v*inverse(q). The engine applies the TRANSPOSE of this."""

    x, y, z, w = q
    u: Vec3 = (x, y, z)
    a = _scale(u, 2 * _dot(u, v))
    b = _scale(v, w * w - _dot(u, u))
    c = _scale(_cross(u, v), 2 * w)
    return (a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2])


def _frame_nodes(runtime: Path) -> dict[str, dict]:
    body = FRAME_NODES_RE.search(runtime.read_text(encoding="utf-8"))
    assert body, f"no FRAME_NODES table in {runtime}"
    roles = {}
    for role, name, x, y, z in ROLE_RE.findall(body.group(1)):
        roles[role] = {"name": name, "mesh": (float(x), float(y), float(z))}
    return roles


def _runtimes() -> list[tuple[str, Path]]:
    found = []
    for spec in sorted(PACK_ROOT.glob("*/spec.py")):
        matches = sorted(spec.parent.glob("mod/lua/ge/extensions/*/runtime.lua"))
        if matches:
            found.append((spec.parent.name, matches[0]))
    return found


MODS = _runtimes()
IDS = [key for key, _ in MODS]


def _candidates(roles: dict[str, dict]):
    """Every viable pair, plus the one the runtime's score selects."""

    ref = roles["ref"]["mesh"]
    viable, best, best_score = [], None, 0.0
    for first_role, second_role in (("back", "left"), ("back", "up"), ("left", "up")):
        first = _sub(roles[first_role]["mesh"], ref)
        second = _sub(roles[second_role]["mesh"], ref)
        basis = baseline_basis(first, second)
        if basis is None:
            continue
        viable.append(((first_role, second_role), basis))
        score = min(_norm(first), _dot(second, basis[1]))
        if score > best_score:
            best_score, best = score, (first_role, second_role)
    return viable, best, best_score


@pytest.mark.parametrize("key,runtime", MODS, ids=IDS)
def test_frame_nodes_match_the_jbeam_refnodes(key: str, runtime: Path) -> None:
    """The emitted table must name the same nodes the jbeam designates."""

    import json

    roles = _frame_nodes(runtime)
    assert sorted(roles) == ["back", "left", "ref", "up"], (key, sorted(roles))
    mod_id = runtime.parent.name
    handoff = json.loads(
        (PACK_ROOT / key / "authoring" / f"{mod_id}.handoff.json").read_text(encoding="utf-8")
    )
    positions = {node["id"]: tuple(float(v) for v in node["position"]) for node in handoff["nodes"]}
    for role, node_id in handoff["refnodes"].items():
        assert roles[role]["name"] == node_id, (key, role)
        emitted = roles[role]["mesh"]
        authored = positions[node_id]
        assert max(abs(a - b) for a, b in zip(emitted, authored, strict=True)) < 1e-6, (
            key,
            role,
            emitted,
            authored,
        )


@pytest.mark.parametrize("key,runtime", MODS, ids=IDS)
def test_cage_offers_a_well_conditioned_baseline_pair(key: str, runtime: Path) -> None:
    """Every cage must give the frame a pair with real margin.

    A cage that only just clears ``baselineBasis``'s 5 cm floor would drop to
    the stale-object-transform fallback after one authoring tweak, and on flat
    ground nothing would notice.
    """

    roles = _frame_nodes(runtime)
    viable, best, score = _candidates(roles)
    assert viable, f"{key}: no viable baseline pair - the frame would never leave the fallback"
    assert best is not None, key
    assert score >= MIN_SELECTED_SCORE_M, {
        "mod": key,
        "selected_pair": best,
        "score_m": score,
        "message": "selected baseline pair is poorly conditioned",
    }


@pytest.mark.parametrize("key,runtime", MODS, ids=IDS)
def test_every_viable_pair_recovers_the_same_rotation(key: str, runtime: Path) -> None:
    """Pair choice must not be able to mirror or otherwise alter the frame.

    ``R = V * transpose(U)`` with both triads built by the same right-handed
    construction, so every pair should return the prop's true attitude. This is
    what makes the per-frame pair selection safe.
    """

    roles = _frame_nodes(runtime)
    ref = roles["ref"]["mesh"]
    viable, _, _ = _candidates(roles)
    assert viable, key

    # Deterministic spread of attitudes, including the level and yaw-only cases
    # that hid the original bugs, and steeply tilted ones that expose them.
    attitudes = [(0.0, 0.0, 0.0), (0.0, 0.0, 40.0), (30.0, 0.0, 0.0), (0.0, 25.0, 140.0)]
    attitudes += [(a * 17.0 % 180.0, a * 41.0 % 180.0, a * 79.0 % 360.0) for a in range(1, 13)]

    worst = 0.0
    for pitch, roll, yaw in attitudes:
        rotation = _euler(pitch, roll, yaw)
        world = {role: _apply(rotation, _sub(data["mesh"], ref)) for role, data in roles.items()}
        recovered = []
        for (first_role, second_role), (u1, u2, u3) in viable:
            live = baseline_basis(
                _sub(world[first_role], world["ref"]), _sub(world[second_role], world["ref"])
            )
            assert live is not None, (key, first_role, second_role)
            v1, v2, v3 = live
            columns = [
                tuple(v1[i] * u1[j] + v2[i] * u2[j] + v3[i] * u3[j] for i in range(3))
                for j in range(3)
            ]
            recovered.append(columns)
            for j in range(3):
                for i in range(3):
                    worst = max(worst, abs(columns[j][i] - rotation[i][j]))
        for other in recovered[1:]:
            for j in range(3):
                for i in range(3):
                    assert abs(other[j][i] - recovered[0][j][i]) < 1e-9, (key, pitch, roll, yaw)
    assert worst < 1e-9, {"mod": key, "worst_component_error": worst}


@pytest.mark.parametrize("key,runtime", MODS, ids=IDS)
def test_basis_quat_is_conjugated_for_the_engine_convention(key: str, runtime: Path) -> None:
    """``basisQuat`` must return the CONJUGATE of the textbook quaternion.

    The engine's ``q * vec3`` applies the opposite handedness, so the textbook
    quaternion transposes the rotation -- an exact no-op while the prop is level
    and silently wrong the moment it tilts. Shipping the un-conjugated form left
    Boot of Doom's instruments 2.2 m out on a slope.
    """

    roles = _frame_nodes(runtime)
    ref = roles["ref"]["mesh"]
    viable, _, _ = _candidates(roles)
    assert viable, key

    for pitch, roll, yaw in ((35.0, 12.0, 0.0), (5.0, 0.0, 40.0), (60.0, 45.0, 200.0)):
        rotation = _euler(pitch, roll, yaw)
        world = {role: _apply(rotation, _sub(data["mesh"], ref)) for role, data in roles.items()}
        (first_role, second_role), (u1, u2, u3) = viable[0]
        live = baseline_basis(
            _sub(world[first_role], world["ref"]), _sub(world[second_role], world["ref"])
        )
        assert live is not None, key
        v1, v2, v3 = live
        columns = [
            tuple(v1[i] * u1[j] + v2[i] * u2[j] + v3[i] * u3[j] for i in range(3)) for j in range(3)
        ]
        quat = basis_quat(columns[0], columns[1], columns[2])
        # Engine result == textbook(conjugate) == R applied the intended way.
        for j, axis in enumerate(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))):
            engine = rotate_textbook((-quat[0], -quat[1], -quat[2], quat[3]), axis)
            for i in range(3):
                assert abs(engine[i] - columns[j][i]) < 1e-9, (key, pitch, roll, yaw, j)


def _euler(pitch_deg: float, roll_deg: float, yaw_deg: float):
    """Row-major rotation matrix; columns are the rotated basis vectors."""

    p, r, y = map(math.radians, (pitch_deg, roll_deg, yaw_deg))
    cp, sp, cr, sr, cy, sy = (
        math.cos(p),
        math.sin(p),
        math.cos(r),
        math.sin(r),
        math.cos(y),
        math.sin(y),
    )
    rx = ((1, 0, 0), (0, cp, -sp), (0, sp, cp))
    ry = ((cr, 0, sr), (0, 1, 0), (-sr, 0, cr))
    rz = ((cy, -sy, 0), (sy, cy, 0), (0, 0, 1))
    return _matmul(_matmul(rz, ry), rx)


def _matmul(a, b):
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )


def _apply(m, v: Vec3) -> Vec3:
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))  # type: ignore[return-value]


def test_the_pack_has_frame_nodes_for_every_mod() -> None:
    """A mod without a generated runtime silently escapes every check above."""

    specs = {spec.parent.name for spec in PACK_ROOT.glob("*/spec.py")}
    covered = {key for key, _ in MODS}
    missing = sorted(specs - covered)
    assert not missing, f"mods with no generated runtime to check: {missing}"

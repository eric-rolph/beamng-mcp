"""Place the B4 props: TSStatic records, the four prefab clusters and the registry handoff.

    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.place_props \\
        --manifest examples/hot_potato_arena/authoring/ericrolph_hot_potato_arena_props_place.json

What this module owns in the level tree
---------------------------------------
* ``main/MissionGroup/props/items.level.json`` -- 74 placed TSStatics (4 logs, the tripod, the
  lantern, the pot, the sign, 2 cairns, 4 lantern posts, 61 fence segments) plus 430 ``Prefab``
  instances of the four cluster files.
* ``art/prefabs/<id>_pf_*.prefab`` -- the four cluster files, in the stock TorqueScript form
  (``groupPosition = "0 0 0"`` and LOCAL child positions, which is how stock italy authors a
  prefab it instantiates 42 times at 42 different world positions -- verified by reading
  ``levels/italy/art/prefabs/italy_traf_sign_arrows_left_right.prefab``).
* ``art/shapes/props/<id>_props.materials.json`` -- via ``prop_textures.material_document``.
* the registry handoff rows B5 folds into ``level_obstacles``.

It owns NOTHING else: B1's terrain, sky, water, backdrop, roads-as-records and camera
bookmarks, B2's hearth, and B3's forest are read but never written.

Every z comes from ``terrain_io.surface_z`` (the shipped grid), not from the design model, and
the difference between the two is recorded per row so a critic can see the terrain drift
rather than take it on trust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from examples.hot_potato_arena.level import props_spec as ps
from examples.hot_potato_arena.level import terrain_io as terrain
from examples.hot_potato_arena.level import terrain_model as tm

LEVEL_ID = ps.LEVEL_ID
EXAMPLE_ROOT = ps.EXAMPLE_ROOT
LEVEL_ROOT = EXAMPLE_ROOT / "mod" / "levels" / LEVEL_ID
PLACE_SEED = 0x504C4143  # "PLAC"
GROUP = ps.PROPS_GROUP
ROAD_KEEPOUT_M = 12.0
TRAIL_EDGE_BAND = (7.0, 14.0)


def persistent_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp/{LEVEL_ID}/{name}"))


def _r6(value: float) -> float:
    return round(float(value) + 0.0, 6)


def _r3(value: float) -> float:
    return round(float(value) + 0.0, 3)


def facing_matrix(bearing_deg: float) -> list[float]:
    """A shape whose local +Y points at compass ``bearing_deg``."""

    return ps.engine_yaw_matrix(-bearing_deg)


def _normalise(v):
    length = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / length for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def terrain_normal(x: float, y: float, h: float = 1.0) -> tuple[float, float, float]:
    dzdx = (float(terrain.surface_z(x + h, y)) - float(terrain.surface_z(x - h, y))) / (2 * h)
    dzdy = (float(terrain.surface_z(x, y + h)) - float(terrain.surface_z(x, y - h))) / (2 * h)
    return _normalise((-dzdx, -dzdy, 1.0))


def slope_matrix(x: float, y: float, yaw_deg: float, max_tilt_deg: float = 20.0) -> list[float]:
    """Rows = local axes: +Z along the terrain normal (capped), +X yawed about it."""

    nz = terrain_normal(x, y)
    tilt = math.degrees(math.acos(min(1.0, max(-1.0, nz[2]))))
    if tilt > max_tilt_deg and tilt > 1e-9:
        t = math.radians(max_tilt_deg)
        horiz = math.hypot(nz[0], nz[1]) or 1.0
        nz = (nz[0] / horiz * math.sin(t), nz[1] / horiz * math.sin(t), math.cos(t))
    a = math.radians(yaw_deg)
    ref = (math.cos(a), math.sin(a), 0.0)
    ny = _normalise(_cross(nz, ref))
    nx = _normalise(_cross(ny, nz))
    return [_r6(c) for c in (*nx, *ny, *nz)]


def _static(
    name: str,
    shape_key: str,
    position: tuple[float, float, float],
    rotation: list[float],
    *,
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    collision: str | None = None,
    shape_path: str | None = None,
) -> dict[str, Any]:
    spec = ps.SHAPES.get(shape_key, {})
    kind = collision or spec.get("collision", "Collision Mesh")
    return {
        "name": name,
        "class": "TSStatic",
        "persistentId": persistent_id(name),
        "__parent": GROUP,
        "position": [_r6(position[0]), _r6(position[1]), _r3(position[2])],
        "rotationMatrix": rotation,
        "scale": [float(s) for s in scale],
        "shapeName": shape_path or ps.shape_path(shape_key),
        "collisionType": kind,
        "decalType": kind,
        "prebuildCollisionData": "1",
        "useInstanceRenderData": True,
        "playAmbient": "1",
        "instanceColor": "White",
    }


# ------------------------------------------------------------------ the placed props
def fence_stations() -> list[dict[str, Any]]:
    """Post centres along the trail's downhill edge, and the bays between them."""

    samples = tm.trail_samples(1.0)
    rows = []
    for index in range(ps.FENCE["posts"] + 1):
        m = ps.FENCE["start_m"] + index * ps.FENCE["pitch_m"]
        i = int(min(max(m, 0), len(samples) - 2))
        (ax, ay), (bx, by) = samples[i], samples[i + 1]
        length = math.hypot(bx - ax, by - ay) or 1.0
        ux, uy = (bx - ax) / length, (by - ay) / length
        px = ax + uy * ps.FENCE["lateral_m"]
        py = ay - ux * ps.FENCE["lateral_m"]
        rows.append(
            {
                "m": m,
                "x": _r6(px),
                "y": _r6(py),
                "z": _r3(float(terrain.surface_z(px, py))),
                "heading": round(math.degrees(math.atan2(ux, uy)) % 360.0, 3),
            }
        )
    return rows


def placed_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    z_rows: list[dict[str, Any]] = []

    def note(name: str, x: float, y: float, z: float, design_z: float | None) -> None:
        z_rows.append(
            {
                "name": name,
                "x": _r6(x),
                "y": _r6(y),
                "z": _r3(z),
                "terrain_z": _r3(float(terrain.surface_z(x, y))),
                "design_terrain_z": None if design_z is None else _r3(design_z),
            }
        )

    # --- the logs and the giant props: REMOVED (amendment A2) ---------------------------
    # 2026-09-15/16, the user's call, in two messages: the two kindling logs ("smoking
    # logs"), the enamel pot ("cauldron"), the lantern tripod ("cooking tripod") and the
    # hurricane lantern that hung from it; then the leaner log (it lay across the trail),
    # the half-log bench deck and the four lantern posts. Their shapes stay in the tree
    # (members, manifests and harvests untouched); only the placements are gone. The hearth
    # round's log-end fire/smoke emitters, the four kindling fire lights, the lantern's two
    # lights and the four track-lantern lights on the posts are removed in hearth_spec for
    # the same reason. `ps.log_row` / `ps.prop_row` still answer for every one of them, so
    # the shape gates keep measuring the shipped bytes.

    # --- the sign and the two cairns ----------------------------------------------------
    sign = ps.prop_row("trail_sign")
    sx, sy = float(sign["x"]), float(sign["y"])
    sz = float(terrain.surface_z(sx, sy))
    records.append(
        _static(f"{LEVEL_ID}_trail_sign", "trail_sign", (sx, sy, sz), facing_matrix(330.0))
    )
    note(f"{LEVEL_ID}_trail_sign", sx, sy, sz, float(sign["z_ground"]))
    for index in (0, 1):
        cairn = ps.prop_row(f"trail_cairn_{index}")
        cx, cy = float(cairn["x"]), float(cairn["y"])
        cz = float(terrain.surface_z(cx, cy))
        records.append(
            _static(
                f"{LEVEL_ID}_trail_cairn_{index}",
                "trail_cairn",
                (cx, cy, cz - 0.12),
                slope_matrix(cx, cy, 37.0 + index * 91.0),
            )
        )
        note(f"{LEVEL_ID}_trail_cairn_{index}", cx, cy, cz, float(cairn["z_ground"]))

    # --- the four lantern posts: REMOVED 2026-09-16 (amendment A2; see the note above) ---

    # --- the split-rail fence along the trail -------------------------------------------
    stations = fence_stations()
    for index, station in enumerate(stations):
        records.append(
            _static(
                f"{LEVEL_ID}_fence_post_{index:02d}",
                "fence_post",
                (station["x"], station["y"], station["z"]),
                slope_matrix(station["x"], station["y"], 90.0 - station["heading"], 12.0),
            )
        )
    for index in range(len(stations) - 1):
        a, b = stations[index], stations[index + 1]
        mx, my = (a["x"] + b["x"]) / 2.0, (a["y"] + b["y"]) / 2.0
        mz = (a["z"] + b["z"]) / 2.0
        heading = math.degrees(math.atan2(b["x"] - a["x"], b["y"] - a["y"])) % 360.0
        for level, height in enumerate(ps.FENCE["rail_z"]):
            records.append(
                _static(
                    f"{LEVEL_ID}_fence_rail_{index:02d}_{level}",
                    "fence_rail",
                    (mx, my, mz + height),
                    ps.heading_matrix(heading),
                )
            )
    return records, z_rows, stations


# ------------------------------------------------------------------ prefab clusters
def _rng(*parts: Any) -> np.random.Generator:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big") ^ PLACE_SEED)


def cluster_members(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    """The prefab file's children: LOCAL positions inside ``spread`` metres of its origin."""

    rng = _rng("members", cluster["key"])
    mix = ps.CLUSTER_MIX[cluster["key"]]
    rows = []
    for index, (family, shape) in enumerate(mix):
        angle = 2.0 * math.pi * (index + rng.random() * 0.6) / len(mix)
        radius = cluster["spread"] * (0.25 + 0.75 * rng.random())
        rows.append(
            {
                "name": f"{cluster['key']}_{index:02d}",
                "family": family,
                "shape": shape,
                "x": _r3(radius * math.sin(angle)),
                "y": _r3(radius * math.cos(angle)),
                "z": _r3(-0.15 - 0.35 * rng.random()),
                "yaw": round(float(rng.random() * 360.0), 2),
                "scale": round(float(0.8 + rng.random() * 0.9), 3),
            }
        )
    return rows


_TRAIL_XY: np.ndarray | None = None


def _trail_samples() -> np.ndarray:
    """The corner-rounded trail centreline at 0.5 m, as an (N, 2) array (cached).

    ``terrain_model.trail_distance_field`` builds a full meshgrid, which is the right shape
    for a 2048-square terrain pass and the wrong one for a rejection sampler asking about one
    point at a time; the samples underneath it are the same.
    """

    global _TRAIL_XY
    if _TRAIL_XY is None:
        _TRAIL_XY = np.asarray(tm.trail_samples(0.5), dtype=np.float64)
    return _TRAIL_XY


def _trail_distance(x: float, y: float) -> float:
    xy = _trail_samples()
    return float(np.min(np.hypot(xy[:, 0] - x, xy[:, 1] - y)))


def _road_distance(x: float, y: float) -> float:
    """Distance to the nearest road centreline (track ring, AI ring, trail)."""

    r = math.hypot(x - ps.CENTER[0], y - ps.CENTER[1])
    ring_gap = min(abs(r - tm.TRACK_R), abs(r - 170.0))
    if ring_gap >= ROAD_KEEPOUT_M and r > tm.TRACK_R + 60.0:
        # far outside both rings; only the trail can be nearer
        return min(ring_gap, _trail_distance(x, y))
    return min(ring_gap, _trail_distance(x, y))


def cluster_sites(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    """Instance centres: rejection-sampled against the roads, the lanes and the layers."""

    rng = _rng("sites", cluster["key"])
    r0, r1 = cluster["r"]
    want = cluster["instances"]
    sites: list[dict[str, Any]] = []
    tries = 0
    samples = tm.trail_samples(1.0) if cluster["zone"] == "trail" else None
    while len(sites) < want and tries < want * 1200:
        tries += 1
        if samples is not None:
            # sample ALONG the trail, not over the annulus: a 7-14 m edge band is 1.2 % of
            # the annulus's area and a uniform draw wastes 99 % of its tries on it
            i = int(rng.integers(1, len(samples) - 2))
            (ax, ay), (bx, by) = samples[i], samples[i + 1]
            length = math.hypot(bx - ax, by - ay) or 1.0
            ux, uy = (bx - ax) / length, (by - ay) / length
            side = 1.0 if rng.random() < 0.5 else -1.0
            band = TRAIL_EDGE_BAND[1] - TRAIL_EDGE_BAND[0]
            lateral = side * (TRAIL_EDGE_BAND[0] + rng.random() * band)
            x, y = ax + uy * lateral, ay - ux * lateral
            r, bearing = ps.polar(x, y)
            if not (r0 <= r <= r1):
                continue
        else:
            r = math.sqrt(rng.random() * (r1 * r1 - r0 * r0) + r0 * r0)
            bearing = rng.random() * 360.0
            x, y = ps.bearing_point(bearing, r)
        if abs(x - ps.CENTER[0]) > 980 or abs(y - ps.CENTER[1]) > 980:
            continue
        if cluster["zone"] == "trail":
            d = _trail_distance(x, y)
            if not (TRAIL_EDGE_BAND[0] <= d <= TRAIL_EDGE_BAND[1]):
                continue
        else:
            if tm.tree_free(x, y):
                continue
            if _road_distance(x, y) < ROAD_KEEPOUT_M:
                continue
        z = float(terrain.surface_z(x, y))
        if not np.isfinite(z):
            continue
        if cluster["zone"] == "shore":
            if not (tm.LAKE_LEVEL + 0.10 <= z <= tm.LAKE_LEVEL + 4.5):
                continue
        elif z <= tm.LAKE_LEVEL + 0.5:
            continue
        if cluster["layers"]:
            if terrain.layer_at(x, y) not in cluster["layers"]:
                continue
        normal = terrain_normal(x, y)
        if normal[2] < math.cos(math.radians(34.0)):
            continue
        if any(math.dist((x, y), (s["x"], s["y"])) < cluster["spread"] * 2.2 for s in sites[-60:]):
            continue
        sites.append(
            {
                "x": _r6(x),
                "y": _r6(y),
                "z": _r3(z),
                "yaw": round(float(rng.random() * 360.0), 2),
                "r": round(r, 1),
                "bearing": round(bearing, 1),
                "layer": terrain.layer_at(x, y),
            }
        )
    return sites


def prefab_relative(key: str) -> str:
    return f"{ps.PREFAB_DIR}/{LEVEL_ID}_{key}.prefab"


def prefab_document(cluster: dict[str, Any]) -> bytes:
    """One stock-form ``.prefab``: a SimGroup at the origin with LOCAL child transforms."""

    lines = [
        "//--- OBJECT WRITE BEGIN ---",
        "$ThisPrefab = new SimGroup() {",
        '   canSave = "1";',
        '   canSaveDynamicFields = "1";',
        '      groupPosition = "0.000000 0.000000 0.000000";',
        "",
    ]
    for member in cluster_members(cluster):
        matrix = ps.engine_yaw_matrix(member["yaw"])
        lines += [
            "   new TSStatic() {",
            f'      shapeName = "{ps.b3_shape_path(member["family"], member["shape"])[1:]}";',
            '      dynamic = "0";',
            '      playAmbient = "1";',
            '      meshCulling = "0";',
            '      originSort = "0";',
            '      useInstanceRenderData = "1";',
            '      instanceColor = "White";',
            '      collisionType = "Collision Mesh";',
            '      decalType = "Collision Mesh";',
            '      prebuildCollisionData = "1";',
            '      renderNormals = "0";',
            f'      position = "{member["x"]:.6f} {member["y"]:.6f} {member["z"]:.6f}";',
            f'      scale = "{member["scale"]} {member["scale"]} {member["scale"]}";',
            '      rotationMatrix = "' + " ".join(f"{c:.9f}" for c in matrix) + '";',
            '      canSave = "1";',
            '      canSaveDynamicFields = "1";',
            f'      persistentId = "{persistent_id(member["name"])}";',
            "   };",
        ]
    lines += ["};", "//--- OBJECT WRITE END ---", ""]
    return "\n".join(lines).encode("utf-8")


def prefab_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for cluster in ps.PREFAB_CLUSTERS:
        sites = cluster_sites(cluster)
        for index, site in enumerate(sites):
            name = f"{LEVEL_ID}_{cluster['key']}_{index:03d}"
            records.append(
                {
                    "name": name,
                    "class": "Prefab",
                    "persistentId": persistent_id(name),
                    "__parent": GROUP,
                    "position": [site["x"], site["y"], site["z"]],
                    "rotationMatrix": slope_matrix(site["x"], site["y"], site["yaw"]),
                    "fileName": f"levels/{LEVEL_ID}/{prefab_relative(cluster['key'])}",
                }
            )
        summary[cluster["key"]] = {
            "instances": len(sites),
            "requested": cluster["instances"],
            "members": len(ps.CLUSTER_MIX[cluster["key"]]),
            "statics": len(sites) * len(ps.CLUSTER_MIX[cluster["key"]]),
            "r_min": min((s["r"] for s in sites), default=None),
            "r_max": max((s["r"] for s in sites), default=None),
            "sites": sites,
        }
    return records, summary


# ------------------------------------------------------------------ the registry handoff
def registry_rows() -> list[dict[str, Any]]:
    """The B4 rows of ``layout.registry_full``, re-derived against the BUILT placement."""

    # B2 owns the 20 hearth stones and the 8 chocks; every other row of the design's 67 is a
    # B4 solid.  Selecting on the design's own ``why`` field rather than guessing from name
    # prefixes is what keeps the tripod's three feet (``why`` = "2.5 m pole") in the handoff:
    # a prefix filter on "lantern_tripod" silently dropped them, because the design names
    # them ``tripod_foot_<n>``.
    b2_reasons = {"hearth stone", "chock"}
    rows = []
    for row in ps.design_layout()["registry_full"]:
        name = row["name"]
        if row["why"] in b2_reasons:
            continue
        rows.append(
            {
                "name": name,
                "x": _r6(row["x"]),
                "y": _r6(row["y"]),
                "r": float(row["r"]),
                "rp": float(row["rp"]),
                "why": row["why"],
                "owner": "B4",
            }
        )
    return rows


# ------------------------------------------------------------------ level outputs
def rendered_outputs() -> dict[str, bytes]:
    from examples.hot_potato_arena.level import prop_textures as pt

    records, _, _ = placed_records()
    prefabs, _ = prefab_records()
    payload = "".join(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        for record in [*records, *prefabs]
    ).encode("utf-8")
    outputs: dict[str, bytes] = {
        f"main/MissionGroup/{GROUP}/items.level.json": payload,
        f"{ps.SHAPE_DIR}/{LEVEL_ID}_props.materials.json": (
            json.dumps(pt.material_document(), indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8"),
    }
    for cluster in ps.PREFAB_CLUSTERS:
        outputs[prefab_relative(cluster["key"])] = prefab_document(cluster)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=LEVEL_ROOT)
    arguments = parser.parse_args(argv)
    started = time.time()
    records, z_rows, stations = placed_records()
    prefabs, summary = prefab_records()
    outputs = rendered_outputs()
    for relative, payload in outputs.items():
        target = arguments.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    manifest = {
        "level_id": LEVEL_ID,
        "seed": PLACE_SEED,
        "placed_statics": len(records),
        "prefab_instances": len(prefabs),
        "prefab_statics": sum(v["statics"] for v in summary.values()),
        "clusters": {
            k: {kk: vv for kk, vv in v.items() if kk != "sites"} for k, v in summary.items()
        },
        "cluster_sites": {k: v["sites"] for k, v in summary.items()},
        "fence_stations": stations,
        "z_rows": z_rows,
        "registry_rows": registry_rows(),
        "files": {
            relative: {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
            for relative, payload in sorted(outputs.items())
        },
        "seconds": round(time.time() - started, 1),
    }
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"[place] {manifest['placed_statics']} statics + {manifest['prefab_instances']} prefab "
        f"instances ({manifest['prefab_statics']} instantiated) in {manifest['seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

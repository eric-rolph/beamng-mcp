"""Write B2's hearth into the level tree, and print every static gate's reading.

    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.place_hearth
    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.place_hearth --check

``--check`` writes nothing and returns 1 if the tree disagrees with the render.

What this writes, and what it merges:

* OWNED (written whole): the three group JSONLs, the hearth and decal material
  documents, the four datablock documents, the audio-forest meta.
* MERGED (read, B2's part replaced, written back): ``main.decals.json`` -- shared
  with B4's road stack -- and ``main/MissionGroup/items.level.json``, which is B1's
  rendered listing of the level's SimGroups.  B2 adds three namespaced rows to
  it (``<id>_hearth`` / ``<id>_night_light`` / ``<id>_audio``); the three-line patch for
  ``level_writer.mission_group_records()`` is in ``report_B2.md`` so B1/B6 can fold
  it in and the merge becomes a no-op.
* HANDED OFF: ``authoring/<id>_level_obstacles.json`` -- the 67 registry rows B5
  needs, with B2's own 28 stones marked.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from examples.hot_potato_arena.level import hearth_build as hb
from examples.hot_potato_arena.level import hearth_spec as hs
from examples.hot_potato_arena.level import terrain_model as tm

LEVEL_ROOT = hb.LEVEL_ROOT


def merge_groups(root: Path, *, check_only: bool = False) -> dict[str, Any]:
    """Add B2's three SimGroup rows to B1's MissionGroup listing, idempotently."""

    target = root / hb.GROUPS_MEMBER
    existing: list[dict[str, Any]] = []
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    have = {str(record.get("name")) for record in existing}
    added = [record for record in hs.group_records() if record["name"] not in have]
    if not added:
        return {"added": [], "total": len(existing)}
    merged = existing + added
    payload = hb._jsonl(merged)
    if not check_only:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return {"added": [r["name"] for r in added], "total": len(merged)}


def merge_decals(root: Path, *, check_only: bool = False) -> dict[str, Any]:
    """Replace only B2's own keys in ``main.decals.json``; leave every other key."""

    target = root / hb.DECALS_MEMBER
    document: dict[str, Any]
    if target.is_file():
        document = json.loads(target.read_text(encoding="utf-8"))
    else:
        document = {
            "header": {
                "name": "DecalData File",
                "comments": (
                    "Instances format: rectIdx, size, renderPriority, position.x, position.y, "
                    "position.z, normal.x, normal.y, normal.z, tangent.x, tangent.y, "
                    "tangent.z, uid"
                ),
                "version": 2,
            },
            "instances": {},
        }
    instances = dict(document.get("instances") or {})
    mine = hb.decal_instances()
    foreign = {k: v for k, v in instances.items() if k not in mine}
    instances = {**foreign, **mine}
    document["instances"] = dict(sorted(instances.items()))
    payload = hb._json(document)
    stale = not target.is_file() or target.read_bytes() != payload
    if stale and not check_only:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return {
        "keys": len(mine),
        "rows": sum(len(v) for v in mine.values()),
        "foreign_keys": sorted(foreign),
        "stale": stale,
    }


# --- the static gates ----------------------------------------------------------------
def gate_clearance() -> dict[str, Any]:
    """G-S1 stone faces >= r 202 from C; G-S2 the four lanes >= 35 m by geometry.

    The lane width is measured the way a car meets it: between the two stones that
    flank the lane, face to face, as the chord perpendicular to the lane axis.  Any
    left/right pair including chocks is tested and the tightest is reported.
    """

    stones = hs.stones()
    faces = []
    for stone in stones:
        r, bearing = hs.polar(float(stone["x"]), float(stone["y"]))
        faces.append(
            {
                "name": stone["name"],
                "r_centre": round(r, 3),
                "bearing": round(bearing, 3),
                "rho": float(stone["diam"]) / 2.0,
                "r_inner_face": round(r - float(stone["diam"]) / 2.0, 3),
                "r_outer_face": round(r + float(stone["diam"]) / 2.0, 3),
            }
        )
    lanes = {}
    for lane in (60.0, 150.0, 240.0, 330.0):
        widths = []
        for a in faces:
            for b in faces:
                if a["name"] >= b["name"]:
                    continue
                da = (a["bearing"] - lane + 180.0) % 360.0 - 180.0
                db = (b["bearing"] - lane + 180.0) % 360.0 - 180.0
                if da == 0 or db == 0 or (da > 0) == (db > 0):
                    continue  # not a left/right pair about this lane
                ax, ay = hs.bearing_point(a["bearing"], a["r_centre"])
                bx, by = hs.bearing_point(b["bearing"], b["r_centre"])
                # perpendicular offsets from the lane axis, minus each stone's radius
                ua, va = _lane_frame(lane, ax, ay)
                ub, vb = _lane_frame(lane, bx, by)
                if ua < 0 or ub < 0:
                    continue
                gap = (abs(va) - a["rho"]) + (abs(vb) - b["rho"])
                widths.append({"pair": [a["name"], b["name"]], "width": round(gap, 3)})
        widths.sort(key=lambda row: row["width"])
        lanes[f"lane_{int(lane)}"] = widths[0] if widths else None
    return {
        "min_inner_face_r": round(min(f["r_inner_face"] for f in faces), 3),
        "faces": faces,
        "lanes": lanes,
        "lane_min": round(min(v["width"] for v in lanes.values() if v), 3),
    }


def _lane_frame(lane_deg: float, x: float, y: float) -> tuple[float, float]:
    """(along, across) of a point in the lane's own frame, origin C."""

    theta = math.radians(lane_deg)
    ax, ay = math.sin(theta), math.cos(theta)
    dx, dy = x - hs.C[0], y - hs.C[1]
    return dx * ax + dy * ay, -dx * ay + dy * ax


def gate_fire_sites() -> dict[str, Any]:
    """G-S3: every fire site >= 1.5 m clear of its log's capsule and >= 30 m from any stone."""

    stones = hs.stones()
    rows = []
    for fire in hs.layout()["fires"]:
        distances = [
            (
                math.hypot(float(fire["x"]) - float(s["x"]), float(fire["y"]) - float(s["y"]))
                - float(s["diam"]) / 2.0,
                s["name"],
            )
            for s in stones
        ]
        nearest = min(distances)
        rows.append(
            {
                "fire": fire["name"],
                "clear_of_log_capsule_m": float(fire["clear_of_log_capsule_m"]),
                "nearest_stone": nearest[1],
                "nearest_stone_face_m": round(nearest[0], 3),
            }
        )
    return {
        "fires": rows,
        "min_log_clearance_m": min(r["clear_of_log_capsule_m"] for r in rows),
        "min_stone_face_m": round(min(r["nearest_stone_face_m"] for r in rows), 3),
    }


def gate_z() -> dict[str, Any]:
    """G-S4: every placed object's z minus the terrain z beneath it.

    Statics sit at their AUTHORED offset (stones -1.5, chocks -0.8, crust 0);
    emitters, lights and audio must be >= 0.  The terrain here is the frozen
    ``terrain_model``; the live gate repeats the same table by ray.
    """

    rows = []

    def add(kind: str, name: str, x: float, y: float, z: float, authored: float | None) -> None:
        ground = float(tm.z_at(x, y))
        rows.append(
            {
                "kind": kind,
                "name": name,
                "z": round(z, 4),
                "terrain_z": round(ground, 4),
                "delta": round(z - ground, 4),
                "authored_offset": authored,
            }
        )

    for stone in hs.stones():
        add("stone", stone["name"], stone["x"], stone["y"], stone["z"], float(stone["z_offset"]))
    for plate in hs.crust_plates():
        add(
            "crust",
            plate["name"],
            plate["position"][0],
            plate["position"][1],
            plate["position"][2],
            0.0,
        )
    for emitter in hs.layout()["emitters"]:
        add("emitter", emitter["name"], emitter["x"], emitter["y"], emitter["z"], None)
    for light in hs.layout()["night_lights"]:
        add("light", light["name"], light["x"], light["y"], light["z"], None)
    for row in hs.layout()["sfx_emitters"] + hs.layout()["sfx_spaces"]:
        z = float(row["z"]) if "z" in row else float(row["centre"][2])
        add("audio", row["name"], row["x"], row["y"], z, None)
    non_static = [r for r in rows if r["authored_offset"] is None]
    static = [r for r in rows if r["authored_offset"] is not None]
    return {
        "rows": rows,
        "count": len(rows),
        "non_static_min_delta": round(min(r["delta"] for r in non_static), 4),
        "static_offset_max_error": round(
            max(abs(r["delta"] - float(r["authored_offset"])) for r in static), 4
        ),
    }


def gate_names() -> dict[str, Any]:
    """G-S5: the datablock/object/material name census, and no collision anywhere.

    SimObject names are global across classes (level_facts: a Material named like a
    TSForestItemData is refused and every instance of it vanishes), so this walks the
    whole shipped tree -- B1's and B3's names included -- and refuses a collision.
    """

    mine = hb.census()
    own_groups = {str(record["name"]) for record in hs.group_records()}
    foreign: dict[str, str] = {}
    root = hb.LEVEL_ROOT
    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(f"main/MissionGroup/{group}") for group in own_groups):
            continue
        if relative.startswith((hs.SHAPE_DIR, hs.DECAL_DIR, hs.DATABLOCK_DIR)):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if relative.endswith("items.level.json") or relative.endswith(".forest4.json"):
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict):
                records = [v for v in document.values() if isinstance(v, dict)]
            else:
                continue
        for record in records:
            name = record.get("name") or record.get("internalName")
            if isinstance(name, str) and name and name not in own_groups:
                # B2's own three SimGroup rows live in B1's MissionGroup listing
                # because that listing is MERGED, not owned; they are not foreign.
                foreign.setdefault(name, relative)
    names = set()
    for group in (
        hs.stone_records(),
        hs.crust_records(),
        hs.emitter_records(),
        hs.light_records(),
        hs.audio_records(),
        hs.group_records(),
    ):
        names |= {str(r["name"]) for r in group}
    names |= set(hs.rock_materials_document())
    names |= set(hs.decal_materials_document())
    names |= set(hs.decal_datablock_file()[1])
    names |= set(hs.sfx_datablock_file()[1])
    for document in hs.particle_datablock_files().values():
        names |= set(document)
    collisions = sorted((n, foreign[n]) for n in names if n in foreign)
    unnamespaced = sorted(n for n in names if not n.startswith(f"{hs.LEVEL_ID}_"))
    return {
        "b2_names": len(names),
        "duplicate_within_b2": mine["duplicate_names"],
        "collisions_with_the_tree": collisions,
        "unnamespaced": unnamespaced,
        "foreign_names_scanned": len(foreign),
    }


def gate_datablock_resolution() -> dict[str, Any]:
    """G-S6 (design R10): every reference resolves to something the level ships or stock has."""

    stock_particles = {"BNGP_Fire_Huge", "BNGP_6", "BNGP_24", "BNGP_waterfallsteam"}
    stock_nodes = {"lightExampleEmitterNodeData1"}
    stock_loops = {"amb_windtrees_01", "amb_birds_01"}
    level_particles: set[str] = set()
    level_emitters: dict[str, str] = {}
    level_nodes: set[str] = set()
    for document in hs.particle_datablock_files().values():
        for name, record in document.items():
            if record["class"] == "ParticleData":
                level_particles.add(name)
            elif record["class"] == "ParticleEmitterData":
                level_emitters[name] = str(record["particles"])
            elif record["class"] == "ParticleEmitterNodeData":
                level_nodes.add(name)
    level_profiles = set(hs.sfx_datablock_file()[1])
    problems: list[str] = []
    for record in hs.emitter_records():
        if record["emitter"] not in level_emitters and record["emitter"] not in stock_particles:
            problems.append(f"{record['name']}: emitter {record['emitter']} unresolved")
        if record["dataBlock"] not in level_nodes and record["dataBlock"] not in stock_nodes:
            problems.append(f"{record['name']}: dataBlock {record['dataBlock']} unresolved")
    for name, particle in level_emitters.items():
        if particle not in level_particles:
            problems.append(f"{name}: particles {particle} is not a level ParticleData")
    for record in hs.audio_records():
        if record["class"] != "SFXEmitter":
            continue
        track = str(record["track"])
        if track not in level_profiles and track not in stock_loops:
            problems.append(f"{record['name']}: track {track} is not a proven looping profile")
    for record in hs.decal_datablock_file()[1].values():
        if record["material"] not in hs.decal_materials_document():
            problems.append(f"{record['name']}: material {record['material']} is not shipped")
    return {
        "level_particles": sorted(level_particles),
        "level_emitters": level_emitters,
        "level_nodes": sorted(level_nodes),
        "level_sfx_profiles": sorted(level_profiles),
        "stock_referenced": sorted(stock_particles | stock_nodes | stock_loops),
        "problems": problems,
    }


def gate_json() -> dict[str, Any]:
    """G-S7: strict JSON, LF only, uuid5 ids, and every material's version vs its slots."""

    problems: list[str] = []
    outputs = hb.rendered_outputs()
    for path, payload in outputs.items():
        if b"\r" in payload:
            problems.append(f"{path}: CR byte")
        try:
            if path.endswith("items.level.json") or path.endswith("audioSFX.json"):
                for line in payload.decode("utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
            else:
                json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            problems.append(f"{path}: {error}")
    v15_slots = {
        "baseColorMap",
        "normalMap",
        "roughnessMap",
        "ambientOcclusionMap",
        "opacityMap",
        "emissiveMap",
        "metallicMap",
        "detailMap",
        "detailNormalMap",
    }
    v10_only = {"colorMap", "specularMap", "bumpMap"}
    for document in (hs.rock_materials_document(), hs.decal_materials_document()):
        for name, material in document.items():
            stage = material["Stages"][0]
            slots = {k for k in stage if k.endswith("Map")}
            if slots & v10_only:
                problems.append(f"{name}: v1.0 slots {sorted(slots & v10_only)} on version 1.5")
            if not slots & v15_slots:
                problems.append(f"{name}: no v1.5 map slot bound")
            if material.get("version") != 1.5:
                problems.append(f"{name}: version {material.get('version')} with PBR slots")
    ids = []
    for record_set in (
        hs.stone_records(),
        hs.crust_records(),
        hs.emitter_records(),
        hs.light_records(),
        hs.audio_records(),
    ):
        ids.extend(str(r["persistentId"]) for r in record_set)
    if len(set(ids)) != len(ids):
        problems.append("duplicate persistentId among the hearth records")
    for value in ids:
        if len(value) != 36 or value[14] != "5":
            problems.append(f"{value} is not a uuid5")
    return {"files": len(outputs), "persistent_ids": len(ids), "problems": problems}


def all_gates() -> dict[str, Any]:
    return {
        "census": hb.census(),
        "clearance": gate_clearance(),
        "fire_sites": gate_fire_sites(),
        "z": gate_z(),
        "names": gate_names(),
        "datablocks": gate_datablock_resolution(),
        "json": gate_json(),
        "bulk": hb.verify(),
    }


def write(root: Path = LEVEL_ROOT, *, check_only: bool = False) -> dict[str, Any]:
    outputs = hb.rendered_outputs()
    written: list[str] = []
    stale: list[str] = []
    for relative, payload in sorted(outputs.items()):
        target = root / relative
        if target.is_file() and target.read_bytes() == payload:
            continue
        if check_only:
            stale.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written.append(relative)
    groups = merge_groups(root, check_only=check_only)
    decals = merge_decals(root, check_only=check_only)
    handoff = hb.obstacle_handoff()
    payload = hb._json(handoff)
    if not check_only:
        hb.OBSTACLES_HANDOFF.parent.mkdir(parents=True, exist_ok=True)
        hb.OBSTACLES_HANDOFF.write_bytes(payload)
    return {
        "written": written,
        "stale": stale,
        "groups": groups,
        "decals": decals,
        "obstacles": {"rows": len(handoff["rows"]), "owners": handoff["owners"]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=LEVEL_ROOT)
    parser.add_argument("--gates", type=Path, default=None, help="write every gate reading here")
    arguments = parser.parse_args(argv)
    result = write(arguments.root, check_only=arguments.check)
    gates = all_gates()
    if arguments.gates is not None:
        arguments.gates.parent.mkdir(parents=True, exist_ok=True)
        arguments.gates.write_text(
            json.dumps(gates, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    summary = {
        "written": len(result["written"]),
        "stale": result["stale"],
        "groups_added": result["groups"]["added"],
        "decal_rows": result["decals"]["rows"],
        "obstacles": result["obstacles"],
        "census": gates["census"],
        "min_inner_face_r": gates["clearance"]["min_inner_face_r"],
        "lane_min_m": gates["clearance"]["lane_min"],
        "fire_min_stone_face_m": gates["fire_sites"]["min_stone_face_m"],
        "z_non_static_min_delta": gates["z"]["non_static_min_delta"],
        "z_static_offset_max_error": gates["z"]["static_offset_max_error"],
        "name_collisions": gates["names"]["collisions_with_the_tree"],
        "unnamespaced": gates["names"]["unnamespaced"],
        "datablock_problems": gates["datablocks"]["problems"],
        "json_problems": gates["json"]["problems"],
        "bulk": gates["bulk"],
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    bad = (
        summary["stale"]
        or summary["name_collisions"]
        or summary["unnamespaced"]
        or summary["datablock_problems"]
        or summary["json_problems"]
        or gates["bulk"]["missing"]
        or gates["bulk"]["stale"]
    )
    return 1 if (arguments.check and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())

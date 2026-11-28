"""B2's hearth as level-tree outputs: what is rendered, what is allowlisted, what is merged.

Shaped exactly like B3's ``forest_build`` so ``level_writer`` can adopt it with a
three-line hook (see ``report_B2.md``); until it does, ``place_hearth`` writes the
same bytes into the tree directly and ``cut_b2_zip`` cuts B2's own verification zip.

Three classes of output, and the split is deliberate:

* **rendered** -- the three group JSONLs, the two shape/decal ``*.materials.json``,
  the four ``*.datablocks.json`` and the audio-forest meta.  Small pure functions of
  ``hearth_spec``, so a gate can byte-compare them on every release.
* **merged** -- ``main.decals.json`` and ``main/MissionGroup/items.level.json`` are
  SHARED with B1 (and, for the decals, with B4).  ``place_hearth`` reads what is
  there, replaces only B2's own keys/rows and writes back, so a parallel round's
  work is never clobbered.
* **bulk** -- the seven DAEs and the 33 cooked maps, allowlisted from the two
  authoring manifests and verified against their sha256s.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from examples.hot_potato_arena.level import hearth_spec as hs
from examples.hot_potato_arena.level import hearth_textures as ht  # noqa: F401

#: ``ht`` is imported and re-exported so a gate can reach the cook's provenance
#: list (``ht.OVERLAY_SOURCES``) through this module rather than importing twice.
AUTHORING = hs.AUTHORING
SHAPES_MANIFEST = AUTHORING / f"{hs.LEVEL_ID}_hearth_shapes.json"
TEXTURES_MANIFEST = AUTHORING / f"{hs.LEVEL_ID}_hearth_textures.json"
OBSTACLES_HANDOFF = AUTHORING / f"{hs.LEVEL_ID}_level_obstacles.json"
LEVEL_ROOT = hs.EXAMPLE_ROOT / "mod" / "levels" / hs.LEVEL_ID

#: shared files B2 MERGES into rather than owns
DECALS_MEMBER = "main.decals.json"
GROUPS_MEMBER = "main/MissionGroup/items.level.json"


class HearthBuildError(RuntimeError):
    """A B2 manifest is missing or disagrees with the tree."""


def available() -> bool:
    return SHAPES_MANIFEST.is_file() and TEXTURES_MANIFEST.is_file()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise HearthBuildError(f"missing B2 manifest {path}; re-run the hearth build scripts")
    return json.loads(path.read_text(encoding="utf-8"))


def shapes_manifest() -> dict[str, Any]:
    return _load(SHAPES_MANIFEST)


def textures_manifest() -> dict[str, Any]:
    return _load(TEXTURES_MANIFEST)


def crust_uv_axes(level_root: Path = LEVEL_ROOT) -> dict[str, Any]:
    """Read the SHIPPED crust DAE and prove which UV axis carries the radius.

    r3's whole crust cook rests on one claim -- "column x of the map is a fixed radius"
    -- and if the exporter ever swapped u and v, the bank profile would run tangentially
    and paint a bright stripe every 15 degrees.  That is not a defect anyone would catch
    in a manifest, so it is read out of the exported bytes: world radius per vertex from
    the positions (plus the plate's own centroid offset), u and v per vertex from the
    texcoords, and the Pearson correlation of each against the radius.
    """

    import re

    path = level_root / hs.SHAPE_DIR / f"{hs.crust_stem()}.dae"
    text = path.read_text(encoding="utf-8")

    def array(name: str) -> list[float]:
        match = re.search(rf'id="[^"]*{name}-array"[^>]*>([^<]*)<', text)
        if not match:
            raise ValueError(f"{path.name}: no {name} array")
        return [float(v) for v in match.group(1).split()]

    positions = array("mesh-positions")
    texcoords = array("mesh-map-0")
    offsets = {s: int(o) for s, o in re.findall(r'semantic="(\w+)"[^>]*offset="(\d+)"', text)}
    stride = max(offsets.values()) + 1
    indices = [int(v) for v in re.search(r"<p>([^<]*)</p>", text).group(1).split()]
    cx, cy = hs.bearing_point(0.0, hs.CRUST_R_MID)
    radii, us, vs = [], [], []
    for start in range(0, len(indices), stride):
        vertex = indices[start + offsets["VERTEX"]]
        uv = indices[start + offsets["TEXCOORD"]]
        wx = positions[vertex * 3] + cx
        wy = positions[vertex * 3 + 1] + cy
        radii.append(((wx - hs.C[0]) ** 2 + (wy - hs.C[1]) ** 2) ** 0.5)
        us.append(texcoords[uv * 2])
        vs.append(texcoords[uv * 2 + 1])

    def correlation(a: list[float], b: list[float]) -> float:
        n = len(a)
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
        da = sum((x - ma) ** 2 for x in a) ** 0.5
        db = sum((y - mb) ** 2 for y in b) ** 0.5
        return round(num / da / db, 6) if da and db else 0.0

    return {
        "r": [round(min(radii), 4), round(max(radii), 4)],
        "u": [round(min(us), 4), round(max(us), 4)],
        "v": [round(min(vs), 4), round(max(vs), 4)],
        "corr_u_r": correlation(us, radii),
        "corr_v_r": correlation(vs, radii),
        "corners": len(radii),
    }


def dae_members() -> tuple[str, ...]:
    manifest = shapes_manifest()
    rows = list(manifest["stones"].values()) + ([manifest["crust"]] if manifest["crust"] else [])
    return tuple(sorted(str(row["relative"]) for row in rows))


def texture_members() -> tuple[str, ...]:
    return tuple(sorted(textures_manifest()["files"]))


# --- r6: the thin-shell gate, in the frame a car meets ---------------------------------
#: The bars the hearth's collider gate is held to.  ``ratio_min`` and ``parity_max`` are
#: the law adopted in ``level_facts`` 2026-09-07 (critic B2 pass 5) and used verbatim by
#: B3's rock gate and B4's ``G-B4-17``.  The three phantom ceilings are the law's "a
#: published phantom-gap statistic with its threshold set from the five solid stones",
#: made concrete: they are the WORST reading of each statistic over the five stones the
#: critic ruled solid, measured on the r5 SHIPPED bytes in this same world frame
#: (``b2/r6/stone_gate_BEFORE_r5_bytes.json``: ``boulder_01`` sets p50 0.5786 and p90
#: 1.5431, ``namaqualand_boulder_02`` sets max 1.7562, each rounded UP at the third
#: decimal).  A stone may not stand prouder of its own surface than the worst of the
#: class it joins did before the fix.
STONE_COLLIDER_BARS: dict[str, float] = {
    "ratio_min": 0.5,
    "parity_max": 0.30,
    "phantom_p50_m": 0.579,
    "phantom_p90_m": 1.544,
    "phantom_max_m": 1.757,
}


def stone_world_scale() -> dict[str, float]:
    """``asset -> footprint diameter in metres``, from the frozen layout."""

    out: dict[str, float] = {}
    for row in hs.layout()["stones"]:
        out.setdefault(str(row["asset"]), float(row["diam"]))
    return out


def stone_collider_report(asset: str, level_root: Path = LEVEL_ROOT) -> dict[str, Any]:
    """``collider_probe``'s car band on one stone source, cast in the WORLD frame.

    The instrument is B4's and is reused, not reimplemented -- ``signed_volume``,
    ``car_band_rays`` and ``gap_statistics`` are called here exactly as
    ``collider_probe.probe_dae`` calls them.  What this adds is the frame.
    ``blender_hearth.normalise_horizontal`` authors every stone at a 1.0
    longest-horizontal-axis UNIT size and the planter's TSStatic ``scale`` IS the
    design's footprint diameter, so the bytes on disk are a unit shape; but
    ``collider_probe.CAR_BAND_HEIGHTS_M`` (0.30-1.50 m: bumper, sill, bonnet, roof) are
    absolute METRES.  Probing the ``.dae`` as it lies casts the car band 10-22 m up a
    26 m stone and measures nothing a player can touch.  So the geometry is scaled by
    the design diameter first, and only then handed to the instrument.
    """

    from examples.hot_potato_arena.level import collider_probe, mesh_audit

    scale = stone_world_scale()[asset]
    path = level_root / hs.SHAPE_DIR / f"{hs.stone_stem(asset)}.dae"
    geoms = mesh_audit.geometries(path.read_bytes())
    collider_name = next((g for g in geoms if g.startswith("Colmesh_")), None)
    if collider_name is None:
        return {"asset": asset, "file": path.name, "has_colmesh": False}
    col_verts, col_faces = collider_probe._arrays(*geoms[collider_name])
    col_verts = col_verts * scale
    col_volume = collider_probe.signed_volume(col_verts, col_faces)
    origins, directions, band = collider_probe.car_band_rays(col_verts)
    finest = max((g for g in geoms if g != collider_name), key=lambda g: len(geoms[g][1]))
    details: dict[str, Any] = {}
    for gid, (positions, tris) in geoms.items():
        if gid == collider_name:
            continue
        verts, faces = collider_probe._arrays(positions, tris)
        verts = verts * scale
        volume = collider_probe.signed_volume(verts, faces)
        details[gid] = {
            "tris": len(faces),
            "visual_volume_m3": round(volume, 3),
            "volume_ratio_visual_over_colmesh": round(volume / col_volume, 4)
            if col_volume
            else None,
            "car_band": collider_probe.gap_statistics(
                origins, directions, (verts, faces), (col_verts, col_faces)
            ),
        }
    ratios = [d["volume_ratio_visual_over_colmesh"] for d in details.values()]
    return {
        "asset": asset,
        "file": path.name,
        "world_scale_m": scale,
        "has_colmesh": True,
        "colmesh": collider_name,
        "colmesh_tris": len(col_faces),
        "colmesh_volume_m3": round(col_volume, 3),
        "finest_detail": finest,
        "car_band_setup": band,
        "details": details,
        "volume_ratio_min": round(min(ratios), 4),
        "volume_ratio_max": round(max(ratios), 4),
        "lod_parity_ratio_spread": round(max(ratios) - min(ratios), 4),
    }


def stone_collider_problems(row: dict[str, Any]) -> list[str]:
    """Which of :data:`STONE_COLLIDER_BARS` one stone's report fails, in words."""

    bars = STONE_COLLIDER_BARS
    if not row.get("has_colmesh"):
        return ["no Colmesh"]
    problems: list[str] = []
    if row["volume_ratio_min"] < bars["ratio_min"]:
        problems.append(f"volume ratio {row['volume_ratio_min']:.4f} < {bars['ratio_min']}")
    if row["lod_parity_ratio_spread"] > bars["parity_max"]:
        problems.append(f"LOD parity {row['lod_parity_ratio_spread']:.4f} > {bars['parity_max']}")
    finest = row["details"][row["finest_detail"]]["car_band"]
    for key in ("phantom_p50_m", "phantom_p90_m", "phantom_max_m"):
        value = finest.get(key) or 0.0
        if value > bars[key]:
            problems.append(f"{key} {value:.4f} > {bars[key]}")
    return problems


#: **The husk gate** (``level_facts`` 2026-09-09, the CORRECTION entry; critic B2 pass 6).
#:
#: The collider gate above catches PHANTOM WALLS -- collision where nothing is drawn.  It
#: says nothing about whether the body is a boulder or a husk: a wafer whose collision mesh
#: hugs the wafer scores ~1.0 and passes.  The user's video found exactly that failure in
#: the level's rocks, and the discriminator is PCA on the vertex cloud:
#:
#:     flatness = e3/e1   blade = e2/e1   fill = V / (e1 e2 e3)   solidity = V / V(hull)
#:
#: The orchestrator's first bar -- ``fill >= 0.30 AND solidity >= 0.65`` -- is **WITHDRAWN**
#: and is not implemented here.  Critic B2 pass 6 calibrated the two statistics against
#: solids whose answer is known and it fails **4 of the 13 stock BeamNG rocks it was
#: calibrated on**, including ``GridMap__gm_rock_03`` (0.279 / 0.785), an entirely
#: respectable stock rock.  The reason:
#:
#: * **a sphere caps fill at 0.523**, and an ellipsoid of ANY aspect reads the same 0.522,
#:   so FILL measures "how boxy", not "how hollow" -- a tapered clast legitimately reads
#:   0.27 while being 87 % of its own hull;
#: * **any convex body reads solidity 1.000**, and solidity falls only when material is
#:   missing between the surface and the hull.  That is precisely "hollow rind / radiating
#:   sheets": a synthetic spiky husk reads 0.316.
#:
#: **Solidity is the husk statistic; fill is a shape statistic.**  The replacement rule,
#: adopted in ``level_facts`` on 2026-09-09 and implemented below, clears 6 of 6 hearth
#: stones, clears 10 of 13 stock, and fails exactly the seven forest shapes the user's video
#: identified.  Both gates are required and they answer different questions.
STONE_HUSK_BARS: dict[str, float] = {
    #: below every one of the 13 stock rocks measured (stock's own minimum is 0.540)
    "solidity_hard_min": 0.54,
    #: ...and the husk SIGNATURE: not-solid AND not-boxy together
    "solidity_signature_max": 0.67,
    "fill_signature_max": 0.28,
}


def husk_statistics(positions: list[Any], tris: list[Any]) -> dict[str, float]:
    """``flatness / blade / fill / solidity`` for one mesh, in the probe's own definitions.

    Copied from ``geometry_audit/flatness_probe.audit`` so the shipped gate does not reach
    outside the repository for the instrument that decides it.  PCA first, because a
    diagonal blade hides behind an axis-aligned bounding box.
    """

    import numpy as np
    from scipy.spatial import ConvexHull

    points = np.asarray(positions, dtype=float)
    faces = np.asarray(tris, dtype=int)
    centred = points - points.mean(axis=0)
    _, _, vh = np.linalg.svd(centred, full_matrices=False)
    local = centred @ vh.T
    e1, e2, e3 = (float(x) for x in np.sort(local.max(axis=0) - local.min(axis=0))[::-1])
    volume = 0.0
    if len(faces):
        a, b, c = points[faces[:, 0]], points[faces[:, 1]], points[faces[:, 2]]
        volume = float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
    box = e1 * e2 * e3
    return {
        "tris": len(faces),
        "flatness_e3_e1": round(e3 / e1 if e1 else 0.0, 4),
        "blade_e2_e1": round(e2 / e1 if e1 else 0.0, 4),
        "fill_V_over_box": round(volume / box if box > 0 else 0.0, 4),
        "solidity_V_over_hull": round(volume / float(ConvexHull(points).volume), 4),
    }


def stone_husk_report(asset: str, level_root: Path = LEVEL_ROOT) -> dict[str, Any]:
    """The husk statistics of one stone at its FINEST VISUAL LOD, from the shipped DAE."""

    from examples.hot_potato_arena.level import mesh_audit

    path = level_root / hs.SHAPE_DIR / f"{hs.stone_stem(asset)}.dae"
    geoms = mesh_audit.geometries(path.read_bytes())
    visual = {gid: mesh for gid, mesh in geoms.items() if not gid.startswith("Colmesh_")}
    if not visual:
        raise HearthBuildError(f"{asset}: no visual mesh in {path.name}")
    finest = max(visual, key=lambda gid: len(visual[gid][1]))
    row = husk_statistics(*visual[finest])
    row["asset"] = asset
    row["mesh"] = finest
    return row


def stone_husk_problems(row: dict[str, Any]) -> list[str]:
    """Which of :data:`STONE_HUSK_BARS` one stone fails, in words."""

    bars = STONE_HUSK_BARS
    solidity = float(row["solidity_V_over_hull"])
    fill = float(row["fill_V_over_box"])
    problems: list[str] = []
    if solidity < bars["solidity_hard_min"]:
        problems.append(
            f"solidity {solidity:.4f} < {bars['solidity_hard_min']} -- below every stock rock"
        )
    elif solidity < bars["solidity_signature_max"] and fill < bars["fill_signature_max"]:
        problems.append(
            f"husk signature: solidity {solidity:.4f} < {bars['solidity_signature_max']} "
            f"AND fill {fill:.4f} < {bars['fill_signature_max']}"
        )
    return problems


#: What the ENGINE bakes for B2's shapes and B2 harvests back out of ``temp/``:
#: one ``.cdae`` per DAE (QB-8, a ``stock`` item design section 13 says the level
#: MEETS) and, for the six rocks, the ``bb_autobillboard25`` atlas pair.  r1 generated
#: all nineteen and deleted them unread with the rest of the profile footprint, so
#: QB-8 read ``cdae_cov 0.125`` and the ``BB::`` recipe the report claimed was never
#: confirmed on B2's own shapes.  The live gate now copies them out BEFORE the purge
#: (``tests/test_hot_potato_hearth_live.py``), ``b2/r2/stage_harvest.py`` stages them
#: into the tree against their source DAE's sha256, and they ship.
HARVEST_MANIFEST = AUTHORING / f"{hs.LEVEL_ID}_hearth_harvest.json"
HARVEST_SUFFIXES = (".cdae", ".dae.imposter.dds", ".dae.imposter_normals.dds")


def harvest_manifest() -> dict[str, Any]:
    return _load(HARVEST_MANIFEST) if HARVEST_MANIFEST.is_file() else {"files": {}}


def harvest_members(level_root: Path = LEVEL_ROOT) -> tuple[str, ...]:
    """The harvested artefacts that are actually staged in the tree right now.

    Shaped like ``forest_build.imposter_members``: a member only ships when the file
    is there, so a tree without a harvest still builds -- it just fails QB-8.
    """

    out: list[str] = []
    for relative in dae_members():
        stem = relative.removesuffix(".dae")
        for suffix in HARVEST_SUFFIXES:
            candidate = (stem + suffix) if suffix != ".cdae" else (stem + ".cdae")
            if (level_root / candidate).is_file():
                out.append(candidate)
    return tuple(sorted(set(out)))


def bulk_members() -> tuple[str, ...]:
    return tuple(sorted({*dae_members(), *texture_members(), *harvest_members()}))


def _json(value: Any) -> bytes:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if "NaN" in text or "Infinity" in text:
        raise HearthBuildError("non-finite number in a generated hearth document")
    return text.encode("utf-8")


def _jsonl(records: list[dict[str, Any]]) -> bytes:
    lines = []
    for record in records:
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if "NaN" in line or "Infinity" in line:
            raise HearthBuildError("non-finite number in a generated hearth record")
        lines.append(line + "\n")
    return "".join(lines).encode("utf-8")


def audio_forest_document() -> list[dict[str, Any]]:
    """``dynamicAudioEmitters/forestData.audioSFX.json``: the meta row + one row per tree.

    The tree list is B3's shipped ``managedItemData.json`` -- B2 reads it, it never
    writes it.  ``audioForest.lua`` builds the nodes at runtime from the shapes with
    ``include 1``.
    """

    rows: list[dict[str, Any]] = [dict(hs.AUDIO_FOREST_META)]
    managed = LEVEL_ROOT / "art" / "forest" / "managedItemData.json"
    shapes: set[str] = set()
    if managed.is_file():
        for item in json.loads(managed.read_text(encoding="utf-8")).values():
            shape = item.get("shapeFile")
            if isinstance(shape, str) and shape.endswith(".dae") and "/trees/" in shape:
                shapes.add(shape)
    for shape in sorted(shapes):
        rows.append({"type": "shape", "shape": shape, "include": 1})
    return rows


def rendered_outputs() -> dict[str, bytes]:
    """Every hearth SCENE file as bytes keyed by path relative to the level root."""

    particle_files = hs.particle_datablock_files()
    sfx_relative, sfx_document = hs.sfx_datablock_file()
    decal_relative, decal_document = hs.decal_datablock_file()
    outputs: dict[str, bytes] = {
        f"main/MissionGroup/{hs.GROUP_HEARTH}/items.level.json": _jsonl(
            hs.stone_records() + hs.crust_records() + hs.emitter_records()
        ),
        f"main/MissionGroup/{hs.GROUP_NIGHT}/items.level.json": _jsonl(hs.light_records()),
        f"main/MissionGroup/{hs.GROUP_AUDIO}/items.level.json": _jsonl(hs.audio_records()),
        f"{hs.SHAPE_DIR}/{hs.LEVEL_ID}_hearth.materials.json": _json(hs.rock_materials_document()),
        f"{hs.DECAL_DIR}/main.materials.json": _json(hs.decal_materials_document()),
        sfx_relative: _json(sfx_document),
        decal_relative: _json(decal_document),
        f"{hs.AUDIO_DIR}/forestData.audioSFX.json": _jsonl(audio_forest_document()),
    }
    for relative, document in particle_files.items():
        outputs[relative] = _json(document)
    for path, payload in outputs.items():
        if b"\r" in payload:
            raise HearthBuildError(f"CR byte in a generated release text member: {path}")
    return outputs


def decal_instances() -> dict[str, list[list[float]]]:
    from examples.hot_potato_arena.level import terrain_model as tm

    return hs.decal_rows(tm.z_at)


def obstacle_handoff() -> dict[str, Any]:
    """The ``level_obstacles`` rows B5 registers, with B2's own 28 marked PROVEN."""

    rows = hs.obstacle_rows()
    return {
        "level_id": hs.LEVEL_ID,
        "source": "design v4 §7.3 R9 (layout.registry_rows)",
        "runtime_contract": {
            "call": "hotPotatoRegisterObstacles",
            "fields": ["x", "y", "r", "rp"],
            "r_range": [0.5, 30.0],
            "rp_rule": "rp <= r",
            "cap_now": 64,
            "cap_needed": 128,
            "arena_rows": 46,
            "level_rows": len(rows),
            "total": 46 + len(rows),
            "note": (
                "a call REPLACES the set and a 65th entry refuses the WHOLE list, so 46 + 67 "
                "needs runtime ask #8 (OBSTACLE_CAP 64 -> 128); the 18-row fallback is "
                "layout.registry_fallback and is carried below for B5 to choose."
            ),
        },
        "rows": rows,
        "fallback_rows": [
            {**row, "owner": "B2" if row["name"].endswith(tuple("0123456789")) else "B4"}
            for row in hs.layout()["registry_fallback"]
        ],
        "owners": {
            "B2": sum(1 for row in rows if row["owner"] == "B2"),
            "B4": sum(1 for row in rows if row["owner"] == "B4"),
        },
    }


def verify(level_root: Path = LEVEL_ROOT) -> dict[str, list[str]]:
    """Which allowlisted bulk members are missing or no longer match their manifest."""

    missing: list[str] = []
    stale: list[str] = []
    shapes = shapes_manifest()
    rows = list(shapes["stones"].values()) + ([shapes["crust"]] if shapes["crust"] else [])
    for row in rows:
        target = level_root / str(row["relative"])
        if not target.is_file():
            missing.append(str(row["relative"]))
        elif hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
            stale.append(str(row["relative"]))
    for relative, info in textures_manifest()["files"].items():
        target = level_root / relative
        if not target.is_file():
            missing.append(relative)
        elif hashlib.sha256(target.read_bytes()).hexdigest() != info["sha256"]:
            stale.append(relative)
    harvest = harvest_manifest()["files"]
    for relative, info in harvest.items():
        target = level_root / relative
        if not target.is_file():
            missing.append(relative)
        elif hashlib.sha256(target.read_bytes()).hexdigest() != info["sha256"]:
            stale.append(relative)
    # a harvest is a bake of a SHAPE: if the DAE moved, the bake is stale even though
    # its own bytes still hash (B3's law, level_facts "an atlas can bake blank and
    # staleness is invisible to close-range gates")
    shape_hash = {str(row["relative"]): str(row["sha256"]) for row in rows}
    for relative, info in harvest.items():
        source = str(info.get("source_dae", ""))
        if source in shape_hash and shape_hash[source] != info.get("source_sha256"):
            stale.append(relative)
    return {"missing": sorted(missing), "stale": sorted(set(stale))}


def census() -> dict[str, Any]:
    """Everything a gate or the report wants to count, in one place."""

    shapes = shapes_manifest() if SHAPES_MANIFEST.is_file() else {"stones": {}, "crust": None}
    textures = textures_manifest() if TEXTURES_MANIFEST.is_file() else {"files": {}}
    rows = decal_instances()
    names = [
        *(r["name"] for r in hs.stone_records()),
        *(r["name"] for r in hs.crust_records()),
        *(r["name"] for r in hs.emitter_records()),
        *(r["name"] for r in hs.light_records()),
        *(r["name"] for r in hs.audio_records()),
        *hs.rock_materials_document(),
        *hs.decal_materials_document(),
        *hs.decal_datablock_file()[1],
        *hs.sfx_datablock_file()[1],
        *(n for doc in hs.particle_datablock_files().values() for n in doc),
        *(g["name"] for g in hs.group_records()),
    ]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    return {
        "stones": len(hs.stone_records()),
        "crust_plates": len(hs.crust_records()),
        "emitter_nodes": len(hs.emitter_records()),
        "lights": len(hs.light_records()),
        "lights_shadowed": sum(1 for r in hs.light_records() if r["castShadows"]),
        "sfx_emitters": sum(1 for r in hs.audio_records() if r["class"] == "SFXEmitter"),
        "sfx_spaces": sum(1 for r in hs.audio_records() if r["class"] == "SFXSpace"),
        "materials": len(hs.rock_materials_document()) + len(hs.decal_materials_document()),
        "datablocks": {
            "particle": sum(len(d) for d in hs.particle_datablock_files().values()),
            "sfx": len(hs.sfx_datablock_file()[1]),
            "decal": len(hs.decal_datablock_file()[1]),
        },
        "decals": {
            **hs.decal_census(),
            "written_rows": sum(len(v) for v in rows.values()),
        },
        "shapes": len(shapes["stones"]) + (1 if shapes["crust"] else 0),
        "textures": len(textures["files"]),
        "texture_bytes": sum(int(v["bytes"]) for v in textures["files"].values()),
        "unique_names": len(set(names)),
        "duplicate_names": duplicates,
    }

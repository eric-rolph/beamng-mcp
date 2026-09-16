"""Shapes, their materials and the forest that places them: the level's placed objects.

Everything placed in a level (rocks from the lidar bumps, shrubs where the imagery
was green under a bump, the forest planted from the photographed cover) is a
``Forest`` item: one ``TSForestItemData`` per shape variant in
``art/forest/managedItemData.json`` and one line per instance in
``forest/<mod_id>.forest4.json``. Shapes are generated Collada files under
``art/shapes/<mod_id>/`` with their textures and a ``main.materials.json`` beside
them, so the mod carries every asset it references.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import foliage_textures as ft
from . import meshgen


def _yaw_matrix(yaw_deg: float) -> list[float]:
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    return [round(c, 6), round(s, 6), 0.0, round(-s, 6), round(c, 6), 0.0, 0.0, 0.0, 1.0]


def _tilted_matrix(yaw_deg: float, normal) -> list[float]:
    """The yaw matrix tilted so the item's up axis follows the ground normal."""

    n = np.asarray(normal, dtype="float64")
    n /= max(float(np.linalg.norm(n)), 1e-9)
    yaw = np.asarray(_yaw_matrix(yaw_deg)).reshape(3, 3)
    axis = np.cross([0.0, 0.0, 1.0], n)
    sin_a = float(np.linalg.norm(axis))
    if sin_a < 1e-6:
        return [round(float(v), 6) for v in yaw.ravel()]
    axis /= sin_a
    cos_a = float(np.clip(n[2], -1.0, 1.0))
    k = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])
    tilt = np.eye(3) + sin_a * k + (1.0 - cos_a) * (k @ k)
    return [round(float(v), 6) for v in (tilt @ yaw).ravel()]


def _bilinear(dem: np.ndarray, res: float, fp_size_m: float, x: float, y: float) -> float:
    from . import heightmap as hm

    return float(hm.sample_bilinear(dem, res, fp_size_m, x, y))


def _ground_normal(dem: np.ndarray, res: float, fp_size_m: float, x: float, y: float):
    """Unit normal of the terrain at level (x, y), from central differences."""

    n = dem.shape[0]
    col = int(min(max((x + fp_size_m / 2.0) / res, 1), n - 2))
    row = int(min(max((fp_size_m / 2.0 - y) / res, 1), n - 2))
    dzdx = float(dem[row, col + 1] - dem[row, col - 1]) / (2.0 * res)
    dzdy = float(dem[row - 1, col] - dem[row + 1, col]) / (2.0 * res)  # rows run south
    return (-dzdx, -dzdy, 1.0)


def _material(mod_id: str, name: str, tex_url: str, *, kind: str, pid) -> dict:
    stage = {
        "baseColorMap": f"{tex_url}/{name}_b.png",
        "normalMap": f"{tex_url}/{name}_nm.png",
    }
    entry = {
        "name": name,
        "class": "Material",
        "mapTo": name,
        "persistentId": pid(f"material:{name}"),
        "materialTag0": mod_id,
        "version": 1.5,
    }
    if kind == "cards":
        stage["roughnessFactor"] = 0.9
        entry.update(
            {
                "alphaTest": True,
                "alphaRef": 96,
                "doubleSided": True,
                "castShadows": True,
                "materialTag1": "Vegetation",
            }
        )
    else:
        stage["roughnessMap"] = f"{tex_url}/{name}_r.png"
        entry.update(
            {"castShadows": True, "materialTag1": "Rock" if kind == "rock" else "Vegetation"}
        )
    entry["Stages"] = [stage, {}, {}, {}]
    return entry


def build_shapes(
    spec,
    level_root: Path,
    level_url: str,
    pid,
    *,
    tree_species: set[str],
    rock_materials: set[str],
    shrub: bool | set[str],
    cover_colours: dict | None = None,
) -> dict:
    """Write DAEs + textures + materials. Returns a catalogue used by ``write_forest``."""

    mod_id = spec.MOD_ID
    shapes_dir = level_root / "art" / "shapes" / mod_id
    tex_dir = shapes_dir / "textures"
    shapes_url = f"{level_url}/art/shapes/{mod_id}"
    tex_url = f"{shapes_url}/textures"
    objects_spec = getattr(spec, "OBJECTS", {}) or {}
    seed_base = int(objects_spec.get("seed", 100))
    catalogue: dict = {"items": {}, "materials": {}, "shapes": []}
    materials_json: dict = {}

    def add_material(name: str, kind: str) -> str:
        full = f"{mod_id}_{name}"
        if full not in materials_json:
            materials_json[full] = _material(mod_id, full, tex_url, kind=kind, pid=pid)
        return full

    # --- rocks: several variants per material family, unit-normalised (longest axis 1 m)
    rock_variant_shapes = objects_spec.get("rock_variants", 8)
    rock_families = objects_spec.get(
        "rock_materials", {"rock_talus": {"colour": [0.46, 0.43, 0.40], "strata": 0.15}}
    )
    for family in sorted(rock_materials):
        params = rock_families.get(family, {"colour": [0.5, 0.47, 0.43], "strata": 0.2})
        ft.rock_set(
            tex_dir,
            f"{mod_id}_{family}",
            seed_base + hash(family) % 1000,
            colour=tuple(params["colour"]),
            strata=float(params.get("strata", 0.2)),
            lichen_cover=float(params.get("lichen", 0.3)),
        )
        mat = add_material(family, "rock")
        variants = []
        rng = np.random.default_rng(seed_base + 7)
        for v in range(rock_variant_shapes):
            # Aspect ratios spread from flat slabs to blocky boulders; scale is uniform
            # at placement so the variant is chosen by aspect.
            sx = 1.0
            sy = float(rng.uniform(0.55, 1.0))
            z_lo, z_hi = params.get("z_aspect", (0.4, 0.95))  # tabular bedded rock: 0.35-0.65
            sz = float(rng.uniform(float(z_lo), float(z_hi)))
            name = f"{family}_{v:02d}"
            meshes = meshgen.rock_meshes(
                seed_base + 31 * v + hash(family) % 97,
                (sx, sy, sz),
                subdivisions=2,
                angular=float(rng.uniform(0.7, 1.0)),
                material=mat,
                name=name,
            )
            summary = meshgen.write_dae(shapes_dir / f"{name}.dae", meshes, name)
            item = f"{mod_id}_{name}"
            catalogue["items"][item] = {
                "class": "TSForestItemData",
                "internalName": item,
                "shapeFile": f"{shapes_url}/{name}.dae",
                "collidable": True,
                "radius": 0.6,
                "mass": 500,
                "rigidity": 100,
                "windScale": 0,
                "trunkBendScale": 0,
                "branchAmp": 0,
                "detailAmp": 0,
                "detailFreq": 0,
                "snapRotationToTerrain": True,
            }
            variants.append(
                {"item": item, "aspect": [sx, sy, sz], "triangles": summary["triangles"]}
            )
            catalogue["shapes"].append(summary)
        catalogue.setdefault("rock_variants", {})[family] = variants

    # --- trees
    species_params = {
        "spruce": dict(kind="spruce", base_height=14.0, crown=4.6, colour=(0.10, 0.20, 0.12), n=4),
        "fir": dict(kind="fir", base_height=12.0, crown=5.0, colour=(0.12, 0.24, 0.13), n=3),
        "krummholz": dict(
            kind="krummholz", base_height=1.5, crown=3.6, colour=(0.14, 0.22, 0.12), n=3
        ),
        "sapling": dict(kind="sapling", base_height=2.5, crown=1.6, colour=(0.12, 0.22, 0.12), n=2),
        # A willow carr is a grey-green dome wider than tall, not a dark conifer mat.
        "willow": dict(kind="willow", base_height=1.5, crown=3.6, colour=(0.45, 0.50, 0.30), n=3),
        # Mid-August aspen is a medium green, not lime.
        "aspen": dict(base_height=10.0, crown=5.0, colour=(0.38, 0.47, 0.22), n=3),
        # Sucker clumps: a few slender stems in one bushy crown, the aspen card.
        "aspen_sapling": dict(base_height=3.0, crown=2.4, colour=(0.40, 0.49, 0.24), n=2),
    }
    cover_colours = cover_colours or {}
    for species in sorted(tree_species):
        params = dict(species_params[species])
        broad = species in ("aspen", "aspen_sapling", "willow")
        measured = cover_colours.get("broadleaf" if broad else "conifer")
        if measured:
            # Blend the authored card colour 60 % toward the photographed cover so the
            # crowns sit in the base colour instead of on it (a willow only 30 %: the
            # broadleaf cover the flight measured is the aspen's, darker than a carr).
            boost = 1.0
            share = 0.3 if species == "willow" else 0.6
            params["colour"] = tuple(
                round(a * (1.0 - share) + m * share * boost, 4)
                for a, m in zip(params["colour"], measured, strict=True)
            )
        is_aspen = species in ("aspen", "aspen_sapling")
        cards = f"{species}_cards"
        bark = "aspen_bark" if is_aspen else "conifer_bark"
        if is_aspen:
            ft.broadleaf_card(
                tex_dir,
                f"{mod_id}_{cards}",
                seed_base + 41 + (7 if species == "aspen_sapling" else 0),
                colour=params["colour"],
            )
            if f"{mod_id}_{bark}" not in materials_json:
                ft.bark_set(tex_dir, f"{mod_id}_{bark}", seed_base + 42, kind="aspen")
        else:
            ft.conifer_card(
                tex_dir,
                f"{mod_id}_{cards}",
                seed_base + 43 + hash(species) % 50,
                kind=params["kind"],
                colour=params["colour"],
            )
            if f"{mod_id}_{bark}" not in materials_json:
                ft.bark_set(tex_dir, f"{mod_id}_{bark}", seed_base + 44, kind="spruce")
            ft.conifer_tier_card(
                tex_dir,
                f"{mod_id}_{species}_tiers",
                seed_base + 47 + hash(species) % 50,
                kind=params["kind"],
                colour=params["colour"],
            )
        card_mat = add_material(cards, "cards")
        bark_mat = add_material(bark, "bark")
        tier_mat = add_material(f"{species}_tiers", "cards") if not is_aspen else None
        variants = []
        for v in range(params["n"]):
            name = f"{species}_{v:02d}"
            if is_aspen:
                meshes = meshgen.broadleaf_meshes(
                    seed_base + 100 + v + (50 if species == "aspen_sapling" else 0),
                    params["base_height"],
                    params["crown"],
                    card_material=card_mat,
                    bark_material=bark_mat,
                    name=name,
                    stems=3 if species == "aspen_sapling" else 1,
                )
            else:
                meshes = meshgen.conifer_meshes(
                    seed_base + 200 + v + hash(species) % 50,
                    params["base_height"],
                    params["crown"] * (1.0 + 0.12 * (v % 2)),
                    kind=params["kind"],
                    card_material=card_mat,
                    bark_material=bark_mat,
                    name=name,
                    tier_material=tier_mat,
                )
            summary = meshgen.write_dae(shapes_dir / f"{name}.dae", meshes, name)
            item = f"{mod_id}_{name}"
            catalogue["items"][item] = {
                "class": "TSForestItemData",
                "internalName": item,
                "shapeFile": f"{shapes_url}/{name}.dae",
                "collidable": True,
                "radius": 0.9 if species != "krummholz" else 0.6,
                "mass": 5,
                "rigidity": 10,
                "windScale": 0,
                "trunkBendScale": 0,
                "branchAmp": 0,
                "detailAmp": 0,
                "detailFreq": 0,
                "snapRotationToTerrain": False,
            }
            variants.append(
                {
                    "item": item,
                    "base_height": params["base_height"],
                    "triangles": summary["triangles"],
                }
            )
            catalogue["shapes"].append(summary)
        catalogue.setdefault("tree_variants", {})[species] = variants

    # --- shrubs: one card set and three mounds per family (juniper on the plain,
    # sage on the rim), chosen per placement by the layer under it.
    shrub_families = objects_spec.get("shrub_materials") or {
        "shrub": {"colour": objects_spec.get("shrub_colour", (0.18, 0.24, 0.12))}
    }
    wanted = shrub if isinstance(shrub, set) else (set(shrub_families) if shrub else set())
    for family in sorted(wanted & set(shrub_families)):
        params = shrub_families[family]
        ft.shrub_card(
            tex_dir,
            f"{mod_id}_{family}_cards",
            seed_base + 51 + hash(family) % 97,
            colour=tuple(params.get("colour", (0.18, 0.24, 0.12))),
            light_colour=tuple(params.get("light_colour", (0.30, 0.37, 0.19))),
        )
        card_mat = add_material(f"{family}_cards", "cards")
        height = float(params.get("height", 1.0))
        width = float(params.get("width", 1.3))
        variants = []
        for v in range(3):
            name = f"{family}_{v:02d}"
            meshes = meshgen.shrub_meshes(
                seed_base + 300 + v + hash(family) % 53,
                height,
                width + 0.2 * v,
                card_material=card_mat,
                name=name,
            )
            summary = meshgen.write_dae(shapes_dir / f"{name}.dae", meshes, name)
            item = f"{mod_id}_{name}"
            catalogue["items"][item] = {
                "class": "TSForestItemData",
                "internalName": item,
                "shapeFile": f"{shapes_url}/{name}.dae",
                "collidable": False,
                "radius": 0.5,
                "mass": 1,
                "rigidity": 5,
                "windScale": 0,
                "trunkBendScale": 0,
                "branchAmp": 0,
                "detailAmp": 0,
                "detailFreq": 0,
                "snapRotationToTerrain": True,
            }
            variants.append(
                {"item": item, "base_height": height, "triangles": summary["triangles"]}
            )
            catalogue["shapes"].append(summary)
        catalogue.setdefault("shrub_variants", {})[family] = variants

    from .level_builder import write_json

    write_json(shapes_dir / "main.materials.json", materials_json)
    catalogue["materials"] = sorted(materials_json)
    return catalogue


def write_forest(
    spec,
    level_root: Path,
    level_url: str,
    pid,
    catalogue: dict,
    *,
    placed_objects: list[dict],
    trees: list[dict],
    seed: int = 5,
    dem: np.ndarray | None = None,
    res: float = 1.0,
    fp_size_m: float = 0.0,
    min_elevation: float = 0.0,
) -> dict:
    """managedItemData.json + <mod_id>.forest4.json. Returns instance statistics.

    With ``dem`` the rocks are tilted onto the ground normal and sunk a little more
    on slopes, so a flat-based boulder on a 38 degree scree does not float its
    downhill lip; trees stay upright.
    """

    from .level_builder import write_json

    mod_id = spec.MOD_ID
    rng = np.random.default_rng(seed)
    lines: list[str] = []
    counts: dict[str, int] = {}
    triangles = 0
    tri_by_item = {}
    for group in ("rock_variants", "tree_variants"):
        for variants in catalogue.get(group, {}).values():
            for v in variants:
                tri_by_item[v["item"]] = v["triangles"]
    for variants in catalogue.get("shrub_variants", {}).values():
        for v in variants:
            tri_by_item[v["item"]] = v["triangles"]

    gap_max = (getattr(spec, "OBJECTS", None) or {}).get("rock_gap_max_m")
    gap_max = float(gap_max) if gap_max is not None else None

    def emit(
        item: str,
        x: float,
        y: float,
        z: float,
        yaw: float,
        scale: float,
        *,
        tilt: bool = False,
        footprint_m: float = 0.0,
        height_m: float = 0.0,
    ) -> bool:
        nonlocal triangles
        matrix = _yaw_matrix(yaw)
        if tilt and dem is not None:
            # The ground plane under the footprint (its mean height and the normal
            # of a plane through its edges): a block whose footprint drops more
            # across it than three tenths of its height is tilted onto that plane,
            # and every block seats a quarter of its height into the footprint's
            # mean ground, so the uphill edge is buried and the downhill edge sits
            # on the ground instead of in the air.
            n = dem.shape[0]
            half = fp_size_m / 2.0
            radius = max(1, round(footprint_m / 2.0 / res))
            row = int(min(max((half - y) / res, 0), n - 1))
            col = int(min(max((x + half) / res, 0), n - 1))
            patch = dem[
                max(0, row - radius) : row + radius + 1, max(0, col - radius) : col + radius + 1
            ]
            reach = max(footprint_m / 2.0, res)
            east = _bilinear(dem, res, fp_size_m, x + reach, y)
            west = _bilinear(dem, res, fp_size_m, x - reach, y)
            north = _bilinear(dem, res, fp_size_m, x, y + reach)
            south = _bilinear(dem, res, fp_size_m, x, y - reach)
            dzdx = (east - west) / (2.0 * reach)
            dzdy = (north - south) / (2.0 * reach)
            normal = (-dzdx, -dzdy, 1.0)
            slope = math.hypot(dzdx, dzdy)  # tan of the slope over the footprint
            drop = footprint_m * slope
            tilted = drop > 0.3 * max(height_m, 0.1) and slope > math.tan(math.radians(8.0))
            if tilted:
                matrix = _tilted_matrix(yaw, normal)
            centre = _bilinear(dem, res, fp_size_m, x, y)
            # The footprint's cells only: a stone under a cell wide is seated on its
            # own cell, not on the ground a metre either side of it.
            if radius * res > footprint_m / 2.0 + res / 2.0:
                patch = np.asarray([[centre]], dtype="float32")
            mean_ground = float(patch.mean()) if patch.size else centre
            # Never more than four tenths of its height under the ground at its
            # centre (a block on a lip would otherwise seat in the cliff below).
            seat = max(mean_ground - 0.25 * height_m, centre - 0.4 * max(height_m, 0.1))
            seat = min(seat, centre)
            z = seat - min_elevation
            # The base plane's height over the lowest ground under the footprint: a
            # tilted block's base follows the ground plane, so its downhill edge
            # sits half the footprint's drop lower than its centre.
            base_edge = seat - (0.5 * drop if tilted else 0.0)
            gap = base_edge - float(patch.min()) if patch.size else 0.0
            if gap_max is not None and gap > gap_max:
                # Seated down until the gap under the base plane is met, within
                # half its height of the ground at its centre; else not placed.
                extra = gap - gap_max
                if seat - extra >= centre - 0.5 * max(height_m, 0.1):
                    seat -= extra
                    z = seat - min_elevation
                    gap = gap_max
                else:
                    return False
            gaps.append(max(gap, 0.0))
        lines.append(
            json.dumps(
                {
                    "type": item,
                    "pos": [round(x, 3), round(y, 3), round(z, 3)],
                    "rotationMatrix": matrix,
                    "scale": round(scale, 4),
                },
                separators=(",", ":"),
            )
        )
        counts[item] = counts.get(item, 0) + 1
        triangles += tri_by_item.get(item, 0)
        return True

    gaps: list[float] = []
    for obj in placed_objects:
        if obj["kind"] == "rock":
            family = obj.get("material") or next(
                iter(catalogue.get("rock_variants", {"rock_talus": None}))
            )
            variants = catalogue.get("rock_variants", {}).get(family)
            if not variants:
                continue
            w, h, z_ext = obj["size"]
            longest = max(w, h)
            if obj.get("peak_m"):
                # A lidar bump has a measured footprint and height: the variant
                # nearest that shape.
                want = (1.0, min(w, h) / longest, z_ext / longest)
                best = min(
                    variants,
                    key=lambda v: (v["aspect"][1] - want[1]) ** 2 + (v["aspect"][2] - want[2]) ** 2,
                )
            else:
                # A scattered stone has no shape of its own (its triple is the
                # sampler's near-constant draw, which put 77 % of a level's stones
                # on one variant): every variant in turn.
                best = variants[int(rng.integers(0, len(variants)))]
            yaw = obj["yaw_deg"] if w >= h else obj["yaw_deg"] + 90.0
            # A forest item scales uniformly: the scale that puts the block's height
            # at the lidar's peak, reconciled with the one that fits its footprint.
            by_height = z_ext / max(float(best["aspect"][2]), 0.2)
            scale = math.sqrt(longest * by_height) if obj.get("peak_m") else longest
            emit(
                best["item"],
                obj["x"],
                obj["y"],
                obj["z"],
                yaw,
                scale,
                tilt=True,
                footprint_m=longest,
                height_m=z_ext,
            )
        elif obj["kind"] == "shrub" and catalogue.get("shrub_variants"):
            families = catalogue["shrub_variants"]
            variants = families.get(obj.get("material") or "") or next(iter(families.values()))
            v = variants[int(rng.integers(0, len(variants)))]
            scale = max(obj["size"][2], 0.6) / float(v.get("base_height", 1.0))
            emit(v["item"], obj["x"], obj["y"], obj["z"], obj["yaw_deg"], scale)
    for tree in trees:
        variants = catalogue.get("tree_variants", {}).get(tree["species"])
        if not variants:
            continue
        v = variants[int(rng.integers(0, len(variants)))]
        emit(
            v["item"],
            tree["x"],
            tree["y"],
            tree["z"],
            tree["yaw_deg"],
            max(0.2, tree["height_m"] / v["base_height"]),
        )
    forest_dir = level_root / "forest"
    forest_dir.mkdir(parents=True, exist_ok=True)
    forest_file = forest_dir / f"{mod_id}.forest4.json"
    forest_file.write_text(
        "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n"
    )
    write_json(level_root / "art" / "forest" / "managedItemData.json", catalogue["items"])
    gap_arr = np.asarray(gaps, dtype="float32") if gaps else np.zeros(0, dtype="float32")
    return {
        "instances": len(lines),
        "by_item": counts,
        "triangles_if_all_drawn": int(triangles),
        # Rock seating: the base plane's height over the lowest ground under the
        # footprint (0 where the whole footprint touches or is buried).
        "rock_gap_m": (
            {
                "p95": round(float(np.percentile(gap_arr, 95)), 2),
                "over_0_5_fraction": round(float((gap_arr > 0.5).mean()), 4),
                "max": round(float(gap_arr.max()), 2),
            }
            if gap_arr.size
            else None
        ),
        "file": f"{level_url}/forest/{forest_file.name}",
        "sha256": hashlib.sha256(forest_file.read_bytes()).hexdigest(),
    }


def forest_object(spec, level_url: str, pid) -> dict:
    return {
        "name": "theForest",
        "class": "Forest",
        "persistentId": pid("theForest"),
        "__parent": "forest",
        "position": [0, 0, 0],
        "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "scale": [1, 1, 1],
        "dataFile": f"{level_url}/forest/{spec.MOD_ID}.forest4.json",
        "lodReflectScalar": 2,
    }

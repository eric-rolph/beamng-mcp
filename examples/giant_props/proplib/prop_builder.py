"""Translate a Giant Props Blender handoff into BeamNG runtime files.

The Blender generator owns every coordinate. This builder only converts its
checked handoff into the mod tree and refuses stale or incomplete input,
following ``examples/cannon_car_wash/build_selector_prop.py``.

Per prop it writes, all under ``<example>/mod``:

- ``vehicles/<ns>/<ns>.jbeam`` — the measured cage (mixed fixed/free nodes,
  named beam specs, collision triangles, refnodes, one flexbody),
- ``vehicles/<ns>/main.materials.json`` — solid-colour PBR materials,
- ``vehicles/<ns>/info.json`` + ``standard.pc`` + ``info_standard.json``,
- ``vehicles/<ns>/lua/<ns>_vehicle.lua`` — the registration bootstrap,
- ``lua/ge/extensions/<ns>/runtime.lua`` — via :mod:`lua_kit`,
- thumbnails copied from the authored Blender render.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

from . import lua_kit

HANDOFF_SCHEMA = "ericrolph-giant-props-handoff-v1"
HARVEST_SCHEMA = "ericrolph-giant-props-harvest-v1"
AUTHOR = "Eric Rolph"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def ge_extension_name(mod_id: str) -> str:
    """BeamNG doubles literal underscores before replacing the separator."""

    return f"{mod_id}/runtime".replace("_", "__").replace("/", "_")


def camel(mod_id: str) -> str:
    return "".join(part.capitalize() for part in mod_id.split("_"))


def load_handoff(example_root: Path, mod_id: str) -> dict[str, Any]:
    handoff_path = example_root / "authoring" / f"{mod_id}.handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise ValueError(f"unsupported handoff schema in {handoff_path}")
    if handoff.get("asset", {}).get("id") != mod_id:
        raise ValueError("handoff asset id does not match the mod id")
    visual = handoff.get("visual", {})
    dae_path = example_root / "mod" / visual.get("path", "")
    if not dae_path.is_file():
        raise ValueError(f"handoff visual Collada is missing: {dae_path}")
    digest = hashlib.sha256(dae_path.read_bytes()).hexdigest()
    if visual.get("sha256") != digest or visual.get("size") != dae_path.stat().st_size:
        raise ValueError("visual Collada changed after Blender handoff extraction")
    for part in handoff.get("parts", []):
        part_path = example_root / "mod" / part["path"]
        if not part_path.is_file():
            raise ValueError(f"handoff part Collada is missing: {part_path}")
        part_digest = hashlib.sha256(part_path.read_bytes()).hexdigest()
        if part.get("sha256") != part_digest:
            raise ValueError(f"part Collada changed after handoff: {part['name']}")
    return handoff


def build_jbeam(
    mod_id: str, display_name: str, handoff: dict[str, Any]
) -> tuple[dict[str, Any], float]:
    nodes = handoff["nodes"]
    node_ids = {node["id"] for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("handoff contains duplicate node ids")
    base_ids = set(handoff["base_nodes"])
    spawn_ids = set(handoff["spawn_envelope_nodes"])
    if not base_ids <= node_ids or len(base_ids) < 3:
        raise ValueError("handoff base nodes are missing from the cage")
    if len(spawn_ids) != 8 or not spawn_ids <= node_ids:
        raise ValueError("handoff spawn envelope must contain eight cage nodes")
    group = f"{mod_id}_physics"

    node_rows: list[list[Any]] = [["id", "posX", "posY", "posZ"]]
    total_mass = 0.0
    for node in nodes:
        node_group = f"{mod_id}_{node['group']}" if node.get("group") else group
        options: dict[str, Any] = {
            "collision": bool(node["collision"]),
            "selfCollision": bool(node.get("self_collision", False)),
            "fixed": bool(node["fixed"]),
            "frictionCoef": node.get("friction", 0.9),
            "group": node_group,
            "nodeMaterial": node.get("node_material", "|NM_METAL"),
            "nodeWeight": node["weight"],
        }
        if node["collision"] and node["fixed"]:
            options["staticCollision"] = True
        options.update(node.get("extra", {}))
        total_mass += float(node["weight"])
        node_rows.append([node["id"], *node["position"], options])

    beam_specs = handoff["beam_specs"]
    beam_rows: list[list[Any]] = [["id1:", "id2:"]]
    for beam in handoff["beams"]:
        first, second = beam["nodes"]
        if first not in node_ids or second not in node_ids:
            raise ValueError(f"beam references unknown node: {first}, {second}")
        options = dict(beam_specs[beam["spec"]])
        # Per-beam overrides (breakGroup / finite breakStrength for glass).
        options.update(beam.get("extra", {}))
        beam_rows.append([first, second, dict(sorted(options.items()))])

    triangle_rows: list[list[Any]] = [["id1:", "id2:", "id3:"]]
    for triangle in handoff["triangles"]:
        triangle_nodes = triangle["nodes"]
        if len(set(triangle_nodes)) != 3 or not set(triangle_nodes) <= node_ids:
            raise ValueError(f"triangle references invalid nodes: {triangle_nodes}")
        triangle_options: dict[str, Any] = {"groundModel": triangle.get("ground_model", "metal")}
        triangle_options.update(triangle.get("extra", {}))
        triangle_rows.append([*triangle_nodes, dict(sorted(triangle_options.items()))])

    refnodes = handoff["refnodes"]
    if not set(refnodes.values()) <= node_ids:
        raise ValueError("reference nodes are missing from the cage")
    camera_distance = handoff.get("behavior", {}).get("camera_distance", 30.0)
    part = {
        "information": {"authors": AUTHOR, "name": display_name},
        "slotType": "main",
        "cameraExternal": {
            "distance": camera_distance,
            "distanceMin": 8.0,
            "fov": 65.0,
            "offset": {"x": 0.0, "y": 0.0, "z": 3.0},
        },
        "refNodes": [
            ["ref:", "back:", "left:", "up:"],
            [refnodes["ref"], refnodes["back"], refnodes["left"], refnodes["up"]],
        ],
        "flexbodies": [
            ["mesh", "[group]:"],
            [handoff["asset"]["visual_mesh"], [group]],
            *[
                [extra_flex["mesh"], [f"{mod_id}_{g}" for g in extra_flex["groups"]]]
                for extra_flex in handoff["asset"].get("flexbodies_extra", [])
            ],
        ],
        "nodes": node_rows,
        "beams": beam_rows,
        "triangles": triangle_rows,
    }
    rails = handoff.get("rails", {})
    if rails:
        part["rails"] = {
            name: {
                "links:": rail["links"],
                "broken:": [],
                "looped": bool(rail.get("looped", False)),
                "capped": bool(rail.get("capped", True)),
            }
            for name, rail in sorted(rails.items())
        }
    slidenodes = handoff.get("slidenodes", [])
    if slidenodes:
        part["slidenodes"] = [
            [
                "id:",
                "railName",
                "attached",
                "fixToRail",
                "tolerance",
                "spring",
                "strength",
                "capStrength",
            ],
            *[
                [
                    slide["node"],
                    slide["rail"],
                    slide["attached"],
                    slide["fix_to_rail"],
                    slide["tolerance"],
                    slide["spring"],
                    slide["strength"],
                    slide["cap_strength"],
                ]
                for slide in sorted(slidenodes, key=lambda item: (item["node"], item["rail"]))
            ],
        ]
    # Interactive panel buttons (cannon-wash recipe, AGENTS.md field
    # guide): triggers2 rows anchored to dedicated cage nodes with a
    # shared frame pair, each linked to an input action the interaction
    # json forwards to the GE runtime.
    panel = handoff.get("panel")
    if panel:
        frame_x = panel["frame_x_node"]
        frame_y = panel["frame_y_node"]
        if frame_x not in node_ids or frame_y not in node_ids:
            raise ValueError("panel frame nodes are missing from the cage")
        trigger_rows: list[list[Any]] = [
            [
                "id",
                "idRef:",
                "idX:",
                "idY:",
                "type",
                "size",
                "baseRotation",
                "rotation",
                "translation",
                "baseTranslation",
            ]
        ]
        link_rows: list[list[Any]] = [["triggerId:triggers2", "triggerInput", "inputAction"]]
        enabled_rows: list[list[Any]] = [["id"]]
        zero = {"x": 0, "y": 0, "z": 0}
        size = panel.get("button_size", 0.07)
        for button in panel["buttons"]:
            # Per-button box size when provided (centrifuge 2026-08-09e:
            # mushroom caps are twice the diameter of the small round
            # ones; a single panel-wide size fits neither).
            bsize = button.get("size", size)
            box = {"x": bsize, "y": bsize, "z": bsize}
            # CENTRE the box on the anchor (2026-08-09g, player
            # screenshots): the trigger box extends from its origin
            # corner, so a zero baseTranslation parked every hitbox
            # half-a-box up-right of its cap - the offset grew with the
            # box size, which is why the big mushrooms looked worst.
            half = round(-bsize / 2.0, 4)
            centred = {"x": half, "y": half, "z": half}
            anchor = button["node"]
            if anchor not in node_ids:
                raise ValueError(f"panel button anchor missing from cage: {anchor}")
            trigger_id = f"panel_{button['id']}"
            # Per-button frames when provided (round 15): the box basis is
            # (idX - idRef, idY - idRef), so one SHARED frame pair skews
            # and translates the hitbox of every button not co-located
            # with it - the player's hover ghost floated half a cap away.
            bfx = button.get("frame_x_node", frame_x)
            bfy = button.get("frame_y_node", frame_y)
            if bfx not in node_ids or bfy not in node_ids:
                raise ValueError(f"panel button frame missing from cage: {trigger_id}")
            trigger_rows.append(
                [trigger_id, anchor, bfx, bfy, "box", box, zero, zero,
                 zero, centred]
            )
            link_rows.append([trigger_id, "action0", f"{mod_id}_{button['id']}"])
            enabled_rows.append([trigger_id])
        part["triggers2"] = trigger_rows
        part["triggerEventLinks2"] = link_rows
        part["actionsEnabled"] = enabled_rows
    return {mod_id: part}, total_mass


def build_interaction_json(mod_id: str, handoff: dict[str, Any]) -> dict[str, Any] | None:
    """Input-action map: onDown forwards each press to the GE runtime.

    ASCII titles only — BeamNG's tooltip renderer prints unicode escapes
    literally (cannon-wash v1.48 lesson).
    """

    panel = handoff.get("panel")
    if not panel:
        return None
    extension = ge_extension_name(mod_id)
    actions: dict[str, Any] = {}
    for order, button in enumerate(panel["buttons"], start=1):
        title = button["title"]
        if any(ord(ch) > 126 for ch in title):
            raise ValueError(f"panel title must be ASCII: {title!r}")
        actions[f"{mod_id}_{button['id']}"] = {
            "onDown": (
                'obj:queueGameEngineLua(string.format("extensions.'
                + extension
                + ".pressPanelButtonByVehicle(%d, '"
                + button["id"]
                + "')\", objectId))"
            ),
            "order": float(order),
            "title": title,
        }
    return {"actions": actions, "fileversion": 2}


def ensure_textures(example_root: Path, spec: Any) -> dict[str, dict[str, Any]]:
    """Generate every palette texture set into ``<example>/textures``.

    Deterministic (seeded by material name), so reruns are byte-stable. Runs
    in the repo venv (numpy/Pillow); the Blender generators only *load* the
    resulting PNGs for preview.
    """

    from . import texture_kit

    manifests: dict[str, dict[str, Any]] = {}
    texture_dir = example_root / "textures"
    for name, entry in spec.PALETTE.items():
        texture = entry.get("texture")
        if not texture:
            continue
        if texture["family"] == "external":
            manifests[name] = texture_kit.external_set(
                texture_dir, name, example_root, texture["maps"]
            )
            continue
        manifests[name] = texture_kit.build_set(
            texture_dir,
            name,
            texture["family"],
            size=texture.get("size", 512),
            normal_strength=texture.get("normal_strength", 2.0),
            params=texture.get("params"),
        )
    return manifests


# --------------------------------------------------------------------------
# Cooked-DDS harvest bookkeeping.
#
# BeamNG compiles every shipped PNG into a DDS on first load; harvesting that
# cache back into ``<example>/textures_cooked`` and shipping it means players
# never pay for the cook. A harvested DDS is only valid while it is a bake OF
# THE CURRENT SOURCE PNG, and ``<mod_id>.harvest.json`` is what records which
# source that was — the sha256 of each PNG at the moment it was harvested.


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_pixels(path: Path) -> str:
    """Hash of a texture's DECODED image, not of its file bytes.

    THE ENCODER-CHURN LAW (2026-08-15). A generated PNG's file bytes are not a
    stable identity for it: the same seeded generator, run on the same
    machine, encodes the same pixels to different IDAT lengths under different
    Pillow builds, and this box has four Python installations. Measured on
    pachinko_tower: 145 of 145 regenerated textures differed in file bytes and
    max |pixel delta| was 0 on all 145.

    A cooked DDS is a bake of the IMAGE, so the image is what decides whether
    the bake is still current. Non-images fall back to the file hash, which is
    the right answer for them.

    THE FALLBACK IS NARROW ON PURPOSE, and it used to be a blanket
    ``except Exception``. That INVERTED THE GUARD. This law says *same
    pixels, same identity*; the file hash says *different bytes, different
    identity*, which is the rule the 145-PNG incident proved wrong. So a
    transient Pillow failure - a decoder plugin missing from one of the four
    Python installations on this box, a memory error on a 2048 map, a half
    written file - would not fail, it would quietly go back to comparing file
    bytes and invalidate every bake in the harvest. A guard that degrades
    into the failure it guards against is worse than no guard, because it
    reports success. Only two things fall back now: Pillow being absent
    altogether, and a file Pillow positively identifies as not an image.
    Anything else raises.
    """

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return sha256_file(path)
    try:
        with Image.open(path) as image:
            payload = f"{image.mode}|{image.size[0]}x{image.size[1]}|".encode()
            return hashlib.sha256(payload + image.tobytes()).hexdigest()
    except UnidentifiedImageError:
        return sha256_file(path)


def harvest_manifest_path(example_root: Path, mod_id: str) -> Path:
    return example_root / "textures_cooked" / f"{mod_id}.harvest.json"


def load_harvest_manifest(example_root: Path, mod_id: str) -> dict[str, dict[str, str]]:
    """Cooked filename -> {source, source_sha256, dds_sha256}; empty if none."""

    path = harvest_manifest_path(example_root, mod_id)
    if not path.is_file():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != HARVEST_SCHEMA:
        raise ValueError(f"unsupported harvest manifest schema in {path}")
    return manifest.get("textures", {})


def write_harvest_manifest(
    example_root: Path, mod_id: str, stamp: set[str] | None = None
) -> dict[str, dict[str, str]]:
    """Record each cooked DDS against the PNG it was baked from.

    ``stamp`` limits (re)hashing to the cooked files a harvest run actually
    copied this time; everything else carries its existing record forward, so
    a partial harvest can never quietly re-certify an untouched July bake
    against today's sources. ``stamp=None`` stamps every cooked file present,
    which is the explicit ``adopt-harvest`` act. Entries whose DDS or source
    PNG has disappeared are pruned.
    """

    cooked_dir = example_root / "textures_cooked"
    texture_dir = example_root / "textures"
    previous = load_harvest_manifest(example_root, mod_id)
    textures: dict[str, dict[str, str]] = {}
    for cooked in sorted(cooked_dir.glob("*.dds")):
        source = texture_dir / (cooked.name.rsplit(".dds", 1)[0] + ".png")
        if not source.is_file():
            continue
        if stamp is not None and cooked.name not in stamp:
            carried = previous.get(cooked.name)
            if carried:
                textures[cooked.name] = carried
            continue
        textures[cooked.name] = {
            "source": source.name,
            "source_sha256": sha256_file(source),
            # The AUTHORITY (see sha256_pixels). `source_sha256` above stays
            # for the record and for legacy manifests, but it is the decoded
            # image that decides whether this bake is still a bake of it.
            "source_pixels_sha256": sha256_pixels(source),
            "dds_sha256": sha256_file(cooked),
        }
    write_json(
        harvest_manifest_path(example_root, mod_id),
        {"schema": HARVEST_SCHEMA, "mod_id": mod_id, "textures": textures},
    )
    return textures


def cooked_is_current(cooked: Path, fresh: Path, record: dict[str, str] | None) -> bool:
    """Is ``cooked`` a bake of the CURRENT ``fresh`` PNG?

    STALENESS GUARD (2026-08-10; made content-based 2026-08-13). Without a
    check of some kind, a harvest silently shadows every later texture
    change: the centrifuge's cooked set was harvested 2026-07-23, so three
    subsequent rounds of texture work — including the whole procedural-noise
    rebuild — were generated, packaged and installed while the game kept
    rendering the July bake. The player kept reporting the same "digital
    camo" after each fix because they were looking at the same file every
    time.

    The first cut of this guard compared mtimes, which inverted the failure:
    ``ensure_textures`` re-saved every PNG on every run, so a deterministic
    regeneration that produced BYTE-IDENTICAL output still moved the mtime
    and made every cooked DDS look stale forever. Any build after a harvest
    silently reverted the mod to shipping raw PNGs (whale_geyser: 12 files,
    7,230,941 -> 4,816,662 byte zip). Both mods that had been harvested
    before whale_geyser had already lost their DDS this way, unnoticed.

    So validity is a CONTENT question now, answered by the harvest manifest:
    the DDS ships only while the PNG still hashes to what it hashed to when
    the DDS was cooked. Editing a texture invalidates its bake (the
    centrifuge case, still caught); rerunning the generator does not.
    """

    if not cooked.is_file() or not record:
        return False
    # ROUND 2, 2026-08-15: the content question is asked of the DECODED IMAGE,
    # not of the file bytes. The bytes-only form of this check failed exactly
    # once and it failed the expensive way - running the pack test suite under
    # a different Pillow build re-encoded 145 pixel-identical PNGs, every one
    # of pachinko_tower's 130 harvest records went stale in one step, and the
    # certified DDS could not be made current by ANY harvest run because a
    # re-harvest would have been re-encoded again. Records written before this
    # law carry no pixel hash and are still judged by their bytes.
    recorded_pixels = record.get("source_pixels_sha256")
    if recorded_pixels is not None:
        if recorded_pixels != sha256_pixels(fresh):
            return False
    elif record.get("source_sha256") != sha256_file(fresh):
        return False
    recorded_dds = record.get("dds_sha256")
    return recorded_dds is None or recorded_dds == sha256_file(cooked)


def check_emissive_factor(mod_id: str, name: str, stages: list[dict[str, Any]]) -> None:
    """THE THREE-COMPONENT LAW. A 4-element ``emissiveFactor`` renders INERT.

    Measured 2026-08-15 (AGENTS.md "Round-16/17: the photometric ledger") on a
    20-cell calibration strip: two cells differing ONLY in whether a fourth
    component is appended to an otherwise identical ``[1, 1, 1]`` read sRGB
    255.0 (three) and sRGB 0.0 (four) at midnight, in the same frame. Nothing
    rescues four — a cell carrying ``emissive: true`` AND
    ``emissiveIntensityNits: 1800`` on a 4-component factor still reads 0.0.
    All 486 ``emissiveFactor`` arrays in the shipped game write three.

    The pack wrote four by analogy with ``color``, which really IS RGBA, and
    eight materials across four mods shipped completely dark for months while
    three spec files, two texture-family docstrings and AGENTS.md itself all
    recorded the wrong law ("material emissive is inert on this pipeline").
    That is what this raise is here to prevent recurring: the cost of the bug
    is not a bad render, it is a false law that then justifies more work.

    Raising rather than truncating is deliberate. Silently dropping the fourth
    component would let an author keep believing the alpha means something,
    and the value they meant to write may not survive the trim (``letter_glow``
    wrote ``[2.0, 2.05, 2.1, 1.0]`` — the repair was to normalise the factor
    and move the brightness into ``emissiveIntensityNits``, not to lop the 1.0
    off the end). Checked on the FINAL stage dicts, after the ``stage`` /
    ``stage1`` passthroughs have merged, so the raw-key door is shut too.
    """

    for index, stage in enumerate(stages):
        factor = stage.get("emissiveFactor")
        if factor is None or isinstance(factor, str):
            continue
        if len(factor) != 3:
            raise ValueError(
                f"[{mod_id}] material {name!r} stage {index}: emissiveFactor has"
                f" {len(factor)} components ({list(factor)}), and only THREE emit."
                " A four-element factor kills the emissive path dead and no other"
                " key rescues it (AGENTS.md, Round-16/17 photometric ledger)."
                " Drop the alpha and put the brightness in"
                ' "stage": {"emissiveIntensityNits": N}.'
            )


def build_materials(
    mod_id: str,
    handoff: dict[str, Any],
    example_root: Path,
    vehicle_root: Path,
    spec: Any,
) -> dict[str, Any]:
    """BeamNG PBR definitions: textured sets where authored, colour otherwise."""

    palette = handoff["palette"]
    referenced: set[str] = set(handoff["visual"]["materials"])
    for part in handoff.get("parts", []):
        referenced.update(part.get("materials", []))
    # Stock game materials referenced by NAME (e.g. the common vehicle
    # "glass" — real reflective glass shader): no palette entry, no
    # definition written; the game resolves them itself.
    STOCK_MATERIALS = {"glass"}
    referenced -= STOCK_MATERIALS
    missing = sorted(name for name in referenced if name not in palette)
    if missing:
        raise ValueError(f"palette lacks referenced materials: {missing}")

    manifests = ensure_textures(example_root, spec)
    texture_source = example_root / "textures"
    cooked_source = example_root / "textures_cooked"
    harvest = load_harvest_manifest(example_root, mod_id)
    rejected: list[str] = []
    dead_emissive: list[str] = []
    texture_target = vehicle_root / "textures"
    game_prefix = f"/vehicles/{mod_id}/textures"
    if texture_target.is_dir():
        for stale in texture_target.iterdir():
            stale.unlink()

    output: dict[str, Any] = {}
    for name in sorted(referenced):
        entry = palette[name]
        color = entry["color"]
        manifest = manifests.get(name)
        stage0: dict[str, Any] = {
            "metallicFactor": round(float(entry.get("metallic", 0.0)), 6),
        }
        # An emissiveMap the material never switches on is never read by the
        # engine, so it is not written. HISTORY, because the wording used to
        # mis-state the mechanism: across four live pachinko_tower sessions
        # the TextureCooker opened 85 of the mod's 100 textures and the 15 it
        # never touched were exactly the glow-map set - which at the time was
        # named `<base>.emissive.png`. That was TWO faults at once, and only
        # one of them is this drop. The other was the FILENAME: `.emissive`
        # is not a suffix the cooker recognises, so those files could never
        # have cooked even on a material that did switch emission on (round
        # 17; texture_kit.py now writes `<base>_glow.color.png`). Read the
        # sentence above as historical - the live drop-set is the `_glow`
        # maps, and it is dropped because the MATERIAL is not emissive, not
        # because of how the file is named. Shipping them would be dead
        # weight the uncooked-texture gate can never clear. Some texture
        # families emit a glow map unconditionally, so decide per material.
        emissive_enabled = bool(entry.get("emissive")) or bool(
            (entry.get("stage") or {}).get("emissive")
        )
        if manifest:
            texture_target.mkdir(parents=True, exist_ok=True)
            for key in ("baseColorMap", "normalMap", "roughnessMap", "opacityMap",
                        "emissiveMap"):
                filename = manifest.get(key)
                if not filename:
                    continue
                if key == "emissiveMap" and not emissive_enabled:
                    dead_emissive.append(name)
                    continue
                # Ship the BeamNG-cooked DDS when a harvest exists (materials
                # keep referencing .png; the game resolves the cooked
                # sibling — proven Cannon Car Wash release layout). Fall back
                # to shipping the PNG so a fresh checkout still works.
                cooked_name = filename.rsplit(".png", 1)[0] + ".dds"
                cooked = cooked_source / cooked_name
                fresh = texture_source / filename
                # See cooked_is_current: valid means "baked from the PNG
                # that is on disk right now", proven by hash, not by mtime.
                if cooked_is_current(cooked, fresh, harvest.get(cooked_name)):
                    shutil.copyfile(cooked, texture_target / cooked_name)
                else:
                    # EVERY raw PNG that ships is a runtime cook the player
                    # pays for, whether or not a stale DDS happens to sit in
                    # textures_cooked/. The old test (`if cooked.is_file()`)
                    # made the fallback COMPLETELY SILENT for any mod that
                    # had never been harvested at all — which is how
                    # pachinko_tower shipped 100 uncooked PNGs (build serial
                    # 29) with no diagnostic on any build.
                    rejected.append(cooked_name)
                    shutil.copyfile(fresh, texture_target / filename)
                stage0[key] = f"{game_prefix}/{filename}"
            tint = entry.get("tint", [1.0, 1.0, 1.0, color[3]])
            stage0["baseColorFactor"] = [round(float(c), 6) for c in tint]
        else:
            stage0["baseColorFactor"] = [round(float(c), 6) for c in color]
            stage0["roughnessFactor"] = round(float(entry.get("roughness", 0.45)), 6)
        if entry.get("emissive"):
            stage0["emissiveFactor"] = [round(float(c), 6) for c in entry["emissive"]]
        definition: dict[str, Any] = {
            "Stages": [stage0, {}, {}, {}],
            "class": "Material",
            "mapTo": name,
            "materialTag0": mod_id,
            "name": name,
            "persistentId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{mod_id}:{name}")),
            "version": 1.5,
        }
        # Raw passthrough for engine material keys the palette schema does not
        # model (2026-08-10, centrifuge mirror-glazing round). `stage` merges
        # into Stages[0], `material` into the definition root, and both are
        # applied AFTER the derived fields so a palette entry can override a
        # default (e.g. force translucent False on an alpha-1.0 colour).
        # ONLY use keys that exist in shipped BeamNG data - verify by grepping
        # content/vehicles/*.zip materials.json before inventing one. Real:
        # dynamicCubemap, translucent, translucentBlendOp, opacityFactor,
        # castShadows, cubemap. NOT real: alphaType (that is a glTF/Godot
        # spelling; ZERO occurrences in the vehicle data of the install this
        # was checked against). The version this line used to name, "0.38.6",
        # was never read off an engine - it was copied from the test PROFILE
        # DIRECTORY name. Re-derived 2026-08-15 against the engine that
        # actually reports itself as v0.39.4.0 build 20972 (banner in
        # beamng.log; `buildinfo` in the install's integrity.json): still
        # zero, over all 173 zips / 921 materials.json / 6,532 material
        # entries. Say WHICH engine, and get the string from the engine.
        for key, value in (entry.get("stage") or {}).items():
            stage0[key] = value
        # `stage1` fills the SECOND stage slot (2026-08-13, washer water
        # round). Stages beyond 0 are real blended layers - proven by
        # shipped v1.5 data (atv skin stage 1 carries its own opacityMap +
        # colorPaletteMap over stage 0) and by BeamNG's own animated water,
        # italy `river_white_water`, which is TWO stages of the same colour
        # and normal maps scrolled at a ~1.37x speed ratio so the tiling
        # beat never repeats visibly. `inherit_maps` copies stage 0's map
        # paths so the caller only has to state what DIFFERS.
        stage1_spec = entry.get("stage1")
        if stage1_spec:
            stage1: dict[str, Any] = {}
            if stage1_spec.get("inherit_maps"):
                for key in ("baseColorMap", "normalMap", "roughnessMap"):
                    if key in stage0:
                        stage1[key] = stage0[key]
            for key, value in stage1_spec.items():
                if key == "inherit_maps":
                    continue
                stage1[key] = value
            definition["Stages"][1] = stage1
        if entry.get("double_sided"):
            definition["doubleSided"] = True
        if manifest and manifest.get("opacityMap"):
            definition["alphaTest"] = True
            definition["alphaRef"] = 96
            definition["castShadows"] = True
            definition["translucentBlendOp"] = "None"
        elif float(color[3]) < 1.0:
            definition["translucent"] = True
            definition["alphaRef"] = 0
        for key, value in (entry.get("material") or {}).items():
            definition[key] = value
        check_emissive_factor(mod_id, name, definition["Stages"])
        output[name] = definition
    # SAY SO OUT LOUD. Falling back to PNG is a correct-but-costly outcome,
    # and the whole reason the mtime guard could rot for weeks is that it
    # did it silently — three mods lost their harvest with no diagnostic on
    # any build. stderr, so the summary line on stdout stays parseable.
    if dead_emissive:
        print(
            f"[{mod_id}] dropped {len(dead_emissive)} generated emissive map(s): the"
            " palette entry sets no `emissive` (add one, or the glow is inert):"
            f" {', '.join(sorted(dead_emissive))}",
            file=sys.stderr,
        )
    if rejected:
        reason = (
            f"no textures_cooked/{mod_id}.harvest.json (run: build.py <key> harvest)"
            if not harvest
            else "source PNG changed since the harvest (re-cook in game, then harvest)"
        )
        print(
            f"[{mod_id}] shipping PNG instead of {len(rejected)} cooked DDS: {reason}",
            file=sys.stderr,
        )
        for cooked_name in sorted(rejected):
            state = "stale cooked" if (cooked_source / cooked_name).is_file() else "never cooked"
            print(f"[{mod_id}]   {state}: {cooked_name}", file=sys.stderr)
        print(
            f"[{mod_id}] the player will see BeamNG's IMPORTING TEXTURE placeholder"
            " on these surfaces until the runtime cook converges",
            file=sys.stderr,
        )
    return output


def build_bootstrap_lua(mod_id: str, extra: str = "") -> str:
    """extra: spec-provided vehicle-side Lua appended before `return M`.

    Runs in the VEHICLE VM (electrics, obj:createSFXSource, SPOTLIGHT prop
    functions live there - the mechanisms stock emergency lights and mod
    sirens use). The block may wrap M.updateGFX; it must be pcall-safe.
    """
    extension = ge_extension_name(mod_id)
    hook = f"on{camel(mod_id)}Registered"
    return f"""local M = {{}}

local GE_EXTENSION_PATH = "{mod_id}/runtime"
-- BeamNG doubles literal underscores before replacing the path separator.
local GE_EXTENSION_NAME = "{extension}"
local RETRY_INTERVAL_SECONDS = 0.5
local MAX_REGISTRATION_ATTEMPTS = 12

local registrationConfirmed = false
local registrationAttempts = 0
local retryElapsed = 0

local function queueRegistration()
  if registrationConfirmed or registrationAttempts >= MAX_REGISTRATION_ATTEMPTS then return end
  registrationAttempts = registrationAttempts + 1
  local vehicleId = obj:getID()
  obj:queueGameEngineLua(string.format([[
    if not extensions.isExtensionLoaded(%q) then
      extensions.load(%q)
    end
    local extension = extensions[%q]
    if extension and extension.registerProp then
      extension.registerProp(%d)
    end
  ]], GE_EXTENSION_NAME, GE_EXTENSION_PATH, GE_EXTENSION_NAME, vehicleId))
end

local function resetRegistration()
  registrationConfirmed = false
  registrationAttempts = 0
  retryElapsed = RETRY_INTERVAL_SECONDS
end

local function onVehicleLoaded()
  resetRegistration()
  queueRegistration()
end

local function onReset()
  resetRegistration()
  queueRegistration()
end

local function updateGFX(dt)
  if registrationConfirmed or registrationAttempts >= MAX_REGISTRATION_ATTEMPTS then return end
  retryElapsed = retryElapsed + dt
  if retryElapsed < RETRY_INTERVAL_SECONDS then return end
  retryElapsed = 0
  queueRegistration()
end

local function {hook}()
  registrationConfirmed = true
end

local function onExtensionUnloaded()
  local vehicleId = obj and obj:getID() or nil
  if not vehicleId then return end
  obj:queueGameEngineLua(string.format([[
    local extension = extensions[%q]
    if extension and extension.unregisterProp then
      extension.unregisterProp(%d, "vehicle_lua_unloaded")
    end
  ]], GE_EXTENSION_NAME, vehicleId))
end

M.onVehicleLoaded = onVehicleLoaded
M.onReset = onReset
M.updateGFX = updateGFX
M.{hook} = {hook}
M.onExtensionUnloaded = onExtensionUnloaded

{extra}
return M
"""


def build_prop(example_root: Path, spec: Any) -> dict[str, Any]:
    mod_id = spec.MOD_ID
    display_name = spec.DISPLAY_NAME
    handoff = load_handoff(example_root, mod_id)
    mod_root = example_root / "mod"
    vehicle_root = mod_root / "vehicles" / mod_id

    jbeam, total_mass = build_jbeam(mod_id, display_name, handoff)
    # Spec-provided jbeam props rows (e.g. the centrifuge's stock-style
    # amber SPOTLIGHT emergency lights, 2026-08-09): vehicle-side light
    # props driven by electrics, the exact mechanism stock lightbars use.
    extra_props = getattr(spec, "JBEAM_PROPS", None)
    if extra_props:
        jbeam[mod_id]["props"] = extra_props
    write_json(vehicle_root / f"{mod_id}.jbeam", jbeam)
    write_json(
        vehicle_root / "main.materials.json",
        build_materials(mod_id, handoff, example_root, vehicle_root, spec),
    )
    write_json(
        vehicle_root / "info.json",
        {
            "Author": AUTHOR,
            "Name": display_name,
            "Type": "Prop",
            "default_pc": "standard",
        },
    )
    write_json(
        vehicle_root / "standard.pc",
        {
            "format": 2,
            "mainPartName": mod_id,
            "model": mod_id,
            "parts": {},
        },
    )
    write_json(
        vehicle_root / "info_standard.json",
        {
            "Configuration": "Standard",
            "Value": int(spec.VALUE_DOLLARS),
            "Weight": total_mass,
        },
    )
    bootstrap_dir = vehicle_root / "lua"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    (bootstrap_dir / f"{mod_id}_vehicle.lua").write_text(
        build_bootstrap_lua(mod_id, getattr(spec, "VEHICLE_LUA_EXTRA", "")),
        encoding="utf-8",
        newline="\n",
    )
    interaction = build_interaction_json(mod_id, handoff)
    if interaction is not None:
        write_json(vehicle_root / f"{mod_id}_default.interaction.json", interaction)

    # Static vehicle-side assets: <example>/assets/ is a mixed bag of BUILD
    # INPUTS (hero .glb meshes the Blender generator imports, the source PNGs
    # the "external" texture family stages into <example>/textures/) and the
    # handful of files the game itself opens off the VFS at runtime — the
    # washer's live-LCD html, which an htmlTexture webview loads by path and
    # so cannot be derived from the palette.
    #
    # THE SHIPPED-ASSET LAW (2026-08-13): staging is opt-in, never a blind
    # rglob. A blind copy shipped boot_of_doom's hero .glb plus a second,
    # unreferenced copy of its three baked maps — ~11 MB of a 42 MB zip that
    # nothing in the built tree pointed at (main.materials.json resolves the
    # textures/ copies the external family already stages). Build inputs must
    # never reach a player's disk, so a spec declares exactly what ships.
    for asset_rel in getattr(spec, "SHIP_ASSETS", ()):
        source = (example_root / "assets" / asset_rel).resolve()
        assets_root = (example_root / "assets").resolve()
        if assets_root not in source.parents:
            raise ValueError(f"SHIP_ASSETS entry escapes assets/: {asset_rel}")
        if not source.is_file():
            raise FileNotFoundError(f"SHIP_ASSETS entry missing: {source}")
        destination = vehicle_root / asset_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    runtime_path = mod_root / "lua" / "ge" / "extensions" / mod_id / "runtime.lua"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_source = lua_kit.generate_runtime(mod_id, display_name, handoff, spec)
    runtime_path.write_text(runtime_source, encoding="utf-8", newline="\n")

    thumbnail = example_root / "authoring" / f"{mod_id}_thumbnail.jpg"
    if thumbnail.is_file():
        shutil.copyfile(thumbnail, vehicle_root / "default.jpg")
        shutil.copyfile(thumbnail, vehicle_root / "standard.jpg")

    summary = {
        "model": mod_id,
        "nodes": len(handoff["nodes"]),
        "beams": len(handoff["beams"]),
        "triangles": len(handoff["triangles"]),
        "parts": [part["name"] for part in handoff.get("parts", [])],
        "mass_kg": total_mass,
        "visual_sha256": handoff["visual"]["sha256"],
    }
    print(json.dumps(summary, sort_keys=True))
    return summary

"""Generate the Gateway Skillet scenario package from the reviewed authoring files.

Two sources of truth, both under ``authoring/``:

- ``ericrolph_hot_potato_arena.handoff.json`` (geometry worker): the prefab
  TSStatic instances, the obstacle keep-out table, the shape table and the
  materials file. Counts are the handoff's to decide.
- ``ericrolph_hot_potato_arena.layout.json`` (scenario placement table):
  car spawns, pantry stacks, barrel clusters and the three spatter-geyser
  sites (design v3 §3.5 / §5.1 / §5.4 / §6.2 + the v3.1 amendment). If the
  handoff ever carries a ``layout`` section with the same schema it wins.

From those this module emits, deterministically: the JSONL prefab, the
scenario JSON, the generated constants block spliced into the scenario-owned
GE Lua extension, and the 640x360 thumbnail. Every object name, trigger,
material and file basename is namespaced ``ericrolph_hot_potato_arena``;
persistentIds are uuid5 of the object name; every text output is strict JSON
written with LF line endings.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

EXAMPLE_ROOT = Path(__file__).resolve().parent
MOD_ID = "ericrolph_hot_potato_arena"
#: B5 (2026-09-10): the scenario left stock ``gridmap_v2`` and now lives on the
#: round's own level, whose id is the same string as the mod id. BeamNG derives
#: a scenario's level PURELY FROM ITS PATH - ``scenariosLoader.lua`` L45 does
#: ``levelName = gsub(file, "(.*/)(.*)/scenarios/(.*)%.json", "%2")`` and
#: OVERWRITES any ``levelName`` the JSON carries - so this constant, not a
#: field, is the level binding. Keeping both names identical also keeps the
#: ``groundtype`` law (AGENTS.md: a mod material binds a ground type only under
#: ``levels/<id>/art/shapes/...``) satisfied by the level's own id.
LEVEL_ID = MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
HANDOFF_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.handoff.json"
LAYOUT_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.layout.json"
#: B2/B4's registry rows for the level's own solids (hearth stones, chocks,
#: logs, props). The arena's 46 plus these go out in ONE
#: ``hotPotatoRegisterObstacles`` call - the runtime REPLACES the set on every
#: call, so two calls would leave only the second list registered.
LEVEL_OBSTACLES_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}_level_obstacles.json"
RENDER_PATH = EXAMPLE_ROOT / "authoring" / "renders" / "arena_overview_high.jpg"
LEVEL_ROOT = MOD_ROOT / "levels" / LEVEL_ID
SCENARIO_ROOT = LEVEL_ROOT / "scenarios" / MOD_ID
PREFAB_PATH = SCENARIO_ROOT / f"{MOD_ID}.prefab.json"
SCENARIO_PATH = SCENARIO_ROOT / f"{MOD_ID}.json"
LUA_PATH = SCENARIO_ROOT / f"{MOD_ID}.lua"
THUMBNAIL_PATH = SCENARIO_ROOT / f"{MOD_ID}.jpg"
SHAPES_RELATIVE = f"levels/{LEVEL_ID}/art/shapes/hot_potato_arena"
SCENARIO_RELATIVE = f"levels/{LEVEL_ID}/scenarios/{MOD_ID}"
LAYOUT_SCHEMA = "ericrolph-hot-potato-arena-layout-v1"

GROUP_NAME = f"{MOD_ID}_group"
DISPENSER_NAME = f"{MOD_ID}_dispenser"
PLAYER_NAME = f"{MOD_ID}_player"
HOT_POTATO_JBEAM = "ericrolph_hot_potato"
EMITTER_DATABLOCK = "lightExampleEmitterNodeData1"
STEAM_EMITTER = "BNGP_waterfallsteam"
SPATTER_EMITTER = "BNGP_34"
#: Dynamic field stamped on every breakable prop record so a future
#: name-independent runtime filter has a handle (critique round 1, fix 4).
PROP_ROLE_FIELD = f"{HOT_POTATO_JBEAM}_role"

CENTER = (850.0, -280.0, 100.0)
ARENA_RADIUS_M = 91.4
#: The four runtime options the scenario boot touches, in the design's order
#: (§6.3). The Lua snapshots exactly these keys before writing them.
BOOT_OPTION_KEYS = (
    "arena_radius_m",
    "arena_enabled",
    "ai_enabled",
    "arena_magnet_enabled",
    # Serial 53: the player's out-of-bounds penalty. Default 1.0 = OFF, so the
    # arena must switch it on or nothing changes; range {1, 5} (read from the
    # shipped runtime). Camp burn and OOB burn combine with max(), never a
    # product. Snapshotted and handed back like every other boot key.
    "oob_burn_multiplier",
)

GENERATED_BEGIN = "-- BEGIN GENERATED (sync_scenario_outputs.py; do not edit by hand)"
GENERATED_END = "-- END GENERATED"

#: The runtime dodge hook's ceiling (hotPotatoRegisterObstacles contract).
#: Runtime ask #8 raised ``v26.OBSTACLE_CAP`` 64 -> 128 at Hot Potato build
#: serial 56 (design v4 §7.3 R9), because the arena's 46 rows plus the level's
#: 67 need 113 in one call and a 129th entry refuses the WHOLE list.
OBSTACLE_HOOK_CAP = 128
#: The runtime's dodge keep-out band: an r outside it refuses the whole call
#: (``spec.py`` v26.OBSTACLE_R_MIN / OBSTACLE_R_MAX).
OBSTACLE_R_MIN = 0.5
OBSTACLE_R_MAX = 30.0
#: The runtime's floor for the physical radius in the two-radius contract
#: (serial 55): an rp below this refuses the WHOLE registration call.
OBSTACLE_RP_FLOOR = 0.1
#: Authoring-only obstacle metadata: never passed to the runtime.
OBSTACLE_AUTHORING_FIELDS = frozenset({"rp_kind"})
STOCK_PROP_JBEAMS = frozenset({"cardboard_box", "barrels"})

IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

#: How BeamNG reads a prefab record's nine-float ``rotationMatrix``. MEASURED
#: live (arena smoke, 2026-09-01): with textbook row-major "world = R * local"
#: matrices every rotated wall arc landed MIRRORED - the spout authored for
#: bearing 60 sat at 300 under the identity-placed trim ring's floating rivet,
#: and bearing 60 read a bare arc_45 crest; the structure10 witness rays read
#: bare ground at the textbook footprint and a 16 m cube stack at the
#: transposed one. The engine takes the three ROWS as the object's local X/Y/Z
#: axes expressed in world space (Torque MatrixF column convention; the game's
#: own terrain-tilted barrier prefabs show the same signature). For a pure Z
#: rotation that is the transpose of the textbook matrix, so every matrix here
#: is derived from the authored CCW angle through ``engine_yaw_matrix``. The
#: geometry v2 handoff declares the same convention (``matrix_convention``).
ENGINE_ROTATION_CONVENTION = "transposed"
HANDOFF_ENGINE_CONVENTION_KEY = "rows-are-local-axes"


class SyncError(RuntimeError):
    """The authoring files or the checked-in outputs violate the package contract."""


def persistent_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{MOD_ID}:{name}"))


def _r6(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _r9(value: float) -> float:
    rounded = round(float(value), 9)
    return 0.0 if rounded == 0 else rounded


def bearing_point(bearing_deg: float, r: float) -> tuple[float, float]:
    """Compass bearing (0 = +Y, 90 = +X) and range to world XY (design §3)."""

    theta = math.radians(bearing_deg)
    return _r6(CENTER[0] + r * math.sin(theta)), _r6(CENTER[1] + r * math.cos(theta))


def bearing_tangent(bearing_deg: float) -> tuple[float, float]:
    theta = math.radians(bearing_deg)
    return _r6(math.cos(theta)), _r6(-math.sin(theta))


def bearing_normal(bearing_deg: float) -> tuple[float, float]:
    theta = math.radians(bearing_deg)
    return _r6(math.sin(theta)), _r6(math.cos(theta))


def standard_yaw_matrix(yaw_deg: float) -> list[float]:
    """Textbook row-major world = R * local (what the v1 handoff carried)."""

    c = math.cos(math.radians(yaw_deg))
    s = math.sin(math.radians(yaw_deg))
    return [_r9(c), _r9(-s), 0.0, _r9(s), _r9(c), 0.0, 0.0, 0.0, 1.0]


def engine_yaw_matrix(yaw_ccw_deg: float) -> list[float]:
    """The engine encoding of a CCW yaw about +Z (rows = local axes in world)."""

    c = math.cos(math.radians(yaw_ccw_deg))
    s = math.sin(math.radians(yaw_ccw_deg))
    return [_r9(c), _r9(s), 0.0, _r9(-s), _r9(c), 0.0, 0.0, 0.0, 1.0]


def yaw_matrix(yaw_deg: float) -> list[float]:
    return engine_yaw_matrix(yaw_deg)


def facing_center_matrix(bearing_deg: float) -> list[float]:
    """A BeamNG vehicle faces local -Y; yaw -bearing points it at the pad."""

    return engine_yaw_matrix(-bearing_deg)


def _matrices_close(a: list[float], b: list[float], tolerance: float = 1e-6) -> bool:
    return len(a) == len(b) == 9 and all(abs(x - y) <= tolerance for x, y in zip(a, b))


def _finite(values: Any) -> bool:
    return all(math.isfinite(float(value)) for value in values)


# --- handoff ------------------------------------------------------------------


def read_handoff(path: Path = HANDOFF_PATH) -> dict[str, Any]:
    handoff = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(handoff, dict) or handoff.get("arena_id") != MOD_ID:
        raise SyncError(f"handoff is not the {MOD_ID} handoff: {path}")
    instances = handoff.get("instances")
    obstacles = handoff.get("obstacles")
    # Counts are the handoff's to decide (v1: 31 instances / 16 obstacles; v2:
    # 31 / 42). The only hard ceiling is the runtime dodge hook's 64-point cap.
    if not isinstance(instances, list) or not instances:
        raise SyncError("handoff must carry at least one prefab instance")
    if not isinstance(obstacles, list) or not obstacles or len(obstacles) > OBSTACLE_HOOK_CAP:
        raise SyncError(f"handoff obstacle table must hold 1..{OBSTACLE_HOOK_CAP} points")
    shapes = handoff.get("shapes")
    if not isinstance(shapes, dict) or not shapes:
        raise SyncError("handoff must carry the shape table")
    centre = [float(value) for value in handoff["center_world"]]
    if centre != list(CENTER):
        raise SyncError(f"handoff centre {centre} differs from the design anchor {CENTER}")
    if float(handoff["crest_radius_m"]) != ARENA_RADIUS_M:
        raise SyncError("handoff crest radius must equal the runtime default arena radius")
    declared = str(handoff.get("matrix_convention", ""))
    engine_declared = declared.startswith(HANDOFF_ENGINE_CONVENTION_KEY)
    names = [str(instance["name"]) for instance in instances]
    if len(set(names)) != len(names):
        raise SyncError("handoff instance names must be unique")
    for instance in instances:
        name = str(instance["name"])
        if not name.startswith(f"{MOD_ID}_"):
            raise SyncError(f"handoff instance is not namespaced: {name}")
        if instance["collision"] not in {"visible-mesh", "none"}:
            raise SyncError(f"unknown collision flag on {name}: {instance['collision']!r}")
        dae = str(instance["dae"])
        if not dae.startswith(f"{SHAPES_RELATIVE}/{MOD_ID}_") or not dae.endswith(".dae"):
            raise SyncError(f"handoff instance references a shape outside the mod: {dae}")
        if not (MOD_ROOT / dae).is_file():
            raise SyncError(f"handoff shape missing from the mod tree: {dae}")
        matrix = [float(value) for value in instance["rotationMatrix"]]
        position = [float(value) for value in instance["position"]]
        scale = [float(value) for value in instance["scale"]]
        if len(matrix) != 9 or len(position) != 3 or len(scale) != 3:
            raise SyncError(f"invalid transform on handoff instance {name}")
        if not _finite((*matrix, *position, *scale)):
            raise SyncError(f"non-finite transform on handoff instance {name}")
        angle = float(instance["rotation_ccw_deg_z"])
        # The authored angle is the intent. A handoff that DECLARES the engine
        # convention must carry the engine matrix for that angle (never
        # double-transpose); an undeclared one may carry either encoding.
        instance_declared = str(instance.get("matrix_convention", declared))
        if instance_declared.startswith(HANDOFF_ENGINE_CONVENTION_KEY):
            if not _matrices_close(matrix, engine_yaw_matrix(angle)):
                raise SyncError(
                    f"handoff matrix on {name} is not the engine encoding of {angle} deg"
                )
        elif not (
            _matrices_close(matrix, standard_yaw_matrix(angle))
            or _matrices_close(matrix, engine_yaw_matrix(angle))
        ):
            raise SyncError(f"handoff matrix on {name} is not a Z rotation of {angle} deg")
    obstacle_names = []
    for obstacle in obstacles:
        if not {"name", "x", "y", "r_keepout"} <= set(obstacle):
            raise SyncError(f"malformed obstacle entry: {obstacle}")
        if not (0.0 < float(obstacle["r_keepout"]) <= 20.0):
            raise SyncError(f"obstacle keep-out out of range: {obstacle}")
        if not _finite((obstacle["x"], obstacle["y"], obstacle["r_keepout"])):
            raise SyncError(f"non-finite obstacle entry: {obstacle}")
        # The two-radius contract (geometry v3.5, runtime serial 55): rp is
        # the measured PHYSICAL radius of the solid, r the dodge keep-out.
        # The runtime REFUSES the whole registration call if any rp is
        # non-finite, below the 0.1 floor, or larger than its own r - so a bad
        # value must fail here, at generation, and never reach a boot.
        if "rp" in obstacle:
            rp = float(obstacle["rp"])
            if not _finite((rp,)):
                raise SyncError(f"non-finite obstacle rp: {obstacle}")
            if rp < OBSTACLE_RP_FLOOR:
                raise SyncError(
                    f"obstacle rp below the runtime's {OBSTACLE_RP_FLOOR} floor: {obstacle}"
                )
            if rp > float(obstacle["r_keepout"]):
                raise SyncError(f"obstacle rp exceeds its own keep-out r: {obstacle}")
        obstacle_names.append(str(obstacle["name"]))
    if len(set(obstacle_names)) != len(obstacle_names):
        raise SyncError("handoff obstacle names must be unique")
    for key, shape in shapes.items():
        dae = str(shape["dae"])
        if not (MOD_ROOT / dae).is_file():
            raise SyncError(f"handoff shape table names a missing DAE: {key} -> {dae}")
        # The handoff's sha256 is the geometry lock: the DAE on disk must be
        # the one the geometry worker measured, or the package is stale.
        declared_sha = str(shape.get("sha256", ""))
        if declared_sha:
            actual_sha = hashlib.sha256((MOD_ROOT / dae).read_bytes()).hexdigest()
            if actual_sha != declared_sha:
                raise SyncError(
                    f"shape {key} on disk ({actual_sha[:12]}) is not the handoff's ({declared_sha[:12]}); "
                    "re-run the geometry export or refresh the handoff"
                )
        lod = shape.get("lod")
        if isinstance(lod, dict):
            # Geometry v3: stock-convention detail nodes (_a<pixel size> under
            # base00/start01 + nulldetail<px>). The engine selects them by
            # projected size on its own; the prefab record only has to leave
            # forceDetail at -1. Verify the DAE really carries them so a
            # re-cut cannot silently ship a floor without its far detail.
            source = (MOD_ROOT / dae).read_text(encoding="utf-8")
            node_ids = set(re.findall(r'<node id="([^"]+)"', source))
            expected_nodes = {
                f"{MOD_ID}_{key}_a{int(lod['near_detail_px'])}",
                f"{MOD_ID}_{key}_a{int(lod['far_detail_px'])}",
                f"nulldetail{int(lod['null_detail_px'])}",
            }
            missing = sorted(expected_nodes - node_ids)
            if missing:
                raise SyncError(
                    f"shape {key} declares LOD but its DAE lacks detail nodes {missing}"
                )
    materials_json = str(handoff.get("materials_json", ""))
    if (
        not materials_json.startswith(f"{SHAPES_RELATIVE}/{MOD_ID}")
        or not (MOD_ROOT / materials_json).is_file()
    ):
        raise SyncError(f"handoff materials json is missing or misplaced: {materials_json!r}")
    handoff["_engine_convention_declared"] = engine_declared
    return handoff


def shipped_art_members(handoff: dict[str, Any]) -> list[str]:
    """The level-scoped art the package ships, derived from reviewed sources.

    Shapes come from the handoff's shape table, the materials file from the
    handoff, and every texture from the materials file's own map references
    (a material naming a texture that is not on disk is a packaging error).
    """

    members = {str(shape["dae"]) for shape in handoff["shapes"].values()}
    materials_json = str(handoff["materials_json"])
    members.add(materials_json)
    materials = json.loads((MOD_ROOT / materials_json).read_text(encoding="utf-8"))
    for definition in materials.values():
        for stage in definition.get("Stages", []):
            for field, value in stage.items():
                if field.endswith("Map") and isinstance(value, str):
                    if not value.startswith(f"/{SHAPES_RELATIVE}/textures/{MOD_ID}_"):
                        raise SyncError(f"material map outside the mod's texture root: {value}")
                    relative = value.removeprefix("/")
                    if not (MOD_ROOT / relative).is_file():
                        raise SyncError(f"material references a missing texture: {value}")
                    members.add(relative)
    return sorted(members)


# --- the level's own obstacle rows (B2 + B4 handoff) --------------------------


def _check_obstacle_row(row: dict[str, Any], where: str) -> None:
    """The runtime's registration contract, enforced at generation time.

    ``hotPotatoRegisterObstacles`` REFUSES THE WHOLE LIST on one bad entry, so a
    row that would be refused must fail here and never reach a boot.
    """

    if not {"name", "x", "y", "r", "rp"} <= set(row):
        raise SyncError(f"{where}: malformed obstacle row: {row}")
    if not _finite((row["x"], row["y"], row["r"], row["rp"])):
        raise SyncError(f"{where}: non-finite obstacle row: {row}")
    r = float(row["r"])
    rp = float(row["rp"])
    if not (OBSTACLE_R_MIN <= r <= OBSTACLE_R_MAX):
        raise SyncError(
            f"{where}: obstacle r outside the runtime band "
            f"[{OBSTACLE_R_MIN}, {OBSTACLE_R_MAX}]: {row}"
        )
    if rp < OBSTACLE_RP_FLOOR:
        raise SyncError(f"{where}: obstacle rp below the runtime's {OBSTACLE_RP_FLOOR} floor: {row}")
    if rp > r:
        raise SyncError(f"{where}: obstacle rp exceeds its own keep-out r: {row}")


def read_level_obstacles(path: Path = LEVEL_OBSTACLES_PATH) -> list[dict[str, Any]]:
    """The level's registry rows (B2's 28 stones + B4's 39 props), validated.

    The file is a HANDOFF from the level rounds: this module never authors a
    row, it only carries them into the single registration call. Returned rows
    are stripped to the runtime's four fields plus ``name`` (local diagnostics).
    """

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("level_id") != LEVEL_ID:
        raise SyncError(f"level obstacle handoff is not {LEVEL_ID}'s: {path}")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise SyncError(f"level obstacle handoff carries no rows: {path}")
    out: list[dict[str, Any]] = []
    for row in rows:
        _check_obstacle_row(row, path.name)
        out.append(
            {
                "name": str(row["name"]),
                "x": float(row["x"]),
                "y": float(row["y"]),
                "r": float(row["r"]),
                "rp": float(row["rp"]),
            }
        )
    names = [row["name"] for row in out]
    if len(set(names)) != len(names):
        raise SyncError(f"level obstacle names must be unique: {path}")
    return out


def obstacle_rows(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    """The ONE registration payload: the arena's own rows, then the level's.

    Design v4 §7.3 R9. The arena's 46 come first and stay byte-identical so a
    diff of the generated block shows exactly the level's rows arriving; the
    level's 67 follow. A call REPLACES the runtime's set, so this list is the
    whole dodge census the pin reflex will ever see.
    """

    arena = [
        {
            "name": str(obstacle["name"]),
            "x": float(obstacle["x"]),
            "y": float(obstacle["y"]),
            "r": float(obstacle["r_keepout"]),
            "rp": float(obstacle.get("rp", OBSTACLE_RP_FLOOR)),
            "source": "arena",
        }
        for obstacle in handoff["obstacles"]
    ]
    for row in arena:
        _check_obstacle_row(row, "handoff.obstacles")
    level = [{**row, "source": "level"} for row in read_level_obstacles()]
    rows = [*arena, *level]
    names = [row["name"] for row in rows]
    if len(set(names)) != len(names):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise SyncError(f"arena and level obstacle names collide: {duplicates}")
    if len(rows) > OBSTACLE_HOOK_CAP:
        raise SyncError(
            f"obstacle table ({len(rows)}) exceeds the runtime hook cap ({OBSTACLE_HOOK_CAP}); "
            "a call with one entry too many refuses the WHOLE list"
        )
    return rows


# --- layout -------------------------------------------------------------------


def read_layout(handoff: dict[str, Any] | None = None, path: Path = LAYOUT_PATH) -> dict[str, Any]:
    """The scenario placement table: the handoff's ``layout`` section if present, else the file."""

    handoff = handoff or read_handoff()
    layout = handoff.get("layout")
    source = "handoff"
    if not isinstance(layout, dict):
        layout = json.loads(path.read_text(encoding="utf-8"))
        source = path.name
    if not isinstance(layout, dict) or layout.get("schema") != LAYOUT_SCHEMA:
        raise SyncError(f"layout ({source}) does not carry schema {LAYOUT_SCHEMA}")
    cars = layout.get("cars")
    if not isinstance(cars, list) or not cars:
        raise SyncError("layout must carry at least one car spawn")
    if sum(1 for car in cars if car.get("role") == "player") != 1:
        raise SyncError("layout must carry exactly one player spawn")
    for car in cars:
        if car.get("role") not in {"player", "ai"} or not str(car.get("jbeam", "")):
            raise SyncError(f"malformed car spawn: {car}")
        if not _finite((car["bearing"],)):
            raise SyncError(f"non-finite bearing on car spawn: {car}")
    for group_key in ("box_walls", "barrel_clusters"):
        for group in layout.get(group_key, []):
            if str(group.get("jbeam", "")) not in STOCK_PROP_JBEAMS:
                raise SyncError(f"{group_key} entry must use a stock prop jbeam: {group}")
            if int(group["count"]) < 1 or float(group["pitch_m"]) <= 0:
                raise SyncError(f"malformed {group_key} entry: {group}")
            if not _finite((group["bearing"], group["r"])):
                raise SyncError(f"non-finite {group_key} entry: {group}")
    geysers = layout.get("geysers")
    if not isinstance(geysers, list) or not geysers:
        raise SyncError("layout must carry at least one geyser site")
    seen = set()
    for site in geysers:
        name = str(site.get("name", ""))
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in seen:
            raise SyncError(f"geyser site names must be unique lowercase identifiers: {name!r}")
        seen.add(name)
        for key in ("half_len", "half_wid", "off", "on"):
            if float(site[key]) <= 0:
                raise SyncError(f"geyser {name}: {key} must be positive")
        if not site.get("wisp_offsets") or not site.get("curtain_offsets"):
            raise SyncError(f"geyser {name}: needs at least one wisp and one curtain emitter")
        span = max(abs(float(v)) for v in site["curtain_offsets"])
        # The pop strip may never be wider than the visible steam (critique
        # round 1, fix 10): the outermost curtain node plus a 3 m plume.
        if float(site["half_len"]) > span + 3.0:
            raise SyncError(f"geyser {name}: pop strip ({site['half_len']} m) wider than its steam")
    if float(layout.get("geyser_pop_mps", 0)) <= 0:
        raise SyncError("layout must carry a positive geyser_pop_mps")
    layout["_source"] = source
    return layout


# --- records ------------------------------------------------------------------


def static_records(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for instance in handoff["instances"]:
        collides = instance["collision"] == "visible-mesh"
        records.append(
            {
                "name": str(instance["name"]),
                "class": "TSStatic",
                "persistentId": persistent_id(str(instance["name"])),
                "__parent": GROUP_NAME,
                "shapeName": "/" + str(instance["dae"]),
                "dynamic": "0",
                "playAmbient": "0",
                "useInstanceRenderData": "1",
                "instanceColor": "White",
                # Probe P1: a prefab mod TSStatic with Visible Mesh Final
                # collides at level load and is castRayStatic-visible. The
                # floor skins are the medallion-law visual inlay: no collision.
                "collisionType": "Visible Mesh Final" if collides else "None",
                "decalType": "Visible Mesh Final" if collides else "None",
                "prebuildCollisionData": "1" if collides else "0",
                "renderNormals": "0",
                # NO forceDetail / meshCulling / originSort: stock gridmap_v2
                # (8,993 records) and CCW emit none, and the JSON prefab
                # loader leaves a string-typed S32 slot UNINITIALISED (critic
                # r3: the four floors read 12589 / four different large
                # integers across two boots). The class defaults read back
                # -1 / 0 and are what auto LOD selection needs.
                "mode": "Ignore",
                "canSave": "1",
                "canSaveDynamicFields": "1",
                "position": [_r6(value) for value in instance["position"]],
                # Derived from the authored CCW angle in the ENGINE convention
                # (see ENGINE_ROTATION_CONVENTION); read_handoff verified the
                # handoff's own matrix against the angle.
                "rotationMatrix": engine_yaw_matrix(float(instance["rotation_ccw_deg_z"])),
                "scale": [_r6(value) for value in instance["scale"]],
            }
        )
    return records


def _vehicle_record(entry: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": entry["name"],
        "class": "BeamNGVehicle",
        "persistentId": persistent_id(entry["name"]),
        "__parent": GROUP_NAME,
        "position": [_r6(value) for value in entry["position"]],
        "dataBlock": "default_vehicle",
        "jBeam": entry["jbeam"],
    }
    if entry.get("licence"):
        record["licenseText"] = entry["licence"]
    record["rotationMatrix"] = list(entry["rotation"])
    # Probe P4: the prefab-record Dispenser registers at the first poll with
    # this exact shape; the player focus comes from the scenario JSON
    # ``vehicles`` block, never from auto-enter.
    record["autoEnterVehicle"] = "false"
    if entry["role"] == "prop":
        record["canSaveDynamicFields"] = "1"
        record[PROP_ROLE_FIELD] = "prop"
    return record


def vehicle_layout(
    handoff: dict[str, Any] | None = None, layout: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """The vehicle census from the placement table: dispenser, cars, boxes, barrels."""

    handoff = handoff or read_handoff()
    layout = layout or read_layout(handoff)
    car_z = float(layout["car_spawn_z"])
    prop_z = float(layout["prop_spawn_z"])
    ring = float(layout["spawn_ring_r"])
    vehicles: list[dict[str, Any]] = [
        {
            "name": DISPENSER_NAME,
            "role": "dispenser",
            "jbeam": HOT_POTATO_JBEAM,
            "position": (CENTER[0], CENTER[1], float(layout["dispenser_z"])),
            "rotation": list(IDENTITY),
            "licence": "POTATO",
        }
    ]
    for car in layout["cars"]:
        bearing = float(car["bearing"])
        x, y = bearing_point(bearing, float(car.get("r", ring)))
        name = PLAYER_NAME if car["role"] == "player" else f"{MOD_ID}_{car['name']}"
        vehicles.append(
            {
                "name": name,
                "role": car["role"],
                "jbeam": str(car["jbeam"]),
                "position": (x, y, car_z),
                "rotation": facing_center_matrix(bearing),
                "licence": str(car.get("licence", "")),
                "bearing": bearing,
            }
        )
    for group_key, singular in (("box_walls", "box"), ("barrel_clusters", "barrel")):
        for group in layout.get(group_key, []):
            bearing = float(group["bearing"])
            cx, cy = bearing_point(bearing, float(group["r"]))
            tx, ty = bearing_tangent(bearing)
            count = int(group["count"])
            pitch = float(group["pitch_m"])
            for index in range(count):
                offset = (index - (count - 1) / 2.0) * pitch
                vehicles.append(
                    {
                        "name": f"{MOD_ID}_{group['name']}_{singular}_{index + 1}",
                        "role": "prop",
                        "jbeam": str(group["jbeam"]),
                        "position": (_r6(cx + tx * offset), _r6(cy + ty * offset), prop_z),
                        "rotation": yaw_matrix(-bearing) if singular == "box" else list(IDENTITY),
                        "licence": "",
                    }
                )
    names = [entry["name"] for entry in vehicles]
    if len(set(names)) != len(names):
        raise SyncError("vehicle names collide in the layout")
    return vehicles


def vehicle_records(layout_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_vehicle_record(entry) for entry in layout_entries]


def geyser_layout(
    handoff: dict[str, Any] | None = None, layout: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    handoff = handoff or read_handoff()
    layout = layout or read_layout(handoff)
    instances = {str(instance["name"]): instance for instance in handoff["instances"]}
    emitter_z = float(layout["emitter_z"])
    grade_z = float(layout["grade_z"])
    sites = []
    for spec in layout["geysers"]:
        bearing = float(spec["bearing"])
        cx, cy = bearing_point(bearing, float(spec["r"]))
        anchor = spec.get("anchor")
        if anchor:
            missing = [name for name in anchor if name not in instances]
            if missing:
                raise SyncError(
                    f"geyser {spec['name']} anchors on unknown handoff instances: {missing}"
                )
            anchored = [instances[name]["position"] for name in anchor]
            cx = _r6(sum(float(p[0]) for p in anchored) / len(anchored))
            cy = _r6(sum(float(p[1]) for p in anchored) / len(anchored))
        tx, ty = bearing_tangent(bearing)
        nx, ny = bearing_normal(bearing)
        prefix = f"{MOD_ID}_geyser_{spec['name']}"
        wisp = [
            {
                "name": f"{prefix}_wisp_{index}",
                "emitter": STEAM_EMITTER,
                "role": "wisp",
                "position": (_r6(cx + tx * float(offset)), _r6(cy + ty * float(offset)), emitter_z),
            }
            for index, offset in enumerate(spec["wisp_offsets"], start=1)
        ]
        curtain = [
            {
                "name": f"{prefix}_curtain_{index}",
                "emitter": STEAM_EMITTER,
                "role": "curtain",
                "position": (_r6(cx + tx * float(offset)), _r6(cy + ty * float(offset)), emitter_z),
            }
            for index, offset in enumerate(spec["curtain_offsets"], start=1)
        ]
        curtain.append(
            {
                "name": f"{prefix}_spatter",
                "emitter": SPATTER_EMITTER,
                "role": "curtain",
                "position": (cx, cy, emitter_z),
            }
        )
        sites.append(
            {
                "name": str(spec["name"]),
                "cx": cx,
                "cy": cy,
                "cz": grade_z,
                "tx": tx,
                "ty": ty,
                "nx": nx,
                "ny": ny,
                "half_len": float(spec["half_len"]),
                "half_wid": float(spec["half_wid"]),
                "off": float(spec["off"]),
                "on": float(spec["on"]),
                "phase": _r6(spec["phase"]),
                "wisp": wisp,
                "curtain": curtain,
                "emitters": [*wisp, *curtain],
            }
        )
    return sites


def emitter_records(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for site in sites:
        for emitter in site["emitters"]:
            records.append(
                {
                    "name": emitter["name"],
                    "class": "ParticleEmitterNode",
                    "persistentId": persistent_id(emitter["name"]),
                    "__parent": GROUP_NAME,
                    "dataBlock": EMITTER_DATABLOCK,
                    "emitter": emitter["emitter"],
                    # Wisps are the always-on OFF tell (design §5.4 "idle wisp
                    # when OFF"); curtain nodes switch with the ON window.
                    "active": emitter["role"] == "wisp",
                    "position": [_r6(value) for value in emitter["position"]],
                    "rotationMatrix": list(IDENTITY),
                    "scale": [1.0, 1.0, 1.0],
                }
            )
    return records


def group_record() -> dict[str, Any]:
    return {
        "name": GROUP_NAME,
        "class": "SimGroup",
        "persistentId": persistent_id(GROUP_NAME),
        "groupPosition": "0.000000 0.000000 0.000000",
    }


def prefab_records(
    handoff: dict[str, Any], layout: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    layout = layout or read_layout(handoff)
    records = [
        *vehicle_records(vehicle_layout(handoff, layout)),
        *static_records(handoff),
        *emitter_records(geyser_layout(handoff, layout)),
        group_record(),
    ]
    names = [record["name"] for record in records]
    if len(set(names)) != len(names):
        raise SyncError("prefab object names collide")
    identifiers = [record["persistentId"] for record in records]
    if len(set(identifiers)) != len(identifiers):
        raise SyncError("prefab persistentIds collide")
    return records


def scenario_document() -> list[dict[str, Any]]:
    return [
        {
            "name": "Hot Potato: The Gateway Skillet",
            "description": (
                "The Arch stands in the middle of a colossal cast-iron skillet: a banked "
                "pan wall, two pour spouts, butter pools, a salt ring, three spatter "
                "geysers, a one-way skillet handle and a pantry of breakable boxes. "
                "Drive onto the medallion to pick up the potato; pass it before it pops. "
                "Requires the Hot Potato mod (hot_potato_ericrolph.zip)."
            ),
            "difficulty": 0,
            "authors": "Eric Rolph",
            "lapConfig": [],
            "forceNoCountDown": True,
            "extensions": [{"name": MOD_ID}],
            "vehicles": {PLAYER_NAME: {"playerUsable": True, "startFocus": True}},
            "prefabs": [],
        }
    ]


# --- generated Lua ------------------------------------------------------------


def _lua_number(value: float) -> str:
    if not math.isfinite(float(value)):
        raise SyncError("non-finite value in generated Lua")
    return repr(float(value))


def _lua_string(value: str) -> str:
    return json.dumps(value)


def _lua_string_list(values: list[str]) -> str:
    return "{" + ", ".join(_lua_string(value) for value in values) + "}"


def generated_lua_block(handoff: dict[str, Any], layout: dict[str, Any] | None = None) -> str:
    layout = layout or read_layout(handoff)
    sites = geyser_layout(handoff, layout)
    vehicles = vehicle_layout(handoff, layout)
    obstacles = obstacle_rows(handoff)
    arena_count = sum(1 for row in obstacles if row["source"] == "arena")
    level_count = len(obstacles) - arena_count
    lines = [GENERATED_BEGIN]
    lines.append(
        f"local CENTER = {{x = {_lua_number(CENTER[0])}, y = {_lua_number(CENTER[1])}, "
        f"z = {_lua_number(CENTER[2])}}}"
    )
    lines.append(f"local ARENA_RADIUS_M = {_lua_number(ARENA_RADIUS_M)}")
    lines.append(f"local GEYSER_POP_MPS = {_lua_number(layout['geyser_pop_mps'])}")
    lines.append(f"local DISPENSER_NAME = {_lua_string(DISPENSER_NAME)}")
    lines.append(f"local PLAYER_NAME = {_lua_string(PLAYER_NAME)}")
    lines.append(f"local BOOT_OPTION_KEYS = {_lua_string_list(list(BOOT_OPTION_KEYS))}")
    lines.append("local STATIC_NAMES = {")
    for instance in handoff["instances"]:
        lines.append(f"  {_lua_string(str(instance['name']))},")
    lines.append("}")
    lines.append("local VEHICLE_NAMES = {")
    for entry in vehicles:
        lines.append(f"  {_lua_string(entry['name'])},")
    lines.append("}")
    lines.append("-- Obstacle keep-outs for the runtime dodge hook (design §6.4a / v4 §7.3 R9).")
    lines.append("-- r = dodge keep-out, rp = measured physical radius of the solid")
    lines.append("-- (two-radius contract, geometry v3.5 / runtime serial 55). The name is")
    lines.append("-- local diagnostics only; rp_kind is authoring metadata and never ships.")
    lines.append("-- The arena's own rows come FIRST and are byte-identical to the gridmap_v2")
    lines.append("-- build; the level's solids (B2's stones, B4's props) follow. They go out")
    lines.append("-- in ONE call because the runtime REPLACES the set on every call.")
    lines.append(
        "local OBSTACLE_COUNTS = {arena = %d, level = %d, total = %d, cap = %d}"
        % (arena_count, level_count, len(obstacles), OBSTACLE_HOOK_CAP)
    )
    lines.append("local OBSTACLES = {")
    for obstacle in obstacles:
        lines.append(
            "  {name = %s, x = %s, y = %s, r = %s, rp = %s},"
            % (
                _lua_string(str(obstacle["name"])),
                _lua_number(obstacle["x"]),
                _lua_number(obstacle["y"]),
                _lua_number(obstacle["r"]),
                _lua_number(obstacle["rp"]),
            )
        )
    lines.append("}")
    lines.append("-- Spatter geyser sites (design §5.4): strip frame + cycle + emitter roles.")
    lines.append("local GEYSERS = {")
    for site in sites:
        lines.append("  {")
        lines.append(f"    name = {_lua_string(site['name'])},")
        lines.append(
            f"    cx = {_lua_number(site['cx'])}, cy = {_lua_number(site['cy'])}, "
            f"cz = {_lua_number(site['cz'])},"
        )
        lines.append(f"    tx = {_lua_number(site['tx'])}, ty = {_lua_number(site['ty'])},")
        lines.append(f"    nx = {_lua_number(site['nx'])}, ny = {_lua_number(site['ny'])},")
        lines.append(
            f"    half_len = {_lua_number(site['half_len'])}, "
            f"half_wid = {_lua_number(site['half_wid'])},"
        )
        lines.append(
            f"    off = {_lua_number(site['off'])}, on = {_lua_number(site['on'])}, "
            f"phase = {_lua_number(site['phase'])},"
        )
        lines.append(f"    wisp = {_lua_string_list([e['name'] for e in site['wisp']])},")
        lines.append(f"    curtain = {_lua_string_list([e['name'] for e in site['curtain']])},")
        lines.append("  },")
    lines.append("}")
    lines.append(GENERATED_END)
    return "\n".join(lines)


_BLOCK_PATTERN = re.compile(
    re.escape(GENERATED_BEGIN) + r".*?" + re.escape(GENERATED_END),
    re.DOTALL,
)


def splice_lua(source: str, block: str) -> str:
    if source.count(GENERATED_BEGIN) != 1 or source.count(GENERATED_END) != 1:
        raise SyncError("the scenario Lua must carry exactly one generated block")
    return _BLOCK_PATTERN.sub(lambda _match: block, source, count=1)


def thumbnail_bytes(render_path: Path = RENDER_PATH) -> bytes:
    """640x360 scenario thumbnail: the reviewed overview render, captioned."""

    with Image.open(render_path) as source:
        image = ImageOps.fit(source.convert("RGB"), (640, 360), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 316, 640, 360), fill=(18, 14, 12))
    draw.text((14, 326), "HOT POTATO: THE GATEWAY SKILLET", fill=(255, 196, 64))
    draw.text((14, 340), "a Hot Potato arena on Giant's Hearth by Eric Rolph", fill=(226, 218, 204))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def _jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records)


def render_outputs(
    handoff: dict[str, Any] | None = None, lua_source: str | None = None
) -> dict[Path, bytes]:
    """Every generated output as bytes, keyed by destination path."""

    handoff = handoff or read_handoff()
    layout = read_layout(handoff)
    lua_source = lua_source if lua_source is not None else LUA_PATH.read_text(encoding="utf-8")
    outputs = {
        PREFAB_PATH: _jsonl(prefab_records(handoff, layout)).encode("utf-8"),
        SCENARIO_PATH: (json.dumps(scenario_document(), indent=2) + "\n").encode("utf-8"),
        LUA_PATH: splice_lua(
            lua_source.replace("\r\n", "\n"), generated_lua_block(handoff, layout)
        ).encode("utf-8"),
        THUMBNAIL_PATH: thumbnail_bytes(),
    }
    for path, payload in outputs.items():
        if path.suffix != ".jpg" and b"\r" in payload:
            raise SyncError(f"generated text output carries CR bytes: {path}")
    return outputs


def main() -> None:
    outputs = render_outputs()
    written = []
    for path, payload in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != payload:
            path.write_bytes(payload)
            written.append(path.relative_to(EXAMPLE_ROOT).as_posix())
    handoff = read_handoff()
    layout = read_layout(handoff)
    records = prefab_records(handoff, layout)
    registry = obstacle_rows(handoff)
    print(
        json.dumps(
            {
                "handoff_schema": handoff.get("schema"),
                "layout_source": layout["_source"],
                "level_id": LEVEL_ID,
                "engine_convention_declared": handoff["_engine_convention_declared"],
                "obstacles": len(handoff["obstacles"]),
                "obstacles_level": sum(1 for row in registry if row["source"] == "level"),
                "obstacles_total": len(registry),
                "prefab_object_count": len(records),
                "statics": sum(1 for record in records if record["class"] == "TSStatic"),
                "vehicles": sum(1 for record in records if record["class"] == "BeamNGVehicle"),
                "emitters": sum(
                    1 for record in records if record["class"] == "ParticleEmitterNode"
                ),
                "written": written,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

# BeamNG.drive road & terrain pipeline

Incorporated 2026-09-17 from the user-supplied `agents.md` (BeamNG.drive Road & Terrain
Engineering Pipeline), reconciled against what this repository has **measured** on
BeamNG.drive 0.39.4.0 build 20972 while building `ericrolph_hot_potato_arena`
("Giant's Hearth", `examples/hot_potato_arena/`).

**Precedence.** `AGENTS.md` is the constitution and outranks this file. Where the incorporated
guide and one of this repo's measured laws disagree, **the measured law wins** and the conflict
is written down in §9 rather than quietly dropped — a third-party guide is a good prior, not
evidence. Anything in the guide this repo has not tested is marked **UNTESTED** and is a
candidate experiment, never a claim.

---

## 1. Invariants — adopted as written

* **World coordinates:** right-handed, Z-up (+X east, +Y north, +Z elevation).
* **Metric scale:** 1 unit = 1 m; every asset exports with scale applied (1, 1, 1).
* **Physics rate:** 2000 Hz. Collision meshes must be smooth enough not to micro-snag a
  wheel; a facet the solver sees at 2 kHz is a hammer blow, not a bump.
* **Separation of concerns:** never drive on a raw photogrammetry mesh. A physics surface is a
  retopologised strip or a dedicated Colmesh.

This repo already enforces the last two through `level/mesh_audit.py`, the husk/thin-shell
gates and `level/collider_probe.py`.

## 2. Level layout

The guide's layout is the hand-authored one. Ours is generated, and differs in three ways that
matter when reading either:

| Guide | This repo | Why |
|---|---|---|
| one `items.level.json` | `main/MissionGroup/<group>/items.level.json`, one per group | several rounds write the scene; a shared file loses objects silently (`AGENTS.md`, scene-index law) |
| one `main.materials.json` | a `*.materials.json` beside each art directory | keeps a round's materials in the round's own write set |
| hand-edited in F11 | rendered by `level/level_writer.py`, verified with `--check` | every byte gate depends on a reproducible build |

**Never hand-edit a generated file.** Change the generator and re-render.

## 3. Road tooling

### 3.1 DecalRoad vs MeshRoad

| | DecalRoad | MeshRoad |
|---|---|---|
| geometry | projected onto terrain | independent ribbon with side and bottom thickness |
| physics | inherits terrain collision **and friction** | own rigid collision body |
| ground type | from the terrain layer underneath | **ignores its material's `groundType`** (measured, §9) |
| navgraph | auto, via `drivable` + `drivability` | **none** — a MeshRoad joins no navgraph |
| use for | ground-level asphalt, dirt trails, markings, wear | bridges, viaducts, banked passes, elevated ramps, benches cut into a cliff |

### 3.2 Node placement

* 10–25 m on straights; 3–8 m through tight apexes and elevation change.
* **`textureLength` 4–10 m** for a normal road surface; drop to 3–5 m through hairpins or the
  UVs stretch. Measured against stock `SURFACE`-class roads: p05 2.0, **median 4.0**, p95 15.0 —
  so the guide's range is stock practice. This level ships 5–48 m on some roads; anything over
  ~15 m needs a reason written beside it.
* **Banking / superelevation:** 1.5–2.5 % cross-slope for drainage, up to 6–10 % on a banked
  corner. On a MeshRoad the per-node *normal* is the bank angle.
* Break a long road into **100–250 m segments** so occlusion culling can work. Never ship a
  multi-kilometre pass as one mesh.

### 3.3 Terrain conformation

A DecalRoad over unconformed terrain shows polygonal dips. Native flow: the road inspector's
**Terrain Actions** → border margin 1–3 m + smoothing → *Conform Terrain to Road*, then a soft
Gaussian sculpt brush to blend the shoulder.

In this repo the `.ter` is generated and frozen, so conformation happens in
`level/terrain_model.py` / `level/brink.py` at build time, not in the editor. Use the editor
route to *prototype* a shape, then move it into the generator.

## 4. Real-world elevation data

Source → process → import:

* **Sources:** USGS 3DEP (US, 1 m lidar), DEFRA (UK, 1 m / 50 cm), OpenTopography.
* **QGIS:** reproject to the target UTM zone (metric), clip to 2048 or 4096 m, export
  **16-bit** grayscale PNG. 8-bit causes stair-stepping that no amount of smoothing recovers.
* **Import:** new terrain block, 2048² or 4096², 1.0 m per pixel, height scale = the DEM's own
  `Zmax − Zmin` in metres.

Already exercised: the canyon skyline is USGS 3DEP 1 m lidar of the Island in the Sky rim above
the Shafer benches, Canyonlands (`authoring/design_amendments.md` A4), with provenance recorded
under `url` / `crs` / `place`. **Every GIS source ships a provenance entry; no BeamNG
proprietary data ever enters the repo.**

## 5. Materials (PBR 1.5) and ground type

```json
{
  "<name>": {
    "name": "<name>", "mapTo": "<name>", "class": "Material",
    "stage": [{ "colorMap": "...", "normalMap": "...", "roughnessMap": "...",
                "ambientOcclusionMap": "...",
                "pixelSpecular": true, "roughness": 1.0, "metallic": 0.0 }],
    "version": 1.5, "materialTag0": "Road", "groundType": "ASPHALT"
  }
}
```

`groundType` selects the tire-friction table: `ASPHALT` (µ≈1.0), `DIRT`, `GRAVEL`, `CONCRETE`.
**It does not reach the wheels through a MeshRoad** — see §9.

## 6. AI navigation

* A DecalRoad joins the navgraph by ticking **drivable** and setting **drivability**:
  1.0 paved highway, 0.5 rough backroad, 0.1 dirt track / service trail.
* A MeshRoad does not. To give one AI traffic, lay a hidden DecalRoad along the lane centre, or
  place explicit waypoints and connect them.
* Rebuild the nav map and test with radial AI spawning.

**Measured caveat:** `ai.set_line` is not a drivability proof — it left its own line by 12 m
within 60 m. Drivability is proven by steering the car yourself (`AGENTS.md`).

## 7. Blender road ribbons, when the native tools do not fit

Only when no native object does the job. Curve + array or geometry nodes; lanes 3.25–3.75 m;
1.5 % crown; 2–5 m vertex spacing on straights, 0.5–1.0 m in corners; weighted normals.

* **Dual mesh:** full-detail visual + simplified Colmesh with no drain grates or stripe geometry
  to catch a suspension.
* **Export:** Collada `.dae` (or `.cdae`), Z-up, +Y forward, transforms applied.
* **Trampoline effect:** if cars bounce on a custom road, the triangles are too big — subdivide
  to roughly 1×1 to 2×2 m quads.

## 8. QA protocol — the four gates

Run before finalising a package:

1. **Normal orientation** — every road normal points up. Inverted normals drop cars through.
2. **2000 Hz physics pass** — spawn a low-clearance car (Scintilla, Bastion) and drive the
   surface at **150 km/h**. Steering oscillation means micro-kinks in the spline or mesh: smooth
   it or add nodes. *This repo has no such gate yet — the canyon road was proven at climbing
   speed only. Adopted as a new gate.*
3. **Wall / guardrail snag** — drive flush against every curb and barrier; a wheel must not
   catch on a vertical seam. *New gate.*
4. **Drawcall budget** — 100–250 m segments, occlusion culling possible, no 10 km single mesh.
   *New gate; the shipped canyon MeshRoad is one 2,340 m object and has never been measured
   against it.*

## 9. Where the guide and measurement disagree

Each row is something this repo measured on the engine. **The measured column is what binds.**

| Topic | The guide says | This repo measured |
|---|---|---|
| `groundType` on a MeshRoad | assign top/side materials and the physics follows | wheels read `ASPHALT` regardless — tested with the deck material set to `ERHP_TRAIL` and then to stock `DIRT`, before and after `be:reloadCollision()`. The same probe reads `ICE` correctly off a TSStatic. A road that must grip like dirt is a **TSStatic + Colmesh**, or painted terrain. |
| decal layering | base road priority 1, lines 2, patches 3 (higher on top) | **a LOWER `renderPriority` draws ON TOP** (`level/level_writer.py:273`, calibrated against stock `postFx` ordering). Our stack runs 3–20 with the topmost layer lowest. |
| Colmesh naming | `Colmesh-wood` / `-metal` / `-asphalt` set sound and tire particles | **UNTESTED here, and it conflicts with a law we did measure**: only nodes named exactly `Colmesh-N` are collision-only and invisible; any other name *renders* (material-less geometry renders fallback orange). `Colmesh_<stem>-1` also works. If the suffix really does select a surface model it would settle the MeshRoad deck problem — **worth one experiment, not an assumption.** |
| level layout | one `items.level.json`, one `main.materials.json` | split per group and per art directory; a shared scene index dropped 153 objects four times |
| editor workflow | author in F11 | author in a generator; F11 is for prototyping and inspection. Frozen-spec and byte gates require a reproducible build. |

## 10. What this changes for Giant's Hearth

* Adopt QA gates 2–4 (§8) as real gates on the canyon road: a 150 km/h pass, a snag pass, and a
  segment/drawcall measurement.
* Run the `Colmesh-asphalt` experiment (§9) before accepting the deck's asphalt grip as permanent
  debt — it is the cheapest of the candidate fixes by a wide margin.
* `textureLength` on the shelf road is 12 m against a stock median of 4; check it for stretching
  through the road's tighter radii.
* The hidden-DecalRoad trick (§6) is the concrete route to AI traffic on the canyon road.

# Cannon Car Wash Technical-Art Overhaul

This is the production workflow for the Cannon Car Wash visual asset. It is intentionally tied to
the deterministic Blender generator, geometry handoff, BeamNG material definitions, and isolated
live gates in this repository. Do not make a one-off edit in the World Editor and treat it as source.

The authoritative BeamNG references are the official
[Materials 1.5 guide](https://documentation.beamng.com/modding/materials/materials_1.5/),
[texture-cooker rules](https://documentation.beamng.com/modding/materials/texture_cooker/),
[level lighting guide](https://documentation.beamng.com/modding/levels/level_creation/section7/),
[level optimization guide](https://documentation.beamng.com/modding/levels/level_creation/section8/),
and [Blender-to-DAE pipeline](https://documentation.beamng.com/modding/levels/level_creation/section11/).

## 1. Blender geometry and UV workflow

### Source-of-truth sequence

1. Work in metres, right-handed Z-up coordinates. Keep the wash drive axis at local `+Y` and its
   ground datum at local `Z=0`; do not compensate for BeamNG placement in the mesh.
2. Edit `blender/create_cannon_car_wash.py`, then rebuild `cannon_car_wash.blend`, the scenario
   Collada, selector Collada, geometry manifest, and selector handoff together.
3. Keep the four collision helpers simple and unchanged unless a physical opening changes. Visual
   corrugations, mortar, conduits, puddles, and brush cards do not belong in collision geometry.
4. Apply object scale before export, recalculate normals outside, triangulate at export, and inspect
   the generated Collada rather than trusting the Blender viewport alone.
5. Give every runtime object, mesh datablock, material, image, light, and animation the
   `ericrolph_cannon_car_wash_` prefix. The only exceptions are BeamNG's file-local collision helper
   names and intentional stock datablock references.

### Building surfaces

- Exterior structural wall faces use `ericrolph_cannon_car_wash_exterior_cmu`. Five real window
  openings per side are boolean-cut through each wall and its liner; the cutters stay strictly
  inside the wall bounding box, so the evaluated bounds feeding the selector cage are unchanged,
  and the metric UVs are re-authored after the cut so the masonry maps continuously around the
  reveals. Recessed glass and a stainless surround sit inside each opening; the simple collision
  shell stays solid behind the glass.
- Thin interior liners use `ericrolph_cannon_car_wash_interior_brick`; they remain inside the
  collision shell and never reduce the validated drive envelope.
- The floor uses `ericrolph_cannon_car_wash_wet_concrete`. Wet/dry breakup primarily lives in the
  roughness map, avoiding an expensive full-floor transparent overlay.
- Roof, fascia, and ceiling liner use `ericrolph_cannon_car_wash_corrugated_blue`.
- `UVMap` (the first/export UV set, commonly called UV0) uses dominant-axis metric box projection.
  Its per-material tile size is authored in the generator: approximately 0.8 x 0.4 m for masonry,
  2 x 2 m for the floor, and 1.2 x 1.2 m for corrugated panels. Keep corrugated ribs vertical on
  fascia/walls and longitudinal on the ceiling; never stretch one texture across an entire 18 m
  wall.
- `UVMap_2` (the second/export UV set, commonly called UV1) is currently a normalized
  dominant-axis projection on each source object. Its islands overlap after objects are joined. It
  is useful only for repeatable broad masks today; it is **not** a unique baked-lightmap/AO unwrap.
  Before using any BeamNG `*MapUseUV: 1` field for a baked atlas, create a non-overlapping 0..1
  unwrap with padding, regenerate the handoff/export, and prove it in the DAE and in game.

### Brush redesign

The original brushes used repeated box bristles. The production version uses a shared atlas and
radial card fans:

1. Keep a low-sided steel centre shaft as one submesh.
2. Build each vertical brush as the current 16 intersecting radial cards. Each card spans the brush
   height and inner-to-outer radius; mirrored backfaces are unnecessary because the material is
   double-sided.
3. Build the overhead brush as the current 14-card fan around its X-axis. It shares the
   vertical-brush atlas with rotated UVs.
4. Map every fin to 0..1. The atlas contains many independently alpha-clipped navy/cyan EVA strips,
   colour-dilated past the opaque edge to prevent dark mip halos.
5. Join all cards for one animated brush into one mesh with one `brush_cards` material. The shaft is
   the only additional material slot. Preserve one named spinner root and the shared `ambient`
   animation sequence.
6. Use alpha test, not alpha blending. Alpha test writes depth and avoids the severe card-ordering
   artifacts that appear when several rotating transparent planes overlap.

If a future close-up LOD needs more silhouette motion, use 24–36 two-quad ribbons only for a tightly
bounded LOD0, the current 16/14-card fans for LOD1, and an opaque low-sided cylinder plus shaft for
LOD2. Each successive LOD should roughly halve triangles while preserving the five animation
channels. Measure alpha overdraw before adding cards; silhouette quality alone does not justify a
fill-rate regression.

### Detail geometry

Use short, low-sided cylinders and joined meshes for the following readable details:

- stainless water manifolds and inward-facing nozzle heads;
- red/blue utility piping, electrical conduit, and compact junction boxes;
- drain grates recessed visually into the floor;
- yellow/black track warnings and wheel guides;
- payment screen, emergency-stop button, bollards, and entrance clearance bar;
- a few thin puddle/decal meshes only where the base floor roughness cannot sell pooled water.

Keep repeated fittings in one joined object per material. Bevel only silhouette-critical edges; a
normal map and weighted normals should carry sub-centimetre detail.

## 2. BeamNG PBR material setup

The build script at `textures/build_pbr_textures.py` creates 22 power-of-two source maps. Base colour
is saved as `*.color.png` (sRGB), tangent normals as `*.normal.png` (OpenGL Y+), and roughness, AO,
and opacity as grayscale `*.data.png` (linear). The sign emissive RGB map is also linear
`*.data.png`. The CMU, interior-brick, and corrugated tiles are drawn procedurally at true metric
scale — the CMU tile is exactly two 390 x 190 mm blocks per course over 0.8 x 0.4 m, the ivory-buff
brick tile is six 190 x 65 mm modular bricks across eight courses over 1.2 x 0.6 m, and the
corrugated tile carries six 0.2 m-pitch trapezoidal ribs — with wrap-periodic cell hashing so every
tile is seamless by construction rather than mirrored. Their normal and AO maps derive from a real
metric height field (mortar recess, arris rounding, rib profile), not a luminance guess. Only the
wet-concrete floor still starts from a photo source; it is made seamless with an offset cross-fade
plus periodic value noise, and its tile-edge saw-cut joints land on the 2 x 2 m UV grid so the whole
floor reads as jointed slabs.

Each material uses only relevant maps. Masonry, concrete, and factory-painted corrugated steel are
dielectric at the paint surface, so they use `metallicFactor: 0.0` and omit metallic maps. Bare
stainless details use a numeric metallic factor. The brush alone uses opacity. The sign alone uses
emissive. This avoids allocating meaningless textures just to fill every possible slot.

Channel responsibilities are:

- base colour/albedo: sRGB surface colour only, with no baked sun, lamp, specular highlight, or AO;
- normal: linear tangent-space OpenGL Y+ micro-surface direction, never a substitute for silhouette;
- roughness: linear perceptual microsurface variation—low for wet patches/stainless, high for CMU,
  rubber, mortar, and dry concrete;
- metallic: linear mask or factor, 1 only where bare metal is visible and 0 for masonry, water,
  rubber, cloth/EVA, and factory paint;
- ambient occlusion: linear small-scale cavity attenuation, kept subtle and independent of scene
  lighting;
- opacity: linear alpha-test mask for brush-card cutouts; colour is dilated beyond its opaque edge;
- emissive: linear RGB mask/factor for sign and fixture self-illumination; a real PointLight or
  SpotLight is still required to illuminate nearby geometry and vehicles.

The following two-entry template shows the complete mapped surface, alpha-test, and emissive
patterns without combining physically unrelated opacity and emission on one material:

```json
{
  "ericrolph_cannon_car_wash_example_cards": {
    "name": "ericrolph_cannon_car_wash_example_cards",
    "mapTo": "ericrolph_cannon_car_wash_example_cards",
    "class": "Material",
    "persistentId": "replace-with-a-stable-unique-uuid",
    "Stages": [
      {
        "ambientOcclusionMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example_ao.data.png",
        "baseColorMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example.color.png",
        "metallicFactor": 0.0,
        "normalMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example.normal.png",
        "opacityMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example_opacity.data.png",
        "roughnessMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example_roughness.data.png"
      },
      {},
      {},
      {}
    ],
    "alphaRef": 96,
    "alphaTest": true,
    "doubleSided": true,
    "translucentBlendOp": "None",
    "version": 1.5
  },
  "ericrolph_cannon_car_wash_example_sign": {
    "name": "ericrolph_cannon_car_wash_example_sign",
    "mapTo": "ericrolph_cannon_car_wash_example_sign",
    "class": "Material",
    "persistentId": "replace-with-another-stable-unique-uuid",
    "Stages": [
      {
        "baseColorMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example_sign.color.png",
        "emissive": true,
        "emissiveMap": "/art/shapes/ericrolph_cannon_car_wash/textures/example_sign_emissive.data.png",
        "emissiveFactor": [2.6, 3.2, 4.0],
        "metallicFactor": 0.0,
        "roughnessFactor": 0.32
      },
      {},
      {},
      {}
    ],
    "castShadows": false,
    "version": 1.5
  }
}
```

For large tiling surfaces, UV0 supplies the primary repetition. Optional `detailMap`,
`detailNormalMap`, `detailNormalMapStrength`, and `detailScale` can add micro breakup without another
mesh/material slot. The current overlapping second UV channel may carry only non-baked procedural
masks; do not select it with `*MapUseUV: 1` for a unique AO/lightmap until it has been replaced by a
padded non-overlapping unwrap. Do not bake a directional lamp or sun into base colour.

### Texture cooking

1. Keep the wet-concrete source image under `textures/source/` and rebuild the 22 PNG authoring
   maps once; the masonry, corrugated, brush, and sign maps are fully procedural.
2. Install the unpacked development mod into the sentinel BeamNG profile.
3. Start one visual asset session and allow the game to cook the complete batch.
4. Check `beamng.log` for texture-cooker errors.
5. Run `textures/cook_release_textures.py collect --profile-current <sentinel-current>`; it rejects
   missing/invalid DDS magic, dimensions, or channel class before copying from
   `temp/art/shapes/.../textures`.
6. Keep material paths pointed at the PNG names. BeamNG resolves the cooked DDS beside the logical
   source path.
7. The public ZIP contains the cooked runtime textures selected by the explicit distribution
   allowlist; authoring sources and prompts stay outside `mod/`.

## 3. Signage and lighting entity setup

The sign is a tower-mounted cabinet package, all outside the building at y <= -9.25 so the drive
envelope is untouched:

1. A raised deep-blue entrance tower fascia (7.30 x 0.14 x 2.10 m, z 4.00-6.10, its bottom matching
   the existing header soffit) carries a 5.00 x 0.25 x 1.36 m cabinet, a stainless retainer frame
   wrapping the 4.8 x 1.2 m UV-mapped face at (0, -9.639, 4.90), two stainless downlight cans on
   arms, and a stainless cannon-barrel finial with a hazard-yellow muzzle ring breaking the coping
   line along the launch arc. The face uses the 2048x512 sign atlas: circular cannonball-comet
   badge, "CANNON" (Bahnschrift Bold Condensed) beside "WASH" (SemiLight Condensed), and a
   safety-orange "WASH · WAX · LAUNCH" tagline pill.
2. The same face uses a separate emissive mask and restrained HDR factor that lights only the
   graphic elements — letters, badge, and the pill with knocked-out dark text — so the night read
   is channel-lit signage on a dark panel. Emission drives bloom but does not cast useful light on
   vehicles or asphalt.
3. Two namespaced SpotLights at the entrance provide real illumination. Their exact production
   transforms and settings are listed below; both remain shadowless in this release.

The production rig contains exactly thirteen bounded, shadowless lights:

- five cool-blue PointLights at local positions `[0, -6.8, 4.34]`, `[0, -3.4, 4.34]`,
  `[0, 0, 4.34]`, `[0, 3.4, 4.34]`, and `[0, 6.8, 4.34]`, colour `[0.56, 0.82, 1.0]`,
  brightness 1.45, radius 5.0;
- four warm-white wall task-fill PointLights at `[-/+2.7, -/+4.6, 3.9]`, colour
  `[0.92, 0.96, 1.0]`, brightness 1.15, radius 3.8, each anchored to an emissive WallPack
  fixture on the pier between the windows so the source reads;
- two entrance/sign SpotLights at local positions `[-1.9, -8.72, 4.08]` and
  `[1.9, -8.72, 4.08]`, local direction `[0, -0.97, -0.24]`, and two mirrored exit SpotLights at
  `[-1.9, 8.72, 4.08]` and `[1.9, 8.72, 4.08]`, direction `[0, 0.97, -0.24]` — all four colour
  `[0.1, 0.64, 1.0]`, brightness 1.8, range 7.5, inner angle 28 degrees, outer angle 48 degrees;
- all thirteen have shadows disabled. Add a shadow caster only after a measured night composition
  demonstrates that the added GPU and CPU cost is worth it.

The Blender generator owns local light anchors and emits their exact transforms into the geometry
manifest. `sync_scenario_outputs.py` converts those into persistent PointLight/SpotLight prefab
records. The selector manager creates equivalent non-saveable scene objects, multiplies each local
anchor by the placed prop transform, and deletes them with the prop. Test a nonzero prop yaw; a light
that only works at world rotation zero is not complete.

At dusk/night, validate front, rear, tunnel-centre, brush close-up, and sign views. Check for light
leaking through the roof, blown-out letters, overlapping shadow noise, wet-floor fireflies, and
lights left behind after deleting the selector prop.

## 4. Performance checklist

These are project budgets, not claimed engine limits. The current measured baseline is the primary
regression target:

- scenario DAE: 13,830 rendered triangles, 34 geometry/primitive groups, 18 materials;
- consolidated selector DAE: 13,782 rendered triangles and 18 primitive/material groups;
- separate vehicle-local animated DAE: retain five independently animated brush channels rather
  than joining them into an unanimated static draw;
- whole visible LOD0 hard gate: at or below 15,000 rendered triangles;
- all brush cards/ribbons: target below 2,500 triangles;
- complete authored material inventory: 18; do not add a new material when an atlas or existing PBR
  surface can carry the detail;
- primitive-group budgets: no more than 36 for the scenario and 20 for the consolidated selector;
- one object with one material is one baseline draw call; every extra material slot adds another;
- each LOD should roughly halve both triangles and material count;
- tileable CMU, brick, concrete, and corrugated sets: 1K in this release; move to 2K only after a
  measured close-up shows 1K is insufficient;
- brush atlas: 512; signage atlas (entrance sign + wash-menu board + exit strip): 2048x1024;
  small prop atlas: 512–1K;
- use grayscale BC4-ready data maps and BC5-ready normal maps rather than RGB where one/two channels
  suffice;
- avoid 4K textures, a light per fluorescent tube, overlapping translucent puddles, and individual
  bristle objects;
- keep the current thirteen lights shadowless; a future pass may use at most one carefully
  measured shadow-casting key with a 256–512 px shadow map;
- keep particle counts bounded and turn all wash effects off when the last vehicle leaves;
- test on a mid-range target as well as the RTX 5090. The fast development GPU is not the audience's
  VRAM or fill-rate budget.

Record triangles, vertices, object count, material count, texture inventory, light count, cooker
errors, and representative frame timing in the geometry/validation manifests before release.

## 5. Efficient inspection and release validation

Do not cold-start BeamNG after every Lua edit:

1. Run static JSON/JBeam/DAE/material contracts first.
2. For Lua-only work, use one sentinel-owned BeamNG process with an unpacked development mod, reload
   the namespaced extension in-process where safe, and run a small repair/countdown/occupancy matrix.
3. Read structured namespaced Lua events and warnings incrementally from `beamng.log`; query exact
   transforms, OOBBs, integrity, velocity, triggers, effects, and lights through GELua/BeamNGpy.
4. For texture/mesh work, batch edits before one cold asset-cache load. Capture canonical day and
   dusk RenderViews and inspect them semantically; pixel variance alone cannot detect a floating
   prop, stretched UV, or sideways nozzle.
5. Treat a local GPU vision/VLM review as advisory. Numeric ground-contact, centerline, quaternion,
   containment, cleanup, and damage assertions remain deterministic release gates.
6. Phase 4 includes the Phase 3 scenario path; do not run both on every iteration. The normal final
   matrix is four cold starts: Phase 2 asset/material/light resolution, Phase 4 complete scenario,
   selector-runtime/city-bus, and one exact prebuilt-ZIP proof.

The narrow Phase 3 and selector-spawn tests remain available when a failure needs isolation. They
are not additional ritual gates after the broader tests pass. The normal edit loop should need one
targeted session and one exact-package proof—not repeated full-game restarts after each source edit.

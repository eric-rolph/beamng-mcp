# Cannon Car Wash provenance

This record is source-side submission evidence. It is not included in the public mod ZIP.

## Authorship and runtime content

- Author and submitter: Eric Rolph.
- Runtime namespace: `ericrolph_cannon_car_wash`.
- Geometry origin: generated from `blender/create_cannon_car_wash.py` and saved/exported with
  Blender 4.5.4 LTS. The scenario DAE is 10,714 triangles across 33 primitive groups; the
  consolidated selector DAE is 10,666 triangles across 18 groups. A separate vehicle-local DAE
  preserves five independent animated brush channels.
- Physics origin: the 79-node, 329-beam JBeam cage is derived deterministically from evaluated
  Blender bounds recorded in `authoring/ericrolph_cannon_car_wash.selector_handoff.json`. Its 144
  collision triangles and 79 fixed nodes total 15,125 kg.
- Ground datum: the evaluated selector handoff records
  `ericrolph_cannon_car_wash_ground_reference` at exact BeamNG coordinates `[0, 0, 0]` and
  `ericrolph_cannon_car_wash_ground_back` at `[0, 3, 0]`; those authored coordinates are used
  directly by the JBeam reference frame and surface-Z placement contract.
- Sign source: `textures/build_pbr_textures.py` draws the source-side sign atlas with Arial Bold,
  falling back to Segoe UI Bold if Arial is unavailable. The release contains the derived sign DDS,
  not a font file or converted 3D text geometry.
- Materials: 18 namespaced BeamNG PBR materials authored here. Four AI-generated source images feed
  deterministic tileable colour/normal/roughness/AO derivation; brush-card and sign maps are
  generated procedurally. The release contains 22 verified BeamNG-cooked DDS files and no PNG
  authoring sources.
- Audio: none.
- Lua origin: the scenario-owned extension, selector vehicle bootstrap, shared light specification,
  and on-demand GE manager are authored for this mod. They share no copied third-party code and
  retain distinct scenario and selector lifecycles.
- Third-party models, scripts, textures, audio, or maps copied into the mod: none.
- External inspiration content copied from HavocNG or another creator: none.
- Repository gallery images: captured in-game by the opt-in Phase 4 RenderView gate at 1280x720 on
  BeamNG.drive 0.38.6, once before entry and once after all wash effects were live.
- Repository icon: created with the built-in OpenAI image editor using only this mod's authored
  Blender render as its reference, then downsampled to the required 96x96 JPEG. It contains no
  third-party imagery.
- Selector and scenario thumbnails: rendered from this authored asset; no third-party image was
  used.

## AI-generated texture sources

All four base-colour sources were generated with Codex's built-in `imagegen` capability. The
generation-session originals were copied byte-for-byte into `textures/source/`; the repository copy
is the stable authoring input. No web image, stock texture, BeamNG asset, or creator screenshot was
used as a generation reference.

| Repository source | Generation-session original | Prompt record |
| --- | --- | --- |
| `textures/source/cmu_source.png` | `C:\Users\ericr\.codex\generated_images\019f7ce9-56d1-7b90-acb2-e3235924b731\exec-d7eb9363-5c4b-43d6-9c32-184a3048ebe4.png` | “Perfectly seamless square orthographic game-ready PBR base-colour texture of commercial split-face gray CMU block, restrained mortar variation and industrial grime, no perspective, no directional lighting, no baked shadows, no text, logos, objects, or border; opposing edges tile continuously.” |
| `textures/source/interior_brick_source.png` | `C:\Users\ericr\.codex\generated_images\019f7ce9-56d1-7b90-acb2-e3235924b731\exec-39eac2c5-ef28-4f6e-8a25-56339e2f561d.png` | “Perfectly seamless square orthographic game-ready PBR base-colour texture of dark industrial interior brick for a wet commercial car-wash tunnel, restrained mortar variation and water staining, no perspective, directional lighting, baked shadows, text, logos, objects, or border; opposing edges tile continuously.” |
| `textures/source/wet_concrete_source.png` | `C:\Users\ericr\.codex\generated_images\019f7ce9-56d1-7b90-acb2-e3235924b731\exec-d6a98dcd-fd29-4d8d-af76-6c96f19d5278.png` | “Perfectly seamless square orthographic game-ready PBR base-colour texture of wet commercial concrete flooring, subtle pooled-water and soap variation with restrained industrial grime, no perspective, directional lighting, baked shadows, text, logos, objects, or border; opposing edges tile continuously.” |
| `textures/source/corrugated_blue_source.png` | `C:\Users\ericr\.codex\generated_images\019f7ce9-56d1-7b90-acb2-e3235924b731\exec-84719d32-7000-4114-b4db-89d44512ed2a.png` | “Create a perfectly seamless, square, orthographic game-ready PBR base-color texture for painted commercial corrugated metal siding used on a modern car-wash roof and fascia. Deep saturated cobalt blue factory-painted steel, narrow vertical ribs evenly spaced, subtle realistic edge wear and water streaks, restrained industrial grime, physically plausible color variation, no perspective, no directional lighting, no baked shadows, no text, no logos, no objects, no border. The left/right and top/bottom edges must tile continuously. Clean high-frequency detail suitable for a 1024x1024 base-color map.” |

`textures/build_pbr_textures.py` mirror-tiles and resamples those sources to deterministic
power-of-two maps. It derives conservative OpenGL-Y+ normals, roughness, and AO from luminance;
those maps are approximations rather than photogrammetric height data. It also builds the
colour-dilated 512 brush atlas, opacity/roughness/normal maps, and the 1024x256 dual-layer sign.
`authoring/ericrolph_cannon_car_wash.textures.json` locks dimensions, channel mode, and SHA-256 for
all 22 logical PNGs. `textures/cook_release_textures.py` accepts cooked DDS files only when header,
dimensions, and channel family match the corresponding source map.

## Referenced BeamNG resources

The runtime refers to, but does not redistribute, these BeamNG-provided resources:

- Gridmap V2
- Gavril D-Series model `pickup` and `default_vehicle`
- Wentward DT40L model `citybus`, configuration `city`, metadata source
  `vehicles/citybus/info_city.json`, and nominal validation envelope 3.11 x 12.63 x 2.994 m
  (validation target only; not redistributed)
- particle emitter `BNGP_sprinkler`
- particle emitter `BNGP_waterfallsteam` (stock particle `BNG_waterfallsteam`)
- particle emitter `BNGP_34` (stock particle `BNG_steam_light_exhaust`)
- particle emitter `BNGP_2` (stock particle `BNG_dust_light`)
- emitter datablock `lightExampleEmitterNodeData1`
- `/levels/gridmap_v2/art/shapes/grid/s_gm_block_16mX2mX8m.dae`

The two static Collada files and the vehicle-local animated Collada use numeric preview materials
and contain no external image references. Runtime texture mapping lives in namespaced
`main.materials.json` files, whose logical `.png` paths resolve to the shipped cooked DDS payloads.
Generated JBeam and material files use the strict-JSON subset of BeamNG's JSONC-compatible formats.

The authored namespace is covered by collision checks against the installed BeamNG 0.38.6 content
and Repository audit set. No exact authored-name conflict was found. Generic `Cube*`/`Cylinder*`
export IDs were removed; the remaining `Colmesh-*` object names are BeamNG collision-recognition
conventions with namespaced geometry IDs.

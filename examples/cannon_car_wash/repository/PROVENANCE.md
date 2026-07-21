# Cannon Car Wash provenance

This record is source-side submission evidence. It is not included in the public mod ZIP.

- Author and submitter: Eric Rolph.
- Runtime namespace: `ericrolph_cannon_car_wash`.
- Geometry origin: generated from
  `blender/create_cannon_car_wash.py` and saved/exported with Blender 4.5.4 LTS.
- Physics origin: the 79-node, 329-beam JBeam cage is derived deterministically from evaluated
  Blender bounds recorded in `authoring/ericrolph_cannon_car_wash.selector_handoff.json`. Its 144
  collision triangles and 79 fixed nodes total 15,125 kg.
- Ground datum: the evaluated selector handoff records
  `ericrolph_cannon_car_wash_ground_reference` at exact BeamNG coordinates `[0, 0, 0]` and
  `ericrolph_cannon_car_wash_ground_back` at `[0, 3, 0]`; those authored coordinates are used
  directly by the JBeam reference frame and surface-Z placement contract.
- Text geometry: Blender's built-in font was converted to mesh during procedural authoring.
- Materials: authored as numeric PBR factors. The mod contains no imported textures.
- Audio: none.
- Lua origin: the scenario-owned extension, selector vehicle bootstrap, and on-demand GE manager
  are authored for this mod. They share no copied third-party code and have distinct lifecycles.
- Third-party models, scripts, or maps copied into the mod: none.
- External inspiration content copied from HavocNG or another creator: none.
- Repository gallery images: captured in-game by the opt-in Phase 3 RenderView gate at 1280x720
  on BeamNG.drive 0.38.6, once before entry and once after all wash effects were live.
- Repository icon: created with the built-in OpenAI image editor using only this mod's authored
  Blender render as its reference, then downsampled to the required 96x96 JPEG. It contains no
  third-party imagery.
- Selector and scenario thumbnails: rendered from this authored asset; no third-party image was
  used.

The runtime refers to, but does not redistribute, these BeamNG-provided resources:

- Gridmap V2
- Gavril D-Series model `pickup` and `default_vehicle`
- particle emitter `BNGP_sprinkler`
- particle emitter `BNGP_waterfallsteam` (stock particle `BNG_waterfallsteam`)
- particle emitter `BNGP_34` (stock particle `BNG_steam_light_exhaust`)
- particle emitter `BNGP_2` (stock particle `BNG_dust_light`)
- emitter datablock `lightExampleEmitterNodeData1`
- `/levels/gridmap_v2/art/shapes/grid/s_gm_block_16mX2mX8m.dae`

The two Collada files have no external image references. Generated JBeam and material files use
the strict-JSON subset of BeamNG's JSONC-compatible formats.

The authored namespace is covered by collision checks against the installed BeamNG 0.38.6 content
and Repository audit set. No exact authored-name conflict was found. Generic
`Cube*`/`Cylinder*` export IDs were removed; the remaining
`Colmesh-*` object names are BeamNG collision-recognition conventions with namespaced geometry IDs.

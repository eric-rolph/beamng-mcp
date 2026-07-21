# Cannon Car Wash provenance

This record is source-side submission evidence. It is not included in the public mod ZIP.

- Author and submitter: Eric Rolph.
- Runtime namespace: `ericrolph_cannon_car_wash`.
- Geometry origin: generated from
  `blender/create_cannon_car_wash.py` and saved/exported with Blender 4.5.4 LTS.
- Physics origin: the 77-node JBeam cage is derived deterministically from evaluated Blender
  bounds recorded in `authoring/ericrolph_cannon_car_wash.selector_handoff.json`.
- Text geometry: Blender's built-in font was converted to mesh during procedural authoring.
- Materials: authored as numeric PBR factors. The mod contains no imported textures.
- Audio: none.
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
- emitter datablock `lightExampleEmitterNodeData1`
- `/levels/gridmap_v2/art/shapes/grid/s_gm_block_16mX2mX8m.dae`

The two Collada files have no external image references. Generated JBeam and material files use
the strict-JSON subset of BeamNG's JSONC-compatible formats.

The final namespace and 42 persistent UUIDs were checked against all 167 BeamNG 0.38.6 content
archives and the 58 Repository ZIPs installed in the isolated audit set. No exact authored-name or
UUID conflict was found. Generic `Cube*`/`Cylinder*` export IDs were removed; the remaining
`Colmesh-*` object names are BeamNG collision-recognition conventions with namespaced geometry IDs.

# Cannon Car Wash texture authoring

This directory contains source-side texture inputs and the deterministic BeamNG cook handoff. Only
the 22 verified cooked DDS files under `../mod/art/shapes/ericrolph_cannon_car_wash/textures/` enter
the public ZIP. Do not copy `source/`, `generated_png/`, prompts, or this README into the mod.

## Inputs and ownership

The four files in `source/` are project-owned base-colour inputs generated with Codex's built-in
`imagegen` capability:

- `cmu_source.png`: commercial split-face gray CMU;
- `interior_brick_source.png`: dark wet-tunnel industrial brick;
- `wet_concrete_source.png`: commercial concrete with subtle pooled-water variation;
- `corrugated_blue_source.png`: cobalt factory-painted corrugated metal.

The exact prompts, generation-session paths, authorship declarations, and downstream derivation are
recorded in [`../repository/PROVENANCE.md`](../repository/PROVENANCE.md). These four copies are the
stable repository inputs; machine-local generated-image paths are evidence, not build dependencies.

## Deterministic authoring build

From the repository root:

```powershell
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\textures\build_pbr_textures.py
```

The builder mirror-tiles and resamples the base images, then writes 22 maps to `generated_png/` and
locks their dimensions, channel modes, and SHA-256 values in
`../authoring/ericrolph_cannon_car_wash.textures.json`:

- four 1024 square tileable colour maps, each with OpenGL-Y+ normal, roughness, and AO maps;
- a 512 brush-card colour/normal/opacity/roughness atlas with colour dilation beyond the alpha edge;
- a 1024x256 sign colour map and linear emissive mask generated with Arial Bold or the Segoe UI
  Bold fallback.

Normals and AO derived from source luminance are conservative approximations. They are suitable for
this release but should not be described as scanned or physically measured height data. A future
height-authoring pass must replace the inputs, regenerate the manifest, and rerun visual/cook gates.

## BeamNG texture cook

BeamNG materials keep logical `.png` paths even though the public release carries cooked DDS files.
Use only a sentinel-isolated BeamNG profile:

```powershell
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\textures\cook_release_textures.py stage
# Launch one isolated visual asset session and allow BeamNG to cook the batch.
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\textures\cook_release_textures.py collect `
  --profile-current '<sentinel BeamNG user profile>\current'
```

`stage` copies only the manifest-backed PNG set into the runtime texture location. `collect` verifies
the DDS magic, image dimensions, and expected RGB/RGBA or single-channel class before copying it
into the release tree; it then removes the staged runtime PNGs. Review new `beamng.log` bytes for
texture-cooker warnings or errors before accepting the batch.

Release invariants:

- exactly 22 namespaced DDS files in the runtime texture directory;
- no PNG, source prompt, generator output directory, cache file, or unnamespaced texture in `mod/`;
- colour maps are treated as sRGB; `.normal` and `.data` maps are linear;
- grayscale AO, roughness, and opacity remain single-channel cooked payloads;
- `main.materials.json` paths retain their logical names and are validated in BeamNG, not only by a
  JSON parser or Blender's numeric preview materials.

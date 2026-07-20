# Roadmap

## Near term

- Expand the sentinel-gated local BeamNG.drive harness to BeamNG.tech and record versioned results
- Camera semantic/depth ground-truth backend for oracle comparisons
- Route planner and waypoint fusion for the hybrid controller
- Transactional cloned-level editing with World Editor undo/rollback, save previews, artifact
  manifests, and no writes to shipped game archives
- Expand the typed ephemeral `BeamNGTrigger` v1 lifecycle beyond live-tested Box enter/exit event
  emission only after each new shape/action receives a dedicated safety review and runtime matrix
- Managed motion/path runtime for bridge-created props and triggers, including bounded looping,
  pause/resume/stop, ownership, and cleanup
- Typed River/water-volume authoring with validated geometry, flow/material parameters, preview,
  and transactional persistence in cloned levels
- Artifact-hash review manifests and one-shot operator approvals for executable mod installation
- Expand the concrete-ramp build/load regression into mod-specific deterministic smoke scenarios,
  BeamNG log collection, and reusable disposable-profile provisioning
- Texture-hashed multi-material/multi-flexbody Blender handoffs and selector-preview generation
- A separate level-asset/TSStatic handoff with texture provenance, semantic path rebasing, and a
  cloned-level workflow; do not overload the vehicle/JBeam soft-body contract
- Animation-preserving visual export with an explicit rule that animated visuals never substitute
  for JBeam collision or mechanism physics
- A versioned multi-body mechanism schema with actuator-only connectivity, separate evidenced
  subassemblies, and more than one structural asset per mod
- Automated soft-body spawn/settle/impulse and actuator-limit sweeps with debug-data capture
- TensorRT-RTX standalone EP ABI integration and cache management
- Low-rate asynchronous VLM advisor that cannot issue direct actuation
- Multi-vehicle engine-side lease telemetry and deterministic lease-expiry fault injection

Tutorial workflows sometimes queue raw Lua or edit BeamNG's installed ZIP archives directly.
Those shortcuts are deliberately excluded: new scene/runtime features must use typed allowlisted
schemas, and authored content must remain in user-folder overlays or transactional cloned levels.

## Protocol evolution

- Migrate the isolated MCP adapter to Python SDK v2 after the stable release and client ecosystem
  settle
- Adopt the future MCP Tasks extension only after it is standardized and supported; retain domain
  job IDs for backward compatibility
- Package to PyPI, then publish `server.json` to the official MCP Registry

## Evaluation

- Reproducible episode manifests and reports
- Scenario suites for weather, lighting, traffic, damaged sensors, and bridge loss
- Safety-gate suites for existing-object edits, exact-level saves, executable mod installation, and
  engine-side lease expiry
- Latency histograms, route completion, lane departures, collisions, damage, and emergency reasons
- Optional dataset recording/export that never commits copyrighted BeamNG assets

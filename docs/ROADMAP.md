# Roadmap

## Near term

- Automated local BeamNG.tech integration harness with recorded versioned results
- Camera semantic/depth ground-truth backend for oracle comparisons
- Route planner and waypoint fusion for the hybrid controller
- Cloned-level workflow with World Editor undo transactions and save previews
- Artifact-hash review manifests and one-shot operator approvals for executable mod installation
- Mod-specific deterministic smoke scenarios, BeamNG log collection, and disposable user folders
- Texture-hashed multi-material/multi-flexbody Blender handoffs and selector-preview generation
- A versioned multi-body mechanism schema with actuator-only connectivity, separate evidenced
  subassemblies, and more than one structural asset per mod
- Automated soft-body spawn/settle/impulse and actuator-limit sweeps with debug-data capture
- TensorRT-RTX standalone EP ABI integration and cache management
- Low-rate asynchronous VLM advisor that cannot issue direct actuation
- Multi-vehicle engine-side lease telemetry and deterministic lease-expiry fault injection

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

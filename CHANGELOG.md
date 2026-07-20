# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project
uses semantic versioning after the initial alpha series.

## [Unreleased]

## [0.2.0] - 2026-07-19

### Added

- Four soft-body authoring tools, one schema resource, and a guided Blender-to-BeamNG prompt
- Version-controlled Blender exporter for evaluated world-space vertices, explicit coordinate
  transforms, sparse cage topology, roles, bounds, volume, and hash-bound DAE evidence
- Expiring single-use Blender inboxes with fixed paths, stable reads, Collada security checks, and
  transactional binary/text mod bundle commits
- Deterministic JBeam compiler for exact nodes, explicit beams and X-braces, collision triangles,
  heavy/fixed bases, mass distribution, four starting material baselines, hydros, and
  rails/slidenodes
- Full canonical build provenance and assembled-mod recompilation/hash validation
- End-to-end soft-body methodology, Blender 5.2/DAE compatibility notes, and manual physics smoke
  checklist

## [0.1.0] - 2026-07-19

### Added

- FastMCP v1 local server with 47 typed tools, four resource patterns, and three prompts
- BeamNGpy 1.35.1 simulator/vehicle/scenario/sensor/map adapter
- Authenticated loopback GELua WebSocket bridge
- Confined mod authoring, validation, packaging, install backups, and jobs
- Default-off executable-mod installation, file/count/byte quotas, and stage-aware bounded jobs
- Managed-only map edits by default, a separate existing-object gate, and exact-level save checks
- Native AI plus classical, SegFormer, and ONNX/TensorRT vision control paths
- Python stale-frame watchdog plus a vehicle-scoped, engine-real-time GELua safety lease that
  brakes on missed renewal and reports `engine_deadman_*` status
- Post-0.37 `BeamNG.drive.ini` user-folder discovery and `modScript.lua` bridge activation
- Windows diagnostics, hardened Lua installer, documentation, security policy, tests, and CI

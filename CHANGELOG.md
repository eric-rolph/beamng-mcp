# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project
uses semantic versioning after the initial alpha series.

## [Unreleased]

### Changed

- Constrain `onnxruntime-gpu` below 1.27 for the CUDA 12.8 Windows profile because ONNX Runtime
  1.27 removed CUDA 12 support

### Fixed

- Make `doctor --json` distinguish advertised ONNX CUDA/TensorRT providers from provider libraries
  whose native dependencies actually load
- Import PyTorch's compatible CUDA/cuDNN runtime before ONNX session creation and exercise a
  session that reports active CUDA inference beside BeamNG; CPU fallback remains explicit in
  runtime status
- Serialize BeamNGpy connect, status, disconnect, and shutdown transitions; make cancellation wait
  for in-flight worker cleanup; and keep failed shutdowns retryable instead of closing the executor
  around a live session
- Dispose of provisional BeamNGpy sessions and launched processes when setup or the initial
  capability probe fails, including raw-process fallback, exited-process detection, and retained
  ownership when every termination path fails
- Reset and automatically restart the Lua WebSocket listener before processing a native event batch
  that exceeds strict count/byte work bounds, closing peers and fail-safe braking instead of
  silently discarding or deferring tail commands; mission transitions use the same reset boundary
  so stale native events cannot execute in the next mission
- Strengthen the real soft-body regression to prove the generated node/beam topology, total mass,
  and vehicle directory loaded in BeamNG
- Cover positive hydro, rail, and slidenode serialization and remove the unsupported claim that v1
  compiles a tested hinge/torsion composition

## [0.3.0] - 2026-07-20

### Added

- Six typed, ephemeral `BeamNGTrigger` tools with connection-owned drafts, explicit
  enable/disable, Box geometry, typed modes/tests, and loss-aware cursor paging over bounded
  vehicle enter/exit events
- A sentinel-gated BeamNG 0.38.6 trigger regression covering a real vehicle enter/exit sequence,
  injection and foreign-owner rejection, disable/re-enable, confirmed deletion, and owner cleanup
- Runtime Blender discovery and a fail-closed `doctor` capability probe that reports the exact
  executable/version, selection-only Collada operator, and glTF availability
- Opt-in real-runtime regressions for transformed Blender exports, Blender MCP profile registration,
  isolated BeamNG/Lua/vehicle control, an end-to-end concrete-ramp build/install/load, and rendered
  GPU perception through a test-only retail RenderView fixture with an optional downloads-disabled
  CUDA SegFormer baseline
- BeamNGpy 1.35 call-signature compatibility coverage and loopback WebSocket fault-injection tests

### Changed

- The Python bridge client now verifies trigger-method capability advertisement before any trigger
  request and directs stale installations to `install-lua --force`
- Trigger deletion uses strict boolean confirmation; uncertain mutation timeouts/cancellation close
  the owning peer; and failed exact engine cleanup is retained as ownerless, event-silent quarantine
- BeamNG launch configuration accepts an explicit direct `beamng.binary`; an active user folder
  named `current` is preserved for mod/token operations while its parent is passed to `-userpath`
- Soft-body setup now documents the validated side-by-side Blender 4.5.4 LTS/Blender MCP 1.6.4
  profile, capability-first checks, and transcript-derived visual-animation/JBeam collision boundary
- Retail BeamNG.drive 0.38.6 is documented as rejecting BeamNGpy `Camera`; production
  camera-driven autonomy remains in the BeamNG.tech tier
- Live regressions lock the sentinel-marked profile, reserve random tcom/WebSocket ports, rotate
  its bridge credentials, require process ownership before mutation, and restore bridge config

### Fixed

- Probe Blender Doctor capabilities against the active Blender MCP user/add-on profile, rejecting
  duplicate DAE exporters, and require all four deterministic glTF export options before reporting
  glTF available
- Decode Blender STRING point attributes as UTF-8 bytes and reject invalid encodings instead of
  emitting Python byte-literal node IDs
- Discover only DAE export operators, avoiding ambiguity with the matching Collada import operator
- Call BeamNGpy's `tech_enabled()` method instead of treating its method object as true, and fall
  back to each connected vehicle's State sensor when retail Drive rejects batched state requests
- Accept BeamNG's validated one-time native WebSocket information preamble while preserving strict
  malformed-message, correlation-ID, expected-method, authentication, and subprotocol checks
- Flag whitespace-obfuscated and member-qualified Lua `load`, `loadstring`, and `dostring`
  dynamic evaluation while ignoring longer identifiers such as `preload`
- Reject relative Blender visual/manifest output paths before normalization and report the bounded
  active-profile DAE operator set when capability probing finds a missing or ambiguous exporter
- Make post-swap mod-install recovery identity-bound and no-clobber: remove only proven-owned new
  files, restore overwritten files safely, and preserve concurrent replacements plus recovery data
- Confine every live-test mutation to a sentinel profile without junction/reparse traversal, defer
  extension loads until process ownership is proven, and bound terminate/kill/wait cleanup

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

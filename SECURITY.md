# Security Policy

## Supported versions

Until the first stable release, only the current `main` branch receives security fixes.

## Reporting a vulnerability

Please use GitHub's private security advisory flow for this repository. Do not open a public issue
for a vulnerability involving arbitrary code execution, path escape, authentication bypass,
secret disclosure, or unsafe vehicle actuation. Include version, environment, reproduction steps,
and impact. Do not include real credentials.

## Threat model

The AI client and model output are treated as untrusted. BeamNG, operator-approved installed mods,
local model weights, and the workstation remain part of the trusted local computing base. A mod
authored by the model is not trusted merely because it validates or packs successfully. This
project reduces risk; it cannot sandbox a compromised game installation, executable mod, or
malicious native model runtime.

Primary risks:

- arbitrary code execution through simulator scripting
- arbitrary file read/write or path traversal
- unauthorized loopback access or DNS rebinding
- secret disclosure through logs/tool results
- stale learned controls continuing after failure
- destructive map or mod changes
- denial of service through frames, arrays, payloads, or jobs

## Controls

- No direct arbitrary Lua-eval, Python, shell, or BeamNGpy `queue_lua_command` MCP tool. Installing
  a model-authored Lua mod is nevertheless code execution inside BeamNG, so installation is
  disabled by default with `workspace.allow_mod_install = false` and still requires confirmation
  after operator opt-in.
- GELua has a fixed command allowlist, per-install token, constant-time token comparison,
  heartbeat expiry, bounded payload/queue handling, and loopback binding.
- stdio default; optional HTTP is loopback-only, bearer-authenticated, and Host/Origin protected.
- Mod I/O is rooted, canonicalized, file/count/byte-bounded, symlink/reparse-point-aware, atomic,
  and revision-aware.
- Bridge-managed map objects are the default mutation scope. Editing pre-existing level objects
  requires a separate default-off Python/Lua gate.
- Persistent map save requires independent Python and Lua configuration gates, confirmation, and
  the exact loaded level identifier. Object and vehicle deletion also require confirmation.
- Sensor arrays/images become local artifacts instead of unbounded MCP JSON.
- The real-time supervisor independently watches frame age and command deadlines and brakes on
  failure/shutdown.
- Every automated-driving mode must arm an authenticated, vehicle-scoped GELua lease before it
  starts. Healthy progress renews the lease; engine-real-time expiry disables AI and applies full
  service plus parking brake even if Python is stalled. Explicit stop brakes before disarming.
- `emergency_stop` attempts supervisor, BeamNGpy, and GELua paths independently where available.
- Secrets are never committed or printed by installer/doctor commands.

## Deployment guidance

- Keep all game/control endpoints on `127.0.0.1`.
- Prefer stdio.
- Do not port-forward the WebSocket, BeamNGpy port, or MCP HTTP endpoint.
- Use a dedicated BeamNG user folder for testing. On BeamNG 0.37+, resolve it from `userFolder` in
  `%LOCALAPPDATA%\BeamNG\BeamNG.drive.ini`; the Windows default is
  `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current`.
- Work only on cloned/user levels and source-controlled mod workspaces.
- Keep `allow_mod_install`, `allow_existing_map_object_edits`, and
  `allow_persistent_map_edits` false unless a specific reviewed workflow requires them.
- Review third-party model licenses and use safe weight formats where possible.
- Treat optional native GPU runtimes as privileged code.
- Keep a keyboard/controller emergency-stop path outside the AI system.

The engine lease depends on BeamNG's GELua update loop and cannot act if the game process itself is
frozen. It protects the `autonomy_start` workflows, not real vehicles or an operator's explicit
one-shot `vehicle_control` calls.

BeamNG's own BeamNGpy protocol is unencrypted and unauthenticated and should remain local. The Lua
token does not add authentication to BeamNGpy itself.

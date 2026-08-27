# beamng-mcp — session entry point

`AGENTS.md` in this directory is the authoritative repository constitution: architecture and
ownership boundaries, the gated Blender→BeamNG pipeline, the Cannon Car Wash baseline, Repository
policy, validated runtimes, and the accumulated hard-won engine laws. **Read the sections of
`AGENTS.md` relevant to your task before changing protocol, safety, structural, packaging, or
live-simulator behavior.** This file only routes; it never overrides that document.

The knowledge ladder, most-current first:

1. `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/TOOLS.md`, `docs/SOFTBODY_AUTHORING.md` —
   system design and the opt-in live gates.
2. The test suites are the gates: static suites always; `lupa` state-machine suites from the repo
   venv (they SKIP silently without lupa); `*_live.py` only against the sentinel-isolated profile.
3. `AGENTS.md` — the constitution, including per-mod round ledgers and engine laws.
4. `examples/giant_props/workflow_archive/` — frozen as-run critic/audit harnesses. Reference
   designs only; never re-run them.

Operational facts every session needs:

- Venv python: `.\.venv\Scripts\python.exe`. Blender: side-by-side 4.5.4 at
  `C:\Users\ericr\Applications\Blender\4.5.4\blender.exe` (see `AGENTS.md` for invocations).
- Giant props build: `python examples/giant_props/build.py <key> prop|dist|harvest` — `dist` is a
  RE-ZIP of `mod/`, never a rebuild, and `prop` can downgrade cooked textures without a certified
  harvest manifest. Read the release re-cut law in `AGENTS.md` before touching a shipped mod.
- Local play deployment: `python examples/giant_props/deploy_local.py` reports the REAL profile
  (`%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods`) against every release lock; `--deploy`
  syncs what is stale, hash-verified. Tests and fixtures NEVER go to the real profile — live
  gates use the sentinel profile env vars in `AGENTS.md` and install through the service.
- Generated release-bound text files must be written with `newline="\n"`; JBeam/material outputs
  stay strict JSON.
- Do not commit, push, merge, or publish a mod unless the user explicitly asks.

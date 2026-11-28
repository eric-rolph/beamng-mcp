# beamng-mcp — session entry point

`AGENTS.md` in this directory is the authoritative repository constitution: architecture and
ownership boundaries, the gated Blender→BeamNG pipeline, the Cannon Car Wash baseline, Repository
policy, validated runtimes, and the accumulated hard-won engine laws. **Read the sections of
`AGENTS.md` relevant to your task before changing protocol, safety, structural, packaging, or
live-simulator behavior.** This file only routes; it never overrides that document.

The knowledge ladder, most-current first:

1. `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/TOOLS.md`, `docs/SOFTBODY_AUTHORING.md` —
   system design and the opt-in live gates. `docs/BEAMNG_LEVEL_PIPELINE.md` — the road/terrain/
   forest pipeline for level work (native editors, GIS heightmaps, PBR 1.5, navgraph, QA gates);
   its §9 records where the incorporated third-party guide loses to a measurement.
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
- Hot Potato arena (Shell-B scenario, `examples/hot_potato_arena/`): re-cut =
  `sync_scenario_outputs.py` → `python -m examples.hot_potato_arena.build_distribution --overwrite`;
  its lock chains to the Hot Potato lock and it is NOT in `deploy_local.py`'s table (see its README).
- Giant's Hearth level (same directory, `level/`): start from `ROUND_HANDOFF.md` there. Full cut =
  `python -m examples.hot_potato_arena.level.build_level_zip --members-file
  examples/hot_potato_arena/level/members_full_level.json --stage-into <clean dir> --overwrite`;
  install level + arena to the real profile and BeamMP with `install_level.py --deploy`. Level
  rounds run under the capped critic process in `AGENTS.md` ("the round process, capped").
- Local play deployment: `python examples/giant_props/deploy_local.py` reports the REAL profile
  (`%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods`) against every release lock; `--deploy`
  syncs what is stale, hash-verified. Tests and fixtures NEVER go to the real profile — live
  gates use the sentinel profile env vars in `AGENTS.md` and install through the service.
- Generated release-bound text files must be written with `newline="\n"`; JBeam/material outputs
  stay strict JSON.
- Do not commit, push, merge, or publish a mod unless the user explicitly asks.

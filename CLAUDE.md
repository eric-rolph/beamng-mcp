# beamng-mcp — session entry point

This repository is the BeamNG.drive MCP server and the frameworks around it: the BeamNGpy
adapter, the GELua bridge, the Blender-to-BeamNG export pipeline, the JBeam and Collada writers,
the vision backends, and the gates that hold all of it honest. It is Windows-first and
loopback-only by design.

**The mods are not here.** Six GIS-derived maps, the giant props pack and the Cannon Car Wash
live in [`beamng-mods`](https://github.com/eric-rolph/beamng-mods), a private repository, with
their build scripts, their per-mod gates and their authoring ledgers. If a task is about the
geometry, materials, ledger or release of a specific mod, it belongs there. If it is about the
machinery that produces mods, it belongs here.

`AGENTS.md` in this directory is the authoritative repository constitution: architecture and
ownership boundaries, the gated Blender→BeamNG pipeline, Repository policy, validated runtimes,
and the accumulated hard-won engine laws that apply to the pipeline itself. **Read the sections
of `AGENTS.md` relevant to your task before changing protocol, safety, structural, packaging, or
live-simulator behavior.** This file only routes; it never overrides that document.

The knowledge ladder, most-current first:

1. `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/TOOLS.md`, `docs/SOFTBODY_AUTHORING.md` —
   system design and the opt-in live gates.
2. The test suites are the gates: static suites always; `*_live.py` only against the
   sentinel-isolated profile.
3. `AGENTS.md` — the constitution.

Operational facts every session needs:

- Venv python: `.\.venv\Scripts\python.exe`. Blender: side-by-side 4.5.4 at
  `C:\Users\ericr\Applications\Blender\4.5.4\blender.exe` (see `AGENTS.md` for invocations).
- Run the suite as `python -m pytest`, never the bare `pytest` entry point: the live gates import
  `tests.live_support`, which only resolves because `-m` puts the working directory on `sys.path`.
- Tests and fixtures NEVER go to the real BeamNG profile — live gates use the sentinel profile
  env vars in `AGENTS.md` and install through the service.
- Generated release-bound text files must be written with `newline="\n"`; JBeam/material outputs
  stay strict JSON.
- Do not commit, push, merge, or publish unless the user explicitly asks.

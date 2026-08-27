# Workflow archive

As-run multi-agent workflow harnesses, rescued 2026-08-26 from Claude Code
session directories (`~/.claude/projects/.../workflows/scripts/` and session
temp scratchpads) before garbage collection. These are the scripts behind the
critic/audit rounds referenced in commit messages ("COLOSSUS round 7:
UNANIMOUS", "the verifier round") and AGENTS.md's round ledgers. They are the
seed corpus for codifying the critic loop as a repo-owned workflow (Gatehouse
Phase 3).

**Frozen as-run. Do not re-run them.** Each script hardcodes absolute repo
paths, a round-specific CONTEXT block (the previous round's work order and
what was done about it), and that round's evidence set. Re-running a frozen
round against today's tree judges the wrong artifact with the wrong context.
Read them as reference designs; extract the patterns into a parameterized
harness instead.

## Contents and provenance

Filenames are cleaned of `-wf_<runid>` suffixes; bytes and mtimes are as
found. Origin sessions, for locating the full run transcripts while they
still exist (`subagents/workflows/wf_*/` in the same session dirs):

| Directory | Origin session | Dates | What ran |
| --- | --- | --- | --- |
| `colossus_tire/` r1–r7 | `2820968f` | 08-24 → 08-26 | The complete six-lens critic loop on COLOSSUS: six specialist critics (tire-engineering, beamng-physics, mesh-quality, texture-materials, gameplay, pipeline) + a chair who re-verifies findings against the source before issuing a ranked work order; looped until round 7 came back unanimous 6/6 wowed. r1–r3 were auto-persisted by the Workflow tool; r4–r7 were invoked via scriptPath from the session scratchpad. |
| `colossus_tire/verdicts/` | `2820968f` | 08-24/25 | Raw lens verdict payloads; by timestamp these are the round-1 and round-2 outputs (23:12 08-24 and 01:03 08-25). Later rounds' verdicts live only in the run transcripts and the AGENTS.md ledger. |
| `giant_fan/` | `dc3b5fb8` | 08-25 | Giant Fan artifact critic panel + a resume harness (continuing a killed/paused panel — the resume pattern itself is worth keeping). |
| `slope_fix/` | `dd04b8ae` | 08-24 | The getRotation()-stale-on-slopes campaign: an understand workflow (parallel readers over the gate + runtime), a fix-review panel, and the boot_of_doom repository-update bundle. |
| `spin_launch/` | `f76d9835` | 08-24 | Checkpoint-1 geometry review and the repair-design judge panel (29 KB — the largest harness here; multiple competing repair designs, scored). |
| `pack_2026-08/` | `01aac343` | 08-06 → 08-13 | The pack-era generation: build chiefs with worker+critic pairs (centrifuge), mass build of mods 14–17 with per-mod adversarial critics, read-only pack-wide audits with an adversarial refute phase, listing-copy blitz, pachinko/sumo look-and-feel pairs. |

## Patterns worth extracting into the shared harness

- **Lens panel + chair**: N specialist critics with disjoint briefs; a chair
  who re-verifies every finding against the tree (drops none silently) and
  emits a ranked work order. Stop condition: unanimity.
- **Audit → adversarial refute**: a read-only auditor per mod, then a
  verifier whose job is to kill weak findings. Findings that survive are
  worth human attention; the rest never reach it.
- **Worker+critic pairs until wowed**: per-component build loops where the
  critic "defaults to NOT wowed" and judges rendered pixels, not intentions.
- **Round context handoff**: each round's CONTEXT block lists the previous
  work order and what was done, and instructs the panel to *verify rather
  than trust* the claims.
- **Concurrent-sibling discipline**: the read-only audits open with ABSOLUTE
  CONSTRAINTS blocks because sibling workflows were writing the same repo —
  the textual ancestor of the one-live-consumer / exclusive-session rules.
- **Resume harness**: `giant-fan-critics-resume.js` shows the shape of
  continuing a partially-completed panel without re-judging finished lenses.

## Deliberately not rescued

- `lensB2–B10.py`, `phys_relax_lensB.py` (colossus session scratchpad):
  iterative drafts of the physics-lens relax solver; the finished version is
  the unilateral-contact settle gate in `tests/test_colossus_tire_geometry.py`.
- `patch_criticA/B.py`, `patch_panel_round1–4.py` (high_five session
  scratchpad): one-shot repair scripts whose results are already in the specs
  and shipped textures.
- High Five's critic/verifier rounds: they ran as plain subagent calls, not
  Workflow scripts — no harness files exist. Their evidence renders are
  already in `high_five/authoring/review/`; the narrative is in AGENTS.md.
- Reference JPEGs from the high_five scratchpad (`REF_*.jpg`): provenance
  unknown, possibly third-party — per repo policy they stay out.

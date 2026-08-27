export const meta = {
  name: 'spin-launch-cp1-geometry',
  description: 'Apply the Spin Launch Tier-1 geometry repairs, rebuild, and prove them',
  phases: [
    { title: 'CP0', detail: 'land the new gates first, so the findings are encoded as failing tests' },
    { title: 'CP1', detail: 'apply the datum, clearance, envelope and console-geometry edits; rebuild until green' },
    { title: 'CP1r', detail: 'render the five shots the gates cannot see' },
    { title: 'Verify', detail: 'independent adversarial re-derivation from the rebuilt artifacts' },
  ],
}

const SCRATCH = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr-beamng-mcp/f76d9835-91b3-4c0d-a814-0663fa155ef1/scratchpad'

const CONTEXT = `
# Spin Launch — Tier 1 geometry repair

Repo: C:\\Users\\ericr\\beamng-mcp. The mod is \`spin_launch\` in the
\`examples/giant_props\` pack. A car drives up a ramp, through an airlock, into a
vacuum chamber standing on edge, and is flung out a launch tube that pivots
around the rim to stay tangent to the release point.

## YOUR SOURCES OF TRUTH — READ THESE FIRST, IN FULL

1. \`${SCRATCH}/master_plan.md\` — the reconciled master plan. Sections:
   §0 datum-safety proof, §1 the eighth defect, §2 conflict rulings, §3 merged
   text for conflicting hunks, §4 the staged tier tables, §5 the checkpoint
   schedule and HARD ORDERING RULES, §6 cut list, §7 verification plan.
2. \`${SCRATCH}/plans/\` — the seven source plans as JSON, each with an
   \`edits\` array of {file, rationale, old, new}. The master plan refers to
   these as "P1 e1", "P2 e5" and so on. The mapping:
   - P1 = plan_spawn_datum__re_datum_spin_launch_so_aut.json  (21 edits)
   - P2 = plan_swept_volume_clearance.json                    (11 edits)
   - P3 = plan_pressure_envelope__the_omitted_arc_openi.json  (10 edits)
   - P4 = plan_state_machine_defects_in_the_gelua_behav.json  (23 edits)
   - P5 = plan_the_console_and_its_instruments.json           (24 edits)
   - P6 = plan_audio___procedural_cue_set__generator__a.json  (17 edits)
   - P7 = plan_test_coverage___what_the_three_existing_.json  (22 edits)
   \`edits[i]\` is 0-indexed in the JSON; "e1" means the FIRST edit.

**§3 of the master plan overrides the source plans wherever they overlap.**
Everything not in §3 applies verbatim from its source plan.

## THE BUILD CHAIN

\`\`\`
A: .venv/Scripts/python.exe examples/giant_props/build.py spin_launch textures
B: "C:/Users/ericr/Applications/Blender/4.5.4/blender.exe" --factory-startup --background --python examples/giant_props/spin_launch/blender/create_spin_launch.py
C: .venv/Scripts/python.exe examples/giant_props/build.py spin_launch all
\`\`\`

Behaviour CODE (the Lua in spec.py) re-splices on every run of C. \`BEHAVIOR\`
params, geometry, the cage, the handoff, the jbeam, the DAE hashes and the zip
lock move **only** through B. **Never run C alone after a geometry edit** — that
ships new Lua against the OLD handoff and the machine holds every part in the
wrong place while reporting healthy.

Blender takes ~2 minutes. Use a 600000 ms timeout on those Bash calls.

## RULES

- **Never weaken, skip, xfail or delete a gate to make it pass.** The only
  sanctioned xfail in this plan is \`sumo_gyro_platform\` in the new ref-node
  gate, which the plan specifies as \`xfail(strict=True)\` with a tombstone.
  If a gate fails, fix the thing it is testing.
- Preserve this codebase's commenting culture. Every non-obvious constant
  carries a derivation and the reason it is what it is. The plans supply that
  text — use it. Do not strip comments to save space.
- \`examples/giant_props/**\` is stored byte-for-byte (\`.gitattributes\`:
  \`-text\`). Write files with explicit \`newline="\\n"\` where you control it.
- Do not commit to git.
- Do not launch BeamNG. A later checkpoint does that.
- Derive, never guess. If you must invent a number the plans did not supply,
  show the arithmetic in the comment.
`

phase('CP0')
const cp0 = await agent(CONTEXT + `
## YOUR TASK: CP-0 — land the gates BEFORE the fixes

Apply, from the plans, ONLY the new/changed test files. Per master plan §4
(T1-37, T1-39, T1-40, T1-41) and §3.11:

1. \`tests/live_support.py\` — P7's \`purge_cached_prop_meshes\` helper, plus its
   safety tests in \`tests/test_live_support.py\`. This deletes a directory
   inside a real player profile, so match the file's existing confinement
   idioms EXACTLY (\`require_confined_profile_target\`, the reparse/symlink
   rejection, \`cleanup_exact_live_artifacts\`). It must be impossible for it to
   escape the sentinel profile.
2. \`tests/test_giant_props_pack.py\` — insert, in this order, before
   \`test_materials_cover_all_referenced\`:
   a. P1's \`test_reference_node_is_the_lowest_node\` (the jbeam version, with
      the handoff cross-check and the \`sumo_gyro_platform\` xfail tombstone),
   b. P7's \`test_panel_button_chain_is_wired_end_to_end\` verbatim.
3. New file \`tests/test_spin_launch_clearance.py\` — P2's module, MINUS the two
   \`BORE_SLOT_DEG\` assertions (ruling §2.1 cut that constant).
4. New file \`tests/test_spin_launch_geometry.py\` — P7's module.
5. New file \`tests/test_spin_launch_envelope.py\` — P3's module.

Then run:
\`\`\`
.venv/Scripts/python.exe -m pytest -q tests/test_live_support.py tests/test_giant_props_pack.py tests/test_spin_launch_geometry.py tests/test_spin_launch_clearance.py tests/test_spin_launch_envelope.py
\`\`\`

**EXPECT RED, and the reds are the point.** Per §5 CP-0 the expected failures are:
- \`test_reference_node_is_the_lowest_node[spin_launch]\` — lift 3.000
- \`[sumo_gyro_platform]\` — xfail (so: xfailed, not failed)
- the corridor gate on \`part:beacon\` at tilts 34/39/45 and on node
  \`bore_1_00_1\` at tilt 72
- the envelope gate's two AST tests

\`test_panel_button_chain_is_wired_end_to_end\` must be **GREEN today** on all 20
props. If it is red, you have mis-transcribed it — fix the test, not the props.

Report: exactly which tests are red and whether that set matches the plan's
prediction. Any red the plan did NOT predict is a transcription bug or a real
new finding — say which, with evidence.
`, { label: 'cp0:gates-first', phase: 'CP0', effort: 'high' })

phase('CP1')
const cp1 = await agent(CONTEXT + `
## YOUR TASK: CP-1 — apply the geometry tier and rebuild until green

The gates from CP-0 are already in the tree and RED. Here is that agent's
report:

${cp0}

Apply master plan §4 **TIER 1 items T1-01 … T1-25** and **TIER 2 items
T2-01 … T2-09**. That is: the datum re-work, the swept-volume clearance block,
the pressure envelope, the merged \`build_chamber\`/\`build_slot\`, the annular
bore caps, and the console/instrument geometry.

**Do NOT apply** T1-26…T1-33 (behaviour Lua), T1-34/T1-35 (needles/bars),
T1-36/T1-38/T1-43 (live gate), or anything in Tier 3. Those are later
checkpoints.

### Obey the hard ordering rules in §5 exactly

1. **T1-12 before T1-13 and T1-14.** \`swept_edge_deg\`, \`TUBE_SWEPT_R\`,
   \`SWEPT_CLEARANCE_MIN\` and the derived \`SLOT_DEG\` are all defined in T1-12.
   Landing T1-13 alone is a \`NameError\` at import that breaks the ENTIRE pack.
2. **T1-17 before T1-18** (\`_theta_at_z\` reads \`TUNNEL_TOP_Z\`).
3. **T1-15 and T1-11 are a pair.**
4. Apply §3's merged text wherever it covers a hunk; source plans elsewhere.
5. Take the §3.7 comment ledger — Plan 5 solved its layout against the OLD
   datum, so ~40 of its world-z comments are stale by exactly +3.0.

### The one edit the planner could not execute

**T1-25, the annular bore caps (§3.6).** \`oriented_cylinder\` defaults
\`cap=True\`, so eleven flanges plus the collar, seal, muzzle and hazard band are
**fifteen solid steel discs across a 2.55 m bore**. Looking down the muzzle you
see a wall. The planner wrote a \`tube_ring\` helper against \`grid_surface\`'s
signature but could not run it, and flagged that a winding or \`outward\`
mismatch renders it as a hole — a NEW instance of the defect it closes.

Read \`grid_surface\` and \`_winding_is_wrong\` in the generator (~line 137)
before you write this. \`outward\` for a flat annulus is the tube AXIS (or its
negative) depending on which end of the barrel section the face caps. Get it
right, and prove it in the CP-1r render.

\`tube_breech\` at \`TUBE_S0 - 0.5\` **keeps its cap** — it is the closed back of
the barrel and is supposed to be solid.

### Then rebuild and get green

Run **A → B → C**, then the whole static suite plus the new gates:
\`\`\`
.venv/Scripts/python.exe -m pytest -q tests/test_giant_props_pack.py tests/test_spin_launch_sequence.py tests/test_spin_launch_geometry.py tests/test_spin_launch_clearance.py tests/test_spin_launch_envelope.py tests/test_live_support.py
\`\`\`

**All four CP-0 reds must go green** (\`sumo_gyro_platform\` stays xfail).
Iterate: fix, rebuild, re-run. Blender is ~2 min; budget for several passes.

Report: every edit applied and any you could not; the before/after of the four
CP-0 reds; the final node/beam/triangle/part counts and zip lock; anything in
the plans that turned out to be wrong when it met the real file, with evidence.
`, { label: 'cp1:geometry', phase: 'CP1', effort: 'high' })

phase('CP1r')
const renders = await agent(CONTEXT + `
## YOUR TASK: CP-1r — render the five shots no gate can see

CP-1 is applied and the static gates are green. Here is its report:

${cp1}

Master plan §5 CP-1r calls these non-negotiable. Write a THROWAWAY preview
script in \`${SCRATCH}\` (do NOT add it to the repo) that imports the generator
module and renders. There is an existing one at
\`${SCRATCH}/preview_spin_launch.py\` — read it; it already shows the idiom
(importlib-load \`create_spin_launch.py\`, call \`build_materials\`,
\`build_visual\`, \`build_parts\`, then \`blender_kit.render_thumbnail\`). The
generator's \`main()\` is behind an \`__main__\` guard so importing is safe.

Render, at 1100x700 or better, into \`${SCRATCH}/cp1r/\`:

a. **tilt 34** and **tilt 72** from the +Y quarter, crown / lower jamb / beacon
   in frame. These are the elevations nothing in the evidence chain has ever
   rendered, and where the beacon used to sit inside the bore. To pose the tube
   at a non-default tilt you must apply the runtime's own transform yourself:
   the tube part rotates about the chamber axis by
   \`radians(tilt - TILT_REF_DEG)\` about authored +X through \`spec.HUB\`, and
   the muzzle hatch is carried with it. Do it in the preview script, in Blender,
   by rotating those objects — do not change the generator.
b. **Down the bore from the muzzle**, at tilt 50 AND tilt 34. This is the ONLY
   proof of T1-25 and the single most important shot. If you see a disc, the
   fix did not land.
c. **The portal from the plaza** — spandrels closed, no open sky over the mouth.
d. **The chamber interior at low elevation** — the closed bore liner.
e. **The console at 2 m** — typography, needles, purge guard, status stack.

Plus, because §7 flags it as unproven: **the full machine from the approach**,
showing the 24 m longer ramp that nobody has ever seen.

Then LOOK at every render with the Read tool and report honestly what you see.
For each shot: does it prove what it was supposed to prove? Any hole, backwards
winding, z-fight, gap, or floating geometry? Be specific about which render and
where in frame.

Report the absolute path of every render you produced.
`, { label: 'cp1r:renders', phase: 'CP1r', effort: 'high' })

phase('Verify')
const CHECKS = [
  {
    key: 'clearance',
    prompt: `Re-derive the SWEPT-VOLUME CLEARANCE from the REBUILT artifacts, independently.
Load \`examples/giant_props/spin_launch/authoring/ericrolph_spin_launch.handoff.json\`
and \`spec.py\`. For every collision node and every part pivot in the SHIPPED
handoff, at all eight elevation rungs, compute the perpendicular distance to the
launch tube's bore axis and to the barrel steel. Report the full table and the
global minimum. The claim to refute is that nothing now intrudes into the 2.55 m
bore and nothing rides inside the barrel steel. Do NOT read the clearance gate's
code and echo it — derive it yourself from first principles and see if you agree.`,
  },
  {
    key: 'envelope',
    prompt: `Re-derive the PRESSURE ENVELOPE from the REBUILT artifacts, independently.
The claim to refute: every arc omitted from the chamber shell and bore liner is
now fully covered — by the tunnel box, by the new spandrels, or by the shingle
leaves — with no residual open sky and no open side strips. Compute the omitted
arcs from \`spec.py\`, compute what each plugging surface actually subtends at
each radius and in x, and report any residual gap in square metres. Also verify
the shingle leaf union covers \`SLOT_DEG\` including the overlap. Derive it
yourself; do not just read the envelope gate.`,
  },
  {
    key: 'datum',
    prompt: `Verify the RE-DATUM landed correctly and completely, from the REBUILT artifacts.
Check: (a) in the shipped jbeam, the ref node IS the lowest node, to 1e-6;
(b) every other prop in the pack still satisfies that, except the tombstoned
\`sumo_gyro_platform\`; (c) the ramp's authored foot is at ground level and its
grade is what \`RAMP_GRADE\` claims, computed from the actual cage nodes;
(d) the chamber's lowest outer point sits above the plinth bottom;
(e) nothing in \`spec.py\` or the generator still carries a stale absolute z from
the old datum — audit BOTH files for numeric literals and comments that no
longer match the value they name. Report every stale comment you find, with
file and line.`,
  },
  {
    key: 'regression',
    prompt: `Hunt for REGRESSIONS the gates would not catch.
CP-1 changed the datum, the slot arcs, the chamber arcs, the baffle position, the
rib fan, the console rows and added annular caps. Diff the REBUILT handoff
against what you can infer of the previous one, and look for: parts whose pivot
moved unintentionally; cage nodes that lost or gained collision; triangles that
became degenerate; UV scales that are now wrong because a surface changed size;
materials that lost their only referencing mesh; flexbody groups that no longer
bind. Also re-run the whole static suite yourself and read the ZIP: confirm it
contains the current runtime.lua and the current DAEs, and that no build input
(a .glb, a source PNG that should not ship) leaked in. Report anything that
looks off, even if every gate is green.`,
  },
]
const verdicts = await parallel(CHECKS.map(check => () =>
  agent(CONTEXT + `
## YOUR TASK: adversarial verification — ${check.key}

CP-1 has been applied and rebuilt. Here is the implementer's report:

${cp1}

You are the check on it. **You are READ-ONLY — do not edit any file, do not
rebuild, do not launch Blender or BeamNG.** Run read-only commands and
throwaway Python only.

${check.prompt}

Assume the implementer's report is optimistic. Your job is to find where it is
wrong. If you agree with it, say so with your own numbers, not by restating its.
`, { label: `verify:${check.key}`, phase: 'Verify', effort: 'high' })
))

return { cp0, cp1, renders, verdicts: verdicts.filter(Boolean) }

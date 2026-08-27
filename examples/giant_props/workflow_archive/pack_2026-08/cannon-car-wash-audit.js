export const meta = {
  name: 'cannon-car-wash-audit',
  description: 'Adversarial physics/behaviour audit of the Cannon Car Wash mod (v1.47)',
  phases: [
    { title: 'Audit', detail: 'read-only auditor over the shipped car wash' },
    { title: 'Refute', detail: 'adversarial verifier kills weak findings and catches misses' },
  ],
}

const READONLY = `
ABSOLUTE CONSTRAINTS - two sibling workflows are concurrently reading and WRITING
in this same repository:
- DO NOT edit, create or delete ANY file. This is a read-only audit.
- DO NOT run Blender, any build script, or pytest. The shipped artifacts under
  examples/cannon_car_wash/mod/ and dist/ are already built - audit THOSE.
- DO NOT launch BeamNG or touch %LOCALAPPDATA%/BeamNG.
- Bash resets cwd: prefix every Bash call with "cd /c/Users/ericr/beamng-mcp && ".
- Read-only Python one-liners via ./.venv/Scripts/python.exe are encouraged. Any
  scratch file goes ONLY under
  C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr/01aac343-2951-4984-a938-b549490f7a7b/scratchpad/
- ASCII only in anything you emit.
`

const LAWS = `
## Defect classes this codebase has actually shipped and paid for

1. STALE / MISSING RUNTIME COLLISION. A TSStatic spawned at runtime has NO static
   collision until be:reloadCollision() is called - and castRayStatic never sees
   runtime TSStatics even after the reload, so a ray-based "is it solid" check
   lies. Every setPosRot on a collidable must be followed by a reload if the
   collision is meant to follow. Use collisionType "Visible Mesh Final", never
   "Visible Mesh" (the latter logs a warning that live gates fail on).
2. ANIMATION CLIP TRUNCATION. The DAE exporter bakes only up to scene.frame_end.
   A clip whose keys were extended past frame_end ships arrays covering only part
   of its declared duration and STALLS mid-motion. (v1.47: keys moved to frame
   193 while frame_end stayed at 61 - an 8 s surge-stall the player caught on
   video.) Check every animated clip's declared duration against its actual
   sample count.
3. CLIP RESTART ON TOGGLE. playAmbient toggling restarts the clip from frame 0;
   any transform refresh also restarts it. Anything that appears to "stutter" on
   state change is this.
4. MATERIALS PROVENANCE. art/ main.materials.json is engine-special-cased. The
   selector materials.json is DERIVED - editing it instead of the scenario source
   silently reverts. Check nothing edits a derived file as if it were source.
5. TEXTURE ATLAS SAMPLING. Atlas V samples from the image BOTTOM, not the top.
   An off-by-one-row atlas reads as smeared or wrong-cell art.
6. QUATERNION COMPOSITION ORDER. BeamNG quats compose LEFT-TO-RIGHT (a*b means
   a-then-b). A reversed pair renders an object inverted or mirrored.
7. LUA UPVALUE LIMIT. A Lua function closing over more than 60 upvalues fails to
   load. Long single-function control files are at risk.
8. EPOCH / CACHE STALENESS. Cached artifacts shadowing fresh ones is a recurring
   class here - look for anything keyed on a timestamp or epoch that can go stale.
9. STUCK STATE. Enumerate the state machine. Every phase needs an exit; prove a
   wreck parked in a sensor zone or a vehicle that despawns mid-wash cannot pin
   the machine forever.
10. UNBOUNDED FORCES. Any per-frame velocity change applied to a vehicle must be
    magnitude-clamped, with a sanity skip for vehicles already moving absurdly
    fast.
11. RESET / REPAIR CORRECTNESS. This mod has a documented history of reset bugs -
    rotated-yaw reset angles, two-pass repair-reset, pose preservation. Check the
    reset path restores orientation and clears every latch.
12. NUMERICAL LANDMINES. normalize() on a possibly-zero vector, division by dt,
    unguarded acos, angle wrap at +/-180.
`

const FINDING_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['headline', 'health', 'findings', 'evidence_run', 'clean_checks'],
  properties: {
    headline: { type: 'string' },
    health: { type: 'number' },
    evidence_run: { type: 'array', items: { type: 'string' } },
    clean_checks: { type: 'array', items: { type: 'string' } },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['law', 'severity', 'summary', 'evidence', 'failure_scenario', 'fix'],
        properties: {
          law: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          summary: { type: 'string' },
          evidence: { type: 'string' },
          failure_scenario: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['headline', 'confirmed', 'refuted', 'missed'],
  properties: {
    headline: { type: 'string' },
    confirmed: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['severity', 'summary', 'evidence', 'failure_scenario', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          summary: { type: 'string' }, evidence: { type: 'string' },
          failure_scenario: { type: 'string' }, fix: { type: 'string' },
        },
      },
    },
    refuted: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['summary', 'why_wrong'],
        properties: { summary: { type: 'string' }, why_wrong: { type: 'string' } },
      },
    },
    missed: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['severity', 'summary', 'evidence', 'failure_scenario', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          summary: { type: 'string' }, evidence: { type: 'string' },
          failure_scenario: { type: 'string' }, fix: { type: 'string' },
        },
      },
    },
  },
}

phase('Audit')
const audit = await agent(
  `You are auditing the SHIPPED Cannon Car Wash BeamNG mod for latent physics and behaviour
defects. It lives at C:/Users/ericr/beamng-mcp/examples/cannon_car_wash/ and is at v1.47.

This mod is structured differently from the giant_props pack: it has its own
build_distribution.py / build_selector_prop.py / sync_scenario_outputs.py, a blender/
generator, a scenario under mod/, telemetry/ and validation/ directories, plus README.md
and TECHNICAL_ART.md. Map the layout yourself before drawing conclusions.

${READONLY}

## Orientation

Read C:/Users/ericr/beamng-mcp/AGENTS.md first - the "Prop authoring field guide" section
and every Cannon Car Wash round note. Nearly every law below is a scar recorded there.
Then read examples/cannon_car_wash/README.md and TECHNICAL_ART.md, then the generator, then
the shipped Lua under mod/.

${LAWS}

## How to work

Go through the checklist against this mod. Prefer machine checks to reading: parse the
shipped materials JSON and the scenario Lua, extract animation clip durations from the DAEs
and compare them against the sample counts actually present, count upvalues in the longest
Lua functions, list what the build scripts write versus what is committed.

Every finding needs file:line or command output as EVIDENCE and a concrete FAILURE
SCENARIO. Speculation is worse than silence - an adversarial verifier reads this next and
will spend real effort killing anything unfounded.

Record in "clean_checks" every checklist item you verified and found sound, by name.`,
  { label: 'audit:cannon_car_wash', phase: 'Audit', schema: FINDING_SCHEMA },
)

phase('Refute')
const verdict = await agent(
  `You are an adversarial verifier. An auditor has reported defects in the shipped Cannon Car
Wash mod at C:/Users/ericr/beamng-mcp/examples/cannon_car_wash/ (v1.47). Kill the wrong
ones and catch what they missed.

${READONLY}

## The audit you are attacking

${JSON.stringify(audit, null, 2)}

## Your standard

Default to REFUTED. For each finding go to the source and try to prove it wrong: the guard
exists further up; the value is clamped by the caller; the reload IS called after that
setPosRot; that file is generated and the source it derives from is correct; the clip's
frame_end was fixed in v1.47. Confirm ONLY what you independently reproduced and can state
the failure scenario for in your own words. Unsure means REFUTED.

Read AGENTS.md's Cannon Car Wash history before ruling - several of these defect classes
were fixed in named versions, and a finding that describes an already-fixed bug is refuted
by that history plus the current source.

Then do your own independent pass for what the auditor MISSED, against the same checklist:

${LAWS}`,
  { label: 'refute:cannon_car_wash', phase: 'Refute', schema: VERDICT_SCHEMA },
)

const blockers = (verdict.confirmed || []).filter(f => f.severity === 'blocker').length
log(`cannon car wash: ${blockers} confirmed blockers, ${(verdict.confirmed || []).length} confirmed total, ${(verdict.missed || []).length} caught only by the verifier`)
return { mod: 'cannon_car_wash', audit, verdict }

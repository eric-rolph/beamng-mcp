export const meta = {
  name: 'giant-props-14-17',
  description: 'Build giant-props mods 14-17 with adversarial critics that must be wowed',
  phases: [
    { title: 'Build', detail: 'one builder per mod: spec + Blender generator + green build' },
    { title: 'Critique', detail: 'adversarial critic per mod, defaults to NOT wowed' },
    { title: 'Fix', detail: 'address every finding and rebuild' },
    { title: 'Verdict', detail: 'fresh critic decides wowed / not wowed' },
  ],
}

const BRIEF = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr/01aac343-2951-4984-a938-b549490f7a7b/scratchpad/giant_props_brief.md'

const MODS = [
  {
    key: 'pachinko_tower',
    title: 'Vertical Vehicle Pachinko Tower',
    concept: `A ~55 m tall pachinko BOARD stood on end. The player drives into a lift carriage at
the base; the carriage hoists the car to the release gate at the top; the gate opens and the car
FALLS through a staggered field of giant steel pegs, ricocheting off them, into one of several
scoring bins at the bottom. Bins have different point values (the middle one is the hard one).
A scoreboard reports the bin hit and the score. Backboard behind, guard rails on the sides so the
car cannot leave the board, catch apron at the bottom feeding the bins.`,
    wow: `The peg field must ACTUALLY deflect the car - real peg collision geometry, staggered rows,
peg spacing derived from car width so a car cannot fall a clean unobstructed column. Scoring must be
honest: read the car's real landing position, not a random number. The lift must be a believable
machine (mast, carriage, cable, sheaves, counterweight) and the release gate must be a real moving
part, not a teleport.`,
  },
  {
    key: 'belt_sander_trap',
    title: 'Belt Sander Conveyor Trap',
    concept: `A giant belt sander, ~30 m long. The abrasive belt runs over a drive drum and an idler
with a flat platen between them. The player drives up an entry ramp onto the belt; the belt is
running, and it drags the car toward the drive-drum end while the car tries to escape under its own
power. Sparks and dust at the contact line. At the drum end the car is thrown off a kicker ramp.
A tension-arm, guarding, a dust-extraction hood and a control stand with belt-speed controls.`,
    wow: `The belt must apply a REAL tangential surface velocity to the car so the tug-of-war is
genuine and winnable at low belt speed / hopeless at high. The belt surface must visibly scroll
(scrolling UVs or moving segments - do not fake it with a static texture and claim it moves). Belt
speed must be operator-adjustable and the readout must be truthful. Cars must be able to drive on
AND off without hitting a vertical wall.`,
  },
  {
    key: 'sumo_gyro_platform',
    title: 'Free-Pivot Car Sumo Gyro-Platform',
    concept: `A ~26 m diameter dish on a free gimbal, ringed by a hazard-striped lip and surrounded
by a soft landing apron. Drive on and the platform TILTS under you - the further you are from the
centre the harder it tips, so standing still is a losing move. Two cars on it turn into sumo. Fall
off the edge and the platform slowly re-levels for the next round. Central hub, gimbal yoke,
hydraulic-looking struts, a scoreboard reporting who is still on.`,
    wow: `The tilt must be driven by where the cars ACTUALLY are - a real torque balance from every
occupant's mass moment about the pivot, integrated with inertia and damping, not a scripted wobble.
The tilting deck's COLLISION must follow the visual without leaving a stale bake in a bad state
(read the mouth-shelf lesson in AGENTS.md). Re-level must be smooth and must never launch a car.`,
  },
  {
    key: 'junk_chute_grinder',
    title: 'Junk Chute Grinder Trap',
    concept: `A scrapyard shredder. A steep walled chute feeds a pair of counter-rotating toothed
shredder rollers set in a heavy frame; below them a discharge conveyor drops the remains onto a
scrap pile. The player drives into the chute mouth, slides down, the rollers grab the car, chew it
(progressive damage / shaking), and spit the wreck out the bottom. Feed hopper, tooth combs,
hydraulic power pack, walkway and hand rails, warning beacon and horn.`,
    wow: `The rollers must visibly counter-rotate at a speed consistent with the pull they apply, and
the grab must be a real velocity coupling that drags the car in - not a teleport down the chute. The
chew must be honest (shake + damage, and say plainly in the report what BeamNG damage you could and
could not actually apply). The wreck must reliably reach the bottom and the machine must self-clear
if something jams.`,
  },
]

const CRITIC_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['wowed', 'headline', 'score', 'findings', 'evidence_run'],
  properties: {
    wowed: { type: 'boolean', description: 'true ONLY if this is genuinely impressive work' },
    headline: { type: 'string', description: 'one sentence verdict' },
    score: { type: 'number', description: '0-100' },
    evidence_run: {
      type: 'array', items: { type: 'string' },
      description: 'commands you actually ran and what they showed',
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'area', 'summary', 'evidence', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          area: { type: 'string' },
          summary: { type: 'string' },
          evidence: { type: 'string', description: 'file:line or command output proving it' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const BUILD_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['mod_key', 'built', 'gate_passed', 'summary', 'files', 'notes'],
  properties: {
    mod_key: { type: 'string' },
    built: { type: 'boolean', description: 'Blender + build.py both ran clean' },
    gate_passed: { type: 'boolean', description: 'pytest tests/test_giant_props_pack.py green' },
    summary: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
    notes: { type: 'array', items: { type: 'string' }, description: 'honest gaps / unverified claims' },
  },
}

const RULES = `
Read ${BRIEF} FIRST, in full. Then read
examples/giant_props/catapult_seesaw/spec.py and its Blender generator end to end, and
skim the "Prop authoring field guide" section of C:/Users/ericr/beamng-mcp/AGENTS.md.

HARD CONSTRAINTS:
- Work ONLY inside examples/giant_props/<mod_key>/. Never edit proplib/, build.py, other
  mods, AGENTS.md or tests/ - three sibling agents are editing the same repo concurrently.
- Never launch BeamNG and never write anything under %LOCALAPPDATA%/BeamNG.
- Bash resets cwd: prefix every Bash call with "cd /c/Users/ericr/beamng-mcp && ".
- Blender exits 0 on Python errors: ALWAYS grep its output for Traceback.
- ASCII only in Python and Lua source.
`

phase('Build')
const results = await pipeline(
  MODS,

  // ---- Stage 1: build it
  (mod) => agent(
    `You are building a new BeamNG "giant contraption" prop mod for the giant_props pack in
C:/Users/ericr/beamng-mcp. Your mod key is "${mod.key}".

${RULES}

## What you are building: ${mod.title}

${mod.concept}

## The bar ("wow")

${mod.wow}

An adversarial critic will review your work next and defaults to NOT impressed. It will run
your build itself, read your jbeam and handoff JSON, and trace your Lua by hand. It will
reject: geometry a car cannot drive into, cage/visual mismatch, physics that would teleport
or explode a car, phases with no way out, uncapped per-frame velocity changes, magic numbers
with no derivation, faked motion, and any claim in your report you did not actually verify.

## Deliverable

1. examples/giant_props/${mod.key}/spec.py
2. examples/giant_props/${mod.key}/blender/create_${mod.key}.py
3. A GREEN build: Blender stage with no Traceback, then
   ./.venv/Scripts/python.exe examples/giant_props/build.py ${mod.key} all
4. GREEN pack gate: ./.venv/Scripts/python.exe -m pytest tests/test_giant_props_pack.py -q
   (92 tests pass before you start; yours must not break any and will add more)
5. Sanity-inspect what you shipped: dump the jbeam node/beam/triangle counts, confirm the
   handoff parts list matches the exported DAEs, and eyeball the rendered thumbnail
   (authoring/<MOD_ID>_thumbnail.jpg) with the Read tool - if the thumbnail shows a mess,
   fix the geometry, do not ship it.

Iterate until all of the above are green. Do the real engineering: derive dimensions from
the fact that a BeamNG car is roughly 2.0 m wide, 4.5 m long, 1.5 m tall, and comment WHY
for every tuned number.

Return the structured result. In "notes", be brutally honest about anything you could not
verify or had to approximate - the critic will find it anyway and an admitted gap costs you
far less than a discovered one.`,
    { label: `build:${mod.key}`, phase: 'Build', schema: BUILD_SCHEMA },
  ),

  // ---- Stage 2: adversarial critic
  (built, mod) => agent(
    `You are an adversarial reviewer of a newly authored BeamNG prop mod. Mod key:
"${mod.key}", at C:/Users/ericr/beamng-mcp/examples/giant_props/${mod.key}/.

${RULES}
You are REVIEWING, not fixing: do not edit any source file. You MAY run builds and tests.

The brief the author worked from is at ${BRIEF}. What they were asked to build:

${mod.concept}

The bar they were held to:

${mod.wow}

Their own summary of what they did:
${JSON.stringify(built, null, 2)}

## Your standard

Default to NOT wowed. "It builds" is table stakes, not impressive. To set wowed=true you
must believe a demanding BeamNG modder would look at this and say "how did they do that".

## You must EARN your verdict with evidence, not vibes

Actually run things. At minimum:
- Re-run the Blender stage and the build, and grep the Blender output for Traceback.
- Run pytest tests/test_giant_props_pack.py -q.
- Parse the shipped jbeam (strip // comments, then json.loads) and check node/beam/triangle
  counts, refnodes, the spawn envelope, and that no vertical collision face stands in a
  driving lane.
- Read the handoff JSON: do the declared parts match the exported DAE files, do the
  Contains triggers actually fit a car (>= 2.9 x 4.5 x 3.0), do all BEHAVIOR keys the Lua
  reads actually exist in the handoff tunables (a missing key is nil at runtime - this
  exact bug froze the centrifuge mid-cycle).
- Hand-trace the Lua state machine: enumerate the phases, prove every phase has an exit,
  and prove a wreck parked in a sensor zone cannot pin the machine forever.
- Check every per-frame velocity change is dv-capped and that launch vs add semantics are
  right (launchSubject SETS velocity, addSubjectVelocity ADDS).
- Read the thumbnail image at authoring/<MOD_ID>_thumbnail.jpg with the Read tool and say
  what you actually see. If it looks like a pile of boxes, say so.
- Verify the WOW claims specifically. If the author says a surface scrolls, a roller
  counter-rotates, or a platform responds to real car positions, find the code that does it
  and confirm it is real rather than decorative.

Every finding needs file:line or command output as evidence. A finding you cannot evidence
does not go in the list. Rank blockers first.`,
    { label: `critic:${mod.key}`, phase: 'Critique', schema: CRITIC_SCHEMA },
  ),

  // ---- Stage 3: fix everything the critic found
  (critique, mod) => agent(
    `You are fixing the BeamNG prop mod "${mod.key}" at
C:/Users/ericr/beamng-mcp/examples/giant_props/${mod.key}/ in response to an adversarial
review.

${RULES}

What it was supposed to be:
${mod.concept}

The bar:
${mod.wow}

## The review

${JSON.stringify(critique, null, 2)}

## Your job

Fix EVERY blocker and EVERY major. Fix the minors and polish items too unless a fix would
make something worse - and if you skip one, say exactly why. Where the critic says the work
is merely adequate, make it genuinely impressive: this mod goes back to a FRESH critic who
has not seen the first review and who also defaults to NOT wowed.

If the critic is factually wrong about something, prove it with evidence rather than
silently ignoring it, and say so in your summary.

End green: Blender (grep for Traceback), build.py <key> all, and
pytest tests/test_giant_props_pack.py -q. Re-read the regenerated thumbnail and confirm the
machine reads as a machine.

Return the structured build result, with "notes" listing every finding you consciously did
not act on and why.`,
    { label: `fix:${mod.key}`, phase: 'Fix', schema: BUILD_SCHEMA },
  ),

  // ---- Stage 4: fresh critic, final wow gate
  (fixed, mod) => agent(
    `You are a FRESH adversarial reviewer - you have not seen any earlier review of this
work. Mod key "${mod.key}" at C:/Users/ericr/beamng-mcp/examples/giant_props/${mod.key}/.

${RULES}
You are REVIEWING, not fixing: do not edit any source file. You MAY run builds and tests.

What this was supposed to be:
${mod.concept}

The bar it was held to:
${mod.wow}

The author's summary:
${JSON.stringify(fixed, null, 2)}

## Your standard

You are the final gate and you default to NOT wowed. Set wowed=true only if this is
genuinely impressive: the machine is believable as machinery, the mechanic actually works
in code you can point at, the physics is bounded and safe, every phase has an exit, and the
thing would hold up to a demanding modder reading the source.

Earn the verdict: re-run the Blender stage (grep Traceback), the build, and
pytest tests/test_giant_props_pack.py -q. Parse the shipped jbeam. Read the handoff and
confirm every BEHAVIOR key the Lua reads exists. Hand-trace the state machine for stuck
states. Confirm per-frame velocity changes are capped. Read the thumbnail with the Read
tool and describe what you actually see. Verify each WOW claim against real code.

Every finding needs file:line or command output as evidence. If you set wowed=false, the
findings list must make it completely clear what would have to change to earn a yes.`,
    { label: `verdict:${mod.key}`, phase: 'Verdict', schema: CRITIC_SCHEMA },
  ),
)

const report = MODS.map((mod, i) => ({ mod: mod.key, title: mod.title, verdict: results[i] }))
const wowed = report.filter(r => r.verdict && r.verdict.wowed).map(r => r.mod)
log(`wowed: ${wowed.length}/4 -> ${wowed.join(', ') || 'none'}`)
return report

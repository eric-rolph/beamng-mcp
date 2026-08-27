export const meta = {
  name: 'spin-launch-repair-design',
  description: 'Design precise, conflict-free repairs for every verified Spin Launch defect',
  phases: [
    { title: 'Design', detail: 'seven independent read-only deep dives, each returning exact edits' },
    { title: 'Reconcile', detail: 'merge into one ordered master plan with no conflicting edits' },
  ],
}

const PREAMBLE = `
You are working on a BeamNG.drive mod in the repo at C:\\Users\\ericr\\beamng-mcp.
The mod is \`spin_launch\`, a prop in the \`examples/giant_props\` pack: a car drives
up a ramp, through an airlock, into a 43 m vacuum chamber standing on edge, parks
on a cradle, and is auto-detected. The chamber seals, evacuates, the load deck
retracts, a composite tether spins up, and the car is launched out a launch tube
that PIVOTS around the chamber rim to stay tangent to the release point. A console
sets POWER (exit m/s) and ELEVATION (degrees). The governing identity is
\`theta_release = 90 + elevation\` — the launch tangent IS the trajectory.

Files that matter (READ THE CURRENT STATE — these were edited very recently):
- examples/giant_props/spin_launch/spec.py            (authored constants + the GELua behaviour chunk)
- examples/giant_props/spin_launch/blender/create_spin_launch.py  (deterministic geometry generator)
- examples/giant_props/spin_launch/mod/lua/ge/extensions/ericrolph_spin_launch/runtime.lua  (GENERATED - never hand-edit)
- examples/giant_props/proplib/{blender_kit,prop_builder,lua_kit,texture_kit,packaging}.py  (shared toolkit)
- examples/giant_props/README.md                      (pack standards)
- tests/test_giant_props_pack.py                      (static gates for all 20 props)
- tests/test_spin_launch_sequence.py                  (headless lupa state-machine gate)
- tests/test_spin_launch_live.py                      (in-game gate, currently PASSING)
- examples/giant_props/gforce_centrifuge/spec.py      (the pack's quality bar - study it)

Build chain (behaviour CODE re-reads on every build.py run; behaviour PARAMS,
geometry, cage and handoff ONLY move when the Blender stage runs):
  .venv/Scripts/python.exe examples/giant_props/build.py spin_launch textures
  "C:/Users/ericr/Applications/Blender/4.5.4/blender.exe" --factory-startup --background --python examples/giant_props/spin_launch/blender/create_spin_launch.py
  .venv/Scripts/python.exe examples/giant_props/build.py spin_launch all

## HARD RULES FOR YOU

1. **YOU ARE READ-ONLY. Do not edit, create or delete ANY file in the repo.**
   Many agents are working in parallel and \`spec.py\` is a single file nearly all
   of them touch. Your deliverable is a PATCH PLAN, not a patch.
2. You MAY and SHOULD run read-only commands and throwaway Python to DERIVE and
   VERIFY numbers (\`.venv/Scripts/python.exe - <<'PY' ... PY\`, importlib-loading
   spec.py is fine and safe — it has no side effects). Do not run Blender, do not
   run build.py, do not launch BeamNG.
3. Every number you propose must be DERIVED and shown, not guessed. This pack's
   entire ethos is derived-not-guessed. If you propose a constant, show the
   arithmetic that produces it and the constraint it satisfies.
4. Produce EXACT edits: the precise existing text to match and the precise
   replacement, so someone else can apply them mechanically without judgement.
   Include the comment you want on the change — this codebase documents WHY a
   value is what it is, and a bare number is not acceptable here.
5. State explicitly what your edits DEPEND on from other dimensions.
`

const DIMENSIONS = [
  {
    key: 'datum',
    label: 'datum:spawn-height',
    prompt: `
## YOUR DIMENSION: the spawn datum (THE most important defect)

CONFIRMED DEFECT, measured live: the prop spawns 3 m in the air. \`origin.z\`
returns 3.0 for a prop spawned at surface z = 0, so the approach ramp's foot
sits 3 m above the terrain and **a player cannot drive onto the machine at all.**

Root cause: BeamNG places a vehicle by its base origin — the LOWEST node.
\`spin_launch\` authored its ref node at the ramp foot (authored z 0) while
\`PLINTH_BOTTOM = -3.0\`, deliberately "burying" the plinth. On a flat map nothing
can be buried; the lowest node lands on the terrain and everything above it is
lifted. Measured across the pack: 18 of 20 props have \`ref_z == min_z == 0\`.
spin_launch is 3.00 m out (sumo_gyro_platform is 0.75 m out — NOT your problem,
but mention it if you think it should be filed).

Read \`proplib/blender_kit.py\` \`set_ground_reference\` and \`set_refnodes_existing\`
docstrings — they state the rule this violates.

## What to design

The complete re-datum so the authored ground plane z = 0 IS the lowest point of
the prop and the ramp foot sits on the terrain. Derive:

- the new \`DECK_Z\` (everything keys off it: \`HUB_Z = DECK_Z + TETHER_R\`), such
  that the chamber's lowest OUTER point \`HUB_Z - SHELL_R\` sits a sensible
  thickness of plinth above z = 0;
- \`PLINTH_BOTTOM\`, \`PLINTH_TOP\`;
- the ramp: \`RAMP_Y0\`, \`APRON_Y0\`, the resulting grade — check the grade is
  drivable for a heavy vehicle (state the percentage; the current one is ~12.5%);
- EVERY other constant in spec.py that is an absolute z or keys off the old
  datum and does NOT auto-derive. Audit the whole file: PALETTE is fine, but
  check \`MAST_HEIGHT\`, \`BUILDING_SIZE\`, \`PUMP_POSITIONS\`, \`EFFECTS\` positions,
  \`TRIGGERS\` centres, \`BEACON_PIVOT\`, \`STATUS_STACK\`, console rows, and the
  plaza/plinth extents in the generator.
- anything in \`create_spin_launch.py\` with a hard-coded z or y that must move
  (grep for numeric literals in build_civil, build_plant, build_cage).

Then design a STATIC GATE for \`tests/test_giant_props_pack.py\` that asserts, for
every prop in the pack, that the ref node is the lowest node (within a small
tolerance). Note in your plan that sumo_gyro_platform will fail it at 0.75 m and
say how you would handle that (fix it too? xfail with a tombstone? tolerance?) —
recommend one, with reasoning.

Sanity-check your new numbers by loading spec.py in Python with your proposed
values substituted and printing the resulting derived geometry.
`,
  },
  {
    key: 'clearance',
    label: 'clearance:beacon-in-bore',
    prompt: `
## YOUR DIMENSION: swept-volume clearance

CONFIRMED DEFECT, verified by arithmetic: the rotating warning beacon sits
INSIDE the launch tube's bore at low elevation settings.

\`BEACON_PIVOT = (0.0, 4.2, CHAMBER_TOP_Z + 0.55)\`. Perpendicular distance from
that point to the bore centreline, per elevation rung:

  tilt 34 -> 0.115 m  (station 15.87 down the bore)  INSIDE THE BORE
  tilt 39 -> 1.329 m  (station 17.20)                INSIDE THE BORE
  tilt 45 -> 3.207 m  (station 18.63)                inside the rib flanges
  tilt 50 -> 4.880 m                                  clear
  tilt 56..72 -> 7.0 .. 13.1 m                        clear

TUBE_BORE_R = 2.55, TUBE_RIB_R = 3.62. At tilt 34 the beacon is 11.5 cm off the
axis of a barrel a car flies down at up to 182 m/s, and the beacon housing plus
its 2.2 x 2.2 m base plate are fully swallowed.

Why it was invisible: every render, the selector thumbnail, the headless test
default and the live gate default all sit at 50 degrees — the FIRST clear rung.
Nothing in the evidence chain has ever exercised 34, 39 or 45.

I already checked the obvious fix and it is WRONG: moving the beacon to a
mirrored pair at x = +/-6.5 clears the bore, but the +X one lands 1.962 m from
the sonic-baffle case centreline, and that box has half-extents 1.55 x 1.30. The
baffle hangs off the tube at lateral +4.55 m, radial -1.55 m.

## What to design

1. The correct new beacon placement, derived, clearing BOTH the bore/ribs AND
   the baffle case across the whole tilt ladder with a stated margin. Consider
   whether a single beacon or a pair is better and say why. Consider whether it
   should move in x, in y, or off the chamber crown entirely.
2. A SWEPT-VOLUME AUDIT: the tube sweeps the entire plane x ~ 0 above the
   chamber. Enumerate EVERY static fixture the generator places, and check each
   against the swept bore across all eight rungs. The beacon is the one I know
   about; find any others (slot rails, shingles, jamb, girders, masts, hub
   flanges, sign, anything). Show the distance table.
3. A STATIC GATE that asserts no authored fixture intrudes into the swept bore
   at any rung, so this can never regress. Write it against spec.py constants so
   it needs no Blender run. Say exactly where it should live and give the code.
4. Note what would make the low elevations visible in the evidence chain
   (renders at 34, a headless/live launch at a low rung) — the coverage agent is
   handling tests, so just state the requirement.
`,
  },
  {
    key: 'envelope',
    label: 'envelope:chamber-holes',
    prompt: `
## YOUR DIMENSION: the pressure envelope has holes in it

CONFIRMED DEFECT, verified by arithmetic. \`build_chamber\` omits shell and bore
surface over \`arcs_excluding(SLOT_DEG, TUNNEL_DEG)\`. The omission removes the
FULL profile width; the tunnel that is supposed to plug it is a RECTANGULAR box.

Measured with the CURRENT spec values (re-derive them yourself, they were edited
recently — TUNNEL_DEG is now derived, not authored):
- the omitted tunnel arc extends ABOVE the tunnel soffit, leaving an arc of wall
  open to the sky (previously theta 207.0 -> 212.96 at the bore radius);
- the tunnel box is |x| <= TUNNEL_HALF_X (3.4) while the omission runs to
  |x| <= HALF_X (4.2) on the bore and |x| <= OUTER_HALF_X (5.4) on the shell,
  leaving 0.80 m and 2.00 m strips open on EACH side across the whole portal arc.

The generator's own comment claims "Walls and soffit run a little past the tunnel
proper so the omitted shell arc never shows an open edge" — but \`y_far, y_near\`
is an overrun in Y ONLY. Nothing extends in X or Z, which is where the arc
escapes the rectangle.

Visible in the render at
C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr-beamng-mcp/f76d9835-91b3-4c0d-a814-0663fa155ef1/scratchpad/final/tunnel_mouth.jpg
— open your eyes on it with the Read tool. This is the shot the player stares at
while the machine says "AIRLOCK SEALED. Evacuating chamber."

## What to design

1. Re-derive the true angular extent the tunnel box actually subtends at both
   the bore and shell radii, at the box's top and bottom, and show the gap.
2. The fix. Two candidate idioms: (a) shrink the omitted arc to exactly what the
   box plugs and widen the box to the full profile width; (b) add spandrel
   surfaces revolving the shell/bore profile across the residual arc and the
   side strips. NOTE the tombstone in \`blender_kit.cut_openings\` — boolean
   difference on a bevelled primitive is forbidden in this pack, so a spandrel
   built with \`revolve\`/\`grid_surface\` is the house idiom. Recommend one and
   give exact edits.
3. Apply the SAME audit to \`SLOT_DEG\` — the launch-tube slot omits a 64-degree
   arc of shell and is supposed to be covered by shingle leaves plus the tube's
   travelling apron. Verify the shingles actually span the full omitted arc AND
   the full profile width, at every tilt. If there is a gap, that is a second
   hole in the same class; derive it and fix it.
4. A STATIC GATE asserting the omitted arcs are fully covered. Say where it
   lives and give the code.

Your edits will need the FINAL datum numbers (another agent is re-datuming
DECK_Z/HUB_Z). Express everything as DERIVED formulas off spec constants rather
than absolute numbers wherever possible, and state explicitly which of your
values would change if DECK_Z moves.
`,
  },
  {
    key: 'runtime',
    label: 'runtime:state-machine',
    prompt: `
## YOUR DIMENSION: state-machine defects in the GELua behaviour

The behaviour chunk lives in \`spec.py\` as \`LUA_BODY\` (assembled into
\`LUA_BEHAVIOR\` at the end of the file). \`runtime.lua\` is GENERATED from it —
read runtime.lua to see what actually ships, but write your edits against
spec.py.

FOUR CONFIRMED DEFECTS (I verified all four by grep):

1. **Phase "arming" is read twice and never assigned.** Reads at runtime.lua:879
   (\`local amber = phase == "arming" or ...\`) and :1228
   (\`if b.phase == "idle" or b.phase == "arming" then\`). No assignment exists.
   Consequence: the entire 3.0 s \`arm_delay_s\` countdown emits NOTHING — no
   message, and both \`poseBeaconLights\` and \`poseStatusStack\` key on
   \`phase ~= "idle"\`, so the beacon stays retracted and the lamp stays green.
   The machine is byte-identical to idle for three seconds and then fires.

2. **PURGE has no phase interlock.** \`elseif buttonId == "btn_purge" then
   purgeChamber(state)\` — bare, unlike DOOR/POWER/ELEVATION which all guard.
   Pressed during \`release\` at 182 m/s it replaces the payload's ride velocity,
   sets \`b.launched[id] = true\` so the field lets go, and throws it "out through
   the airlock" — which is SHUT. Phase never changes; the machine walks on to
   fire an empty tether with a wrecked car loose in a sealed chamber.

3. **\`b.doorManual\` survives a reset.** \`behavior.init\` assigns ~24 fields and
   never \`b.doorManual\`; \`behavior.reset = behavior.init\`. One press of the
   DOOR button pins the door shut AND disables auto-detect
   (\`if candidate and not b.doorManual then\`), and resetting the prop — the
   universal player fix — does not clear it. The machine is bricked with no
   message explaining why.

4. **The tether field drives EVERY chamber occupant to the same point.**
   \`applyTetherField\` iterates \`chamberOccupants(state)\` and gives every one of
   them the identical target velocity; \`fireLaunch\` likewise fires everything
   with one vector. \`b.payloadId\` is stored but never used to filter. A second
   car parked on the deck, or a wreck left from a previous abort, is inside
   \`insideChamber\` and gets teleport-yanked into the same cubic metre the
   instant the field engages. \`hot_potato\` already ships the multi-car pattern
   in this pack — study it.

## What to design

Exact edits for all four, plus:

5. RE-READ the whole behaviour chunk adversarially and find what I missed. Trace
   every phase transition and every \`b.\` field. Specifically consider: what
   happens on \`onVehicleResetted\` for the PROP mid-spin; what happens if the
   payload is destroyed mid-ride; whether \`b.launched\` / \`b.quarantine\` /
   \`b.stats\` are cleaned up correctly; whether the abort path can strand state;
   whether \`release_timeout_s\` is reachable and what it does if it fires
   (a previous reviewer believes it is unreachable and would fire from an
   arbitrary position — check and decide); whether the endpoint collision-bake
   latch can miss an arrival; and what a hostile player can do.
6. For each new defect, the same treatment: exact edit + why it matters.

The headless gate \`tests/test_spin_launch_sequence.py\` must keep passing —
read it, and for any behaviour change say which existing assertion covers it or
what new assertion the coverage agent should add.
`,
  },
  {
    key: 'instruments',
    label: 'instruments:console-polish',
    prompt: `
## YOUR DIMENSION: the console and its instruments

The console is the thing a player leans in and reads. It is currently the
best-executed print in the pack (the ladder scale marks put the UNITS on the
nominal segment) and it is let down by its hardware.

CONFIRMED DEFECTS:

1. **Both gauge needles are authored at MID-SCALE.** \`build_needle\` authors
   \`needle_vel\` and \`needle_vac\` at the same pose, pointing +Z, which is
   \`gauge_angle_deg(0.5)\` — i.e. the dials read 100 m/s exit velocity and 50 kPa
   chamber pressure on a machine at rest.

2. **The dial faces are typographically foreign to the panel.** Near-white print
   on a near-white face inside a near-white bezel on a cream cabinet — three
   near-identical luminance values stacked — 20 cm above a panel that is bold
   sans on near-black. Numerals are at UV radius 0.34 (\`_dial_scale(radius=0.68)\`)
   while the tick inner ends are at ~0.359, so numeral tops overrun their own
   ticks, visibly on "0" and "200".

3. **The PURGE guard is two disconnected sticks.** \`create_spin_launch.py\`
   emits only the two LEGS of the flip-guard — there is no crossbar, so the
   thing its own comment calls "a wire flip-guard OVER the purge cap" does not
   exist. They are r=0.018 8-gons leaning 0.20 m out of the panel, protruding
   further than the E-STOP mushroom (0.125 m). At reading distance they read as
   two yellow slashes scribbled across the button.

4. **Cap sockets are a constant 0.028 m annulus** regardless of cap size, so
   \`round_small\` (r 0.042) sits in a hole two-thirds again its own radius while
   \`estop\` (r 0.128) hugs.

5. **The status lamp stack is crowded against the panel bezel** — 26 cm of
   clearance for a 0.115 m lamp; it reads as a clipped sliver.

## What to design

Exact edits for all five, derived. Then go further — this dimension is about
being WOWED, not merely correct:

6. Study the console renders and say what else is short of excellent. Open:
   .../scratchpad/preview4/panel.jpg  (panel close-up)
   .../scratchpad/preview5/console_wide.jpg  (console + gauges)
   .../scratchpad/final/bay.jpg
   (full prefix: C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr-beamng-mcp/f76d9835-91b3-4c0d-a814-0663fa155ef1/scratchpad/)
   Compare against \`gforce_centrifuge\`'s console (its spec.py PANEL_BUTTONS /
   PANEL_LEGEND_LABELS and the round-14/15 comments describe what it took to get
   that one right).
7. Consider what LIVE FEEDBACK the console is missing. The player watches the
   sequence from 25 m away through a closed blast door; what should the console
   be telling them? The runtime already exposes phase, omega, vac, deck, clamp.
   Design it, but keep it cheap — this pack does not ship a UI app.

Read \`proplib/texture_kit.py\` \`panel_legend\` before proposing typography changes
so your parameters are real.
`,
  },
  {
    key: 'audio',
    label: 'audio:the-missing-half',
    prompt: `
## YOUR DIMENSION: the mod is completely silent

The mod ships NO audio. \`grep -i "sfx|sound|playSound"\` over runtime.lua returns
three hits, all comments. There is no \`assets/\` directory, no \`SHIP_ASSETS\`, no
\`.ogg\`, no \`SFXEmitter\`.

Meanwhile \`spec.py\`'s own module docstring claims: "every one of those steps has
its own sound-of-machinery beat, and the longest pause is the one right before
the throw." That is currently false.

An independent reviewer called this THE single highest-leverage change, and the
reasoning is sound: this machine's mechanic is 4.4-28.6 s of spin-up, a 4 s hold
and a 1.4 s hatch — a build-up and nothing else. In silence that is a progress
bar with text floating over it. Sound also reaches the player through a sealed
blast door when light does not, so it retroactively repairs the two dead beats
(the 3 s arm countdown and the 7 s evacuation).

## The proven mechanism in this pack

\`gforce_centrifuge/spec.py\` ships a spin-up stem: read its \`VEHICLE_LUA_EXTRA\`
and the surrounding comments IN FULL. Key facts recorded there:
- \`obj:createSFXSource\` in the VEHICLE VM is the proven-audible raw-ogg path; a
  bare prop's VM does NOT boot the module stack, so GE-side and jbeam-prop
  mechanisms do not work (there is a tombstone about exactly that).
- The emitter is 2D (\`is3D=0\`) because FMOD downmixes 3D sources to mono, so
  distance falloff is SCRIPTED from the camera distance.
- The GE runtime pushes state to the vehicle VM on phase edges.
- \`SHIP_ASSETS\` in spec.py is what makes a file actually ship (there is a
  tombstone about an 11 MB blind copy).

## What to design

1. The full sound design: which cues, on which edges, with what envelope. At
   minimum: pump-down bed on \`evacuating\`, door travel + a slam on the
   \`doorClose >= 1.0\` edge, deck retract, clamp close, a spin loop whose pitch
   and level track \`b.omega\`, the muzzle hatch, the release, and a shutdown
   one-shot on \`enterRecover\`. Say what each one is FOR dramatically.
2. **How the audio files get made.** There are no source recordings and none can
   be downloaded. Design a DETERMINISTIC PROCEDURAL GENERATOR in the repo venv
   (numpy is available; check what else is) that synthesises the .ogg/.wav files
   from a seed — the same way \`texture_kit.py\` synthesises every texture in this
   pack. Give the actual synthesis approach per cue (harmonic stack + filtered
   noise for a turbine, resonant sweep for pump-down, impulse + body resonance
   for the slam, etc.), the file format and rate BeamNG wants, and where the
   generator script should live so it matches pack convention. Verify what audio
   encoders are available: check \`.venv/Scripts/python.exe -c "import soundfile"\`,
   \`import scipy\`, and whether \`ffmpeg\` is on PATH. If OGG is not reachable,
   say what IS and whether BeamNG will load it.
3. The exact \`VEHICLE_LUA_EXTRA\` and the GE-side push, written against THIS
   mod's phases.
4. \`SHIP_ASSETS\` and the size budget (the ZIP is currently 26 MB).
5. Be honest about risk: this is the one dimension that cannot be verified
   without the game and cannot be verified by looking. Say exactly what a live
   run would have to check to prove the audio is audible and correctly gated.
`,
  },
  {
    key: 'coverage',
    label: 'coverage:test-gaps',
    prompt: `
## YOUR DIMENSION: what the tests do not cover

The evidence chain is: static gates (tests/test_giant_props_pack.py, 20 props),
a headless lupa state-machine gate (tests/test_spin_launch_sequence.py), and an
in-game gate (tests/test_spin_launch_live.py) which currently PASSES.

Known holes, all confirmed:

1. **Nothing has ever exercised the low half of the elevation ladder in
   geometry.** Every render, the selector thumbnail, the headless default and
   the live default sit at 50 degrees. A geometry defect (the warning beacon
   sitting inside the launch bore) lives at 34/39/45 and was invisible for
   exactly this reason. The headless test DOES parametrise tilt over [1,4,8] but
   stubs have no geometry, so it cannot see it.

2. **BeamNG caches compiled meshes per model path in
   \`<profile>/temp/vehicles/<mod_id>/*.cdae\` and does NOT invalidate them when
   the ZIP changes.** During the live session three rebuilds silently did
   nothing — the game kept serving .cdae files from the first session while the
   gate happily verified the NEW ZIP's SHA-256 against its lock. It was provable
   only from "Loaded Static Collision ... Verts: 373, Tris: 472" staying frozen
   while the deck mesh had gained two boxes. JBeam and Lua changes land
   immediately; MESH changes do not. **A green live run does not currently prove
   the shipped ZIP's geometry.** This is the highest-value gap.

3. **POWER 8 (182 m/s) is untested live** and is believed marginal at low frame
   rates: the residual radius error grows with frame time, and past the 20.4 m
   bore \`insideChamber\` stops counting the payload and the machine fires an
   empty tether.

4. The live gate proves ONE nominal path: default power, default tilt, one car.
   Multi-car, abort-at-speed, purge, and the manual-door interlock are all
   headless-only or untested.

5. \`origin.z\` came back as 3.0 for a prop spawned at surface 0 and NO gate
   noticed — the live gate teleports the car onto the prop's own apron, so it
   never touches the ground. 18 of 20 props have \`ref_z == min_z\`; a static gate
   would have caught this before it ever reached the game.

## What to design

Exact test code for:
a. The \`.cdae\` cache purge — design it in \`tests/live_support.py\` so EVERY live
   gate in the pack benefits, not just this one. Read that file and the other
   live gates first; match their safety idioms exactly (they are extremely
   careful about confining writes to the sentinel profile — see
   \`require_confined_profile_target\`, \`cleanup_exact_live_artifacts\`). Deleting
   a directory inside a player profile is dangerous; design it so it CANNOT
   escape.
b. A static ref-node-is-lowest-node gate over all 20 props.
c. A static swept-bore clearance gate over the whole tilt ladder.
d. Live coverage of a LOW elevation and of MAX power — decide whether that is a
   second test function, a parametrisation, or a single longer test, and justify
   the wall-clock cost (a full sequence is ~35 s of sim; passing runs took ~35 s
   wall, failing ones ~5.5 min).
e. Whatever else you find missing after reading all three gates adversarially.
   Ask specifically: does each assertion actually prove what its name claims, or
   is it self-confirming?

Also review the live gate's ONE harness change from the last session (the block
that stops the car on the pad): a stock automatic on a fresh profile runs the
arcade gearbox where brake-held-at-standstill is REVERSE, which floored the
payload backwards out of the airlock at 11.5 m/s. It now brakes until stopped
then releases. Confirm that fix is correct and idiomatic against the other live
gates in the pack, and say if it should move into \`live_support.py\` as a shared
helper.
`,
  },
]

phase('Design')
const plans = await parallel(DIMENSIONS.map(dimension => () =>
  agent(PREAMBLE + dimension.prompt, {
    label: dimension.label,
    phase: 'Design',
    effort: 'high',
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['dimension', 'summary', 'edits', 'gates', 'depends_on', 'risks'],
      properties: {
        dimension: { type: 'string' },
        summary: { type: 'string', description: 'What you found and what you propose, in prose.' },
        derivations: { type: 'string', description: 'The arithmetic behind every number you propose, shown.' },
        edits: {
          type: 'array',
          description: 'Exact, mechanically applicable edits, in the order they must be applied.',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['file', 'rationale', 'old', 'new'],
            properties: {
              file: { type: 'string' },
              rationale: { type: 'string' },
              old: { type: 'string', description: 'Exact existing text to match. Empty string means append/insert; say where in rationale.' },
              new: { type: 'string', description: 'Exact replacement text, including the explanatory comment.' },
            },
          },
        },
        gates: { type: 'string', description: 'Test code you propose, with the file it belongs in.' },
        depends_on: { type: 'string', description: 'What you need from other dimensions before your edits are valid.' },
        risks: { type: 'string', description: 'What could go wrong applying this, and what you could not verify.' },
      },
    },
  })
))

phase('Reconcile')
const merged = await agent(
  PREAMBLE + `
## YOUR JOB: reconcile seven independent patch plans into ONE ordered master plan

Seven agents each designed repairs for a different dimension of the same mod,
in parallel, without seeing each other's work. Nearly all of them edit the SAME
file (\`examples/giant_props/spin_launch/spec.py\`). Your job is to turn their
output into a single ordered sequence a human can apply mechanically without
hitting a conflict or an ordering bug.

Here are the seven plans as JSON:

${JSON.stringify(plans.filter(Boolean), null, 2)}

## What to produce

1. **A dependency-ordered master edit list.** The datum re-work changes DECK_Z
   and HUB_Z, which nearly every geometry number keys off. Any plan that quotes
   an absolute number derived from the OLD datum must be recomputed or
   re-expressed as a formula. Find every such case and fix it — this is the main
   value you add. Re-derive numbers yourself (you may run read-only Python) and
   show your working where you change one.
2. **Conflict resolution.** Where two plans edit overlapping text, merge them
   into a single edit that satisfies both, and say which plans it came from.
   Where two plans disagree on approach, pick one and justify it.
3. **A build/verify checkpoint schedule**: which edits can be applied in one
   batch before rebuilding, and where a Blender rebuild + gate run must happen
   before continuing. Remember behaviour CODE re-reads on every build.py run but
   behaviour PARAMS/geometry/cage/handoff only move on a Blender run.
4. **A staged plan with explicit tiers**, so it can be applied incrementally:
   - Tier 1: correctness defects that make the mod broken or unshippable.
   - Tier 2: things that make it good.
   - Tier 3: things that make it WOW.
   Put each edit in a tier and order within tier.
5. **An honest cut list**: anything you judge not worth doing, or too risky, or
   that should be filed separately (e.g. sibling-prop defects). Say why.
6. **The verification plan**: exactly which gates prove each tier landed.

Be specific and complete. Someone will apply this directly. Where a plan gave a
vague edit, sharpen it; where a plan gave a number without a derivation, either
derive it or flag it as unverified.
`,
  { label: 'reconcile:master-plan', phase: 'Reconcile', effort: 'high' }
)

return { plans: plans.filter(Boolean).length, master: merged }

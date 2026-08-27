export const meta = {
  name: 'colossus-tire-critics',
  description: 'Six-lens critic panel on the COLOSSUS giant rollable tire mod; each must be utterly wowed or return actionable fixes',
  phases: [
    { title: 'Critique', detail: 'six independent specialist critics' },
    { title: 'Synthesis', detail: 'dedupe, rank, and decide the verdict' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
You are reviewing a NEW BeamNG.drive mod in the repo at ${REPO}.

THE BRIEF FROM THE USER (verbatim intent): build a giant rollable tire in
BeamNG.drive, large enough that a vehicle can drive around INSIDE it as it
rolls; driving in it should make it roll because the tire obeys physics;
"spare no polygon", it should look amazing at large size with realistic
details that sell it as a super-massive realistic tire; highly detailed
textures and geometry.

WHAT WAS BUILT: "COLOSSUS 8400/80R580" - a 28.172 m outer diameter earthmover
radial standing on its tread. It is a genuine free physics body (960 free
jbeam nodes); nothing about its motion is scripted. A car boards through a
bolted access port in the right sidewall, via a loading dock and a boarding
gangway that hangs off the tire. Two ratchet straps hold it at spawn; the
runtime cuts them and the tire is free.

FILES TO READ (read what your lens needs; do not read everything):
  ${MOD}/spec.py                                  authored constants + the Lua behaviour chunk
  ${MOD}/blender/create_colossus_tire.py          the deterministic geometry generator
  ${MOD}/authoring/ericrolph_colossus_tire.handoff.json   measured physics handoff (large)
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.jbeam   generated jbeam
  ${MOD}/mod/lua/ge/extensions/ericrolph_colossus_tire/runtime.lua            generated GE runtime
  examples/giant_props/proplib/texture_kit.py     texture families (tire_tread, tire_sidewall,
                                                  tire_sidewall_print, tire_liner, tire_laminate,
                                                  tire_bead, diamond_plate are the new ones)
  examples/giant_props/proplib/blender_kit.py     CageBuilder + exporters
  examples/giant_props/proplib/prop_builder.py    handoff -> jbeam/materials
  examples/giant_props/README.md                  the pack's conventions
  AGENTS.md                                       the repo's hard rules (long; grep it)

RENDERS (read these as IMAGES with the Read tool - they are JPEGs):
  ${RENDERS}/hero.jpg           three-quarter, with the dock
  ${RENDERS}/profile.jpg        head on, tread face
  ${RENDERS}/tread_close.jpg    lug detail: chamfers, tie bars, stone ejector, wear indicator
  ${RENDERS}/shoulder.jpg       shoulder + sidewall lettering
  ${RENDERS}/buttress.jpg       shoulder lug wrap over the buttress
  ${RENDERS}/sidewall_print.jpg moulded sidewall type close up
  ${RENDERS}/port.jpg           the access port, bezel, straps
  ${RENDERS}/port_close.jpg     port interior, cut edge laminate
  ${RENDERS}/cabin.jpg          inside the carcass (lit by a render-only work lamp)
  ${RENDERS}/dock.jpg           the loading dock
  ${RENDERS}/scale.jpg          whole thing at distance
  ${RENDERS}/underside.jpg      low angle
Texture PNGs are in ${MOD}/textures/ - these are near-black rubbers, so if you
open one directly expect it to look black; judge them in the renders or by
reading the generator code.

MEASURED FACTS (do not re-derive, but DO check them if your lens cares):
  outer diameter 28.172 m, section width 8.400 m, aspect ratio 80,
  rim/bead diameter 580 in = 14.732 m, tread depth 0.634 m,
  cavity radius 13.152 m (the floor the car drives on), cavity floor 0.933 m
  above the ground at the bottom, tread pitches 36 (variable pitch sequence),
  visual triangles 138,220, cage: 976 nodes / 4,390 beams / 2,838 collision
  triangles, tire mass 31,000 kg (deliberate departure, derived in spec.py).
  Pack precedent for scale: pachinko_tower ships 1382 nodes / 4503 beams /
  4698 tris; gforce_centrifuge ships a 39.8 MB Collada.

CONSTRAINTS THAT ARE NOT NEGOTIABLE (do not spend findings on these):
  - BeamNG props here are jbeam "vehicles"; one connected cage per prop.
  - Blender 4.5.4 headless, deterministic generator; no hand-edited runtime files.
  - Textures are procedurally generated PNG (numpy/Pillow), no external art.
  - The mass is deliberately ~1/60 of a real tire's; the reasoning is in spec.py.
    Argue with the REASONING if it is wrong, not with the existence of a departure.

YOUR JOB: be a specialist critic. The bar is "utterly wowed" - not "good
enough", not "ships". If you would not stop and stare at this, you are not
wowed. But every finding must be SPECIFIC and ACTIONABLE: name the file, the
constant or the function, say what is wrong, and say what to do instead. A
finding that amounts to "add more detail" is worthless. Rank findings by how
much they move the result.

Do not invent problems to look thorough. If something is genuinely excellent,
say so plainly - the panel needs to know what NOT to touch.
`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'wowed', 'verdict_reason', 'excellent', 'findings'],
  properties: {
    lens: { type: 'string' },
    wowed: { type: 'boolean', description: 'true ONLY if you would stop and stare; false otherwise' },
    verdict_reason: { type: 'string', description: 'one paragraph: why wowed or not' },
    excellent: {
      type: 'array', maxItems: 6,
      items: { type: 'string' },
      description: 'things that are genuinely excellent and must NOT be changed',
    },
    findings: {
      type: 'array', maxItems: 12,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'title', 'where', 'problem', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          title: { type: 'string', maxLength: 90 },
          where: { type: 'string', description: 'file:symbol or file:line, or the render that shows it' },
          problem: { type: 'string' },
          fix: { type: 'string', description: 'concrete instruction: what to change, to what value/approach' },
        },
      },
    },
  },
}

const LENSES = [
  {
    key: 'tire-engineering',
    prompt: `LENS: TIRE ENGINEERING REALISM. You are a tire design engineer who has
stood next to 59/80R63 mining radials. Judge whether this reads as a real
earthmover tire scaled up, at every distance.

Check: the size code vs the actual geometry (does 8400/80R580 produce the
modelled radii?); section profile and where maximum section width sits;
tread pattern class (is it credibly E-4/L-5 rock service?); lug proportions,
void ratio, chamfer, tie bars, stone ejectors, tread wear indicators, the
variable pitch sequence; the shoulder/buttress wrap; sidewall features -
rim line, protector ribs, moulded type, DOT/TIN format and plausibility;
the carcass laminate shown at the port cut edge (layer order, proportions,
cord pitch); bead area; anything a tire person would flinch at. Also flag
anything present that a real tire of this class would NOT have.`,
  },
  {
    key: 'beamng-physics',
    prompt: `LENS: BEAMNG PHYSICS AND JBEAM CORRECTNESS. You are a BeamNG softbody
author. The central question: WILL THIS ACTUALLY ROLL, hold its shape, and
behave, at 2000 Hz, with a car driving inside it?

Check: node count/mass distribution and the resulting stability (beamSpring
vs node mass - compute omega*dt at 2000 Hz for the stiffest families and say
whether it is safe); the beam families and whether the structure resists
ovalisation, lateral collapse and lozenging; the "inflation" truss idea;
collision triangle WINDING (the crown must collide from outside, the liner
from inside) and whether add_oriented_quad actually achieves that; whether
the car can fall through anything; node friction/nodeMaterial choices;
groundModel validity; the breakGroup strap release and whether
beamstate.breakBreakGroup is the right call; refnodes/base nodes/spawn
envelope; what happens when the tire rolls 300 m from its fixed dock nodes
(same vehicle!); contact-patch deflection under 31 t; whether the car can
actually impart enough torque. Name specific numbers.`,
  },
  {
    key: 'mesh-quality',
    prompt: `LENS: GEOMETRY AND TOPOLOGY QUALITY. You are a hard-surface/vehicle
modeller and a render TD.

Check: is the 138k triangle budget spent where it shows? Any degenerate,
zero-area, coincident or intersecting geometry? Face winding and normals
(the lettering is mirrored on one sidewall and normals are recalculated -
verify that is right)? Smooth/flat shading choices? UV correctness and
METRIC texel density (TILE_TREAD/TILE_SIDEWALL/TILE_LINER/TILE_STEEL) - is
the density consistent between adjacent surfaces, and does anything stretch?
Is the carcass watertight where it needs to be, and are there visible holes,
seams, or z-fighting? Does the tread pattern close exactly at the seam?
Look hard at the renders for artifacts: spikes, floating pieces, gaps
between the tongue and the dock, the port cut edge, the buttress wraps.
Also: is anything cheap that could be much better for few triangles?`,
  },
  {
    key: 'texture-materials',
    prompt: `LENS: TEXTURE AND MATERIAL REALISM. You are a look-dev artist.

Read the seven new families in examples/giant_props/proplib/texture_kit.py
(tire_tread, tire_sidewall, tire_sidewall_print, tire_liner, tire_laminate,
tire_bead, diamond_plate) and judge them as PBR sets, then judge how they
read in the renders. Check: base colour values for carbon-black rubber
(is 0.043 right, and is the hue neutral or should it skew?); roughness
ranges and whether the roughness map is doing real work; normal map
amplitude vs the _height_to_normal strength; whether the features are at
the right SPATIAL FREQUENCY given the metric UV tiling (a 2.2 m tile on a
1024 px map is 2.1 mm/texel - does the authored detail survive that?);
tileability; the bloom/checking/spew/bladder-lattice/laminate ideas and
whether they are executed convincingly; material JSON metallic/roughness
values in spec.PALETTE vs the maps. Say specifically what to change and to
what value.`,
  },
  {
    key: 'gameplay',
    prompt: `LENS: PLAYABILITY AND FEEL. You are a BeamNG player and a level designer.

Walk the whole loop: spawn, drive up the dock, cross the gangway, get
through the port, turn 90 degrees in the cavity, get the thing rolling,
roll, and get out again. Check the actual measured clearances against a
2.0 x 4.5 x 1.5 m car: dock grade and width, the gangway step and gap, the
port opening 3.77 m x ~6.1 m, the cavity floor 7.2 m wide and its curvature
(sagitta over a 4.5 m car on a 13.15 m radius), whether a 90 degree turn is
possible, whether the exit window through the rotating port is achievable,
what happens if the tire tips over (it is 28 m tall and 8.4 m wide - compute
the tip angle), and whether the release beat has real anticipation. Read
spec.LUA_BEHAVIOR and judge the messages, the countdown, the telemetry, the
exit warning, and whether the state machine has holes. Is this FUN, and what
single change would most improve it?`,
  },
  {
    key: 'pipeline',
    prompt: `LENS: REPO CONVENTION AND PIPELINE COMPLIANCE. You are the maintainer.

Grep AGENTS.md and read examples/giant_props/README.md, then audit this mod
against the house rules: the Blender-owns-every-coordinate evidence chain;
determinism and byte-stable reruns (is there any unseeded randomness, any
Date/time dependence, any dict-iteration-order dependence?); the one
connected cage rule and whether the strap tether is a legitimate authored
connection or a fabricated one; SHIP_ASSETS discipline; texture cooking and
the harvest manifest; the generated-never-hand-edited rule; whether spec.py
documents its departures the way the pack's other specs do; whether the
static gates in tests/test_giant_props_pack.py actually cover what matters
for THIS mod and what gate is missing; whether anything in the new
texture_kit families breaks the existing pack (they are shared code);
naming, palette coverage, materials JSON. Also read the generator for dead
code, unused variables, and anything left over from an earlier round.`,
  },
]

phase('Critique')
const reviews = await parallel(
  LENSES.map((lens) => () =>
    agent(`${CONTEXT}\n\n${lens.prompt}\n\nSet "lens" to "${lens.key}".`, {
      label: `critic:${lens.key}`,
      phase: 'Critique',
      schema: SCHEMA,
    })
  )
)

const alive = reviews.filter(Boolean)
const notWowed = alive.filter((r) => !r.wowed).map((r) => r.lens)
log(`${alive.length}/${LENSES.length} critics reported; not wowed: ${notWowed.join(', ') || 'none'}`)

phase('Synthesis')
const synthesis = await agent(
  `${CONTEXT}

You are the panel chair. Six specialist critics have reported. Here are their
verdicts and findings as JSON:

${JSON.stringify(alive, null, 2)}

Produce the work order for the next build round:
1. Verify the findings you can cheaply verify against the actual files, and
   DROP any that are factually wrong about the code (say which you dropped
   and why). Critics sometimes assert things the code does not do.
2. Merge duplicates across lenses into one instruction each.
3. Rank by how much each moves the result toward "utterly wowed", not by
   severity label.
4. For each, give a single concrete instruction an implementer can act on
   without re-reading the critic's prose.
Also state the overall verdict and what specifically is still missing for a
unanimous wow.`,
  {
    label: 'chair',
    phase: 'Synthesis',
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['unanimous_wow', 'still_missing', 'dropped', 'work_order'],
      properties: {
        unanimous_wow: { type: 'boolean' },
        still_missing: { type: 'string' },
        dropped: { type: 'array', items: { type: 'string' }, maxItems: 12 },
        work_order: {
          type: 'array',
          maxItems: 22,
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['rank', 'title', 'where', 'instruction', 'lenses'],
            properties: {
              rank: { type: 'integer' },
              title: { type: 'string', maxLength: 90 },
              where: { type: 'string' },
              instruction: { type: 'string' },
              lenses: { type: 'array', items: { type: 'string' } },
            },
          },
        },
      },
    },
  }
)

return { verdicts: alive.map((r) => ({ lens: r.lens, wowed: r.wowed })), synthesis }

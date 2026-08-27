export const meta = {
  name: 'chief-centrifuge-refine',
  description: 'Critic-first refinement loops on the five CHIEF centrifuge component modules',
  phases: [
    { title: 'Refine', detail: 'critic judges, worker fixes, repeat until wowed' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const COMP_DIR = REPO + '/examples/giant_props/gforce_centrifuge/blender/components'
const RENDER_DIR = REPO + '/examples/giant_props/gforce_centrifuge/blender/component_renders'
const BLENDER = 'C:/Users/ericr/Applications/Blender/4.5.4/blender.exe'

const SHARED_CONTRACT = `
SHARED LAYOUT CONTRACT (meters, Z-up, bowl centre = origin, entry azimuth = -Y):
- Track bowl r 0..19.5: shallow cone floor (r 2.0,z 0.5) -> (r 16.0,z 2.6), then concave velodrome bank r 16->19.5 climbing z 2.6->7.0, rim lip r 19.5 z 7.0.
- Rotor machine at centre within r 3.5; rotor arm at z ~3.4.
- Louver facade ring r 24, z 0..7.5, entry gap at -Y.
- White shell roof spans r 12..26 at z 7.5..12, big oval oculus over the bowl (r<12 stays OPEN SKY).
- Interior vault/crane between r 12..24, z 7.5..11.
Stay inside your assigned region; never create geometry outside it.

FILE CONTRACT: edit ONLY ${COMP_DIR}/<component>.py (module exposes build(materials) -> list of Blender objects). Unique object names prefixed f"{spec.MOD_ID}_". Deterministic (no unseeded random).

BUILDERS (proplib.blender_kit as bk): add_box(name, center, full_dims, material, bevel=, rotation=(euler XYZ), metric_uv=), add_cylinder(name, center, radius, depth, material, vertices=, axis="Z"|"X"|"Y", bevel=)  [NO rotation kwarg], add_torus(name, center, major_r, minor_r, material, major_segments=, minor_segments=), add_sphere(name, center, radius, material, segments=, rings=), assign_material(obj, mat). Custom meshes via bpy + mesh.from_pydata(verts, [], faces); smooth with bpy.ops.object.shade_auto_smooth(angle=math.radians(40)).
Material keys: f"{spec.MOD_ID}_" + one of shell_white, terracotta, waffle_white, rotor_blue, rotor_white, crane_orange, spoke_blue, track_grey, drum_steel, bank_hazard, floor_concrete, pylon_dark, ramp_steel, paint_white, obs_glass, console_cream, dial_white, beacon_amber, needle_red.

RENDER LOOP (run from ${REPO} with Bash, quote the exe):
  "${BLENDER}" --factory-startup --background --python examples/giant_props/gforce_centrifuge/blender/render_component.py -- <component>
Writes ${RENDER_DIR}/<component>_{front,three_quarter,top}.png. READ them with the Read tool and iterate before declaring done.`

const COMPONENTS = [
  { id: 'track_bowl', brief: 'The CHIEF hypergravity platform as a drivable arena: light-grey machined cone floor (r2->r16, z0.5->2.6) with subtle radial seam grooves; concave velodrome bank r16->19.5 climbing to z7.0 (must read smooth and drivable, 4-5 profile rings); 8 royal-blue radial spokes lying FLUSH on the cone from a blue hub ring (r2.2) to r15.8 following the slope exactly; hazard-yellow rim band + steel bead at the lip; 24 triangular gusset ribs on the outer bank face; clean circular opening r<2.0 for the rotor pedestal. Must look like a precision instrument at massive scale - cold laboratory elegance, not a skate ramp.' },
  { id: 'rotor_machine', brief: 'The CHIEF rotor: low white DOMED pedestal (r3.2 z0.5 -> flat cap r1.2 z2.6) with royal-blue skirt band and 2 inspection hatches; horizontal ROTOR ARM at z3.4 spanning 14 m along X - white outer sections, broad royal-blue centre band (~4 m), blue end collars, ribbed cooling-fin rings, panel lines; small red auxiliary cylinder slung under the arm near the hub; two massive light-grey C-frame bearing supports at x=+-2.6 with bearing collars wrapping over the arm WITHOUT touching it (5 cm clearance, the arm spins); steel hub column through the pedestal top. CRITICAL NAMING: every arm piece that must SPIN is named f"{spec.MOD_ID}_rotorarm_..."; static pieces f"{spec.MOD_ID}_rotor_...". Precision aerospace hardware.' },
  { id: 'shell_roof', brief: 'The signature flowing white shell: annular swept surface r12 (upturned rolled inner rim, z9.0) to r26 outer eave (z7.6), crest ~z11.5 near r18-20, profile an elegant S like stretched fabric; ENTRY SWOOP where the eave lifts to z10 over a ~50 deg sector at -Y, blending smoothly; TWO secondary oval oculi (~7x4.5 m) cut through at azimuths ~60 and ~200 around r19 with slim rolled lips; subtle panelization seam lines (16 meridians, 4 parallels, very slim, flush); r<12 stays open. Smooth shading, no faceting kinks - world-class architecture, a manta-ray tent shell.' },
  { id: 'louver_facade', brief: 'Terracotta vertical louver curtain wall: 150 fins (0.28 x 0.5 x 7.3) at r24 every 2.4 deg with a 16-deg entry gap at -Y; dark recessed glazing band behind; entry portal framed by two chunky terracotta pylons + a deep white canopy slab at z8; a 10 m wide vehicle-friendly concrete ramp rising 0.45 m to the sill; slim white fascia rail capping the fins at z7.5 and a steel base rail. Rhythm of the fins is the star.' },
  { id: 'interior_vault', brief: 'Waffle-vault soffit + orange gantry crane: gently domed annular soffit (r13..23.5, z7.6..9.0, waffle_white) with a coffer grid of 24 radial ribs + 3 concentric ring ribs hanging just below so coffers read as recessed diamonds; ORANGE bridge crane spanning the hall above the bowl rim (two parallel box girders at z8.6 along X, end carriages, riding grey rail beams as chords at y=+-10.2 supported by 3 slim white columns each); crane trolley + hook block on a thin cable; 24 round ceiling lights on the soffit at r17 and r20.' },
]

const CRITIC_SCHEMA = {
  type: 'object',
  properties: {
    wowed: { type: 'boolean' },
    score: { type: 'number' },
    feedback: { type: 'string' },
  },
  required: ['wowed', 'score', 'feedback'],
}
const WORKER_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    notes: { type: 'string' },
  },
  required: ['status', 'notes'],
}

const results = await pipeline(
  COMPONENTS,
  async (comp) => {
    let verdict = null
    for (let round = 1; round <= 3; round += 1) {
      verdict = await agent(
        `You are the CRITIC for the "${comp.id}" component of a BeamNG.drive giant prop recreating the CHIEF Centrifugal Hypergravity facility (Hangzhou) design language. Judge ONLY this component.

TARGET BRIEF:
${comp.brief}

READ all three renders with the Read tool:
${RENDER_DIR}/${comp.id}_front.png
${RENDER_DIR}/${comp.id}_three_quarter.png
${RENDER_DIR}/${comp.id}_top.png
Then skim ${COMP_DIR}/${comp.id}.py for cheats: floating geometry, coplanar z-fighting slabs, wrong materials, regions violated, unsmoothed curves that the brief calls smooth.

Score 0-10 on silhouette fidelity, proportion, craftsmanship, material discipline, and AAA-game plausibility. wowed=true ONLY at 8.5+. Give at most 6 concrete prioritized fixes. If a render is missing or the module fails to build, wowed=false and say exactly what broke.`,
        { label: `critique:${comp.id}:r${round}`, phase: 'Refine', schema: CRITIC_SCHEMA, effort: 'high' }
      )
      if (!verdict) return { component: comp.id, verdict: { wowed: false, score: 0, feedback: 'critic died' } }
      if (verdict.wowed) {
        log(`${comp.id}: WOWED at round ${round} (score ${verdict.score})`)
        break
      }
      log(`${comp.id}: round ${round} score ${verdict.score} - fixing`)
      const worker = await agent(
        `You are the WORKER improving the "${comp.id}" component module of a BeamNG.drive giant prop that recreates the CHIEF Centrifugal Hypergravity facility design language.

TARGET BRIEF:
${comp.brief}

${SHARED_CONTRACT}

CRITIC FEEDBACK (score ${verdict.score}/10) - address EVERY point, highest priority first:
${verdict.feedback}

Edit ${COMP_DIR}/${comp.id}.py, re-run the render harness, READ the renders, self-critique, iterate at least twice before returning. Return status=done with honest notes on anything you could not fix.`,
        { label: `fix:${comp.id}:r${round}`, phase: 'Refine', schema: WORKER_SCHEMA, effort: 'high' }
      )
      if (!worker || worker.status === 'blocked') {
        return { component: comp.id, verdict: { wowed: false, score: verdict.score, feedback: 'worker blocked: ' + (worker ? worker.notes : 'died') } }
      }
    }
    return { component: comp.id, verdict }
  }
)

return { components: results }
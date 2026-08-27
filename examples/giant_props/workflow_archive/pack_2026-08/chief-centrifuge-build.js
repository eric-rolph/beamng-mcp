export const meta = {
  name: 'chief-centrifuge-build',
  description: 'Worker+critic pairs build CHIEF-facility centrifuge components with render critique loops',
  phases: [
    { title: 'Author', detail: 'five worker/critic pairs iterate on component modules' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const COMP_DIR = REPO + '/examples/giant_props/gforce_centrifuge/blender/components'
const RENDER_DIR = REPO + '/examples/giant_props/gforce_centrifuge/blender/component_renders'
const BLENDER = 'C:/Users/ericr/Applications/Blender/4.5.4/blender.exe'

const SHARED_CONTRACT = `
SHARED CONTRACT (all lengths meters, Z-up, bowl centre = origin, authored +Y = drive/entry axis; the entry/garage azimuth is -Y):
- Track bowl occupies r 0..19.5: shallow cone floor from (r 2.0, z 0.5) rising to (r 16.0, z 2.6), then a steep curved bank r 16.0->19.5 climbing z 2.6->7.0, rim lip at r 19.5 z 7.0.
- Rotor machine at centre: pedestal within r 3.5, rotor arm at z ~3.4.
- Louver facade ring at r 24 (outer wall), z 0..7.5, with a 7 m wide entry opening centred on -Y.
- White shell roof spans r 12..26 at z 7.5..12; a large oval oculus over the bowl (the r<12 region is OPEN SKY - never cover it).
- Interior vault/crane live between r 12..24, z 7.5..11 (under the shell).
Your component must stay inside its assigned region and MUST NOT create geometry outside it.

FILE CONTRACT: create exactly one file, ${COMP_DIR}/<component>.py with:
  from __future__ import annotations
  import math
  import spec
  from proplib import blender_kit as bk
  def build(materials): ...  # returns list of Blender objects
Name every object f"{spec.MOD_ID}_<component>_<something>" (unique names). Deterministic only (no unseeded random). Do not edit ANY other file.

AVAILABLE BUILDERS (from proplib.blender_kit as bk):
- bk.add_box(name, (x,y,z)_center, (dx,dy,dz)_full_dims, material, bevel=0.04, rotation=(rx,ry,rz) euler XYZ radians, metric_uv=None)
- bk.add_cylinder(name, center, radius, depth, material, vertices=24, axis="Z"|"X"|"Y", bevel=0.0, radius_x=None, radius_y=None)  # NO rotation kwarg
- bk.add_torus(name, center, major_radius, minor_radius, material, major_segments=48, minor_segments=12)
- bk.add_sphere(name, center, radius, material, segments=16, rings=12)
- bk.assign_material(obj, material)
- Custom meshes: import bpy; mesh = bpy.data.meshes.new(name); mesh.from_pydata(verts, [], faces); mesh.update(); obj = bpy.data.objects.new(name, mesh); bpy.context.scene.collection.objects.link(obj); bk.assign_material(obj, material). For smooth shading: select the object, bpy.ops.object.shade_auto_smooth(angle=math.radians(40)).
Materials dict keys (use ONLY these): f"{spec.MOD_ID}_" + one of: shell_white, terracotta, waffle_white, rotor_blue, rotor_white, crane_orange, spoke_blue, track_grey, drum_steel, bank_hazard, floor_concrete, pylon_dark, ramp_steel, paint_white, obs_glass, console_cream, dial_white, beacon_amber.

RENDER LOOP: after every edit, run from repo root C:/Users/ericr/beamng-mcp (Bash; quote the exe path):
  "${BLENDER}" --factory-startup --background --python examples/giant_props/gforce_centrifuge/blender/render_component.py -- <component>
It writes ${RENDER_DIR}/<component>_front.png, _three_quarter.png, _top.png. READ those images yourself and iterate until they look excellent BEFORE declaring done. If Blender errors, read the traceback and fix. Budget: <= 9000 triangles for your component (check the console output object count sanity; prefer elegant economy).`

const COMPONENTS = [
  {
    id: 'track_bowl',
    design: `Build the TRACK BOWL - the star of the machine, modeled on the CHIEF hypergravity platform: a vast shallow steel cone like a giant satellite dish lying flat, blended into a velodrome bank.
- Cone floor: light-grey (track_grey) surface of flat panels from r 2.0 (z 0.5) to r 16.0 (z 2.6), built as a smooth swept cone mesh (from_pydata ring grid, ~48 azimuth steps) with subtle radial seam grooves (thin darker pylon_dark lines lying flush every 15 degrees, slim boxes following the slope).
- Banked wall: continuous curved transition from the cone edge (r 16, z 2.6) climbing steeply to the rim (r 19.5, z 7.0) - use 4-5 intermediate profile rings so the curve reads smooth and drivable (a velodrome wall, concave), same swept-mesh technique, track_grey.
- ROYAL-BLUE RADIAL SPOKES (spoke_blue): 8 flat bars (about 0.5 m wide, 0.1 thick) lying FLUSH on the cone surface, running from a blue hub ring (torus, r 2.2) out to r 15.8, following the cone slope exactly (compute the tilt from the cone profile). Like the reference's blue lifting-frame spokes.
- Rim: hazard-yellow (bank_hazard) edge band torus at the very top lip (r 19.5, z 7.0) plus a slim steel rim bead.
- Gusset ribs: around the outside of the bank (visible from outside), 24 small triangular rib plates (drum_steel) angled against the outer face, like the reference's rim gussets.
- Centre: leave r < 2.0 EMPTY (the rotor pedestal goes there; a clean circular opening edge ring in drum_steel is welcome).
The whole thing must look precision-engineered and MASSIVE - a machined instrument, not a skate ramp. Aim for the cold laboratory elegance of the reference.`,
  },
  {
    id: 'rotor_machine',
    design: `Build the ROTOR MACHINE centrepiece, modeled on the CHIEF hypergravity centrifuge rotor:
- Low white DOMED pedestal (rotor_white) centred at origin: dome from r 3.2 at z 0.5 rising to a flat top cap at r 1.2, z 2.6 (use a swept profile mesh or a squashed sphere + cylinder skirt), with a royal-blue (rotor_blue) skirt band torus at its base and 2 small circular inspection hatches (flat cylinders, axis Y, slightly proud) on the dome face.
- ROTOR ARM mounted horizontally at z 3.4 spanning 14 m tip-to-tip along the X axis: a cylindrical arm (radius 0.65) built from segments - white outer sections (rotor_white), a broad royal-blue centre band about 4 m wide (rotor_blue), and blue end caps with slightly larger radius collars. Add ribbed cooling-fin rings (thin torus rings, drum_steel, every 0.8 m along the white sections) and slim panel lines. IMPORTANT: name every arm piece f"{spec.MOD_ID}_rotorarm_..." (the integrator splits those into the spinning part) and every static piece f"{spec.MOD_ID}_rotor_..." .
- A small RED auxiliary cylinder (needle_red is not available - use crane_orange or make it deep red via beacon_amber? Use materials[f"{spec.MOD_ID}_needle_red"] if present in the dict, else crane_orange) slung under the arm near the hub, axis X, radius 0.28, length 2.2.
- Two massive light-grey C-frame bearing supports (ramp_steel) flanking the hub at x = +-2.6: each a sturdy portal (two thick uprights + a top beam with a bearing collar half-ring wrapping over the arm) - they must NOT touch the arm (5 cm clearance) since the arm spins.
- Hub: a vertical steel column (drum_steel, r 0.5) from the pedestal top up through the arm centre with a collar above and below.
The machine must look like precision aerospace hardware: clean, chunky, purposeful. This sits in the bowl centre (r < 3.5) - stay inside that region, pedestal base at z 0.5.`,
  },
  {
    id: 'shell_roof',
    design: `Build the WHITE SHELL ROOF, modeled on the CHIEF facility's flowing panelized shell (its signature): a continuous taut white surface (shell_white) that flows like stretched fabric over the building ring.
- Overall: an annular shell spanning r 12 (inner oculus edge, z 9.0 with a softly UPTURNED rolled rim) out to r 26 (outer eave), crown height ~z 11.5 around r 18-20, draping DOWN to z 7.6 at the outer eave. Build as a swept profile mesh (from_pydata, ~64 azimuth steps, 8-10 radial profile points) - the profile should be an elegant S: rises from the upturned inner rim, crests, then sweeps down and slightly outward at the eave like fabric being lifted.
- ENTRY SWOOP: at the -Y azimuth (entry side, a ~50 degree sector), the eave lifts into a higher arched opening (eave rises to z 10 at the centreline of the sector, blending smoothly back to z 7.6 over the sector edges) - modulate the outer-edge z of the swept profile by azimuth with a smooth cosine bump.
- TWO SECONDARY OVAL OCULI: two smaller teardrop/oval openings cut through the shell at azimuths ~60 and ~200 degrees, centred around r 19, sized ~7 x 4.5 m, with gently upturned rims - build these by OMITTING faces inside the oval (test point-in-ellipse in the swept grid, in the shell's parameter space) and adding a slim rolled lip torus-like ring (can be an ellipse of small cylinders or a scaled torus) around each opening in shell_white.
- PANELIZATION: suggest the diamond-panel look with fine seam lines - lay a sparse grid of very slim, slightly darker (dial_white or waffle_white... use track_grey at 0.02 thickness) seam strips flush on the shell along ~16 meridians and 4 parallels; keep it subtle.
- The r < 12 region stays OPEN (main oculus over the bowl).
Elegance is everything here: smooth shading (shade_auto_smooth), no faceting kinks, flowing curves. It should read as world-class architecture, a manta-ray tent shell.`,
  },
  {
    id: 'louver_facade',
    design: `Build the TERRACOTTA LOUVER FACADE, modeled on the CHIEF facility's warm curtain wall beneath the white shell:
- A ring of VERTICAL FINS (terracotta) at r 24.0: slim rectangles 0.28 wide (tangential) x 0.5 deep (radial) x 7.3 tall (z 0.15..7.45), spaced every 2.4 degrees of azimuth (=150 fins), EXCEPT a 16-degree gap centred on -Y (the entry).
- Behind the fins at r 24.5: a continuous DARK GLAZING band (obs_glass looks pale - use pylon_dark for a deep recessed backdrop) from z 0.3..7.3, built as a simple open cylinder arc (from_pydata ring wall) with the same entry gap.
- ENTRY PORTAL at -Y: frame the gap with two chunky terracotta pylon boxes (1.2 x 1.2 x 8.0) and a deep flat canopy slab (shell_white, 9 x 4 x 0.5) at z 8.0 spanning the opening; add a low wide 3-step plinth (floor_concrete boxes) at the threshold, and slim hazard-yellow (bank_hazard) edge nosing on the steps... actually make the steps a smooth vehicle-friendly ramp wedge instead (cars must drive through): a 10 m wide, 6 m long concrete ramp rising 0.45 m to the doorway sill.
- Top rail: a slim white (shell_white) fascia beam ring capping the fins at z 7.5 (segmented boxes following the circle every 10 degrees), and a matching base rail (drum_steel) at z 0.2.
The rhythm of the fins is the star: even, warm, precise. Stay in r 23..26, z 0..8.2 (plus the entry ramp reaching out to y -30).`,
  },
  {
    id: 'interior_vault',
    design: `Build the INTERIOR VAULT + GANTRY CRANE, modeled on the CHIEF hall interior:
- WAFFLE VAULT: the visible underside ceiling between r 13..23.5 at z ~7.6..9.0 (it sits UNDER the shell roof): build a gently domed annular soffit (waffle_white, swept mesh, ~48 azimuth steps) whose underside carries a COFFER GRID - crossing ribs: 24 radial ribs (slim boxes following the soffit slope, 0.25 wide x 0.35 deep, waffle_white) and 3 concentric ring ribs (torus, minor 0.16, waffle_white) at r 15/18/21.5, all hanging just below the soffit so the coffers read as recessed diamonds.
- ORANGE GANTRY CRANE (crane_orange): a bridge crane spanning the hall ABOVE the bowl rim: two parallel box girders (0.7 x 20 x 0.9) side by side 1.4 m apart, running along the X axis at z 8.6, from r -10 to +10 (they visually hang inside the oculus - that is fine and dramatic), with end carriages (boxes) at both ends riding a pair of slim grey rail beams (ramp_steel, 0.4 x 0.5 section) that run chords across at y = +-10... wait the rails must be supported: run the two rail beams as CHORDS across the vault at y = +-10.2, z 8.3, from x -18..18, each supported by 3 slim white columns (shell_white, r 0.25 cylinders) dropping to z 7.0 where they meet the bank rim region - place columns at x = -14, 0, 14.
- A small crane TROLLEY (crane_orange box 1.6 x 1.2 x 1.0) with a hook block (drum_steel small box + hazard stripe) hanging 1.5 m below on a slim cable (pylon_dark cylinder r 0.03).
- 24 small round ceiling LIGHTS (dial_white flat cylinders r 0.28, axis Z) dotted on the soffit underside ring at r 17 and r 20 (12 each, alternating azimuths).
Keep everything r 9..24 (crane bridge may cross the centre at high z), z 6.8..9.2.`,
  },
]

const WORKER_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    triangles_estimate: { type: 'number' },
    notes: { type: 'string' },
  },
  required: ['status', 'notes'],
}
const CRITIC_SCHEMA = {
  type: 'object',
  properties: {
    wowed: { type: 'boolean' },
    score: { type: 'number' },
    feedback: { type: 'string' },
  },
  required: ['wowed', 'score', 'feedback'],
}

const results = await pipeline(
  COMPONENTS,
  async (comp) => {
    let feedback = ''
    let verdict = null
    for (let round = 1; round <= 4; round += 1) {
      const worker = await agent(
        `You are the WORKER building one component of a BeamNG.drive giant prop that recreates the design language of the CHIEF Centrifugal Hypergravity facility (Hangzhou). Work in repo C:/Users/ericr/beamng-mcp.

YOUR COMPONENT: ${comp.id}
DESIGN BRIEF (translated from reference photographs - follow it faithfully):
${comp.design}

${SHARED_CONTRACT}

${round > 1 ? 'CRITIC FEEDBACK FROM THE PREVIOUS ROUND - address every point:\n' + feedback : 'This is round 1: create the module from scratch.'}

Work loop: write/edit ONLY your module file, run the render harness, READ the three PNGs, self-critique against the brief, iterate (at least 2 self-iterations before declaring done). Return status done with honest notes about weaknesses that remain.`,
        { label: `build:${comp.id}`, phase: 'Author', schema: WORKER_SCHEMA, effort: 'high' }
      )
      if (!worker || worker.status === 'blocked') {
        return { component: comp.id, verdict: { wowed: false, score: 0, feedback: 'worker blocked: ' + (worker ? worker.notes : 'died') } }
      }
      verdict = await agent(
        `You are the CRITIC for one component of a BeamNG giant prop recreating the CHIEF Centrifugal Hypergravity facility's design language. Be exacting - you sign off only when genuinely WOWED, judging against this brief:

${comp.design}

READ these three renders (use the Read tool on each):
${RENDER_DIR}/${comp.id}_front.png
${RENDER_DIR}/${comp.id}_three_quarter.png
${RENDER_DIR}/${comp.id}_top.png

Also skim the module source at ${COMP_DIR}/${comp.id}.py for cheats (floating geometry, wrong materials, regions violated: ${'the shared layout contract places this component in its assigned region only'}).

Judge: silhouette fidelity to the brief, proportion, craftsmanship (no z-fighting slabs, no floating parts, smooth curves where specified), material usage, and whether it would look professional inside a AAA game. Score 0-10. wowed=true ONLY for 8.5+. Give concrete, prioritized feedback (max 6 points) the worker can act on. If renders are missing, wowed=false and say so.`,
        { label: `critique:${comp.id}`, phase: 'Author', schema: CRITIC_SCHEMA, effort: 'high' }
      )
      if (!verdict) {
        return { component: comp.id, verdict: { wowed: false, score: 0, feedback: 'critic died' } }
      }
      if (verdict.wowed) break
      feedback = verdict.feedback
      log(`${comp.id}: round ${round} score ${verdict.score} - iterating`)
    }
    return { component: comp.id, verdict }
  }
)

return { components: results }
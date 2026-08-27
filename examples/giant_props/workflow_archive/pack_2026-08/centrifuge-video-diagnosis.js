export const meta = {
  name: 'centrifuge-video-diagnosis',
  description: 'Exhaustive diagnosis of the centrifuge entry/track defects from video frames + code + measured geometry',
  phases: [
    { title: 'Investigate', detail: 'parallel lenses: frames, ramp math, cage-vs-visual, portal clearance' },
    { title: 'Verify', detail: 'adversarial refutation of every finding' },
    { title: 'Synthesize', detail: 'ranked root-cause report' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const CFG = REPO + '/examples/giant_props/gforce_centrifuge'
const FRAMES = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr/01aac343-2951-4984-a938-b549490f7a7b/scratchpad/vid3'
const BLENDER = 'C:/Users/ericr/Applications/Blender/4.5.4/blender.exe'

const CONTEXT = `
SUBJECT: a BeamNG.drive giant prop - a drivable centrifuge (the "CHIEF" hypergravity facility). A player recorded a 15 s video (30 frames at 2 fps in ${FRAMES}/f001.png .. f030.png) showing that a car CANNOT cleanly enter the drum and that surfaces appear missing.

KEY GEOMETRY FACTS (verified by measurement this session):
- Cone deck (drivable floor): r 2.0 -> 15.2 m, z 0.5 -> 2.48 m (slope 0.15). Built by ${CFG}/blender/components/track_bowl.py (_build_cone, CONE_R0/CONE_Z0/CONE_SLOPE/BANK_R0).
- Bank (banked wall) real curve: starts r 15.2 z 2.48, ends r 18.551 z 5.775. Sampled from track_bowl._bank_frame(). spec.BANK_PROFILE now holds that measured 7-point curve.
- Entry: a "vomitory" ramp from the concourse (r~30, z 0) climbing to the cone lip (r 15.2, z 2.48), passing THROUGH a portal opened in the bank at azimuth 257-283 deg. Ramp visual is a single pitched box in ${CFG}/blender/create_gforce_centrifuge.py (search "_vomitory_ramp"); the collision cage tunnel stations are in build_cage() (search "tunnel_stations").
- Collision cage: cone = 4 radial rings x 28 azimuths of quads; bank = spec.BANK_PROFILE levels x 28 segments (both windings); a perimeter "skirt" wall at r 15.2 from z 0 to 2.48 closes the void UNDER the raised dish; a ground plate spans +-26 m at z 0..0.08 with floor_concrete (pale speckled).
- The prop is a VEHICLE (jbeam). Authored coordinates map to world with a 180 deg Z flip: authored (x, y) renders at world (-x, -y). Authored -Y (the entry) appears at world +Y.
- A textureless dark material (track_asphalt) paints the cone; the ground apron uses floor_concrete which is PALE SPECKLED. If you see pale speckle where the track should be, you are seeing the apron/ground THROUGH or PAST the cone.

WHAT THE PLAYER REPORTS: car gets hung up entering; suspension/tires break; a visible gap/missing surface where the car drives across; the drum interior shows surfaces that should not be visible.

Repo root is ${REPO}. Read any source you need. You may run Blender headless:
  "${BLENDER}" --factory-startup --background --python <script.py>
and you may write throwaway analysis scripts under C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr/01aac343-2951-4984-a938-b549490f7a7b/scratchpad/.
DO NOT modify any file under ${CFG} or ${REPO}/examples - this is a READ-ONLY diagnosis. Analysis scripts in scratchpad are fine.`

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          evidence: { type: 'string' },
          location: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          proposed_fix: { type: 'string' },
        },
        required: ['title', 'evidence', 'location', 'severity', 'proposed_fix'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    confidence: { type: 'number' },
    reasoning: { type: 'string' },
  },
  required: ['refuted', 'confidence', 'reasoning'],
}

const LENSES = [
  {
    key: 'frames-early',
    prompt: `Examine video frames f001..f010 (the approach and first contact with the entrance). READ EACH IMAGE with the Read tool. Describe precisely what surfaces are visible, where the car is, what it collides with, and identify any place where a surface visibly ENDS, steps, or shows the pale speckled ground where track should be. Correlate what you see against the geometry facts and name the specific mesh/code responsible.`,
  },
  {
    key: 'frames-late',
    prompt: `Examine video frames f011..f030 (the car on/at the ramp and inside). READ EACH IMAGE with the Read tool. Identify the exact failure: what does the car catch on, where does it drop, what geometry is missing or misaligned. Name the specific mesh/code responsible.`,
  },
  {
    key: 'ramp-math',
    prompt: `Analytically audit the ENTRY RAMP. Read create_gforce_centrifuge.py: the "_vomitory_ramp" box (centre, dims, rotation) and build_cage()'s tunnel_stations + the bridge quad to the cone ring. Compute, in world/authored coordinates, the ramp's TOP SURFACE height as a function of radius, and the cone deck height as a function of radius (z = 0.5 + (r-2.0)*0.15 for r<=15.2). Find every radius where they disagree by more than 5 cm, and every place the visual ramp and the COLLISION tunnel disagree. Also check the ramp's inner end vs the cone lip: is there a step, a gap, or an overlap? Show your arithmetic.`,
  },
  {
    key: 'cage-vs-visual',
    prompt: `Audit COLLISION vs VISUAL across the whole drivable surface. Write a scratchpad python script that (a) imports track_bowl.py's pure-math head (stub bpy/bmesh/mathutils modules, exec the source up to the first mesh helper) to get the real cone and bank curves, and (b) reproduces the cage geometry from create_gforce_centrifuge.py build_cage() (cone rings/azimuths, bank levels, skirt). Report every radius/azimuth where collision and visual differ by >5 cm, including the POLYGONAL INSCRIPTION error (cage uses N azimuth divisions; a chord at radius r sits r*(1-cos(pi/N)) inside the true circle). Quantify at the cone rim and at the bank.`,
  },
  {
    key: 'portal-clearance',
    prompt: `Audit the PORTAL the car drives through. The bank cage skips quads for levels < 5 at GARAGE_SEGMENTS {20,21} of 28; the visual bank skips faces for the lower 72% of its profile rows across azimuth 257-283 deg. Determine: the actual clear WIDTH (arc) and HEIGHT of the opening at each radius the car traverses, versus a typical BeamNG car (about 1.9 m wide, 1.45 m tall). Does the ramp pass UNDER any part of the bank, and if so what is the clearance? Also check the vomitory side walls / kick / stripe / cap boxes for intrusion into the driving envelope, and the door plug's PARKED position for intrusion. Show numbers.`,
  },
  {
    key: 'skirt-and-void',
    prompt: `Audit the region UNDER and AROUND the dish. The cone deck is raised (z 0.5..2.48) over a ground plate at z 0..0.08 with a pale speckled concrete material. A perimeter "skirt" at r 15.2 spans z 0..2.48 to close that void, with its quads skipped at the mouth. Determine whether any sightline or drivable path lets a car reach the void UNDER the cone, and whether the pale speckled surface the player sees inside the drum could be that ground plate showing through a hole, a missing cone face, or a backface-culled surface. Check the cone mesh's face winding and whether the cone is single-sided. Be specific about which object and which faces.`,
  },
]

const scouted = await pipeline(
  LENSES,
  async (lens) => {
    const found = await agent(
      `You are a forensic diagnostician on a BeamNG prop. LENS: ${lens.key}.\n\n${CONTEXT}\n\nYOUR TASK:\n${lens.prompt}\n\nReport concrete, falsifiable findings. Each needs: title, EVIDENCE (frame numbers you actually read, or arithmetic you actually did, or file:line you actually read), location (file:line or mesh name), severity, and a specific proposed fix. Do not speculate without labelling it as such. Prefer 2-5 high-quality findings over a long weak list.`,
      { label: `scout:${lens.key}`, phase: 'Investigate', schema: FINDINGS_SCHEMA, effort: 'high' }
    )
    if (!found || !found.findings || !found.findings.length) return []
    // Verify each finding with three adversarial lenses.
    const verified = await parallel(
      found.findings.map((f) => () =>
        parallel(
          ['geometry-arithmetic', 'source-code-truth', 'does-it-explain-the-video'].map((angle) => () =>
            agent(
              `You are an adversarial VERIFIER. Try hard to REFUTE this claimed defect in a BeamNG centrifuge prop. Judge it through the "${angle}" lens.\n\n${CONTEXT}\n\nCLAIM: ${f.title}\nEVIDENCE OFFERED: ${f.evidence}\nLOCATION: ${f.location}\nPROPOSED FIX: ${f.proposed_fix}\n\nGo check independently (read the files, redo the arithmetic, read the frames). Set refuted=true if the claim is wrong, overstated, already fixed in the current source, or cannot explain the observed video. Default to refuted=true when genuinely uncertain. Give reasoning citing what you actually checked.`,
              { label: `verify:${angle}`, phase: 'Verify', schema: VERDICT_SCHEMA, effort: 'high' }
            )
          )
        ).then((votes) => {
          const good = votes.filter(Boolean)
          const kept = good.filter((v) => !v.refuted).length
          return { ...f, votes_kept: kept, votes_total: good.length, verdicts: good.map((v) => v.reasoning) }
        })
      )
    )
    return verified.filter(Boolean).filter((f) => f.votes_kept >= 2)
  }
)

const confirmed = scouted.flat().filter(Boolean)
log(`confirmed findings after adversarial verification: ${confirmed.length}`)

const report = await agent(
  `You are the LEAD ENGINEER writing the final diagnosis of why a car cannot enter this BeamNG centrifuge and why surfaces appear missing.\n\n${CONTEXT}\n\nCONFIRMED FINDINGS (each survived >=2 of 3 adversarial verifiers):\n${JSON.stringify(confirmed, null, 1)}\n\nWrite a tight report: (1) THE single root cause if there is one, or the ranked set of independent causes; (2) for each, the precise geometry/code at fault with numbers; (3) an ordered fix plan where each step is concrete and independently testable; (4) explicitly call out anything that is still uncertain. Be rigorous and readable. Plain prose plus short lists. No fluff.`,
  { label: 'synthesis', phase: 'Synthesize', effort: 'high' }
)

return { confirmed_count: confirmed.length, findings: confirmed, report }
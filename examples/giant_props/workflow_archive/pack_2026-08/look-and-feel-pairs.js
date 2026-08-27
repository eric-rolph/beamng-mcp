export const meta = {
  name: 'look-and-feel-pairs',
  description: 'Worker+critic pairs polish pachinko tower and sumo gyro visuals until the critic is utterly wowed',
  phases: [
    { title: 'Look & feel rounds', detail: 'worker edits visuals, renders; critic judges the pixels; up to 3 rounds per object' },
  ],
}

const ROOT = 'C:/Users/ericr/beamng-mcp'
const SP = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr/01aac343-2951-4984-a938-b549490f7a7b/scratchpad'
const MODS = ['pachinko_tower', 'sumo_gyro_platform']

const WORKER_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['changes', 'renders_ok', 'deferred'],
  properties: {
    changes: { type: 'array', items: { type: 'string' }, description: 'each visual change made, one line each' },
    deferred: { type: 'array', items: { type: 'string' }, description: 'fixes that would need functional geometry/behavior changes - noted, NOT done' },
    renders_ok: { type: 'boolean', description: 'true only after the final Blender run printed PROP RENDER DONE with zero Traceback' },
  },
}

const CRITIC_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['wowed', 'score', 'first_read', 'fixes', 'best_view'],
  properties: {
    wowed: { type: 'boolean' },
    score: { type: 'number', description: '1-10; the pack bar (CHIEF centrifuge) is 8.5; wowed needs >= 9' },
    first_read: { type: 'string', description: 'one sentence: what the machine reads as at first glance' },
    fixes: { type: 'array', items: { type: 'string' }, description: 'surgical ordered demands, each implementable via palette or build_visual only; empty if wowed' },
    best_view: { type: 'string' },
  },
}

function renderCmd(key) {
  return '"C:/Users/ericr/Applications/Blender/4.5.4/blender.exe" --factory-startup --background --python examples/giant_props/' + key + '/blender/create_' + key + '.py --python "' + SP + '/render_prop_views.py" -- ' + key + ' "' + SP + '/renders/' + key + '" 2>&1 | grep -iE "traceback|RENDER DONE"'
}

function guardrails(key) {
  return [
    'HARD GUARDRAILS - this mod just had precision functional fixes landed; you touch VISUALS ONLY:',
    '- ALLOWED in ' + ROOT + '/examples/giant_props/' + key + '/spec.py: the PALETTE dict ONLY (colors, metallic, roughness, texture family params, marquee sign text). Texture families must already exist in examples/giant_props/proplib/texture_kit.py (grep its family names first) or be textureless color-only entries. NEW families are FORBIDDEN (in-engine they render pure white - documented trap).',
    '- ALLOWED in ' + ROOT + '/examples/giant_props/' + key + '/blender/create_' + key + '.py: the build_visual function only - add, reshape, rematerial or remove DECORATIVE meshes.',
    '- FORBIDDEN everywhere: LUA_BEHAVIOR, BEHAVIOR, TRIGGERS, EFFECTS, every non-PALETTE spec constant, build_cage / NodeStore / any cage or collision code, build_parts (part contents, pivots, collision flags, names), and functional geometry (doorways, deck, pegs, ramp, dish profile, kerb positions). If a fix seems to need any of那 - do NOT do it; record it in `deferred`.',
    '- Emissives are INERT in this pack (hard law). Never rely on glow; make shape and color read without it.',
    '',
    'BUILD + RENDER LOOP (run from ' + ROOT + '; pass timeout 420000 to every Blender call - it takes minutes):',
    '1. If you changed PALETTE: ./.venv/Scripts/python.exe examples/giant_props/build.py ' + key + ' textures',
    '2. ' + renderCmd(key),
    '   Blender exits 0 even when the script throws - the grep MUST show "PROP RENDER DONE" and no Traceback, or your edit broke the generator and you must fix it before ending.',
    '3. Read your five fresh renders at ' + SP + '/renders/' + key + '/' + key + '_{front,three_quarter,side,top,approach}.png and self-check before you finish.',
    'Do NOT run build.py "all", do not touch dist/, do not install anything.',
  ].join('\n')
}

function intent(key) {
  return [
    'DESIGN INTENT SOURCES (read all three):',
    '- ' + ROOT + '/examples/giant_props/' + key + '/spec.py module docstring (the design story).',
    '- ' + ROOT + '/examples/giant_props/' + key + '/authoring/listing_copy.md - the certified page that SELLS this machine; the renders must look like the thing that page promises.',
    '- ' + ROOT + '/examples/giant_props/README.md - the pack design rule: exaggerate the anticipation; every prop has a real-world reference it must visually honour.',
  ].join('\n')
}

function workerPrompt(key, round, fixes) {
  const head = round === 1
    ? 'You are the look-and-feel WORKER for the BeamNG giant-props mod "' + key + '" (round 1: opinionated first pass).\n\nBaseline renders (JPEG, pre-pass) are at ' + SP + '/renders/' + key + '/' + key + '_{front,three_quarter,side,top,approach}.jpg - Read them all first, then read the intent sources, decide what stands between this machine and its concept, and fix it.'
    : 'You are the look-and-feel WORKER for the BeamNG giant-props mod "' + key + '" (round ' + round + ': the critic was not wowed).\n\nCRITIC DEMANDS - apply every one, in order, within the guardrails:\n' + JSON.stringify(fixes, null, 2) + '\n\nRead the current renders at ' + SP + '/renders/' + key + '/ (newest are .png) before editing.'
  return [
    head, '', intent(key), '', guardrails(key), '',
    'Aim: at first glance the machine must read as its concept, not as engineering. Color story, material believability, detail density where the player looks (the approach and the interaction zones), and honest signage. The renders are flat-lit EEVEE previews - judge and fix geometry, materials, color and composition; lighting is not yours to fix.',
    '',
    'Return via schema: changes (one line each), deferred (functional wishes you did NOT touch), renders_ok.',
  ].join('\n')
}

function criticPrompt(key, round) {
  return [
    'You are the merciless look-and-feel CRITIC for the BeamNG giant-props mod "' + key + '" (round ' + round + '). Default to NOT wowed.',
    '',
    'Read the five fresh renders: ' + SP + '/renders/' + key + '/' + key + '_{front,three_quarter,side,top,approach}.png',
    '', intent(key), '',
    'Judge as a player AND as an art director:',
    '- First read: from the three_quarter and approach shots, does it instantly read as its concept (a pachinko parlor machine / a heavy hydraulic sumo ring), or as grey engineering?',
    '- Color story: deliberate palette that matches the concept, or default steel?',
    '- Material honesty: does every big surface read as a real material at this scale?',
    '- Detail density: rich where the player looks (approach, interaction zones), calm elsewhere. Blank slabs and uniform repeated fields are programmer-art tells.',
    '- Signage and composition: does the machine present itself?',
    'The renders are flat-lit EEVEE previews: do NOT judge or demand lighting, glow, shadows or post effects (emissives are inert in-engine anyway - a pack law). Geometry, materials, color, composition only.',
    'Every fix you demand MUST be implementable through the PALETTE dict or the build_visual function only - never collision, behavior, functional geometry, or new texture families.',
    '',
    'wowed = true ONLY if the machine scores >= 9 against the pack bar (the CHIEF centrifuge look is the 8.5 reference) AND you would put these exact shots on the mod page. score: 1-10. first_read: one honest sentence. fixes: surgical and ordered, empty only if wowed. best_view: which shot sells it hardest.',
    'You are READ-ONLY: change no files.',
  ].join('\n')
}

const results = await pipeline(
  MODS,
  async (key) => {
    let lastFixes = []
    let verdict = null
    let allDeferred = []
    for (let round = 1; round <= 3; round++) {
      const w = await agent(workerPrompt(key, round, lastFixes), {
        label: 'worker' + round + ':' + key,
        phase: 'Look & feel rounds', schema: WORKER_SCHEMA,
      })
      if (w && w.deferred && w.deferred.length) allDeferred = allDeferred.concat(w.deferred)
      const v = await agent(criticPrompt(key, round), {
        label: 'critic' + round + ':' + key,
        phase: 'Look & feel rounds', schema: CRITIC_SCHEMA,
      })
      if (!v) { lastFixes = ['critic failed; general concept-fidelity polish pass']; continue }
      verdict = v
      log(key + ': round ' + round + ' score ' + v.score + (v.wowed ? ' - WOWED' : ' - ' + (v.fixes ? v.fixes.length : 0) + ' fixes demanded'))
      if (v.wowed) return { key: key, wowed: true, score: v.score, rounds: round, first_read: v.first_read, best_view: v.best_view, deferred: allDeferred, remaining: [] }
      lastFixes = v.fixes || []
    }
    return { key: key, wowed: false, score: verdict ? verdict.score : 0, rounds: 3, first_read: verdict ? verdict.first_read : '', best_view: verdict ? verdict.best_view : '', deferred: allDeferred, remaining: lastFixes }
  }
)

const done = results.filter(Boolean)
log('Complete: ' + done.filter(r => r.wowed).length + '/' + done.length + ' objects certified wowed')
return { mods: done }
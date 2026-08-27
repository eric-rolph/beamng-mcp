export const meta = {
  name: 'listing-copy-blitz',
  description: 'Draft beamng.com listing copy for 16 undistributed giant-props mods, each pair-reviewed by a hard-to-wow critic',
  phases: [
    { title: 'Draft', detail: 'one grounded writer per mod' },
    { title: 'Critique & revise', detail: 'critic must be utterly wowed; up to 2 revision rounds' },
  ],
}

const ROOT = 'C:/Users/ericr/beamng-mcp'
const MODS = [
  'belt_sander_trap', 'boot_of_doom', 'bouncy_castle', 'catapult_seesaw',
  'dino_egg_hatcher', 'giant_toaster', 'glass_atrium', 'junk_chute_grinder',
  'monster_flyswatter', 'pachinko_tower', 'pendulum_gauntlet',
  'spider_web_catcher', 'spin_cycle_washer', 'sumo_gyro_platform',
  'vacuum_of_doom', 'whale_geyser',
]

const WRITER_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['headline', 'fact_count', 'wrote_file'],
  properties: {
    headline: { type: 'string', description: 'your best subtitle option, verbatim' },
    fact_count: { type: 'number', description: 'distinct spec-grounded numbers in the page' },
    wrote_file: { type: 'boolean' },
  },
}

const CRITIC_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['wowed', 'score', 'fact_errors', 'fixes', 'best_line'],
  properties: {
    wowed: { type: 'boolean' },
    score: { type: 'number', description: '1-10; the exemplars are an 8; wowed needs >= 9' },
    fact_errors: { type: 'array', items: { type: 'string' } },
    fixes: { type: 'array', items: { type: 'string' }, description: 'surgical ordered revision demands; empty if wowed' },
    best_line: { type: 'string', description: 'the single strongest line on the page' },
  },
}

const EXEMPLAR_A = ROOT + '/examples/giant_props/gforce_centrifuge/authoring/listing_copy.md'
const EXEMPLAR_B = ROOT + '/examples/cannon_car_wash/repository/SUBMISSION.md'

function listingPath(key) {
  return ROOT + '/examples/giant_props/' + key + '/authoring/listing_copy.md'
}
function specPath(key) {
  return ROOT + '/examples/giant_props/' + key + '/spec.py'
}

function draftPrompt(key) {
  return [
    'You are drafting the beamng.com Repository listing copy for ONE BeamNG mod from the giant-props pack.',
    '',
    'MOD: ' + key + ' — dir ' + ROOT + '/examples/giant_props/' + key + '/',
    '',
    'REQUIRED READING (use the Read tool, absolute paths):',
    '1. ' + ROOT + '/examples/giant_props/README.md — the pack pitch table ("the bit") and the shared design rule: exaggerate the anticipation.',
    '2. ' + EXEMPLAR_A + ' — THE VOICE + STRUCTURE EXEMPLAR. Only the first section, before the "Resource update post" divider.',
    '3. ' + EXEMPLAR_B + ' — the precision exemplar: note how its Overview brags with real, checkable numbers.',
    '4. ' + specPath(key) + ' — THE SOLE SOURCE OF TRUTH. Mine: the module docstring (the design story), DISPLAY_NAME, dimension constants, trigger/tunable constants, and the LUA_BEHAVIOR chunk — read the behavior code, it is the exact runtime sequence the player experiences (phases, timings, speeds, counts).',
    '5. Optional for visual flavour: ' + ROOT + '/examples/giant_props/' + key + '/blender/create_' + key + '.py (docstrings near the top).',
    '',
    'WRITE this file (create it): ' + listingPath(key),
    '',
    'Required structure (mirror the centrifuge exemplar):',
    '# beamng.com resource listing copy — <DISPLAY_NAME>',
    '## Subtitle (pick one) — 3 numbered one-sentence options, each with at least one concrete number or vivid specific',
    '## Description — bold-opener hook paragraph, then the ride: what the player does and what the machine does, in the order the LUA_BEHAVIOR actually performs it',
    '### one or two named feature sections that fit the mod (the dial, the drum, the bridge...)',
    '### Details — 5-8 bullets of real features: sequence stages, tunables, physics facts, visual/night touches',
    '### How to use — spawn from the vehicle selector like any prop, drive a second vehicle in, ground-space needs, any drive-by control zones',
    'Close with: "Built with the shared giant-props framework. Feedback and bug reports welcome." — and, only if you can earn it, one short signature line of personality like the centrifuge\'s "Drive in. The machine is patient."',
    '',
    'VOICE: carnival barker backed by an engineer — every brag is a checkable fact. The pack design rule is "exaggerate the anticipation": the pause before the chaos is the joke; the copy should honour that rhythm.',
    '',
    'GROUNDING LAW (absolute): every number and behaviour claim must be traceable to spec.py (a constant or the LUA_BEHAVIOR chunk). Convert units for the player where helpful (m/s to km/h and mph — do the arithmetic correctly). NO invented stats, NO speculative features, NO build-internals jargon (jbeam, handoff, node counts) unless it is genuinely a player-facing brag. Unsure whether something is real? Leave it out.',
    '',
    'Hard-wrap at roughly 80 columns like the exemplar. Do not touch any other file.',
    '',
    'Return via the schema: headline = your best subtitle; fact_count = distinct spec-grounded numbers used; wrote_file = true only after the Write succeeded.',
  ].join('\n')
}

function criticPrompt(key, round) {
  return [
    'You are the merciless listing-page critic for the giant-props pack (round ' + round + ').',
    'Your bar is "utterly wowed": you would install the mod RIGHT NOW, and the page matches or beats both exemplars. Default to NOT wowed.',
    '',
    'FILE UNDER REVIEW (Read it): ' + listingPath(key),
    'If the file is missing: wowed=false, score=0, fixes=["file missing — write it per the required structure"].',
    '',
    'CALIBRATION (Read both): ' + EXEMPLAR_A + ' (voice + structure; ignore everything after the "Resource update post" divider) and ' + EXEMPLAR_B + ' (its Overview is the precision bar).',
    '',
    'FACT AUDIT (non-negotiable): open ' + specPath(key) + ' and verify EVERY number and EVERY behaviour claim in the listing against the constants or the LUA_BEHAVIOR chunk. Redo every unit conversion yourself (m/s to km/h/mph). Anything you cannot trace to the spec is a fact error.',
    '',
    'Also hunt: ride sequence described out of order vs the behavior code; build-internals jargon leaking through; missing required sections (3 subtitles / Description / feature section / Details / How to use / framework closer); flat or generic sentences a hundred other mod pages could contain; overclaiming beyond what the code does.',
    '',
    'wowed = true ONLY if: zero fact errors AND all required sections present AND the hook makes you want to install immediately AND nothing in either exemplar outclasses this page.',
    'score: 1-10. The exemplars are an 8. wowed requires >= 9.',
    'fixes: surgical, ordered, concrete — each actionable by a reviser with spec.py open. Empty only if wowed.',
    'best_line: quote the single strongest line verbatim.',
    'You are READ-ONLY: change no files.',
  ].join('\n')
}

function revisePrompt(key, fixes, factErrors) {
  return [
    'You are revising listing copy for the giant-props mod "' + key + '" after a critic review.',
    '',
    'FILE (rewrite in place with Write): ' + listingPath(key),
    '',
    'CRITIC FACT ERRORS (fix every one, verify against the spec):',
    JSON.stringify(factErrors, null, 2),
    '',
    'CRITIC FIXES (apply every one, in order):',
    JSON.stringify(fixes, null, 2),
    '',
    'Method: Read the current file. Re-read ' + specPath(key) + ' — re-verify every number you touch against its constants and the LUA_BEHAVIOR chunk, redo unit conversions yourself. Keep the voice and structure of the exemplar at ' + EXEMPLAR_A + ' (first section only). Do not lose what already works. Hard-wrap ~80 columns. Touch no other file.',
    '',
    'If the file is missing entirely, write it from scratch per the exemplar structure: title line, 3 subtitle options, Description, a named feature section, Details bullets, How to use, framework closer.',
    '',
    'Return via the schema: headline = the page\'s best subtitle; fact_count = distinct spec-grounded numbers; wrote_file = true after Write.',
  ].join('\n')
}

const results = await pipeline(
  MODS,
  key => agent(draftPrompt(key), {
    label: 'draft:' + key, phase: 'Draft', schema: WRITER_SCHEMA,
  }),
  async (draft, key) => {
    let headline = (draft && draft.headline) || ''
    let best = { score: -1, wowed: false, best_line: '' }
    let lastFixes = []
    let lastErrors = []
    for (let round = 1; round <= 3; round++) {
      if (round > 1) {
        const rev = await agent(revisePrompt(key, lastFixes, lastErrors), {
          label: 'revise' + (round - 1) + ':' + key,
          phase: 'Critique & revise', schema: WRITER_SCHEMA,
        })
        if (rev && rev.headline) headline = rev.headline
      }
      const v = await agent(criticPrompt(key, round), {
        label: 'critique' + round + ':' + key,
        phase: 'Critique & revise', schema: CRITIC_SCHEMA,
      })
      if (!v) { lastFixes = ['critic run failed; do a general accuracy + wow polish pass']; lastErrors = []; continue }
      if (v.score > best.score) best = v
      const clean = !v.fact_errors || v.fact_errors.length === 0
      if (v.wowed && clean) {
        log(key + ': WOWED at round ' + round + ' (score ' + v.score + ')')
        return { key: key, wowed: true, score: v.score, rounds: round, headline: headline, best_line: v.best_line, remaining: [] }
      }
      log(key + ': round ' + round + ' score ' + v.score + ' — ' + (v.fact_errors ? v.fact_errors.length : 0) + ' fact errors, ' + (v.fixes ? v.fixes.length : 0) + ' fixes demanded')
      lastFixes = v.fixes || []
      lastErrors = v.fact_errors || []
    }
    return { key: key, wowed: false, score: best.score, rounds: 3, headline: headline, best_line: best.best_line, remaining: lastFixes.concat(lastErrors) }
  }
)

const done = results.filter(Boolean)
const wowedCount = done.filter(r => r.wowed).length
log('Complete: ' + wowedCount + '/' + done.length + ' pages certified wowed')
return { wowed: wowedCount, total: done.length, mods: done }
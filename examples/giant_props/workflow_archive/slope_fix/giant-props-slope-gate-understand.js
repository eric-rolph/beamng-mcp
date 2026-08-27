export const meta = {
  name: 'giant-props-slope-gate-understand',
  description: 'Map the dist/release pipeline and live-test conventions before landing a sloped-terrain gate and re-cutting 19 mod releases',
  phases: [
    { title: 'Map', detail: 'parallel readers over packaging, live harness, runtime telemetry' },
  ],
}

const REPO = 'C:\\Users\\ericr\\beamng-mcp'

const READERS = [
  {
    key: 'packaging',
    prompt: `Read ${REPO}/examples/giant_props/build.py, ${REPO}/examples/giant_props/proplib/packaging.py, and ${REPO}/examples/giant_props/proplib/prop_builder.py.

I need to rebuild the dist ZIP for 19 giant_props mods (every one except boot_of_doom, which is already rebuilt). Answer PRECISELY, quoting file:line:

1. What does the 'dist' stage actually do, start to finish?
2. The lock file has "build_serial" and "member_timestamp" with scheme "monotonic-serial-days@2026-08-01-clamped-to-build-clock". Explain exactly how build_serial and member_timestamp are computed. Does rebuilding the SAME content twice produce the SAME sha256, or does the serial/timestamp bump change the hash every time? This is critical — I need to know if a rebuild is idempotent.
3. What PRECONDITIONS can make the dist stage fail or silently ship stale content? Specifically look at 'cooked_is_current' and the textures_cooked/harvest machinery. Which of these preconditions are per-mod?
4. Is there any release/versioning metadata (version numbers, changelogs, repo submission files) that a re-release is supposed to bump alongside the zip? Look for anything under each mod's authoring/ directory.
5. Does anything verify the zip against the lock at build time vs at test time?

Do NOT modify any files. Do NOT run builds. Read and report only.`,
  },
  {
    key: 'cooked',
    prompt: `In ${REPO}/examples/giant_props, determine for EACH of the 20 mod directories whether its dist stage can be rebuilt right now WITHOUT needing Blender or a BeamNG texture-cook harvest.

Read proplib/prop_builder.py's cooked_is_current (and anything it calls), then inspect each mod directory's textures/, textures_cooked/, and any *.harvest.json manifests on disk.

Report a table: mod key | has textures_cooked | has harvest manifest | would cooked_is_current pass | any blocker.

Also state clearly which mods (if any) would FAIL or degrade if I run 'python examples/giant_props/build.py <key> dist' right now. Quote the code paths that decide this.

Do NOT modify files. Do NOT run the build. Use file inspection and reading only (you may run read-only shell like ls/cat/python -c to inspect files, but never a build or the game).`,
  },
  {
    key: 'harness',
    prompt: `Read ${REPO}/tests/live_support.py in full, plus ${REPO}/tests/test_giant_props_live.py and ${REPO}/tests/test_giant_props_functional_live.py.

I am writing a NEW opt-in live test that boots BeamNG on a TERRAIN map (utah), spawns a giant-prop vehicle on flat / sloped / yawed spots, and asserts that runtime-created TSStatic parts stay glued to the vehicle cage nodes they belong to.

Report PRECISELY, quoting file:line:
1. Every safety primitive I must use and in what order (isolated_profile_lock, reserve_loopback_ports, require_confined_profile_target, claim_owned_beamng_process, cleanup_owned_beamng_session, cleanup_exact_live_artifacts, BeamNGLogCursor). What does each guarantee, and what breaks if omitted?
2. The exact pytest marker and env-var skip pattern used to gate live tests. Where is the marker registered (pyproject/pytest.ini)?
3. The exact scenario setup + teardown sequence used by test_giant_props_live.py, including the watchdog timer, deterministic settings, pause/step discipline, and how it cleans up the installed zip and scenario directory.
4. How the tests assert "no namespaced errors" from the runtime log, and how the start marker works.
5. Anything in these files that assumes a FLAT map (smallgrid) that I would need to change for a terrain map — e.g. surface_z raycasts, cling, spawn positions.
6. Conventions I must follow so the new test does not violate the repo rule "never run two live test files concurrently against one profile".

Do NOT modify files. Do NOT run anything live.`,
  },
  {
    key: 'telemetry',
    prompt: `Read the generated runtime template in ${REPO}/examples/giant_props/proplib/lua_kit.py, especially getSystemState, emitEvent/emitError, and the M.* export table at the end.

I am writing a live test that must assert runtime PART PLACEMENT is correct on sloped terrain. Report:
1. Exactly what getSystemState returns today (every field). Quote it.
2. Is there any existing way, from GE Lua, to ask the runtime where it thinks its parts are (state.origin, state.modelRotation, part world positions)? If not, what is the MINIMAL, lowest-risk addition to getSystemState that would expose enough for a test to verify placement — without changing runtime behaviour?
3. List every M.* export and note which are test-facing.
4. How does the runtime log structured events (log tag, JSON shape, severity letters)? What would an error look like if propFrame returned nil?
5. Read propFrame, nodeWorldPosition, baselineBasis and basisQuat as they exist NOW in that file. Sanity-check the Lua for correctness bugs: nil handling, vec3 in-place mutation hazards (BeamNG vec3 :normalize() mutates), operator support, LuaJIT upvalue/local limits, and whether any function is called before it is defined (lexical binding trap). Report concrete findings with line numbers.

Do NOT modify files.`,
  },
  {
    key: 'props-risk',
    prompt: `In ${REPO}/examples/giant_props, I just changed the SHARED runtime generator (proplib/lua_kit.py) so that every prop's placement frame is derived from its four jbeam refNodes' live node positions instead of vehicle:getPosition()/getRotation().

For each of the 20 mods, assess the RISK that this change alters behaviour in a way a flat-ground test would not catch. For each mod report:
- the refNodes used (read the generated mod/lua/ge/extensions/*/runtime.lua FRAME_NODES table, and the mod's blender/create_*.py cage builder)
- whether the refNodes are all FIXED nodes or free/floating ones (check the emitted jbeam node options in mod/vehicles/*/*.jbeam)
- the maximum distance from the ref node to any PART_SPECS pivot, TRIGGER_SPECS position, or EFFECT_SPECS position (this is the lever arm — bigger means more exposure)
- whether the prop has MOVING cage nodes near the refNodes that could make the derived basis jitter frame to frame

Rank the mods by risk. Flag any mod whose refNodes are NOT rigidly fixed, since a deforming base would make the derived frame wobble — that is the main regression risk of this change.

Do NOT modify files. Read-only inspection and small read-only python/shell for measuring distances is fine.`,
  },
]

phase('Map')

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['summary', 'findings'],
  properties: {
    summary: { type: 'string', description: 'Tight prose answer to the questions asked' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['claim', 'evidence'],
        properties: {
          claim: { type: 'string' },
          evidence: { type: 'string', description: 'file:line and a quoted snippet' },
          risk: { type: 'string', description: 'none | low | medium | high' },
        },
      },
    },
    blockers: {
      type: 'array',
      items: { type: 'string' },
      description: 'Things that would stop or corrupt the work if not handled',
    },
  },
}

const results = await parallel(
  READERS.map((r) => () =>
    agent(r.prompt, { label: `map:${r.key}`, phase: 'Map', schema: SCHEMA }).then((v) => ({
      key: r.key,
      ...v,
    })),
  ),
)

return results.filter(Boolean)

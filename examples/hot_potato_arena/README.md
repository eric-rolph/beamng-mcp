# Hot Potato: The Gateway Skillet

A scenario map for the Hot Potato mod on stock Gridmap V2: the Arch stands in
a colossal cast-iron skillet — a banked pan wall with a rounded crest at the
runtime's own 91.4 m arena line, two pour spouts, three butter pools (ICE),
a salt ring (SAND), three cycling spatter geysers, a one-way skillet handle
with two tangential ramps, four masher and four grinder pillars, and a pantry
of sixteen breakable boxes and barrels. Design blueprint, verified-facts
ledger and the full round ledger: [DESIGN.md](DESIGN.md).

The arena is a scenario mod that REQUIRES the Hot Potato mod
(`examples/giant_props/hot_potato/`). It ships nothing under `vehicles/` or
`lua/`; its only top-level root is `levels/`.

## Layout

~~~text
blender/create_arena.py        deterministic Blender 4.5.4 generator: 13 DAEs, materials json,
                               handoff, hashes manifest; asserts A1-A18 run on every build
textures/                      generate_arena_textures.py + the six staged families (18 PNGs)
authoring/                     handoff (statics, obstacles, shape hashes), layout (cars, stacks,
                               barrels, geyser sites), hashes manifests per round, two renders
sync_scenario_outputs.py       handoff + layout -> prefab JSONL, scenario JSON, generated Lua
                               block, thumbnail (uuid5 ids, LF, strict JSON)
build_distribution.py          computed member allowlist, ZIP_STORED, fixed epoch, lock json
mod/                           the exact 36-file ZIP root (levels/ only)
dist/                          hot_potato_arena_ericrolph.zip + ericrolph_hot_potato_arena.lock.json
~~~

## Build

~~~powershell
# Geometry (only when a shape changes; --export keeps frozen DAEs byte-identical):
& $blender454 --factory-startup --background --python .\examples\hot_potato_arena\blender\create_arena.py -- --round <label>
.\.venv\Scripts\python.exe .\examples\hot_potato_arena\textures\generate_arena_textures.py
# Scenario package (every re-cut):
.\.venv\Scripts\python.exe .\examples\hot_potato_arena\sync_scenario_outputs.py
.\.venv\Scripts\python.exe -m examples.hot_potato_arena.build_distribution --overwrite
# Gates (static + lupa + clearance; the lupa suite skips silently without lupa,
# the clearance suite skips without a BeamNG install):
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_hot_potato_arena_package.py .\tests\test_hot_potato_arena_logic.py .\tests\test_hot_potato_arena_site_clearance.py
# Live smoke, sentinel profile ONLY (env vars per AGENTS.md; screenshots to HOT_POTATO_ARENA_SHOT_DIR):
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_hot_potato_arena_live.py -m beamng_live
~~~

The dist is a rebuild of `mod/`, never patched by hand. Its lock records the
sha256 of the Hot Potato dist zip it was cut against (`depends_on`); if `examples/giant_props/hot_potato/dist/hot_potato_ericrolph.zip`
moves, rebuild the arena dist so `depends_on` moves with it — the package
gate `test_checked_in_lock_matches_the_dist_archive_and_the_hot_potato_lock`
fails otherwise, and the live smoke refuses to install a zip that does not
match its lock.

## Install

Since B5 (2026-09-10) the arena lives ON the level — its shapes and scenario
sit under `levels/ericrolph_hot_potato_arena/` — so THREE zips go into the
REAL profile's `mods/` root
(`%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods\`), side by side, under
their stable filenames, and the same three into the BeamMP client folder
(`C:\Users\ericr\Downloads\Resources\Client\`):

1. `examples/giant_props/hot_potato/dist/hot_potato_ericrolph.zip` — the
   runtime the arena depends on. It must be **exactly the build the arena
   lock names**; older runtimes lack the obstacle hook, the hold-mode
   scoring gate and the subject filter, and the arena's boot will log
   `obstacle_hook_missing` and count cardboard boxes as players.
2. `examples/hot_potato_arena/dist/hot_potato_arena_ericrolph.zip` — the
   arena (36 members).
3. `examples/hot_potato_arena/dist_level/hot_potato_arena_level_ericrolph.zip`
   — Giant's Hearth itself (808 members, ~1 GB).

**The level ships its textures cooked.** BeamNG cooks a level's PNGs to DDS
lazily on first load, and until each map is cooked its surface wears the
engine's "NO TEXTURE" placeholder — minutes of untextured foliage and rock on
the first load of every new build. Since 2026-09-15 the level zip carries the
engine's own cooked DDS in place of every PNG a harvest proves (the layout the
giant-props releases use: materials keep naming the `.png`, the game resolves
the cooked sibling). The harvest is `textures_cooked_level/` (taken by
`authoring/round_records/b6_cook/cook_harvest_r1.py` on the sentinel, at
`GraphicTextureQuality` "Normal"), and the full cut is
`build_level_zip … --cooked-dir examples/hot_potato_arena/textures_cooked_level`;
the lock's `cooked` table maps every shipped DDS to its source PNG and both
hashes. A PNG whose bytes moved since the harvest ships raw until the harvest
is re-taken; UI previews, the minimap and the depth map always ship as PNG.

**The installer for the level and the arena is `install_level.py`** (the Hot
Potato runtime stays with `deploy_local.py`). No flags = a report of every
installed copy against its lock; `--deploy` copies what is stale or missing,
hash-verifies the bytes on disk, refuses while the game is running, and
regenerates BeamMP's `mods.json` (its `lastwrite` is a Windows FILETIME):

~~~powershell
.\.venv\Scripts\python.exe .\examples\hot_potato_arena\install_level.py
.\.venv\Scripts\python.exe .\examples\hot_potato_arena\install_level.py --deploy
~~~

**Verify both against their locks, and against each other, before playing.**
Do not compare against numbers printed in any document — the runtime was
re-cut five times during the integration round and only the lock moved each
time. This check reads the locks themselves, so it stays correct:

~~~powershell
.\.venv\Scripts\python.exe - @'
import hashlib, json, pathlib
root = pathlib.Path('.')
arena_d = root/'examples/hot_potato_arena/dist'
hp_d    = root/'examples/giant_props/hot_potato/dist'
arena_l = json.loads((arena_d/'ericrolph_hot_potato_arena.lock.json').read_text())
hp_l    = json.loads((hp_d/'ericrolph_hot_potato.lock.json').read_text())
for lock, zp in ((arena_l, arena_d/'hot_potato_arena_ericrolph.zip'),
                 (hp_l,    hp_d/'hot_potato_ericrolph.zip')):
    got = hashlib.sha256(zp.read_bytes()).hexdigest()
    ok  = got == lock['sha256'] and zp.stat().st_size == lock['size']
    print(('OK  ' if ok else 'BAD '), zp.name, got[:16], zp.stat().st_size)
chain = (arena_l['depends_on']['sha256'] == hp_l['sha256']
         and arena_l['depends_on']['build_serial'] == hp_l['build_serial'])
print(('OK   chain' if chain else 'BAD  chain'), '-> Hot Potato serial', hp_l['build_serial'])
'@
~~~

All three lines must read `OK`. If the chain line reads `BAD`, the arena was
cut against a different runtime build than the one on disk: re-cut it rather
than playing the mismatch —

~~~powershell
.\.venv\Scripts\python.exe .\examples\hot_potato_arena\sync_scenario_outputs.py
.\.venv\Scripts\python.exe -m examples.hot_potato_arena.build_distribution --overwrite
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_hot_potato_arena_package.py
~~~

— then re-run the check. **As last run all three lines read `OK`**, with the
chain at Hot Potato **serial 55** and the arena archive at `cfafe4fc…`,
8,146,038 bytes; the arena static suites are 81 passed. During development
this tree twice sat red for a few minutes between a runtime re-cut and the
arena's — if you catch it in that state the check tells you so, and the
re-cut above fixes it.

**Neither the arena nor the level is
in `examples/giant_props/deploy_local.py`'s release table**: that tool
discovers releases as `examples/giant_props/*/spec.py` directories plus the
Cannon Car Wash submission, so it reports and deploys the Hot Potato zip but
neither reports, deploys, nor shadow-scans the arena or the level. Run it for
the runtime (`--deploy` refuses while the game is running), then
`install_level.py --deploy` for the other two. Never put any of the zips in a
subfolder of `mods/` (BeamNG mounts every zip below it recursively; a stale
copy shadows the release).

## Play

Main menu → **Scenarios** → **Giant's Hearth** (it sorts under G) → **Hot
Potato: The Gateway Skillet**; freeroam on the level has four spawns (South
apron, Trailhead, Kettle Lake shore, Firewood Gap). Since B5 the scenario is
listed under the level, not under Gridmap V2. You spawn in an ETK 800 on the
r 40 ring facing the pad with five
AI cars; drive onto the medallion to pick up the potato and pass it before
it pops. Everything else is the Hot Potato mod as shipped (game modes, HUD
tuner, fireworks).

What the arena sets on the runtime at boot, in order, and hands back when
you leave (mission end, the pause menu's Exit scenario, or the next visit
after a crash) — only if you did not change the key yourself mid-mission
through the HUD tuner:

| Tuner key | Arena value | Why |
| --- | --- | --- |
| `arena_radius_m` | 91.4 | the pan crest is built at this radius; the decay valve steps it to 75 then 60 in a stalled round and restores it at every round exit |
| `arena_enabled` | true | the circle, AI conscription and return steering |
| `ai_enabled` | true | the five AI cars join the game |
| `arena_magnet_enabled` | true | the tractor beam hauls crest-overs back over the lip |
| `oob_burn_multiplier` | 3.0 | **the potato burns three times faster while the carrier is outside the ring.** The runtime ships this OFF (1.0); the arena switches it on, because the magnet alone does not bring a powered car back off the outer apron |

Each write is a Hot Potato toast and a settings save (**five** at boot, a
restart costs the reload boot plus whatever still holds the arena's value).
`arena_magnet_g` is left at the runtime's default 1.2 g. **It is not an
escalation lever against a sustained orbit** — that was the design's
assumption and the live gates disproved it: at 2.0 g a powered car on the
outer apron re-entered in 2 of 6 attempts, exactly as at 1.2 g. What closes
that gap is the out-of-bounds fuse in the table above. In a BeamMP session
the arena writes nothing.

**One rule worth knowing before you play.** Carrying the potato outside the
91.4 m ring makes its fuse burn **3× faster** until you are back inside, with
a HUD flag and a message each time you cross. It is deliberately visible
rather than a hidden tax, and it is the reason you cannot win by driving
circles on the outer apron — an orbiting carrier detonates instead. Measured
over 478 live samples: exactly 3.0× outside and 1.0× inside, without a single
exception, parked and driven.

## Known rough edges

- **Vehicle choice.** The Wentward bus (wheelbase 7.45 m) is supported in the
  bowl, the pour spouts and the under-arch lane, but not on the pillar rings
  or the Handle. **A D-Series pickup will roll on the banked wall if it is
  dragged sideways up there** — measured at r 82.5, 17.8 m/s. Both are the
  same cause: the magnet's tip budget uses one generic half-track / CG-height
  ratio for every car, so a taller vehicle tips on a steeper surface. A car-
  sized vehicle on the bank is fine.
- **Striping from high up only.** From a free camera 150 m or more above the
  arena the outer slope shows faint horizontal white stripes. It is a
  rendering artifact, it does not affect driving, and **from 100 m and below —
  which includes every camera you actually play from — it is clean.** An
  attempted fix removed the boot-to-boot luck of the draw without removing the
  stripes; it is left as a known cosmetic issue rather than chased further.
- **The AI is not perfect.** Roughly once per round a car may glance a spout
  jamb at speed or scuff a pepper grinder at walking pace, then carry on. One
  test run had none at all.
- **The steam is prettier than it is dangerous** — a spout curtain costs about
  a tenth of a percent of your speed and a 1.5 m hop.
- **The plaza is open.** Once the sixteen boxes and barrels are scattered they
  do not come back until the scenario is reloaded.

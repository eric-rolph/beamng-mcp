# beamng.com resource listing — Charlie's Football Field Goal

Submission-ready copy. Every number below is read from `spec.py`,
`blender/create_football_goal_post.py` or the build output — not
remembered. Re-check them if the geometry or the tunables move.

## Resource title

    Charlie's Football Field Goal

## Tag line (the one-liner under the title)

> A regulation gooseneck goal post, built to the installation drawings —
> 45 ft of painted steel, cloth flags on real wind, and it knows when you
> put a car through the uprights.

Alternates, if a shorter one is wanted:

1. Regulation 18' 6" uprights, a padded gooseneck, and a scoring zone that
   actually calls it.
2. Every bolt in the manufacturer's parts list, at 1:1 scale — then a
   trigger that shouts when your car clears the crossbar.
3. Built from the plate-mount install drawings, down to the grommets in
   the flags.

## Category

Vehicles → Props (`"Type": "Prop"` in `info.json`; it spawns from the
vehicle selector alongside the stock barrels and cones).

## Version

    1.0.0

First public release. The build serial in `dist/*.serial.json` is an
internal counter, not the published version — do not paste it here.

## Tags

    goal post, football, field goal, prop, stadium, american football,
    scenery, flags

## Upload checklist

- [x] ZIP contains only `lua/` and `vehicles/` at the root, no stray files
- [x] `vehicles/<id>/default.jpg` + `standard.jpg` present at 500x281
- [x] `info.json` — Name, Author, `"Type": "Prop"`
- [x] No absolute local paths anywhere in the shipped files
- [x] No real brand, logo or trade dress anywhere on the prop
- [x] Nothing re-used from the base game or from another mod
- [ ] **Live play-test** — spawn it, put a car through the uprights, watch
      the flags settle. Not yet done; do this before uploading.
- [ ] Optional: `build.py football_goal_post harvest` after that session
      bakes the 43 source PNGs to cooked DDS, trading a bigger download
      for a zero-cook first load.

## Short description / subtitle (repo "tag line" field, ~140 chars)

> Regulation gooseneck field goal post — 45 ft, padded base, soft-body
> flags on BeamNG's real wind, and a scoring trigger that calls your kick.

## Description

**CHARLIE'S FOOTBALL FIELD GOAL** — a regulation gooseneck football goal
post, modelled from a plate-mount manufacturer's installation drawing
rather than from memory, and dropped into BeamNG as a spawnable prop.

Everything is at true scale. The crossbar's top edge is **10 ft** off the
turf, the uprights stand **18 ft 6 in** apart on the inside and run
**35 ft** above the bar — **45 ft** to the flag tips. The pedestal is
offset **8 ft** behind the goal plane on a single continuous swan-neck
sweep, so there is nothing between the posts to hit. The tube sizes are
the real ones too: 5 in crossbar, 4 in uprights, 6-5/8 in pedestal.

### It calls your kick

Get a car above the crossbar and between the uprights — the only way into
that volume is airborne — and the post calls it:

> **IT'S GOOD! Right through the uprights!**

Six-second cooldown, so a bouncing landing does not spam it. There is
nothing to arm, configure or wire up; spawn the post and start launching.

### The flags are real cloth on real wind

The two directional flags at the upright tips are **soft-body cloth**, not
animated texture and not rigid geometry — a woven node grid with drag on
its triangles, built the way the stock UTV's flags are. They stream on
BeamNG's **physics ground wind**, the same field the game feeds to every
vehicle's aero.

No stock level ships a wind value (it starts at exactly zero), so on spawn
the post sets a light **4 m/s (≈9 mph) breeze from 205°** — but only if the
level's wind is still exactly zero, so it never overrides a wind you set
yourself in the Winds app. Set `breeze_mps = 0` in the spec to turn that
off and let the flags hang dead.

### Built from the drawings

The parts you would find on the real thing are all here, at their real
sizes and in their real places:

- **Welded fixed-end stub joint** at the crossbar — the upright slips over
  a galvanised stub welded to the bar's crown, leaving the crescent of
  bare stub and the saddle fillet weld that a real goal post has and a
  tube-through-tube model never does.
- **Hex washer head serrated flange bolts** throughout, seated on flanges
  machined to the curve of the pipe they land on.
- **Padded pedestal** to the 6 ft the rulebook asks for: a heat-sealed
  vinyl shell over foam that swells between its straps and pinches in at
  each one, closed by four **side-release buckles** on woven webbing.
- **Directional flags** on real hardware — a welded pad, a flat tab bored
  through, and a spring snap hook hanging in the hole, threaded through a
  brass grommet. The doubled hem and the grommet are part of the CLOTH,
  not scenery bolted to the tube, so they fold and swing with the flag.
- **Die-struck end caps** carrying the builder's mark, and a **data plate**
  curved onto the gooseneck with model, serial and patent lines.
- **Turf build-up** at the base: concrete footing, 9-5/8 in of subgrade,
  sod mat and mown grass, exactly the section the drawing's "Natural Grass
  Application" detail specifies. The mounting hardware is built and then
  buried, the way it is installed.

### Specs

| | |
|---|---|
| Height to crossbar (top) | 3.048 m / 10 ft |
| Inside width | 5.639 m / 18 ft 6 in |
| Overall height | 13.72 m / 45 ft |
| Gooseneck offset | 2.438 m / 8 ft |
| Mass | 7,980 kg |
| Value | $14,000 |
| Physics | 157 nodes, 476 beams |

## Installation

1. Download the ZIP.
2. Drop it in `Documents/BeamNG.drive/<version>/mods/` (or use the in-game
   repository once it is listed).
3. Spawn it from the vehicle selector like any other prop — search
   "Charlie".

No level edits, no extra dependencies, no cache clearing.

## Compatibility

Built and tested on **BeamNG.drive 0.39**. Prop mods of this shape have
been stable across recent versions, but 0.39 is what it is verified on.

## Credits and licence

Modelled and textured from scratch — every mesh is generated, every
texture is procedural, nothing is ripped or re-used from the game or from
anyone else's mod. The manufacturer name on the plate and the end caps
(**CHARLIE GOAL SYSTEMS INC. / CGS**) is fictional and deliberately so; no
real brand, logo or trade dress is reproduced anywhere on the prop.

Dimensions follow published NFHS/NCAA field-goal geometry and a
plate-mount installation drawing used as a reference for the hardware
layout. Please do not re-upload; link here instead.

## Assets in this folder

| File | Use |
|---|---|
| `ericrolph_football_goal_post_thumbnail.jpg` | 500x281 — shipped in the ZIP as the vehicle-selector card |
| `resource_icon_96.png` | 96x96 — the repo resource icon |
| `resource_icon_preview_384.png` | 4x preview of the icon, for checking it |
| `listing/01_goal.jpg` … `09_plate.jpg` | 1280x720 gallery, in upload order |

`stage_upload.py` copies all of the above plus the dist ZIP into
`dist/upload/` and warns about any asset older than the ZIP.

Gallery running order and what each shot is for:

1. **01_goal** — establishing: the whole H, flag tips to turf.
2. **02_crossbar** — the hero angle, from the field looking up.
3. **03_base** — padded pedestal, buckles, turf build-up.
4. **04_end_cap** — the die-struck CGS mark on the crossbar cap.
5. **05_flag** — a whole flag, face-on, with its wave and twist.
6. **06_flag_mount** — the whole mount: pad, bored tab, hook, grommet, hem.
7. **07_joint** — the welded stub joint and its bolts.
8. **08_buckle** — a side-release buckle on its woven webbing.
9. **09_plate** — the builder's data plate on the gooseneck.

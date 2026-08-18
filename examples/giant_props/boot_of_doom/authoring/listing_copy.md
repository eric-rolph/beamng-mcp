# beamng.com resource listing — Charlie's Boot of Doom

Submission-ready copy. Numbers below are read from `spec.py` /
`runtime.lua`, not remembered — re-check them if the tunables move.

## Resource title

    Charlie's Boot of Doom

## Tag line (the one-liner under the title)

> A 7.9 m leather work boot that notices your car, draws back, and punts it
> downrange. Field-goal style, with a dial for how far.

Alternates, if a shorter one is wanted:

1. Drive over the X. About 1.2 seconds later you are airborne.
2. Giant working punt machine — drive-through trigger, 62-degree swing,
   1x to 4x kick power on a mid-century console.
3. It has never once ruled itself wide. Video review is on you.

## Category

Vehicles → Props (`"Type": "Prop"` in `info.json`; it spawns from the
vehicle selector like the barrels and the wrecking ball).

## Description

**CHARLIE'S BOOT OF DOOM** — a 7.9 m worn-leather work boot on a steel
ground hinge, parked behind a painted kick pad, waiting for something to
cross.

Drive over the X. You do not have to stop — any crossing wakes it. "The
boot notices you." It quivers on its hinge for 0.3 seconds, and then —
"The boot draws back..." — a 0.7-second wind-up, shuffling 0.8 m rearward
and cocking its toe up 8 degrees, trembling the whole way. It holds the
draw for 0.15 seconds. That pause is the whole joke. Then the swing: 8 to
62 degrees in a quarter of a second, lunging forward so the toe actually
arrives where your car is, and everything still in the strike lane gets
punted at a randomized 27–42 m/s — 97 to 151 km/h at stock power, before
the console gets involved.

Clear the lane in time and "The boot kicks nothing but air." Sit tight
instead: follow-through, return and cooldown take 3.5 seconds, and if you
are still on the pad after that — "The boot notices you. Again."

### The KICK CONTROL console

A walnut-and-cream mid-century console stands behind the boot, and every
cap on it is clickable:

- **POWER, 1X to 4X** — ten steps on a lit bar gauge. At 1X a good kick is
  about sixty yards. At 4X the same kick leaves at up to 168 m/s (over 600
  km/h) and the landing is somebody else's problem.
- **LAUNCH ANGLE, 0 to 90** — ten 10-degree positions on a real swept-arc
  gauge with a moving needle. 0 is a flat skip down the runway, 50 is the
  stock punt, 90 fires straight up and gives it back to you.

The back of the console carries the builder's plate: CHARLIE CO., KINETIC
FOOTWEAR DIV., MODEL BD-1. The ratings on it are derived, not decorative —
the boot is 8.6 tonnes, a kick is 6.86 MJ over a 0.24 s stroke, and the
plate carries the line rating that implies: 2200 H.P. at 2300 V, 3-phase,
60 cycle.

### The strike lane

The kick is not a tap on the pad. At punt time the boot sweeps a
5.4 × 9.4 m lane, 4.4 m tall, covering the pad and the escape route
downrange, so half-committed getaways get collected mid-flight attempt.
Every vehicle in the lane is kicked by the same swing, and each rolls its
own launch speed. Park off the centreline and the kick shanks — sloppy
placement flies wide.

### Details

- Full kick sequence: 0.3 s alert quiver, 0.7 s draw-back, 0.15 s hold,
  then an 8-to-62-degree swing over 0.24 s with the launch firing at the
  moment of visual contact.
- Punt power rolled fresh every kick, then multiplied by the console.
- Drive-through arming: a 4.6 × 5.2 m trigger over the pad. Crossing
  counts; parking on the X is optional and inadvisable.
- One swing, everyone flies: the strike lane is swept at punt time, and
  every occupant gets its own randomized launch speed.
- The boot never dips below its resting plane — it cocks up, then kicks
  out and up through the lane, so the sole stays out of the dirt.
- Honest referee: a whiff gets "The boot kicks nothing but air," and the
  dust only blows when leather actually connects.
- 1.0-second cooldown, then instant re-arm if the pad is still occupied:
  "The boot notices you. Again."
- Sculpted worn-leather boot with a lugged sole and a steel heel hinge, and
  a red X on a painted kick pad that tapers into the road on all four
  sides, so it reads as a poured hump instead of a dropped slab.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle across the X. Give it room: at stock power the punt wants 60–120
yards (55–110 m) of clear landing ground downrange of the pad, and a lot
more than that with the power dial up. Flat open spaces — Gridmap and the
airfields work well.

Built with the shared giant-props framework, same shop as Charlie's LAHC
Centrifuge. Feedback and bug reports welcome.

Cross the pad. You have 1.2 seconds.

---

# Upload

Everything the resource form asks for is assembled in one folder by

```
python examples/giant_props/boot_of_doom/authoring/make_submission.py
```

which writes `dist/repo_submission/` — the ZIP, `icon_96.png`,
`screenshot_01..05.jpg` in gallery order, the text fields, and an
`UPLOAD.txt` that walks the form field by field.

**The description that gets pasted is `authoring/repo/description.bbcode`,
not this file.** beamng.com's Resource Manager is XenForo and its editor
takes BBCode; markdown headings paste through as literal `###`. This
document stays the human-readable working copy — the authored short
fields live beside it in `authoring/repo/` (`title.txt`, `tagline.txt`,
`fields.txt`), and the assembler copies them through verbatim.

| Repository field | What to upload | Authored in |
| --- | --- | --- |
| Resource file | `boot_of_doom_ericrolph.zip` (55 MB, pre-cooked) | `dist/` |
| Resource icon | `icon_96.png` | `authoring/resource_icon_96.png` |
| Screenshots | `screenshot_01..05.jpg` | `authoring/listing/` |
| Title / tag line / description | text files | `authoring/repo/` |

In-game, the vehicle selector card comes from the mod itself —
`authoring/<mod_id>_thumbnail.jpg` is copied to `default.jpg` and
`standard.jpg` at build time, and the selector name comes from
`info.json` (`spec.DISPLAY_NAME`). Nothing to upload for those.

Regenerating the art:

```
# selector card + gallery + icon source art (all deterministic)
blender --factory-startup --background \
    --python examples/giant_props/boot_of_doom/blender/create_boot_of_doom.py
# badge composite, reads authoring/icon_source_boot.png
python examples/giant_props/boot_of_doom/authoring/make_resource_icon.py
```

**Textures are pre-cooked.** All 24 maps ship as DDS harvested from a game
session that actually loaded serial 19, certified against today's source
PNGs in `textures_cooked/ericrolph_boot_of_doom.harvest.json`. Players pay
no cook on first load; the trade is download size — 36 MB of the 55 MB ZIP
is cooked texture, and another 18 MB is the boot's hero-mesh DAE. To
re-harvest after any texture change:

```
# play the mod once so the game cooks the new PNGs, then:
GIANT_PROPS_PROFILE=%LOCALAPPDATA%\BeamNG\BeamNG.drive\current \
    python examples/giant_props/build.py boot_of_doom harvest
python examples/giant_props/build.py boot_of_doom all
```

**Still owed before upload:** the pack's live play-test rule (per-mod
in-game verification of the kick itself). In-game action screenshots from
that session would also beat the studio renders for the gallery — the
renders are honest about the geometry, but nobody buys a punt machine
without seeing a car leave.

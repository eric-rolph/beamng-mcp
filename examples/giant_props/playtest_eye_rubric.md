# Playtest-eye aesthetic rubric

The prompt contract for a vision-language reviewer judging a mod from
`authoring/playtest_eye/` output (`contact_sheet.jpg` for the whole-set read,
individual frames for anything that needs a closer look, `manifest.json` for
camera poses). The frames are normal-exposure in-game screenshots — the
reviewer is seeing exactly what a player sees, which Blender renders and
fixed-exposure renderViews structurally cannot show.

Judge the image as a whole first, then by dimension. Every defect finding must
name its frame(s) and region, guess the pipeline stage (authoring / texture /
material / cook / skinning / lighting), and propose one measurement or one
camera that would confirm it — a finding that cannot be photographed or
measured goes to a measure-first queue, not into a work order.

## Dimensions

1. **First read.** Two seconds per frame: what does the machine read AS?
   If the answer is not the design brief's object, that is the lead finding
   (the catapult read as a ski jump; nothing else about it mattered until
   that did).
2. **Silhouette and massing.** At orbit distance, does the outline carry the
   design? Accidental tangencies, unreadable clutter, features that vanish
   into the mass.
3. **Scale legibility.** Against the parked vehicle, does it read at its true
   size? Wrong-frequency detail (texture grain, panel counts, fastener
   spacing) shrinks giants — the pack's metric-true tiling laws exist for
   this.
4. **Material truth in game light.** Does each surface read as its material
   at normal exposure — and consistently across azimuths as the specular
   response moves? Plastic-looking rubber usually means normal-map slope
   collapse; a value inversion between neighbouring materials (cast iron
   brighter than enamel) is a palette bug, and both have existing
   measurement patterns in the test suite.
5. **Value and color composition.** Is there a value hierarchy that sends the
   eye to the interaction affordance (the deck, the slot, the X)? Name any
   accidental saturation spikes — after checking the manifest that they are
   not annotation.
6. **Feature audibility.** Are the authored focal features (signage, legend
   panels, seams, wear states, lamps) visible AND lit in these player-
   plausible views? A feature no frame can show is indistinguishable from a
   feature that is not there — if the camera set itself is the gap, the
   finding is a new named camera, not a modelling change.
7. **Grounding.** Contact shadow, base-to-terrain transition, no floating or
   sinking edges, no z-fighting shimmer at grazing angles.

## Verdict format

- Three genuine strengths (what must not be lost in fixes).
- Ranked defects: `rank. [frames] region — observation — suspected stage —
  confirming measurement/camera`.
- A wow score out of 10 **for the in-game look specifically**, with the one
  change most likely to raise it.

Two standing cautions from the ledgers: reviewers disagree about different
quantities more often than they disagree about facts — reconcile a conflict
with the previous round's measured claims before acting on it; and never
prescribe a knob value with a target ("0.85 gives −0.25 m") without asking
for the measurement that connects them.

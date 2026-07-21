# Cannon Car Wash Repository submission

This directory contains operator-facing material for the BeamNG Repository form. Nothing here is
packed into `cannon_car_wash_ericrolph.zip`.

## Overview

Drive a Gavril D-Series through a detailed automated car wash on Gridmap V2. Entering the wash
starts five animated brushes, six inward-facing water jets, and a layered mist/steam/dust dryer.
The entry-water arch restores transient vehicle damage to its fresh-spawn state. Once the truck is fully
contained in the exit bay, the system holds it for a 3-2-1-GO countdown and launches it at
360 km/h toward a concrete crash target. The rigid 15,125 kg structure is also available in the
vehicle selector under Props, where the same wash-and-launch cycle works with arbitrary vehicles
in free roam.

## Installation and use

1. Subscribe through the Repository, or place the downloaded ZIP in the BeamNG user folder's
   `mods` directory.
2. Open Scenarios and select **Cannon Car Wash** to run the complete wash-and-launch trap.
3. Open the vehicle selector's Props category to place the functional car wash on a measured flat
   surface. Drive any standard vehicle fully inside to run its rollers, water, dryer, repair,
   countdown, and
   launch cycle.

## v1.6.0 notes

- Replaced the exit water bank with six primary waterfall-mist jets, two exhaust-steam accents,
  and two ambient-dust accents for a layered blow-dryer effect while retaining six water jets at
  the entry arch.
- Added a dedicated entry-water repair trigger. It preserves and briefly freezes the controller,
  uses BeamNG's full `RESET_PHYSICS` path plus flex-mesh restoration, restores the exact pre-reset
  pose, consumes both intentional reset callbacks, verifies damage, parts, beams, and tires, then
  acknowledges restoration of the prior freeze state before completing once per wash pass.
- Added scenario and free-roam regressions for all three trigger zones, exact stock emitter
  bindings, arbitrary-vehicle repair, reset recursion prevention, post-repair integrity, and the
  complete countdown/launch path.

## v1.5.0 notes

- Fixed Vehicle Selector placement so the prop uses eight Blender-derived collision-envelope
  corners for BeamNG safe placement and lands flush instead of inheriting a vehicle's reference
  height.
- Corrected all twelve sprinkler transforms so local +Z faces inward in both the scenario prefab
  and the free-roam runtime, including after the prop is rotated.
- Replaced the countdown's repeated velocity/brake override with an acknowledged controller
  freeze, one uniform main-cluster stop, an acknowledged release, and a two-simulation-frame grace
  before launch. Live tests record zero pre-GO damage and zero pre-GO damaged parts.
- Added live regressions for elevated safe placement, eight engine collision-mode-3 nodes,
  90-degree mister orientation, controller freeze/release state, part damage, launch speed, and
  clean Lua logs.

## v1.4.0 notes

- Added a selector-owned runtime so placed Props are functional outside the scenario and work with
  arbitrary real vehicles.
- Added automatic animated rollers, twelve spray misters, and a full-containment
  `3... 2... 1... GO!` launch at 100 m/s to every registered selector instance.
- Added an exact Blender-derived Z=0 ground datum and expanded the rigid cage to 79 fixed nodes,
  329 beams, 144 collision triangles, and 15,125 kg for flush, stable placement.
- Kept the Gridmap V2 extension scenario-owned while the selector uses a vehicle bootstrap and an
  on-demand GE manager. Both paths clean up with their owner; there is no global `modScript.lua`.
- Moved the shared animated asset into BeamNG's common `art` root so the selector prop renders on
  maps beyond Gridmap V2, while keeping a deterministic 16-file upload under only `art`, `levels`,
  `lua`, and `vehicles`.

## Manual upload checklist

- Upload the stable `cannon_car_wash_ericrolph.zip` artifact; do not rename it on future updates.
- Use the dedicated 96x96 `repository/icon.jpg` as the resource icon.
- Upload both images under `repository/images` through the Repository image uploader.
- Paste the overview above; do not add a README to the ZIP.
- Confirm the submitting BeamNG account and author display name are correct.
- Confirm the archive was tested alone from `USER_FOLDER/mods` on BeamNG.drive 0.38.6.
- Confirm the uploaded file matches the final byte size and SHA-256 locked in
  `repository/submission.json` after the exact prebuilt-ZIP live gate passes.
- Review `PROVENANCE.md`, the automated distribution gates, and the latest live telemetry.
- Check the in-game console for new warnings or errors before submitting for moderator review.

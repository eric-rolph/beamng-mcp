# Cannon Car Wash Repository submission

This directory contains operator-facing material for the BeamNG Repository form. Nothing here is
packed into `cannon_car_wash_ericrolph.zip`.

## Overview

Drive a Gavril D-Series through a detailed automated car wash on Gridmap V2. Entering the wash
starts five animated brushes, six inward-facing water jets, and a layered mist/steam/dust dryer.
The midpoint restore zone returns transient vehicle damage to its fresh-spawn state, re-centers the
renewed vehicle, aligns it upright and parallel to the tunnel, and preserves its direction of
travel. Once a repaired vehicle is fully contained in the bay, the system holds it for a
3-2-1-GO countdown and launches it at 360 km/h toward a concrete crash target. The rigid 15,125 kg structure is also available in the
vehicle selector under Props, where the same wash-and-launch cycle works with arbitrary vehicles
in free roam, including the stock Wentward city bus. Rollers and effects remain active while any
vehicle occupies the wash.

## Installation and use

1. Subscribe through the Repository, or place the downloaded ZIP in the BeamNG user folder's
   `mods` directory.
2. Open Scenarios and select **Cannon Car Wash** to run the complete wash-and-launch trap.
3. Open the vehicle selector's Props category to place the functional car wash on a measured flat
   surface. Drive a standard or large vehicle fully inside to run its rollers, water, dryer, repair,
   countdown, and
   launch cycle.

## v1.8.0 notes

- Fixed midpoint repair orientation: after the full physics renewal, the runtime uses the renewed
  live OOBB to center the vehicle without changing its longitudinal progress, aligns forward and up
  to the car-wash corridor, preserves the incoming travel sign, and permits at most two corrective
  retries. The isolated D-Series proof records 0.036987 m centerline error, 0.9997017
  corridor-direction dot, and 0.9997559 upright dot; the selector-runtime city-bus path also passes
  its pose and launch gates.
- Rebuilt the brushes as optimized alpha-tested card fans: 16 radial cards per vertical brush and
  14 for the overhead brush, with a shared colour-dilated 512 atlas and five retained animation
  channels.
- Added a complete namespaced PBR pass for exterior CMU, interior brick, wet concrete, painted blue
  corrugated panels, brush cards, and dual-layer emissive signage. The public package ships 22
  channel-validated BeamNG-cooked DDS files and no PNG authoring sources.
- Added low-cost industrial details including conduits, water piping, nozzle assemblies, drain
  grates, hazard markings, wheel guides, fixtures, junction boxes, and a correctly proportioned
  sign while consolidating repeated static geometry.
- Added seven synchronized real scene lights: five shadowless tunnel PointLights and two
  shadowless entrance/sign SpotLights. The scenario owns persistent lights; the free-roam manager
  creates and cleans up matching transform-following lights per prop.
- Reduced the visible asset to 10,714 scenario triangles across 33 primitive groups and 18
  materials; the selector is 10,666 triangles across 18 groups, with its animated runtime visual
  kept separate.
- Strengthened release validation with cooked-DDS channel checks, incremental structured Lua-log
  reads, semantic day/active visual review, and a four-cold-start final matrix covering Phase 2,
  complete Phase 4, selector-runtime/city-bus, and the exact public ZIP.

## v1.7.0 notes

- Moved the one-pass restore trigger to the physical midpoint of the wash and made completed
  repair a strict prerequisite for the launcher.
- Expanded and live-validated the full-containment launcher for the stock Wentward DT40L city bus
  while retaining `Contains` plus `Bounding box` semantics and the 360 km/h launch target.
- Made wash occupancy reference-counted: rollers and all sixteen effects remain active until the
  final vehicle exits, and one vehicle resetting no longer stops the wash for other occupants.
- Added large-vehicle containment stabilization for BeamNG OOBB-edge jitter without masking a real
  wash exit, plus live regressions for midpoint repair, two-vehicle occupancy, and the city-bus
  launch.

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
  maps beyond Gridmap V2, while keeping the historical v1.4 release to a deterministic 16-file
  upload under only `art`, `levels`, `lua`, and `vehicles`.

## Manual upload checklist

- Upload the stable `cannon_car_wash_ericrolph.zip` artifact; do not rename it on future updates.
- Use the dedicated 96x96 `repository/icon.jpg` as the resource icon.
- Upload both images under `repository/images` through the Repository image uploader.
- Paste the overview above; do not add a README to the ZIP.
- Confirm the submitting BeamNG account and author display name are correct.
- Confirm the archive was tested alone from `USER_FOLDER/mods` on BeamNG.drive 0.38.6.
- Confirm all 22 cooked DDS textures, all 18 material mappings, and all seven lights resolve with no
  namespaced warning/error in the fresh-session log.
- Confirm the uploaded file matches the final byte size and SHA-256 locked in
  `repository/submission.json` after the exact prebuilt-ZIP live gate passes.
- Review `PROVENANCE.md`, the automated distribution gates, and the latest live telemetry.
- Check the in-game console for new warnings or errors before submitting for moderator review.

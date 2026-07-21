# Cannon Car Wash

Functional Cannon Car Wash trap for the BeamNG.drive Gridmap V2 test scenario, plus a standalone
spawnable structure in the vehicle selector's **Props** category.

The selector model is rooted at `vehicles/cannon_car_wash`. Its `Standard` configuration uses a
14,875 kg cross-braced JBeam with all structure nodes fixed, fourteen heavy floor-edge foundation
nodes, 144 collision triangles, and one multi-material flexbody. The prop remains open at both ends,
does not wobble or flex, and can be placed like stock large structures. Selecting the prop does not
create the wash-cycle or cannon triggers; that scripted behavior belongs to the scenario described
below.

The packaged Gridmap V2 scenario places the car-wash asset on the flat central
test pad, spawns a default Gavril D-Series at the entrance, and creates two Blender-aligned
`BeamNGTrigger` objects. `WashActivationTrigger_Mesh` overlaps the full bay; its enter/exit events
start and stop the visual's ambient roller animation and twelve inward-facing `BNGP_sprinkler`
particle emitters. `LaunchTrigger_Mesh` uses bounding-box `Contains` mode over the exit half of the
bay. The packaged `cannon_car_wash/main` game-engine Lua extension accepts only those exact live
triggers and revalidates their live modes, requires the named Gavril D-Series to have entered the
wash-cycle volume with every effect active, and starts the launch sequence only when that truck is
fully contained. Same-frame nested trigger events are deferred until the wash is active, and any
partial effect update is rolled back to all-off. The launcher then disables AI, holds the truck at
zero velocity, displays `3... 2... 1... GO!` at one-second simulation-time intervals, and replaces
the truck's velocity with a normalized 100 m/s (360 km/h) vector along its current forward axis.

Every state transition is written to `beamng.log` as a versioned JSON record
tagged `CANNON_CAR_WASH`, including wash-cycle entry/exit, effect start/stop, verified containment,
hold, countdown, release, launch, abort, and error events. Exit/reset/mission lifecycle hooks stop
the effects, re-arm the trap, and release any held controls safely.

A stock Gridmap V2 concrete crash block spans the lane 32 m beyond the
trigger center. The Phase 4 automation approaches in Drive at 3–5 m/s, records
state/electrics/damage telemetry through the launch and impact, and rejects
missing damage, insufficient launch speed, weak deceleration, or Lua errors.

## Coordinate contract

- Coordinate system: right-handed, meters, Z-up
- Asset drive axis: local `+Y`
- Asset world origin: `[-122.011475, -170.0, 100.0]`
- Wash-cycle trigger local center/dimensions: `[0.0, 0.0, 2.2]` / `[5.8, 17.5, 4.4]`
- Wash-cycle trigger world center: `[-122.011475, -170.0, 102.2]` (`Overlaps`)
- Launch trigger local center/dimensions: `[0.0, 5.0, 2.1]` / `[5.8, 7.5, 4.6]`
- Launch trigger world center: `[-122.011475, -165.0, 102.1]` (`Contains`)
- Mister banks: local `Y=-5.6` (pre-soak) and `Y=5.65` (rinse), at `X=±2.62` and
  `Z=1.25, 2.1, 3.0`; all twelve use `BNGP_sprinkler` and point inward
- Truck spawn: `[-122.011475, -182.5, 100.747742]`, facing world `+Y`

The authoritative Blender measurements remain in
`levels/gridmap_v2/art/shapes/carwash/cannon_car_wash.geometry.json`.
The Phase 3 scripting contract is recorded in
`mod_info/cannon_car_wash/phase3_manifest.json`.
The automated impact and telemetry contract is recorded in
`mod_info/cannon_car_wash/phase4_manifest.json`.

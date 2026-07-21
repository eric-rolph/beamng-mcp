# Cannon Car Wash

Functional Cannon Car Wash trap for the BeamNG.drive Gridmap V2 test scenario, plus a standalone
spawnable structure in the vehicle selector's **Props** category.

The selector model is rooted at `vehicles/cannon_car_wash`. Its `Standard` configuration uses a
14,875 kg cross-braced JBeam with fourteen heavy fixed floor-edge nodes, 144 collision triangles,
and one multi-material flexbody. The prop remains open at both ends and can be placed like stock
large structures. Selecting the prop does not create the cannon trigger; that scripted behavior
belongs to the scenario described below.

The packaged Gridmap V2 scenario places the car-wash asset on the flat central
test pad, spawns a default Gavril D-Series at the entrance, and creates the
named `LaunchTrigger_Mesh` `BeamNGTrigger` at the Blender-authored marker.
The packaged `cannon_car_wash/main` game-engine Lua extension accepts only that
exact live trigger and the named Gavril D-Series. On entry it disables AI,
holds the truck at zero velocity, displays `3... 2... 1... GO!` at one-second
simulation-time intervals, and replaces the truck's velocity with a normalized
100 m/s (360 km/h) vector along its current forward axis.

Every state transition is written to `beamng.log` as a versioned JSON record
tagged `CANNON_CAR_WASH`, including trigger entry, hold, countdown, release,
launch, abort, and error events. Exit/reset/mission lifecycle hooks re-arm the
trap and release any held controls safely.

A stock Gridmap V2 concrete crash block spans the lane 29.65 m beyond the
trigger center. The Phase 4 automation approaches in Drive at 3–5 m/s, records
state/electrics/damage telemetry through the launch and impact, and rejects
missing damage, insufficient launch speed, weak deceleration, or Lua errors.

## Coordinate contract

- Coordinate system: right-handed, meters, Z-up
- Asset drive axis: local `+Y`
- Asset world origin: `[-122.011475, -170.0, 100.0]`
- Trigger local center: `[0.0, 7.35, 1.82]`
- Trigger world center: `[-122.011475, -162.65, 101.82]`
- Trigger dimensions: `[4.8, 1.5, 3.4]`
- Truck spawn: `[-122.011475, -182.5, 100.747742]`, facing world `+Y`

The authoritative Blender measurements remain in
`levels/gridmap_v2/art/shapes/carwash/cannon_car_wash.geometry.json`.
The Phase 3 scripting contract is recorded in
`mod_info/cannon_car_wash/phase3_manifest.json`.
The automated impact and telemetry contract is recorded in
`mod_info/cannon_car_wash/phase4_manifest.json`.

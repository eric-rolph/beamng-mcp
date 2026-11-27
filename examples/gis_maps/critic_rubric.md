# Critic rubric for the GIS maps art pass

The critic reviews the sheets in `<map>/authoring/critic/` (rendered by
`critic_sheets.py` from the built level, never from a game capture) against this
rubric and writes a verdict per map. A verdict is **WOWED** only when every line below
is at least "convincing"; anything "distracting" is a finding with a concrete,
data-driven fix the generator can make (a spec value, a family parameter, a
classifier threshold), never "make it prettier".

| Line | Sheet | Convincing means |
| --- | --- | --- |
| Base colour | 01_overview | No baked sun: shaded walls read as the same material as lit ones; no seams, no black holes, no blown highlights; the plain is the reference photo's tone (crater: warm tan with cream rim ledges; pass: grey talus, green forest, olive tundra). |
| Ground-level read | 02_view_*_driver | Standing at a spawn the terrain reads as that place: scale, colour and object density match the photograph; nothing floats or sinks; no obvious tiling. |
| Drone read | 02_view_*_drone | The landmark (rim, shelf road, forest edge) is recognisable; placed objects follow the landform (boulders on talus, trees stopping at the tree line, shrubs on the plain, none on the road bed). |
| Terrain materials | 03_terrain_swatches | Each family is nameable at a glance (blocks, cobbles, bedded ledges, plates, tussocks, asphalt, rutted track); no corduroy, brickwork, paving or worm patterns; normal maps carry the shapes; height maps are plausible relief. |
| Objects and roads | 04_object_and_road_swatches | Rocks look like weathered rock, not cells; bark looks like bark; foliage cards have a believable silhouette and colour; road decals have ruts and edges. |
| Shapes | 05_shape_geometry | Boulders are lumpy and asymmetric with a flat base; trees have a trunk and a spire/crown of the right proportions; nothing is a box. |
| Placement | 06_placement_map | Density and distribution match the data story: rocks where the lidar found bumps on rock layers, shrubs as the photograph's dots, forest as the photograph's cover with a real edge; no rows, grids or fence lines. |
| Road bed | 07_road_profile | The grade line is smooth at driving scale (no 1 m noise), with no cliffs or trenches. |

Each finding names the sheet, the line, what is wrong in plain words, and the fix as a
spec or parameter change. The verdict is the last line: `VERDICT: WOWED` or
`VERDICT: NOT YET`.

"""Blender-headless backdrop skyline for the Giant's Hearth level (design v4 §2.6).

Run (Blender 4.5.4, the validated runtime)::

    $script = 'examples/hot_potato_arena/level/blender_backdrop.py'
    $out = 'examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena/' +
        'art/shapes/hot_potato_arena_backdrop'
    & $blender454 --factory-startup --background --python $script -- --out $out

The ring closes the world beyond the 2,047 m terrain block on the axes and stands ON the
block's last 316 m at the corners (critic r11 N11-8): mountains 1,150-1,400 m from the
anchor C, rising from a foot at z 140 (below every sightline out of the basin) to a ridge
line between z 320 and z 640, and since r12 a closed solid with collision (below). It
casts no shadow: ``castShadows false``.

**r2 rebuild (critic r1 D-1).** r1 shipped ONE quad strip - two vertices per
column, 384 triangles for the whole horizon, every column at essentially the same
radius - so no ridgeline could ever occlude another, and the profile was a sum of
sines whose 24-cycle term repeated the silhouette every 30 deg (measured circular
autocorrelation 0.926 at lag 30 deg, peak-height stdev +-5.6 % on a 577 m mean).
This module now builds:

* ``RINGS`` = 3 concentric ridge rings at separated radius bands (near 1,180 m,
  mid 1,288 m, far 1,382 m), each a closed strip from z 140 up to its own ridge
  line, so a near ridge OCCLUDES the far ones behind it and far summits show over
  the near saddles - the primary depth cue r1 had none of;
* per-ring silhouettes built from a SEEDED set of Gaussian summits with
  log-uniform amplitudes (a factor of 5-6 spread, not +-5.6 %) at jittered
  bearings, plus a seeded 1-D crenellation for shoulders and spurs. Nothing in
  the profile is periodic, so the silhouette does not repeat;
* ``SEGMENTS_V`` = 4 vertical segments per column and ``COLUMN_SEGMENTS`` = 384
  columns per ring (0.94 deg), i.e. 9,216 triangles instead of 384;
* the 306 deg outlet notch built as a real notch: the near ring's summits are
  suppressed there and the far ring carries two tall summits at 306 +- 7 deg, so
  the S1 frame sees two farther peaks THROUGH the notch;
* an 8,192-wide strip (22.76 px/deg against 20.98 screen px/deg at 1920 x 1080,
  vertical FOV 60) so the texture is minified, not magnified 1.87x.

**r7 ridge pass (critics r3, r4, r5 and r6, the same sentence four times).** r2
fixed REPETITION and never touched SHAPE. Every summit was one Gaussian,
``exp(-(d/w)^2)``: symmetric about its apex, zero slope at the apex, an infinite
smooth tail, and identical to every other summit up to a scale factor. That is the
definition of a dome, and six of eight day bearings read as a row of dunes. The
generator is rebuilt around the five things that make a silhouette read as rock:

* **a sharp apex**, which needs a profile whose slope at the apex is not zero. Every
  flank is now ``(1 - t**a)**b`` on ``t = |d| / w``, whose apex slope is ``-b`` at
  ``a == 1`` and unbounded for ``a < 1``, whose foot is a cliff for ``b < 1`` and a
  feather for ``b > 1``, and which has COMPACT SUPPORT so saddles are real ground
  rather than the sum of two tails. ``a = 2, b = 1`` is exactly r2's parabola, kept
  as one archetype in five so the range still has rounded shoulders in it;
* **asymmetry**: each massif carries its own half-width, ``a`` and ``b`` PER SIDE,
  the steep side placed away from ``WIND_BEARING`` (with a seeded 1-in-6 reversal so
  the rule is not readable), so no summit is a mirror of itself;
* **per-summit shape, not per-summit scale**: five archetypes (``horn``, ``wedge``,
  ``massif``, ``mesa``, ``shield``) with seeded jitter on all six shape numbers - a
  jitter that may never carry an exponent across ``a == 1``, because that boundary is
  the archetype - so neighbouring summits differ in outline and not only in height. As
  shipped: 14 horns, 18 wedges, 12 massifs, 4 mesas, 8 shields, **32 of 56 with a
  non-zero apex slope, 0 of 56 symmetric, median flank asymmetry 0.3483** (r8 / critic
  r7 B7-1: r7 printed 0.3534, which is ``sorted(...)[n // 2]`` - the 29th of 56, an
  UPPER median. ``statistics.median`` is now what the module computes and prints);
* **FOUR TIERS instead of one.** ``_range_walls`` gives each ring 3-4 GREAT RANGES,
  each **37.7-115.6 deg of half-width per side** (r8 / critic r7 B7-6: r7 printed
  "50-115 deg of arc", which is not any reading of the shipped ``_RANGES`` - the three
  that exist are half-width 37.7-115.6, full support 105.7-194.5 and FWHM 64.7-116.9
  deg), the continuous wall a real skyline is (the Sierra from Owens
  Valley), whose normalised height also scales each massif's amplitude, so summits
  are tall on a range's high shoulder and stubby out on its toe. The massifs stand on
  that; **139 spurs** stand on the massifs, half of them past their parent's own foot
  where a subsidiary summit belongs; and a per-ring ``backbone`` and ``crest`` term,
  both a periodic Musgrave RIDGED MULTIFRACTAL - ``(1 - |noise|)**2`` accumulated with
  multifractal weighting, crease where smooth noise rounds;
* **notches that read at 1.2 km**: **48 cols**, cut only where the pre-notch crest is
  above its own 55th percentile (i.e. THROUGH the skyline, not into a saddle that was
  already low), **0.3065-1.3177 deg of half-width and 20.37-74.80 m deep as shipped**,
  which is **12.9-55.3 screen px wide and 16.3-61.0 px tall** at 1,180-1,382 m. A single
  ring may cut below the design's
  z 320 floor - that is what a col IS, and the ring behind it shows through - while the
  VISIBLE silhouette may not: ``_close_the_world`` shallows notches on a 4x-oversampled
  grid until that holds, so the world-closure invariant is structural rather than lucky.
  ``_headroom_scale`` does the same job at the ceiling, because a summit the ``H_MAX``
  clamp catches comes out dead flat on top - the one silhouette defect worse than a dome.

None of that is visible at 0.94 deg per column, so ``TESSELLATION`` goes 8 -> 32:
**1,536 columns per ring at 0.234 deg**, i.e. 4.9 screen px per column at 1920 x 1080
and vertical FOV 60, against a notch 13 px wide. 36,864 triangles, and ``r7/probe/
frame_cost.py`` prices them against a backdrop-off control in the same boot.

**r7 kept r2's envelope and changed only its outline**, which was the control that made
that A/B mean something: visible crest mean **447.206 m against r6's 447.550** - a move of
**0.344 m, 0.077 %** - at 7,680 common bearings, a refinement of BOTH meshes' column grids
(r8 / critic r7 B7-5: r7 printed 447.2 / 447.3 from two different samplings and a header
that named a third; ``r8/probe/ring_envelope.py`` is the script).

**THOSE ARE r7's NUMBERS AND THEY ARE NO LONGER THIS MODULE'S** (r14 / critic r13 B13-2:
they stood here in the present tense through the r13 crest rebuild, a pin-break staleness
in the one file that ships). Measured today on this module at those same 7,680 bearings by
``r14/probe/relief.py``, against r12 frozen:

===========================================  ==========  ==========  =========
cell                                              r12         today     change
===========================================  ==========  ==========  =========
visible crest mean                            447.183 m   436.630 m   -10.553
visible crest min                             346.871 m   348.454 m    +1.582
visible crest max                             634.998 m   597.456 m   -37.542
median 45 deg window relief (720 grid)        189.117 m   133.991 m   -29.1 %
worst 45 deg window relief                    111.151 m    80.771 m   -27.3 %
max apparent elevation from C                  23.128 d    21.385 d    -1.742
===========================================  ==========  ==========  =========

**r13 traded height for shape, and the envelope half of that trade was not deliberate.**
Split the median-relief loss in two: the crest's total range fell 288.13 -> 249.00 m
(93.5 % -> 80.8 % of the 308 m the design's own z 332 visible floor and z 640 ceiling
allow), which is -13.6 %; and its relief per metre of range fell 0.656 -> 0.538, which is
-18.0 %. 0.864 x 0.820 = 0.709, the whole of it. The second half **is the fix**: a range
whose summits are gathered into massifs has 45 deg windows that sit on one massif, where a
picket puts several teeth in every window - the picket's high window relief was a symptom
of the defect, and critic r13's own band decomposition says so (picket energy k21-60 fell
3.6x, 0.204 -> 0.057, while massif energy k4-8 rose 2.2x). The first half is 39 m of
envelope this range simply is not using, and it is recoverable: scaling the visible crest's
AC about its own mean by k leaves EVERY normalised repetition cell exactly unchanged - they
are all shares of AC variance or dimensionless shape ratios - and the floor binds at
**k = 1.1866**, worth a median relief of **158.99 m**. r14 does not spend it: this
revision's claim is that the crest did not move at all (0.000 m at 7,680 bearings, so the
apron is provably buried), and moving the crest and the world's edge in one revision would
leave neither checkable. It is named, priced and carried.

Scored by ``r7/probe/ridge_shape.py``
against seven stock terrains' own ray-marched skylines, band-limited to our own column
pitch, ``peak_asymmetry`` goes from 0.0263 - **4.8x BELOW** the stock minimum, and 0.000
by construction for a Gaussian - to **0.192, inside the stock band**, and all four other
shape cells move toward it.

Geometry is a pure function of the bearing, so the module's constants are
importable without ``bpy`` and the static gate can predict every vertex:

    ridge_profile(bearing) -> (visible ridge top z, its radius from C)

which is the silhouette a player at the basin floor actually sees: the ring whose
apparent elevation is highest at that bearing.

**r12: a SOLID RANGE (critic r11 B11-3; the user's requirement that "the rocks, boulder
and mountain aren't just facade, but have complete 3D geometry").** Through r11 each ring
was ONE open surface: 1,536 columns x 7 rows from a foot at z 140.00 to the crest, 0.00 m
of radial thickness at all 4,608 columns, six boundary loops, single-sided, ``collisionType
"None"`` and no Colmesh - and the square terrain block, 1,447 m from C at its corners, ran
PAST the near ring's foot on 562 columns, so a car drove through the ribbon onto grass
behind a range that was not drawn from there. r12 closes every column into a POLYGON:

* a **front toe** 60 m inside the foot at ``Z_FLOOR`` (z 60, under the WaterPlane at 98 and
  the lowest terrain node under the range at 110.2 - the lake bed at the arena, 86, is the
  block's global minimum and lies 1 km inside the ring), so the foot is buried on every
  column - including the 59 where it hung up to 17.8 m above the ground;
* the **seven front rows unchanged**, vertex for vertex and in the same order, so the crest
  polyline is bit-for-bit r11's and every published silhouette statistic survives. The
  crest edge AND the foot edge are marked SHARP (Blender writes split per-loop normals
  while the vertices stay shared - ``b1/r12/blender_test/sharp_probe.py``), so the front
  face's per-loop normals on all seven rows are r11's too - the shading the basin sees does
  not move by one bit - and the ridge is an arete;
* a two-segment **summit shoulder** behind the crest, always below it;
* a three-segment **back face** - a headwall under the shoulder, a steep flank, a gentle
  apron - down to a **back foot** that stands ``PENETRATION_M`` beyond the NEXT ring's crest
  radius (so the near ring's back runs into the mid ring's front and the valley floor is
  their intersection, with no water and no daylight between the ridges), or, for the far
  ring, on a bench at ``OUTER_BENCH_R`` = 1,470 m, beyond the block's 1,447 m corners;
* a **back toe** at ``Z_FLOOR`` (a near-vertical drop hidden inside the next ring; a 40 deg
  apron into the sea for the far ring) and a flat **underside** closing the loop.

Where the terrain block reaches the back foot (the four diagonal arcs) the back foot is set
``VALLEY_BURY_M`` UNDER the ground there, so the back face rises out of the terrain along a
natural intersection rather than a straight line. **It is NOT "a real high valley a camera
can stand in", which is what this sentence used to claim** (r14 / critic r12's N12-1 and
critic r13's B13-2: the claim was asked to be corrected in r12, the r13 report's section 16
withdrew the frames that rested on it, and the sentence was left standing in the source
that ships). The measurement is r13's own: **free terrain between the near ring's back and
the mid ring's front exists on 9 of 384 columns** - 2.3 % of the circle - and everywhere
else the two solids meet or overlap. A camera can be put there; a player cannot drive to
it, and nine columns is a slot, not a valley. r14 does not touch any back face, so the
number stands; where it does not reach, the back foot is ``VALLEY_Z`` or the highest
terrain node under the span plus ``VALLEY_MARGIN_M``, whichever is higher, so no terrain
ever shows through a
back face. The terrain is read from the shipped ``.ter`` (numpy only, so this runs inside
Blender) and its sha256 is printed with the build.

Each ring is then a closed torus - boundary 0, non-manifold 0 by
``geometry_audit/manifold_probe.py`` - with a back, a top and an underside, **46,080
triangles per ring since r14's fifteenth row** (r12-r13: 43,008), i.e. **138,240 for the
range** (r12-r13: 129,024), which is exactly the top of the critic's own 92,160-138,240
price band, and a ``Colmesh_<name>-1`` node built from the SAME fifteen-row polygons at
EVERY column - the visual, vertex for vertex, 138,240 triangles - so there is no chord
anywhere between what is
seen and what is hit (the first draft's seven-row chord floated ~20 m over the concave back
face): the TSStatic record is ``collisionType "Collision Mesh"``. The back and the skirt
reuse the atlas with ``v`` keyed to absolute z on both sides of the crest and mirrored below
the foot, so the texture is continuous over the ridge and at the foot and no row is
stretched.

Node tree follows the stock trailing-number convention and the arena laws:
``base00 -> start01 -> {<id>_backdrop_ring_a1, Colmesh_<id>_backdrop_ring-1, nulldetail1}`` -
one detail that engages from 1 px (i.e. always), the collision mesh, and the stock
``nulldetail`` node (QB-7).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

LEVEL_ID = "ericrolph_hot_potato_arena"
BACKDROP_DAE_NAME = f"{LEVEL_ID}_backdrop_ring.dae"
BACKDROP_MATERIAL = f"{LEVEL_ID}_backdrop"
BACKDROP_DETAIL_PX = 1
BACKDROP_NODE = f"{LEVEL_ID}_backdrop_ring_a{BACKDROP_DETAIL_PX}"
NULLDETAIL_NODE = "nulldetail1"

RIDGE_COLUMNS = 48
#: r7: 8 -> 32. At 0.9375 deg a column is 19.7 screen px wide at 1920 x 1080 / vertical
#: FOV 60, so the silhouette was a 20-px polyline and no notch, spur or step narrower
#: than a fifth of a summit could exist in the mesh at all. 0.234375 deg is 4.9 px.
TESSELLATION = 32
COLUMN_SEGMENTS = RIDGE_COLUMNS * TESSELLATION  # 1,536 columns per ring, 0.234375 deg
#: r9: 4 -> 6. A curtain needs one segment; a FLANK needs enough rows to resolve
#: ``d phi / d t``, and 6 with ``VERTICAL_BIAS`` puts four of them in the top 30 % of the
#: column - the part the basin rim leaves visible. 8 was measured and is within 1 % of 6
#: on every shading statistic for 1.9 MB more of `.dae`, so 6 is where it stops.
SEGMENTS_V = 6  # vertical segments per column
Z_BASE = 140.0
Z_TOP = 650.0
H_MIN, H_MAX = 320.0, 640.0
#: r7: the floor a SINGLE ring may cut to. ``H_MIN`` is design §2.6's ridge line and is
#: asserted on the VISIBLE silhouette (``ridge_profile``, the max apparent elevation over
#: the three rings); a col in the near ring that drops below it reveals the mid or far
#: ring standing behind, which is what a mountain pass looks like and what the three
#: separated radius bands were built for. Nothing here may show sky below H_MIN.
RING_FLOOR_Z = 252.0
R_MIN, R_MAX = 1150.0, 1400.0
NOTCH_BEARING = 306.0  # the outlet notch the sun sets over
EYE_Z = 100.0  # the basin floor: what "visible silhouette" is measured from
#: r7: the bearing the prevailing wind comes from. Each massif's STEEP side is placed
#: away from it (a seeded 1-in-6 reversal keeps the rule from being readable), so the
#: range has a windward and a lee grain instead of 56 mirror-symmetric summits. (r8 /
#: critic r7 B7-9: 56, not 54. ``spec.summits`` sums to 54, but ``_summits`` appends two
#: more to the far ring for the outlet notch and both are Gaussian terms in r2-r6.)
WIND_BEARING = 245.0
#: The atlas the UVs below are written for. The ONE authority for its size is
#: ``cook_terrain_textures.BACKDROP_STRIP``: 8,192 / 360 = 22.76 px per degree, against
#: 1920 / 91.5 = 20.98 screen px per degree at the design's 1920 x 1080 / vertical FOV
#: 60 (critic r1 D-1). r2 also declared a local ``STRIP_H = 2304`` that nothing read and
#: that is NOT a power of two - the exact trap this round's own law names (the engine
#: logs "skip cooking, texture is smaller than 16x16 or not power of 2" and renders the
#: shape untextured). Deleted; the height comes from the cook (critic r2 N-1).
#: (This module must stay importable inside Blender, which has numpy but no Pillow, so
#: it cannot import the cook - the static gate asserts the two agree instead.)
STRIP_W, STRIP_H = 8192, 2048
STRIP_BANDS = 3  # one horizontal haze band per ring, STRIP_H // 3 rows each

# --- r9: the FLANK (critic r8, "the player"; leg 3 of the B7-10 depth study) ----------
#: Through r8 the ring was a VERTICAL CURTAIN - one radius per (ring, bearing). Every
#: quad had an exactly vertical edge ``(0, 0, a)``; crossed with the tangential edge
#: ``(p, q, c)`` that is ``(-aq, ap, 0)``, so **all 36,864 triangle normals had ``n_z``
#: exactly zero** (critic r8 read them out of the shipped DAE). No face could catch or
#: lose light with height, and on the one front-lit certified bearing the biggest massif
#: rendered as a cream cut-out with no shading gradient anywhere across it.
#:
#: Leg 3 pins the CREST VERTEX bit-for-bit and leans the flank below it inward:
#:
#:     z(b, t) = Z_BASE + D(b) * t                 D(b) = top(b) - Z_BASE
#:     r(b, t) = r(b) - Dm(b) * phi(b, t)          phi(b, 1) = 0
#:
#: * the ``t = 1`` row is the shipped crest polyline unchanged, so `ridge_profile`,
#:   `visible_ring`, `silhouette_summary`, `_close_the_world` and all five `ridge_shape`
#:   cells are invariant AS VALUES at every eye - not only at the ring centre, which is
#:   where leg 2 (``b1/r8/probe/ring_fold_v2.py``) failed under critic r8's B8-4;
#: * ``Dm`` is the crest height SMOOTHED over ``HEIGHT_SMOOTH_DEG``. Scaling by the
#:   column's own ``D`` puts the crest's 0.234 deg noise into the RADIUS and renders as
#:   thin vertical blades; leg 1 divided by ``D`` and rendered as corduroy. Both defects
#:   are runnable in ``b1/r9/probe/ring_flank.py``;
#: * the bearing fields are DIFFERENCES OF GAUSSIANS, not of boxcars. A boxcar pair is a
#:   band-pass with sinc sidelobes that pass the crest noise straight through - r9's first
#:   draft did that and rendered 31 m fins.
#: The mesh is smooth-shaded and the bearing-0 seam is WELDED (the columns wrap; the u
#: seam lives in the per-loop UVs), so no normal is averaged across a hole and there is no
#: bright line at bearing 0.
#: The flank's KNEE as a fraction of the column height. ``G(t) = (1-t)/((1-t)+K)`` is a
#: mountain's own profile - steep immediately under the summit, flattening into an apron.
#: The slope just under the crest is ``S / K``. ``1 - t**3`` was tried first and its
#: median face was 3.4 deg off vertical: a curtain with a lean, not a flank.
FLANK_KNEE = 0.12
#: The flank depth as a fraction of the column height: mid +- swing across the massif
#: band. Strictly positive at every bearing, so no column can lean the wrong way.
FLANK_DEPTH_MID = 0.056
FLANK_DEPTH_SWING = 0.028
#: The spur amplitude, same units, SIGNED: a spur advances toward the basin and the gully
#: beside it retreats, and both vanish at the crest and at the foot.
SPUR_AMPLITUDE = 0.048
#: Gaussian sigma pairs, in degrees, for the two bearing fields. Sized in METRES on the
#: ring: sigma 4 deg = 82 m (a spur), sigma 22 deg = 453 m (a massif).
MASSIF_BAND_DEG = (4.0, 22.0)
SPUR_BAND_DEG = (1.6, 5.0)
# --- r13: the BUTTRESS (critic r12, "the player": the foot) ---------------------------
#: *"At the foot it is still a texture wall - a beige blur at 10 m, a ruler-straight seam
#: with the grass."* Half of that is texture and is answered by the detail graft in
#: ``cook_terrain_textures``. The other half is GEOMETRY, and it is this: through r12 the
#: ring's foot sat at ``Z_BASE`` = 140.00 on all 4,608 columns - a perfect horizontal
#: circle - and the front face below the crest was a smooth surface of revolution leaning
#: uniformly inward. Where that meets flat ground the intersection is a straight line,
#: because both surfaces are smooth and one of them is level. Nothing about the seam is a
#: texture problem.
#:
#: A third bearing field fixes it: ribs and gullies at the 0.45-2.6 deg scale (9-54 m wide
#: on the near ring) that are strongest AT the foot and gone by ``BUTTRESS_TOP``. The
#: terrain then cuts the face along a line that wanders by tens of metres instead of
#: running level, and a player at 10 m is standing in front of a buttress rather than a
#: wall. It is taken from the crest's own fine structure through the same difference of
#: Gaussians the other two fields use, so a rib runs down from a real feature above it -
#: which is what a buttress is - rather than being noise sprayed on the bottom.
#:
#: Zero at ``t = 1`` by construction, like everything else in ``flank_offset_m``: the
#: silhouette this revision paid for is not touched by the foot.
BUTTRESS_BAND_DEG = (0.45, 2.6)
#: Amplitude as a fraction of the column's own smoothed height. **One-sided: the field
#: only ever CUTS BACK, never protrudes.**
#:
#: The first draft was signed - a rib standing out toward the basin, a gully beside it -
#: and it doubled the level's overhang. A larger offset is a smaller radius, so a rib
#: PROTRUDING at the foot is a low ``offset(0)``, and every point above it then leans out
#: past the foot toward the player. Measured (``b1/r13/probe/foot_geometry.py``): r12 had
#: 272 columns leaning out over ground a car can stand on, by at most **4.40 m**; the
#: signed buttress made that **19.66 m**, which is not a mountain feature, it is a roof.
#:
#: A one-sided field cannot do that: ``B(t)`` is non-increasing and the coefficient is
#: non-negative, so the term is non-increasing and can never lift a higher point's offset
#: above the foot's. And it is the more honest shape anyway - water cuts channels into a
#: mountain's foot; nothing extrudes ribs out of it. The ribs are still there. They are
#: what is left standing between the gullies, which is what a rib is.
BUTTRESS_AMPLITUDE = 0.085
#: ``_band_residual`` normalises by the p95 of ``|residual|`` and clips, so most columns
#: come back near zero: measured on the first draft, the median rib was 0.0096 of the
#: column height (2.4 m) against a maximum of 13.8 m. A wall with two ribs on it is still
#: a wall. A signed gamma below 1 lifts the MIDDLE of the distribution without touching
#: its ends, so every column gets some section and the biggest ribs stay the biggest.
BUTTRESS_GAMMA = 0.6
#: The height fraction the buttress has died out by. 0.42 of a 210-460 m column is
#: 88-193 m - a real buttress, not a skirting board.
BUTTRESS_TOP = 0.42
#: The falloff exponent from the foot to ``BUTTRESS_TOP``. Above 1 the rib holds its
#: section for the lower half of its run and then tapers, which is a buttress; at 1 it is
#: a wedge and reads as a fold in a curtain.
BUTTRESS_POWER = 1.6
#: The sigma the column height is smoothed with before it scales the radial offset.
HEIGHT_SMOOTH_DEG = 3.0
#: Row spacing: ``t = (step / SEGMENTS_V) ** VERTICAL_BIAS``. Below 1 it clusters the rows
#: under the crest, where ``G`` bends.
VERTICAL_BIAS = 0.55
#: Gaussian kernels are truncated here and renormalised.
GAUSSIAN_TRUNCATION_SIGMA = 3.0

# --- r12: the SOLID (critic r11 B11-3) ------------------------------------------------
#: The underside of the range. Below the WaterPlane (z 98) and the lowest terrain node
#: (z 110.2), so no column's underside is ever in the open.
Z_FLOOR = 60.0
#: The front toe leans this far INSIDE the foot on its way down to ``Z_FLOOR``: a buried
#: (or, on the axes, sea-facing) apron rather than a vertical plate.
FRONT_TOE_IN_M = 60.0
#: The summit shoulder behind the crest, as (metres out, metres down) from the crest
#: vertex. Every point is below and behind the crest, so nothing here can rise into the
#: pinned silhouette from any eye inside the ring.
SHOULDER: tuple[tuple[float, float], ...] = ((5.0, 2.0), (14.0, 7.0))
#: The back face between the shoulder's end and the back foot, as (fraction of the run,
#: fraction of the drop): a headwall, a steep flank, then the gentle apron a valley floor
#: is met with. The last segment is the back foot itself at (1, 1).
BACK_PROFILE: tuple[tuple[float, float], ...] = ((0.12, 0.45), (0.40, 0.85))
#: The lowest a valley floor between two rings may be where no terrain lies under it.
VALLEY_Z = 230.0
#: A back foot that passes OVER terrain clears the highest node under its span by this.
VALLEY_MARGIN_M = 10.0
#: A back foot that stands ON terrain is set this far under the ground, so the back face
#: rises out of the terrain along a natural intersection instead of ending on a step.
VALLEY_BURY_M = 12.0
#: The terrain envelope is dilated this many columns each way before it is smoothed, so
#: the smoothing can never dip under a node the dilation saw.
VALLEY_DILATE_COLUMNS = 8
VALLEY_SMOOTH_DEG = 0.7
#: The back foot of the near and mid rings stands this far beyond the NEXT ring's crest
#: radius: the back face runs into the next ring's front face and the visible valley floor
#: is their intersection, so there is no gap, no water and no daylight between ridges.
PENETRATION_M = 20.0
#: The far ring's back foot: a bench beyond the terrain block's corners (1,446.7 m from C).
OUTER_BENCH_R = 1470.0
#: Metres of run per metre of drop for the far ring's apron into the sea (~40 deg).
OUTER_RUN = 1.2
#: The near and mid back toes: a near-vertical drop, hidden inside the next ring.
BACK_TOE_OUT_M = 10.0

# --- r14: the SHORE APRON (critic r13 B13-1) ------------------------------------------
#: *"On my own boots, at 90, 20 and 250 degrees, the car leaves the terrain block before
#: the mountain and ends at z 0.98, 0.11 and -122.96 with no wheel on anything."*
#:
#: The square block is 2,047 m and C is its centre, so the ground stops **1,023 m** out on
#: the axes and **1,447 m** out on the diagonals, while the ring's foot stands at
#: 1,111-1,187 m all the way round. On the diagonals the ground therefore laps 260-330 m
#: PAST the foot and a car drives into rock. On the axes it stops up to **82 m short of
#: the ring's own toe**, and between the two there was nothing at all - not water, not
#: rock, not a kill plane: the car fell. ``r14/probe/world_edge.py`` sweeps it analytically
#: at 0.25 deg and finds the hole open on **648 of 1,440 bearings - 45 % of the circle**,
#: in four arcs of 36.5-44.75 deg centred on the four axes, worst 82.16 m at 94.75 deg.
#: Every drive in r11, r12, critic r12 and r13 was fired at 45 / 135 / 225 / 315, which is
#: why three revisions of gates never saw it. It is B11-3's last quarter.
#:
#: The fix is an APRON: the ring's front toe is pulled inward until it stands **under the
#: terrain block** on every bearing, so the first thing outward of the grass is rock. That
#: needs a **fifteenth polygon row**, because the toe cannot simply be raised: the
#: underside is one edge from the back toe to the front toe, and a front toe at the block
#: edge's own height (110-267 m) lifts that edge above the foot at z 140 and the section
#: stops being a simple polygon. So row 0 becomes the **apron LIP** - the point where the
#: rock meets the ground, 1.5 m under it - and a new last row is the **front toe**,
#: directly below the lip at ``Z_FLOOR``. The underside stays flat at z 60 on every column,
#: which is the invariant r12 bought and critic r13 verified, and the new edge 14 is a
#: vertical inner wall that is buried or under water everywhere.
#:
#: Price, declared: 14 -> 15 rows is 129,024 -> **138,240** triangles per geometry, which
#: is exactly the top of critic r7's own 92,160-138,240 price band, and 64,512 -> 69,120
#: vertices. Nothing else in the section moves.
#: The lip stands this far INSIDE the block edge. Small on purpose: the drop a player
#: takes at the lip is ``APRON_BURY_M + APRON_OVERLAP_M x (apron slope - ground slope)``,
#: so a wide overlap makes the step WORSE, not better. 5 m against a 4.5 m column pitch and
#: a 0.002 m chord sag is still an overlap on every column.
APRON_OVERLAP_M = 5.0
#: And this far under the ground at the lip, so the rock never pokes through the grass.
APRON_BURY_M = 1.5
#: The shortest run the apron chord may have from the lip to the foot, and the radius
#: inside the foot past which the lip is no longer moved out to meet the block's edge.
#: It is deliberately the same 20 m the probe calls ``AT_THE_MOUNTAIN_M``: inside it the
#: grass meets the front FACE and there is no apron to speak of, so the two thresholds are
#: one number and the branch changes exactly where the regime does.
APRON_MIN_RUN_M = 20.0
#: The inner wall's minimum height, for the columns that need no apron at all (the mid and
#: far rings, and the near ring where the block already laps past its toe): the row must
#: still be a row, because a zero-height quad is a degenerate triangle.
APRON_MIN_LIP_M = 8.0
#: The lip is smoothed along the bearing and then RE-ASSERTED against both bounds, exactly
#: as ``valley_floors`` does, so a kink where the two bounds cross cannot leave a sliver.
APRON_SMOOTH_DEG = 0.7
#: The clearance rule is sampled this many times along the part of the apron that is still
#: under the block. Burying only the LIP is not enough: where the ground falls away faster
#: than the chord does, the rock comes back out through the grass further along - 17.3 m
#: proud on the r14 first draft, measured by ``r14/probe/world_edge.py``.
APRON_CLEARANCE_SAMPLES = 24
#: The clearance samples stop this far short of the foot. The chord's lever goes to zero
#: there, so the bound goes to infinity (or, where the ground is below z 140 - the hanging
#: foot r11 measured - to minus infinity) and the sample says nothing about the lip.
APRON_TIP_GUARD_M = 12.0
#: Only the NEAR ring carries the shore apron. The mid and far rings stand behind it and
#: cannot be reached; an apron on them would reach INSIDE the near ring's own face and
#: render in front of it.
APRON_BANDS: tuple[int, ...] = (0,)
#: --- r16 / B15-2: the gutter gets a floor -------------------------------------------------
#:
#: **The finding this row answers, and it is not the one r15 named.** r15 proposed spending
#: this row on a BENCH at the top of the apron chord. Critic pass 15 priced that correctly
#: and it does not survive the price: the exposed slope is
#: ``(ground - APRON_BURY_M - Z_BASE) / (foot_r - edge_r)``, both terms fixed by the terrain
#: and by the ring, so **an extra vertex anywhere on the chord redistributes the drop and
#: cannot lower its maximum.** Measured on the shipped module over the 852 shore columns
#: (``r16/probe/apron_r16.json``): median exposed run 92.632 m, median drop 70.009 m, so
#: 0 / 5 / 10 / 20 / 30 m of bench give **37.08 / 38.62 / 40.27 / 43.95 / 48.18 deg** - and a
#: 10-20 m bench is **0.30-0.71 s** at the 28-33 m/s cars actually cross the edge at. It
#: buys the crawler a shelf and hands the charger a steeper chute.
#:
#: **What the same row buys at the other end of the chord is a road.** The gutter - the V
#: between the descending apron and the ring's own front face - has, today, a floor
#: **0.493 m wide** (median over the shore columns, measuring the mesh within 0.35 m of
#: ``Z_BASE``). A car is 2 m wide. The apron comes down at 39.5 deg and the face goes up at
#: **78.65 deg**, an included angle of **61.9 deg**: it is a ditch, and that is why r15's own
#: live leg found *"two of four could not traverse it"* and why critic pass 15's car covered
#: **0.5 m in 60 s of full throttle**. Nobody has named it, in three revisions of measuring
#: the fall.
#:
#: So the extra row is the apron's TOE: a level strip at ``Z_BASE`` from ``foot_r - w`` out
#: to the ring's own foot. It costs the chute **0.91 / 1.22 / 1.86 / 2.52 / 3.19 deg** for
#: **3 / 4 / 6 / 8 / 10 m** of floor - a fraction of the bench's price for the same triangles
#: - and what it buys is **7.2 km of level road** at the foot of the mountains, with the
#: 73 exits the census already found at the end of it. ``GUTTER_FLOOR_M`` is 6 m: three times
#: a vehicle's width, and **1.86 deg**, which leaves the median column at 38.94 deg, still
#: under the 40 deg line that today marks 416 of the 852 shore columns.
#:
#: Price, declared: 15 -> 16 rows is 138,240 -> **147,456** triangles per geometry and
#: 69,120 -> **73,728** vertices - exactly the count critic pass 15 predicted for this row.
GUTTER_FLOOR_M = 6.0
#: The floor never closes to nothing: a zero-width row is a degenerate triangle, which is
#: the same reason ``APRON_MIN_LIP_M`` exists. Where the block laps past the ring's foot the
#: strip is buried under the terrain and 0.5 m of it is a formality, not a shelf.
GUTTER_FLOOR_MIN_M = 0.5
#: The floor keeps this much clear of the block's own edge, and the width ramps from the
#: minimum to the full 6 m as the foot comes out from under the block, so ``w`` is a
#: continuous function of the bearing and no column gets a step in it.
GUTTER_FLOOR_MARGIN_M = 4.0
#: Rows appended to each column after the seven front rows: apron lip, (r16) the apron toe
#: that floors the gutter, two shoulder rows, two back rows, the back foot, the back toe and
#: (r14) the front toe.
EXTRA_ROWS = 9
POLYGON_ROWS = SEGMENTS_V + 1 + EXTRA_ROWS  # 16 vertices round each column's section
#: Which polygon point is the FIRST of the seven front rows. r14's section put the lip at
#: point 0 and the front rows at 1..7; r16 adds the apron toe at point 1, so they start at 2.
#: Every index map below is written against this rather than against a literal, because the
#: last time this number moved it moved in four places.
FRONT_POINT_0 = 2
#: The polygon edges that are NOT the front face (0: lip -> toe; 1: toe -> foot, the gutter's
#: floor; 8: crest -> shoulder; 14: back toe -> front toe, the flat underside; 15: front toe
#: -> lip, the inner wall). Derived, so it cannot disagree with ``FRONT_POINT_0``.
EXTRA_EDGES: tuple[int, ...] = tuple(
    edge for edge in range(POLYGON_ROWS) if not FRONT_POINT_0 <= edge < FRONT_POINT_0 + SEGMENTS_V
)
#: ...and the polygon POINTS that are not front rows, which is what ``solid_vertices``
#: appends and what ``EXTRA_ROWS`` counts. Derived from the same number for the same reason.
EXTRA_POINTS: tuple[int, ...] = tuple(
    point
    for point in range(POLYGON_ROWS)
    if not FRONT_POINT_0 <= point <= FRONT_POINT_0 + SEGMENTS_V
)
if len(EXTRA_POINTS) != EXTRA_ROWS:  # the two are the same count said two ways
    raise RuntimeError(f"{len(EXTRA_POINTS)} extra points against EXTRA_ROWS {EXTRA_ROWS}")
#: The collision mesh: EVERY column and ALL fourteen polygon rows, i.e. the visual polygon
#: itself. A first draft took every second column and seven rows (32,256 triangles): its
#: front-face chord sat within 0.6 m of the visual flank where a car can reach, but its one
#: chord from the shoulder to the back foot floated ~20 m above the concave back face, and
#: the odd columns sat up to 0.15 m off the chord at the sharpest spurs. The cost of the
#: full polygon is 96,768 more collision triangles for a phantom gap of exactly 0.0 m at
#: every column and every row, and a visual / Colmesh volume ratio of exactly 1.
COLMESH_COLUMN_STEP = 1
COLMESH_ROWS: tuple[int, ...] = tuple(range(POLYGON_ROWS))
COLMESH_NODE = f"Colmesh_{LEVEL_ID}_backdrop_ring-1"
#: The shipped terrain, read by the valley-floor rule. The .ter is B1's own output and is
#: frozen in every cut since r6; its sha256 is printed with the build.
TERRAIN_TER = (
    Path(__file__).resolve().parents[1] / "mod" / "levels" / LEVEL_ID / (f"{LEVEL_ID}_terrain.ter")
)
TER_VERSION = 9
TERRAIN_POSITION = (-174.0, -1304.0)
TERRAIN_UNIT_M = 5.0 / 1024.0
#: The ring's TSStatic sits at C; the DAE is local to it (``level_writer.CENTER``).
CENTER_XY = (850.0, -280.0)
TERRAIN_SAMPLES_PER_SPAN = 128
TERRAIN_EDGE_INSET_M = 1.5

COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
EXPECTED_TREE = {
    "base00": None,
    "start01": "base00",
    BACKDROP_NODE: "start01",
    COLMESH_NODE: "start01",
    NULLDETAIL_NODE: "start01",
}


@dataclass(frozen=True)
class RingSpec:
    """One concentric ridge ring."""

    name: str
    radius_m: float
    radius_swing_m: float
    base_z: float
    amp_lo: float
    amp_hi: float
    summits: int
    #: r7: the ridged-multifractal CREST detail (m). r2's ``crenellation_m`` was a
    #: smooth Catmull-Rom at 7-8 m - 0.33 deg, six screen px, and rounded. A crease
    #: has to be 15-30 m to read at 1.2 km, and it has to be a crease.
    crest_m: float
    #: r7: the range's own long undulation (m), 3 octaves, so the crest line is not
    #: level between massifs.
    backbone_m: float
    #: r7: how many GREAT RANGES the ring is made of, and how tall the tallest is (m).
    #: See ``_range_walls``: this is the tier that turns a picket of cones into a wall.
    range_walls: int
    range_m: float
    #: r7: cols cut THROUGH the crest, chosen above the ring's own 55th percentile.
    notches: int
    seed: int


#: Three rings in SEPARATED radius bands, so which one is in front is never
#: ambiguous and the near ones always occlude the far ones.
#: r7 lowers each ``base_z`` (the col floor) and raises the amplitudes by the same
#: order, so the crest has somewhere to fall to: r2's near ring sat on a 332 m plinth
#: and could only ever undulate 48-176 m above it.
#: r13 raises ``crest_m`` (24/22/19 -> 30/27/24) with the sixth crest octave: see
#: ``CREST_OCTAVES``. The crest detail is the only tier that is BROADBAND, and it is what
#: keeps a massif's top a ridge rather than a plateau (critic r12, taste). 34/31/27 was
#: tried and rejected: it randomised the half-widths enough to push ``peak_asym_mean``
#: BELOW the stock band (0.1594 against a floor of 0.1625) while adding nothing the eye
#: could see, which is the shape of a number chased instead of a picture improved.
RINGS: tuple[RingSpec, ...] = (
    RingSpec("near", 1180.0, 26.0, 310.0, 48.0, 148.0, 24, 30.0, 20.0, 4, 62.0, 21, 0xB1A5E1),
    RingSpec("mid", 1288.0, 22.0, 304.0, 46.0, 154.0, 17, 27.0, 18.0, 3, 70.0, 15, 0xB1A5E2),
    RingSpec("far", 1382.0, 15.0, 308.0, 48.0, 128.0, 13, 24.0, 17.0, 3, 70.0, 12, 0xB1A5E3),
)


@dataclass(frozen=True)
class Massif:
    """One summit, authored as a SHAPE rather than as a scaled copy of one shape.

    ``a_*`` / ``b_*`` are the flank exponents of ``(1 - t**a)**b`` on that side, with
    ``t = |bearing - self.bearing| / w``. The apex slope is ``0`` for ``a > 1``
    (r2's dome), ``-b`` for ``a == 1`` (a wedge) and unbounded for ``a < 1`` (a horn);
    the foot is a cliff for ``b < 1`` and a feather for ``b > 1``. Compact support: a
    massif contributes nothing beyond its own half-width, so what lies between two of
    them is the crest, not the sum of two Gaussian tails.
    """

    bearing: float
    amplitude: float
    archetype: str
    w_neg: float
    a_neg: float
    b_neg: float
    w_pos: float
    a_pos: float
    b_pos: float


@dataclass(frozen=True)
class Notch:
    """A col cut through the crest. ``power`` < 1 gives the steep walls of a slot."""

    bearing: float
    depth_m: float
    half_width_deg: float
    power: float


#: The five outlines, as ``(a, b)`` for the STEEP side and the GENTLE side plus the
#: spur count band. ``shield`` (a=2, b=1) is exactly r2's parabola - one in five, so
#: the range keeps rounded shoulders without being made of them.
ARCHETYPES: tuple[tuple[str, float, float, float, float, int, int], ...] = (
    # name,      a_steep, b_steep, a_gentle, b_gentle, spur_lo, spur_hi
    ("horn", 0.82, 0.70, 1.15, 1.00, 2, 3),
    ("wedge", 1.00, 0.92, 1.55, 1.10, 2, 4),
    ("massif", 1.30, 0.78, 1.25, 0.92, 3, 4),
    ("mesa", 3.10, 0.52, 2.35, 0.60, 1, 3),
    ("shield", 2.00, 1.00, 2.20, 1.05, 1, 2),
)
#: How often each archetype is drawn (cumulative). Horns and wedges carry the skyline.
ARCHETYPE_WEIGHTS: tuple[float, ...] = (0.26, 0.26, 0.22, 0.14, 0.12)


def _angdiff(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def _catmull(points: list[float], t: float) -> float:
    """Periodic Catmull-Rom over ``points`` sampled at ``t`` in [0, 1)."""

    n = len(points)
    x = (t % 1.0) * n
    i = math.floor(x)
    f = x - i
    p0, p1 = points[(i - 1) % n], points[i % n]
    p2, p3 = points[(i + 1) % n], points[(i + 2) % n]
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * f
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * f * f
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * f * f * f
    )


class _Splitmix:
    """A tiny deterministic PRNG - the profile must be identical on every machine."""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def _next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF

    def random(self) -> float:
        return self._next() / 18446744073709551616.0

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()


def _flank(t: float, a: float, b: float) -> float:
    """``(1 - t**a)**b`` on ``t = |d| / w``, clipped to the massif's own support.

    The whole shape vocabulary of the r7 ridge is in these two exponents:
    ``a < 1`` an unbounded apex slope (a horn), ``a == 1`` a corner (a wedge),
    ``a > 1`` a smooth apex (r2's dome), ``a >> 1`` a plateau (a mesa); ``b < 1`` a
    cliff at the foot, ``b > 1`` a feathered one.
    """

    if t >= 1.0:
        return 0.0
    if t <= 0.0:
        return 1.0
    return (1.0 - t**a) ** b


def _pick_archetype(u: float) -> tuple[str, float, float, float, float, int, int]:
    total = 0.0
    for index, weight in enumerate(ARCHETYPE_WEIGHTS):
        total += weight
        if u < total:
            return ARCHETYPES[index]
    return ARCHETYPES[-1]


def _jitter(rng: _Splitmix, value: float, spread: float) -> float:
    return value * rng.uniform(1.0 - spread, 1.0 + spread)


def _clamped_jitter(rng: _Splitmix, value: float, spread: float) -> float:
    """Jitter a flank exponent without letting it cross ``a == 1``.

    ``a <= 1`` is the difference between an apex with slope and an apex without one,
    i.e. between a peak and a dome; it is a property of the archetype, not a number to
    be smeared. A horn or a wedge stays on its own side of the line.
    """

    jittered = _jitter(rng, value, spread)
    if value <= 1.0:
        return min(jittered, 1.0)
    return max(jittered, 1.0 + 1.0e-6)


def _noise_points(seed: int, count: int) -> list[float]:
    rng = _Splitmix(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(count)]


#: Octave point counts for the ridged multifractals. Pairwise coprime, so no two
#: octaves ever line up and the sum has no period.
#: r13: a sixth octave and a heavier tail. Two findings meet here. (1) critic r12's taste
#: note - *"the tops read as flat rock plateaus with strata dragged across them; noise on
#: the shoulder rows would make them ridges"*. (2) The repetition measurement: a stock
#: skyline carries broadband roughness from real terrain at every scale down to the march
#: step, and that roughness is the DENOMINATOR of ``comb_power``. Our analytic crest was
#: smooth below 1 deg, so whatever variance the massif tier carried was a larger share of
#: a smaller total, and the cell read high for a reason that has nothing to do with
#: repetition. 853 keeps the pairwise-coprime property (it is prime), so the sum still has
#: no period.
CREST_OCTAVES: tuple[int, ...] = (25, 51, 103, 211, 421, 853)
CREST_AMPLITUDES: tuple[float, ...] = (1.0, 0.54, 0.29, 0.16, 0.085, 0.048)
#: 5 and 9 points around the circle: features 40-90 deg wide, the scale a real range
#: is high on and then low on.
BACKBONE_OCTAVES: tuple[int, ...] = (5, 9, 17)
BACKBONE_AMPLITUDES: tuple[float, ...] = (1.0, 0.42, 0.19)
RIDGE_GAIN = 1.9
#: What the great-range envelope multiplies a massif's amplitude by, low end and span:
#: a summit on the high shoulder of a range is over three times the one out on its toe.
#: r13: 0.38/1.28 -> 0.32/1.50, i.e. a 4.4x spread across the envelope becomes 5.7x. All
#: seven stock ranges put their dominant angular harmonic at **k = 4** - a real range's
#: variance lives at the 90 deg scale, the scale of "high here, low over there". r12 sat
#: at k = 15 and r13's first clustered draft moved it to k = 7 while RAISING its share of
#: the variance to 0.137. Deepening the great-range envelope's grip on summit height is
#: the honest way to move variance DOWN in frequency: it does not raise a single col, so
#: the world stays closed, and it does not touch the ceiling, because it only ever scales
#: a summit that is already inside it.
RANGE_GAIN_LO, RANGE_GAIN_SPAN = 0.32, 1.50

# --- r13: the MASSIF GROUP (the user's own footage; critic r12 "the player") ----------
#: **The tier r7-r12 did not have, and the reason the skyline read as shark teeth.**
#: r7 built three scales - a 90-120 deg great wall, a 40-90 deg backbone and a 3.6-7.4 deg
#: summit - and placed the summits as a JITTERED PARTITION of the circle: 24 of them at a
#: 15.0 deg step with +-3.6 deg of jitter. Measured against the same seven stock BeamNG
#: ranges r7 scored (``b1/r13/probe/repetition.py``), that put the dominant angular
#: harmonic of our skyline at **k = 15** where all seven stock ranges sit at **k = 4**,
#: 25 prominent peaks round the circle where stock carries 4-8, and a peak-prominence
#: spread of **0.61** against a stock band of **1.03-1.30**. A picket fence, by
#: construction, at exactly the scale the eye reads.
#:
#: A real range does not space its summits evenly. It CLUSTERS them: three to five tops on
#: one massif, the cols between them staying at half the summit height because they are on
#: the massif's own shoulder, and then a real gap - a pass, a valley - to the next massif.
#: These constants build that. ``_summits`` now draws GROUPS, gives each group its own
#: amplitude, hangs its members off an unequal internal walk, and stands the whole group
#: on a broad SHOULDER whose amplitude is taken OUT OF the members' rather than added to
#: them, so the crest keeps its ceiling and the cols inside a massif rise.
GROUP_SIZE_LO, GROUP_SIZE_HI = 2, 5
#: How much of its own share of the circle a group's members may occupy. Below 1 the
#: members huddle and the gap between groups opens; this single number IS the difference
#: between a comb and a range.
GROUP_HUDDLE = 0.46
#: How hard the great-range envelope packs the groups onto its own high sections. A slot
#: is scaled by ``RANGE_PACKING_CEILING - _range01``, so a group over the top of a great
#: range takes ``ceiling - 1`` of the width one out on its toe takes. At 1.55 that is a
#: factor of 2.8; at infinity the packing vanishes and the groups float free of the tier
#: below them, which is the r7 defect one tier up.
#: r13 measured 1.55 (hard), 1.90 and 2.60 (soft). Hard packing emptied the 170-260 deg
#: arc and moved ``comb_power`` by less than the eye-to-eye spread of the cell itself
#: (0.164 -> 0.151 -> 0.172), so the packing is kept SOFT: it tilts the massifs toward
#: the great ranges without being allowed to gut a quadrant, and the coverage invariant
#: below - not this number - is what guarantees the world is worth looking at everywhere.
RANGE_PACKING_CEILING = 2.60
#: **The world is a RING, and that is the one way it is not a landscape.** A stock level
#: may be flat over a quadrant because the player is looking away from the mountains; a
#: 360 deg enclosure that is flat over a quadrant has a hole in it. At
#: ``RANGE_PACKING_CEILING`` 1.55 with uncapped slots, the packing emptied the whole
#: 170-260 deg arc - the ``f10`` bearing of the user's own footage - into a 50 deg run of
#: low crest with nothing standing in it, which reads worse than the teeth it replaced.
#: Every slot is therefore clamped to this band around the mean slot AFTER the range
#: reweighting, so the largest gap between two massifs is bounded and the packing shapes
#: the range instead of gutting it.
GROUP_SLOT_LO, GROUP_SLOT_HI = 0.58, 1.70
#: A GROUP's total height is drawn log-uniformly over the ring's own amplitude band
#: WIDENED at both ends by these factors. r7 drew each summit independently over
#: ``amp_lo..amp_hi`` - a 3.1x spread - and that is why the peak-prominence spread came
#: out at 0.61 against a stock band of 1.03-1.30. Widening the band to 5.5x at the GROUP
#: level (so a whole massif is small or large, not one tooth in a row of equal teeth) is
#: what moves that cell. The high factor stays just OVER 1.0 rather than well over it,
#: because the ceiling is not a tuning parameter: an amplitude that runs past ``H_MAX``
#: is caught by ``_headroom_scale`` and paid for by every summit in the ring. The first
#: draft used an independent multiplicative gain on top of the band draw and squeezed the
#: mid ring's headroom to **0.6663** - a third of its relief spent on one stack.
GROUP_SPREAD_LO, GROUP_SPREAD_HI = 0.55, 1.02
#: A subsidiary top as a fraction of its group's own summit, nearest and furthest.
SUBSIDIARY_HI, SUBSIDIARY_LO = 0.82, 0.36
#: The SHOULDER's share of the group's height, and its half-width as a multiple of the
#: group's own half-extent. The share is TAKEN FROM the members, never added.
#: 0.40-0.70 was the first draft and it over-corrected: the summits sank into their own
#: base and the A/B strip showed one broad dome where a picket had been - the razor-mesa
#: failure this module already names, arrived at from the other side. A shoulder should
#: raise the COLS, not swallow the tops.
SHOULDER_SHARE_LO, SHOULDER_SHARE_HI = 0.38, 0.66
SHOULDER_WIDTH_LO, SHOULDER_WIDTH_HI = 1.10, 1.75
#: The shoulder is a BASE, not a peak: a smooth apex (a > 1) with a fairly abrupt foot
#: (b < 1), so it carries summits without becoming one and does not smear into its
#: neighbour. It is the only place in this module where a dome is the correct object.
SHOULDER_A, SHOULDER_B = 1.85, 0.88
#: Log-uniform spread on every summit's width, so the range holds broad shoulders and
#: narrow horns side by side rather than one width scaled by amplitude.
#: ``exp(+-0.62)`` is a factor of 1.86 either way.
WIDTH_SPREAD = 0.62


def _ridged(octaves: list[list[float]], amplitudes: tuple[float, ...], t: float) -> float:
    """Periodic Musgrave ridged multifractal in ``t`` over [0, 1).

    ``(1 - |noise|)**2`` folds the noise about zero, so where smooth noise has a
    rounded extremum this has a CREASE; the multifractal weight then lets an octave
    add detail only where the octave below it is already high, which is why a real
    range is rough on its ridges and smooth in its basins. This is the whole
    difference between r2's ``crenellation`` and an outline that reads as rock.
    """

    result = 0.0
    weight = 1.0
    for points, amplitude in zip(octaves, amplitudes, strict=True):
        signal = 1.0 - abs(_catmull(points, t))
        signal = signal * signal * weight
        weight = min(max(signal * RIDGE_GAIN, 0.0), 1.0)
        result += signal * amplitude
    return result


def _normalised_ridged(
    octaves: list[list[float]], amplitudes: tuple[float, ...], samples: int
) -> tuple[float, float]:
    """(offset, scale) mapping ``_ridged`` onto [0, 1] over the whole circle."""

    values = [_ridged(octaves, amplitudes, i / samples) for i in range(samples)]
    low, high = min(values), max(values)
    return low, 1.0 / max(high - low, 1e-9)


_CREST_NOISE = {
    spec.name: [
        _noise_points(spec.seed ^ (0x51DE + 0x1D * i), n) for i, n in enumerate(CREST_OCTAVES)
    ]
    for spec in RINGS
}
_BACKBONE_NOISE = {
    spec.name: [
        _noise_points(spec.seed ^ (0x8B0E + 0x1D * i), n) for i, n in enumerate(BACKBONE_OCTAVES)
    ]
    for spec in RINGS
}
_RADIUS_NOISE = {spec.name: _noise_points(spec.seed ^ 0x2AD1, 9) for spec in RINGS}
_CREST_NORM = {
    spec.name: _normalised_ridged(_CREST_NOISE[spec.name], CREST_AMPLITUDES, 4096) for spec in RINGS
}
_BACKBONE_NORM = {
    spec.name: _normalised_ridged(_BACKBONE_NOISE[spec.name], BACKBONE_AMPLITUDES, 4096)
    for spec in RINGS
}


def _backbone01(spec: RingSpec, bearing_deg: float) -> float:
    """The range's own long undulation at this bearing, on [0, 1]."""

    low, span = _BACKBONE_NORM[spec.name]
    t = (bearing_deg % 360.0) / 360.0
    return (_ridged(_BACKBONE_NOISE[spec.name], BACKBONE_AMPLITUDES, t) - low) * span


def _range_walls(spec: RingSpec) -> list[Massif]:
    """The ring's GREAT RANGES: 3-4 walls, 37.7-115.6 deg of half-width per side.

    **The tier r2 never had, and the one ``ridge_shape.py`` found missing.** r2 spread
    24 independent cones evenly round the circle, which put 66 % of the ring's variance
    below a 12 deg window (``angular_roughness`` 0.663) where the seven stock terrains
    put 8-16 %: a real skyline is a CONTINUOUS WALL for a hundred degrees - the Sierra
    from Owens Valley, the Inyos opposite it - that rises and falls by a third of its
    height and carries its summits on top. These are that wall: broad, low-exponent,
    asymmetric, compact-support shapes that the massifs then stand on, and whose
    normalised height also scales each massif so summits are tall on the high sections
    and stubby on the low ones.
    """

    rng = _Splitmix(spec.seed ^ 0x9A11)
    step = 360.0 / spec.range_walls
    out: list[Massif] = []
    for index in range(spec.range_walls):
        bearing = ((index + 0.5 + rng.uniform(-0.20, 0.20)) * step) % 360.0
        amplitude = spec.range_m * rng.uniform(0.52, 1.0)
        wide = rng.uniform(0.62, 1.05) * step
        narrow = wide * rng.uniform(0.52, 0.86)
        steep_is_pos = _angdiff(WIND_BEARING, bearing) < 0.0
        pos_w, neg_w = (narrow, wide) if steep_is_pos else (wide, narrow)
        out.append(
            Massif(
                bearing,
                amplitude,
                "range",
                neg_w,
                _jitter(rng, 1.75, 0.20),
                _jitter(rng, 1.05, 0.18),
                pos_w,
                _jitter(rng, 1.55, 0.20),
                _jitter(rng, 1.20, 0.18),
            )
        )
    return out


def _raw_range_sum(spec: RingSpec, bearing_deg: float) -> float:
    height = 0.0
    for m in _RANGES[spec.name]:
        delta = _angdiff(bearing_deg, m.bearing)
        if delta < 0.0:
            if -delta < m.w_neg:
                height += m.amplitude * _flank(-delta / m.w_neg, m.a_neg, m.b_neg)
        elif delta < m.w_pos:
            height += m.amplitude * _flank(delta / m.w_pos, m.a_pos, m.b_pos)
    return height


def _range01(spec: RingSpec, bearing_deg: float) -> float:
    """The great-range envelope at this bearing, normalised onto [0, 1].

    Normalising the SUM rather than each wall is what keeps two overlapping ranges from
    stacking into a plateau taller than either: the envelope spans exactly
    ``0..spec.range_m`` however many walls happen to meet at a bearing.
    """

    low, span = _RANGE_NORM[spec.name]
    return (_raw_range_sum(spec, bearing_deg) - low) * span


def _range_sum(spec: RingSpec, bearing_deg: float) -> float:
    return spec.range_m * _range01(spec, bearing_deg)


def _log_spread(rng: _Splitmix, spread: float) -> float:
    """``exp(U(-spread, spread))`` - a multiplicative jitter with a real tail.

    A uniform jitter on a width is symmetric in metres and therefore skewed in RATIO:
    ``U(0.5, 1.5)`` makes "half as wide" and "twice as wide" different-sized events. A
    log-uniform one is symmetric in ratio, which is what "no two peaks alike" means for
    a quantity that is a scale.
    """

    return math.exp(rng.uniform(-spread, spread))


def _group_plan(spec: RingSpec, rng: _Splitmix) -> list[int]:
    """The group sizes, summing to exactly ``spec.summits``.

    Exactness matters: design 2.6 fixes the near ring's AUTHORED summit count at 24 and
    the static gate asserts it, so the clustering may change where the summits stand and
    never how many there are. A leftover of one is folded into the group before it rather
    than stranded, because a lone summit between two gaps is the picket this tier exists
    to remove.
    """

    sizes: list[int] = []
    remaining = spec.summits
    while remaining > 0:
        size = GROUP_SIZE_LO + int(rng.random() * (GROUP_SIZE_HI - GROUP_SIZE_LO + 1))
        size = min(size, remaining)
        if remaining - size == 1 and size < GROUP_SIZE_HI:
            size += 1
        sizes.append(size)
        remaining -= size
    return sizes


def _summits(spec: RingSpec) -> tuple[list[Massif], list[Massif], list[Massif]]:
    """(massifs, spurs, shoulders) for one ring - seeded, CLUSTERED, shaped per summit.

    **r13.** Through r12 the bearings were a jittered partition of the circle:
    ``((index + 0.5 + U(-0.24, 0.24)) * 360 / summits)``. That is a comb with a little
    rattle in it, and ``b1/r13/probe/repetition.py`` measured exactly that - the dominant
    harmonic at k = 15 against a stock band that is k = 4 on all seven levels, 25
    prominent peaks against stock's 4-8, peak-prominence spread 0.61 against 1.03-1.30.
    The per-peak SHAPE work of r7-r12 is untouched and was never the defect: every
    archetype, every flank exponent, every spur and every notch below is r7's. What
    changes is the PLAN.

    A ring is now drawn as MASSIF GROUPS:

    * ``_group_plan`` splits ``spec.summits`` into groups of 2-5, so the authored count
      is exact and design 2.6's 24 survives;
    * each group takes a jittered slot on a MUCH coarser step (``360 / groups``) and
      huddles its members into ``GROUP_HUDDLE`` of it, which opens a real pass between
      one massif and the next - the long gaps a comb does not have;
    * the members walk across the group on UNEQUAL gaps (drawn 0.55-1.45 and normalised),
      so the spacing is irregular inside a group as well as between groups;
    * one member, chosen at random rather than the middle one, is the group's SUMMIT; the
      others fall away from it with distance, which is what a massif looks like;
    * the group draws its own log-uniform ``GROUP_GAIN``, so one massif is nearly three
      times the massif beside it - this is the cell that was 0.61 against a 1.03 floor;
    * a **SHOULDER** - a broad, smooth-apexed, abrupt-footed Massif spanning the group -
      takes ``SHOULDER_SHARE`` of the group's height OUT OF its members. It is the tier
      that turns a picket into a wall: inside a massif the cols now stand at 0.40-0.70 of
      the summit because they are on its own shoulder, while between massifs the crest
      falls to the great-range envelope;
    * a member's STEEP side faces AWAY from its group's summit (the ridge that connects
      it to the summit is the gentle side, the drop into the pass is the steep one), so
      the lean reverses several times inside one 90 deg view instead of once per
      revolution as ``WIND_BEARING`` alone made it. The wind still decides the SUMMIT's
      own lean and still reverses on a seeded one in six.
    """

    rng = _Splitmix(spec.seed)
    massifs: list[Massif] = []
    spurs: list[Massif] = []
    shoulders: list[Massif] = []
    #: (bearing, amplitude, steep_is_pos or None to use the wind rule)
    plan: list[tuple[float, float, bool | None]] = []
    sizes = _group_plan(spec, rng)
    # r13, second pass: the GROUPS are placed on an unequal walk too, not on a partition
    # of their own. The first draft anchored them at ``(index + 0.5 + U(-0.30, 0.30)) *
    # 360 / groups`` and simply moved the comb one tier up: measured, the dominant
    # harmonic went from k = 15 to k = 7 and its share of the variance ROSE from 0.079 to
    # 0.137, out the top of a stock band of 0.010-0.093. A partition with jitter is a comb
    # however coarse it is. Drawing the gaps and normalising them onto the circle leaves
    # no preferred angular frequency anywhere in the plan.
    slots = [rng.uniform(0.42, 1.72) for _ in sizes]
    origin = rng.uniform(0.0, 360.0)

    def _walk(widths: list[float]) -> tuple[list[float], list[float]]:
        run = sum(widths)
        centres: list[float] = []
        extents: list[float] = []
        walked = 0.0
        for width in widths:
            centres.append((origin + 360.0 * (walked + 0.5 * width) / run) % 360.0)
            extents.append(360.0 * width / run)
            walked += width
        return centres, extents

    # r13, third pass: the groups are PULLED ONTO THE GREAT RANGES. A walk with drawn
    # gaps removed the comb's regularity but left the group tier floating free of the
    # 90-120 deg tier below it, so the skyline carried an independent bump at the group
    # frequency: measured, 0.164 of the variance at k = 8 against a stock ceiling of
    # 0.093. Massifs in a real range are not scattered at random over it - they crowd the
    # high sections and thin out over the passes, which is the same statement as "the
    # range's own long wavelength is where its variance lives", and all seven stock
    # levels put their strongest harmonic at k = 4 for exactly that reason. Reweighting
    # each slot by ``1 - _range01`` at its own provisional bearing packs the groups onto
    # the high shoulders and opens the low sections, so the two tiers reinforce ONE
    # frequency instead of adding two.
    provisional, _ = _walk(slots)
    slots = [
        slot * (RANGE_PACKING_CEILING - _range01(spec, bearing))
        for slot, bearing in zip(slots, provisional, strict=True)
    ]
    mean_slot = sum(slots) / len(slots)
    slots = [min(max(slot, GROUP_SLOT_LO * mean_slot), GROUP_SLOT_HI * mean_slot) for slot in slots]
    anchors, spans = _walk(slots)
    for index, size in enumerate(sizes):
        anchor = anchors[index]
        # r13: the HUDDLE varies per group as well. Some massifs sprawl across most of
        # their slot (a range section, summits shoulder to shoulder); others draw into a
        # tight knot with open ground either side (an isolated massif). One fixed huddle
        # made every group the same object at a different scale - the r7 defect one tier
        # up. Capped at 0.44 of the slot so no group's members reach into its neighbour.
        half_span = min(
            0.5 * GROUP_HUDDLE * spans[index] * rng.uniform(0.62, 1.44),
            0.44 * spans[index],
        )
        low = spec.amp_lo * GROUP_SPREAD_LO
        high = spec.amp_hi * GROUP_SPREAD_HI
        total = low * (high / low) ** rng.random()
        share = rng.uniform(SHOULDER_SHARE_LO, SHOULDER_SHARE_HI)
        # an UNEQUAL walk across the group: gaps drawn, then normalised onto the span
        gaps = [rng.uniform(0.55, 1.45) for _ in range(max(size - 1, 1))]
        run = sum(gaps) if size > 1 else 1.0
        offsets: list[float] = []
        walked = 0.0
        for step_index in range(size):
            if step_index:
                walked += gaps[step_index - 1]
            offsets.append((-1.0 + 2.0 * walked / run) * half_span if size > 1 else 0.0)
        head = int(rng.random() * size)
        for member, offset in enumerate(offsets):
            bearing = (anchor + offset) % 360.0
            reach = abs(member - head) / max(size - 1, 1)
            span = SUBSIDIARY_HI - SUBSIDIARY_LO
            fall = 1.0 if member == head else SUBSIDIARY_HI - span * reach
            amplitude = total * (1.0 - share) * _jitter(rng, fall, 0.12)
            # r7: the RANGE's own long wavelength. A real skyline is high for 40-90 deg and
            # then low for 40-90 deg; r2 spread 24 summits of independent height evenly round
            # the circle, which put essentially all of the ring's variance at one angular
            # scale (measured: angular_roughness 0.663 against a stock band of 0.078-0.152).
            # Scaling each massif by the backbone AT ITS OWN BEARING moves variance up to
            # 40-90 deg without lowering a single saddle, so the world stays closed.
            amplitude *= RANGE_GAIN_LO + RANGE_GAIN_SPAN * _range01(spec, bearing)
            if spec.name == "near" and abs(_angdiff(bearing, NOTCH_BEARING)) < 13.0:
                # the outlet notch: the near crest steps back so the far ring shows through
                amplitude *= 0.36
            lean = None if member == head else offsets[member] >= offsets[head]
            plan.append((bearing, amplitude, lean))
        # the SHOULDER the group stands on, centred on the group's own centre of mass
        centre = (anchor + sum(offsets) / size) % 360.0
        shoulder_amplitude = total * share
        shoulder_amplitude *= RANGE_GAIN_LO + RANGE_GAIN_SPAN * _range01(spec, centre)
        if spec.name == "near" and abs(_angdiff(centre, NOTCH_BEARING)) < 13.0:
            shoulder_amplitude *= 0.36
        wide = max(half_span, 1.0) * rng.uniform(SHOULDER_WIDTH_LO, SHOULDER_WIDTH_HI)
        narrow = wide * rng.uniform(0.58, 0.90)
        steep_is_pos = _angdiff(WIND_BEARING, centre) < 0.0
        pos_w, neg_w = (narrow, wide) if steep_is_pos else (wide, narrow)
        shoulders.append(
            Massif(
                centre,
                shoulder_amplitude,
                "shoulder",
                neg_w,
                _jitter(rng, SHOULDER_A, 0.18),
                _jitter(rng, SHOULDER_B, 0.16),
                pos_w,
                _jitter(rng, SHOULDER_A, 0.18),
                _jitter(rng, SHOULDER_B, 0.16),
            )
        )
    if spec.name == "far":
        # the two farther, taller peaks the S1 frame sees through the notch. r7 lowers
        # them from 0.98/0.90 of amp_hi: at r6's amplitudes one of them overlapped a
        # regular massif and the sum ran 71 m PAST H_MAX, which the clamp would have
        # turned into 40 columns of dead-flat crest - a razor mesa, the one silhouette
        # defect worse than a dome. r13 leaves them standing ALONE, with no shoulder:
        # two isolated far summits seen through a pass is the picture, and a shoulder
        # under them would fill the pass they are seen through.
        plan.append(((NOTCH_BEARING + 7.0) % 360.0, spec.amp_hi * 0.74, None))
        plan.append(((NOTCH_BEARING - 7.0) % 360.0, spec.amp_hi * 0.68, None))
    for bearing, amplitude, lean in plan:
        name, a_steep, b_steep, a_gentle, b_gentle, spur_lo, spur_hi = _pick_archetype(rng.random())
        # r13: a subsidiary top leans away from its group's summit; the summit itself
        # keeps r7's rule - the steep side faces AWAY from the wind, reversed on a
        # seeded one in six.
        if lean is None:
            steep_is_pos = _angdiff(WIND_BEARING, bearing) < 0.0
            if rng.random() < 1.0 / 6.0:
                steep_is_pos = not steep_is_pos
        else:
            steep_is_pos = lean
            if rng.random() < 1.0 / 8.0:
                steep_is_pos = not steep_is_pos
        # r13: the width is keyed to the member's share of a GROUP's height (the members
        # are smaller than r7's independent summits by ``1 - share``, so keying to
        # ``amp_hi`` as r7 did would have made every summit narrower as well as the same
        # width), and carries a log-uniform spread of its own.
        size_ratio = min(amplitude / max(spec.amp_hi * (1.0 - SHOULDER_SHARE_LO), 1.0e-6), 1.7)
        base_w = rng.uniform(3.6, 7.4) * (0.62 + 0.55 * size_ratio) * _log_spread(rng, WIDTH_SPREAD)
        steep_w = base_w * rng.uniform(0.46, 0.72)
        gentle_w = base_w * rng.uniform(1.02, 1.44)
        # jitter never crosses a == 1: that boundary IS the archetype. Above it the apex
        # slope is zero and the summit is a dome however the other five numbers fall, so
        # a jittered horn or wedge that landed at 1.04 would quietly stop being one.
        shape_steep = (
            steep_w,
            _clamped_jitter(rng, a_steep, 0.16),
            _jitter(rng, b_steep, 0.14),
        )
        shape_gentle = (
            gentle_w,
            _clamped_jitter(rng, a_gentle, 0.16),
            _jitter(rng, b_gentle, 0.14),
        )
        pos, neg = (shape_steep, shape_gentle) if steep_is_pos else (shape_gentle, shape_steep)
        massif = Massif(bearing, amplitude, name, neg[0], neg[1], neg[2], pos[0], pos[1], pos[2])
        massifs.append(massif)
        for _ in range(spur_lo + int(rng.random() * (spur_hi - spur_lo + 1))):
            side = 1.0 if rng.random() < 0.5 else -1.0
            parent_w = massif.w_pos if side > 0 else massif.w_neg
            # r7: 0.42-1.02 kept every spur INSIDE the massif's own support, where it
            # only rounds the flank; a real range has subsidiary summits standing off
            # the parent past its own foot, separated by a col. Half of them now do.
            offset = side * parent_w * rng.uniform(0.44, 1.62)
            spur_w = parent_w * rng.uniform(0.20, 0.52)
            fraction = rng.uniform(0.18, 0.62)
            # a spur is a shoulder, so it is sharper than the massif that carries it
            spur_a = rng.uniform(0.80, 1.30)
            spur_b = rng.uniform(0.62, 1.05)
            spurs.append(
                Massif(
                    (bearing + offset) % 360.0,
                    amplitude * fraction,
                    f"{name}_spur",
                    spur_w * rng.uniform(0.82, 1.18),
                    spur_a,
                    spur_b,
                    spur_w * rng.uniform(0.82, 1.18),
                    _jitter(rng, spur_a, 0.22),
                    _jitter(rng, spur_b, 0.22),
                )
            )
    return massifs, spurs, shoulders


#: Headroom kept under ``H_MAX`` so no summit is ever cut off flat by the clamp.
CREST_HEADROOM_M = 5.0

#: r15 (critic r13 B13-2, carried through r14 and spent here). **THE ENVELOPE.**
#:
#: r13 gathered the picket of teeth into massifs, which is the fix every critic since r6
#: had asked for. It also cost the range **29-30 % of its median 45 deg window relief**,
#: and r14 measured what that loss is actually made of: the range's own span fell from
#: 288.13 m to 249.00 m, which is 93.5 % -> **80.8 %** of the 308 m between the design's
#: z 332 visible floor and its z 640 ceiling. **Thirteen and a half per cent of the
#: envelope is simply unused**, and the rest (-18.0 %) IS the fix - a range gathered into
#: massifs has 45 deg windows sitting on one massif, where a picket puts several teeth in
#: every window, so the picket's high window relief was a symptom.
#:
#: This is the lever that spends it, and its whole virtue is that it CANNOT buy the picket
#: back. Every published repetition cell - ``peak_asym_cv``, prominence and spacing
#: coefficients of variation, half-prominence width spreads, band shares of AC variance -
#: is either a coefficient of variation of the crest's AC or a share of its variance, and
#: **all of those are invariant under a uniform AC gain by construction**. So this can only
#: make the range taller, never more repetitive; r15's re-derivation prints both halves
#: side by side to show that it did exactly that.
#:
#: It multiplies the ring's whole profile about the ring's own reference level
#: (``_BARE_MEAN``), so it is a gain on the crest's alternating component and not on its
#: mean. Everything downstream prices it: ``_headroom_scale`` sees the gained peak and
#: scales the massifs if the ceiling binds, ``_notches`` picks its candidates above the
#: gained 55th percentile, and ``_close_the_world`` enforces the z 332 visible floor on the
#: gained crest.
#:
#: **r14 named the wrong wall, and the sweep found it.** r14 wrote that the binding
#: constraint is the z 332 visible floor and that the ceiling had *"42.5 m spare at k = 1"*.
#: 42.5 m is ``H_MAX`` minus the VISIBLE crest maximum (640 - 597.456), and neither of those
#: is the constraint the module actually enforces: ``_headroom_scale`` measures the BARE
#: peak of ALL THREE RINGS - a ring hidden behind another one still has to fit - against
#: ``H_MAX - CREST_HEADROOM_M``. That peak is **605.40 m at k = 1**, so the real spare is
#: **29.60 m**, and it runs out at **k = 1.133**. The floor never binds at all in that
#: range: the visible crest minimum only falls from 348.45 to 347.83 (`envelope.json`,
#: 0 bearings under 332 at every k up to 1.30). So the recoverable envelope is smaller than
#: r14 priced it, and the number that was carried for a revision was carried against the
#: wrong wall.
#:
#: **k = 1.13**, with 0.61 m of ceiling to spare. It takes the visible crest's span from
#: 249.00 m to **277.58 m - 80.8 % to 90.1 %** of the 308 m the design allows, which is
#: nine of the thirteen points r13 left on the table and all of the points that were ever
#: there to take.
CREST_GAIN = 1.13

# --- r13: the coverage invariant ------------------------------------------------------
#: **The one way a 360 deg ring is not a landscape.** A stock level may be flat over a
#: quadrant, because the player is looking away from the mountains and there is somewhere
#: else to look. A ring that is flat over a quadrant has a HOLE in the world: turn that
#: way and there is nothing. The clustering this revision introduces makes that failure
#: reachable for the first time - r12's uniform partition could not produce a dead arc
#: because it could not produce a live one either - and the first clustered draft did
#: produce it: a 50 deg run over the ``f10`` bearing of the user's own footage with 20 m
#: of visible relief in it, which reads worse than the teeth it replaced.
#:
#: ``_stand_in_every_quarter`` is the repair, built in the shape of ``_close_the_world``
#: and printed the same way: on a fixed grid, any window whose VISIBLE crest (the max
#: apparent elevation over the three rings, which is what a player sees) spans less than
#: ``RELIEF_MIN_SPAN_M`` has its tallest contributor lifted by ``RELIEF_LIFT``, and the
#: sweep repeats until every window clears or the pass budget is spent. The pass count is
#: published in ``silhouette_summary`` exactly as ``notch_repair_passes`` is, so a reader
#: can see whether the invariant was structural or merely lucky.
RELIEF_WINDOW_DEG = 45.0
RELIEF_MIN_SPAN_M = 74.0
RELIEF_GRID = 720
RELIEF_LIFT = 1.09
RELIEF_MAX_PASSES = 200

_RANGES: dict[str, list[Massif]] = {}
_RANGE_NORM: dict[str, tuple[float, float]] = dict.fromkeys(
    (spec.name for spec in RINGS), (0.0, 1.0)
)
for _spec in RINGS:
    _RANGES[_spec.name] = _range_walls(_spec)
for _spec in RINGS:
    _values = [_raw_range_sum(_spec, 360.0 * i / 2048) for i in range(2048)]
    _RANGE_NORM[_spec.name] = (min(_values), 1.0 / max(max(_values) - min(_values), 1e-9))

_SUMMITS: dict[str, list[Massif]] = {}
_SPURS: dict[str, list[Massif]] = {}
#: r13: the massif-group shoulders. See ``_summits``.
_SHOULDERS: dict[str, list[Massif]] = {}
for _spec in RINGS:
    _SUMMITS[_spec.name], _SPURS[_spec.name], _SHOULDERS[_spec.name] = _summits(_spec)


def _visible_bare(bearing_deg: float) -> float:
    """The crest a basin eye sees at this bearing, BEFORE headroom and notches.

    Used only by ``_stand_in_every_quarter``, which runs before either exists.
    """

    best, best_elev = 0.0, -math.inf
    for spec in RINGS:
        top = _bare_profile(spec, bearing_deg, scale=1.0)
        # the NOMINAL radius, not ``_radius``: the swing is 15-26 m on 1,180-1,382 and
        # ``_radius`` is not defined until after the notches. Which ring is in front is a
        # question the 100-200 m radius SEPARATION answers; a 2 % wobble cannot change it.
        elevation = math.atan2(top - EYE_Z, spec.radius_m)
        if elevation > best_elev:
            best, best_elev = top, elevation
    return best


def _stand_in_every_quarter() -> int:
    """Lift the tallest contributor in any window the visible crest goes flat over.

    Returns the number of passes spent. Mutates ``_SUMMITS`` / ``_SHOULDERS`` in place,
    which is why it runs here - between the draw and ``_headroom_scale``, so the ceiling
    accounts for whatever this adds rather than being asserted against a crest that then
    grows under it.
    """

    window = max(1, round(RELIEF_WINDOW_DEG / 360.0 * RELIEF_GRID))
    for passes in range(1, RELIEF_MAX_PASSES + 1):
        heights = [_visible_bare(360.0 * i / RELIEF_GRID) for i in range(RELIEF_GRID)]
        worst_span, worst_at = math.inf, 0
        for start in range(RELIEF_GRID):
            arc = [heights[(start + k) % RELIEF_GRID] for k in range(window)]
            span = max(arc) - min(arc)
            if span < worst_span:
                worst_span, worst_at = span, start
        if worst_span >= RELIEF_MIN_SPAN_M:
            return passes
        centre = 360.0 * (worst_at + window / 2.0) / RELIEF_GRID
        best: tuple[float, str, str, int] | None = None
        for spec in RINGS:
            for kind, rows in (("summit", _SUMMITS), ("shoulder", _SHOULDERS)):
                for index, m in enumerate(rows[spec.name]):
                    if abs(_angdiff(m.bearing, centre)) > RELIEF_WINDOW_DEG / 2.0:
                        continue
                    key = (-m.amplitude, spec.name, kind, index)
                    if best is None or key < best:
                        best = key
        if best is None:
            return passes
        _, name, kind, index = best
        rows = _SUMMITS if kind == "summit" else _SHOULDERS
        old = rows[name][index]
        rows[name][index] = Massif(
            old.bearing,
            old.amplitude * RELIEF_LIFT,
            old.archetype,
            old.w_neg,
            old.a_neg,
            old.b_neg,
            old.w_pos,
            old.a_pos,
            old.b_pos,
        )
    return RELIEF_MAX_PASSES


def _massif_sum(spec: RingSpec, bearing_deg: float, scale: float) -> float:
    """Every massif, spur and shoulder of one ring at one bearing. Compact support."""

    height = 0.0
    for group in (_SUMMITS[spec.name], _SPURS[spec.name], _SHOULDERS[spec.name]):
        for m in group:
            delta = _angdiff(bearing_deg, m.bearing)
            if delta < 0.0:
                if -delta >= m.w_neg:
                    continue
                height += m.amplitude * _flank(-delta / m.w_neg, m.a_neg, m.b_neg)
            else:
                if delta >= m.w_pos:
                    continue
                height += m.amplitude * _flank(delta / m.w_pos, m.a_pos, m.b_pos)
    return height * scale


#: The ring's own reference level, measured once at unit gain: the mean of the bare crest
#: over ``CREST_MEAN_GRID`` bearings. ``CREST_GAIN`` scales the profile's departure from
#: THIS, so the gain is a pure AC gain and the ring's mean height is untouched. It is empty
#: while the module is still importing - which is exactly the state the reference itself
#: has to be measured in, and ``_bare_profile`` says so below.
_BARE_MEAN: dict[str, float] = {}
CREST_MEAN_GRID = 8192


def _bare_profile(
    spec: RingSpec, bearing_deg: float, scale: float | None = None, gain: float | None = None
) -> float:
    """The ring's crest BEFORE its notches are cut - massifs, spurs, backbone, crest."""

    if scale is None:
        scale = _HEADROOM[spec.name]
    height = spec.base_z + _range_sum(spec, bearing_deg) + _massif_sum(spec, bearing_deg, scale)
    t = (bearing_deg % 360.0) / 360.0
    height += spec.backbone_m * _backbone01(spec, bearing_deg)
    low, span = _CREST_NORM[spec.name]
    height += spec.crest_m * (_ridged(_CREST_NOISE[spec.name], CREST_AMPLITUDES, t) - low) * span
    # r15 / B13-2, the envelope. ``CREST_GAIN`` is read as a module global at CALL time, so
    # ``r15/probe/envelope.py`` can sweep the lever against a fixed set of massifs, notches
    # and repairs - a controlled sweep of one variable, which is the only honest way to
    # choose it. Before ``_BARE_MEAN`` is measured the profile is its own ungained self,
    # which is the state the reference level must be measured in.
    reference = _BARE_MEAN.get(spec.name)
    gain = CREST_GAIN if gain is None else gain
    if gain != 1.0 and reference is not None:
        height = reference + gain * (height - reference)
    return height


def _headroom_scale(spec: RingSpec) -> float:
    """A single per-ring amplitude scale that keeps the bare crest under ``H_MAX``.

    The clamp in ``ring_profile`` is a safety net, not a shaping tool: a summit it
    catches comes out dead flat on top. Two overlapping massifs can sum past the top,
    so each ring's massifs and spurs are scaled ONCE, uniformly, by whatever it takes
    to keep the bare crest ``CREST_HEADROOM_M`` under ``H_MAX``. ``1.0`` means the
    ring was already inside and nothing was touched - which is the case for all three
    as shipped; ``silhouette_summary`` prints the factor either way.
    """

    peak = max(_bare_profile(spec, 360.0 * i / 8192, scale=1.0) for i in range(8192))
    ceiling = H_MAX - CREST_HEADROOM_M
    if peak <= ceiling:
        return 1.0
    # r15: ``CREST_GAIN`` multiplies EVERY term of the profile, the massif sum included, so
    # the part of the peak that scaling the massifs can move is ``gain x massif_sum``. With
    # the gain at 1.0 this is the r13 arithmetic unchanged.
    movable = CREST_GAIN * _massif_sum(spec, _argmax_bearing(spec), scale=1.0)
    return max(0.05, (ceiling - (peak - movable)) / max(movable, 1e-6))


def _argmax_bearing(spec: RingSpec) -> float:
    best, best_h = 0.0, -math.inf
    for i in range(8192):
        bearing = 360.0 * i / 8192
        height = _bare_profile(spec, bearing, scale=1.0)
        if height > best_h:
            best, best_h = bearing, height
    return best


def _notches(spec: RingSpec) -> list[Notch]:
    """Cols cut through the crest, placed only where the crest is actually high.

    A notch in a saddle is invisible; a notch through a skyline is the single most
    legible "this is rock" cue there is. Candidates are drawn seeded, kept only where
    ``_bare_profile`` is above the ring's own 55th percentile and no closer than
    ``2.2 * half_width`` to a notch already taken, so two cols never merge into one
    wide gap.
    """

    grid = 1440
    heights = [_bare_profile(spec, 360.0 * i / grid) for i in range(grid)]
    # NEAREST-RANK 55th percentile by intent, not a linear-interpolated one: this is a
    # threshold on a 1,440-sample sweep, so index 792 IS a sampled crest height and the
    # rule "cut only above it" is exact rather than approximately exact. Declared here
    # because r8's ``order_stats_audit.py`` recomputes it against both conventions and a
    # reader has to be able to tell an intended convention from B7-1's accident.
    threshold = sorted(heights)[int(0.55 * grid)]
    rng = _Splitmix(spec.seed ^ 0xC01)
    taken: list[Notch] = []
    for _ in range(4000):
        if len(taken) >= spec.notches:
            break
        bearing = rng.uniform(0.0, 360.0)
        if heights[int(bearing / 360.0 * grid) % grid] < threshold:
            continue
        half_width = rng.uniform(0.30, 1.35)
        if any(
            abs(_angdiff(bearing, n.bearing)) < 2.2 * (half_width + n.half_width_deg) for n in taken
        ):
            continue
        taken.append(Notch(bearing, rng.uniform(20.0, 78.0), half_width, rng.uniform(0.55, 1.15)))
    return sorted(taken, key=lambda n: n.bearing)


_HEADROOM: dict[str, float] = dict.fromkeys((spec.name for spec in RINGS), 1.0)
#: r13: the coverage repair runs HERE - after ``_bare_profile`` exists and before the
#: ceiling is measured, so ``_headroom_scale`` prices whatever it added instead of being
#: asserted against a crest that then grows under it.
RELIEF_PASSES: int = _stand_in_every_quarter()
#: r15: measured after the coverage repair (which can add a massif) and before the ceiling,
#: at unit gain and unit massif scale, so the reference level is a property of the range's
#: SHAPE and not of either correction that runs over it.
_BARE_MEAN.update(
    {
        spec.name: sum(
            _bare_profile(spec, 360.0 * i / CREST_MEAN_GRID, scale=1.0, gain=1.0)
            for i in range(CREST_MEAN_GRID)
        )
        / CREST_MEAN_GRID
        for spec in RINGS
    }
)
_HEADROOM = {spec.name: _headroom_scale(spec) for spec in RINGS}
_NOTCHES = {spec.name: _notches(spec) for spec in RINGS}

#: How far the visible silhouette must clear design §2.6's z 320 floor after the notches
#: are cut. ``_close_the_world`` shallows notches until it does, so the invariant is
#: STRUCTURAL rather than a property that happened to hold at one sample count.
VISIBLE_MARGIN_M = 12.0
REPAIR_GRID = 4 * COLUMN_SEGMENTS


def _notched(spec: RingSpec, bearing_deg: float, notches: list[Notch]) -> float:
    height = _bare_profile(spec, bearing_deg)
    for notch in notches:
        delta = _angdiff(bearing_deg, notch.bearing)
        if abs(delta) >= notch.half_width_deg:
            continue
        height -= notch.depth_m * _flank(abs(delta) / notch.half_width_deg, 1.0, notch.power)
    return min(max(height, RING_FLOOR_Z), H_MAX)


def _close_the_world(notches: dict[str, list[Notch]]) -> dict[str, list[Notch]]:
    """Shallow any notch that would let the VISIBLE silhouette fall below the floor.

    A col in one ring is only legal while another ring still stands behind it. On a
    4x-oversampled grid, every bearing whose visible ridge falls under
    ``H_MIN + VISIBLE_MARGIN_M`` has the deepest notch covering it reduced by 12 %, and
    the sweep repeats until the floor holds everywhere or 240 passes are spent. It
    converges in a handful; the count is recorded in ``silhouette_summary``.
    """

    current = {name: list(rows) for name, rows in notches.items()}
    floor = H_MIN + VISIBLE_MARGIN_M
    passes = 0
    for passes in range(1, 241):  # noqa: B007 - the loop variable IS the record
        worst: tuple[float, str, int] | None = None
        for index in range(REPAIR_GRID):
            bearing = 360.0 * index / REPAIR_GRID
            tops = [_notched(spec, bearing, current[spec.name]) for spec in RINGS]
            elevations = [
                math.atan2(top - EYE_Z, _radius(spec, bearing))
                for top, spec in zip(tops, RINGS, strict=True)
            ]
            best = max(range(len(RINGS)), key=lambda i: elevations[i])
            if tops[best] >= floor:
                continue
            for ring_index, spec in enumerate(RINGS):
                for notch_index, notch in enumerate(current[spec.name]):
                    if abs(_angdiff(bearing, notch.bearing)) >= notch.half_width_deg:
                        continue
                    key = (tops[best] - notch.depth_m, spec.name, notch_index)
                    if worst is None or key < worst:
                        worst = key
                del ring_index
        if worst is None:
            break
        _, name, notch_index = worst
        old = current[name][notch_index]
        current[name][notch_index] = Notch(
            old.bearing, old.depth_m * 0.88, old.half_width_deg, old.power
        )
    return {name: rows for name, rows in current.items()} | {"_passes": passes}  # type: ignore[dict-item]


def _radius(spec: RingSpec, bearing_deg: float) -> float:
    return min(
        max(
            spec.radius_m
            + spec.radius_swing_m * _catmull(_RADIUS_NOISE[spec.name], bearing_deg / 360.0),
            R_MIN,
        ),
        R_MAX,
    )


_REPAIRED = _close_the_world(_NOTCHES)
REPAIR_PASSES: int = _REPAIRED.pop("_passes")  # type: ignore[assignment]
_NOTCHES = _REPAIRED  # type: ignore[assignment]


# --- B7 (2026-09-16): the crest is a real canyon wall ---------------------------------
#
# Design amendment A4.  Everything above this line still builds the SYNTHETIC skyline --
# ranges, massifs, spurs, crest noise, notches and the repair pass -- and it stays here,
# runs at import and is still what `silhouette_summary()` reports when the GIS source is
# off.  What changed is where the crest comes from: `ericrolph_hot_potato_arena_backdrop_gis.json`
# carries the ground elevation of the Island in the Sky rim above the Shafer benches
# (USGS 3DEP 1 m lidar, public domain), sampled on three circles at this level's own ring
# radii, 1,536 bearings each, in metres above the bowl floor.
#
# The mapping is measured, not tuned (`b7/choose_mapping.py`, `b7/finalise_mapping.py`):
#   * OFFSET pins the COMBINED median crest (the max over the three rings, which is what an
#     eye on the basin floor actually sees) onto the median that ships today, so the basin
#     keeps its enclosure at 15.76 deg while the SHAPE becomes the real wall;
#   * ROTATION per ring, because a canyon that cuts one circle cuts the other two at the
#     same bearing.  Turning the rings puts wall behind canyon -- which is exactly what the
#     synthetic rings did with independent seeds -- and the triple is chosen so that a real
#     canyon mouth lands on the 306 deg outlet the sunset frame looks through (the near ring
#     dips 267.7 m there and is backed by 200.9 m of farther wall);
#   * VERTICAL SCALE 1.7, and this one is an EXAGGERATION, stated rather than hidden.
#     True scale was the first choice and was measured out: `RELIEF_MIN_SPAN_M` asks that
#     the visible crest vary by 74 m inside every 45 deg window, the worst window's span is
#     exactly proportional to this scale, and the best any rotation triple reaches at 1.0 is
#     about 46.7 m.  A real mesa rim IS level over an arc -- that is what a plateau edge is
#     -- and the invariant was calibrated on a generator that could always lift a massif
#     until it cleared.  The choice was between stretching the vertical and weakening a
#     shipped invariant by a third; stretching is the smaller lie, it keeps every ridge,
#     bench and canyon in correct relative proportion, and distant terrain in a game is
#     routinely exaggerated to read at all.  1.7 is the SMALLEST stretch that passes: 1.55
#     puts nothing at all through the sweep, and 2.0 also passes but is a bigger lie.
#     So: the SHAPE is Canyonlands, metre for metre in plan; the HEIGHTS are that shape
#     stretched 1.7x.
#
# EVERY NUMBER BELOW IS THE MODULE'S OWN, not a re-implementation: `b7/verify_candidates.py`
# installs each candidate into these constants and judges it with `silhouette_summary()` and
# the shipped gates' own arithmetic (an earlier search re-implemented the peak statistics,
# got them wrong, and passed its own version of the gate).  On the chosen triple:
#   world shut on all 1,536 bearings; no crest height is a clamp;
#   height_min 320.950, height_max 566.332  (the design's window is 320 .. 640)
#   worst 45 deg window span 75.54 m        (RELIEF_MIN_SPAN_M is 74.0)
#   prominent peaks 18, visible peaks 18    (the GIS branch of the gate asks for 12)
#   590 bearings with a farther ridge behind the near one (the gate asks for 96)
#   autocorrelation +0.6082 at 7.5 deg, and inside (-0.60, 0.30) at 15/30/45/90/180
#   peak spread 0.1195 of the mean (> 0.09), tallest/shortest 1.72 (> 1.4)
GIS_PROFILE_PATH = (
    Path(__file__).resolve().parents[1] / "authoring" / f"{LEVEL_ID}_backdrop_gis.json"
)
GIS_ENABLED = True
GIS_VERTICAL_SCALE = 1.7
GIS_OFFSET_M = 54.2083
GIS_ROTATION_DEG = {"near": 24.375, "mid": 310.7812, "far": 249.8438}
#: the softplus knee used to keep the crest off the structural floor. With the chosen
#: mapping nothing reaches it -- the nearest approach is 107 m clear -- so this is a
#: guard rail, not a shaping tool, and the gate below asserts it never bites.
GIS_FLOOR_KNEE_M = 14.0
_GIS: dict[str, list[float]] = {}


def gis_document() -> dict:
    """The checked-in lidar profile, with its provenance. Read once."""

    if "_document" not in _GIS:
        _GIS["_document"] = json.loads(GIS_PROFILE_PATH.read_text(encoding="utf-8"))  # type: ignore[assignment]
    return _GIS["_document"]  # type: ignore[return-value]


def _gis_series(name: str) -> list[float]:
    """One ring's crest in LEVEL z, rotated, scaled and offset. Pure, cached."""

    if name not in _GIS:
        document = gis_document()
        values = document["crest_m"][name]
        columns = len(values)
        shift = round(GIS_ROTATION_DEG[name] / 360.0 * columns) % columns
        knee = GIS_FLOOR_KNEE_M
        series = []
        for index in range(columns):
            metres = values[(index - shift) % columns]
            z = GIS_OFFSET_M + GIS_VERTICAL_SCALE * metres
            t = (z - RING_FLOOR_Z) / knee
            # softplus, evaluated without overflowing for a tall wall
            lift = t if t > 30.0 else math.log1p(math.exp(t))
            series.append(RING_FLOOR_Z + knee * lift)
        _GIS[name] = series
    return _GIS[name]


def gis_crest(spec: RingSpec, bearing_deg: float) -> float:
    """The lidar crest for one ring at a bearing: linear between the 1,536 samples."""

    series = _gis_series(spec.name)
    columns = len(series)
    position = (bearing_deg % 360.0) / 360.0 * columns
    low = math.floor(position) % columns
    frac = position - math.floor(position)
    return series[low] * (1.0 - frac) + series[(low + 1) % columns] * frac


def ring_profile(spec: RingSpec, bearing_deg: float) -> tuple[float, float]:
    """(ridge top z, radius from C) for ONE ring at a compass bearing. Pure."""

    if GIS_ENABLED:
        return gis_crest(spec, bearing_deg), _radius(spec, bearing_deg)
    return _notched(spec, bearing_deg, _NOTCHES[spec.name]), _radius(spec, bearing_deg)


def visible_ring(bearing_deg: float) -> int:
    """Index of the ring whose apparent elevation is highest from the basin floor."""

    best, best_elev = 0, -math.inf
    for index, spec in enumerate(RINGS):
        top, radius = ring_profile(spec, bearing_deg)
        elevation = math.atan2(top - EYE_Z, radius)
        if elevation > best_elev:
            best, best_elev = index, elevation
    return best


def ridge_profile(bearing_deg: float) -> tuple[float, float]:
    """(z, radius) of the ridge a player at the basin floor actually SEES here."""

    return ring_profile(RINGS[visible_ring(bearing_deg)], bearing_deg)


# --- r9: the flank fields (see the FLANK constants above) -----------------------------


def _gaussian_circular(values: list[float], sigma_deg: float) -> list[float]:
    """Circular Gaussian blur of a per-column series. Pure, deterministic, no numpy.

    PERIODIC: column 0 and column ``COLUMN_SEGMENTS`` are the same bearing, so the field
    wraps exactly and ``_close_the_world``'s invariant survives the flank. Truncated at
    ``GAUSSIAN_TRUNCATION_SIGMA`` and renormalised, so the kernel sums to one everywhere.
    """

    n = len(values)
    sigma = max(sigma_deg / (360.0 / n), 1.0e-6)
    half = max(1, math.ceil(GAUSSIAN_TRUNCATION_SIGMA * sigma))
    weights = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-half, half + 1)]
    total = sum(weights)
    weights = [w / total for w in weights]
    out = []
    for i in range(n):
        acc = 0.0
        for k in range(-half, half + 1):
            acc += values[(i + k) % n] * weights[k + half]
        out.append(acc)
    return out


def _band_residual(crest: list[float], band: tuple[float, float]) -> list[float]:
    """The crest's relief inside one bearing band, normalised to [-1, 1] at its p95.

    A DIFFERENCE OF GAUSSIANS. Leg 1 and leg 2 both used a difference of BOXCARS; a
    boxcar's transfer function is a sinc whose sidelobes pass the crest's own 0.234 deg
    noise straight through, and the first thing r9 rendered with one was a row of 31 m
    blades. The Gaussian pair rolls off monotonically, so the field is really band-limited
    and the face slope is really smooth. (``b1/r9/probe/ring_flank.py`` renders both.)
    """

    fine = _gaussian_circular(crest, band[0])
    coarse = _gaussian_circular(crest, band[1])
    residual = [fine[i] - coarse[i] for i in range(len(crest))]
    ranked = sorted(abs(value) for value in residual)
    # A nearest-rank p95 over an even-length list: an ORDER STATISTIC BY INTENT. It ranks
    # a normalising SCALE, not a measurement anybody publishes (r9, critic r8 B8-2/B8-3).
    scale = ranked[int(0.95 * (len(ranked) - 1))] or 1.0
    return [max(-1.0, min(1.0, value / scale)) for value in residual]


_FLANK_FIELDS: dict[str, dict[str, list[float]]] = {}


def flank_fields() -> dict[str, dict[str, list[float]]]:
    """``{ring: {depth, spur, height}}``, one value per column. Cached; ~4 s the first time.

    Deliberately LAZY. Only the mesh builders need it, and a static gate that asks only
    about the silhouette must not pay for it.
    """

    if _FLANK_FIELDS:
        return _FLANK_FIELDS
    for spec in RINGS:
        crest = [ring_profile(spec, 360.0 * i / COLUMN_SEGMENTS)[0] for i in range(COLUMN_SEGMENTS)]
        massif = _band_residual(crest, MASSIF_BAND_DEG)
        spur = _band_residual(crest, SPUR_BAND_DEG)
        buttress = _band_residual(crest, BUTTRESS_BAND_DEG)
        _FLANK_FIELDS[spec.name] = {
            "depth": [FLANK_DEPTH_MID + FLANK_DEPTH_SWING * value for value in massif],
            "spur": [SPUR_AMPLITUDE * value for value in spur],
            # r13: the near-field gullies. See the BUTTRESS block above. ``_band_residual``
            # returns [-1, 1]; this maps it onto [0, 1] and then applies the gamma, so the
            # term is non-negative (no overhang) and its MIDDLE is lifted (every column
            # gets some section, not just the two extremes).
            "buttress": [
                BUTTRESS_AMPLITUDE * (0.5 * (value + 1.0)) ** BUTTRESS_GAMMA for value in buttress
            ],
            # The SMOOTHED column height, in metres. Scaling the offset by the column's
            # OWN height puts the crest's column-scale noise into the RADIUS, which
            # renders as thin vertical blades - r9's first draft did exactly that.
            "height": _gaussian_circular([value - Z_BASE for value in crest], HEIGHT_SMOOTH_DEG),
        }
    return _FLANK_FIELDS


#: r13: the row heights, as a TABLE rather than ``(step / SEGMENTS_V) ** VERTICAL_BIAS``.
#:
#: r9 chose the power law when the ring was a curtain the basin rim cut off at the bottom:
#: *"6 with VERTICAL_BIAS puts four of them in the top 30 % of the column - the part the
#: basin rim leaves visible."* r12 changed the object. The range is a solid a car stops
#: against, and critic r12 photographed its foot from 10 m. The power law puts exactly ONE
#: row below ``BUTTRESS_TOP`` (0.377), so the buttress would render as a single linear
#: taper - a fold in a curtain, not a rib.
#:
#: This table costs **zero triangles** and keeps the crest resolution exactly: three rows
#: in the top 30 % either way (0.76 / 0.90 / 1.00 against r9's 0.799 / 0.905 / 1.00). It
#: buys the third foot row from the middle of the column, where nothing is happening -
#: r9's 0.552 and 0.683 are two rows describing the same smooth stretch of ``G(t)``.
#: ``t = 1`` is unchanged, so the crest polyline and every silhouette statistic are
#: untouched by this line.
ROW_T: tuple[float, ...] = (0.0, 0.12, 0.34, 0.58, 0.76, 0.90, 1.0)


def row_t(step: int) -> float:
    """The height fraction of mesh row ``step``: rows under the crest AND at the foot."""

    return ROW_T[step]


def _flank_shape(t: float) -> float:
    """G(t): 0 at the crest, ~1 at the foot, slope ``1 / FLANK_KNEE`` under the crest."""

    return (1.0 - t) / ((1.0 - t) + FLANK_KNEE)


def _spur_shape(t: float) -> float:
    """H(t): 0 at the crest AND at the foot, peak 1 at t = 2/3."""

    return 6.75 * t * t * (1.0 - t)


def _buttress_shape(t: float) -> float:
    """B(t): 1 at the foot, 0 at and above ``BUTTRESS_TOP``, and therefore 0 at t = 1."""

    if t >= BUTTRESS_TOP:
        return 0.0
    return (1.0 - t / BUTTRESS_TOP) ** BUTTRESS_POWER


def flank_offset_m(spec: RingSpec, column: int, t: float) -> float:
    """How far column ``column`` of ``spec`` leans INWARD at height fraction ``t``, in m.

    Zero at ``t = 1`` for every column and every ring, by construction: that is what pins
    the crest vertex and makes the silhouette invariant from every eye. r13's buttress
    term obeys the same rule - it is zero at and above ``BUTTRESS_TOP`` = 0.42.
    """

    field = flank_fields()[spec.name]
    index = column % COLUMN_SEGMENTS
    height = field["height"][index]

    def raw(value: float) -> float:
        return height * (
            field["depth"][index] * _flank_shape(value)
            + field["spur"][index] * _spur_shape(value)
            + field["buttress"][index] * _buttress_shape(value)
        )

    offset = raw(t)
    if t <= BUTTRESS_TOP:
        # --- r13 / N12-2, decided rather than left as a taste --------------------------
        # A smaller offset is a LARGER radius, i.e. nearer the basin. A point higher up
        # with a larger offset than the foot therefore leans OUT over its own foot toward
        # the player, and if it does so within a car's reach of the ground it is a roof a
        # car can be trapped under. r12 had 6 such columns across the three rings (max
        # 15.9 m of lean, worst instance 190 m up - unreachable); r13's buttress made it
        # 189 columns, because a protruding rib LOWERS the foot's offset and everything
        # above it then leans out past it.
        #
        # The ruling: an overhang high on a mountain is a FEATURE and stays; an overhang a
        # car can be roofed by is a TRAP and is forbidden. So the face is monotone from
        # the foot up through the whole buttress zone - it may lean in, never out - and
        # above ``BUTTRESS_TOP`` (88-193 m up, past anything a car reaches) the spur is
        # left free to do what r9 built it to do. The clamp bites only where the natural
        # offset would exceed the foot's, and there it renders as a vertical lower face
        # under a sloping upper one, which is what a buttress looks like.
        offset = min(offset, raw(0.0))
    return offset


def ring_vertex_count() -> int:
    """Vertices without building them - a static gate must not pay for the fields."""

    return len(RINGS) * COLUMN_SEGMENTS * (SEGMENTS_V + 1)


def ring_vertices() -> list[tuple[float, float, float]]:
    """(x, y, z) for every vertex of all three rings, local to C. **A FLANK, not a curtain.**

    r9 (critic r8, "the player"). Through r8 this returned one radius per (ring, bearing):
    a vertical curtain whose every triangle normal had ``n_z`` exactly 0, so no face could
    catch or lose light with height. See the FLANK block at the top of this module for the
    algebra, the two rejected legs and why the fields are Gaussian.

    The ring now WRAPS - column ``COLUMN_SEGMENTS`` IS column 0, not a duplicate of it -
    so a smooth-shaded normal is averaged over all six neighbours at bearing 0 exactly as
    it is everywhere else and there is no seam line. The u seam lives in the per-loop UVs
    (``ring_triangle_uvs``), which is where COLLADA wants it.

    The ``t = 1`` row is bit-for-bit the crest polyline ``ring_profile`` returns, which is
    what ``ridge_profile``, ``visible_ring``, ``silhouette_summary`` and ``ridge_shape``
    all read. Nothing any of them publishes can move.
    """

    out: list[tuple[float, float, float]] = []
    for spec in RINGS:
        for column in range(COLUMN_SEGMENTS):
            bearing = 360.0 * column / COLUMN_SEGMENTS
            top, radius = ring_profile(spec, bearing)
            theta = math.radians(bearing)
            sin_t, cos_t = math.sin(theta), math.cos(theta)
            height = top - Z_BASE
            for step in range(SEGMENTS_V + 1):
                t = row_t(step)
                r = radius - flank_offset_m(spec, column, t)
                out.append((r * sin_t, r * cos_t, Z_BASE + height * t))
    return out


def _ring_vertex_index(band: int, column: int, step: int) -> int:
    per_column = SEGMENTS_V + 1
    per_ring = COLUMN_SEGMENTS * per_column
    return band * per_ring + (column % COLUMN_SEGMENTS) * per_column + step


def ring_triangles() -> list[tuple[int, int, int]]:
    """Two inward-facing triangles per column segment, for every ring. Wraps at 360 deg."""

    faces: list[tuple[int, int, int]] = []
    for band in range(len(RINGS)):
        for column in range(COLUMN_SEGMENTS):
            for step in range(SEGMENTS_V):
                b0 = _ring_vertex_index(band, column, step)
                t0 = _ring_vertex_index(band, column, step + 1)
                b1 = _ring_vertex_index(band, column + 1, step)
                t1 = _ring_vertex_index(band, column + 1, step + 1)
                # wound so the normal points INWARD (toward C), the only side ever seen
                faces.append((b0, t1, t0))
                faces.append((b0, b1, t1))
    return faces


def ring_triangle_uvs() -> list[tuple[tuple[float, float], ...]]:
    """Per-CORNER (u, v) aligned one-for-one with ``ring_triangles()``.

    The ring's vertices wrap, so the last column's right-hand corners must carry ``u = 1``
    and not ``u = 0``, or the whole 8,192 px atlas is squeezed into one 0.234 deg quad.
    COLLADA indexes TEXCOORD per loop, so this costs nothing but the list.
    """

    #: v is keyed to ABSOLUTE z, not to the column's height fraction - that is what keeps
    #: the snow line at z = 500 on one strip row all the way round, and it is exactly the
    #: curtain's own mapping, so the 8,192 x 2,048 atlas needs no change at all.
    tops = [
        [ring_profile(spec, 360.0 * c / COLUMN_SEGMENTS)[0] for c in range(COLUMN_SEGMENTS)]
        for spec in RINGS
    ]

    def uv(band: int, column: int, step: int) -> tuple[float, float]:
        top = tops[band][column % COLUMN_SEGMENTS]
        z = Z_BASE + (top - Z_BASE) * row_t(step)
        local = (z - Z_BASE) / (Z_TOP - Z_BASE)
        return (column / COLUMN_SEGMENTS, (band + local) / STRIP_BANDS)

    out: list[tuple[tuple[float, float], ...]] = []
    for band in range(len(RINGS)):
        for column in range(COLUMN_SEGMENTS):
            for step in range(SEGMENTS_V):
                b0 = uv(band, column, step)
                t0 = uv(band, column, step + 1)
                b1 = uv(band, column + 1, step)
                t1 = uv(band, column + 1, step + 1)
                out.append((b0, t1, t0))
                out.append((b0, b1, t1))
    return out


# --- r12: the solid ---------------------------------------------------------------------

_TERRAIN: dict[str, object] = {}


def terrain_grid() -> dict[str, object]:
    """``{z, size, sha256}`` of the shipped .ter: heights in metres, indexed ``[y, x]``.

    numpy only (Blender has numpy and no Pillow), and the parse is the header + the u16
    height array of ``terrain_io.read_ter_bytes`` - the static gate asserts the two agree.
    """

    if not _TERRAIN:
        import struct

        import numpy as np

        payload = TERRAIN_TER.read_bytes()
        version, size = struct.unpack_from("<BI", payload, 0)
        if version != TER_VERSION:
            raise RuntimeError(f"unsupported .ter version {version} in {TERRAIN_TER}")
        heights = np.frombuffer(payload, dtype="<u2", count=size * size, offset=5)
        _TERRAIN["z"] = heights.reshape(size, size).astype(np.float64) * TERRAIN_UNIT_M
        _TERRAIN["size"] = int(size)
        _TERRAIN["sha256"] = hashlib.sha256(payload).hexdigest()
    return _TERRAIN


def terrain_z_world(x, y):  # numpy arrays in, numpy array out
    """Bilinear terrain height at WORLD (x, y); NaN outside the block (inset 1.5 m)."""

    import numpy as np

    grid = terrain_grid()
    z = grid["z"]
    size = grid["size"]
    fx = np.asarray(x, dtype=np.float64) - TERRAIN_POSITION[0]
    fy = np.asarray(y, dtype=np.float64) - TERRAIN_POSITION[1]
    inside = (
        (fx >= TERRAIN_EDGE_INSET_M)
        & (fy >= TERRAIN_EDGE_INSET_M)
        & (fx <= size - 1 - TERRAIN_EDGE_INSET_M)
        & (fy <= size - 1 - TERRAIN_EDGE_INSET_M)
    )
    i = np.clip(np.floor(fx).astype(np.int64), 0, size - 2)
    j = np.clip(np.floor(fy).astype(np.int64), 0, size - 2)
    u = np.clip(fx - i, 0.0, 1.0)
    w = np.clip(fy - j, 0.0, 1.0)
    value = (
        (1.0 - u) * (1.0 - w) * z[j, i]
        + u * (1.0 - w) * z[j, i + 1]
        + (1.0 - u) * w * z[j + 1, i]
        + u * w * z[j + 1, i + 1]
    )
    return np.where(inside, value, np.nan)


def _bearing_unit(column: int) -> tuple[float, float]:
    theta = math.radians(360.0 * column / COLUMN_SEGMENTS)
    return math.sin(theta), math.cos(theta)


def _front_column(spec: RingSpec, column: int) -> list[tuple[float, float]]:
    """The seven front rows of one column as (radius, z) - the same arithmetic, in the
    same order, as ``ring_vertices`` (which is what pins them to r11)."""

    bearing = 360.0 * column / COLUMN_SEGMENTS
    top, radius = ring_profile(spec, bearing)
    height = top - Z_BASE
    out = []
    for step in range(SEGMENTS_V + 1):
        t = row_t(step)
        out.append((radius - flank_offset_m(spec, column, t), Z_BASE + height * t))
    return out


def back_foot_radius(band: int, column: int) -> float:
    """Where ring ``band``'s back foot stands: beyond the next ring's crest, or the bench."""

    if band + 1 < len(RINGS):
        bearing = 360.0 * column / COLUMN_SEGMENTS
        return _radius(RINGS[band + 1], bearing) + PENETRATION_M
    return OUTER_BENCH_R


_VALLEY: dict[str, dict[str, list]] = {}


def valley_floors() -> dict[str, dict[str, list]]:
    """Per ring, per column: the back foot's z and how it was set. Cached; needs the terrain.

    ``regime`` is ``"terrain"`` where the block reaches the back foot (the foot is set
    ``VALLEY_BURY_M`` under the ground, the ground between the ridges stays a real valley)
    and ``"rock"`` elsewhere (``VALLEY_Z``, or the highest node under the span plus
    ``VALLEY_MARGIN_M``). The rock rule is applied to a dilated, smoothed envelope and then
    re-asserted per column, so the floor is smooth along the bearing AND never under a node.
    """

    if _VALLEY:
        return _VALLEY
    import numpy as np

    fractions = np.linspace(0.0, 1.0, TERRAIN_SAMPLES_PER_SPAN)
    for band, spec in enumerate(RINGS):
        columns = np.arange(COLUMN_SEGMENTS)
        theta = np.radians(360.0 * columns / COLUMN_SEGMENTS)
        sin_t, cos_t = np.sin(theta), np.cos(theta)
        r_foot = np.array([_front_column(spec, c)[0][0] for c in range(COLUMN_SEGMENTS)])
        r_back = np.array([back_foot_radius(band, c) for c in range(COLUMN_SEGMENTS)])
        r0 = r_foot - 5.0
        r1 = r_back + 15.0
        radii = r0[:, None] + (r1 - r0)[:, None] * fractions[None, :]
        tz = terrain_z_world(
            CENTER_XY[0] + radii * sin_t[:, None], CENTER_XY[1] + radii * cos_t[:, None]
        )
        no_terrain = np.all(np.isnan(tz), axis=1)
        with warnings.catch_warnings():
            # a column with no terrain under it is an all-NaN row: handled on the next line
            warnings.simplefilter("ignore", RuntimeWarning)
            row_max = np.nanmax(tz, axis=1)
        envelope = np.where(no_terrain, -np.inf, row_max)
        at_foot = terrain_z_world(CENTER_XY[0] + r_back * sin_t, CENTER_XY[1] + r_back * cos_t)
        on_terrain = ~np.isnan(at_foot)
        # the rock rule on a dilated envelope, smoothed; the terrain rule where the block
        # reaches the back foot. Both are then smoothed together and re-asserted.
        raw = np.where(np.isfinite(envelope), envelope + VALLEY_MARGIN_M, VALLEY_Z - 100.0)
        dilated = raw.copy()
        for shift in range(-VALLEY_DILATE_COLUMNS, VALLEY_DILATE_COLUMNS + 1):
            dilated = np.maximum(dilated, np.roll(raw, shift))
        rock = np.maximum(dilated, VALLEY_Z)
        target = np.where(on_terrain, at_foot - VALLEY_BURY_M, rock)
        smoothed = _gaussian_circular([float(v) for v in target], VALLEY_SMOOTH_DEG)
        floor: list[float] = []
        regime: list[str] = []
        bumps = 0
        for c in range(COLUMN_SEGMENTS):
            value = smoothed[c]
            if on_terrain[c]:
                limit = float(at_foot[c]) - 5.0
                if value > limit:
                    value, bumps = limit, bumps + 1
                regime.append("terrain")
            else:
                limit = float(envelope[c]) + 5.0 if np.isfinite(envelope[c]) else -math.inf
                if value < limit:
                    value, bumps = limit, bumps + 1
                regime.append("rock")
            floor.append(value)
        _VALLEY[spec.name] = {
            "z": floor,
            "regime": regime,
            "envelope": [float(v) if np.isfinite(v) else None for v in envelope],
            "terrain_at_back_foot": [float(v) if np.isfinite(v) else None for v in at_foot],
            "back_foot_radius": [float(v) for v in r_back],
            "bumps": [bumps],
        }
    return _VALLEY


def block_edge_radius(bearing_deg):
    """Distance from C to the TerrainBlock's boundary along ``bearing_deg`` (numpy in/out).

    The block is ``size`` nodes at 1 m from ``TERRAIN_POSITION``; C sits at its centre, so
    this is 1,023-1,024 m on the axes and 1,447 m at the corners. Exact, per side - not a
    circle, which is the whole point of B13-1.
    """

    import numpy as np

    size = int(terrain_grid()["size"])
    x0, y0 = TERRAIN_POSITION
    cx, cy = CENTER_XY
    theta = np.radians(np.asarray(bearing_deg, dtype=np.float64))
    sin_t, cos_t = np.sin(theta), np.cos(theta)
    limit = np.full(theta.shape, np.inf)
    for delta, direction in (
        (x0 + (size - 1) - cx, sin_t),
        (x0 - cx, sin_t),
        (y0 + (size - 1) - cy, cos_t),
        (y0 - cy, cos_t),
    ):
        with np.errstate(divide="ignore", invalid="ignore"):
            hit = np.where(np.abs(direction) > 1.0e-12, delta / direction, np.inf)
        limit = np.minimum(limit, np.where(hit > 0.0, hit, np.inf))
    return limit


_APRON: dict[str, dict[str, list[float]]] = {}


def apron_lips() -> dict[str, dict[str, list[float]]]:
    """r14 / B13-1. Per ring, per column: where the front toe's LIP stands and why.

    On the near ring the lip goes **where the ground runs out**: if the block's own edge,
    less ``APRON_OVERLAP_M``, is inside ``foot - APRON_MIN_RUN_M`` then that is the lip,
    and otherwise the block laps far enough past the foot that r12's ``FRONT_TOE_IN_M``
    toe-in is already under it and is kept. The other rings take the toe-in alone. ``z``
    is the ground at that radius less ``APRON_BURY_M``, floored at ``Z_FLOOR +
    APRON_MIN_LIP_M`` so the inner wall is never degenerate. Both are smoothed along the
    bearing and then re-asserted against their own bounds, so smoothing can never push a
    lip outside the block or above the ground.

    **Why the lip is not simply ``min(toe-in, edge)``, which is what the first draft
    used.** That expression keeps the toe 60 m inside the foot wherever it can, so on the
    bearings where the block stops only 20-55 m short of the foot the lip sits far inside
    the block and the chord from it to the foot has already dived tens of metres by the
    time the grass runs out. The world was closed - a car landed on rock at every launch
    speed - but it landed after a **78.9 m** drop, and 97 bearings had a step over 10 m
    (``r14/probe/world_edge.py``). Putting the lip at the edge instead makes the rock
    emerge where the ground ends, and the step becomes ``APRON_BURY_M`` plus five metres
    of the chord's own slope.
    """

    if _APRON:
        return _APRON
    import numpy as np

    columns = np.arange(COLUMN_SEGMENTS)
    bearings = 360.0 * columns / COLUMN_SEGMENTS
    theta = np.radians(bearings)
    sin_t, cos_t = np.sin(theta), np.cos(theta)
    edge_r = block_edge_radius(bearings)
    floor_z = Z_FLOOR + APRON_MIN_LIP_M
    for band, spec in enumerate(RINGS):
        r_foot = np.array([_front_column(spec, int(c))[0][0] for c in columns])
        default_r = r_foot - FRONT_TOE_IN_M
        # r16 / B15-2: the gutter's floor. ``w`` is the radial width of the level strip at
        # ``Z_BASE`` immediately inside the ring's foot. It is bounded by the room between
        # the foot and the block's own edge, so where the block laps past the foot - which
        # is most of the mid and far rings and 684 of the near ring's columns - it closes to
        # ``GUTTER_FLOOR_MIN_M`` and the strip is a formality buried under the terrain.
        # ``room`` is continuous in the bearing, so ``w`` is too, and the smoothing can only
        # lower it: no column gets a step and none gets a degenerate quad.
        room = r_foot - block_edge_radius(bearings) - GUTTER_FLOOR_MARGIN_M
        floor_bound = (
            np.clip(room, GUTTER_FLOOR_MIN_M, GUTTER_FLOOR_M)
            if band in APRON_BANDS
            # Only the NEAR ring has a gutter a car can reach, for the same reason only it
            # carries the shore apron. The others take the minimum, so their sections keep a
            # non-degenerate row and gain a 0.5 m shelf that is buried behind the ring in
            # front of them - the cost of the row, and nothing else.
            else np.full(COLUMN_SEGMENTS, GUTTER_FLOOR_MIN_M)
        )
        floor_w = np.minimum(
            np.array(_gaussian_circular([float(v) for v in floor_bound], APRON_SMOOTH_DEG)),
            floor_bound,
        )
        r_toe = r_foot - floor_w
        if band not in APRON_BANDS:
            # The mid and far rings stand behind the near one and cannot be reached: they
            # keep r13's toe radius exactly and take the minimum inner wall, so this row
            # costs them a buried 8 m face and nothing else.
            _APRON[spec.name] = {
                "r": [float(v) for v in default_r],
                "z": [floor_z for _ in columns],
                "default_r": [float(v) for v in default_r],
                "block_edge_r": [float(v) for v in edge_r],
                "pulled_in_m": [0.0 for _ in columns],
                "is_a_shore_apron": [False for _ in columns],
                "gutter_floor_m": [float(v) for v in floor_w],
            }
            continue

        def ground(radius):
            return terrain_z_world(CENTER_XY[0] + radius * sin_t, CENTER_XY[1] + radius * cos_t)

        at_the_edge = edge_r - APRON_OVERLAP_M
        bound_r = np.where(at_the_edge < r_foot - APRON_MIN_RUN_M, at_the_edge, default_r)
        smoothed_r = np.array(_gaussian_circular([float(v) for v in bound_r], APRON_SMOOTH_DEG))
        final_r = np.minimum(smoothed_r, bound_r)

        # The apron is the chord from the lip to the foot. It may not rise through the
        # ground ANYWHERE it is still under the block - not only at the lip - so the lip's
        # height is the tightest of those bounds, sampled along the covered run. Without
        # this the rock stood up to 17.3 m proud of the grass where the ground falls away
        # faster than the chord does (measured, r14 first draft).
        # r16: the chord now ends at the apron's TOE, ``r_toe = r_foot - w``, not at the
        # foot, so the lever that turns "the ground here" into "the highest the lip may be"
        # is measured against the toe. Leaving ``r_foot`` in it would under-bury the chord by
        # the floor's own width, which is exactly the class of error the clearance sampling
        # was written to catch.
        span_hi = np.minimum(edge_r, r_toe - APRON_TIP_GUARD_M)
        bound_z = np.full(COLUMN_SEGMENTS, np.inf)
        for fraction in np.linspace(0.0, 1.0, APRON_CLEARANCE_SAMPLES):
            radius = final_r + (span_hi - final_r) * fraction
            covered = radius <= np.maximum(final_r, span_hi)
            here = ground(radius)
            lever = np.maximum(r_toe - radius, 1.0) / np.maximum(r_toe - final_r, 1.0)
            candidate = Z_BASE + (here - APRON_BURY_M - Z_BASE) / np.maximum(lever, 1e-9)
            candidate = np.where(np.isnan(here) | ~covered, np.inf, candidate)
            bound_z = np.minimum(bound_z, candidate)
        bound_z = np.where(np.isfinite(bound_z), bound_z, floor_z)
        smoothed_z = np.array(_gaussian_circular([float(v) for v in bound_z], APRON_SMOOTH_DEG))
        final_z = np.maximum(np.minimum(smoothed_z, bound_z), floor_z)
        reached = np.array(at_the_edge < r_foot - APRON_MIN_RUN_M)
        _APRON[spec.name] = {
            "r": [float(v) for v in final_r],
            "z": [float(v) for v in final_z],
            "default_r": [float(v) for v in default_r],
            "block_edge_r": [float(v) for v in edge_r],
            "pulled_in_m": [float(v) for v in (default_r - final_r)],
            "is_a_shore_apron": [bool(v) for v in reached],
            "gutter_floor_m": [float(v) for v in floor_w],
        }
    return _APRON


def column_polygon(band: int, column: int) -> list[tuple[float, float]]:
    """The 16 (radius, z) vertices round one column's section, in traversal order.

    apron lip, (r16) the apron toe, front rows 0..6 (foot .. crest), shoulder x2, back x2,
    back foot, back toe, front toe. r14 (B13-1): the lip and the front toe share a radius;
    the wall between them is edge 15 and the flat underside from the back toe to the front
    toe is edge 14. r16 (B15-2): the apron toe stands ``gutter_floor_m`` INSIDE the foot at
    ``Z_BASE``, so edge 1 - toe to foot - is a level strip and the V at the bottom of the
    apron has a floor a car can sit on. The front rows themselves are untouched, which is
    what keeps r11's front face and its UVs pinned through this change.
    """

    spec = RINGS[band]
    column %= COLUMN_SEGMENTS
    front = _front_column(spec, column)
    r_crest, z_top = front[-1]
    lip = apron_lips()[spec.name]
    r_lip, z_lip = lip["r"][column], lip["z"][column]
    r_foot, z_foot = front[0]
    points = [(r_lip, z_lip), (r_foot - lip["gutter_floor_m"][column], z_foot), *front]
    for out, down in SHOULDER:
        points.append((r_crest + out, z_top - down))
    r_shoulder, z_shoulder = points[-1]
    valley = valley_floors()[spec.name]
    r_back = valley["back_foot_radius"][column]
    z_back = valley["z"][column]
    run, drop = r_back - r_shoulder, z_shoulder - z_back
    if run <= 0.0 or drop <= 0.0:
        raise RuntimeError(f"{spec.name} column {column}: back run {run}, drop {drop}")
    for f_run, f_drop in BACK_PROFILE:
        points.append((r_shoulder + f_run * run, z_shoulder - f_drop * drop))
    points.append((r_back, z_back))
    if band + 1 < len(RINGS):
        toe = r_back + BACK_TOE_OUT_M
    else:
        toe = r_back + (z_back - Z_FLOOR) * OUTER_RUN
    points.append((toe, Z_FLOOR))
    points.append((r_lip, Z_FLOOR))  # r14: the front toe, under the lip
    if len(points) != POLYGON_ROWS:
        raise RuntimeError(f"{len(points)} polygon rows, expected {POLYGON_ROWS}")
    return points


def _extra_index(band: int, column: int, row: int) -> int:
    slot = band * COLUMN_SEGMENTS + column % COLUMN_SEGMENTS
    return ring_vertex_count() + slot * EXTRA_ROWS + row


def polygon_vertex_index(band: int, column: int, point: int) -> int:
    """Vertex index of polygon point ``point`` (0..15) of ``column`` in ring ``band``.

    r16: points below ``FRONT_POINT_0`` are the apron's lip and toe, points
    ``FRONT_POINT_0 .. FRONT_POINT_0 + SEGMENTS_V`` are r11's seven front rows in r11's own
    order and slots, and everything after them is an extra row. The extra ROW number of a
    point past the front face is ``point - SEGMENTS_V - 1``, which is the same arithmetic
    r14 used with ``FRONT_POINT_0`` = 1.
    """

    point %= POLYGON_ROWS
    if point < FRONT_POINT_0:
        return _extra_index(band, column, point)
    if point <= FRONT_POINT_0 + SEGMENTS_V:
        return _ring_vertex_index(band, column, point - FRONT_POINT_0)
    return _extra_index(band, column, point - SEGMENTS_V - 1)


def solid_vertex_count() -> int:
    return ring_vertex_count() + len(RINGS) * COLUMN_SEGMENTS * EXTRA_ROWS


def solid_vertices() -> list[tuple[float, float, float]]:
    """``ring_vertices()`` first - unchanged, in order - then the NINE extra rows per column."""

    out = list(ring_vertices())
    for band in range(len(RINGS)):
        for column in range(COLUMN_SEGMENTS):
            sin_t, cos_t = _bearing_unit(column)
            polygon = column_polygon(band, column)
            for point in EXTRA_POINTS:
                r, z = polygon[point]
                out.append((r * sin_t, r * cos_t, z))
    if len(out) != solid_vertex_count():
        raise RuntimeError(f"{len(out)} solid vertices, expected {solid_vertex_count()}")
    return out


def _polygon_quad(band: int, column: int, edge: int) -> list[tuple[int, int, int]]:
    """The two triangles between polygon edge ``edge -> edge + 1`` of ``column`` and of
    ``column + 1``, wound exactly as ``ring_triangles`` winds the front face."""

    b0 = polygon_vertex_index(band, column, edge)
    t0 = polygon_vertex_index(band, column, edge + 1)
    b1 = polygon_vertex_index(band, column + 1, edge)
    t1 = polygon_vertex_index(band, column + 1, edge + 1)
    return [(b0, t1, t0), (b0, b1, t1)]


def solid_triangles() -> list[tuple[int, int, int]]:
    """The front face's 55,296 triangles first, in r11's order, then the closure."""

    faces = ring_triangles()
    for band in range(len(RINGS)):
        for column in range(COLUMN_SEGMENTS):
            for edge in EXTRA_EDGES:
                faces.extend(_polygon_quad(band, column, edge))
    return faces


def _solid_uv(band: int, u_column: int, z: float) -> tuple[float, float]:
    """The atlas mapping for any point: ``u`` by column, ``v`` by |z - Z_BASE| in the
    ring's band - the front face's own mapping, mirrored below the foot and carried over
    the crest onto the back, so the texture is continuous at both edges."""

    local = abs(z - Z_BASE) / (Z_TOP - Z_BASE)
    return (u_column / COLUMN_SEGMENTS, (band + local) / STRIP_BANDS)


def solid_triangle_uvs() -> list[tuple[tuple[float, float], ...]]:
    """Per-corner UVs aligned with ``solid_triangles()``: r11's for the front, then the rest."""

    out = ring_triangle_uvs()
    polygons = [
        [column_polygon(band, column) for column in range(COLUMN_SEGMENTS)]
        for band in range(len(RINGS))
    ]
    for band in range(len(RINGS)):
        for column in range(COLUMN_SEGMENTS):
            here = polygons[band][column]
            there = polygons[band][(column + 1) % COLUMN_SEGMENTS]
            for edge in EXTRA_EDGES:
                nxt = (edge + 1) % POLYGON_ROWS
                b0 = _solid_uv(band, column, here[edge][1])
                t0 = _solid_uv(band, column, here[nxt][1])
                b1 = _solid_uv(band, column + 1, there[edge][1])
                t1 = _solid_uv(band, column + 1, there[nxt][1])
                out.append((b0, t1, t0))
                out.append((b0, b1, t1))
    return out


def _front_row_edge_keys(step: int) -> set[tuple[int, int]]:
    keys = set()
    for band in range(len(RINGS)):
        for column in range(COLUMN_SEGMENTS):
            a = _ring_vertex_index(band, column, step)
            b = _ring_vertex_index(band, column + 1, step)
            keys.add((a, b) if a < b else (b, a))
    return keys


def crest_edge_keys() -> set[tuple[int, int]]:
    """The (lower, higher) vertex index of every crest edge: marked SHARP in the mesh."""

    return _front_row_edge_keys(SEGMENTS_V)


def foot_edge_keys() -> set[tuple[int, int]]:
    """Every foot edge (front row 0), also SHARP: the skirt below starts its own shading
    and the foot row keeps the per-loop normals r11 computed for a boundary."""

    return _front_row_edge_keys(0)


def colmesh_columns() -> int:
    return COLUMN_SEGMENTS // COLMESH_COLUMN_STEP


def _colmesh_index(band: int, col: int, slot: int) -> int:
    return (band * colmesh_columns() + col % colmesh_columns()) * len(COLMESH_ROWS) + slot


def colmesh_vertices() -> list[tuple[float, float, float]]:
    out = []
    for band in range(len(RINGS)):
        for col in range(colmesh_columns()):
            column = col * COLMESH_COLUMN_STEP
            sin_t, cos_t = _bearing_unit(column)
            polygon = column_polygon(band, column)
            for point in COLMESH_ROWS:
                r, z = polygon[point]
                out.append((r * sin_t, r * cos_t, z))
    return out


def colmesh_triangles() -> list[tuple[int, int, int]]:
    """Closed like the visual: the seven collision rows swept round, same winding."""

    faces = []
    slots = len(COLMESH_ROWS)
    for band in range(len(RINGS)):
        for col in range(colmesh_columns()):
            for slot in range(slots):
                b0 = _colmesh_index(band, col, slot)
                t0 = _colmesh_index(band, col, (slot + 1) % slots)
                b1 = _colmesh_index(band, col + 1, slot)
                t1 = _colmesh_index(band, col + 1, (slot + 1) % slots)
                faces.append((b0, t1, t0))
                faces.append((b0, b1, t1))
    return faces


def mesh_volumes(
    vertices: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    band_of_vertex,  # int -> int
) -> list[float]:
    """Signed volume per ring by the divergence theorem: positive iff the normals face OUT."""

    totals = [0.0 for _ in RINGS]
    for a, b, c in triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = vertices[a], vertices[b], vertices[c]
        cross = (by * cz - bz * cy, bz * cx - bx * cz, bx * cy - by * cx)
        totals[band_of_vertex(a)] += (ax * cross[0] + ay * cross[1] + az * cross[2]) / 6.0
    return totals


def solid_band_of_vertex(index: int) -> int:
    per_ring = COLUMN_SEGMENTS * (SEGMENTS_V + 1)
    if index < ring_vertex_count():
        return index // per_ring
    return (index - ring_vertex_count()) // (COLUMN_SEGMENTS * EXTRA_ROWS)


def colmesh_band_of_vertex(index: int) -> int:
    return index // (colmesh_columns() * len(COLMESH_ROWS))


def _prominent_peaks(heights: list[float], min_prominence: float) -> int:
    """Local maxima whose drop to the deeper adjacent saddle exceeds the prominence."""

    n = len(heights)
    count = 0
    for i in range(n):
        if not (heights[i] > heights[i - 1] and heights[i] >= heights[(i + 1) % n]):
            continue
        peak = heights[i]
        prominence = peak
        for direction in (-1, 1):
            saddle = peak
            j = i
            for _ in range(n):
                j = (j + direction) % n
                if heights[j] > peak:
                    break
                saddle = min(saddle, heights[j])
            prominence = min(prominence, peak - saddle)
        if prominence >= min_prominence:
            count += 1
    return count


def silhouette_summary() -> dict[str, object]:
    """What the static gate checks without Blender."""

    bearings = [360.0 * i / COLUMN_SEGMENTS for i in range(COLUMN_SEGMENTS)]
    per_ring = {spec.name: [ring_profile(spec, b) for b in bearings] for spec in RINGS}
    visible = [ridge_profile(b) for b in bearings]
    heights = [t for t, _ in visible]
    radii = [r for _, r in visible]
    near = [t for t, _ in per_ring["near"]]
    occluded = sum(
        1
        for i, b in enumerate(bearings)
        if visible_ring(b) == 0
        and any(
            math.atan2(per_ring[spec.name][i][0] - EYE_Z, per_ring[spec.name][i][1])
            < math.atan2(per_ring["near"][i][0] - EYE_Z, per_ring["near"][i][1])
            for spec in RINGS[1:]
        )
    )
    all_massifs = [m for spec in RINGS for m in _SUMMITS[spec.name]]
    # a summit reads as ROCK only if its apex slope is non-zero, which for
    # ``(1 - t**a)**b`` means a <= 1 on at least one side. r2's Gaussian is a = 2 on
    # both sides for every summit, so this number was 0 in every round up to r6.
    sharp = sum(1 for m in all_massifs if min(m.a_neg, m.a_pos) <= 1.0)
    widths = [(m.w_neg, m.w_pos) for m in all_massifs]
    # r8 (critic r7 B7-1): ``sorted(...)[n // 2]`` is the UPPER median on an even n, and
    # n is 56. It printed 0.3534 - the 29th of 56 - where the median is 0.3483, in the
    # revision whose own blocking item was five upper medians printed as medians.
    # ``statistics.median`` averages the two middle order statistics; nothing else in
    # this module takes an order statistic except ``_notches``, whose 55th percentile is
    # a nearest-rank index by intent and is audited as such.
    asymmetry = sorted(abs(a - b) / (a + b) for a, b in widths)
    return {
        "rings": len(RINGS),
        "columns": COLUMN_SEGMENTS,
        "column_degrees": round(360.0 / COLUMN_SEGMENTS, 5),
        "control_columns": RIDGE_COLUMNS,
        "vertical_segments": SEGMENTS_V,
        # r12: the visual mesh is the closed solid; the front face is r11's 55,296 inside it.
        "triangles": len(solid_triangles()),
        "front_triangles": len(ring_triangles()),
        "colmesh_triangles": len(colmesh_triangles()),
        # r9: counted, not built. ``ring_vertices()`` now needs the flank fields, which
        # cost seconds; this gate only wants the number and must stay static and fast.
        "vertices": solid_vertex_count(),
        "front_vertices": ring_vertex_count(),
        "mesh_kind": "solid",
        "z_floor": Z_FLOOR,
        "valley_z": VALLEY_Z,
        "outer_bench_r": OUTER_BENCH_R,
        "penetration_m": PENETRATION_M,
        "colmesh_node": COLMESH_NODE,
        "colmesh_columns": colmesh_columns(),
        "flank_knee": FLANK_KNEE,
        "flank_depth_mid": FLANK_DEPTH_MID,
        "flank_depth_swing": FLANK_DEPTH_SWING,
        "spur_amplitude": SPUR_AMPLITUDE,
        "vertical_bias": VERTICAL_BIAS,
        "z_base": Z_BASE,
        "height_min": round(min(heights), 3),
        "height_max": round(max(heights), 3),
        "radius_min": round(min(radii), 3),
        "radius_max": round(max(radii), 3),
        # design §2.6's 24 silhouette peaks: the near (primary) ring's AUTHORED massifs.
        # r7 (B6-1) gave each massif spurs, a broken crest and cols of its own, so the
        # measured prominent-peak count is no longer the authored count - the authored
        # count is what design §2.6 fixes and it is still exactly 24.
        "primary_summits": len(_SUMMITS["near"]),
        "peaks": _prominent_peaks(near, 8.0),
        "visible_peaks": _prominent_peaks(heights, 8.0),
        "bearings_with_a_far_ridge_behind_the_near_one": occluded,
        "snow_columns": sum(1 for h in heights if h > 500.0),
        "strip_px_per_degree": round(STRIP_W / 360.0, 3),
        # --- r7 (B6-1): the SHAPE of the outline, not just its variety ---------------
        "massifs": len(all_massifs),
        "spurs": sum(len(_SPURS[spec.name]) for spec in RINGS),
        # --- r13: the massif-group tier and its two invariants ------------------------
        "shoulders": sum(len(_SHOULDERS[spec.name]) for spec in RINGS),
        "shoulders_per_ring": {spec.name: len(_SHOULDERS[spec.name]) for spec in RINGS},
        "summits_per_group": round(
            len(all_massifs) / max(sum(len(_SHOULDERS[spec.name]) for spec in RINGS), 1), 3
        ),
        "relief_window_deg": RELIEF_WINDOW_DEG,
        "relief_min_span_m": RELIEF_MIN_SPAN_M,
        "relief_repair_passes": RELIEF_PASSES,
        "worst_visible_span_in_a_window_m": round(
            min(
                max(window) - min(window)
                for window in (
                    [
                        heights[(start + k) % COLUMN_SEGMENTS]
                        for k in range(round(RELIEF_WINDOW_DEG / 360.0 * COLUMN_SEGMENTS))
                    ]
                    for start in range(COLUMN_SEGMENTS)
                )
            ),
            2,
        ),
        "range_walls": sum(len(_RANGES[spec.name]) for spec in RINGS),
        "notches": sum(len(_NOTCHES[spec.name]) for spec in RINGS),
        "archetypes": {
            name: sum(1 for m in all_massifs if m.archetype == name) for name, *_ in ARCHETYPES
        },
        "sharp_apex_summits": sharp,
        "median_flank_asymmetry": round(statistics.median(asymmetry), 4),
        "symmetric_summits": sum(1 for value in asymmetry if value < 1.0e-9),
        "notch_repair_passes": REPAIR_PASSES,
        "headroom_scale": {name: round(value, 4) for name, value in _HEADROOM.items()},
        "ring_floor_z": RING_FLOOR_Z,
    }


# --- Collada inspection (used by the static gate; no bpy) ------------------------------


def dae_node_parents(dae_path: Path) -> dict[str, str | None]:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    scene = root.find("c:library_visual_scenes/c:visual_scene", COLLADA_NS)
    out: dict[str, str | None] = {}

    def walk(node, parent):
        for child in node.findall("c:node", COLLADA_NS):
            name = child.get("name") or child.get("id")
            out[name] = parent
            walk(child, name)

    walk(scene, None)
    return out


def dae_material_names(dae_path: Path) -> set[str]:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    return {m.get("name") for m in root.iter(f"{{{COLLADA_NS['c']}}}material")}


def dae_tri_count(dae_path: Path) -> int:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    return sum(int(t.get("count")) for t in root.iter(f"{{{COLLADA_NS['c']}}}triangles"))


def dae_tri_counts(dae_path: Path) -> dict[str, int]:
    """Triangles per ``<geometry id>``: the visual solid and the Colmesh are two."""

    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    out: dict[str, int] = {}
    for geometry in root.iter(f"{{{COLLADA_NS['c']}}}geometry"):
        out[geometry.get("id")] = sum(
            int(t.get("count")) for t in geometry.iter(f"{{{COLLADA_NS['c']}}}triangles")
        )
    return out


def dae_positions(dae_path: Path, geometry_id: str) -> list[tuple[float, float, float]]:
    """The POSITION array of one geometry, parsed as floats, in the file's order."""

    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    for geometry in root.iter(f"{{{COLLADA_NS['c']}}}geometry"):
        if geometry.get("id") != geometry_id:
            continue
        mesh = geometry.find("c:mesh", COLLADA_NS)
        sources = {s.get("id"): s for s in mesh.findall("c:source", COLLADA_NS)}
        vertices = mesh.find("c:vertices", COLLADA_NS)
        for inp in vertices.findall("c:input", COLLADA_NS):
            if inp.get("semantic") == "POSITION":
                array = sources[inp.get("source").lstrip("#")].find("c:float_array", COLLADA_NS)
                values = [float(v) for v in array.text.split()]
                return [tuple(values[i : i + 3]) for i in range(0, len(values), 3)]
    raise RuntimeError(f"geometry {geometry_id} not in {dae_path}")


# --- Blender side -----------------------------------------------------------------------

#: r7: the wall-clock Blender stamps into every Collada ``<asset>`` block, pinned.
DAE_CLOCK = "2026-09-06T00:00:00"
#: r12: how far a printed vertex may sit from the module's float64 value. Blender keeps
#: float32 and its Collada exporter prints seven significant digits, so a coordinate under
#: 2,048 m is written to 1e-3 m; the r12 export measured 0.00057 m at worst.
EXPORT_ROUNDING_M = 1.0e-3


def _pin_dae_clock(dae_path: Path) -> int:
    """Replace Blender's ``<created>``/``<modified>`` with a fixed stamp. Returns 2.

    **A defect r7 found by looking, and that stood unnoticed through six rounds.** Two
    independent Blender 4.5.4 exports of the identical mesh produce DIFFERENT FILES:
    ``8cabe990...`` and ``b51df3be...`` fifteen minutes apart. Diffed, they differ in
    exactly two lines - ``<created>`` and ``<modified>`` in the ``<asset>`` block, which
    the exporter fills with the wall clock. Every other byte - every vertex, every UV,
    the material, the node tree - is identical, so the MESH was always reproducible and
    the FILE never was, and no round noticed because no round re-exported it.

    That matters here for the first time, because the r7 cut's whole argument is a
    member-by-member diff against r6's: a shape that re-exports to different bytes cannot
    be part of one. Pinning the two lines makes the export deterministic, so
    ``r7/dae_check/`` now reproduces the shipped ``.dae`` byte for byte. LF only - the
    static gate asserts no ``\\r`` reaches the tree.
    """

    text = dae_path.read_text(encoding="utf-8")
    changed = 0
    for tag in ("created", "modified"):
        text, count = re.subn(
            rf"<{tag}>[^<]*</{tag}>", f"<{tag}>{DAE_CLOCK}</{tag}>", text, count=1
        )
        changed += count
    if changed != 2:
        raise RuntimeError(f"expected 2 Collada clock lines to pin, found {changed}")
    dae_path.write_text(text, encoding="utf-8", newline="\n")
    return changed


def _build(out_dir: Path) -> dict[str, object]:
    import bmesh  # noqa: F401  (imported for parity with the rest of the pipeline)
    import bpy

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    material = bpy.data.materials.get(BACKDROP_MATERIAL) or bpy.data.materials.new(
        BACKDROP_MATERIAL
    )
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.44, 0.42, 0.44, 1.0)

    base = bpy.data.objects.new("base00", None)
    bpy.context.collection.objects.link(base)
    start = bpy.data.objects.new("start01", None)
    bpy.context.collection.objects.link(start)
    start.parent = base

    # r12: the closed solid. The first 32,256 vertices and the first 55,296 triangles are
    # r11's front face, in r11's order; the closure follows (see the module docstring).
    vertices = solid_vertices()
    faces = solid_triangles()
    face_uvs = solid_triangle_uvs()
    mesh = bpy.data.meshes.new(BACKDROP_NODE)
    mesh.from_pydata(list(vertices), [], [list(f) for f in faces])
    mesh.update()
    if len(mesh.polygons) != len(faces):
        raise RuntimeError(f"expected {len(faces)} polygons, mesh has {len(mesh.polygons)}")
    # r9: UVs are PER LOOP, not per vertex. The ring wraps, so the last column's
    # right-hand corners carry u = 1 while sharing column 0's vertices; a per-vertex UV
    # would squeeze the whole atlas into one 0.234 deg quad.
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        corners = face_uvs[polygon.index]
        for corner, loop_index in enumerate(polygon.loop_indices):
            uv_layer.data[loop_index].uv = corners[corner]
    # r9: SMOOTH. A flat-shaded flank is a 6-band staircase; smooth-shading averages the
    # face normals per vertex and the seam is welded, so the shading is continuous all the
    # way round. Verified against the exporter in `b1/r9/blender_test/normals_probe.py`:
    # `use_smooth` makes `wm.collada_export` write per-loop normals, deduplicated.
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    # r12: the crest is an ARETE and the foot is a crease. With both edges marked sharp the
    # exporter writes split per-loop normals on the shared vertices
    # (`b1/r12/blender_test/sharp_probe.py`), so the front face's normals on all seven rows
    # are exactly r11's - in r11 both rows were boundaries and their normals were averaged
    # over the front faces only, which is what a sharp edge reproduces - and the shoulder
    # behind the crest and the skirt below the foot each start with their own normal.
    crest = crest_edge_keys()
    foot = foot_edge_keys()
    sharpened = {"crest": 0, "foot": 0}
    for edge in mesh.edges:
        a, b = edge.vertices
        key = (a, b) if a < b else (b, a)
        if key in crest:
            edge.use_edge_sharp = True
            sharpened["crest"] += 1
        elif key in foot:
            edge.use_edge_sharp = True
            sharpened["foot"] += 1
    if sharpened != {"crest": len(crest), "foot": len(foot)}:
        raise RuntimeError(f"sharpened {sharpened}, expected {len(crest)} crest + {len(foot)} foot")
    mesh.update()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(BACKDROP_NODE, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = start

    # r12: the collision mesh - the same polygons at every column (fifteen rows since
    # r14's apron), closed,
    # wound outward like the visual: what is hit IS what is seen, at every vertex. Its node
    # name is the arena convention every hearth stone and forest rock in the delivery
    # already uses (``Colmesh_<stem>-1``).
    col_vertices = colmesh_vertices()
    col_faces = colmesh_triangles()
    colmesh = bpy.data.meshes.new(COLMESH_NODE)
    colmesh.from_pydata(list(col_vertices), [], [list(f) for f in col_faces])
    colmesh.update()
    if len(colmesh.polygons) != len(col_faces):
        raise RuntimeError(
            f"expected {len(col_faces)} Colmesh polygons, mesh has {len(colmesh.polygons)}"
        )
    colmesh.materials.append(material)
    col_obj = bpy.data.objects.new(COLMESH_NODE, colmesh)
    bpy.context.collection.objects.link(col_obj)
    col_obj.parent = start

    # the stock nulldetail node: below 1 px the shape renders nothing (QB-7)
    nulldetail = bpy.data.objects.new(NULLDETAIL_NODE, None)
    bpy.context.collection.objects.link(nulldetail)
    nulldetail.parent = start

    out_dir.mkdir(parents=True, exist_ok=True)
    dae_path = out_dir / BACKDROP_DAE_NAME
    bpy.ops.object.select_all(action="DESELECT")
    for item in (base, start, obj, col_obj, nulldetail):
        item.select_set(True)
    bpy.context.view_layer.objects.active = base
    result = bpy.ops.wm.collada_export(
        filepath=str(dae_path),
        check_existing=False,
        selected=True,
        include_children=True,
        include_animations=False,
        include_all_actions=False,
        apply_modifiers=True,
        triangulate=True,
        use_texture_copies=False,
        apply_global_orientation=True,
        export_global_forward_selection="Y",
        export_global_up_selection="Z",
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"collada export did not finish: {result}")
    stamped = _pin_dae_clock(dae_path)
    parents = dae_node_parents(dae_path)
    if parents != EXPECTED_TREE:
        raise RuntimeError(f"unexpected DAE node tree: {parents}")
    materials = dae_material_names(dae_path)
    if BACKDROP_MATERIAL not in materials:
        raise RuntimeError(f"backdrop material missing from the DAE: {materials}")
    per_geometry = dae_tri_counts(dae_path)
    visual_id, colmesh_id = f"{BACKDROP_NODE}-mesh", f"{COLMESH_NODE}-mesh"
    if per_geometry.get(visual_id) != len(faces) or per_geometry.get(colmesh_id) != len(col_faces):
        raise RuntimeError(
            f"expected {len(faces)} visual + {len(col_faces)} Colmesh triangles, "
            f"DAE has {per_geometry}"
        )
    # r12 read-back: the shipped positions are the module's, in order, to within the
    # exporter's own rounding - Blender stores a vertex as float32 and prints it at seven
    # significant digits, i.e. <= 1e-3 m below 2,048 m (measured: 0.00057 m). "Bit for
    # bit" is a claim about BYTES, and it is made where bytes can be compared: against
    # r11's shipped DAE, by ``b1/r12/probe/crest_pin_r12.py`` - the same values through
    # the same exporter print the same text, so the front rows' position, normal and UV
    # tokens are identical there.
    shipped = dae_positions(dae_path, visual_id)
    if len(shipped) != len(vertices):
        raise RuntimeError(f"{len(shipped)} shipped vertices, expected {len(vertices)}")
    worst = max(
        abs(got[k] - want[k]) for got, want in zip(shipped, vertices, strict=True) for k in range(3)
    )
    if worst > EXPORT_ROUNDING_M:
        raise RuntimeError(
            f"exported positions are {worst} m off the module's, over {EXPORT_ROUNDING_M}"
        )
    volumes = mesh_volumes(vertices, faces, solid_band_of_vertex)
    col_volumes = mesh_volumes(col_vertices, col_faces, colmesh_band_of_vertex)
    if min(volumes) <= 0.0 or min(col_volumes) <= 0.0:
        raise RuntimeError(f"a ring's normals face inward: {volumes} / {col_volumes}")
    payload = dae_path.read_bytes()
    return {
        "dae": str(dae_path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "triangles": sum(per_geometry.values()),
        "triangles_per_geometry": per_geometry,
        "nodes": parents,
        "clock_lines_pinned": stamped,
        "crest_edges_sharpened": sharpened["crest"],
        "foot_edges_sharpened": sharpened["foot"],
        "positions_worst_abs_diff_from_module_m": worst,
        "exporter_rounding_m": EXPORT_ROUNDING_M,
        "terrain_ter_sha256": terrain_grid()["sha256"],
        "valley_bumps": {name: rows["bumps"][0] for name, rows in valley_floors().items()},
        "volume_m3": {spec.name: round(v, 1) for spec, v in zip(RINGS, volumes, strict=True)},
        "colmesh_volume_m3": {
            spec.name: round(v, 1) for spec, v in zip(RINGS, col_volumes, strict=True)
        },
        "visual_over_colmesh_volume": {
            spec.name: round(v / c, 4)
            for spec, v, c in zip(RINGS, volumes, col_volumes, strict=True)
        },
        **silhouette_summary(),
    }


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(json.dumps(_build(arguments.out), sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

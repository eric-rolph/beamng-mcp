"""The world's edge, made visible: B1's own brink repaint, applied OUTSIDE the frozen model.

B1 r16 (critic pass 15, B15-2) painted the last metres before the block's boundary as
``scree`` then ``rock``, so a driver sees the ground change before a 70 m fall to the
backdrop's gutter. r16 wrote that repaint INTO ``terrain_model.py``, which is vendored
byte-for-byte from the frozen design spec (``level_design_v4.lock.json``), and the frozen-spec
gate failed. The orchestrator's r17 ruling: keep the safety fix AND the byte identity by
moving the repaint here. Critic pass 16 proved the move byte-neutral: the frozen model's grid
plus this function yields the ``.ter`` sha256
``8e354091c24e30c6fafdb9e9b7a2c57e84e2cc75714ede3322e81db37569fad6``, identical to r16's
shipped member (``b1/critic_r16/move_the_repaint_mine.json``).

Every reader of the grid must go through :func:`terrain_io.grid`, which applies this
repaint once and memoises the result; a module that calls ``terrain_model.get_grid()``
directly sees the world WITHOUT the band.

It is painted where the hazard IS and nowhere else: ``BRINK_FALL_M`` is measured against
the gutter's floor, so on the bearings where the block runs into the mountain and a car
simply drives off a kerb there is no band, and the band therefore tells the truth rather
than ringing the world. ``rock`` is chosen for the last metres because it is what is
actually under the lip, and because it is the strongest cue the shipped textures can give
at a driver's range: detail-map luma ``forest_floor`` 0.5176, ``scree`` 0.4600, ``rock``
0.3487. The far base map is flattened to 0.4260 / 0.4154 / 0.4064 and carries almost no
cue at all (``r16/foot/brink_r16.json``).

Critic pass 16 (B16-2) also showed that r16's "the drop is now visible" frame evidence was
an exposure artefact - net of a byte-identical control wall the ground moved the wrong way.
The repaint is real (119,925 nodes, 0 heights moved); driver visibility is NOT established
and is recorded as debt, not claimed here.

Coverage consequence, recorded as a design amendment (``authoring/design_amendments.md``):
``forest_floor`` 68.95590 % -> 66.14223 %, ``scree`` 2.15650 % -> 4.02875 %, ``rock``
9.34701 % -> 10.28843 %; the other eight layers move by 0.00000 pp.

``BACKDROP_GUTTER_Z`` is ``blender_backdrop.Z_BASE``. It is repeated rather than imported
because ``blender_backdrop`` imports the terrain model and the cycle is not worth breaking
for one float; ``tests/test_hot_potato_level_scaffold.py`` asserts the two are equal.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from examples.hot_potato_arena.level import terrain_model

BACKDROP_GUTTER_Z = 140.0
BRINK_FALL_M = 8.0  # a fall this deep is a hazard, not a step: about two storeys
BRINK_SCREE_M = 18.0  # talus from 18 m out to the rock lip
BRINK_ROCK_M = 6.0  # bare rock in the last 6 m before the ground ends


def apply_brink(layers: np.ndarray, zq: np.ndarray, xs: Any, ys: Any) -> np.ndarray:
    """Return a COPY of ``layers`` with the brink band painted; ``layers`` is not touched.

    The frozen model memoises its grid, so the caller's array is shared with every other
    reader - mutating it in place would paint the band into the "unpainted" arm of any
    control as well.
    """

    X, Y = np.meshgrid(np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64))
    out = np.array(layers, copy=True)
    edge = terrain_model.edge_distance(X, Y)
    z = np.asarray(zq, dtype=np.float64)
    brink = (z - BACKDROP_GUTTER_Z > BRINK_FALL_M) & (edge <= BRINK_SCREE_M)
    out[brink] = terrain_model.LAYER_ID["scree"]
    out[brink & (edge <= BRINK_ROCK_M)] = terrain_model.LAYER_ID["rock"]
    return out


def painted_grid(grid: dict[str, Any]) -> dict[str, Any]:
    """A shallow copy of the model's grid dict whose ``layers`` carry the band."""

    out = dict(grid)
    out["layers"] = apply_brink(grid["layers"], grid["zq"], grid["xs"], grid["ys"])
    return out

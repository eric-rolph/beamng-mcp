"""D5 gate: P0.2's free-chute asserts, moved into the test suite.

THE GAP. ``assert_no_clean_column`` and ``assert_no_two_contact_rest`` are the
two proofs that the board has no free chute and no two-contact rest. They live
in ``blender/create_pachinko_tower.py`` and were called only from ``main()``,
i.e. only inside a Blender build - so ``grep -rn clean_column tests/`` returned
nothing and the strongest geometric arguments in the project were not among the
suite's tests. A proof that only runs during a build is a proof that runs when
nobody is looking for a counterexample.

WHY THIS FILE STILL DOES NOT IMPORT THE GENERATOR. ``create_pachinko_tower.py``
used to call ``main()`` at module level (last line of the file) so that
Blender's ``--background --python`` invocation ran it on import - and so did
every other importer. Importing it from a test therefore attempted a full
build: it would rewrite the DAEs, the jbeam, the materials and the dist zip.
That is not a hypothetical - it is exactly the sequence that destroyed the
in-repo baseline on 2026-08-18 at 03:49. That call now sits behind
``if __name__ == "__main__":``, as it does in all 19 generators, pinned
pack-wide by ``test_generator_is_import_safe`` in test_giant_props_pack.py.

Extraction stays anyway, because the guard removed the SIDE EFFECT and not the
DEPENDENCY: the generator imports ``bpy`` at module level, so a plain import
still fails outside Blender. Executing one vetted node at a time remains the
only way to reach these asserts from the suite.

So the two asserts are reached by EXTRACTION instead. The module is parsed with
``ast``; every top-level ``def`` and simple assignment is executed on its own,
and nothing else is. Executing a ``def`` binds a name and never runs the body,
so even the functions that need ``bpy`` are safe to define - they simply must
not be called. The two asserts depend only on ``spec`` and ``math``, which is
what makes this possible and is a property worth keeping: if a future edit
makes them reach for ``bpy``, this file fails and says so.

The compile step must carry ``from __future__ import annotations``' flag. The
generator's signatures are annotated with ``bpy.types.Object``; without the
flag those annotations are evaluated at definition time and every ``def``
raises NameError.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import math
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_DIR = PACK_ROOT / "pachinko_tower"
GENERATOR = MOD_DIR / "blender" / "create_pachinko_tower.py"

# An assignment mentioning any of these is skipped rather than executed: this
# file's whole safety argument is that nothing with a side effect runs.
BLOCKED = ("bpy", "bmesh", "mathutils", "bk.", "open(", "write", "Path(")


@pytest.fixture(scope="module")
def spec():
    loader = importlib.util.spec_from_file_location("pachinko_spec_free_chute", MOD_DIR / "spec.py")
    module = importlib.util.module_from_spec(loader)
    sys.modules[loader.name] = module
    loader.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator(spec):
    """The generator's pure functions, without the generator's side effects."""

    source = GENERATOR.read_text(encoding="utf-8")
    flags = __import__("__future__").annotations.compiler_flag
    namespace: dict[str, object] = {"math": math, "spec": spec}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            pass  # defining is safe: the body does not run
        elif isinstance(node, ast.Assign):
            segment = ast.get_source_segment(source, node) or ""
            if any(token in segment for token in BLOCKED):
                continue
        else:
            continue  # imports, the module docstring, and the __main__ guard
        try:
            exec(  # noqa: S102 - executing one vetted node at a time is the point
                compile(ast.Module(body=[node], type_ignores=[]), str(GENERATOR), "exec", flags),
                namespace,
            )
        except NameError:
            # A path constant built from another path constant we skipped. The
            # asserts under test do not read any of them.
            continue
    for name in ("assert_no_clean_column", "assert_no_two_contact_rest", "rank_runs"):
        assert name in namespace, f"{name} was not extracted from the generator"
    return namespace


def _run(namespace: dict, name: str) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        namespace[name]()
    return buffer.getvalue()


# --------------------------------------------------------------------------
# The proofs themselves.
# --------------------------------------------------------------------------
def test_no_clean_column(generator):
    """No 2.0 m lane clears two consecutive ranks - vertical, drifting, or ballistic."""

    report = _run(generator, "assert_no_clean_column")
    assert "no vertical lane over any consecutive pair" in report


def test_no_two_contact_rest(generator):
    _run(generator, "assert_no_two_contact_rest")


# --------------------------------------------------------------------------
# D5: the ballistic sweep must cover the WHOLE achievable launch band.
# --------------------------------------------------------------------------
def test_the_ballistic_sweep_covers_the_whole_eject_band(generator, spec):
    """It has been under-derived twice, and the second fix was still wrong.

    Round one swept ONE speed, out of ``eject_speed_max_mps``, and called the
    result "the whole physical launch family". D5 widened that to the eject
    CLAMP band [10.74, 11.35]. Both stopped at the eject field - but THE
    KICKER fires at exactly the point the launch is being derived from and
    ADDS to it, up to ``lip_kick_scale_max`` x (4.0 inboard, 2.6 up) on top of
    the clamped 4.5. The lip bound is therefore 11.667 m/s and the apron exit
    reaches 15.645, 37.8% above the band that was being swept.

    Every endpoint below is derived from BEHAVIOR rather than typed, so this
    test tracks the machine: re-tune the kicker and the sweep must follow.
    """

    v_clamp = spec.BEHAVIOR["eject_speed_max_mps"]
    assert spec.BEHAVIOR["eject_speed_mps"] <= v_clamp
    kick = spec.BEHAVIOR["lip_kick_scale_max"]
    v_lip = math.hypot(
        v_clamp + kick * spec.BEHAVIOR["lip_kick_x_mps"],
        kick * spec.BEHAVIOR["lip_kick_z_mps"],
    )
    assert v_lip > v_clamp, (
        "the kicker no longer adds to the eject field - if it has been deleted "
        "this test is asserting the wrong bound"
    )
    drop = spec.APRON_Z_HI - spec.APRON_Z_LO
    lo = math.sqrt(2 * 9.81 * drop)
    hi = math.sqrt(v_lip**2 + 2 * 9.81 * drop)
    assert (round(v_lip, 3), round(lo, 3), round(hi, 3)) == (11.667, 10.424, 15.645)
    assert hi > math.sqrt(v_clamp**2 + 2 * 9.81 * drop), (
        "the kicker-derived band is no wider than the clamp-only band it "
        "replaced, which means the kicker has stopped being accounted for"
    )

    report = _run(generator, "assert_no_clean_column")
    assert f"|v| {lo:.3f}-{hi:.3f} m/s" in report, (
        "the ballistic sweep does not report the kicker-derived band; if it "
        "sweeps the eject clamp alone again, it is under-derived by 37.8%"
    )
    assert "both signs of vz0" in report, (
        "vz0 was forced negative for two rounds, so the one launch the kicker "
        "exists to produce - the car going UP over the convex break - was the "
        "one launch never swept"
    )
    assert "ballistic from the deck lip" in report, (
        "only the apron slide is swept; the kicker's whole job is to throw the "
        "car airborne over the lip, so free flight from the lip is the case "
        "that must not be assumed away"
    )


def test_the_headline_counts_are_measured_not_typed(generator):
    """The build log's headline used to be a hardcoded zero.

    ``f"... all {len(ranks)} ranks: 0 of {len(slopes)} slopes"`` printed a
    literal 0, correct only because the ``raise`` above it fires first. A
    number that cannot be wrong is not a measurement. The margin ladder is
    checked here too: the verdict alone gives no warning before the assert.
    """

    report = _run(generator, "assert_no_clean_column")
    assert "all 8 ranks: 0 of 6001 slopes" in report
    assert "margin: a diagonal survives" in report, (
        "the report gives a verdict and no margin, so a change costing one "
        "rank of closure jumps straight from '0 of 6001' to a firing assert"
    )
    assert "cross-checks:" in report and "VERTICAL path only" in report, (
        "the march cross-check must say what it does and does not cover"
    )


def test_both_span_families_are_swept(generator):
    """The projected span and the lower-edge span.

    On the shipped lattice a peg is a vertical prism so the two are identical
    by construction and the second pass proves the plumbing rather than a new
    fact. That is worth asserting precisely because it is easy to report as
    two independent results - it is one computation run twice, today.
    """

    report = _run(generator, "assert_no_clean_column")
    assert "projected span" in report and "lower-edge span" in report


# --------------------------------------------------------------------------
# The mutation check: the proof must be able to fail.
# --------------------------------------------------------------------------
def test_a_degenerate_lattice_trips_the_clean_column_assert(generator, spec, monkeypatch):
    """A tripwire that cannot fire is a comment with an assert in front of it.

    Every rank is replaced by the same pair of runs, leaving one identical
    car-wide gate at every height - i.e. a free chute straight down the middle,
    the exact thing the stagger exists to prevent.
    """

    edge = spec.FIELD_HW + 1.0
    monkeypatch.setattr(spec, "peg_row_runs", lambda rank: [(-edge, -4.0), (4.0, edge)])
    with pytest.raises(AssertionError, match="clean vertical column"):
        _run(generator, "assert_no_clean_column")


def test_the_real_lattice_still_passes_after_the_mutation(generator):
    """monkeypatch is undone between tests; this catches a leaked patch."""

    _run(generator, "assert_no_clean_column")


# --------------------------------------------------------------------------
# The positive controls, moved in from scratchpad.
#
# They lived in scratchpad/p0/p02_probe2.py and p02_diag.py, which nothing
# re-runs: a one-off, not a guard. Three of them were also broken in a way
# that read as a pass - two fired on the VERTICAL assert without ever
# reaching the code they claimed to be isolating, and one was an identity
# copy that could not fire at all. Each control below asserts the MESSAGE, so
# firing on the wrong assert is a failure rather than a tick.
# --------------------------------------------------------------------------
def _shifted_odd_rows(spec):
    """The historic left-wall lane: odd rows moved onto the even ones."""

    return lambda rank: sorted(
        (x - spec.PEG_R, x + spec.PEG_R)
        for x in (
            [v + spec.PEG_OFFSET_X for v in spec.peg_row_xs(rank)]
            if rank % 2
            else spec.peg_row_xs(rank)
        )
    )


def test_control_the_historic_left_wall_lane_fires_the_vertical_assert(
    generator, spec, monkeypatch
):
    runs = _shifted_odd_rows(spec)
    monkeypatch.setitem(generator, "rank_runs", runs)
    monkeypatch.setitem(generator, "rank_runs_lower_edge", runs)
    with pytest.raises(AssertionError, match="clean vertical column"):
        _run(generator, "assert_no_clean_column")


def test_control_a_defect_in_the_lower_edge_span_alone_is_caught(
    generator, spec, monkeypatch
):
    """The second pass must not be a no-op.

    The scratchpad control for this returned ``spec.peg_row_runs(rank)``
    unchanged - an identity copy described as "shifted 1.0 m". It could not
    fire. Here the PROJECTED span is the real, clean lattice and only the
    LOWER EDGE is defective, so the assert can only fire if the second pass
    genuinely runs, and its message has to name that span.
    """

    monkeypatch.setitem(generator, "rank_runs", spec.peg_row_runs)
    monkeypatch.setitem(generator, "rank_runs_lower_edge", _shifted_odd_rows(spec))
    with pytest.raises(AssertionError, match=r"clean vertical column.*lower-edge span"):
        _run(generator, "assert_no_clean_column")


def test_control_a_straight_diagonal_fires_the_diagonal_assert(
    generator, spec, monkeypatch
):
    """One gate per rank, centred on a straight line, too narrow to fall down.

    Shearing the real lattice cannot produce this control and it is worth
    knowing why: a periodic pitch-7.6 pattern needs a per-row shift of at
    least the 3.4 m eroded gate to break the vertical proof, i.e. |s| >= 0.85,
    and 0.85 m/m over 28 m of drop is 23.8 m of drift across a 24 m field. The
    scratchpad's "thin-pin diagonal" control fired on the VERTICAL assert for
    a related reason and so never executed a line of the diagonal code.
    """

    def runs(rank):
        x = 0.25 * (spec.PEG_ROW_Z[0] - spec.PEG_ROW_Z[rank])
        edge = spec.FIELD_HW + 1.0
        return [(-edge, x - 1.06), (x + 1.06, edge)]

    monkeypatch.setitem(generator, "rank_runs", runs)
    monkeypatch.setitem(generator, "rank_runs_lower_edge", runs)
    with pytest.raises(AssertionError, match="straight diagonal of slope"):
        _run(generator, "assert_no_clean_column")


def test_control_an_achievable_parabola_fires_the_ballistic_assert(
    generator, spec, monkeypatch
):
    """No straight line threads it; exactly one achievable launch does.

    A parabola is strictly convex, so a lattice whose only gates sit on one
    trajectory cannot be threaded by any straight line - which is what makes
    this an isolation of the ballistic block rather than another diagonal
    control. The scratchpad version used a SINGLE rank, and ``admits([0])``
    admits every slope, so it fired on the diagonal assert instead.
    """

    vx, vz0 = -6.50, -8.40
    assert math.hypot(vx, vz0) > math.sqrt(2 * 9.81 * (spec.APRON_Z_HI - spec.APRON_Z_LO))

    def runs(rank):
        edge = spec.FIELD_HW + 1.0
        if spec.PEG_ROW_Z[rank] >= spec.APRON_Z_LO:
            return [(-edge, edge)]
        fall = spec.APRON_Z_LO - spec.PEG_ROW_Z[rank]
        vz = -math.sqrt(vz0**2 + 2 * 9.81 * fall)
        x = spec.APRON_X_LO + vx * (vz - vz0) / -9.81
        return [(-edge, x - 1.06), (x + 1.06, edge)]

    monkeypatch.setitem(generator, "rank_runs", runs)
    monkeypatch.setitem(generator, "rank_runs_lower_edge", runs)
    with pytest.raises(AssertionError, match="physically achievable"):
        _run(generator, "assert_no_clean_column")


def test_the_per_pair_diagonal_ratchet_is_live(generator, monkeypatch):
    """The pair counts were printed and asserted by nothing.

    DESIGN.md calls the equivalent number on the replacement gauge "the one
    number that carries the argument"; a change could have taken a pair from
    5398 to 6001 and the build would have passed. A pair count above the
    ceiling with the whole-board invariant still holding is not constructible
    by hand on this geometry, so the ratchet is exercised from the other side:
    the board is left exactly as shipped and the ceiling is dropped by one.
    """

    assert generator["DIAGONAL_PAIR_CEILING"] == 5398
    monkeypatch.setitem(generator, "DIAGONAL_PAIR_CEILING", 5397)
    with pytest.raises(AssertionError, match="above the recorded ceiling"):
        _run(generator, "assert_no_clean_column")

"""D6 gate: the pachinko cage digest, as three literals.

WHY THIS FILE EXISTS - AND WHY THE PREVIOUS EVIDENCE DID NOT COUNT.

On 2026-08-18 at 03:49 a build sequence rewrote this mod's jbeam, materials,
runtime.lua, 34 sounds and ``dist/pachinko_tower_ericrolph.zip`` - destroying
the only in-repo baseline. The round then argued "nothing was lost" from the
fact that a regenerated cage matched the shipped jbeam. That argument is
CIRCULAR: the shipped jbeam is derived from that same regeneration, so
``test_handoff_hashes_match_daes`` and ``test_jbeam_matches_handoff`` would
have passed identically on a silently corrupted rebuild. They check internal
consistency, which a corrupted rebuild also has.

Nor could hashing have settled it. The DAE exporter is NOT deterministic - it
stamps wall-clock ``<created>`` times and carries last-ULP float jitter - so a
hash taken after the write proves only that the write happened.

What actually settles it is a baseline from OUTSIDE the rebuild, and one
exists: the installed archive in the player's live BeamNG profile,
``…/BeamNG.drive/current/mods/pachinko_tower_ericrolph.zip``, 40,620,733 bytes,
stamped 2026-08-15 01:32:49 - predating the incident by three days and written
by a different build. That file is the reference; it is deliberately NOT read
by this test, because a unit test must not reach into the user's live profile.

IT WAS READ ONCE, BY HAND, AND IT SETTLES THE QUESTION. Comparing that archive's
jbeam against the working tree's:

    node ids                    identical, 1382 of 1382
    beam id-pairs               identical, 4503
    triangle id-triples         identical, 4698
    nodes with any coordinate change      12 of 1382
    and all twelve are ``…_hood_1342`` … ``…_hood_1353``, each moved
    (0, 0, +2.100) m - which is HOOD_CLEAR 3.40 -> 5.50 exactly

So the ONLY structural difference between the pre-incident build and the
rebuild is the change P0.6 intended to make. Nothing was lost. That is an
argument from an artifact the rebuild could not have touched, which is what the
circular version lacked.

So this file does the one thing that was missing and is cheap: it PINS THE
CAGE. Before today the triple 1382 / 4503 / 4698 was asserted nowhere - the
pack suite only checks the jbeam against the handoff, i.e. one derived artifact
against another. Three literals here mean the next rebuild that quietly drops a
peg row, a divider or a wall panel fails a test instead of shipping.

The numbers are TRIPWIRES, not requirements. Geometry is allowed to change -
Phase 1 deletes the peg lattice outright and these will all move. Editing them
is fine; editing them WITHOUT NOTICING is the thing being prevented. When you
change them, add a dated line to the table below, the way
``test_giant_props_pack.py`` records its MOD_KEYS bumps.

    2026-08-18  1382 / 4503 / 4698   pinned by D6, from the 03:49 rebuild
"""

from __future__ import annotations

import json
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_ID = "ericrolph_pachinko_tower"
JBEAM_PATH = PACK_ROOT / "pachinko_tower" / "mod" / "vehicles" / MOD_ID / f"{MOD_ID}.jbeam"

CAGE_NODES = 1382
CAGE_BEAMS = 4503
CAGE_TRIANGLES = 4698


def reject_constants(value: str):
    """NaN/Infinity in a jbeam is a silently broken cage. House pattern."""

    raise AssertionError(f"non-finite constant in jbeam: {value}")


def _part() -> dict:
    jbeam = json.loads(JBEAM_PATH.read_text(encoding="utf-8"), parse_constant=reject_constants)
    assert list(jbeam) == [MOD_ID], f"jbeam declares parts {list(jbeam)}, not just {MOD_ID}"
    return jbeam[MOD_ID]


def _rows(section: str) -> list:
    """Every row after the header, and a check that the header is a header.

    Each section's first row names the columns (``["id","posX",…]``); counting
    it would inflate every number by one, and doing that consistently would
    make the inflation invisible. The section is also asserted to be free of
    dict rows (jbeam's inline property-modifier form), because those are not
    nodes/beams/triangles and would corrupt the count in the other direction.
    """

    rows = _part()[section]
    header = rows[0]
    assert isinstance(header, list) and all(isinstance(name, str) for name in header), (
        f"{section}[0] is {header!r}, not a column header - the -1 below is wrong"
    )
    body = rows[1:]
    non_lists = [row for row in body if not isinstance(row, list)]
    assert not non_lists, (
        f"{section} carries {len(non_lists)} non-list rows (jbeam property "
        "modifiers); the count is no longer a simple length"
    )
    return body


def test_cage_node_count() -> None:
    assert len(_rows("nodes")) == CAGE_NODES


def test_cage_beam_count() -> None:
    assert len(_rows("beams")) == CAGE_BEAMS


def test_cage_triangle_count() -> None:
    assert len(_rows("triangles")) == CAGE_TRIANGLES


def test_the_cage_is_one_part_with_the_sections_a_cage_needs() -> None:
    """A rebuild that dropped a whole section would otherwise KeyError deep in
    the pack suite rather than failing here with the reason on the line."""

    part = _part()
    for section in ("nodes", "beams", "triangles"):
        assert section in part, f"the shipped jbeam has no {section} section at all"


def test_every_beam_and_triangle_names_a_node_that_exists() -> None:
    """Connectivity, checked against the SHIPPED jbeam rather than the handoff.

    The pack suite checks the jbeam against the handoff it was generated from.
    This checks the artifact against itself, which is the check that survives
    the handoff being regenerated - it is what "the cage is intact" means when
    the thing you are worried about is the generator.
    """

    node_ids = {row[0] for row in _rows("nodes")}
    assert len(node_ids) == CAGE_NODES, "duplicate node ids in the shipped cage"
    dangling = set()
    for section, arity in (("beams", 2), ("triangles", 3)):
        for row in _rows(section):
            for ref in row[:arity]:
                if ref not in node_ids:
                    dangling.add((section, ref))
    assert not dangling, f"beams/triangles referencing nodes that do not exist: {sorted(dangling)}"

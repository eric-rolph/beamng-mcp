"""A seed derived from a name, stable across processes.

``hash()`` on a str is salted per interpreter process (PEP 456), so a seed built from
one is a different seed on every build. Every generator in this pack is seeded, which
made the placed objects look deterministic while each build in fact planted a different
forest and carved different rocks: comparing two CI builds of the same commit, the
terrain, heightmap and materials were bit-identical and all 24 rock meshes, all 6 shrub
meshes and the forest scatter had moved, with the instance count 9032 against 9040.

That is not a cosmetic defect. A critic round attributes a visual change to the spec
change that caused it, and it cannot do that while every rock moves between builds
whatever anyone edited.

``crc32`` is the choice here because it is stdlib, fixed by standard rather than by a
Python version, and returns an unsigned 32-bit int the existing call sites can take a
modulus of unchanged. It is not a cryptographic hash and nothing here wants one: a seed
only has to be the same number next time.

Do not reach for ``PYTHONHASHSEED`` instead. Pinning it in the workflow would make CI
reproducible and leave every local build unreproducible, which hides the defect exactly
where a person would meet it.
"""

from __future__ import annotations

import zlib


def stable_hash(name: str) -> int:
    """A non-negative int for ``name``, the same in every process and every version."""

    return zlib.crc32(name.encode("utf-8"))

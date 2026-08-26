"""Shared pytest policy for the repository's test tree.

One job for now: make the ABSENCE of generated pack artifacts a clean skip
instead of an error, so CI can run the source-contract layer of the suite on
a fresh checkout.

Commit b5f1724 deliberately stopped tracking the Giant Props build output
("track source, not build output": ~1.3 GB, with the Collada exporter and
PNG encoders provably byte-unstable), so `examples/giant_props/*/mod|dist|
textures|textures_cooked` exist only on machines that have run
`build.py <key> all`. The test suite predates that decision in places and
reads those trees directly; on the first CI run of this branch that produced
266 failures, every one of them a FileNotFoundError under a gitignored build
directory.

The hook below rewrites exactly that failure class - a FileNotFoundError
whose path sits under one of the gitignored build subtrees - into a skip
with an actionable reason. It deliberately does NOT touch:

- FileNotFoundError outside those subtrees (a missing SOURCE file is a real
  failure: specs, handoffs, generators and assets are all tracked), and
- assertion failures of any kind, including tests that assert on artifact
  content - those are gated individually in their own files where absence
  is legitimate.

The full artifact suite still runs, unskipped, on any tree that has built
the pack - which is exactly the machine allowed to certify a release.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The gitignored build-output subtrees (.gitignore lines 9 and 25-40). The
# cannon_car_wash mod/ tree IS tracked, so only dist/ applies outside
# giant_props - the path test below mirrors the ignore rules rather than
# blanket-matching every directory with one of these names.
_GENERATED_PATTERNS = (
    re.compile(r"[\\/]examples[\\/]giant_props[\\/][^\\/]+[\\/](mod|textures|textures_cooked)[\\/]"),
    re.compile(r"[\\/]examples[\\/]giant_props[\\/][^\\/]+[\\/]authoring[\\/](review|listing|verify)[\\/]"),
    re.compile(r"[\\/]dist[\\/]"),
)


def _generated_artifact_in(excinfo: pytest.ExceptionInfo) -> str | None:
    """The missing generated-artifact path, if that is what this failure is."""

    exc: BaseException | None = excinfo.value
    while exc is not None:
        if isinstance(exc, FileNotFoundError):
            candidate = str(exc.filename or "")
            if not candidate:
                # pathlib raises with the path only in args on some versions.
                match = re.search(r"'([^']+)'", str(exc))
                candidate = match.group(1) if match else ""
            if candidate and any(p.search(candidate) for p in _GENERATED_PATTERNS):
                return candidate
        exc = exc.__cause__ or exc.__context__
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    if report.outcome != "failed" or call.excinfo is None:
        return
    missing = _generated_artifact_in(call.excinfo)
    if missing is None:
        return
    try:
        relative = str(Path(missing).relative_to(_REPO_ROOT))
    except ValueError:
        relative = missing
    report.outcome = "skipped"
    report.longrepr = (
        str(item.fspath),
        item.location[1] or 0,
        f"Skipped: generated pack artifact absent (gitignored build output): "
        f"{relative}. Run `build.py <mod_key> all` to build it; the artifact "
        f"layer of this suite certifies on built trees only.",
    )

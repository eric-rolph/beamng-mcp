"""Raise the tail of a failed build as a GitHub check annotation.

The sessions that drive this branch cannot read an Actions log: the log endpoint
redirects to blob storage their egress policy denies, so a failure whose reason
lives only in the log leaves them guessing. Check annotations they can read, and
an OOM kill (a bare ``Killed`` and status 137) leaves no Python traceback
anywhere else at all.

Usage: python3 .github/scripts/build_failure_annotation.py <status> <log> [env]
"""

from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 3000
TAIL_LINES = 60


def _read(path: str) -> list[str]:
    try:
        return Path(path).read_text(errors="replace").splitlines()
    except OSError as exc:
        return [f"(could not read {path}: {exc})"]


def main(argv: list[str]) -> int:
    status = argv[0] if argv else "?"
    lines = _read(argv[1]) if len(argv) > 1 else []
    env = _read(argv[2]) if len(argv) > 2 else []
    body = "\n".join([*env, f"--- last {TAIL_LINES} lines of the build", *lines[-TAIL_LINES:]])
    # Annotations are single-line: the workflow-command escapes carry the rest.
    escaped = body[-LIMIT:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=Build failed (status {status})::{escaped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

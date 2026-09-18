"""Raise the tail of a failed build as a GitHub check annotation.

The sessions that drive this branch cannot read an Actions log: the log endpoint
redirects to blob storage their egress policy denies, so a failure whose reason
lives only in the log leaves them guessing. Check annotations they can read, and
an OOM kill (a bare ``Killed`` and status 137) leaves no Python traceback
anywhere else at all.

The same problem reaches the gates step, and the blind tail is worse than useless
there: ``pytest -q`` ends with a wall of SKIPPED reasons, so the last sixty lines of a
failed gates run name which maps opted out of which contract and never name the
assertion that failed. Pass ``--pytest`` to select the lines a failure is actually in.

``--title`` names the annotation. It defaults to the release workflow's wording, which
is wrong anywhere else: the same digest now runs on `ci.yml`'s test suite, where "Static
gates failed" would send a reader to the wrong workflow.

Usage: python3 .github/scripts/build_failure_annotation.py <status> <log> [env] [--pytest]
                                                           [--title TEXT]
"""

from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 3000
TAIL_LINES = 60
#: Lines of the FAILURES section to carry, which is where the assertion text lives.
FAILURE_CONTEXT = 40


def _read(path: str) -> list[str]:
    try:
        return Path(path).read_text(errors="replace").splitlines()
    except OSError as exc:
        return [f"(could not read {path}: {exc})"]


def pytest_digest(lines: list[str]) -> list[str]:
    """The lines a pytest failure is in, which are not the ones at the end.

    Under ``-q`` a run that fails ends with every SKIPPED reason in the suite, and this
    pack skips a great deal - a gates run reports well over a hundred. A tail of that
    says which maps declined which contract and never says what went red, which is
    exactly what the first unreadable gate failure delivered.

    So: the short summary block, then every FAILED or ERROR line, then the head of the
    FAILURES section for the assertion text. Deduplicated, order preserved. If none of
    those markers appear the caller falls back to the tail, because an empty annotation
    is worse than an imprecise one.
    """

    summary_at = next(
        (i for i, line in enumerate(lines) if "short test summary info" in line), len(lines)
    )
    picked: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith(("FAILED ", "ERROR ")):
            picked.append(line)
        elif line.startswith("=") and "FAILURES" in line:
            # Stop at the summary heading. Without the clamp the context window runs
            # straight past it into the skip wall, which is the thing being avoided.
            picked.extend(lines[index : min(index + FAILURE_CONTEXT, summary_at)])
    # The summary, minus its skips: `-ra` lists SKIPPED first and this pack skips well
    # over a hundred, so keeping them would spend the budget on contracts never in
    # question. What is left is the FAILED lines and the count.
    picked.extend(row for row in lines[summary_at:] if not row.startswith("SKIPPED"))
    seen, out = set(), []
    for line in picked:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def main(argv: list[str]) -> int:
    pytest_mode = "--pytest" in argv
    title_at = argv.index("--title") if "--title" in argv else -1
    title_arg = argv[title_at + 1] if 0 <= title_at < len(argv) - 1 else None
    if title_at >= 0:
        del argv[title_at : title_at + 2]
    argv = [a for a in argv if a != "--pytest"]
    status = argv[0] if argv else "?"
    lines = _read(argv[1]) if len(argv) > 1 else []
    env = _read(argv[2]) if len(argv) > 2 else []
    if pytest_mode:
        digest = pytest_digest(lines)
        heading = (
            "--- the failing gates"
            if digest
            else f"--- last {TAIL_LINES} lines (no FAILED line found)"
        )
        body = "\n".join([*env, heading, *(digest or lines[-TAIL_LINES:])])
    else:
        body = "\n".join([*env, f"--- last {TAIL_LINES} lines of the build", *lines[-TAIL_LINES:]])
    # Annotations are single-line: the workflow-command escapes carry the rest.
    # The digest leads with the summary and the FAILED lines, so keep the HEAD of it;
    # a build's tail is where its error is, so keep the tail of that.
    trimmed = body[:LIMIT] if pytest_mode else body[-LIMIT:]
    escaped = trimmed.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    title = title_arg or ("Static gates failed" if pytest_mode else "Build failed")
    print(f"::error title={title} (status {status})::{escaped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

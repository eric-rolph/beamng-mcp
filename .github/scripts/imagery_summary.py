"""Print each built map's imagery numbers to the job log.

The handoffs only leave the runner in `Collect release assets`, which runs AFTER the
gates and is skipped when they go red - so a red run produces every number in them and
then throws it away. That is the failure this pack keeps finding in its own pipeline
(a stage measuring something and recording it where nobody can read it), and it bites
hardest exactly when the gates are red, which is when the numbers are wanted.

Runs BEFORE the gates rather than behind `if: always()`, so a failure in this script
cannot be mistaken for a gate failure and the output is in the log either way.

Lists are skipped: `refill_check.largest` is 25 fields of a dozen keys each and would
bury everything else. Everything scalar, one level deep, is kept.
"""

from __future__ import annotations

import json
import pathlib
import sys

SCALARS = (str, int, float, bool, type(None))


def flatten(prefix: str, value, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, inner in sorted(value.items()):
            if key.startswith("_"):
                continue
            flatten(f"{prefix}.{key}" if prefix else key, inner, out)
    elif isinstance(value, SCALARS):
        out.append(f"{prefix}={value}")


def main(root: str) -> int:
    paths = sorted(pathlib.Path(root).glob("*/authoring/*.handoff.json"))
    if not paths:
        print("imagery summary: no handoffs found", file=sys.stderr)
        return 0
    for path in paths:
        try:
            handoff = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # a half-written handoff is not fatal here
            print(f"--- {path.parent.parent.name}: unreadable ({exc})")
            continue
        fields: list[str] = []
        flatten("", handoff.get("imagery") or {}, fields)
        print(f"--- imagery: {path.parent.parent.name}")
        for field in fields:
            print(f"    {field}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "examples/gis_maps"))

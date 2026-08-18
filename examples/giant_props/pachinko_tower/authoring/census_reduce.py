"""Reduce pachinko runtime telemetry into the eight-class census.

SHIPPED 2026-08-18 FOR D3. The census metric was two event keys and a comment
asking everyone to keep them apart:

    census_class     one of the eight classes, or "sensor_unknown"
    census_counted   whether the play is in the denominator at all

A repo-wide grep for those two keys returned exactly two files - spec.py and
the runtime it generates - which is to say NOTHING CONSUMED THE METRIC. A
separation that only a comment enforces is not a separation; the first readout
anybody wrote in a hurry would have summed the histogram and quietly put the
dropped plays back in the denominator. This file is that readout, written once,
correctly, so the wrong one never gets written.

It is deliberately the strict reader. Three shapes that a lenient reducer would
absorb are HARD ERRORS here, because each of them is a real defect that has
already happened once:

  1. An event carrying `census_class` with no `census_counted` companion. This
     is exactly what `pachinko_gave_up` used to do (fixed in the same round):
     a class with no gate on it, emitted for a play that ALSO emits an
     authoritative `pachinko_scored` fifteen lines later. A reducer over "every
     event with a census_class" would have double-counted every conceded play
     and read one of the two copies ungated. If that key ever comes back on a
     second event, this file stops rather than producing a number.
  2. `census_counted = false` on anything other than "sensor_unknown", or
     "sensor_unknown" on a counted play. The two travel together by
     construction; if they ever come apart, the metric is lying and a rate
     computed from it is worse than no rate.
  3. A census line on any event other than `pachinko_scored`. Payout is the one
     terminal site every play goes through - scored, conceded, timed out,
     straddled, guttered alike - so it is the only place a census line can be
     authoritative. Any other emitter is a second source of truth.

DENOMINATORS, STATED ONCE. `sensor_unknown` plays are NOT faults and NOT clean:
they are plays the sensor could not read, and they leave the census entirely.
So the fault rate is faults / counted, never faults / (counted + dropped), and
`coverage` is reported alongside it precisely so that a fault rate computed
from a session where the sensor was down half the time is visibly
untrustworthy rather than merely wrong.

THE CLASS LISTS ARE DUPLICATED HERE ON PURPOSE. This file must run against a
beamng.log on a machine that has no Blender, no proplib and no spec.py import
path, so it does not import spec.py. The duplication is not left to trust:
tests/test_pachinko_census_reduce.py asserts these tuples equal spec.py's
CENSUS_CLASSES / CENSUS_FAULT_CLASSES / CENSUS_SENSOR_UNKNOWN, so a class added
to the spec and not to this file fails the suite.

Run:  ./.venv/Scripts/python.exe \
        examples/giant_props/pachinko_tower/authoring/census_reduce.py \
        <profile>/beamng.log
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG_TAG = "ERICROLPH_PACHINKO_TOWER_RUNTIME"

# The one authoritative emitter. See (3) above.
CENSUS_EVENT = "pachinko_scored"

CENSUS_CLASSES: tuple[str, ...] = (
    "held",
    "field_hang",
    "mouth_hang",
    "shaft_hang",
    "throat_jam",
    "knife_hang",
    "clean",
    "unclassified",
)
CENSUS_FAULT_CLASSES: tuple[str, ...] = (
    "field_hang",
    "mouth_hang",
    "shaft_hang",
    "throat_jam",
    "knife_hang",
    "unclassified",
)
CENSUS_SENSOR_UNKNOWN = "sensor_unknown"


class CensusError(Exception):
    """The telemetry is malformed in a way that would corrupt the metric.

    Raised, never warned. A census that silently drops the records it did not
    understand reports a rate over a denominator nobody chose.
    """


@dataclass
class Census:
    """A reduced session. `counted` and `dropped` never mix - that is the point."""

    counted: dict[str, int] = field(default_factory=dict)
    dropped: int = 0
    duplicates_ignored: int = 0
    records_seen: int = 0

    @property
    def total_counted(self) -> int:
        return sum(self.counted.values())

    @property
    def total_plays(self) -> int:
        """Every play that produced a census line, readable or not."""

        return self.total_counted + self.dropped

    @property
    def faults(self) -> int:
        return sum(self.counted.get(name, 0) for name in CENSUS_FAULT_CLASSES)

    @property
    def fault_rate(self) -> float | None:
        """faults / COUNTED. None when nothing was counted - not 0.0.

        A zero here would read as "no faults" when what happened is "no data",
        which is the same class of lie the sensor tri-state exists to prevent.
        """

        if self.total_counted == 0:
            return None
        return self.faults / self.total_counted

    @property
    def coverage(self) -> float | None:
        """counted / (counted + dropped). How much of the session the sensor saw."""

        if self.total_plays == 0:
            return None
        return self.total_counted / self.total_plays


def parse_log(text: str) -> list[dict[str, Any]]:
    """Pull this mod's JSON telemetry records out of a beamng.log.

    Same shape as the live gates' own reader (tests/test_giant_props_live.py):
    the tag selects the lines, the first "{" starts the payload. Lines that do
    not parse are skipped rather than raised on - the log interleaves output
    from every subsystem in the game and a torn line is a logging artifact, not
    a metric defect. Malformed CENSUS records are a different matter and are
    raised on, in reduce_records.
    """

    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if LOG_TAG not in line:
            continue
        start = line.find("{")
        if start < 0:
            continue
        try:
            record = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("event"), str):
            records.append(record)
    return records


def reduce_records(records: Iterable[dict[str, Any]]) -> Census:
    """Fold census lines into a Census. Strict - see the module docstring."""

    census = Census()
    seen: set[tuple[Any, Any, Any]] = set()
    for record in records:
        has_class = "census_class" in record
        has_counted = "census_counted" in record
        if not has_class and not has_counted:
            continue
        census.records_seen += 1
        event = record.get("event")
        if has_class and not has_counted:
            raise CensusError(
                f"event {event!r} carries census_class="
                f"{record.get('census_class')!r} with no census_counted "
                "companion. An ungated class is not a census line: it cannot "
                "be told apart from a play the sensor could not read, and if "
                "the play also reaches payout it is counted twice. This is "
                "the pachinko_gave_up defect (D3, 2026-08-18) returning."
            )
        if has_counted and not has_class:
            raise CensusError(
                f"event {event!r} carries census_counted="
                f"{record.get('census_counted')!r} with no census_class"
            )
        if event != CENSUS_EVENT:
            raise CensusError(
                f"event {event!r} carries a census line, but {CENSUS_EVENT!r} "
                "is the only terminal site every play passes through and so "
                "the only emitter that can be authoritative. A second emitter "
                "is a second denominator."
            )

        counted = record["census_counted"]
        if not isinstance(counted, bool):
            raise CensusError(f"census_counted is {counted!r}, not a boolean")
        name = record["census_class"]

        # De-duplicate on the PLAY, not on the line: a log read twice, or two
        # sessions concatenated, must not double the counts. The triple is
        # unique per play because b.stats.plays increments once per play.
        key = (record.get("session"), record.get("subject_id"), record.get("plays"))
        if None not in key:
            if key in seen:
                census.duplicates_ignored += 1
                continue
            seen.add(key)

        if not counted:
            if name != CENSUS_SENSOR_UNKNOWN:
                raise CensusError(
                    f"census_counted=false on class {name!r}. Only "
                    f"{CENSUS_SENSOR_UNKNOWN!r} leaves the census; a real "
                    "class that is not counted is a play deleted from the "
                    "denominator with no reason attached."
                )
            census.dropped += 1
            continue
        if name == CENSUS_SENSOR_UNKNOWN:
            raise CensusError(
                f"{CENSUS_SENSOR_UNKNOWN!r} counted as a class. It is the "
                "absence of a classification - counting it makes a sensor "
                "outage look like a fault mode."
            )
        if name not in CENSUS_CLASSES:
            raise CensusError(
                f"census_class {name!r} is not one of the eight classes "
                f"{CENSUS_CLASSES}. Either the spec grew a class and this "
                "reducer was not updated, or the runtime is emitting a name "
                "nothing defines."
            )
        census.counted[name] = census.counted.get(name, 0) + 1
    return census


def format_census(census: Census) -> str:
    """ASCII only - this gets piped through cp1252 consoles."""

    lines = ["class            count", "----------------------"]
    for name in CENSUS_CLASSES:
        count = census.counted.get(name, 0)
        mark = " *" if name in CENSUS_FAULT_CLASSES else "  "
        lines.append(f"{name:<16} {count:>5}{mark}")
    lines.append("----------------------")
    lines.append(f"{'counted':<16} {census.total_counted:>5}")
    lines.append(f"{'dropped':<16} {census.dropped:>5}   (sensor_unknown, NOT a fault)")
    if census.duplicates_ignored:
        lines.append(f"{'duplicates':<16} {census.duplicates_ignored:>5}   (ignored)")
    rate = census.fault_rate
    coverage = census.coverage
    lines.append("")
    lines.append("* = fault class. fault rate is faults / COUNTED.")
    lines.append(
        f"faults        {census.faults}"
        + (
            f"   rate {rate * 100:.1f}%"
            if rate is not None
            else "   rate n/a (nothing counted)"
        )
    )
    lines.append(
        "coverage      "
        + (
            f"{coverage * 100:.1f}%  ({census.total_counted}/{census.total_plays} readable)"
            if coverage is not None
            else "n/a (no census lines)"
        )
    )
    if coverage is not None and coverage < 1.0:
        lines.append(
            "WARNING: the sensor did not read every play. A fault rate over a "
            "partial session is a rate over a denominator you did not choose."
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reduce pachinko telemetry into the eight-class census."
    )
    parser.add_argument("log", nargs="+", type=Path, help="beamng.log (or JSONL) to read")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    records: list[dict[str, Any]] = []
    for path in args.log:
        records.extend(parse_log(path.read_text(encoding="utf-8", errors="replace")))
    try:
        census = reduce_records(records)
    except CensusError as exc:
        print(f"CENSUS ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "counted": {name: census.counted.get(name, 0) for name in CENSUS_CLASSES},
                    "total_counted": census.total_counted,
                    "dropped": census.dropped,
                    "duplicates_ignored": census.duplicates_ignored,
                    "faults": census.faults,
                    "fault_rate": census.fault_rate,
                    "coverage": census.coverage,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(format_census(census))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

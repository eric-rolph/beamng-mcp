"""The level installer: FILETIME law, report classification, atomic copy, mods.json."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from examples.hot_potato_arena import install_level as inst


def test_filetime_is_windows_100ns_ticks_since_1601() -> None:
    # The BeamMP server wrote 134333879172577879 for the 2026-09-08 18:38 level zip; the
    # file's mtime_ns // 100 + 116444736000000000 reproduces it to the tick (measured
    # 2026-09-15, delta 0). The epoch offset alone is the well-known constant.
    assert inst.filetime_from_mtime_ns(0) == 116444736000000000
    assert inst.filetime_from_mtime_ns(1_000_000_000) == 116444736000000000 + 10_000_000
    assert inst.filetime_from_mtime_ns(123_456_789_099) == 116444736000000000 + 1_234_567_890


def _fake_release(tmp_path: Path, label: str, payload: bytes) -> dict[str, object]:
    source = tmp_path / f"{label}.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(payload)
    return {
        "label": label,
        "zip": source.name,
        "source": source,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
        "deployable": True,
    }


def test_classify_reports_missing_stale_and_current(tmp_path: Path) -> None:
    row = _fake_release(tmp_path / "dist", "level", b"release-bytes")
    target = tmp_path / "mods"
    target.mkdir()
    assert inst.classify(target, row)["state"] == "missing"
    (target / "level.zip").write_bytes(b"old-bytes")
    assert inst.classify(target, row)["state"] == "stale"
    (target / "level.zip").write_bytes(b"release-bytes")
    assert inst.classify(target, row)["state"] == "current"


def test_atomic_copy_rehashes_the_bytes_on_disk_and_leaves_no_temp(tmp_path: Path) -> None:
    source = tmp_path / "src.zip"
    source.write_bytes(b"payload")
    destination = tmp_path / "mods" / "src.zip"
    digest = inst._copy_atomic(source, destination, hashlib.sha256(b"payload").hexdigest())
    assert digest == hashlib.sha256(b"payload").hexdigest()
    assert destination.read_bytes() == b"payload"
    assert [p.name for p in destination.parent.iterdir()] == ["src.zip"]
    with pytest.raises(inst.InstallError):
        inst._copy_atomic(source, destination, "0" * 64)
    assert [p.name for p in destination.parent.iterdir()] == ["src.zip"]


def test_mods_json_lists_every_zip_with_filetime_and_keeps_protected(tmp_path: Path) -> None:
    client = tmp_path / "Client"
    client.mkdir()
    (client / "a_ericrolph.zip").write_bytes(b"aaa")
    (client / "b_ericrolph.zip").write_bytes(b"bbbb")
    (client / "mods.json").write_text(
        json.dumps(
            {"a_ericrolph.zip": {"filesize": 1, "hash": "x", "lastwrite": 1, "protected": True}}
        ),
        encoding="utf-8",
    )
    entries = inst.regenerate_mods_json(client)
    assert sorted(entries) == ["a_ericrolph.zip", "b_ericrolph.zip"]
    assert entries["a_ericrolph.zip"]["protected"] is True
    assert entries["b_ericrolph.zip"]["protected"] is False
    assert entries["b_ericrolph.zip"]["filesize"] == 4
    assert entries["b_ericrolph.zip"]["hash"] == hashlib.sha256(b"bbbb").hexdigest()
    mtime_ns = os.stat(client / "b_ericrolph.zip").st_mtime_ns
    assert entries["b_ericrolph.zip"]["lastwrite"] == inst.filetime_from_mtime_ns(mtime_ns)
    raw = (client / "mods.json").read_bytes()
    assert b"\r" not in raw
    assert json.loads(raw.decode("utf-8")) == entries
    assert any(p.name.startswith("mods.json.bak-") for p in client.iterdir())

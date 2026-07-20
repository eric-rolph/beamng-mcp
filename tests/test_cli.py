from __future__ import annotations

import json
from pathlib import Path

import pytest

from beamng_mcp.autodetect import Installation
from beamng_mcp.cli import main
from beamng_mcp.config import Settings
from beamng_mcp.services.blender import BlenderProbe


def test_serve_rejects_zero_port_before_starting_server(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["serve", "--port", "0"]) == 2
    captured = capsys.readouterr()
    assert "MCP port must be between 1 and 65535" in captured.err


def test_doctor_reports_the_probed_blender_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blender = tmp_path / "blender.exe"
    settings = Settings(blender={"executable": blender})
    installation = Installation(
        home=tmp_path / "BeamNG.drive",
        user=tmp_path / "user",
        executable=tmp_path / "BeamNG.drive" / "Bin64" / "BeamNG.drive.x64.exe",
        version="0.38",
    )
    probe = BlenderProbe(
        executable=str(blender),
        found=True,
        version="4.5.4 LTS",
        collada_export=True,
        collada_operator="wm.collada_export",
        collada_selected_only=True,
        gltf_export=True,
    )
    monkeypatch.setattr("beamng_mcp.cli._load", lambda _path: settings)
    monkeypatch.setattr("beamng_mcp.cli.detect_installation", lambda _settings: installation)
    monkeypatch.setattr("beamng_mcp.cli._gpu_info", lambda: {})
    monkeypatch.setattr("beamng_mcp.cli._vision_runtime_info", lambda: {})
    monkeypatch.setattr("beamng_mcp.cli.probe_blender_runtime", lambda *args, **kwargs: probe)

    assert main(["doctor", "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    runtime = report["softbody_authoring"]["blender_runtime"]
    assert runtime["executable"] == str(blender)
    assert runtime["version"] == "4.5.4 LTS"
    assert runtime["collada_operator"] == "wm.collada_export"
    assert runtime["compatible"] is True

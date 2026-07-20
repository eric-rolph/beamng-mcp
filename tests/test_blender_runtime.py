from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from beamng_mcp.config import Settings
from beamng_mcp.services.blender import (
    _PROBE_SOURCE,
    BlenderProbe,
    find_blender,
    probe_blender,
    probe_blender_runtime,
)


def test_blender_executable_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "Blender" / "blender.exe"
    monkeypatch.setenv("BEAMNG_MCP_BLENDER_EXECUTABLE", str(executable))

    settings = Settings.load()

    assert settings.blender.executable == executable


def test_find_blender_prefers_an_explicit_existing_executable(tmp_path: Path) -> None:
    executable = tmp_path / "Blender" / "blender.exe"
    executable.parent.mkdir()
    executable.touch()

    assert find_blender(executable) == executable.resolve()


def test_probe_blender_reports_collada_export_capabilities(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "Blender" / "blender.exe"
    executable.parent.mkdir()
    executable.touch()
    payload = {
        "version": "4.5.4 LTS",
        "collada_export": True,
        "collada_operator": "wm.collada_export",
        "collada_operator_count": 1,
        "collada_operators": ["wm.collada_export"],
        "collada_selected_only": True,
        "gltf_export": True,
    }
    marker = "BEAMNG_MCP_BLENDER_PROBE=" + json.dumps(payload)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0]
        assert isinstance(command, list)
        assert command[0] == str(executable.resolve())
        assert command[1:4] == [
            "--background",
            "--python-exit-code",
            "1",
        ]
        assert "--factory-startup" not in command
        assert "--python-expr" in command
        assert kwargs["timeout"] == 12.0
        return subprocess.CompletedProcess(command, 0, stdout=f"Blender log\n{marker}\n", stderr="")

    monkeypatch.setattr("beamng_mcp.services.blender.subprocess.run", fake_run)

    report = probe_blender(executable, timeout_seconds=12.0)

    assert report.found is True
    assert report.compatible is True
    assert report.version == "4.5.4 LTS"
    assert report.collada_operator == "wm.collada_export"
    assert report.collada_operator_count == 1
    assert report.collada_operators == ("wm.collada_export",)
    assert report.collada_selected_only is True
    assert report.gltf_export is True
    assert report.error is None


def test_probe_blender_fails_closed_when_probe_output_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "blender.exe"
    executable.touch()

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout="Blender 4.5.4\n", stderr="")

    monkeypatch.setattr("beamng_mcp.services.blender.subprocess.run", fake_run)

    report = probe_blender(executable)

    assert report.found is True
    assert report.compatible is False
    assert report.error == "probe output marker was not found"


def test_probe_blender_rejects_a_marker_from_a_failed_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "blender.exe"
    executable.touch()
    marker = "BEAMNG_MCP_BLENDER_PROBE=" + json.dumps(
        {
            "version": "4.5.4 LTS",
            "collada_export": True,
            "collada_operator": "wm.collada_export",
            "collada_selected_only": True,
            "gltf_export": True,
        }
    )

    monkeypatch.setattr(
        "beamng_mcp.services.blender.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout=marker, stderr="probe crashed"
        ),
    )

    report = probe_blender(executable)

    assert report.compatible is False
    assert report.error == "Blender capability probe exited with code 1"


def test_runtime_discovery_skips_an_incompatible_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    incompatible = tmp_path / "5.2" / "blender.exe"
    compatible = tmp_path / "4.5.4" / "blender.exe"
    incompatible.parent.mkdir()
    compatible.parent.mkdir()
    incompatible.touch()
    compatible.touch()
    monkeypatch.setattr(
        "beamng_mcp.services.blender.blender_candidates",
        lambda explicit=None: (incompatible, compatible),
    )

    def fake_probe(executable: Path, *, timeout_seconds: float = 20.0) -> BlenderProbe:
        if executable == incompatible:
            return BlenderProbe(
                executable=str(executable),
                found=True,
                version="5.2.0",
                error="selection-only Collada export unavailable",
            )
        return BlenderProbe(
            executable=str(executable),
            found=True,
            version="4.5.4 LTS",
            collada_export=True,
            collada_operator="wm.collada_export",
            collada_selected_only=True,
        )

    monkeypatch.setattr("beamng_mcp.services.blender.probe_blender", fake_probe)

    report = probe_blender_runtime(None)

    assert report.compatible is True
    assert report.executable == str(compatible)


def test_runtime_discovery_does_not_replace_an_explicit_incompatible_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit = tmp_path / "explicit" / "blender.exe"
    explicit.parent.mkdir()
    explicit.touch()
    probed: list[Path] = []

    def fake_probe(executable: Path, *, timeout_seconds: float = 20.0) -> BlenderProbe:
        probed.append(executable)
        return BlenderProbe(
            executable=str(executable),
            found=True,
            version="5.2.0",
            error="selection-only Collada export unavailable",
        )

    monkeypatch.setattr("beamng_mcp.services.blender.probe_blender", fake_probe)

    report = probe_blender_runtime(explicit)

    assert report.compatible is False
    assert report.executable == str(explicit.resolve())
    assert probed == [explicit.resolve()]


def test_probe_rejects_multiple_profile_dae_exporters(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Operator:
        def __init__(self, *properties: str) -> None:
            self._properties = [SimpleNamespace(identifier=item) for item in properties]

        def get_rna_type(self) -> SimpleNamespace:
            return SimpleNamespace(properties=self._properties)

    fake_bpy = ModuleType("bpy")
    fake_bpy.ops = SimpleNamespace(
        wm=SimpleNamespace(collada_export=Operator("filepath", "selected")),
        export_scene=SimpleNamespace(dae_export=Operator("filepath")),
    )
    fake_bpy.app = SimpleNamespace(version_string="test")
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    exec(_PROBE_SOURCE, {})  # noqa: S102 - execute the fixed in-repo probe against fake bpy

    line = capsys.readouterr().out.strip()
    payload = json.loads(line.removeprefix("BEAMNG_MCP_BLENDER_PROBE="))
    assert payload["collada_export"] is False
    assert payload["collada_operator"] is None
    assert payload["collada_operator_count"] == 2
    assert payload["collada_operators"] == ["export_scene.dae_export", "wm.collada_export"]
    assert payload["collada_selected_only"] is False


def test_probe_blender_reports_ambiguous_profile_operators(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "blender.exe"
    executable.touch()
    marker = "BEAMNG_MCP_BLENDER_PROBE=" + json.dumps(
        {
            "version": "4.5.4 LTS",
            "collada_export": False,
            "collada_operator": None,
            "collada_operator_count": 2,
            "collada_operators": ["export_scene.dae_export", "wm.collada_export"],
            "collada_selected_only": False,
            "gltf_export": True,
        }
    )
    monkeypatch.setattr(
        "beamng_mcp.services.blender.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=f"{marker}\n", stderr=""
        ),
    )

    report = probe_blender(executable)

    assert report.compatible is False
    assert report.collada_operator_count == 2
    assert report.collada_operators == ("export_scene.dae_export", "wm.collada_export")
    assert report.error == "multiple DAE export operators were found in the active profile"


@pytest.mark.parametrize(
    "missing_property",
    ["filepath", "export_format", "use_selection", "export_yup"],
)
def test_probe_rejects_gltf_without_every_deterministic_export_property(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing_property: str,
) -> None:
    class Operator:
        def __init__(self, *properties: str) -> None:
            self._properties = [SimpleNamespace(identifier=item) for item in properties]

        def get_rna_type(self) -> SimpleNamespace:
            return SimpleNamespace(properties=self._properties)

    properties = {"filepath", "export_format", "use_selection", "export_yup"}
    properties.remove(missing_property)
    fake_bpy = ModuleType("bpy")
    fake_bpy.ops = SimpleNamespace(
        export_scene=SimpleNamespace(gltf=Operator(*properties)),
    )
    fake_bpy.app = SimpleNamespace(version_string="test")
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    exec(_PROBE_SOURCE, {})  # noqa: S102 - execute the fixed probe against fake bpy

    line = capsys.readouterr().out.strip()
    payload = json.loads(line.removeprefix("BEAMNG_MCP_BLENDER_PROBE="))
    assert payload["gltf_export"] is False


def test_probe_accepts_gltf_with_every_deterministic_export_property(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Operator:
        def get_rna_type(self) -> SimpleNamespace:
            return SimpleNamespace(
                properties=[
                    SimpleNamespace(identifier=item)
                    for item in ("filepath", "export_format", "use_selection", "export_yup")
                ]
            )

    fake_bpy = ModuleType("bpy")
    fake_bpy.ops = SimpleNamespace(export_scene=SimpleNamespace(gltf=Operator()))
    fake_bpy.app = SimpleNamespace(version_string="test")
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    exec(_PROBE_SOURCE, {})  # noqa: S102 - execute the fixed probe against fake bpy

    line = capsys.readouterr().out.strip()
    payload = json.loads(line.removeprefix("BEAMNG_MCP_BLENDER_PROBE="))
    assert payload["gltf_export"] is True


def test_probe_blender_does_not_execute_a_missing_binary(tmp_path: Path) -> None:
    report = probe_blender(tmp_path / "missing" / "blender.exe")

    assert report.found is False
    assert report.compatible is False
    assert report.error == "Blender executable was not found"

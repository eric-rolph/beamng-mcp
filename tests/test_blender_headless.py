from __future__ import annotations

import json
import os
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from beamng_mcp.services.collada import inspect_collada


def _marker_payload(output: str, marker: str) -> dict[str, object]:
    line = next((item for item in output.splitlines() if item.startswith(marker)), None)
    assert line is not None, output
    payload = json.loads(line.removeprefix(marker))
    assert isinstance(payload, dict)
    return payload


@pytest.mark.blender
@pytest.mark.parametrize(
    ("case", "bounds_min", "bounds_max"),
    [
        ("identity", (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
        ("transformed", (-1.0, -2.0, -0.5), (1.0, 2.0, 0.5)),
    ],
)
def test_real_blender_exports_a_valid_softbody_handoff(
    tmp_path: Path,
    case: str,
    bounds_min: tuple[float, float, float],
    bounds_max: tuple[float, float, float],
) -> None:
    configured = os.getenv("BEAMNG_MCP_TEST_BLENDER")
    if not configured:
        pytest.skip("set BEAMNG_MCP_TEST_BLENDER to run the real Blender export smoke test")
    executable = Path(configured).resolve()
    if not executable.is_file():
        pytest.fail(f"configured Blender executable does not exist: {executable}")

    helper = Path(
        str(files("beamng_mcp").joinpath("assets", "blender", "softbody_export.py"))
    ).resolve()
    script = Path(__file__).with_name("fixtures") / "blender_softbody_smoke.py"
    completed = subprocess.run(  # noqa: S603 - explicitly configured local test binary
        [
            str(executable),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(script),
            "--",
            str(helper),
            str(tmp_path),
            case,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["node_count"] == 8
    assert result["edge_count"] == 12
    assert result["brace_panel_count"] == 6
    assert result["triangle_count"] == 12
    assert result["case"] == case
    assert result["source_state_restored"] is True

    manifest = json.loads((tmp_path / "smoke_asset.structure.json").read_text(encoding="utf-8"))
    assert manifest["visual"]["operator"] == "wm.collada_export"
    assert manifest["visual"]["coordinates_baked_to_beamng"] is True
    assert manifest["structure"]["volume_m3"] == pytest.approx(8.0)

    inspection = inspect_collada(
        (tmp_path / "smoke_asset.dae").read_bytes(),
        expected_mesh_name="smoke_asset_visual",
        expected_material_name="smoke_asset_material",
    )
    assert inspection.bounds_min == pytest.approx(bounds_min)
    assert inspection.bounds_max == pytest.approx(bounds_max)
    assert inspection.vertex_count == 8


@pytest.mark.blender
def test_real_blender_profile_registers_the_blender_mcp_addon() -> None:
    configured = os.getenv("BEAMNG_MCP_TEST_BLENDER_ADDON")
    if not configured:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BLENDER_ADDON to verify the configured Blender MCP profile"
        )
    executable = Path(configured).resolve()
    if not executable.is_file():
        pytest.fail(f"configured Blender executable does not exist: {executable}")
    script = Path(__file__).with_name("fixtures") / "blender_mcp_profile_probe.py"

    completed = subprocess.run(  # noqa: S603 - explicitly configured local test binary
        [
            str(executable),
            "--background",
            "--python-exit-code",
            "1",
            "--python",
            str(script),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    payload = _marker_payload(output, "BEAMNG_MCP_ADDON_PROBE=")
    assert payload["addon_enabled"] is True
    assert payload["addon_version"] == [1, 2]
    assert payload["panel_registered"] is True
    assert payload["start_operator_registered"] is True
    assert payload["server_running"] is False
    assert payload["server_host"] == "localhost"
    assert payload["server_port"] == 9876

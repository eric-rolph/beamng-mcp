"""Discovery and fail-closed capability probing for a local Blender runtime."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from ..assets.blender.softbody_export import (
    DAE_EXPORT_NAME_MARKERS,
    DAE_SELECTION_OPTIONS,
    GLTF_REQUIRED_OPTIONS,
)

_PROBE_MARKER: Final = "BEAMNG_MCP_BLENDER_PROBE="

_PROBE_SOURCE_TEMPLATE: Final = r"""
import bpy
import json

matches = []
name_markers = __DAE_EXPORT_NAME_MARKERS__
selection_names = set(__DAE_SELECTION_OPTIONS__)
gltf_required = set(__GLTF_REQUIRED_OPTIONS__)
for namespace_name in sorted(name for name in dir(bpy.ops) if not name.startswith("_")):
    namespace = getattr(bpy.ops, namespace_name)
    for operator_name in sorted(name for name in dir(namespace) if not name.startswith("_")):
        qualified = f"{namespace_name}.{operator_name}"
        lowered = qualified.casefold()
        if "export" not in lowered or not any(marker in lowered for marker in name_markers):
            continue
        operator = getattr(namespace, operator_name)
        try:
            properties = {
                item.identifier for item in operator.get_rna_type().properties
            }
        except Exception:
            continue
        if "filepath" in properties:
            matches.append((qualified, sorted(properties)))

gltf_properties = set()
try:
    gltf_operator = getattr(getattr(bpy.ops, "export_scene"), "gltf")
    gltf_properties = {
        item.identifier for item in gltf_operator.get_rna_type().properties
    }
except Exception:
    pass
gltf_export = gltf_required.issubset(gltf_properties)
payload = {
    "version": str(bpy.app.version_string),
    "collada_export": len(matches) == 1,
    "collada_operator": matches[0][0] if len(matches) == 1 else None,
    "collada_operator_count": len(matches),
    "collada_operators": [item[0] for item in matches[:32]],
    "collada_selected_only": (
        len(matches) == 1 and bool(set(matches[0][1]).intersection(selection_names))
    ),
    "gltf_export": bool(gltf_export),
}
print("BEAMNG_MCP_BLENDER_PROBE=" + json.dumps(payload, sort_keys=True))
"""
_PROBE_SOURCE: Final = (
    _PROBE_SOURCE_TEMPLATE.replace("__DAE_EXPORT_NAME_MARKERS__", repr(DAE_EXPORT_NAME_MARKERS))
    .replace("__DAE_SELECTION_OPTIONS__", repr(DAE_SELECTION_OPTIONS))
    .replace("__GLTF_REQUIRED_OPTIONS__", repr(GLTF_REQUIRED_OPTIONS))
)


@dataclass(frozen=True, slots=True)
class BlenderProbe:
    executable: str | None
    found: bool
    version: str | None = None
    collada_export: bool = False
    collada_operator: str | None = None
    collada_operator_count: int = 0
    collada_operators: tuple[str, ...] = ()
    collada_selected_only: bool = False
    gltf_export: bool = False
    error: str | None = None

    @property
    def compatible(self) -> bool:
        """Whether the runtime can perform the reviewed DAE handoff."""

        return self.found and self.collada_export and self.collada_selected_only

    def public_snapshot(self) -> dict[str, Any]:
        result = asdict(self)
        result["compatible"] = self.compatible
        return result


def blender_candidates(explicit: Path | None = None) -> tuple[Path, ...]:
    """Enumerate explicit or common Windows Blender binaries in preference order."""

    if explicit is not None:
        return (explicit.expanduser().resolve(),)

    candidates: list[Path] = []
    for command in ("blender", "blender.exe"):
        located = shutil.which(command)
        if located:
            candidates.append(Path(located))

    user_root = Path.home()
    candidates.extend(
        sorted(
            (user_root / "Applications" / "Blender").glob("*/blender.exe"),
            reverse=True,
        )
    )
    local_app_data = Path(os.getenv("LOCALAPPDATA", user_root / "AppData" / "Local"))
    candidates.extend(
        sorted(
            (local_app_data / "Programs" / "Blender Foundation").glob("*/blender.exe"),
            reverse=True,
        )
    )
    program_files = Path(os.getenv("ProgramFiles", "C:/Program Files"))
    candidates.extend(
        sorted(
            (program_files / "Blender Foundation").glob("*/blender.exe"),
            reverse=True,
        )
    )

    found: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            found.append(resolved)
    return tuple(found)


def find_blender(explicit: Path | None = None) -> Path | None:
    """Resolve the first explicit or conservatively discovered Blender binary."""

    candidates = blender_candidates(explicit)
    return candidates[0] if candidates else None


def probe_blender(executable: Path, *, timeout_seconds: float = 20.0) -> BlenderProbe:
    """Inspect Blender in background mode with its active user profile loaded."""

    resolved = executable.expanduser().resolve()
    if not resolved.is_file():
        return BlenderProbe(
            executable=str(resolved),
            found=False,
            error="Blender executable was not found",
        )

    command = [
        str(resolved),
        "--background",
        "--python-exit-code",
        "1",
        "--python-expr",
        _PROBE_SOURCE,
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - operator-selected local executable
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return BlenderProbe(
            executable=str(resolved),
            found=True,
            error="Blender capability probe timed out",
        )
    except OSError as exc:
        return BlenderProbe(
            executable=str(resolved),
            found=True,
            error=f"Blender capability probe failed: {type(exc).__name__}",
        )

    if completed.returncode != 0:
        return BlenderProbe(
            executable=str(resolved),
            found=True,
            error=f"Blender capability probe exited with code {completed.returncode}",
        )

    marker_line = next(
        (line for line in completed.stdout.splitlines() if line.startswith(_PROBE_MARKER)),
        None,
    )
    if marker_line is None:
        error = (
            f"Blender capability probe exited with code {completed.returncode}"
            if completed.returncode
            else "probe output marker was not found"
        )
        return BlenderProbe(executable=str(resolved), found=True, error=error)

    try:
        payload = json.loads(marker_line.removeprefix(_PROBE_MARKER))
        if not isinstance(payload, dict):
            raise TypeError
    except (json.JSONDecodeError, TypeError):
        return BlenderProbe(
            executable=str(resolved),
            found=True,
            error="Blender capability probe returned invalid JSON",
        )

    raw_operators = payload.get("collada_operators")
    if isinstance(raw_operators, list):
        collada_operators = tuple(
            item for item in raw_operators[:32] if isinstance(item, str) and 1 <= len(item) <= 128
        )
    else:
        single_operator = payload.get("collada_operator")
        collada_operators = (single_operator,) if isinstance(single_operator, str) else ()
    raw_count = payload.get("collada_operator_count")
    collada_operator_count = (
        raw_count
        if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count >= 0
        else len(collada_operators)
    )
    selected_only = payload.get("collada_selected_only") is True
    probe_error: str | None = None
    if collada_operator_count == 0:
        probe_error = "no DAE export operator was found in the active profile"
    elif collada_operator_count > 1:
        probe_error = "multiple DAE export operators were found in the active profile"
    elif not selected_only:
        probe_error = "the DAE export operator has no selection-only option"

    return BlenderProbe(
        executable=str(resolved),
        found=True,
        version=str(payload["version"]) if payload.get("version") is not None else None,
        collada_export=payload.get("collada_export") is True,
        collada_operator=(
            str(payload["collada_operator"])
            if payload.get("collada_operator") is not None
            else None
        ),
        collada_operator_count=collada_operator_count,
        collada_operators=collada_operators,
        collada_selected_only=selected_only,
        gltf_export=payload.get("gltf_export") is True,
        error=probe_error,
    )


def probe_blender_runtime(explicit: Path | None, *, timeout_seconds: float = 20.0) -> BlenderProbe:
    """Probe candidates until one satisfies the reviewed DAE capability contract."""

    candidates = blender_candidates(explicit)
    if not candidates:
        return BlenderProbe(
            executable=None,
            found=False,
            error="Blender executable was not found",
        )
    first_report: BlenderProbe | None = None
    for candidate in candidates:
        report = probe_blender(candidate, timeout_seconds=timeout_seconds)
        if first_report is None:
            first_report = report
        if report.compatible:
            return report
    assert first_report is not None
    return first_report

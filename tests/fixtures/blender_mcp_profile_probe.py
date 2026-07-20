"""Report Blender MCP registration from the active Blender user profile."""

from __future__ import annotations

import importlib
import json

import bpy


def main() -> None:
    module_name = "blender_mcp_addon"
    enabled = module_name in bpy.context.preferences.addons
    module = importlib.import_module(module_name) if enabled else None
    payload = {
        "version": str(bpy.app.version_string),
        "addon_enabled": enabled,
        "addon_file": str(module.__file__) if module is not None else None,
        "addon_version": list(module.bl_info["version"]) if module is not None else None,
        "panel_registered": hasattr(bpy.types, "BLENDERMCP_PT_Panel"),
        "start_operator_registered": "start_server" in dir(bpy.ops.blendermcp),
        "server_running": bool(getattr(bpy.context.scene, "blendermcp_server_running", False)),
        "server_host": getattr(bpy.types, "blendermcp_server", None).host if module else None,
        "server_port": getattr(bpy.types, "blendermcp_server", None).port if module else None,
    }
    print("BEAMNG_MCP_ADDON_PROBE=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

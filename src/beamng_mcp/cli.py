"""Command-line entry point for serving, installing, and diagnosing BeamNG MCP."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import logging
import shutil
import subprocess
import sys
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

from . import __version__
from .autodetect import detect_installation
from .config import Settings
from .errors import BeamNGMCPError, ConfigurationError
from .installer import BRIDGE_CONFIG, MOD_DIRECTORY, discover_lua_token, install_lua_bridge
from .mcp_adapter import BearerAuthMiddleware, create_mcp_server
from .services.mods import ModWorkspace


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beamng-mcp",
        description="Local MCP control plane and autonomous-driving stack for BeamNG",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the MCP server")
    serve.add_argument("--config", type=Path)
    serve.add_argument("--transport", choices=("stdio", "streamable-http"))
    serve.add_argument("--host", choices=("127.0.0.1", "localhost", "::1"))
    serve.add_argument("--port", type=int)

    doctor = subparsers.add_parser(
        "doctor", help="inspect local prerequisites without launching BeamNG"
    )
    doctor.add_argument("--config", type=Path)
    doctor.add_argument("--json", action="store_true", dest="as_json")

    install = subparsers.add_parser(
        "install-lua", help="install/update the authenticated GELua bridge"
    )
    install.add_argument("--config", type=Path)
    install.add_argument("--user", type=Path)
    install.add_argument("--port", type=int, default=8765)
    install.add_argument("--force", action="store_true")

    validate = subparsers.add_parser(
        "validate-mod", help="validate a mod in the configured workspace"
    )
    validate.add_argument("mod_name")
    validate.add_argument("--config", type=Path)

    pack = subparsers.add_parser("pack-mod", help="validate and pack a mod workspace")
    pack.add_argument("mod_name")
    pack.add_argument("--config", type=Path)

    subparsers.add_parser("client-config", help="print example MCP client configuration")
    return parser


def _load(path: Path | None) -> Settings:
    return Settings.load(path)


def _serve(args: argparse.Namespace) -> int:
    settings = _load(args.config)
    if args.transport:
        settings.mcp.transport = args.transport
    if args.host:
        settings.mcp.host = args.host
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            raise ConfigurationError("MCP port must be between 1 and 65535")
        settings.mcp.port = args.port
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp, _ = create_mcp_server(settings)
    if settings.mcp.transport == "stdio":
        mcp.run(transport="stdio")
        return 0
    if settings.mcp.http_token is None:
        raise ConfigurationError(
            "streamable-http requires mcp.http_token or BEAMNG_MCP_HTTP_TOKEN (32+ characters)"
        )
    token = settings.mcp.http_token.get_secret_value()
    if len(token) < 32:
        raise ConfigurationError("HTTP token must contain at least 32 characters")
    import uvicorn

    asgi = BearerAuthMiddleware(mcp.streamable_http_app(), token)
    uvicorn.run(asgi, host=settings.mcp.host, port=settings.mcp.port, log_level="info")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    settings = _load(args.config)
    installation = detect_installation(settings)
    bridge_path = installation.user / "mods" / "unpacked" / MOD_DIRECTORY
    token = discover_lua_token(installation.user)
    gpu = _gpu_info()
    vision_runtime = _vision_runtime_info()
    blender_helper = files("beamng_mcp").joinpath("assets", "blender", "softbody_export.py")
    report: dict[str, Any] = {
        "beamng_mcp": __version__,
        "python": sys.version.split()[0],
        "beamngpy": _package_version("beamngpy"),
        "mcp_sdk": _package_version("mcp"),
        "beamng": {
            "home": str(installation.home) if installation.home else None,
            "executable": str(installation.executable) if installation.executable else None,
            "user": str(installation.user),
            "target_version": installation.version,
            "found": installation.executable is not None,
        },
        "lua_bridge": {
            "path": str(bridge_path),
            "installed": (bridge_path / BRIDGE_CONFIG).is_file(),
            "token_configured": token is not None,
            "url": settings.lua.url,
        },
        "gpu": gpu,
        "vision_runtime": vision_runtime,
        "softbody_authoring": {
            "blender_mcp_executable": shutil.which("blender-mcp"),
            "blender_mcp_package": _package_version("blender-mcp"),
            "reviewed_helper_packaged": blender_helper.is_file(),
            "runtime_visual_format": "dae",
            "dae_operator_status": "verify in live Blender; helper fails closed if absent",
        },
        "workspace": str(settings.workspace.root.expanduser().resolve()),
        "full_feature_tier": "BeamNG.tech + BeamNGpy",
        "retail_drive_tier": "experimental GELua bridge",
    }
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"BeamNG MCP {report['beamng_mcp']} / Python {report['python']}")
        print(f"BeamNG executable: {report['beamng']['executable'] or 'not found'}")
        print(f"BeamNG user folder: {report['beamng']['user']}")
        print(
            "Lua bridge: "
            + (
                "installed and configured"
                if report["lua_bridge"]["token_configured"]
                else "not configured"
            )
        )
        print(f"GPU: {gpu.get('name') or 'not detected'}")
        torch_runtime = vision_runtime.get("torch", {})
        print(
            "PyTorch CUDA: "
            + ("available" if torch_runtime.get("cuda_available") else "unavailable")
        )
        onnx_runtime = vision_runtime.get("onnxruntime", {})
        if onnx_runtime:
            print("ONNX providers: " + ", ".join(onnx_runtime.get("providers", [])))
        helper_status = (
            "packaged" if report["softbody_authoring"]["reviewed_helper_packaged"] else "missing"
        )
        print(
            f"Soft-body Blender helper: {helper_status}; "
            "live Collada operator verification required"
        )
        print(f"BeamNGpy {report['beamngpy']} / MCP SDK {report['mcp_sdk']}")
    return 0 if installation.executable is not None else 1


def _install(args: argparse.Namespace) -> int:
    settings = _load(args.config)
    installation = detect_installation(settings)
    user_path = args.user.expanduser().resolve() if args.user else installation.user
    result = install_lua_bridge(settings, user_path=user_path, port=args.port, force=args.force)
    print(f"Installed {result.files} bridge files at {result.destination}")
    print(f"WebSocket: ws://127.0.0.1:{result.port}")
    print("Authentication token generated and stored locally (value intentionally not shown).")
    print("Connect with simulator_connect or load GELua extension beamng_mcp/bridge in-game.")
    return 0


def _validate(args: argparse.Namespace) -> int:
    workspace = ModWorkspace(_load(args.config).workspace)
    result = workspace.validate(args.mod_name)
    print(result.model_dump_json(indent=2))
    return 0 if result.valid else 2


def _pack(args: argparse.Namespace) -> int:
    workspace = ModWorkspace(_load(args.config).workspace)
    result = workspace.pack(args.mod_name)
    print(result.model_dump_json(indent=2))
    return 0


def _client_config() -> int:
    executable = str(Path(sys.executable).with_name("beamng-mcp.exe"))
    config = {
        "mcpServers": {
            "beamng": {
                "command": executable,
                "args": ["serve", "--transport", "stdio"],
            }
        }
    }
    print(json.dumps(config, indent=2))
    return 0


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _gpu_info() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {}
    try:
        completed = subprocess.run(  # noqa: S603 - read-only diagnostic executable
            [
                executable,
                "--query-gpu=name,driver_version,memory.total,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    first = completed.stdout.strip().splitlines()[0].split(",")
    if len(first) < 4:
        return {"raw": completed.stdout.strip()}
    return {
        "name": first[0].strip(),
        "driver": first[1].strip(),
        "memory_mb": int(first[2].strip()),
        "compute_capability": first[3].strip(),
    }


def _vision_runtime_info() -> dict[str, Any]:
    """Report optional local inference runtimes without importing them at server startup."""

    result: dict[str, Any] = {}
    try:
        torch = importlib.import_module("torch")
        cuda_available = bool(torch.cuda.is_available())
        torch_info: dict[str, Any] = {
            "version": str(torch.__version__),
            "cuda_available": cuda_available,
            "cuda_runtime": str(torch.version.cuda) if torch.version.cuda else None,
            "device": None,
        }
        if cuda_available:
            torch_info["device"] = str(torch.cuda.get_device_name(0))
        result["torch"] = torch_info
    except (ImportError, OSError, RuntimeError, AttributeError) as exc:
        result["torch"] = {"available": False, "error": type(exc).__name__}

    try:
        onnxruntime = importlib.import_module("onnxruntime")
        result["onnxruntime"] = {
            "version": str(onnxruntime.__version__),
            "providers": [str(item) for item in onnxruntime.get_available_providers()],
        }
    except (ImportError, OSError, RuntimeError, AttributeError) as exc:
        result["onnxruntime"] = {"available": False, "error": type(exc).__name__}

    try:
        cv2 = importlib.import_module("cv2")
        result["opencv"] = {"version": str(cv2.__version__)}
    except (ImportError, OSError, RuntimeError, AttributeError) as exc:
        result["opencv"] = {"available": False, "error": type(exc).__name__}
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args)
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "install-lua":
            return _install(args)
        if args.command == "validate-mod":
            return _validate(args)
        if args.command == "pack-mod":
            return _pack(args)
        if args.command == "client-config":
            return _client_config()
    except (BeamNGMCPError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

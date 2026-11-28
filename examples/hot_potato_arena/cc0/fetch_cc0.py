"""Fetch CC0 source assets from Poly Haven into an ignored cache with a provenance ledger.

The Hot Potato level ships only content authored in this repository or content whose
redistribution is documented (AGENTS.md, "Namespacing and official Repository policy").
Poly Haven publishes everything under CC0 1.0, which needs no attribution, but we record
the provenance of every byte anyway so a critic can re-verify it and a future re-cut can
re-fetch it: asset id, map, resolution, URL, the md5 Poly Haven publishes, the sha256 we
measured, the byte count, the authors from the /info endpoint and the download time.

Usage::

    .\\.venv\\Scripts\\python.exe examples/hot_potato_arena/cc0/fetch_cc0.py manifest.json
    .\\.venv\\Scripts\\python.exe examples/hot_potato_arena/cc0/fetch_cc0.py --list forest_floor

The manifest is a JSON list of requests::

    [{"asset": "forest_floor", "maps": ["Diffuse", "nor_gl", "Rough", "AO", "Displacement"],
      "res": "4k", "fmt": "png"},
     {"asset": "pine_tree_01", "maps": ["twig_diff", "twig_alpha", "twig_nor_gl", "twig_rough",
      "bark_diff", "bark_nor_gl", "bark_rough"], "res": "2k", "fmt": "png"},
     {"asset": "boulder_01", "file": "gltf", "res": "2k"}]

Files land in ``examples/hot_potato_arena/cc0_cache/<asset>/`` (git-ignored). The ledger
``examples/hot_potato_arena/authoring/cc0_provenance.json`` is tracked and rewritten on every
run (sorted keys, LF newlines). A file already present with the published md5 is not fetched
again. Nothing here touches the mod tree; cooking/deriving is the build scripts' job.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.polyhaven.com"
HERE = Path(__file__).resolve().parent
ARENA_ROOT = HERE.parent
CACHE_ROOT = ARENA_ROOT / "cc0_cache"
LEDGER_PATH = ARENA_ROOT / "authoring" / "cc0_provenance.json"
LICENSE = "CC0 1.0 Universal (https://creativecommons.org/publicdomain/zero/1.0/)"
SOURCE = "https://polyhaven.com"
USER_AGENT = "beamng-mcp hot_potato_arena cc0 fetcher (https://github.com/eric-rolph)"


def _open(url: str, timeout: int) -> Any:
    # Only the two https Poly Haven hosts are ever opened here; the scheme is fixed
    # by the API and download URLs the /files endpoint returns.
    if not url.startswith(("https://api.polyhaven.com/", "https://dl.polyhaven.org/")):
        raise ValueError(f"refusing to open a non-Poly-Haven URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def _get_json(url: str) -> Any:
    with _open(url, 60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with _open(url, 600) as response, partial.open("wb") as handle:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
    partial.replace(target)


def _md5(path: Path) -> str:
    # Poly Haven publishes md5 per file; it is an integrity check, not a security one.
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_ledger() -> dict[str, Any]:
    if LEDGER_PATH.is_file():
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return {"license": LICENSE, "source": SOURCE, "files": {}}


def _write_ledger(ledger: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ledger["files"] = dict(sorted(ledger["files"].items()))
    text = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    with LEDGER_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _flatten_file_entries(
    files: dict[str, Any],
    map_name: str,
    res: str,
    fmt: str | None,
    file_kind: str | None,
) -> list[tuple[str, dict[str, Any]]]:
    """Return [(relative_name, {url, size, md5})] for one map/res selection.

    Texture maps: files[map][res][fmt] -> {url, size, md5}.
    Model files:  files["gltf"][res]["gltf"] -> {url, size, md5, include: {rel: {url, size, md5}}}.
    """
    node = files.get(map_name)
    if node is None:
        raise KeyError(f"no map {map_name!r}; available: {sorted(files)}")
    if res not in node:
        raise KeyError(f"map {map_name!r} has no resolution {res!r}; available: {sorted(node)}")
    by_fmt = node[res]
    if file_kind:
        entry = by_fmt.get(file_kind) or next(iter(by_fmt.values()))
        out = [(Path(entry["url"]).name, entry)]
        for rel, inc in sorted(entry.get("include", {}).items()):
            out.append((rel, inc))
        return out
    if fmt is None:
        fmt = "png" if "png" in by_fmt else next(iter(by_fmt))
    if fmt not in by_fmt:
        raise KeyError(f"map {map_name!r} {res} has no format {fmt!r}; available: {sorted(by_fmt)}")
    entry = by_fmt[fmt]
    return [(Path(entry["url"]).name, entry)]


def fetch(manifest: list[dict[str, Any]], *, dry_run: bool = False) -> int:
    ledger = _load_ledger()
    fetched = 0
    for request in manifest:
        asset = request["asset"]
        res = request.get("res", "2k")
        info = _get_json(f"{API}/info/{asset}")
        files = _get_json(f"{API}/files/{asset}")
        authors = info.get("authors", {})
        selections: list[tuple[str, dict[str, Any], str]] = []
        if "file" in request:
            kind = request["file"]
            for rel, entry in _flatten_file_entries(files, kind, res, None, kind):
                selections.append((rel, entry, kind))
        for map_name in request.get("maps", []):
            for rel, entry in _flatten_file_entries(files, map_name, res, request.get("fmt"), None):
                selections.append((rel, entry, map_name))
        for rel, entry, map_name in selections:
            target = CACHE_ROOT / asset / rel
            key = f"{asset}/{rel}"
            if target.is_file() and _md5(target) == entry["md5"]:
                status = "cached"
            elif dry_run:
                status = "would fetch"
            else:
                _download(entry["url"], target)
                got = _md5(target)
                if got != entry["md5"]:
                    target.unlink()
                    raise RuntimeError(f"{key}: md5 {got} != published {entry['md5']}")
                status = "fetched"
                fetched += 1
            print(f"{status:11s} {key}  {entry['size'] / 1e6:8.1f} MB")
            if target.is_file():
                ledger["files"][key] = {
                    "asset": asset,
                    "map": map_name,
                    "resolution": res,
                    "url": entry["url"],
                    "md5_published": entry["md5"],
                    "sha256": _sha256(target),
                    "bytes": target.stat().st_size,
                    "authors": dict(sorted(authors.items())),
                    "asset_files_hash": info.get("files_hash"),
                    "license": LICENSE,
                    "source": SOURCE,
                    "downloaded_at": _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat(),
                }
    if not dry_run:
        _write_ledger(ledger)
    return fetched


def list_asset(asset: str) -> None:
    info = _get_json(f"{API}/info/{asset}")
    files = _get_json(f"{API}/files/{asset}")
    print(
        f"{asset}: {info.get('name')} | authors {info.get('authors')} | "
        f"polycount {info.get('polycount')} | dims(mm) {info.get('dimensions')}"
    )
    for map_name, node in sorted(files.items()):
        if not isinstance(node, dict):
            continue
        for res, by_fmt in sorted(node.items()):
            sizes = ", ".join(
                f"{fmt} {entry.get('size', 0) / 1e6:.1f} MB"
                for fmt, entry in sorted(by_fmt.items())
                if isinstance(entry, dict) and "size" in entry
            )
            print(f"  {map_name:16s} {res:4s} {sizes}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("manifest", nargs="?", help="JSON list of fetch requests")
    parser.add_argument("--list", metavar="ASSET", help="print the files Poly Haven offers")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        list_asset(args.list)
        return 0
    if not args.manifest:
        parser.error("manifest or --list required")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    fetched = fetch(manifest, dry_run=args.dry_run)
    print(f"done: {fetched} file(s) fetched; ledger {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

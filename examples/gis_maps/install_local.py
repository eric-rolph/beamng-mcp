"""One command from a checkout to the six maps installed in your BeamNG.drive.

    python examples/gis_maps/install_local.py                       # build from public data, deploy
    python examples/gis_maps/install_local.py --release gis-maps-v1 # download a GitHub Release
    python examples/gis_maps/install_local.py --parts <folder>      # rejoin delivered parts
    python examples/gis_maps/install_local.py --maps meteor_crater black_bear_pass
    python examples/gis_maps/install_local.py --no-deploy          # stop after the dist ZIPs exist

To uninstall, see ``deploy_local.py --remove``.

For every map it makes sure ``<map>/dist/<key>_ericrolph.zip`` exists and matches its lock:
downloaded from a GitHub Release when ``--release`` names a tag (verified against the
release's ``SHA256SUMS.txt``), from delivered parts when ``--parts`` names a folder that
holds them (verified against ``SHA256SUMS.txt``), otherwise by running the pipeline
(fetch -> terrain -> level -> dist; about 3 GB of public downloads the first time, cached
after that). Then it runs
``deploy_local.py --deploy``, which copies the ZIPs into
``%LOCALAPPDATA%\\BeamNG\\BeamNG.drive\\current\\mods`` and re-hashes them. Close BeamNG first;
the deploy step refuses to swap files under a running game.

``--release`` needs a GitHub token in ``BEAMNG_MODS_TOKEN`` (or ``GITHUB_TOKEN``/``GH_TOKEN``)
only when the release lives in a private repository; it asks for one, naming the permission,
at the moment the download is refused.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent
RELEASE_REPO = "eric-rolph/beamng-mcp"


def _load(name: str):
    loader = importlib.util.spec_from_file_location(f"gis_maps_{name}", PACK_ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(loader)
    sys.modules[loader.name] = module
    loader.loader.exec_module(module)
    return module


build = _load("build")
join_parts = _load("join_parts")
deploy_local = _load("deploy_local")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, path: Path, *, headers: dict[str, str] | None = None) -> None:
    import requests

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    sent = {"User-Agent": "beamng-maps-install"}
    sent.update(headers or {})
    with requests.get(url, stream=True, timeout=300, headers=sent) as response:
        response.raise_for_status()
        with tmp.open("wb") as sink:
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                sink.write(chunk)
    tmp.replace(path)


# --- authenticated release downloads -------------------------------------------------
# A private repository does not serve `releases/download/<tag>/<asset>` to an anonymous
# request. Rather than switch on a flag, the download tries the plain URL first and falls
# back to the authenticated asset endpoint when GitHub refuses it, so the same code is
# correct whether or not the repository is private, and stays correct if it is ever made
# public again.
#
# The fallback is not optional politeness: it is the only route to a private release
# asset. `GET /repos/{owner}/{repo}/releases/assets/{id}` with
# `Accept: application/octet-stream` needs the asset ID, not its name, so the release has
# to be resolved through the API first.
#
# Worth knowing if you try to verify this from an agent session rather than a
# workstation: you cannot. That environment's proxy authenticates every request to
# GitHub - an invalid token and an empty Authorization header both still succeed - so a
# private repository looks public from there. The only honest test is running this.

_TOKEN_VARIABLES = ("BEAMNG_MODS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")


def _token() -> str | None:
    for name in _TOKEN_VARIABLES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _token_help(repo: str) -> str:
    return (
        f"Set a GitHub token with 'Contents: Read' on {repo} in one of "
        f"{', '.join(_TOKEN_VARIABLES)}, then run this again.\n"
        "A fine-grained personal access token is enough and it needs no other permission:\n"
        "  https://github.com/settings/personal-access-tokens"
    )


def _refusal_status(error: BaseException) -> int | None:
    """The HTTP status behind a failed download, whichever library raised it.

    Written against the attributes rather than a requests import so an injected
    ``download`` is free to use any HTTP client.
    """

    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is None:
        status = getattr(error, "code", None)
    return status if isinstance(status, int) else None


def _api_assets(repo: str, tag: str, token: str) -> dict[str, str]:
    """Asset name -> API download URL for release ``tag``, resolved with ``token``.

    Only called once the plain download has been refused, which is what a private
    repository does to an anonymous request.
    """

    import requests

    response = requests.get(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        timeout=60,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "beamng-maps-install",
        },
    )
    if response.status_code in (401, 403, 404):
        raise SystemExit(
            f"The token was rejected for {repo} release {tag} (HTTP {response.status_code}).\n"
            "A private repository answers 404 rather than 403 when the token cannot see it,\n"
            "so this is most likely a missing permission rather than a missing release.\n"
            f"{_token_help(repo)}"
        )
    response.raise_for_status()
    return {asset["name"]: asset["url"] for asset in response.json().get("assets", [])}


def release_downloader(repo: str, tag: str, download=_download):
    """A ``fetch(asset_name, path)`` that works on a public or a private repository.

    The authenticated asset list is resolved at most once, and only if it is needed.
    """

    base = f"https://github.com/{repo}/releases/download/{tag}"
    assets: dict[str, str] | None = None
    token: str | None = None

    def fetch(name: str, path: Path) -> None:
        nonlocal assets, token
        if assets is None:
            try:
                download(f"{base}/{name}", path)
                return
            except Exception as error:
                if _refusal_status(error) not in (401, 403, 404):
                    raise
                token = _token()
                if not token:
                    raise SystemExit(
                        f"{repo} would not serve release {tag} without credentials, which is\n"
                        f"what a PRIVATE repository does.\n{_token_help(repo)}"
                    ) from error
                print(f"== {repo} is not serving {tag} anonymously; using an authenticated fetch")
                assets = _api_assets(repo, tag, token)
        url = assets.get(name)
        if url is None:
            raise SystemExit(f"{name} is not an asset of {repo} release {tag}")
        download(
            url,
            path,
            headers={
                "Accept": "application/octet-stream",
                "Authorization": f"Bearer {token}",
            },
        )

    return fetch


def fetch_release(
    tag: str, keys: list[str], *, repo: str = RELEASE_REPO, download=_download
) -> None:
    """Download each map's ZIP from the GitHub Release ``tag`` into ``<map>/dist/`` and lock it.

    Every ZIP is verified against the release's SHA256SUMS.txt; a mismatch is deleted.
    """

    fetch = release_downloader(repo, tag, download=download)
    sums_path = build.PACK_ROOT / "_downloads" / tag / "SHA256SUMS.txt"
    fetch("SHA256SUMS.txt", sums_path)
    sums = join_parts.read_sums(sums_path.parent)
    for key in keys:
        spec = build.load_spec(key)
        expected = sums.get(spec.ZIP_BASENAME)
        if not expected:
            raise SystemExit(
                f"{key}: {spec.ZIP_BASENAME} is not listed in the release's SHA256SUMS.txt"
            )
        zip_path = build.PACK_ROOT / key / "dist" / spec.ZIP_BASENAME
        if zip_path.is_file() and sha256_file(zip_path) == expected:
            print(f"== {key}: release ZIP already downloaded and verified")
        else:
            print(f"== {key}: downloading {spec.ZIP_BASENAME} from release {tag}")
            fetch(spec.ZIP_BASENAME, zip_path)
            digest = sha256_file(zip_path)
            if digest != expected:
                zip_path.unlink()
                raise SystemExit(
                    f"{key}: downloaded ZIP hash {digest[:16]}... "
                    f"!= release {expected[:16]}..., deleted"
                )
        lock = join_parts.write_lock(zip_path, spec.MOD_ID, spec.ZIP_BASENAME)
        lock["origin"] = f"downloaded from GitHub Release {tag}"
        (zip_path.parent / f"{spec.MOD_ID}.lock.json").write_text(
            json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            f"   {spec.ZIP_BASENAME}: {lock['size'] / 1e6:.1f} MB, "
            f"{lock['members']} members, sha256 verified"
        )


def release_ok(key: str) -> bool:
    spec = build.load_spec(key)
    dist = build.PACK_ROOT / key / "dist"
    zip_path = dist / spec.ZIP_BASENAME
    lock_path = dist / f"{spec.MOD_ID}.lock.json"
    if not zip_path.is_file() or not lock_path.is_file():
        return False
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    return sha256_file(zip_path) == lock["sha256"]


def ensure_release(key: str, *, force: bool) -> None:
    if release_ok(key) and not force:
        print(f"== {key}: release present and matches its lock")
        return
    started = time.time()
    for stage in ("fetch", "terrain", "level", "dist"):
        build.run_stage(key, stage, force=False)
    print(f"== {key}: built in {(time.time() - started) / 60:.1f} min")
    if not release_ok(key):
        raise SystemExit(f"{key}: build finished but the dist ZIP does not match its lock")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--release",
        metavar="TAG",
        help="download the ZIPs from this GitHub Release tag instead of building",
    )
    parser.add_argument(
        "--parts", type=Path, help="folder holding <key>_ericrolph.zip.partN files + SHA256SUMS.txt"
    )
    parser.add_argument(
        "--maps", nargs="*", help="map keys to install (default: every map in the pack)"
    )
    parser.add_argument("--no-deploy", action="store_true", help="stop once the dist ZIPs exist")
    parser.add_argument(
        "--force-rebuild", action="store_true", help="rebuild even when a matching release exists"
    )
    args = parser.parse_args(argv)

    keys = args.maps or build.discover_maps()
    unknown = [k for k in keys if k not in build.discover_maps()]
    if unknown:
        raise SystemExit(
            f"unknown map key(s): {unknown}; try: python examples/gis_maps/build.py --list"
        )

    if args.release:
        fetch_release(args.release, keys)

    if args.parts:
        print(f"== rejoining delivered parts from {args.parts}")
        try:
            join_parts.join(args.parts)
        except SystemExit as exc:
            print(f"   parts step: {exc}; maps without a verified ZIP will be built instead")

    for key in keys:
        ensure_release(key, force=args.force_rebuild)

    if args.no_deploy:
        print("dist ZIPs are ready; run: python examples/gis_maps/deploy_local.py --deploy")
        return 0
    print("== deploying into the BeamNG play profile")
    # --maps has to reach the deploy step too, or installing one map silently deploys
    # every ZIP that happens to be sitting in the pack's dist folders.
    argv = ["--deploy"]
    if args.maps:
        argv += ["--maps", *keys]
    return deploy_local.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

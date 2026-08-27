"""Texture gates for COLOSSUS 10350/80R457 — measured on the shipped PNGs.

NOTHING IN THE SUITE OPENED A TEXTURE UNTIL THIS FILE. Four rounds of review
found defects that only a pixel could have shown, and every one of them shipped
because the gates all stopped at the spec:

  * thirteen ``normal_strength`` values sat one level out of the dict that
    reads them, so every map was baked at the default and the carcass laminate
    - the cut edge at the port, the surface forty lines of spec prose are about
    - had 95% of its texels under one degree of slope;
  * the concrete albedo was corrected in a palette key the builder writes
    ``[1,1,1,1]`` over whenever a texture exists, so the shipped PNG still
    decoded to 2.34x the authored value and the pier pads stayed the brightest
    thing in the frame;
  * the inner liner's bladder lattice sat at four texels per cycle, so its
    relief halved with every mip level and the largest interior surface in the
    prop - the one the brief is about - read as painted sheet metal from ten
    metres;
  * a non-wrapping roughness ramp put a hard sheen line across the moulded
    brand type, once round the tire.

So: slope in an authored band, slope that SURVIVES two mips, a wrap step that
is not the largest step in the map, and a decoded albedo that matches what the
palette says it asked for.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "giant_props" / "colossus_tire"
TEXTURES = EXAMPLE_ROOT / "textures"


@pytest.fixture(autouse=True)
def _require_generated_textures():
    """Every test here measures the generated texture set, which is
    gitignored build output; on a fresh checkout the failures arrive as
    zero-relief reads and "only 0 textures compared" AssertionErrors that
    the conftest artifact hook cannot classify. One gate, honestly, for the
    whole module - including the seam test, which with zero files on disk
    would otherwise pass vacuously."""

    if not TEXTURES.is_dir():
        pytest.skip(
            "generated texture set absent (gitignored); run build.py colossus_tire textures"
        )


@pytest.fixture(scope="module")
def spec():
    path = EXAMPLE_ROOT / "spec.py"
    loader = importlib.util.spec_from_file_location("colossus_texture_spec", path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def _slopes(array):
    """Surface slope in degrees, from a tangent-space normal map."""

    import numpy as np

    normal = array * 2.0 - 1.0
    lateral = np.linalg.norm(normal[:, :, :2], axis=2)
    up = np.clip(normal[:, :, 2], 1e-6, 1.0)
    return np.degrees(np.arctan2(lateral, up))


def _open(path):
    pytest.importorskip("numpy")
    image = pytest.importorskip("PIL.Image")
    return image.open(path).convert("RGB")


def _array(image, mip=0):
    import numpy as np

    if mip:
        from PIL import Image

        image = image.resize((image.width >> mip, image.height >> mip), Image.LANCZOS)
    return np.asarray(image).astype("float32") / 255.0


# A map that is flat at mip 0 is a plastic surface; a map that is flat by mip 2
# is a plastic surface at every distance a player actually looks from. The
# bands are the pack's own measured spread, not an aspiration.
SLOPE_BAND = (10.0, 50.0)
# 9.0 is set from the MEASURED set, just under the gentlest map that ships
# (sidewall_type at 10.2, which is deliberately polished) and comfortably
# above the two the review caught: the liner shipped at 8.5 and machined_steel
# at 6.1. A floor that would not have failed the thing it was written for is
# not a floor.
MIP2_FLOOR = 9.0


def test_every_shipped_normal_map_has_relief(spec):
    """Slope in the pack's band at mip 0, and still there at mip 2."""

    import numpy as np

    checked = 0
    weak = {}
    harsh = {}
    faded = {}
    for name in sorted(spec.PALETTE):
        path = TEXTURES / f"{name}.normal.png"
        if not path.is_file():
            continue
        checked += 1
        image = _open(path)
        peak = float(np.percentile(_slopes(_array(image)), 99.9))
        mip2 = float(np.percentile(_slopes(_array(image, 2)), 99.9))
        label = name.replace(f"{spec.MOD_ID}_", "")
        if peak < SLOPE_BAND[0]:
            weak[label] = round(peak, 1)
        if peak > SLOPE_BAND[1]:
            harsh[label] = round(peak, 1)
        if mip2 < MIP2_FLOOR:
            faded[label] = round(mip2, 1)

    assert checked >= 6, f"only {checked} normal maps found under {TEXTURES}"
    assert not weak, f"normal maps with no relief at all (p99.9 slope, degrees): {weak}"
    assert not harsh, f"normal maps that will shimmer (p99.9 slope, degrees): {harsh}"
    assert not faded, (
        f"normal maps whose relief is gone two mips out: {faded} - these are the "
        f"surfaces that read as painted sheet metal at any real viewing distance"
    )


def test_no_shipped_map_seams_at_its_own_wrap(spec):
    """The wrap step may not be the largest step in the map.

    Every one of these is tiled at least once round a 28 m body, so the last
    row meets the first and the last column meets the first. A ramp that does
    not wrap puts a hard line there - measured at 35.64 code values across the
    moulded brand type, the single largest step anywhere in that map.
    """

    import numpy as np

    offenders = {}
    for name in sorted(spec.PALETTE):
        for suffix in (".color.png", ".normal.png", "_roughness.data.png"):
            path = TEXTURES / f"{name}{suffix}"
            if not path.is_file():
                continue
            data = _array(_open(path)) * 255.0
            for axis in (0, 1):
                steps = np.abs(np.diff(data, axis=axis)).mean(axis=2)
                wrap = np.abs(np.take(data, 0, axis=axis) - np.take(data, -1, axis=axis)).mean(
                    axis=-1
                )
                interior = float(np.percentile(steps, 99.9))
                seam = float(np.percentile(wrap, 99.9))
                if seam > max(interior * 2.5, 6.0):
                    label = f"{name.replace(f'{spec.MOD_ID}_', '')}{suffix}"
                    offenders[f"{label}:axis{axis}"] = (
                        f"{seam:.1f} against a {interior:.1f} interior"
                    )
    assert not offenders, f"maps that seam at their own wrap: {offenders}"


def _authored_bases(texture):
    """The albedo(s) a family was ASKED to draw: explicit params, else the
    family function's own signature defaults. Single-colour families return
    one base; two-colour families (hazard_chevron's c1/c2) return both, and
    the shipped mean is judged against their envelope.

    Round 5 found the original gate vacuous: it required params["base"],
    which zero of the eight then-shipping entries authored, so the gate
    written to end vacuous floors asserted over an empty dict.
    """

    import importlib.util
    import inspect

    params = texture.get("params") or {}
    kit_path = REPO_ROOT / "examples" / "giant_props" / "proplib" / "texture_kit.py"
    loader = importlib.util.spec_from_file_location("colossus_texture_kit", kit_path)
    kit = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(kit)
    family = getattr(kit, texture["family"], None)
    signature = inspect.signature(family).parameters if family else {}
    bases = []
    for key in ("base", "c1", "c2"):
        if key in params:
            bases.append(tuple(params[key]))
        elif key in signature and signature[key].default is not inspect.Parameter.empty:
            bases.append(tuple(signature[key].default))
    return bases


def test_the_shipped_textures_are_the_staged_textures(spec):
    """The suite measures the staging dir; the player mounts the shipped one.

    One byte-equality sweep closes the gap - without it every other gate in
    this file is a claim about files the game never opens.
    """

    shipped = EXAMPLE_ROOT / "mod" / "vehicles" / spec.MOD_ID / "textures"
    assert shipped.is_dir(), shipped
    compared = 0
    # SHIPPED drives the walk: the staging dir legitimately holds sources
    # the pruner removed from the shipped tree (furniture-era fossils), but
    # every byte the game mounts must be exactly its staged source.
    for path in sorted(shipped.glob(f"{spec.MOD_ID}_*.png")):
        twin = TEXTURES / path.name
        assert twin.is_file(), f"shipped but never staged: {path.name}"
        assert twin.read_bytes() == path.read_bytes(), (
            f"shipped bytes differ from staged: {path.name} - rebuild, and "
            f"check the dist-is-a-rezip trap"
        )
        compared += 1
    assert compared >= 20, f"only {compared} textures compared"


def test_the_shipped_albedo_is_what_the_palette_asked_for(spec):
    """A textured entry's ``color`` is a MIRROR, and it has to be a true one.

    prop_builder writes ``baseColorFactor [1,1,1,1]`` whenever a texture
    exists, so on a textured material the palette's ``color`` tints nothing -
    it is a statement about what the family was asked to draw. Round 4's
    concrete correction went into that key alone and the shipped PNG still
    decoded to 0.617 linear against an authored 0.26; round 5 armed the gate
    with family-default bases and it immediately flagged the hazard mirror
    sitting a whole hue away from the safety orange the family ships.
    """

    import numpy as np

    offenders = {}
    checked = 0
    for name, entry in sorted(spec.PALETTE.items()):
        texture = entry.get("texture")
        path = TEXTURES / f"{name}.color.png"
        if not texture or not path.is_file():
            continue
        bases = _authored_bases(texture)
        if not bases:
            continue
        checked += 1
        encoded = _array(_open(path))
        linear = np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)
        measured = linear.reshape(-1, 3).mean(axis=0)
        primary = np.array(bases[0], dtype=float)
        stated = np.array(entry["color"][:3], dtype=float)
        label = name.replace(f"{spec.MOD_ID}_", "")
        if not np.allclose(primary, stated, atol=0.06):
            offenders[f"{label}:mirror"] = (
                f"palette colour {stated.round(3).tolist()} does not mirror the "
                f"family's base {primary.round(3).tolist()}"
            )
        # A family shades, patterns and weathers what it was given, so the
        # shipped mean lands inside the ENVELOPE of its authored colours
        # (plus working room), not on any single one - a chevron is half c1,
        # half c2, and its mean is their blend.
        stack = np.array(bases, dtype=float)
        lo = stack.min(axis=0) - 0.15
        hi = stack.max(axis=0) + 0.15
        if np.any(measured < lo) or np.any(measured > hi):
            offenders[f"{label}:shipped"] = (
                f"decoded {measured.round(3).tolist()} outside the authored "
                f"envelope {stack.round(3).tolist()}"
            )
    assert checked >= 6, f"only {checked} albedo maps resolved a base"
    assert not offenders, f"albedo that never reached a pixel: {offenders}"


def test_the_palette_roughness_mirrors_the_shipped_map(spec):
    """Same law as the albedo mirror: with a roughness MAP shipped, the
    palette's ``roughness`` is inert prose - and round 5 measured four of
    them drifted up to +0.34 from the maps they claim to describe."""

    import numpy as np

    offenders = {}
    checked = 0
    for name, entry in sorted(spec.PALETTE.items()):
        path = TEXTURES / f"{name}_roughness.data.png"
        if not path.is_file():
            continue
        checked += 1
        image = _open(path)
        mean = float((np.asarray(image).astype("float32") / 255.0).mean())
        stated = float(entry["roughness"])
        if abs(mean - stated) > 0.12:
            label = name.replace(f"{spec.MOD_ID}_", "")
            offenders[label] = f"map mean {mean:.3f} vs palette {stated:.2f}"
    assert checked >= 6, f"only {checked} roughness maps found"
    assert not offenders, f"roughness mirrors that lie: {offenders}"

"""Deterministic procedural PBR texture sets for the Giant Props pack.

Pure numpy + Pillow (runs in the repo venv, not inside Blender). Every
family is seeded and tileable, and emits the exact map names the proven
Cannon Car Wash material schema consumes:

- ``<name>.color.png``            (sRGB base colour, optional alpha)
- ``<name>.normal.png``           (tangent-space, from a height field)
- ``<name>_roughness.data.png``   (linear grayscale)
- ``<name>_opacity.data.png``     (only for cut-out families like mesh)

Art direction comes from real references gathered 2026-07-22: 1950s Sunbeam
chrome toasters (Art Deco scribed side lines, bakelite), commercial 15-20 oz
PVC inflatables (triple-stitched seam bands), RIDGID-style ribbed poly shop
vac drums, perforated stainless washer drums with lifters, forged pear
wrecking balls on chain, powder-coated playground steel, and Chuck
Taylor-style canvas/foxing/tread sneakers.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
from PIL import Image


def _rng(seed: str) -> np.random.Generator:
    """Per-material seed that is the same number on every run, forever.

    THE DETERMINISM FIX (2026-08-13). This was
    ``abs(hash(("giant_props", seed))) % 2**32``, and Python randomizes str
    hashing per process (PYTHONHASHSEED), so the module docstring's promise
    that "every family is seeded" was never true across builds: each
    ``build.py <key> textures`` drew a COMPLETELY DIFFERENT noise instance
    for every procedural texture in the pack.

    That is upstream of the cooked-DDS harvest trap. A harvested DDS is a
    bake of one specific PNG, and no staleness check — by mtime or by
    content hash — can preserve a bake whose source never reproduces. It
    also meant every dist ZIP re-hashed on every build for no reason, and
    that "regenerate and see if it changed" was worthless as a review tool.

    sha256 has no per-process salt, so the seed is stable across runs,
    machines and Python versions. The cost of the change is a ONE-TIME
    reshuffle: every procedural texture draws a new (and from here on,
    permanent) noise instance the first time it is regenerated. Families,
    parameters and therefore the art direction are untouched — only the
    particular grain is.
    """

    digest = hashlib.sha256(f"giant_props:{seed}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def _value_noise(size: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    """Periodic value noise in [0, 1], smoothstep-interpolated.

    THE BLOCKINESS FIX (2026-08-10, player: "the floor looks very blocky",
    "the beam texture looks like digital camo"). Every procedural surface
    in the pack bottoms out here, and this used to build a hard np.kron
    grid and soften it with two axis-aligned BOX blurs. A box blur of a
    square grid is not bilinear whatever the old docstring claimed - it is
    a separable tent whose support is a square, so the cell lattice
    survives as axis-aligned steps. Every consumer then stacked more of
    them (fbm octaves, pore masks, speckle) and every round of "make it
    less blocky" added detail on top of a blocky basis instead of fixing
    the basis. Hence concrete that reads as Minecraft chips and steel that
    reads as digital camo, through three separate attempts to tune it out.

    Now: true bilinear sampling of the cell grid with Perlin's smoothstep
    fade, wrapped modulo `cells`, which is isotropic and C1 - no lattice,
    no preferred axis, and still exactly periodic so the tile repeats
    seamlessly. Cost is lower than the two FFT passes it replaces.
    """

    cells = max(1, min(int(cells), size))
    grid = rng.random((cells, cells))
    t = np.arange(size) * (cells / size)
    i0 = np.floor(t).astype(int) % cells
    i1 = (i0 + 1) % cells
    f = t - np.floor(t)
    w = f * f * (3.0 - 2.0 * f)                  # smoothstep fade
    wy, wx = w[:, None], w[None, :]
    g00 = grid[np.ix_(i0, i0)]
    g01 = grid[np.ix_(i0, i1)]
    g10 = grid[np.ix_(i1, i0)]
    g11 = grid[np.ix_(i1, i1)]
    top = g00 * (1.0 - wx) + g01 * wx
    bottom = g10 * (1.0 - wx) + g11 * wx
    tile = top * (1.0 - wy) + bottom * wy
    lo, hi = tile.min(), tile.max()
    return (tile - lo) / max(hi - lo, 1e-9)


def _fbm(
    size: int,
    rng: np.random.Generator,
    base_cells: int = 4,
    octaves: int = 4,
    persistence: float = 0.55,
) -> np.ndarray:
    total = np.zeros((size, size))
    amplitude = 1.0
    weight = 0.0
    cells = base_cells
    for _ in range(octaves):
        cells = min(cells, size // 2)
        total += amplitude * _value_noise(size, cells, rng)
        weight += amplitude
        amplitude *= persistence
        cells *= 2
    total /= weight
    # Renormalise to the full [0, 1] range (2026-08-10). Summing octaves
    # pulls the distribution toward the mean, so an fbm of the new
    # well-behaved basis spans roughly 0.25..0.75 - and every consumer's
    # hand-tuned threshold (`speck > 0.60`, `blotch * 0.4`, the rust and
    # pore masks) was calibrated against the OLD basis, whose per-octave
    # min-max stretch happened to keep the range wide. Without this the
    # blockiness fix reads as "all the detail vanished".
    lo, hi = total.min(), total.max()
    return (total - lo) / max(hi - lo, 1e-9)


def _height_to_normal(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    dz = np.ones_like(height)
    length = np.sqrt(dx * dx + dy * dy + dz * dz)
    normal = np.stack([-dx / length, dy / length, dz / length], axis=-1)
    return (normal * 0.5 + 0.5).clip(0, 1)


def _to_image(array: np.ndarray) -> Image.Image:
    data = (np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    if data.ndim == 2:
        return Image.fromarray(data, "L")
    if data.shape[-1] == 3:
        return Image.fromarray(data, "RGB")
    return Image.fromarray(data, "RGBA")


def _save_stable(image: Image.Image, path) -> None:
    """Encode to PNG and write ONLY when the bytes actually changed.

    THE MTIME-CHURN FIX (2026-08-13). Every family here is seeded and
    deterministic, so a rerun re-encodes byte-identical output - but an
    unconditional ``.save()`` still moves the file's mtime. The cooked-DDS
    staleness guard in :mod:`prop_builder` used to compare mtimes, so a
    single ``build.py <key> textures`` was enough to make every harvested
    DDS look stale FOREVER and silently revert the mod to shipping raw
    PNGs: rebuilding whale_geyser swapped all 12 .dds for .png and dropped
    its zip from 7,230,941 to 4,816,662 bytes. That guard is hash-based
    now, and holding mtimes still here means an unchanged texture also
    stops looking like a change to anything else downstream (packaging
    serials, make-style tooling, file watchers).
    """

    from io import BytesIO
    from pathlib import Path

    target = Path(path)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()
    if target.is_file():
        existing = target.read_bytes()
        if existing == payload:
            return
        if _same_pixels(existing, payload):
            return
    target.write_bytes(payload)


def _same_pixels(left: bytes, right: bytes) -> bool:
    """Do two encoded PNGs decode to the same image?

    THE ENCODER-CHURN FIX (round 2 of the pachinko lighting review,
    2026-08-15). ``_save_stable``'s byte compare was not enough, and the way
    it failed is worth keeping: running the pack test suite rewrote 145 of
    pachinko_tower's 160 PNGs and invalidated all 130 records in its cooked
    DDS harvest, so ``test_certified_harvest_still_ships_dds`` failed and the
    shipped zip stopped being reproducible from the tree.

    MEASURED, not assumed. The generators were cleared first: the whole
    palette was regenerated in three separate processes under three different
    PYTHONHASHSEEDs and 0 of 145 textures differed, so the seeded families are
    stable. Then the regenerated PNGs were decoded and compared to the ones on
    disk PIXEL BY PIXEL: 145 of 145 differed in file bytes and **max |delta|
    was 0 on every one of them**. Same pixels, same zlib CMF/FLG header,
    different IDAT length in both directions (3836 -> 3943 bytes on one file,
    6617 -> 6128 on another), which is a different PNG ENCODER BUILD and not a
    different image. There are four Python installations on this machine and
    the pack can be driven by any of them.

    So the file bytes were never the right identity for a generated texture -
    the DECODED IMAGE is, because that is the only thing the cooker, the
    renderer and the player ever see. A rerun under a different Pillow now
    leaves an unchanged texture completely untouched: no rewrite, no mtime
    move, no invalidated bake, and a zip that still rebuilds from the tree.

    The sibling half of this law is in ``prop_builder.cooked_is_current``.

    THE SAME NARROWING as prop_builder.sha256_pixels (round 3): the handler
    below used to be a blanket ``except Exception: return False``. False
    means "rewrite it", so a transient decode failure did not fail - it
    quietly reverted to byte identity and rewrote the file, which is the
    churn this function exists to stop. Only a payload Pillow positively
    identifies as not an image is answered False; anything else raises.
    """

    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(BytesIO(left)) as a, Image.open(BytesIO(right)) as b:
            if a.mode != b.mode or a.size != b.size:
                return False
            return a.tobytes() == b.tobytes()
    except UnidentifiedImageError:
        return False


def _copy_stable(source, target) -> None:
    """Byte copy that leaves an already-identical target untouched."""

    from pathlib import Path

    source, target = Path(source), Path(target)
    payload = source.read_bytes()
    if target.is_file() and target.read_bytes() == payload:
        return
    target.write_bytes(payload)


def _colorize(base: tuple[float, float, float], variation: np.ndarray, spread: float) -> np.ndarray:
    color = np.empty((*variation.shape, 3))
    for channel in range(3):
        color[..., channel] = base[channel] * (1.0 - spread + variation * spread * 2.0)
    return color.clip(0, 1)


def _stripes(size: int, count: float, axis: int = 1, phase: float = 0.0) -> np.ndarray:
    ramp = np.linspace(0, count, size, endpoint=False)
    wave = (ramp + phase) % 1.0
    if axis == 0:
        return np.tile(wave[:, None], (1, size))
    return np.tile(wave[None, :], (size, 1))


# --------------------------------------------------------------------------
# Families. Each returns (color HxWx3|4, height HxW, rough HxW, opacity|None).


def brushed_metal(size, rng, base=(0.82, 0.83, 0.85), rough=0.22):
    streaks = _fbm(size, rng, base_cells=2, octaves=5)
    streaks = np.tile(streaks.mean(axis=0, keepdims=True), (size, 1))
    fine = _value_noise(size, size // 4, rng)
    height = streaks * 0.6 + fine * 0.1
    color = _colorize(base, streaks * 0.7 + fine * 0.3, 0.06)
    roughness = np.full((size, size), rough) + (fine - 0.5) * 0.1
    return color, height * 0.3, roughness, None


def scribed_chrome(size, rng, base=(0.86, 0.87, 0.9)):
    """Sunbeam-style polished chrome with Art Deco scribed line clusters."""

    color, height, roughness, _ = brushed_metal(size, rng, base, rough=0.12)
    v = np.linspace(0, 1, size, endpoint=False)
    for cluster in (0.3, 0.36, 0.42, 0.62, 0.68):
        line = np.exp(-((v - cluster) ** 2) / (2 * (0.004) ** 2))
        height -= line[:, None] * 0.35
        roughness += line[:, None] * 0.25
        color *= 1.0 - line[:, None, None] * 0.18
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def bakelite(size, rng, base=(0.07, 0.06, 0.06)):
    swirl = _fbm(size, rng, base_cells=3, octaves=4)
    color = _colorize(base, swirl, 0.25)
    color[..., 0] += swirl * 0.02  # faint warm brown streaks
    roughness = 0.16 + swirl * 0.08
    return color.clip(0, 1), swirl * 0.02, roughness, None


def painted_metal(size, rng, base=(0.9, 0.9, 0.9), rough=0.32, peel=0.5,
                  grain=0.0, chalk=0.0, orange_peel=0.0, runoff=0.0):
    """Sprayed paint over sheet steel.

    The three extra terms are OPT-IN AT ZERO, and the defaults reproduce
    the original family byte for byte, because half the pack already ships
    textures baked from it and a change here would invalidate every one of
    their harvest manifests and zip locks.

    They exist because the original is a two-metre cabinet finish and it
    does not survive being asked for a ten-metre machine. Measured on a
    1024 map at the stock settings: FOUR unique RGB triplets across the
    whole tile, a normal map 90.8% within one code step of flat, and every
    varying term riding a 3-texel cell that is gone by mip 2. Rendered on a
    black mast it is not paint, it is a flat fill — and BC1 collapses each
    face to one block.

    * ``grain`` drives ALBEDO from the 4-cell blotch, which is the one
      frequency here that survives mipping.
    * ``chalk`` adds oxidised patches that lift toward grey, the way an old
      spray job actually fails.
    * ``orange_peel`` puts real relief in the height field at a cell coarse
      enough to read at distance.
    """

    fine = _value_noise(size, size // 3, rng)
    blotch = _fbm(size, rng, base_cells=4, octaves=3)
    height = fine * 0.03 * peel
    color = _colorize(base, blotch, 0.03 + 0.09 * grain)
    roughness = np.full((size, size), rough) + (fine - 0.5) * 0.08
    if grain > 0.0:
        # Multiplicative on top of the colorised base: _colorize compresses
        # toward the base hue, so on a near-black paint an additive spread
        # alone still reads as one value (the steel_worn lesson).
        color = color * (1.0 - 0.35 * grain + 0.70 * grain * blotch[..., None])
        roughness = roughness + (blotch - 0.5) * (0.22 * grain)
    if chalk > 0.0:
        patch = np.clip((_fbm(size, rng, base_cells=3, octaves=4) - 0.52) * 3.4, 0.0, 1.0)
        patch = patch * patch
        # A CHALKED BLACK, not a grey. +0.10 on a near-black base is a 3.4x
        # lift to a faintly blue mid-grey, which is where the mouldy-tarp
        # read came from.
        target = np.asarray(base, dtype=np.float64) * 0.55 + 0.035
        color = color * (1.0 - chalk * patch[..., None]) + (
            target * (chalk * patch[..., None])
        )
        roughness = roughness + patch * (0.24 * chalk)
    if runoff > 0.0:
        # Vertical rain streaking. This is what actually says "this has
        # stood outside for years" — weathering has a DIRECTION, and
        # isotropic blotching is contamination, not weather. _streaks runs
        # along v, which on every metric_uv in this pack is the vertical.
        streak = _streaks(size, rng, max(8, size // 5), length_frac=0.22)
        color = color * (1.0 - runoff * 0.10 * (1.0 - streak))[..., None]
        roughness = roughness + (1.0 - streak) * (0.12 * runoff)
    if orange_peel > 0.0:
        peel_field = _fbm(size, rng, base_cells=max(6, size // 96), octaves=3)
        height = height + (peel_field - 0.5) * (0.10 * orange_peel)
        roughness = roughness + (peel_field - 0.5) * (0.10 * orange_peel)
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def plastic_ribs(size, rng, base=(0.9, 0.44, 0.1), ribs=9.0, rough=0.42):
    """RIDGID-style rotomolded drum with horizontal ribs."""

    wave = _stripes(size, ribs, axis=0)
    profile = 0.5 - 0.5 * np.cos(wave * 2 * np.pi)
    speckle = _value_noise(size, size // 4, rng)
    height = profile * 0.5 + speckle * 0.05
    color = _colorize(base, 0.4 + profile * 0.35 + speckle * 0.25, 0.08)
    roughness = np.full((size, size), rough) + (speckle - 0.5) * 0.1
    return color, height, roughness, None


def pvc_weave(size, rng, base=(0.8, 0.15, 0.12), seams=True, quilt=False, rough=0.28):
    """Commercial inflatable vinyl: fine knit backing shine, triple-stitch
    seam bands along tile edges, optional quilted bulge."""

    u = _stripes(size, size / 6.0, axis=1)
    v = _stripes(size, size / 6.0, axis=0)
    knit = 0.5 + 0.25 * np.sin(u * 2 * np.pi) * np.sin(v * 2 * np.pi)
    blotch = _fbm(size, rng, base_cells=3, octaves=3)
    height = knit * 0.06
    color = _colorize(base, 0.45 + blotch * 0.4 + knit * 0.15, 0.09)
    roughness = np.full((size, size), rough) + (blotch - 0.5) * 0.08
    if quilt:
        dome_u = np.sin(_stripes(size, 1.0, axis=1) * np.pi)
        dome_v = np.sin(_stripes(size, 1.0, axis=0) * np.pi)
        height += dome_u * dome_v * 0.5
    if seams:
        edge = np.minimum(
            np.minimum(_stripes(size, 1.0, axis=1), 1 - _stripes(size, 1.0, axis=1)),
            np.minimum(_stripes(size, 1.0, axis=0), 1 - _stripes(size, 1.0, axis=0)),
        )
        band = (edge < 0.035).astype(float)
        stitch_wave = np.sin(_stripes(size, size / 10.0, axis=1) * 2 * np.pi) + np.sin(
            _stripes(size, size / 10.0, axis=0) * 2 * np.pi
        )
        stitches = band * (0.5 + 0.5 * np.sign(stitch_wave))
        height -= band * 0.15
        color *= 1.0 - band[..., None] * 0.25
        color += (stitches * 0.18)[..., None] * np.array([1.0, 1.0, 0.95])
        roughness += band * 0.2
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def canvas(size, rng, base=(0.78, 0.11, 0.09), rough=0.75):
    u = _stripes(size, size / 5.0, axis=1)
    v = _stripes(size, size / 5.0, axis=0)
    weave = 0.5 + 0.22 * np.sin(u * 2 * np.pi) + 0.22 * np.sin(v * 2 * np.pi)
    fade = _fbm(size, rng, base_cells=3, octaves=3)
    color = _colorize(base, 0.35 + weave * 0.35 + fade * 0.3, 0.12)
    height = weave * 0.05
    roughness = np.full((size, size), rough) + (fade - 0.5) * 0.06
    return color, height, roughness, None


def _font_file():
    """Path to a bold sans face, or None if the system has neither."""

    from PIL import ImageFont

    for candidate in (r"C:\Windows\Fonts\arialbd.ttf",
                      r"C:\Windows\Fonts\arial.ttf"):
        try:
            ImageFont.truetype(candidate, 20)
            return candidate
        except OSError:
            continue
    return None


def _blur(field: np.ndarray, radius: float) -> np.ndarray:
    """Gaussian blur a float field, wrapping at the edges."""

    from PIL import ImageFilter

    if radius <= 0.0:
        return field
    lo, hi = float(field.min()), float(field.max())
    span = max(hi - lo, 1e-9)
    img = Image.fromarray(((field - lo) / span * 255.0).astype(np.uint8), "L")
    img = img.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(img, dtype=float) / 255.0 * span + lo


def stamped_mark(size, rng, text="CGS", base=(0.94, 0.70, 0.05),
                 mark_span=0.76, mark_height=0.44, tracking=0.09,
                 mark_drop=0.0, fit_circle=False, fill=0.90, type_aspect=1.0,
                 bead_band=(0.905, 0.980), groove_band=(0.868, 0.900),
                 pocket_r=0.885, ring=True, depth=0.55, rough=0.34, wear=0.30,
                 light=(-0.62, -0.78)):
    """A die-struck maker's mark on a painted steel end cap.

    NOT printed lettering (player, 2026-08-14: "instead of small black and
    white lettering... look like it's stamped into metal"). A stamping die
    sinks a pocket into the cap, the letters go deeper still, and a rim
    bead is left standing proud round the edge. Paint then follows the
    impression, so the mark has to read through SHADING alone and stays
    the cap's own colour throughout — cavity darkening down in the
    grooves, a lit shoulder on every raised edge, a rubbed highlight on
    the bead crown where the paint has worn thin.

    Three things make it read as metal rather than as a decal:

    * the walls are CHAMFERED, not vertical — a blurred mask gives the
      normal map a real die shoulder a few texels wide instead of a
      one-pixel cliff that vanishes at any distance;
    * the bevel light is BAKED into the base colour, so the mark survives
      flat ambient lighting where a normal map alone would disappear;
    * there is no ink anywhere, so it cannot read as a sticker.

    ``mark_span``/``mark_height`` are fractions of the cap DIAMETER (the
    UV square's inscribed circle is the disc), so the type fills the face
    the way a real cast monogram does.

    ``fit_circle`` replaces both with the largest type that still fits the
    DISC: the word's bounding box is inscribed in a circle of radius
    ``fill``/2, solving ``a^2 + b^2 = r^2`` at the word's own aspect ratio
    rather than clipping it to a rectangle. That is the difference between
    type that sits in the middle of a cap and type that owns it — a
    span/height pair tuned by eye always leaves the four corners of the
    circle empty, because the constraint is radial, not rectangular.

    ``type_aspect`` is the width/height ratio of the SURFACE this square
    map is stretched onto. The map is always square, so a badge authored
    as a 2.10 x 1.35 ellipse stretches every glyph 1.556x wide unless the
    type is pre-compressed by the same factor. Pass the surface's own
    aspect and the rendered letters come out with their designed
    proportions; leave it at 1.0 for a square or circular face. The rings
    and the die pocket are deliberately NOT compensated - they are
    concentric with the face, so on an elliptical badge they should read
    as an ellipse, which is exactly what the plain stretch gives.
    """

    from PIL import ImageDraw, ImageFont

    supersample = 4
    hi = size * supersample
    strip = Image.new("L", (hi, hi), 0)
    draw = ImageDraw.Draw(strip)
    font_path = _font_file()

    # --- letters, tracked out and centred ------------------------------
    if text and font_path:
        probe = 200
        probe_font = ImageFont.truetype(font_path, probe)
        boxes = [draw.textbbox((0, 0), ch, font=probe_font) for ch in text]
        widths = [b[2] - b[0] for b in boxes]
        caps = max(b[3] - b[1] for b in boxes)
        gap = probe * tracking
        run = sum(widths) + gap * (len(text) - 1)
        if fit_circle:
            # Inscribe the word's box in the disc: with half-extents a, b at
            # the word's aspect k = a/b, a^2 + b^2 = r^2 gives
            # b = r / sqrt(1 + k^2). Everything else follows from the probe.
            # Solve the inscription against the aspect the type will
            # actually be DRAWN at, i.e. after the type_aspect squeeze,
            # otherwise a compressed word is fitted to the box of an
            # uncompressed one and ends up smaller than the disc allows.
            aspect = (max(run, 1.0) / type_aspect) / max(caps, 1.0)
            half_h = (fill * hi / 2.0) / math.sqrt(1.0 + aspect * aspect)
            scale = 2.0 * half_h / max(caps, 1.0)
        else:
            scale = min(mark_span * hi / max(run, 1.0),
                        mark_height * hi / max(caps, 1.0))
        px = max(12, int(probe * scale))
        font = ImageFont.truetype(font_path, px)
        boxes = [draw.textbbox((0, 0), ch, font=font) for ch in text]
        widths = [b[2] - b[0] for b in boxes]
        caps = max(b[3] - b[1] for b in boxes)
        gap = px * tracking
        run = sum(widths) + gap * (len(text) - 1)
        pen = (hi - run) / 2.0
        # mark_drop moves the type DOWN the face and leaves the rings alone.
        # Row 0 of the map is world-up on the cap (the disc's UV puts v with
        # +z), so a positive drop is simply drawn lower in the image.
        top = (hi - caps) / 2.0 + mark_drop * hi
        for ch, box, width in zip(text, boxes, widths):
            draw.text((pen - box[0], top - box[1]), ch, fill=255, font=font)
            pen += width + gap
        if abs(type_aspect - 1.0) > 1e-9:
            # Squeeze the LETTERS ONLY, about the centre of the face, so the
            # stretch the non-square surface applies puts them back. Drawn
            # centred, so a centred paste is the same operation.
            narrow = max(1, int(round(hi / type_aspect)))
            squeezed = strip.resize((narrow, hi), Image.LANCZOS)
            strip = Image.new("L", (hi, hi), 0)
            strip.paste(squeezed, ((hi - narrow) // 2, 0))
    mark = np.asarray(strip.resize((size, size), Image.LANCZOS),
                      dtype=float) / 255.0

    # --- rim bead and die pocket, analytic and antialiased -------------
    axis = (np.arange(size) + 0.5) / size - 0.5
    radius = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2) / 0.5
    edge = 2.5 / size

    def band(lo, hi_):
        inner = np.clip((radius - lo) / edge, 0.0, 1.0)
        outer = np.clip((hi_ - radius) / edge, 0.0, 1.0)
        return inner * outer

    # One bead hard against the rim, not a double ring: the type has to own
    # the middle of the face ("use most of the height and width of the
    # circle"), and a second ring would push it back to badge size. With
    # ``fit_circle`` the caller pushes the bead right out to the edge and
    # drops the groove entirely, leaving nothing between the rim and the
    # letters.
    bead = band(*bead_band) if ring else np.zeros_like(radius)
    groove = (band(*groove_band) if (ring and groove_band is not None)
              else np.zeros_like(radius))
    pocket = np.clip((pocket_r - radius) / edge, 0.0, 1.0)

    # Level stack, deepest last: field 0, pocket floor, groove, letters.
    height = bead * 0.42 - pocket * 0.22 - groove * 0.60 - mark * 0.85
    # THE CHAMFER: without this the die walls are one texel wide and the
    # normal map has nothing to shade at any real viewing distance.
    height = _blur(height, size / 220.0)

    # --- paint over the impression -------------------------------------
    peel = _fbm(size, rng, base_cells=6, octaves=4)          # orange-peel
    fleck = _value_noise(size, max(size // 3, 8), rng)
    shade = 0.46 + (peel - 0.5) * 0.30 + (fleck - 0.5) * 0.12
    color = _colorize(base, shade, 0.10)

    # Baked bevel light: gradient of the relief against a fixed key.
    grad_v, grad_u = np.gradient(height)
    lit = np.clip(0.5 + (grad_u * light[0] + grad_v * light[1]) * size / 26.0,
                  0.0, 1.0)
    color *= (0.72 + 0.62 * lit)[..., None]
    # Cavity: paint pools and dirt collects wherever the die went deep.
    cavity = _blur(np.clip(-height, 0.0, 1.0), size / 90.0)
    color *= (1.0 - 0.42 * np.clip(cavity / 0.85, 0.0, 1.0))[..., None]
    # Bead crown rubbed back to primer where the paint sits thinnest.
    rub = np.clip((_fbm(size, rng, base_cells=9, octaves=3) - 0.52) * 6.0,
                  0.0, 1.0) * np.clip(bead, 0.0, 1.0) * wear
    color = color * (1.0 - rub[..., None]) + np.array(
        [0.58, 0.56, 0.52]) * rub[..., None]

    roughness = (np.full((size, size), rough)
                 + np.clip(cavity, 0.0, 1.0) * 0.22
                 + (peel - 0.5) * 0.10
                 - rub * 0.08)
    return color.clip(0, 1), height * depth, roughness.clip(0.06, 1), None


def webbing(size, rng, base=(0.088, 0.088, 0.098), warp=54, weft=120,
            rough=0.60, sheen=0.42, selvedge=0.045, fuzz=0.35):
    """Synthetic strap webbing — polypropylene/nylon, 2/2 twill.

    Flat black was reading as vinyl tape (player, 2026-08-14: "the straps
    more synthetic cloth looking"). Real webbing is a WOVEN structure and
    the three tells are all here: individual warp yarns running the length
    of the strap so the surface is ribbed rather than smooth, a twill
    float that steps one pick per yarn (the fine diagonal you see when
    light rakes across a rucksack strap), and a rolled SELVEDGE at both
    edges where the weft turns back.

    ``warp`` yarns lie across the v axis and ``weft`` picks along u, so
    the generator maps v across the strap's width and u along its run.
    Both are integers because the tile has to repeat seamlessly.
    """

    warp = int(warp)
    weft = int(weft)
    v = np.linspace(0.0, 1.0, size, endpoint=False)[:, None]
    u = np.linspace(0.0, 1.0, size, endpoint=False)[None, :]
    wy, wx = v * warp, u * weft
    warp_i, weft_i = np.floor(wy), np.floor(wx)
    # 2/2 twill: over two, under two, shifted one pick per yarn.
    face = ((warp_i + weft_i) % 4) < 2
    warp_round = np.sin(np.pi * np.clip(wy - warp_i, 0.0, 1.0))
    weft_round = np.sin(np.pi * np.clip(wx - weft_i, 0.0, 1.0))
    crown = np.where(face, 0.30 + 0.70 * warp_round, 0.62 * weft_round)

    # Per-yarn dye lottery: no two filaments take the dye identically, and
    # that is most of what separates cloth from a painted surface.
    warp_tone = rng.random(warp)[np.clip(warp_i, 0, warp - 1).astype(int)]
    weft_tone = rng.random(weft)[np.clip(weft_i, 0, weft - 1).astype(int)]
    tone = np.where(face, warp_tone, weft_tone)

    # Rolled selvedge: the last few yarns pack tight into a hard cord.
    edge = np.minimum(v, 1.0 - v - 1.0 / size)
    sel = np.clip(1.0 - edge / max(selvedge, 1e-6), 0.0, 1.0) ** 1.6
    sel = np.broadcast_to(sel, (size, size))
    cord = np.sin(np.pi * np.clip(edge / max(selvedge, 1e-6), 0.0, 1.0))
    crown = crown * (1.0 - sel) + (0.45 + 0.55 * cord) * sel

    lint = _fbm(size, rng, base_cells=max(size // 24, 3), octaves=3)
    shade = 0.40 + crown * 0.42 + (tone - 0.5) * 0.26 + (lint - 0.5) * 0.16
    color = _colorize(base, shade, 0.42)
    # Interstitial shadow: the holes between crossings are near-black, and
    # that micro-contrast is what makes a weave legible at a distance. Not
    # so deep that the albedo crushes to flat black — black webbing still
    # has to show its structure in the colour map, not only in the normal.
    color *= (0.66 + 0.34 * crown)[..., None]

    height = crown * 0.55 + sel * 0.18
    roughness = (np.full((size, size), rough)
                 - crown * sheen * 0.26
                 + (lint - 0.5) * fuzz * 0.22
                 + sel * 0.06)
    return color.clip(0, 1), height, roughness.clip(0.06, 1), None


def molded_nylon(size, rng, base=(0.052, 0.052, 0.059), grain=0.55,
                 rough=0.58, sheen=0.35):
    """Injection-moulded glass-filled nylon — buckles, clips, hardware.

    Mould-tool texture, not smooth plastic: a fine pebble grain broken by
    a network of hairline creases, semi-matte, with the faint directional
    sheen that comes off a polished-then-etched cavity.
    """

    cells = max(size // 10, 6)
    pebble = _fbm(size, rng, base_cells=cells, octaves=3, persistence=0.5)
    # Creases live where the field crosses its own mid-level: a thin,
    # branching network, which is what tool grain actually looks like.
    crease = np.clip(1.0 - np.abs(pebble - 0.5) * 14.0, 0.0, 1.0)
    fine = _value_noise(size, max(size // 2, 8), rng)
    flow = _fbm(size, rng, base_cells=3, octaves=3)

    height = (pebble - 0.5) * 0.30 * grain - crease * 0.22 + (fine - 0.5) * 0.06
    shade = 0.50 + (pebble - 0.5) * 0.30 * grain - crease * 0.28 + (flow - 0.5) * 0.12
    color = _colorize(base, shade, 0.55)
    roughness = (np.full((size, size), rough)
                 + crease * 0.16
                 - (flow - 0.5) * sheen * 0.18)
    return color.clip(0, 1), height, roughness.clip(0.06, 1), None


def flag_satin(
    size,
    rng,
    base=(0.74, 0.09, 0.07),
    rough=0.38,
    sheen=0.5,
    twill=1.0,
    drape=1.0,
    hem=0.0,
):
    """Medium-weight silky flag cloth (nylon/poly satin twill).

    The look is carried by ROUGHNESS, not colour: a satin weave floats
    warp threads over several picks, and those float crowns are what
    catch the light. So the crowns get a low-roughness sheen band while
    the interstices stay matte, which reads as directional silk under a
    moving light — an all-over `rough` constant (what `canvas` does)
    reads as burlap no matter how fine the weave is drawn.

    ``twill`` runs the floats on the usual ~63-degree diagonal; ``drape``
    adds the large soft folds that separate a hanging textile from a
    painted board; ``hem`` darkens a doubled band at the v edges.
    """

    # Fine weave: satin floats on a shallow diagonal, four picks per repeat.
    diagonal = _stripes(size, size / 26.0, axis=1) + twill * _stripes(
        size, size / 52.0, axis=0
    )
    floats = 0.5 + 0.5 * np.sin(diagonal % 1.0 * 2 * np.pi)
    picks = 0.5 + 0.5 * np.sin(_stripes(size, size / 30.0, axis=0) * 2 * np.pi)
    weave = floats * 0.72 + picks * 0.28

    # Soft drape: low-frequency folds, stretched ALONG the streaming axis
    # (v) so they read as hanging creases rather than crumpled paper.
    folds = _fbm(size, rng, base_cells=2, octaves=3)
    folds = 0.65 * folds + 0.35 * np.roll(folds, size // 7, axis=0)
    creases = _fbm(size, rng, base_cells=5, octaves=4)

    shade = 0.42 + weave * 0.16 + (folds - 0.5) * 0.30 * drape
    color = _colorize(base, shade, 0.14)
    # Uneven dye + a little sun fade toward one edge: new flags are flat,
    # flown ones are not.
    fade = np.linspace(1.0, 0.93, size)[:, None]
    color *= (fade * (0.97 + creases[..., None] * 0.06)).clip(0, 1)

    height = weave * 0.035 + (folds - 0.5) * 0.22 * drape

    # Sheen: crowns polish toward `rough - sheen*0.22`, interstices stay
    # near `rough`; the fold shoulders catch a touch more light.
    polish = weave * sheen
    roughness = np.full((size, size), rough) - polish * 0.22
    roughness += (creases - 0.5) * 0.05 - (folds - 0.5) * 0.06 * drape

    if hem > 0.0:
        # Along the u edges: consumers map u ACROSS the cloth, so this is
        # the doubled long-edge hem, not a band across the ends.
        edge = _stripes(size, 1.0, axis=1)
        band = ((edge < hem) | (edge > 1.0 - hem)).astype(float)
        color *= 1.0 - band[..., None] * 0.10
        height += band * 0.05
        roughness += band * 0.06

    return color.clip(0, 1), height, roughness.clip(0.04, 1), None


def _aa_slab(coord, lo, hi, feather):
    """Slab mask with smoothstep edges, feathered in COORDINATE units.

    Every mask in a one-shot skin becomes a metre-scale edge by the time
    the game samples it, so a binary comparison is never an option: the
    washer drum shipped a binary hole mask stretched across an 8.3 m
    plate and the player read it as "blotchy", not as holes. `feather`
    is the full ramp width, so callers convert their own texel size into
    whatever space the coordinate lives in and pass that.
    """

    rise = np.clip((coord - lo) / feather + 0.5, 0.0, 1.0)
    fall = np.clip((hi - coord) / feather + 0.5, 0.0, 1.0)
    return rise * rise * (3.0 - 2.0 * rise) * fall * fall * (3.0 - 2.0 * fall)


def nobori(
    size,
    rng,
    base=(0.62, 0.09, 0.08),
    trim=(0.90, 0.86, 0.78),
    header=0.13,
    border=0.055,
    glyphs=5,
    glyph_width=0.64,
    glyph_fill=0.72,
    weight=1.0,
    taper=0.18,
    slant=0.20,
    ink_bleed=0.07,
    aspect=0.30,
    threads=32.0,
    rough=0.62,
    sheen=0.35,
    twill=1.0,
    drape=1.0,
    hem=0.022,
):
    """Sumo-venue nobori: a whole hung banner as ONE 0..1 cloth skin.

    Field, header band, edge piping and the calligraphy column all live
    HERE because the banner is soft-body cloth: proud geometry cannot
    ride a waving sheet, and the pack's standing law from the catapult
    and boot rounds is that marking geometry always betrays itself
    in-engine anyway (`ramp_deck`, `kick_pad`). So the banner needs no
    dressing at all - map this once and hang it.

    Consumers map u ACROSS the width and v ALONG the drop, 0 at the
    header and 1 at the free hem (the convention `flag_satin`'s `hem`
    documents). Texture v samples from the image BOTTOM, so v=0 is the
    LAST row of the array: this map is stored header-DOWN and a raw
    preview of the PNG looks upside down. That is correct.

    The glyph column is abstract brush MASSING - bars, uprights, stops
    and seal blocks picked from `rng` per cell - not characters of any
    language. It has to carry at apron range (~20 m), which is what
    sets the stroke weights: anything finer than roughly a twentieth of
    the banner width disappears before the banner does. `glyphs` is how
    many cells stack (4 for a short banner, 5 for a tall one),
    `glyph_width`/`glyph_fill` are the cell's share of the field and of
    its own slot, and `weight`/`taper`/`slant`/`ink_bleed` are the hand:
    stroke thickness, the lift at an upright's tail, the rise a brush
    horizontal takes to the right, and how far the inked edge wanders.

    `aspect` is the banner's width/height. It only steers the weave,
    which must be square in METRES over a sheet three times taller than
    it is wide; `threads` is warp floats across the WIDTH, and the v
    count derives from it, so the texture's own resolution is the
    binding constraint (below ~4 px per pick the weave just shimmers).
    """

    # --- cloth, straight off flag_satin -----------------------------------
    # Satin floats on the usual shallow diagonal, matte interstices. The
    # look is carried by ROUGHNESS, not colour; an all-over constant
    # reads as burlap however fine the weave is drawn.
    warp = max(threads, 2.0)
    weft = warp / max(aspect, 1e-3)
    diagonal = _stripes(size, warp, axis=1) + twill * _stripes(
        size, weft * 0.5, axis=0
    )
    floats = 0.5 + 0.5 * np.sin(diagonal % 1.0 * 2 * np.pi)
    picks = 0.5 + 0.5 * np.sin(_stripes(size, weft, axis=0) * 2 * np.pi)
    weave = floats * 0.72 + picks * 0.28

    # Drape: an isotropic fbm in TEXTURE space comes out stretched along
    # the drop once the square map lands on a 3:1 sheet, which is exactly
    # how folds hang - no extra anisotropy needed here. It stays at
    # flag_satin's amplitude on purpose: this sheet is real soft body and
    # supplies its own folds, so a baked fold deep enough to see on a
    # still would double up with the ones the solver is already making.
    folds = _fbm(size, rng, base_cells=2, octaves=3)
    folds = 0.65 * folds + 0.35 * np.roll(folds, size // 7, axis=0)
    creases = _fbm(size, rng, base_cells=5, octaves=4)
    shade = 0.42 + weave * 0.16 + (folds - 0.5) * 0.30 * drape

    # --- banner layout ----------------------------------------------------
    u = ((np.arange(size) + 0.5) / size)[None, :]
    v = (1.0 - (np.arange(size) + 0.5) / size)[:, None]
    texel = 1.0 / size
    crisp = 1.5 * texel

    band = _aa_slab(v, -1.0, header, crisp)
    pipe = np.maximum(
        _aa_slab(u, -1.0, border, crisp),
        _aa_slab(u, 1.0 - border, 2.0, crisp),
    )
    sewn = np.maximum(band, pipe)

    # --- the glyph column -------------------------------------------------
    # Each form is a tuple of (u centre, v centre, u half, v half) strokes
    # in CELL-LOCAL units where +-1 spans the glyph box and +v runs DOWN
    # the banner, matching the drop. Forms carry the marks that make brush
    # writing legible as writing: a heavy horizontal entry, a stop block
    # where the brush parks, uprights that outlive their bars.
    # Nothing here is symmetric or full-width twice over: an evenly ruled
    # grid of bars reads as a barcode, and a CLEAN symmetric one starts
    # colliding with real characters. Every form is deliberately off-axis
    # somewhere - an overshooting bar, a stop block, a stray dash.
    forms = (
        # Crown bar over a hanging stem, stop block, stray left dash.
        (
            (0.02, -0.72, 0.98, 0.16),
            (0.10, 0.22, 0.16, 0.78),
            (0.86, -0.66, 0.15, 0.26),
            (-0.55, 0.30, 0.40, 0.13),
        ),
        # Bracket: two bars closed down one side, inner tick off-centre.
        (
            (0.06, -0.82, 0.92, 0.15),
            (-0.02, 0.78, 0.98, 0.15),
            (-0.80, -0.05, 0.16, 0.92),
            (0.62, 0.40, 0.30, 0.12),
        ),
        # Twin uprights of unequal drop, crossed low, short offset crown.
        (
            (-0.70, 0.05, 0.17, 0.92),
            (0.68, -0.12, 0.15, 0.80),
            (0.0, 0.18, 0.92, 0.15),
            (-0.10, -0.76, 0.62, 0.14),
        ),
        # Seal: a heavy block over its underline, with one entry tick.
        (
            (0.10, -0.34, 0.58, 0.50),
            (-0.02, 0.74, 0.98, 0.17),
            (-0.72, 0.16, 0.15, 0.32),
        ),
        # Three-bar spine, no two bars the same length.
        (
            (0.04, -0.02, 0.16, 0.96),
            (-0.06, -0.58, 0.90, 0.15),
            (0.16, 0.10, 0.62, 0.12),
            (-0.02, 0.72, 0.84, 0.16),
        ),
        # Roof over a short stem and two splayed feet.
        (
            (0.0, -0.80, 0.98, 0.17),
            (-0.06, -0.08, 0.16, 0.58),
            (-0.50, 0.70, 0.46, 0.15),
            (0.58, 0.62, 0.36, 0.13),
        ),
    )
    cells = max(1, int(glyphs))
    strokes = max(len(form) for form in forms)
    # Padded so the whole column can be gathered and broadcast in one
    # shot; the 5th column is the "this slot exists" switch, because a
    # zero-extent slab still returns 0.25 at its own centre.
    table = np.zeros((len(forms), strokes, 5))
    for index, form in enumerate(forms):
        table[index, : len(form), :4] = form
        table[index, : len(form), 4] = 1.0
    # Walk the form list by a non-zero random stride so no two ADJACENT
    # cells can draw the same form: a repeat inside a five-glyph column
    # reads as a tiling artefact, not as writing.
    pick = np.cumsum(rng.integers(1, len(forms), size=cells)) % len(forms)
    mirror = rng.integers(0, 2, size=cells) * 2.0 - 1.0
    stress = 0.88 + 0.24 * rng.random(cells)
    # A hand-written column never sits on a ruled ladder: each cell gets
    # its own size and a nudge along the drop. The cell's own local frame
    # runs to +-1.39 before the form switches, so nothing here can push a
    # stroke into its neighbour's rows.
    hand = 0.92 + 0.16 * rng.random(cells)
    drift = (rng.random(cells) - 0.5) * 0.14
    nib = 0.84 + 0.32 * rng.random((cells, strokes))

    column_top = header + 0.05
    column_bot = 1.0 - 0.06
    slot = (column_bot - column_top) / cells
    ladder = (v[:, 0] - column_top) / slot
    cell = np.clip(np.floor(ladder), 0.0, cells - 1.0).astype(int)
    # Cell-local v; rows outside the column land beyond +-1 and every
    # stroke sits inside it, so no separate in/out mask is needed.
    local_v = (ladder - cell - 0.5) * 2.0 / max(glyph_fill, 1e-3)
    local_u = (u - 0.5) * 2.0 / max(glyph_width, 1e-3)

    row_form = table[pick[cell]]
    grip = hand[cell][:, None]
    centre_u = row_form[..., 0] * mirror[cell][:, None] * grip
    centre_v = row_form[..., 1] * grip + drift[cell][:, None]
    half_u = row_form[..., 2] * grip
    half_v = row_form[..., 3] * grip
    live = row_form[..., 4]
    # Weight rides the THIN axis only - scaling both would stretch bars
    # instead of inking them - and it is drawn per STROKE, because one
    # weight for a whole glyph is what makes drawn marks look extruded.
    upright = (half_v > half_u).astype(float)
    pressure = (stress[cell] * weight)[:, None] * nib[cell]
    half_u = half_u * np.where(upright > 0.0, pressure, 1.0)
    half_v = half_v * np.where(upright > 0.0, 1.0, pressure)
    # Uprights thin toward their tail, which is the brush lifting off.
    reach = np.clip(
        (local_v[:, None] - centre_v) / np.maximum(half_v, 1e-6), -1.0, 1.0
    )
    half_u = half_u * (1.0 - taper * upright * reach)

    # Hand-inked edge: warp the cell's own coordinates with a coarse noise
    # BEFORE the slabs are cut. Wobbling the coordinate keeps every edge
    # smoothstepped, where wobbling the finished mask would either
    # re-binarise it or scumble holes through solid strokes.
    bleed_u = (_value_noise(size, max(size // 16, 8), rng) - 0.5) * ink_bleed
    bleed_v = (_value_noise(size, max(size // 19, 8), rng) - 0.5) * ink_bleed
    # A brush horizontal RISES to the right - roughly six degrees is what
    # separates written from typeset - so the cell's own v axis is sheared
    # by u. Shearing the frame instead of each bar leaves the uprights
    # upright and costs one broadcast.
    soft_v = 3.0 * texel * 2.0 / max(glyph_fill * slot, 1e-6)
    soft_u = 3.0 * texel * 2.0 / max(glyph_width, 1e-3)
    brush_u = (local_u + bleed_u)[:, None, :]
    brush_v = (local_v[:, None] + slant * local_u + bleed_v)[:, None, :]
    span_v = _aa_slab(
        brush_v,
        (centre_v - half_v)[..., None],
        (centre_v + half_v)[..., None],
        soft_v,
    )
    span_u = _aa_slab(
        brush_u,
        (centre_u - half_u)[..., None],
        (centre_u + half_u)[..., None],
        soft_u,
    )
    ink = (span_v * span_u * live[..., None]).max(axis=1)

    stamp = np.maximum(sewn, ink)

    # --- maps -------------------------------------------------------------
    # Trim is DYED CLOTH, so it takes the same weave and drape shading as
    # the field. Flat trim is what makes a banner read as a vinyl sticker.
    color = (
        _colorize(base, shade, 0.14) * (1.0 - stamp[..., None])
        + _colorize(trim, shade, 0.10) * stamp[..., None]
    )
    # The free hem is the end that whips through dust all day; the header
    # end is tied to the arm and stays clean.
    soil = np.linspace(0.94, 1.0, size)[:, None]
    color *= (soil * (0.97 + creases[..., None] * 0.06)).clip(0, 1)

    height = weave * 0.035 + (folds - 0.5) * 0.22 * drape
    # The band and the piping are SEWN tape and get relief; the printed
    # dye does not, which is the whole point of moving the decor off the
    # geometry and into the map.
    height += sewn * 0.06

    polish = weave * sheen
    roughness = np.full((size, size), rough) - polish * 0.18
    roughness += (creases - 0.5) * 0.05 - (folds - 0.5) * 0.06 * drape
    roughness -= stamp * 0.08

    if hem > 0.0:
        doubled = _aa_slab(v, 1.0 - hem, 2.0, crisp)
        color *= 1.0 - doubled[..., None] * 0.10
        height += doubled * 0.05
        roughness += doubled * 0.06

    return color.clip(0, 1), height, roughness.clip(0.04, 1), None


def field_turf(
    size,
    rng,
    base=(0.165, 0.30, 0.105),
    mow_bands=2.0,
    wear=0.28,
    rough=0.82,
    dry=(0.40, 0.38, 0.17),
):
    """Mown natural-grass football turf, authored as a ONE-SHOT skin.

    Two things separate real field turf from "green paint": blade-scale
    breakup at roughly 3 px, and MOWING STRIPES — which are not paint and
    not a hue shift, but the same grass bent toward or away from the
    viewer, so they belong in brightness and in the normal only. Stadium
    grass is also a deep blue-green, never the yellow-green that a naive
    (0.2, 0.6, 0.2) gives you.
    """

    blades = _value_noise(size, max(size // 3, 8), rng)
    fibre = _value_noise(size, max(size // 2, 8), rng)
    clumps = _fbm(size, rng, base_cells=6, octaves=4)
    # Smoothly alternating mow bands (tanh keeps the roller boundary soft).
    lean = 0.5 + 0.5 * np.tanh(
        np.sin(_stripes(size, mow_bands, axis=1) * 2 * np.pi) * 3.0
    )

    # The mat must sit DARKER than the blade cards standing on it — it is
    # thatch seen down between blades, not lit lawn. It was brighter, so
    # the sward read as glowing from underneath.
    shade = 0.22 + blades * 0.24 + fibre * 0.11 + (clumps - 0.5) * 0.18
    shade = shade * (0.87 + lean * 0.26)
    color = _colorize(base, shade, 0.22)

    # Thin/worn grass goes straw-coloured rather than just darker.
    # base_cells 3 over a 2.2 m slab makes 0.7 m blobs, which read as
    # camouflage patches rather than wear.
    thin = _fbm(size, rng, base_cells=9, octaves=3)
    thin_mask = np.clip((thin - (1.0 - wear)) / max(wear, 1e-6), 0.0, 1.0) * 0.6
    color = color * (1.0 - thin_mask[..., None]) + np.array(dry) * thin_mask[..., None]

    height = blades * 0.45 + fibre * 0.20 + (clumps - 0.5) * 0.22
    roughness = (
        np.full((size, size), rough)
        + (blades - 0.5) * 0.10
        - lean * 0.05
        + thin_mask * 0.06
    )
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def field_soil(size, rng, base=(0.185, 0.125, 0.082), rough=0.93, stones=0.3,
               damp=0.3):
    """Rootzone / subgrade soil: clods, grit, damp patches.

    Football subgrade is a sand-loam rootzone — brown with grey-tan grit,
    not the red-brown of garden dirt.
    """

    clods = _fbm(size, rng, base_cells=4, octaves=5)
    grit = _value_noise(size, max(size // 3, 8), rng)
    color = _colorize(base, 0.36 + clods * 0.40 + grit * 0.20, 0.20)
    # Pale sand grains and small stones.
    speck = (_value_noise(size, max(size // 2, 8), rng) > (1.0 - stones * 0.22)).astype(
        float
    )
    color += speck[..., None] * np.array([0.16, 0.15, 0.12])
    # Damp shadowed hollows track the clod lows, so they read as depth.
    wet = np.clip((0.42 - clods) * 2.4, 0.0, 1.0) * damp
    color *= 1.0 - wet[..., None] * 0.42

    height = clods * 0.7 + grit * 0.25 + speck * 0.15
    roughness = np.full((size, size), rough) - wet * 0.30 - speck * 0.10
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def sod_edge(
    size,
    rng,
    soil=(0.175, 0.115, 0.075),
    thatch=(0.34, 0.26, 0.135),
    grass=(0.165, 0.30, 0.105),
    grass_frac=0.30,
    thatch_frac=0.20,
    rough=0.90,
):
    """The cut face of laid sod: grass on top, root/thatch mat, then soil.

    This is the ID-00003 elevation read edge-on, and it is what stops a
    grass patch from looking like a green-topped box. v runs 0..1 bottom
    to top, and v samples from the image BOTTOM, so row 0 is the TOP of
    the sod (the pack's atlas-orientation law).
    """

    rows = np.linspace(1.0, 0.0, size)[:, None]      # 1.0 at row 0 = top
    height_frac = np.tile(rows, (1, size))
    jitter = _fbm(size, rng, base_cells=7, octaves=3)
    fine = _value_noise(size, max(size // 3, 8), rng)

    # Wobble the two interfaces so the layering is never a ruled line.
    grass_line = 1.0 - grass_frac + (jitter - 0.5) * 0.10
    thatch_line = 1.0 - grass_frac - thatch_frac + (jitter - 0.5) * 0.07

    color = _colorize(soil, 0.34 + _fbm(size, rng, base_cells=5, octaves=4) * 0.42, 0.20)
    in_thatch = (height_frac >= thatch_line) & (height_frac < grass_line)
    in_grass = height_frac >= grass_line
    thatch_shade = 0.38 + fine * 0.34 + (jitter - 0.5) * 0.24
    color = np.where(
        in_thatch[..., None], _colorize(thatch, thatch_shade, 0.20), color
    )
    # Vertical blade streaks in the grass band, plus a ragged crown.
    streak = _value_noise(size, max(size // 4, 8), rng)
    streak = np.tile(streak[:1, :], (size, 1)) * 0.6 + streak * 0.4
    grass_shade = 0.34 + streak * 0.36 + fine * 0.16
    color = np.where(in_grass[..., None], _colorize(grass, grass_shade, 0.22), color)

    height = np.where(in_grass, 0.35 + streak * 0.5, 0.0)
    height = np.where(in_thatch, 0.22 + fine * 0.3, height)
    height = np.where(~(in_grass | in_thatch), _fbm(size, rng, base_cells=5, octaves=4) * 0.6, height)

    roughness = np.full((size, size), rough)
    roughness = np.where(in_grass, rough - 0.05 + streak * 0.08, roughness)
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def grass_card(size, rng, base=(0.075, 0.175, 0.055), tip=(0.28, 0.50, 0.115),
               warm_tip=(0.34, 0.47, 0.115), blades=140, rough=0.78, lean=0.5,
               dead=0.07, panels=4):
    """Mown-turf blade card, drawn blade-by-blade, as a 4-panel ATLAS.

    Hard-won rules, all of which a critic caught the violation of:

    * Mown turf is CUT TO A PLANE. Blade height must be near-uniform
      (~1.15:1), not scattered — a wide height spread renders pasture.
    * Blades must be 2-4 mm WIDE. Hairline blades let the ground show
      through at grazing angles no matter how many you scatter.
    * Dead straw lives DOWN in the sward, dark and below the mow line.
      Straw on the tallest blades puts bleached stragglers on the skyline,
      which is the loudest "neglected field" signal there is.
    * Blades need real HUE spread (~20 deg), not just value spread. A
      value-only ramp is what makes turf read as moulded plastic.

    Four independently drawn panels give sixteen distinct card looks once
    the scatter also flips them horizontally, which kills the repeated
    motif you otherwise see at a grazing angle.
    """

    from PIL import ImageDraw

    scale = 3   # supersample: 1 px blade tips alias horribly at 1x
    canvas_size = size * scale
    alpha_img = Image.new("L", (canvas_size, canvas_size), 0)
    depth_img = Image.new("L", (canvas_size, canvas_size), 0)
    straw_img = Image.new("L", (canvas_size, canvas_size), 0)
    hue_img = Image.new("L", (canvas_size, canvas_size), 0)
    alpha_draw = ImageDraw.Draw(alpha_img)
    depth_draw = ImageDraw.Draw(depth_img)
    straw_draw = ImageDraw.Draw(straw_img)
    hue_draw = ImageDraw.Draw(hue_img)

    per_panel = max(blades // panels, 1)
    panel_w = canvas_size / panels
    for panel in range(panels):
        for rank in range(per_panel):
            root_x = (panel + rng.random() * 1.02 - 0.01) * panel_w
            depth = rank / max(per_panel - 1, 1)
            # Near-uniform height = the mow plane; a few short blades the
            # reel missed keep the top edge from being a ruler line.
            tall = (0.84 + 0.16 * rng.random()) * canvas_size
            ragged = rng.random() < 0.12
            if ragged:
                tall *= 0.45
            half_w = (0.0085 + rng.random() * 0.0075) * canvas_size
            sway = (rng.random() - 0.5) * 2.0 * lean * canvas_size * 0.35
            steps = 9
            left, right = [], []
            for step in range(steps + 1):
                t = step / steps
                x = root_x + sway * t * t
                y = canvas_size - tall * t
                taper = half_w * (1.0 - t) ** 0.55
                left.append((x - taper, y))
                right.append((x + taper, y))
            polygon = left + right[::-1]
            alpha_draw.polygon(polygon, fill=255)
            depth_draw.polygon(polygon, fill=int(40 + 215 * (0.35 + 0.65 * depth)))
            hue_draw.polygon(polygon, fill=int(255 * rng.random()))
            # Only SHORT blades go straw, and only below the mow line.
            if tall < 0.62 * canvas_size and rng.random() < dead * 3.0:
                straw_draw.polygon(polygon, fill=255)

    def sample(image):
        return np.asarray(
            image.resize((size, size), Image.LANCZOS), dtype=np.float64
        ) / 255.0

    alpha = sample(alpha_img)
    depth = sample(depth_img)
    straw = sample(straw_img)
    hue = sample(hue_img)

    rise = np.linspace(1.0, 0.0, size)[:, None]     # 1.0 at row 0 = tips
    blend = np.clip(rise * 0.55 + depth * 0.55, 0.0, 1.0)
    # Per-blade hue: cool blue-green through warm yellow-green.
    tip_mix = (
        np.array(tip)[None, None, :] * (1.0 - hue[..., None])
        + np.array(warm_tip)[None, None, :] * hue[..., None]
    )
    color = (
        np.array(base)[None, None, :] * (1.0 - blend[..., None])
        + tip_mix * blend[..., None]
    )
    # Root-zone occlusion. This has to do the work that castShadows would:
    # a 38 mm canopy photographs mostly SHADOW, and with per-card shadows
    # off (they blotch) nothing else supplies the dark. Too shallow a ramp
    # and the sward lights as a flat carpet.
    color *= (0.22 + 0.78 * rise ** 0.9)[..., None]
    straw_colour = np.array([0.26, 0.215, 0.095])
    color = color * (1.0 - straw[..., None] * 0.55) + straw_colour * (
        straw[..., None] * 0.55
    )
    height = depth * 0.5
    roughness = np.full((size, size), rough) - depth * 0.10 + straw * 0.08
    return color.clip(0, 1), height, roughness.clip(0, 1), alpha.clip(0, 1)


def grass_card_sparse(size, rng, base=(0.155, 0.295, 0.10), tip=(0.34, 0.44, 0.14),
                      blades=26, rough=0.8, lean=0.35):
    """Alpha-cutout blade cluster for grass fringe cards.

    A flat lawn plane always reads as a decal at a grazing angle — what
    sells turf up close is real silhouette. These cards supply it: blades
    rising from the bottom edge, tapering, leaning, darker at the root and
    sun-bleached at the tip. Returns an OPACITY map, which the builder
    turns into alphaTest automatically.
    """

    from PIL import ImageDraw

    scale = 2  # draw big, downsample: crisp tapered tips without stair steps
    canvas_size = size * scale
    alpha_img = Image.new("L", (canvas_size, canvas_size), 0)
    shade_img = Image.new("L", (canvas_size, canvas_size), 0)
    alpha_draw = ImageDraw.Draw(alpha_img)
    shade_draw = ImageDraw.Draw(shade_img)

    for index in range(blades):
        root_x = (index + 0.5) / blades + (rng.random() - 0.5) * (0.9 / blades)
        root_x *= canvas_size
        tall = (0.45 + rng.random() * 0.55) * canvas_size
        half_w = (0.004 + rng.random() * 0.010) * canvas_size
        sway = (rng.random() - 0.5) * 2.0 * lean * canvas_size * 0.45
        steps = 7
        left, right = [], []
        for step in range(steps + 1):
            t = step / steps
            # Quadratic lean: blades stand up out of the root and bend over.
            x = root_x + sway * t * t
            y = canvas_size - tall * t
            taper = half_w * (1.0 - t) ** 0.7
            left.append((x - taper, y))
            right.append((x + taper, y))
        polygon = left + right[::-1]
        alpha_draw.polygon(polygon, fill=255)
        # Brighter toward the tip so the cluster has depth, not flat green.
        shade_draw.polygon(polygon, fill=int(60 + 150 * (tall / canvas_size)))

    alpha = np.asarray(
        alpha_img.resize((size, size), Image.LANCZOS), dtype=np.float64
    ) / 255.0
    shade = np.asarray(
        shade_img.resize((size, size), Image.LANCZOS), dtype=np.float64
    ) / 255.0

    rise = np.linspace(1.0, 0.0, size)[:, None]     # 1.0 at row 0 = blade tips
    blend = np.clip(rise * 0.75 + shade * 0.45, 0.0, 1.0)
    color = (
        np.array(base)[None, None, :] * (1.0 - blend[..., None])
        + np.array(tip)[None, None, :] * blend[..., None]
    )
    color *= 0.72 + shade[..., None] * 0.5
    height = shade * 0.5
    roughness = np.full((size, size), rough) - shade * 0.08
    return color.clip(0, 1), height, roughness.clip(0, 1), alpha.clip(0, 1)


def padded_vinyl(size, rng, base=(0.10, 0.14, 0.34), rough=0.36, grain=0.5,
                 sheen=0.45, scuff=0.25):
    """Vinyl-coated foam pad skin — the goal-post cushion shell.

    A pole pad is not upholstery: it is a heat-sealed vinyl SHELL over
    foam, so the surface is a smooth semi-gloss plastic with a fine
    pebble grain, and the softness has to come from the geometry bulging
    between its straps rather than from a quilted weave in the map.
    """

    pebble = _value_noise(size, max(size // 4, 8), rng)
    fine = _value_noise(size, max(size // 2, 8), rng)
    swell = _fbm(size, rng, base_cells=3, octaves=3)

    shade = 0.44 + pebble * 0.16 * grain + fine * 0.08 + (swell - 0.5) * 0.18
    color = _colorize(base, shade, 0.13)

    # Scuffs and chalk marks: pads live at ground level on a used field.
    marks = _fbm(size, rng, base_cells=9, octaves=3)
    mark_mask = np.clip((marks - (1.0 - scuff * 0.4)) * 5.0, 0.0, 1.0) * 0.5
    color = color * (1.0 - mark_mask[..., None] * 0.5) + np.array(
        [0.62, 0.63, 0.66]
    ) * mark_mask[..., None] * 0.5

    height = pebble * 0.10 * grain + (swell - 0.5) * 0.16
    # Broad soft highlight = plastic. Tight variance keeps it from reading
    # as either matte fabric or wet gloss.
    roughness = (
        np.full((size, size), rough)
        - (pebble - 0.5) * 0.10 * sheen
        + mark_mask * 0.22
    )
    return color.clip(0, 1), height, roughness.clip(0.06, 1), None


def rubber_tread(size, rng, base=(0.9, 0.9, 0.88), pattern="dots", rough=0.55):
    """Sneaker outsole: gum dots or bars, worn centers."""

    cell = _stripes(size, 8.0, axis=0), _stripes(size, 8.0, axis=1)
    cu = np.abs(cell[1] - 0.5) * 2
    cv = np.abs(cell[0] - 0.5) * 2
    if pattern == "dots":
        bump = ((cu * cu + cv * cv) < 0.3).astype(float)
    else:
        bump = (cv < 0.45).astype(float)
    wear = _fbm(size, rng, base_cells=2, octaves=3)
    height = bump * 0.4 * (0.6 + wear * 0.4)
    color = _colorize(base, 0.5 + bump * 0.2 - wear * 0.25, 0.1)
    roughness = np.full((size, size), rough) + wear * 0.15
    return color, height, roughness.clip(0, 1), None


def wood_painted(size, rng, base=(0.16, 0.45, 0.66), wear=0.35, rough=0.5):
    """Powder-coat-painted playground plank with grain telegraphing through
    and chipped edges showing wood."""

    grain = _fbm(size, rng, base_cells=2, octaves=5)
    grain = np.tile(grain.mean(axis=0, keepdims=True), (size, 1))
    ripple = _fbm(size, rng, base_cells=6, octaves=3)
    streak = grain * 0.75 + ripple * 0.25
    color = _colorize(base, 0.45 + streak * 0.25, 0.1)
    chips = (_fbm(size, rng, base_cells=8, octaves=3) > (1.0 - wear * 0.25)).astype(float)
    wood = np.array([0.45, 0.31, 0.17])
    color = color * (1 - chips[..., None]) + wood * chips[..., None] * (
        0.7 + streak[..., None] * 0.5
    )
    height = streak * 0.08 - chips * 0.1
    roughness = np.full((size, size), rough) + chips * 0.25 + (ripple - 0.5) * 0.08
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def concrete(size, rng, base=(0.62, 0.6, 0.57), stencil=False, fine=0.0,
             striate=0.0):
    """Cast concrete; ``fine``/``striate`` are OPT-IN so every existing
    consumer renders byte-identical.

    fine > 0 (2026-08-08): the legacy pits are 1-3 texel blobs thresholded
    from near-pixel value noise; metric UVs magnify them into square
    "Minecraft" chips at reading distance (player: "texture is a little
    too basic"). Fine mode replaces them with material-scale detail:
    micro grain, dense soft-edged pores, metre-scale stains.

    striate > 0: column-correlated extrusion streaks for ceramic
    baguettes (terracotta louver fins are extruded, not cast).
    """

    blotch = _fbm(size, rng, base_cells=3, octaves=5)
    pits = (_value_noise(size, size // 3, rng) > 0.82).astype(float)
    # POUR-SCALE CONTRAST (2026-08-11, player on the entrance ramp: "it
    # looks like a repeating pattern too much at a distance ... it looks
    # like some tiles at a distance"). blotch is a 3-cell fbm - ONE
    # feature every third of a tile - and it was swinging luminance
    # 0.4..0.8, a 2:1 brightness ratio. Fine detail averages out as the
    # camera pulls back; a 3-cell swing does not, so the thing that
    # survived at range was the tile grid itself, tiling the ramp in
    # light and dark patches. Real concrete goes FLATTER with distance,
    # not blotchier. Fine mode therefore keeps blotch's full height and
    # roughness variation (that reads as surface relief, which is what
    # near-field concrete needs) and collapses only the COLOUR swing
    # toward the mean. Legacy consumers pass fine=0 and stay byte-
    # identical: tone is blotch exactly when fine <= 0.
    # 0.28 -> 0.10 (2026-08-12, player magenta-marked one dark diagonal
    # smudge PER TILE on the entrance apron): at 0.28 the 3-cell blotch
    # still carried ~+-9% luminance - a single memorable landmark whose
    # clone recurs every tile in lockstep. The eye cannot track the
    # high-frequency aggregate across repeats, but it locks onto exactly
    # one big soft blob. At 0.10 the blob is ~+-3%: pour variation you
    # can see against a fender, not a landmark you can count.
    tone = blotch if fine <= 0.0 else 0.5 + (blotch - 0.5) * 0.10
    if fine > 0.0:
        pits = np.zeros_like(pits)
    color = _colorize(base, 0.4 + tone * 0.4, 0.08)
    color *= 1 - pits[..., None] * 0.25
    height = blotch * 0.08 - pits * 0.15
    roughness = 0.78 + (blotch - 0.5) * 0.1 + pits * 0.15
    if fine > 0.0:
        # The colour swing is not the only tiling channel: blotch height
        # at 0.08 bakes normal-map lobes that SHADE as the same bump
        # every repeat under low sun (2026-08-12 magenta-marks round).
        # Flattened to a third; the aggregate/sand relief below carries
        # the near-field normal detail.
        height = blotch * 0.025
        micro = _fbm(size, rng, base_cells=64, octaves=3, persistence=0.6)
        # Copper-v3 speckle recipe (round 15: the vault beams still read
        # as rectangular chips - a x6 hard threshold on 3-octave noise is
        # value-noise blocks all over again). Multi-octave field, squared
        # for soft edges, clustered by a broad mask, capped well short of
        # black so pores read as cast texture, not confetti.
        speck = _fbm(size, rng, base_cells=24, octaves=4)
        # Flattened toward its mean for the same distance reason: this
        # 4-cell field gates PORE DENSITY, so leaving it at full depth
        # painted patches of "many pores" and "no pores" on a 1/4-tile
        # grid - which at range is a checkerboard, not concrete. Pores
        # still cluster, just not into tile-locked continents.
        cluster = _fbm(size, rng, base_cells=4, octaves=2)
        cluster = 0.5 + (cluster - 0.5) * 0.45
        pores = (np.clip((speck - 0.60) * 2.4, 0.0, 1.0) ** 2
                 * np.clip((cluster - 0.30) * 1.8, 0.0, 1.0))
        pores = np.clip(pores, 0.0, 0.5) * fine
        # Stains DELETED from fine mode (2026-08-12, the magenta-marks
        # round). A 2-cell field is one or two elongated smudges per
        # tile - "kept at a third of its depth" still left a countable
        # landmark recurring in the tile lattice, which is exactly what
        # the player circled. Fine mode's character now comes entirely
        # from scales the eye cannot track across repeats: aggregate,
        # sand, micro grain, pores.
        color *= 1 - pores[..., None] * 0.16
        color *= 0.97 + micro[..., None] * 0.06
        height += (micro - 0.5) * 0.05 * fine - pores * 0.06
        roughness = roughness + (micro - 0.5) * 0.12 + pores * 0.1
        # EXPOSED AGGREGATE (2026-08-10, player: "the floor needs detail to
        # make it look like concrete"). With the blocky basis gone this
        # family was a smooth grey wash - correct, and characterless. Real
        # cast concrete reads as stone chips of varying tone set in paste,
        # a fine sand grain under them, and pour-scale tonal drift; those
        # three scales are what the eye uses to call a surface concrete.
        # Cell size is chosen in METRES via the caller's metric UV: at the
        # pack's typical 1.8-2.5 m tile a size//4 cell lands near 8 mm,
        # which is aggregate, not noise.
        stone_field = _value_noise(size, max(8, size // 4), rng)
        stone_tone = _value_noise(size, max(8, size // 4), rng)
        # Soft-shouldered mask: chips have edges but not hard ones, and
        # each chip carries its own tone so the field never reads as one
        # repeated dot.
        chips = np.clip((stone_field - 0.52) * 3.2, 0.0, 1.0) ** 1.5
        chips *= fine
        chip_tint = (stone_tone - 0.5) * 0.34
        color *= 1.0 + (chips * (0.14 + chip_tint))[..., None]
        sand = _value_noise(size, max(8, size // 2), rng)
        color *= 0.985 + sand[..., None] * 0.03
        # Pour-scale drift: 6 cells across the tile, so at range it is
        # another copy of the tile grid. Depth cut from +-4.5% to +-1.5%;
        # it still carries the roughness variation below at full strength,
        # which is invisible as pattern but keeps the sheen from going
        # plastic.
        drift = _fbm(size, rng, base_cells=6, octaves=3)
        color *= 0.992 + drift[..., None] * 0.016
        height += chips * 0.05 + (sand - 0.5) * 0.02
        # Aggregate is polished harder than the paste around it.
        roughness = roughness - chips * 0.14 + (drift - 0.5) * 0.08
    if striate > 0.0:
        cols = _value_noise(size, min(128, size // 4), rng).mean(axis=0)
        streaks = np.tile(cols[None, :], (size, 1))
        streaks = streaks * 0.8 + _fbm(size, rng, base_cells=6, octaves=2) * 0.2
        height += (streaks - 0.5) * 0.05 * striate
        color *= 0.97 + streaks[..., None] * 0.06 * striate
    # CONTROL JOINTS. Two hard grooves at fixed v, i.e. one dark line
    # every half tile, in permanent lockstep with the tile grid. THIS is
    # what read as "tiled from a distance" on the entrance ramp (player
    # 2026-08-11, second report - the first round chased the blotching
    # and the blotching was not the problem): the eye forgives repeated
    # noise and never forgives a repeated straight line. Real slab joints
    # run every 3-6 m and belong to the geometry, not to a map that
    # repeats every 2 m. Dropped in fine mode; legacy consumers keep them
    # so nothing else in the pack shifts.
    if fine <= 0.0:
        v = np.linspace(0, 1, size, endpoint=False)
        for line in (0.25, 0.75):
            groove = np.exp(-((v - line) ** 2) / (2 * 0.003**2))
            height -= groove[:, None] * 0.2
            color *= 1.0 - groove[:, None, None] * 0.12
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def wood(size, rng, early=(0.455, 0.268, 0.146), late=(0.088, 0.040, 0.019),
         rings=24.0, figure=1.0, pore=1.0, sheen=1.0):
    """One plain-sawn board of fine hardwood, French-polished.

    Built as a real board rather than as stripes, because stripes are
    exactly what a sign face must not look like. The pith is placed off
    the board's long edge, so the annual rings cut the face as nested
    arches - the CATHEDRAL FIGURE that says "sawn from a log" instead of
    "printed pattern". Four scales stack on top of each other:

      rings   annual growth, asymmetric: earlywood fades in gradually,
              latewood ends abruptly. That asymmetry is the single
              biggest tell; a symmetric ring reads as a painted line.
      figure  low-frequency warp of the ring field, so the arches wander
              the way grain actually wanders around the trunk.
      grain   fine lengthwise fibre, one or two texels wide.
      pores   open-pore ticks elongated ALONG the grain, darker in
              latewood where the vessels are denser.

    ``sheen`` drives a polished finish: low roughness overall, with the
    pores staying slightly matte so the surface reads as filled-and-
    polished rather than plastic-dipped. Grain runs along +X.
    """
    early = np.asarray(early, dtype=float)
    late = np.asarray(late, dtype=float)

    yy, xx = np.mgrid[0:size, 0:size].astype(float) / float(size)
    # Pith just off the bottom edge. Far away (py 1.7) the rings come out
    # nearly straight and the board reads as painted stripes; close in
    # they sweep the face as true cathedral arches. py is the single most
    # important number in this function.
    # Far enough out that the concentric CENTRE never enters frame (at
    # 1.07 the pith showed as a bullseye on the bottom edge, which reads
    # as end grain or a knot, not as a board face) but close enough that
    # the arches still sweep.
    px, py = 0.42, 1.24
    # The log axis runs along +X, so ring distance is compressed
    # lengthwise and the arches stretch out down the board.
    wander = _fbm(size, rng, base_cells=3, octaves=4)
    ripple = _fbm(size, rng, base_cells=9, octaves=3)
    d = np.sqrt(((xx - px) * 0.55) ** 2 + (yy - py) ** 2)
    d = d + (wander - 0.5) * 0.055 * figure + (ripple - 0.5) * 0.010

    # Growth is not metronomic - good years are wide, bad years narrow -
    # and evenly spaced rings are what make procedural wood read as a
    # contour map. A monotone warp of d varies the spacing without ever
    # folding the ring order back on itself.
    d = d + 0.055 * np.sin(d * 9.3) + 0.021 * np.sin(d * 23.7 + 1.7)

    phase = (d * rings) % 1.0
    # Latewood is a NARROW, dark line closing each year's growth, not a
    # wide soft ramp - a wide ramp is what made the first attempt look
    # like sand dunes. Peak at 0.82 with a short lead and a shorter tail.
    band = np.clip(1.0 - np.abs(phase - 0.82) / 0.155, 0.0, 1.0) ** 1.25
    lead = np.clip((phase - 0.30) / 0.52, 0.0, 1.0) ** 2.2 * 0.30
    band = np.clip(band + lead, 0.0, 1.0)
    # Not every ring is equally dark either; a uniform line weight is the
    # other half of the contour-map look.
    band *= 0.62 + 0.55 * _fbm(size, rng, base_cells=5, octaves=3)
    band = np.clip(band, 0.0, 1.0)

    # Fibre: one-to-two texel lengthwise grain, plus a slow tone drift so
    # no two spans of the board match.
    fibre = _streaks(size, rng, cells=max(160, size // 2), length_frac=0.16)
    drift = _fbm(size, rng, base_cells=2, octaves=3)

    mix = np.clip(band * 0.96 + (fibre - 0.5) * 0.34, 0.0, 1.0)
    color = early[None, None, :] + (late - early)[None, None, :] * mix[..., None]
    color *= (0.955 + drift * 0.09)[..., None]
    color *= (0.955 + (fibre - 0.5) * 0.19)[..., None]

    # Open pores: short dashes lying along the grain, concentrated in
    # latewood. Thresholded from a lengthwise-smeared field so each tick
    # is a dash, not a dot.
    vessel = _streaks(size, rng, cells=max(64, size // 4), length_frac=0.035)
    ticks = np.clip((vessel - 0.62) * 4.2, 0.0, 1.0) ** 1.4
    ticks *= (0.35 + 0.65 * band) * pore
    color *= 1.0 - ticks[..., None] * 0.42

    height = band * 0.05 + (fibre - 0.5) * 0.02 - ticks * 0.55

    # French polish: glassy across the field, with the unfilled pore
    # bottoms holding a little more diffusion.
    roughness = (0.34 - 0.16 * sheen) + (1.0 - band) * 0.03 + ticks * 0.30
    roughness = roughness + (drift - 0.5) * 0.03

    return color.clip(0, 1), height, roughness.clip(0.02, 1.0), None


def marquee(size, rng, text="SIGN", fg=(0.03, 0.08, 0.30), bg=(0.93, 0.94, 0.95),
            holo=False, holo_outline=(0.87, 0.89, 0.93), holo_shadow=0.62,
            holo_span=1.35, holo_phase=0.06):
    """Backlit cabinet sign: light diffuser field, dark silhouette
    lettering, letters slightly raised. Pair with a uniform emissive
    factor on the material: at night the panel glows and the lettering
    reads as a silhouette - the classic backlit marquee - with no
    per-texel emissive plumbing needed. Deterministic (rng unused; the
    build machine's Arial is the font).

    ``holo`` swaps the flat silhouette for the MODERN PARLOUR numeral
    treatment (2026-08-14 art round): the glyph is filled with a
    holographic hue sweep under a foil highlight, fenced by a hard dark
    outline and dropped onto a soft shadow. That is three ink layers, and
    two of them live OUTSIDE the glyph, so a holo texture's ink bounding
    box is WIDER than the same text drawn flat. Every plate that samples
    a measured ink window (the value plaques in the pachinko generator)
    must re-measure after this flag is turned on - a window measured off
    the flat texture crops the outline and the drop shadow back off, and
    the numeral goes back to looking flat.

    ``holo_span`` is how many hue turns the sweep makes across the strip
    and ``holo_phase`` where it starts; both are here so two plates on
    one machine can be given different foil without redrawing anything.
    """

    del rng
    from PIL import ImageDraw, ImageFont

    # Empty text = plain diffuser: the round-14 channel-letter sign
    # carries its lettering as extruded GEOMETRY in front of the panel
    # (reverse-lit look); the panel is then just the even glow field.
    # Rendering halo hotspots per letter here would need PIL's kerning
    # to agree with Blender's font layout - it does not, so we don't.
    # The 5th return is an EMISSIVE map. It used to be justified like this:
    # "emissiveFactor alone on a textured vehicle material rendered black on
    # the player's game build even though it glowed on the 0.38.6 rig".
    # CORRECTED 2026-08-15 (round 17): that diagnosis was wrong, and so was
    # the version it blamed. `emissiveFactor` alone is sufficient - PROVIDED
    # the array has THREE components. The materials that rendered black had
    # FOUR (an alpha appended by analogy with `color`, which really is RGBA),
    # and a 4-component factor kills the emissive path outright. See the
    # round-16/17 photometric ledger in the repo-root AGENTS.md. The map is
    # still worth shipping - it is how a glow gets a PATTERN rather than a
    # flat field - but it is an enhancement, not a workaround.
    if not text.strip():
        color = np.empty((size, size, 3))
        for channel in range(3):
            color[..., channel] = bg[channel]
        height = np.zeros((size, size))
        roughness = np.full((size, size), 0.32)
        emissive = np.ones((size, size, 3))
        return color.clip(0, 1), height, roughness.clip(0, 1), None, emissive

    # The face UVs map this SQUARE onto a ~9.5:1 panel, squashing it
    # vertically. Draw into a strip at the panel's own aspect and then
    # stretch it into the square, so letters display at true proportions
    # filling ~70% of the band (first cut drew straight into the square
    # and the player got a thin line of squashed text).
    aspect = 9.55
    strip_w = size * 4
    strip_h = max(48, int(strip_w / aspect))
    strip = Image.new("L", (strip_w, strip_h), 0)
    draw = ImageDraw.Draw(strip)
    font_path = None
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf",
                      r"C:\Windows\Fonts\arial.ttf"):
        try:
            ImageFont.truetype(candidate, 20)
            font_path = candidate
            break
        except OSError:
            continue
    if font_path:
        px = int(strip_h * 0.74)
        font = ImageFont.truetype(font_path, px)
        while px > 8:
            font = ImageFont.truetype(font_path, px)
            box = draw.textbbox((0, 0), text, font=font)
            if box[2] - box[0] <= strip_w * 0.94:
                break
            px = int(px * 0.92)
    else:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    tx = (strip_w - (box[2] - box[0])) // 2 - box[0]
    ty = (strip_h - (box[3] - box[1])) // 2 - box[1]
    draw.text((tx, ty), text, fill=255, font=font)
    if holo:
        return _marquee_holo(
            size, strip, strip_w, strip_h, bg, holo_outline, holo_shadow,
            holo_span, holo_phase,
        )
    img = strip.resize((size, size), Image.LANCZOS)
    mask = np.asarray(img, dtype=float) / 255.0
    color = np.empty((size, size, 3))
    for channel in range(3):
        color[..., channel] = bg[channel] * (1 - mask) + fg[channel] * mask
    height = mask * 0.25
    roughness = np.full((size, size), 0.32) + mask * 0.1
    emissive = _marquee_glow(color, mask, size)
    return color.clip(0, 1), height, roughness.clip(0, 1), None, emissive


# How much of the backlight a texel passes, as a function of how dark its own
# artwork is. A marquee is a translucent diffuser with ink ON it: ink is a
# FILTER, not a mask, and a DARKER ink is a heavier filter. Reverse-printed
# signwriting - light type knocked out of a saturated field, which is what this
# machine's plates are - depends on exactly that, and it is why the type on a
# real lit box is so much brighter than the field rather than 45% dimmer.
MARQUEE_CLEAR_TRANSMISSION = 0.30
# Lamp banks behind the diffuser. A real backlit box has them and they are
# visible; a box without them reads as a self-illuminated card.
MARQUEE_LAMP_BANKS = 3
MARQUEE_LAMP_DEPTH = 0.16
MARQUEE_EDGE_FALLOFF = 0.22


def _marquee_glow(color: np.ndarray, mask: np.ndarray, size: int) -> np.ndarray:
    """The glow map of a BACKLIT BOX, in the sign's own colours.

    THE INVERTED-SIGN DEFECT (round 2 of the pachinko lighting review,
    2026-08-15). This used to return a greyscale ``1 - mask``. Against the
    material's ``emissiveFactor`` of [1, 1, 1] that has two consequences, both
    of them photographed on the shipped build:

      * THE SIGN LOSES ITS COLOUR AFTER DARK. The title plate is cream type on
        a deep red field by day and a flat neutral grey-green rectangle at
        night, because a greyscale glow times a white factor can only ever
        emit white. A parlour marquee glows in its own colour; that is most of
        what makes it a parlour marquee.
      * THE TYPE POLARITY FLIPS. ``1 - mask`` forces every glyph to zero, so
        the cream lettering that is the BRIGHT half of the artwork by day
        becomes the BLACK half at night. Ink that is lighter than its field
        has to stay lighter than its field.

    Both fall out of one correction: the glow is the ALBEDO seen through the
    backlight, not a stencil of it.

        glow = albedo x transmission(albedo) x backlight(position)

    Every texel emits its OWN colour, and it emits more of it the lighter its
    artwork is. That preserves the day polarity automatically and in both
    directions - cream type on a red field stays lighter, red type on a white
    field stays darker - with neither case special-cased, and it widens the
    contrast rather than flattening it: measured on the shipped plates the
    type/field luminance ratio comes out about 11:1 on the title and 8:1 on a
    letter, where a flat stencil gave 0:1 the wrong way round.

    ``emissiveFactor`` stays [1, 1, 1] for every material that ships this map,
    and that is deliberate: the colour is now PER TEXEL, and multiplying a
    coloured glow map by a coloured factor would tint the sign twice. The two
    tube materials, which have no glow map, do carry their tint in
    ``emissiveFactor`` - that is where a flat emitter's colour belongs.

    ``backlight`` is the lamp bank behind the diffuser: ``MARQUEE_LAMP_BANKS``
    soft bands across the panel's short axis plus a cosine falloff into the
    box edges, so the panel has the banding and the vignette a lit box has
    instead of being uniformly luminous.
    """

    # v runs across the panel's SHORT axis (the square is stretched onto a
    # ~9.55:1 band), so the lamp tubes band along it, the way tubes sit in a
    # wide box.
    v = np.linspace(0.0, 1.0, size, endpoint=False)[:, None]
    u = np.linspace(0.0, 1.0, size, endpoint=False)[None, :]
    banding = 1.0 - MARQUEE_LAMP_DEPTH * (
        0.5 + 0.5 * np.cos(v * MARQUEE_LAMP_BANKS * 2.0 * np.pi)
    )
    edge = (1.0 - MARQUEE_EDGE_FALLOFF
            * (1.0 - np.sin(np.pi * np.clip(u, 0.0, 1.0)) ** 0.35)
            - MARQUEE_EDGE_FALLOFF * 0.6
            * (1.0 - np.sin(np.pi * np.clip(v, 0.0, 1.0)) ** 0.45))
    backlight = np.clip(banding * edge, 0.0, 1.0)
    del mask
    luminance = (0.2126 * color[..., 0] + 0.7152 * color[..., 1]
                 + 0.0722 * color[..., 2])
    transmission = (MARQUEE_CLEAR_TRANSMISSION
                    + (1.0 - MARQUEE_CLEAR_TRANSMISSION) * luminance)
    glow = color * (transmission * backlight)[..., None]
    return glow.clip(0, 1)


def _hue_sweep(hue: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Fully saturated HSV -> RGB for a hue field, scaled by ``value``.

    Vectorized and small on purpose: the only consumer is the holographic
    numeral fill, which wants a clean spectrum rather than a palette.
    """

    h = (hue % 1.0) * 6.0
    i = np.floor(h)
    f = h - i
    p = np.zeros_like(h)
    q = 1.0 - f
    t = f
    one = np.ones_like(h)
    table = [
        (one, t, p),
        (q, one, p),
        (p, one, t),
        (p, q, one),
        (t, p, one),
        (one, p, q),
    ]
    out = np.zeros((*hue.shape, 3))
    for index, triple in enumerate(table):
        pick = i == index
        for channel in range(3):
            out[..., channel] = np.where(pick, triple[channel], out[..., channel])
    return out * value[..., None]


def _marquee_holo(size, strip, strip_w, strip_h, bg, outline_rgb, shadow,
                  span, phase):
    """The modern-parlour numeral: foil fill, hard outline, drop shadow.

    Drawn in STRIP space (the 9.55:1 band the plate actually shows) and
    stretched into the square exactly like the flat path, so the three ink
    layers keep their true proportions. Dilation is PIL's MaxFilter rather
    than a convolution because the pack has no scipy and a box dilate of a
    binary glyph is what an outline IS.
    """

    from PIL import ImageFilter

    # The outline is the single reason a rainbow numeral does not dissolve
    # into its background, so it is sized in PLATE terms: 4% of the plate
    # height, which on the 2.55 m jackpot plaque is an 11 cm chrome rule -
    # over the pack's ~10 cm read threshold from the drive-out apron. A
    # 2 cm outline measures fine and is invisible at 30 m.
    grow = max(3, (int(strip_h * 0.065) // 2) * 2 + 1)      # odd kernel
    outline_strip = strip.filter(ImageFilter.MaxFilter(grow))
    # The shadow is the OUTLINE offset and softened, not a third dilation.
    # Every pixel these three layers add outside the glyph is plate height
    # the numeral itself does not get (the plaque is a fixed 4.9 x 2.8 m and
    # the type has to keep its round-4 size), and a double-dilated shadow
    # cost 8% of the letter height for a smudge nobody can see.
    drop = max(2, int(strip_h * 0.050))
    shadow_strip = outline_strip.transform(
        (strip_w, strip_h), Image.AFFINE, (1, 0, -drop, 0, 1, -drop),
        resample=Image.BILINEAR,
    ).filter(ImageFilter.GaussianBlur(max(1.0, strip_h * 0.012)))

    def square(image):
        return np.asarray(image.resize((size, size), Image.LANCZOS), dtype=float) / 255.0

    glyph = square(strip)
    ring = square(outline_strip)
    cast = square(shadow_strip)

    # Foil: hue sweeps across the plate and drifts a little with height, so
    # the fill reads as an angled holographic film rather than a flat
    # gradient. The bright band near the top is the specular sheet every
    # printed foil has, and it is what stops the spectrum reading as a
    # rainbow sticker.
    uu = np.linspace(0.0, 1.0, size, endpoint=False)[None, :]
    vv = np.linspace(1.0, 0.0, size, endpoint=False)[:, None]
    hue = phase + uu * span + vv * 0.18
    sheet = 0.72 + 0.55 * np.exp(-(((vv - 0.66) / 0.16) ** 2))
    fill = _hue_sweep(np.broadcast_to(hue, (size, size)).copy(),
                      np.broadcast_to(sheet, (size, size)).copy())
    fill = fill * 0.82 + 0.18          # lift the darkest hues off black

    color = np.empty((size, size, 3))
    for channel in range(3):
        color[..., channel] = bg[channel]
    # Shadow first (it is behind everything), then the outline, then the
    # foil. The outline is BRIGHT here, not dark: on the near-black plate a
    # dark outline is the background, and the first cut of this function
    # drew one and produced a rainbow floating in a void.
    color *= 1.0 - (cast * shadow)[..., None]
    for channel in range(3):
        color[..., channel] = (
            color[..., channel] * (1.0 - ring) + outline_rgb[channel] * ring
        )
    color = color * (1.0 - glyph[..., None]) + fill * glyph[..., None]

    height = ring * 0.18 + glyph * 0.20
    roughness = np.full((size, size), 0.40) - glyph * 0.22 - ring * 0.14
    emissive = np.empty((size, size, 3))
    for channel in range(3):
        emissive[..., channel] = 1.0 - ring
    return color.clip(0, 1), height, roughness.clip(0.02, 1.0), None, emissive


def _wrapped_offsets(size: int, cx: float, cy: float):
    """Toroidal (dx, dy) fields in unit tile space, broadcastable to size^2.

    Every stamped shape below goes through this, which is the whole reason
    the screen-printed field tiles: a shape near an edge is measured
    through the wrap, so its other half draws on the far side.
    """

    coords = (np.arange(size) + 0.5) / float(size)
    dx = ((coords[None, :] - cx + 0.5) % 1.0) - 0.5
    dy = ((coords[:, None] - cy + 0.5) % 1.0) - 0.5
    return dx, dy


def _leaf_stamp(size, cx, cy, length, width, angle, feather):
    """Pointed-oval leaf silhouette; returns (body, midrib) soft masks."""

    dx, dy = _wrapped_offsets(size, cx, cy)
    ca, sa = math.cos(angle), math.sin(angle)
    along = dx * ca + dy * sa
    across = -dx * sa + dy * ca
    half_len = max(length, 1e-6) / 2.0
    t = np.clip(np.abs(along) / half_len, 0.0, 1.0)
    # (1 - t^2)^0.62 is fat in the middle and tapers to a point at the tip;
    # the small linear term makes the base blunter than the tip, which is
    # the difference between a leaf and a lens.
    half_wide = (width / 2.0) * (1.0 - t * t) ** 0.62 * (1.0 - 0.22 * (along / half_len))
    # Gate on LENGTH as well. Without this the width envelope collapses to
    # zero at the tips and keeps going, so the antialiasing feather leaves a
    # hairline running down the leaf's infinite axis - which drew a
    # spider's web of stray lines right across the first tile.
    ends = np.clip(0.5 + (half_len - np.abs(along)) / feather, 0.0, 1.0)
    body = np.clip(0.5 - (np.abs(across) - half_wide) / feather, 0.0, 1.0) * ends
    rib = np.clip(0.5 - (np.abs(across) - width * 0.035) / feather, 0.0, 1.0) * body
    return body, rib


def _chip_stamp(size, cx, cy, radius, angle, kind, feather):
    """Confetti: 0 = disc, 1 = rotated square, 2 = triangle."""

    dx, dy = _wrapped_offsets(size, cx, cy)
    ca, sa = math.cos(angle), math.sin(angle)
    u = dx * ca + dy * sa
    v = -dx * sa + dy * ca
    if kind == 0:
        d = np.sqrt(u * u + v * v) - radius
    elif kind == 1:
        d = np.maximum(np.abs(u), np.abs(v)) - radius * 0.82
    else:
        # Half-plane intersection: an equilateral triangle pointing +v.
        d = np.maximum(
            np.maximum(-v - radius * 0.5, 0.866 * u + 0.5 * v - radius * 0.55),
            -0.866 * u + 0.5 * v - radius * 0.55,
        )
    return np.clip(0.5 - d / feather, 0.0, 1.0)


def parlour_field(size, rng, ground=(0.925, 0.895, 0.795),
                  leaf=(0.705, 0.825, 0.685), leaf_dark=(0.575, 0.725, 0.585),
                  chip_a=(0.855, 0.690, 0.185), chip_b=(0.215, 0.505, 0.570),
                  leaves=9, chips=22, rough=0.56):
    """Hand-screened playfield art: ivory ground, pastel foliage, confetti.

    The 1970s cabinet's board is a CREAM FIELD with pale mint leaf
    silhouettes and mustard/teal confetti - flat screen-printed ink, no
    shading, no outline - and the whole reason it reads as period is that
    the ink is SOFT and the ground is warm. Three things this family is
    careful about:

      * ink is FLAT. Screen ink has no gradient and almost no relief, so
        the height map only carries the ~40 micron ink shoulder that makes
        a print catch the light at a glancing angle.
      * the ground is PAPER, not plastic: a fine tooth plus a slow tone
        drift, so a 24 x 39 m board does not read as one solid swatch.
      * every shape is stamped THROUGH THE WRAP, so the tile is seamless
        at any metric UV. The board face is authored at 6 m per tile, which
        puts a leaf at 1.4-2.2 m - comfortably over the pack's ~10 cm
        read threshold from the drive-in apron.
    """

    tooth = _value_noise(size, size // 3, rng)
    drift = _fbm(size, rng, base_cells=2, octaves=3)
    color = _colorize(ground, 0.42 + tooth * 0.30 + drift * 0.28, 0.045)
    ink = np.zeros((size, size))
    feather = 2.5 / size

    for index in range(int(leaves)):
        cx, cy = rng.random(), rng.random()
        angle = rng.random() * math.pi * 2.0
        length = 0.26 + rng.random() * 0.16
        body, rib = _leaf_stamp(size, cx, cy, length, length * 0.42, angle, feather)
        tint = leaf_dark if index % 3 == 0 else leaf
        for channel in range(3):
            color[..., channel] = color[..., channel] * (1.0 - body) + tint[channel] * body
        # A single screen-printed vein: the ground colour knocked back
        # through the leaf, which is how a two-screen print actually does it.
        for channel in range(3):
            color[..., channel] = color[..., channel] * (1.0 - rib * 0.85) + (
                ground[channel] * rib * 0.85
            )
        ink = np.maximum(ink, body)

    for index in range(int(chips)):
        cx, cy = rng.random(), rng.random()
        angle = rng.random() * math.pi * 2.0
        radius = 0.026 + rng.random() * 0.030
        kind = index % 3
        chip = _chip_stamp(size, cx, cy, radius, angle, kind, feather)
        tint = chip_a if index % 2 == 0 else chip_b
        for channel in range(3):
            color[..., channel] = color[..., channel] * (1.0 - chip) + tint[channel] * chip
        ink = np.maximum(ink, chip)

    height = ink * 0.035 + tooth * 0.012
    roughness = np.full((size, size), rough) - ink * 0.10 + (tooth - 0.5) * 0.05
    return color.clip(0, 1), height, roughness.clip(0.02, 1.0), None


def birch_ply(size, rng, base=(0.845, 0.720, 0.505), late=(0.640, 0.485, 0.290),
              rings=5.0, seam=0.9, wear=0.45, rough=0.38):
    """Blonde birch plywood panel, sheet-jointed and knocked about.

    The cabinet material for the vintage half of the fusion. At the tower's
    scale the ply LAMINATIONS are invisible (a 1 mm veneer on a 3.2 m panel
    is a quarter of a texel), so what has to carry the story is the JOINT:
    a dark hairline where two sheets meet with the raw, paler sawn edge
    band beside it, plus the darker rub the corners of a wooden cabinet
    always pick up. Grain runs along +X, rifted rather than cathedralled -
    a face veneer is sliced, not plain-sawn, so its figure is long and
    quiet next to the marquee's mahogany.
    """

    yy, xx = np.mgrid[0:size, 0:size].astype(float) / float(size)
    wander = _fbm(size, rng, base_cells=3, octaves=4)
    fibre = _streaks(size, rng, cells=max(200, size // 2), length_frac=0.22)
    # Rifted figure: nearly straight bands across the board with a slow
    # wander, so the veneer reads as sliced rather than printed.
    phase = (yy * rings + (wander - 0.5) * 0.55 + (fibre - 0.5) * 0.06) % 1.0
    band = np.clip(1.0 - np.abs(phase - 0.78) / 0.20, 0.0, 1.0) ** 1.3
    band *= 0.55 + 0.60 * _fbm(size, rng, base_cells=6, octaves=3)
    mix = np.clip(band * 0.85 + (fibre - 0.5) * 0.30, 0.0, 1.0)
    early = np.asarray(base, dtype=float)
    dark = np.asarray(late, dtype=float)
    color = early[None, None, :] + (dark - early)[None, None, :] * mix[..., None]
    color *= (0.95 + wander * 0.11)[..., None]

    # Sheet joint. Distance to the nearest tile edge in each axis; the dark
    # hairline sits ON the edge and the pale sawn band just inside it.
    edge_u = np.minimum(xx, 1.0 - xx)
    edge_v = np.minimum(yy, 1.0 - yy)
    edge = np.minimum(edge_u, edge_v)
    # Sized in METERS, not in texels. The board is authored at 4.5 m per
    # tile, so 0.030 is a 13 cm shadow gap and the sawn band is a 27 cm
    # strip of raw edge 25 cm in. A 1 cm joint is truthful and completely
    # invisible from the drive-in apron - the pack's texel-scale law, in the
    # direction that costs you the detail rather than exaggerating it.
    hairline = np.clip(1.0 - edge / 0.030, 0.0, 1.0) * seam
    sawn = np.clip(1.0 - np.abs(edge - 0.055) / 0.030, 0.0, 1.0) * seam
    color *= 1.0 - hairline[..., None] * 0.62
    color += (sawn * 0.10)[..., None] * np.array([1.0, 0.97, 0.88])

    # Corner rub: the two things a wooden cabinet loses first are its
    # arrises and the paint round the handles. Darker, slightly greyer.
    corner = np.clip(1.0 - (edge_u * edge_u + edge_v * edge_v) ** 0.5 / 0.14, 0.0, 1.0)
    scuff = corner * (0.35 + 0.65 * _fbm(size, rng, base_cells=8, octaves=3)) * wear
    color *= 1.0 - scuff[..., None] * 0.30
    color += (scuff * 0.03)[..., None] * np.array([0.6, 0.6, 0.7])

    height = band * 0.04 + (fibre - 0.5) * 0.02 - hairline * 0.55 - sawn * 0.10
    roughness = np.full((size, size), rough) + (1.0 - band) * 0.04 + scuff * 0.16
    roughness += hairline * 0.20
    return color.clip(0, 1), height, roughness.clip(0.02, 1.0), None


def lamp_bands(size, rng, colors=((0.98, 0.42, 0.06), (0.88, 0.11, 0.09),
                                  (0.97, 0.80, 0.13)),
               ferrule=(0.74, 0.75, 0.78), rough=0.13, glow=0.34):
    """Segmented translucent lamp tube: colour bands between metal ferrules.

    The vintage cabinet's lamp tubes are geometry rather than a flat panel
    because a runtime cannot animate a texture, so per-tube control has to
    live in the scene graph. This is the tube's skin: saturated lacquer
    segments, each lifted toward its own centre so the band reads as a lit
    cell rather than as paint, parted by a nickel ferrule. ``glow`` is how
    much the cell centre brightens, and it is the reason a band still reads
    as "lit" in flat daylight.

    This docstring used to justify the geometry with "because emissive maps
    are inert on this pipeline", and called ``glow`` "a CHEAT for the missing
    emissive". RETIRED 2026-08-15 (round 17): emissive is NOT missing. A
    THREE-component `emissiveFactor` emits fine; the pack's dead materials had
    FOUR components, which kills the path. ``glow`` is now just baked shading
    that keeps the tube reading in daylight, where a real emissive contribution
    is swamped anyway (a lamp needs ~2.5k nits to out-read a sunlit surface at
    noon - see the photometric ledger in the repo-root AGENTS.md). The geometry
    and ``glow`` are both still the right call; only the reasoning was wrong.
    """

    del rng
    count = max(1, len(colors))
    v = np.linspace(0.0, 1.0, size, endpoint=False)[:, None]
    cell = (v * count) % 1.0
    index = np.floor(v * count).astype(int) % count
    color = np.zeros((size, size, 3))
    for slot, tint in enumerate(colors):
        pick = (index == slot)
        for channel in range(3):
            color[..., channel] = np.where(pick[:, 0][:, None], tint[channel],
                                           color[..., channel])
    # Lit-cell shading: bright through the middle of the segment, falling to
    # the ferrule. Multiplied, then lifted, so a saturated hue keeps its hue.
    # ``core`` is a COLUMN (size, 1). Multiplying an (H, W, 3) colour by it
    # directly aligns the column against (W, 3) and shades the tube across
    # its circumference instead of along its length - which came out as a
    # diamond checkerboard. Every band-wise term gets an explicit [..., None].
    core = np.exp(-(((cell - 0.5) / 0.30) ** 2))
    color *= (0.80 + 0.26 * core)[..., None]
    color += (core * glow)[..., None] * np.array([1.0, 0.97, 0.90])

    ring = np.clip(1.0 - np.abs(cell - 0.0) / 0.045, 0.0, 1.0)
    ring = np.maximum(ring, np.clip(1.0 - np.abs(cell - 1.0) / 0.045, 0.0, 1.0))
    ring = np.broadcast_to(ring, (size, size)).copy()
    for channel in range(3):
        color[..., channel] = color[..., channel] * (1.0 - ring) + ferrule[channel] * ring

    height = np.broadcast_to(core * 0.35 - ring * 0.45, (size, size)).copy()
    roughness = np.full((size, size), rough) + ring * 0.16 - np.broadcast_to(
        core, (size, size)
    ) * 0.04
    return color.clip(0, 1), height, roughness.clip(0.02, 1.0), None


def asphalt(size, rng, base=(0.16, 0.16, 0.17)):
    # DO NOT EDIT THIS LINE IN PLACE. It was changed once to fix a fleck size
    # in `slap_pad` — which does not call this function, it duplicates it —
    # and the edit silently re-cut `asphalt` in TEN other mods: 30 of 32
    # differing maps pack-wide, 80-96% of texels moved, every one of their
    # certified cooked-DDS harvests invalidated. Shared families take
    # OPT-IN parameters; see painted_metal.
    aggregate = _value_noise(size, size // 2, rng)
    blotch = _fbm(size, rng, base_cells=3, octaves=4)
    color = _colorize(base, 0.35 + aggregate * 0.4 + blotch * 0.25, 0.16)
    height = aggregate * 0.12
    roughness = 0.88 + (blotch - 0.5) * 0.08
    return color, height, roughness.clip(0, 1), None


def wood_plank(size, rng, early=(0.455, 0.268, 0.146),
               late=(0.088, 0.040, 0.019), rings=14.0, figure=1.0,
               pore=1.0, sheen=1.0):
    """Long plain-sawn board, PERIODIC along the grain axis (u).

    The ``wood`` family is a one-shot board FACE - its rings radiate
    from a fixed pith point, so tiling it down a long plank breaks with
    a hard seam at every repeat (catapult seesaw play-test 2026-08-13:
    "create a texture so we don't have to have seams"). Here the ring
    coordinate is distance from a pith PLANE below the board, warped by
    periodic fbm along x - u tiles seamlessly forever, v spans the board
    face width one-shot (callers map v 0..1 across the board, so v never
    wraps). Long wavy parallel ring lines with occasional cathedral
    crests where the wander pinches - which is what a long plain-sawn
    board actually shows. Grain runs along +X."""

    early = np.asarray(early, dtype=float)
    late = np.asarray(late, dtype=float)
    yy = np.mgrid[0:size, 0:size][0].astype(float) / float(size)

    wander = _fbm(size, rng, base_cells=2, octaves=3)
    ripple = _fbm(size, rng, base_cells=6, octaves=3)
    d = (yy - 1.35) + (wander - 0.5) * 0.24 * figure + (ripple - 0.5) * 0.035
    # Uneven growth years (same monotone-warp trick as ``wood``; depends
    # only on d, so periodicity in x survives).
    d = d + 0.055 * np.sin(d * 9.3) + 0.021 * np.sin(d * 23.7 + 1.7)

    phase = (np.abs(d) * rings) % 1.0
    band = np.clip(1.0 - np.abs(phase - 0.82) / 0.155, 0.0, 1.0) ** 1.25
    lead = np.clip((phase - 0.30) / 0.52, 0.0, 1.0) ** 2.2 * 0.30
    band = np.clip(band + lead, 0.0, 1.0)
    band *= 0.62 + 0.55 * _fbm(size, rng, base_cells=5, octaves=3)
    band = np.clip(band, 0.0, 1.0)

    fibre = _streaks(size, rng, cells=max(160, size // 2), length_frac=0.16)
    drift = _fbm(size, rng, base_cells=2, octaves=3)

    mix = np.clip(band * 0.96 + (fibre - 0.5) * 0.34, 0.0, 1.0)
    color = early[None, None, :] + (late - early)[None, None, :] * mix[..., None]
    color *= (0.955 + drift * 0.09)[..., None]
    color *= (0.955 + (fibre - 0.5) * 0.19)[..., None]

    vessel = _streaks(size, rng, cells=max(64, size // 4), length_frac=0.035)
    ticks = np.clip((vessel - 0.62) * 4.2, 0.0, 1.0) ** 1.4
    ticks *= (0.35 + 0.65 * band) * pore
    color *= 1.0 - ticks[..., None] * 0.42

    height = band * 0.05 + (fibre - 0.5) * 0.02 - ticks * 0.55
    roughness = (0.34 - 0.16 * sheen) + (1.0 - band) * 0.03 + ticks * 0.30
    roughness = roughness + (drift - 0.5) * 0.03
    return color.clip(0, 1), height, roughness.clip(0.02, 1.0), None


def end_grain(size, rng, early=(0.50, 0.32, 0.165),
              late=(0.155, 0.082, 0.042), ring_pitch=0.055,
              aspect=3.03, pith_drop=1.9):
    """Crosscut butt end of a plain-sawn board: growth-ring ARCS.

    Added 2026-08-13 (catapult play-test round 4: "the grain texture on
    the end edge of the long boards seem to not be in the correct
    direction"). A board's cut end never shows face grain - it shows
    the log's rings in cross-section: concentric arcs curving from a
    pith somewhere below the board, rough and thirstier than the face.
    One-shot at the butt face's true ``aspect`` (width/thickness), face
    coords in face-height units, pith ``pith_drop`` heights below
    center so the arcs bow downward the way a plain-sawn board's do.
    """

    yy, xx = np.mgrid[0:size, 0:size].astype(float) / float(size)
    fx = (xx - 0.5) * aspect
    fy = (1.0 - yy) - 0.5
    wobble = _fbm(size, rng, base_cells=3, octaves=4)
    r = np.hypot(fx, fy + pith_drop) + (wobble - 0.5) * 0.1
    phase = (r / ring_pitch) % 1.0
    # Latewood band with a soft leading edge and hard trailing edge,
    # same asymmetry the face families use.
    late_band = (np.clip((phase - 0.5) * 3.2, 0.0, 1.0)
                 * np.clip((1.0 - phase) * 9.0, 0.0, 1.0))
    fine = _value_noise(size, size // 3, rng)
    fibre = _value_noise(size, size // 2, rng)
    mix = np.clip(late_band + (fine - 0.5) * 0.25, 0.0, 1.0)[..., None]
    color = (np.array(early)[None, None, :] * (1 - mix)
             + np.array(late)[None, None, :] * mix)
    # End grain is open-pored and drinks the finish: darker overall,
    # speckled, no sheen.
    color *= 0.72 + fibre[..., None] * 0.28
    height = -late_band * 0.06 + (fibre - 0.5) * 0.05
    roughness = 0.68 + (fine - 0.5) * 0.12 + late_band * 0.08
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def cast_iron(size, rng, base=(0.16, 0.155, 0.16), oxide=(0.32, 0.19, 0.12),
              contrast=1.0):
    """Sand-cast iron for the big drop weight (2026-08-13 play-test:
    "much more realistic textures for the steel weight" - the borrowed
    concrete-fine map smeared on the frustum's unmapped UVs).

    Four honest scales, none of them a countable landmark: casting-sand
    granular skin (two frequencies), mill-scale mottle drifting the tone,
    sparse warm oxide bloom clustered by a broad mask, and faint vertical
    weather streaks (the steel_worn smear idiom, transposed so runoff
    runs DOWN the face when u is horizontal)."""

    grain = _value_noise(size, max(8, size // 3), rng)
    grain2 = _value_noise(size, max(8, size // 6), rng)
    mottle = _fbm(size, rng, base_cells=8, octaves=4)
    runoff = _streaks(size, rng, max(8, size // 4), length_frac=0.12).T
    bloom = _fbm(size, rng, base_cells=16, octaves=4)
    cluster = _fbm(size, rng, base_cells=4, octaves=2)
    rust = (np.clip((bloom - 0.62) * 2.4, 0.0, 1.0) ** 1.6
            * np.clip((cluster - 0.35) * 1.6, 0.0, 1.0))
    rust = np.clip(rust, 0.0, 0.5)
    tone = (0.42 + (mottle - 0.5) * 0.28 + (grain - 0.5) * 0.16
            + (grain2 - 0.5) * 0.10)
    # `contrast` scales the tone spread and DEFAULTS TO A NO-OP, so every
    # existing consumer regenerates byte-identical.
    #
    # _colorize is purely multiplicative, so the LINEAR relative contrast
    # here is the same whatever the base. What is not the same is how many
    # 8-bit code values it survives as: sRGB encoding is steep in the
    # shadows and flat higher up, so the identical linear grain that spans
    # a usable spread on a near-black casting collapses to under one code
    # value of standard deviation on a light one. high_five lightened its
    # iron 5.7x to get the castings above the enamel and the sand-cast
    # grain quietly went with it. This is the knob that buys it back, and
    # it is a parameter rather than an edit because cast_iron is SHARED —
    # see the guard on `oxide` directly below.
    color = _colorize(base, tone, 0.10 * contrast)
    color *= 0.94 + runoff[..., None] * 0.12
    # A PARAMETER, defaulting to the original display value so every
    # existing consumer regenerates byte-identical.
    #
    # It was briefly hard-coded to its linear form, because under srgb=True
    # the display value encodes to a pale milky tan instead of rust. That
    # was right about this mod and wrong about the kit: cast_iron is SHARED,
    # the literal is unconditional, and it moved catapult_seesaw
    # (max|d| = 31) and sumo_gyro_platform (max|d| = 17) off their shipped
    # bytes. Exactly the same mistake as the one asphalt's guard comment
    # names, made twice in two rounds. A shared family takes a parameter.
    oxide = np.asarray(oxide, dtype=float)
    color = color * (1 - rust[..., None]) + oxide[None, None, :] * rust[..., None]
    height = ((grain - 0.5) * 0.09 + (grain2 - 0.5) * 0.05
              + (mottle - 0.5) * 0.04 - rust * 0.03)
    roughness = (0.56 + (mottle - 0.5) * 0.16 + (grain - 0.5) * 0.10
                 + rust * 0.24 + (runoff - 0.5) * 0.06)
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def ramp_deck(size, rng, base=(0.16, 0.16, 0.17), aspect=1.782,
              edge_frac=0.0625, chevrons=(0.30, 0.58),
              hazard1=(0.95, 0.75, 0.08), hazard2=(0.12, 0.12, 0.13),
              paint=(0.92, 0.9, 0.85)):
    """One-shot ramp surface: asphalt with hazard edge bands and painted
    chevrons IN the map, mapped 0..1 across the whole deck face.

    Added 2026-08-13 (catapult seesaw play-test): marking GEOMETRY on a
    drivable surface always betrays itself in-engine - even 4 mm plates
    cast shadows and catch edge light ("should appear like they're
    painted on ... no shadow or edge"). Paint that must read as paint
    has to live in the texture, and a tiled map cannot carry one-shot
    glyphs, so this family draws at the deck's true aspect (u across the
    ramp, v up the slope; chevrons point +v) and the caller maps the top
    face 0..1. Height stays flat under the paint - that is the point.
    """

    from PIL import ImageDraw

    aggregate = _value_noise(size, size // 2, rng)
    blotch = _fbm(size, rng, base_cells=3, octaves=4)
    color = _colorize(base, 0.35 + aggregate * 0.4 + blotch * 0.25, 0.16)
    height = aggregate * 0.12
    roughness = 0.88 + (blotch - 0.5) * 0.08

    # Chevron mask, drawn at true aspect then stretched square. PIL y
    # grows down and texture v samples from the image bottom, so
    # "pointing up-ramp (+v)" is apex toward SMALL PIL y.
    strip_w = size * 2
    strip_h = max(64, int(strip_w / aspect))
    pnt = Image.new("L", (strip_w, strip_h), 0)
    draw = ImageDraw.Draw(pnt)
    ww = int(strip_w * 0.21)          # half wingspan
    rise = int(strip_h * 0.17)        # apex rise
    thick = int(strip_h * 0.115)      # band thickness along v
    for v_center in chevrons:
        cy = int((1.0 - v_center) * strip_h)
        cx = strip_w // 2
        draw.polygon(
            [
                (cx - ww, cy + rise // 2),
                (cx, cy - rise // 2),
                (cx + ww, cy + rise // 2),
                (cx + ww, cy + rise // 2 + thick),
                (cx, cy - rise // 2 + thick),
                (cx - ww, cy + rise // 2 + thick),
            ],
            fill=255,
        )
    paint_mask = np.asarray(
        pnt.resize((size, size), Image.LANCZOS), dtype=float) / 255.0

    # Hazard edge bands: diagonal stripes at ~45 degrees in METERS (u and
    # v texel densities differ by `aspect`).
    yy, xx = np.mgrid[0:size, 0:size].astype(float) / float(size)
    band = ((xx < edge_frac) | (xx > 1.0 - edge_frac)).astype(float)
    diag = ((xx * 12.0 + (1.0 - yy) * 12.0 / aspect) % 1.0 < 0.5).astype(float)
    wear = 0.72 + 0.38 * blotch

    haz_color = (np.array(hazard1)[None, None, :] * diag[..., None]
                 + np.array(hazard2)[None, None, :] * (1 - diag[..., None]))
    band_m = (band * wear)[..., None]
    color = color * (1 - band_m) + haz_color * band_m
    paint_m = (paint_mask * (1 - band) * wear)[..., None]
    color = color * (1 - paint_m) + np.array(paint)[None, None, :] * paint_m
    roughness = roughness - band * 0.22 - paint_mask * 0.3
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def kick_pad(size, rng, base=(0.16, 0.16, 0.17), paint=(0.92, 0.9, 0.85),
             target=(0.82, 0.12, 0.08), half_u=2.6, half_v=2.8,
             frame_outer=(2.1, 2.3), frame_width=0.2, corner_radius=0.1,
             stroke_length=3.4, stroke_width=0.55):
    """One-shot kick-pad skin: asphalt with the white border frame and the
    red X painted IN the map, 0..1 across the whole pad footprint.

    Added 2026-08-13 (boot play-test, same law as ramp_deck): marking
    geometry on a drivable surface always betrays itself in-engine — the
    boot pad's 2 cm border plates and X strokes cast shadows and caught
    edge light. All geometry params are METERS (``half_u``/``half_v`` are
    the pad's half extents including the skirt), so the paint lands
    exactly where the old plates sat. Height stays flat under the paint —
    that is the point.
    """

    from PIL import ImageDraw

    aggregate = _value_noise(size, size // 2, rng)
    blotch = _fbm(size, rng, base_cells=3, octaves=4)
    color = _colorize(base, 0.35 + aggregate * 0.4 + blotch * 0.25, 0.16)
    height = aggregate * 0.12
    roughness = 0.88 + (blotch - 0.5) * 0.08

    # Masks drawn oversized then LANCZOS-downsampled for soft painted
    # edges. PIL y grows down while texture v samples from the image
    # bottom, so +v (authored +y) maps to SMALL PIL y.
    canvas_px = size * 2

    def to_px(mx, my):
        return (
            (mx / (2.0 * half_u) + 0.5) * canvas_px,
            (0.5 - my / (2.0 * half_v)) * canvas_px,
        )

    frame_img = Image.new("L", (canvas_px, canvas_px), 0)
    draw = ImageDraw.Draw(frame_img)
    x0, y1 = to_px(-frame_outer[0], -frame_outer[1])
    x1, y0 = to_px(frame_outer[0], frame_outer[1])
    width_px = int(round(frame_width / (2.0 * half_u) * canvas_px))
    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=int(round(corner_radius / (2.0 * half_u) * canvas_px)),
        outline=255,
        width=max(2, width_px),
    )

    x_img = Image.new("L", (canvas_px, canvas_px), 0)
    draw = ImageDraw.Draw(x_img)
    for yaw in (45.0, -45.0):
        c, s = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
        half_l, half_w = stroke_length / 2.0, stroke_width / 2.0
        corners = [
            (dl * c - dw * s, dl * s + dw * c)
            for dl, dw in ((-half_l, -half_w), (half_l, -half_w),
                           (half_l, half_w), (-half_l, half_w))
        ]
        draw.polygon([to_px(mx, my) for mx, my in corners], fill=255)

    frame_mask = np.asarray(
        frame_img.resize((size, size), Image.LANCZOS), dtype=float) / 255.0
    x_mask = np.asarray(
        x_img.resize((size, size), Image.LANCZOS), dtype=float) / 255.0

    wear = 0.72 + 0.38 * blotch
    frame_m = (frame_mask * wear).clip(0, 1)[..., None]
    color = color * (1 - frame_m) + np.array(paint)[None, None, :] * frame_m
    x_m = (x_mask * wear).clip(0, 1)[..., None]
    color = color * (1 - x_m) + np.array(target)[None, None, :] * x_m
    roughness = roughness - (frame_mask + x_mask).clip(0, 1) * 0.3
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def target_decal(size, rng, ring=(0.82, 0.12, 0.08), field=(0.92, 0.9, 0.85),
                 half_u=2.2, half_v=2.2, ring_outer=2.0, ring_inner=1.62,
                 field_radius=1.6, stroke_length=3.2, stroke_width=0.46,
                 seams=(), seam_width=0.055):
    """Worn-paint bullseye DECAL: ring + white field + X, alpha-cutout.

    Added 2026-08-13 (catapult play-test round 4: "make the red circle
    with red x and white background look like it's painted onto the
    wood"). ramp_deck/kick_pad bake paint into an opaque surface map,
    but a plank deck is four individually-jittered BOARDS - an opaque
    skin would flatten them. This family returns an opacity map (the
    builder turns that into an alphaTest cutout), so ONLY the paint
    renders, millimetres over the boards, and the wood stays wood.
    ``seams`` (u-axis positions in meters) erases the paint over each
    board gap - real deck paint breaks at the joints, and those breaks
    are what sell it as paint. All geometry params are METERS on the
    sheet the caller maps 0..1; alpha is guaranteed dead below v=0.05
    so side faces parked at (0.5, 0.02) never render.
    """

    from PIL import ImageDraw

    canvas_px = size * 2
    cx = cy = canvas_px / 2.0

    def to_px(mx, my):
        return ((mx / (2.0 * half_u) + 0.5) * canvas_px,
                (0.5 - my / (2.0 * half_v)) * canvas_px)

    def radius_px(m):
        return m / (2.0 * half_u) * canvas_px

    ring_img = Image.new("L", (canvas_px, canvas_px), 0)
    draw = ImageDraw.Draw(ring_img)
    for r, fill in ((ring_outer, 255), (ring_inner, 0)):
        rp = radius_px(r)
        draw.ellipse((cx - rp, cy - rp, cx + rp, cy + rp), fill=fill)

    field_img = Image.new("L", (canvas_px, canvas_px), 0)
    draw = ImageDraw.Draw(field_img)
    rp = radius_px(field_radius)
    draw.ellipse((cx - rp, cy - rp, cx + rp, cy + rp), fill=255)

    x_img = Image.new("L", (canvas_px, canvas_px), 0)
    draw = ImageDraw.Draw(x_img)
    for yaw in (45.0, -45.0):
        c, s = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
        half_l, half_w = stroke_length / 2.0, stroke_width / 2.0
        corners = [
            (dl * c - dw * s, dl * s + dw * c)
            for dl, dw in ((-half_l, -half_w), (half_l, -half_w),
                           (half_l, half_w), (-half_l, half_w))
        ]
        draw.polygon([to_px(mx, my) for mx, my in corners], fill=255)

    def to_mask(img):
        return np.asarray(img.resize((size, size), Image.LANCZOS),
                          dtype=float) / 255.0

    ring_mask = to_mask(ring_img)
    field_mask = to_mask(field_img)
    x_mask = to_mask(x_img)

    # Wear: alpha thins over traffic blotches and flakes out in small
    # chips (alphaRef 96 turns the thin end into ragged painted edges).
    blotch = _fbm(size, rng, base_cells=3, octaves=4)
    chip = _value_noise(size, size // 6, rng)
    wear = np.clip(0.62 + blotch * 0.5 - (chip > 0.84) * 0.55, 0.0, 1.0)

    alpha = np.clip(ring_mask + field_mask + x_mask, 0.0, 1.0) * wear
    yy, xx = np.mgrid[0:size, 0:size].astype(float) / float(size)
    for seam_m in seams:
        su = seam_m / (2.0 * half_u) + 0.5
        half_w = seam_width / (2.0 * half_u) / 2.0
        alpha *= 1.0 - (np.abs(xx - su) < half_w)
    alpha[int(size * 0.95):, :] = 0.0  # side-face park row stays dead

    color = np.zeros((size, size, 3)) + np.array(field)[None, None, :]
    for mask, paint in ((ring_mask, ring), (x_mask, ring)):
        m = mask[..., None]
        color = color * (1 - m) + np.array(paint)[None, None, :] * m
    # Sun-fade and grime so the paint is not one flat chip of colour.
    color *= 0.86 + blotch[..., None] * 0.22
    height = np.zeros((size, size))
    roughness = 0.52 + (blotch - 0.5) * 0.2 + (1.0 - wear) * 0.18
    rgba = np.concatenate([color.clip(0, 1), alpha[..., None]], axis=-1)
    return rgba, height, roughness.clip(0.05, 1), alpha


def stripe_decal(size, rng, c1=(0.95, 0.75, 0.08), c2=(0.12, 0.12, 0.13),
                 width_m=4.4, height_m=0.875, period_m=0.62,
                 seams=(), seam_width=0.055):
    """Diagonal hazard band as a worn alpha-cutout paint skin (same law
    and same board-seam breaks as target_decal). Both stripe phases are
    PAINT - dark stripes over bare wood would otherwise vanish - and the
    band occupies v 0.1..0.9 of the sheet so side faces parked at
    (0.5, 0.02) stay transparent. Stripes run 45 degrees in METERS.
    """

    yy, xx = np.mgrid[0:size, 0:size].astype(float) / float(size)
    diag = ((xx * width_m + (1.0 - yy) * height_m) / period_m % 1.0
            < 0.5).astype(float)
    band = ((yy > 0.1) & (yy < 0.9)).astype(float)

    blotch = _fbm(size, rng, base_cells=3, octaves=4)
    chip = _value_noise(size, size // 6, rng)
    wear = np.clip(0.62 + blotch * 0.5 - (chip > 0.84) * 0.55, 0.0, 1.0)

    alpha = band * wear
    for seam_m in seams:
        su = seam_m / width_m + 0.5
        half_w = seam_width / width_m / 2.0
        alpha *= 1.0 - (np.abs(xx - su) < half_w)

    color = (np.array(c1)[None, None, :] * diag[..., None]
             + np.array(c2)[None, None, :] * (1 - diag[..., None]))
    color *= 0.86 + blotch[..., None] * 0.22
    height = np.zeros((size, size))
    roughness = 0.55 + (blotch - 0.5) * 0.2 + (1.0 - wear) * 0.18
    rgba = np.concatenate([color.clip(0, 1), alpha[..., None]], axis=-1)
    return rgba, height, roughness.clip(0.05, 1), alpha


def _streaks(size, rng, cells, length_frac=0.06):
    """Periodic directional grain: noise smeared along +X.

    Mill-finished and brushed steel is ANISOTROPIC - that directionality
    is most of what makes a grey surface read as metal rather than as
    grey. The old steel_worn faked it by collapsing a whole fbm to one
    row and tiling it, which gives perfectly straight full-width bands
    (identical on every row); this smears real 2-D noise over a finite
    run, so the grain has ends, wander and varying contrast.
    """

    field = _value_noise(size, cells, rng)
    run = max(2, int(size * length_frac))
    kernel = np.zeros(size)
    kernel[:run] = 1.0 / run
    smear = np.real(np.fft.ifft(np.fft.fft(field, axis=1)
                                * np.fft.fft(kernel)[None, :], axis=1))
    lo, hi = smear.min(), smear.max()
    return (smear - lo) / max(hi - lo, 1e-9)


def steel_worn(size, rng, base=(0.5, 0.53, 0.57), rough=0.42, relief=1.0):
    """Mill-finished structural steel: directional grain, rolling banding,
    scattered scuffs, faint weathering.

    Rebuilt 2026-08-10 (player: "the steel beam texture looks blocky like
    digital camo ... it should look realistic"). The camo was the old
    noise basis (see _value_noise), but once that was fixed this family
    had nothing left - a smooth 3-cell patina and one tiled scratch row
    is a flat grey wash at any distance. Steel needs three scales at once:
    grain you only resolve up close, rolling banding at the metre scale,
    and sparse bright scuffs that catch the light.
    """

    grain = _streaks(size, rng, max(8, size // 3), length_frac=0.09)
    micro = _streaks(size, rng, max(8, size // 2), length_frac=0.03)
    banding = _fbm(size, rng, base_cells=2, octaves=3)
    patina = _fbm(size, rng, base_cells=6, octaves=4)
    # Scuffs: short bright drags, sparse enough to read as damage rather
    # than as a pattern. Squared for soft ends, so they fade instead of
    # terminating on a hard threshold edge.
    scuff = np.clip((_streaks(size, rng, max(8, size // 6), 0.12) - 0.74)
                    * 3.6, 0.0, 1.0) ** 2
    tone = (0.40
            + banding * 0.22
            + (grain - 0.5) * 0.30
            + (micro - 0.5) * 0.12
            + (patina - 0.5) * 0.16)
    color = _colorize(base, tone, 0.06)
    # Direct multiplicative grain on top of the colorised base: _colorize
    # compresses toward the base hue, so tone alone reads as a flat wash
    # at any distance. This is what makes the beam look rolled.
    color *= (0.86 + grain[..., None] * 0.28) * (0.96 + micro[..., None] * 0.08)
    color += scuff[..., None] * 0.22
    # `relief` scales the whole field. Authored at 0.05 amplitude this map
    # quantised to a single byte and shipped literally constant.
    height = ((grain - 0.5) * 0.05 + (micro - 0.5) * 0.02 - scuff * 0.03) * relief
    roughness = (rough
                 + (patina - 0.5) * 0.16
                 + (grain - 0.5) * 0.10
                 - scuff * 0.16)
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def machined_steel(size, rng, base=(0.44, 0.46, 0.49), rough=0.38, relief=1.0,
                   grain_scale=1.0):
    """Machined/turned hardware steel: tight short grain, oily mottle,
    values compressed toward one grey.

    Added 2026-08-13 (catapult play-test round 4: "make the texture for
    the steel more realistic" - the pillow-block washer face). steel_worn
    is ROLLED MILL PLATE: metre-scale banding and long high-contrast
    grain that reads right on a 13 m beam but turns into garish bright
    streaks on a 0.6 m washer face. Machined parts are the opposite
    regime: the tool leaves fine short scratches, handling leaves faint
    oil smudges, and the whole value range stays within a stop. Realism
    here comes from the ROUGHNESS variation (oil patches go shiny), not
    from albedo contrast.
    """

    # Two grain scales: fine tooling scratches (height/roughness only -
    # they mip away in colour) and a medium-scale directional wash that
    # actually survives at viewing distance.
    # ``grain_scale`` COARSENS the tooling grain. At 1.0 - the default, and the
    # behaviour every other mod in the pack was tuned against - the fine grain
    # is a two-texel feature, so it is gone by the first mip and the whole
    # family measured p99.9 15.2 degrees against a 29-46 band: the flattest
    # functional map in the pack, on 2,420 triangles of dock girder, gangway
    # frame, handrail and port bolts that read as pale plastic because of it.
    # A larger value is a coarser tool, which is what a fabrication that size
    # would leave anyway.
    fine_cells = max(16, int(size // 2 * grain_scale))
    med_cells = max(8, int(size // 8 * grain_scale))
    grain_fine = _streaks(size, rng, fine_cells, length_frac=0.02 / max(grain_scale, 0.05))
    grain_med = _streaks(size, rng, med_cells, length_frac=0.05 / max(grain_scale, 0.05))
    micro = _value_noise(size, size // 2, rng)
    mottle = _fbm(size, rng, base_cells=5, octaves=4)
    oil = np.clip((_fbm(size, rng, base_cells=3, octaves=3) - 0.58) * 3.2,
                  0.0, 1.0) ** 1.5
    scuff = np.clip((_streaks(size, rng, max(8, size // 6), 0.08) - 0.78)
                    * 4.0, 0.0, 1.0) ** 2
    tone = (0.5
            + (grain_med - 0.5) * 0.16
            + (micro - 0.5) * 0.06
            + (mottle - 0.5) * 0.12
            - oil * 0.12)
    color = _colorize(base, tone, 0.05)
    color *= ((0.9 + mottle[..., None] * 0.14)
              * (0.93 + grain_med[..., None] * 0.14)
              * (0.97 + grain_fine[..., None] * 0.06))
    color += scuff[..., None] * 0.14
    # `relief` scales the whole field; see steel_worn.
    height = (
        (grain_fine - 0.5) * 0.025 + (grain_med - 0.5) * 0.01 - scuff * 0.015
    ) * relief
    roughness = (rough
                 + (mottle - 0.5) * 0.14
                 + (grain_fine - 0.5) * 0.08
                 + oil * 0.12
                 - scuff * 0.08)
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def forged_ball(size, rng, base=(0.14, 0.13, 0.14)):
    """Forged wrecking-ball steel: hammer-scale mottle, bright scars, faint
    rust bloom in the recesses."""

    scale_mottle = _fbm(size, rng, base_cells=6, octaves=4)
    scars = (_fbm(size, rng, base_cells=5, octaves=3) > 0.8).astype(float)
    rust = _fbm(size, rng, base_cells=3, octaves=3)
    color = _colorize(base, 0.4 + scale_mottle * 0.35, 0.18)
    color[..., 0] += rust * 0.1 * (1 - scale_mottle)
    color[..., 1] += rust * 0.04 * (1 - scale_mottle)
    color += scars[..., None] * 0.28
    height = scale_mottle * 0.12 - scars * 0.1
    roughness = 0.5 + rust * 0.25 - scars * 0.2
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def hazard_chevron(size, rng, c1=(0.95, 0.75, 0.08), c2=(0.12, 0.12, 0.13),
                   glow=False, glow_floor=0.10, relief=0.0):
    """Painted hazard chevrons.

    ``glow`` returns an emissive channel that follows the STRIPES. Without one
    a material with an emissiveFactor emits uniformly - AGENTS.md's own
    photometric ledger measures a missing map at 0.991 of the white-map cell -
    so an emissive chevron glows just as brightly through its dark stripes as
    its light ones and erases the pattern it exists to draw. The glow map is
    decoded as sRGB like any `.color`, so the dark stripes keep a real floor
    rather than going to zero.

    The height field is no longer decorative either: paint laid over steel
    stands proud of it, and at 0.02 amplitude the normal map came out
    literally constant (128, 128, 255) - a blank map on one of the few
    surfaces the player stands right next to.
    """

    diag = (_stripes(size, 4.0, axis=1) + _stripes(size, 4.0, axis=0)) % 1.0
    stripe = (diag < 0.5).astype(float)
    edge = np.clip(1.0 - np.abs(diag - 0.5) / 0.06, 0.0, 1.0)
    grime = _fbm(size, rng, base_cells=3, octaves=3)
    fine = _fbm(size, rng, base_cells=max(48, size // 12), octaves=3)
    color = np.array(c1) * stripe[..., None] + np.array(c2) * (1 - stripe[..., None])
    color *= 0.75 + grime[..., None] * 0.35
    # Paint film + its rolled edge, plus the steel tooth under it. OPT-IN:
    # `relief` defaults to 0 so every mod that already ships this family keeps
    # its exact bytes - a shared kit cannot quietly re-cut twenty other mods'
    # normal maps and invalidate their cooked-DDS harvests.
    if relief <= 0.0:
        height = grime * 0.02
        roughness = 0.45 + grime * 0.2
    else:
        height = (stripe * 0.22 + edge * 0.10 + (fine - 0.5) * 0.16) * relief
        roughness = 0.45 + grime * 0.2 + (1.0 - stripe) * 0.10
    if not glow:
        return color.clip(0, 1), height, roughness, None
    # NEUTRAL GREYSCALE. The emissive map is a MASK saying which parts of the
    # chevron are lit; the hue belongs to the material's emissiveFactor, once.
    # Tinting the map by c1 as well multiplied the hue by itself, so an amber
    # marking emitted a saturated orange nothing on the prop matched. Nothing
    # else in the pack asks this family for a glow map, so there is no old
    # behaviour to preserve here - see the note above about relief.
    emissive = np.zeros((size, size, 3))
    intensity = glow_floor + stripe * (1.0 - glow_floor)
    for channel in range(3):
        emissive[..., channel] = intensity
    return color.clip(0, 1), height, roughness, None, emissive.clip(0, 1)


def eggshell(size, rng, base=(0.91, 0.87, 0.76), speck=(0.42, 0.33, 0.22)):
    pores = _value_noise(size, size // 3, rng)
    mottle = _fbm(size, rng, base_cells=4, octaves=3)
    color = _colorize(base, 0.45 + mottle * 0.25, 0.05)
    speckles = np.zeros((size, size))
    ys = rng.integers(0, size, 420)
    xs = rng.integers(0, size, 420)
    radii = rng.integers(1, 5, 420)
    yy, xx = np.mgrid[0:size, 0:size]
    for y, x, radius in zip(ys, xs, radii, strict=True):
        dy = np.minimum(np.abs(yy - y), size - np.abs(yy - y))
        dx = np.minimum(np.abs(xx - x), size - np.abs(xx - x))
        speckles = np.maximum(speckles, ((dy * dy + dx * dx) < radius * radius) * 1.0)
    color = color * (1 - speckles[..., None] * 0.85) + np.array(speck) * speckles[..., None]
    height = mottle * 0.05 - pores * 0.03 - speckles * 0.02
    roughness = 0.55 + (pores - 0.5) * 0.1
    return color.clip(0, 1), height, roughness, None


def whale_skin(size, rng, base=(0.3, 0.47, 0.65), pleats=0.0):
    mottle = _fbm(size, rng, base_cells=3, octaves=4)
    fleck = _value_noise(size, size // 3, rng)
    color = _colorize(base, 0.4 + mottle * 0.35 + fleck * 0.1, 0.12)
    height = mottle * 0.08
    roughness = 0.32 + (mottle - 0.5) * 0.12
    if pleats > 0:
        groove = 0.5 - 0.5 * np.cos(_stripes(size, pleats, axis=1) * 2 * np.pi)
        height -= groove * 0.35
        color *= 0.88 + groove[..., None] * 0.12
        roughness += groove * 0.08
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def mesh_weave(size, rng, base=(0.2, 0.62, 0.28), wire=0.16):
    u = _stripes(size, 10.0, axis=1)
    v = _stripes(size, 10.0, axis=0)
    on_u = (np.minimum(u, 1 - u) < wire).astype(float)
    on_v = (np.minimum(v, 1 - v) < wire).astype(float)
    wires = np.maximum(on_u, on_v)
    shade = _value_noise(size, size // 8, rng)
    color = _colorize(base, 0.5 + shade * 0.3, 0.1)
    opacity = wires
    height = wires * 0.2 + on_u * 0.1
    roughness = np.full((size, size), 0.5)
    rgba = np.concatenate([color, opacity[..., None]], axis=-1)
    return rgba, height, roughness, opacity


def straw(size, rng, base=(0.78, 0.62, 0.22)):
    fibers = _fbm(size, rng, base_cells=2, octaves=5)
    fibers = np.tile(fibers.mean(axis=0, keepdims=True), (size, 1))
    crosses = _fbm(size, rng, base_cells=8, octaves=3)
    color = _colorize(base, 0.3 + fibers * 0.45 + crosses * 0.25, 0.16)
    height = fibers * 0.12
    roughness = 0.78 + (crosses - 0.5) * 0.1
    return color, height, roughness, None


def drum_perforated(size, rng, base=(0.72, 0.74, 0.78), rows=10, hole=0.012):
    """Perforated stainless washer drum: brushed base + hex hole grid.

    2026-08-13 (player: the drum back plate's holes read "blotchy / low
    resolution"). The mask used to be a BINARY radius test, so every hole
    was a hard-edged ~12 px circle - fine while tiled every 1.9 m on the
    liner, hideous on the back plate where one texture is stretched 1:1
    across the whole 8.3 m disc and each hole blows up to half a metre of
    stair-stepped edge. Two fixes: the hole edge is now anti-aliased in
    PIXEL space (a ~1.5 px smoothstep, so it stays crisp at any size or
    density), and callers can raise `rows` to punch a denser, finer, more
    realistic pattern instead of a few giant portholes. Each hole also
    gets a punched rim - real perforated steel dimples outward where the
    tool pushed through - which reads far better under a normal map than
    a flat-bottomed crater.
    """

    color, height, roughness, _ = brushed_metal(size, rng, base, rough=0.24)
    yy, xx = np.mgrid[0:size, 0:size].astype(float) / size
    # Distance to the nearest hole centre by CELL FOLDING, not a loop over
    # every hole: at high densities (the back plate punches ~900) a
    # per-hole pass over a 2048^2 array is minutes of work, and the hole
    # radius is always far smaller than half the row pitch, so the nearest
    # centre is guaranteed to be the one owning the pixel's own cell.
    # `rows` must be EVEN for the staggered pattern to tile seamlessly.
    pitch = 1.0 / rows
    row_index = np.floor(yy * rows)
    cy = (row_index + 0.5) * pitch
    offset = np.where(row_index % 2 == 1, 0.5 * pitch, 0.0)
    col_index = np.floor((xx - offset) * rows)
    cx = (col_index + 0.5) * pitch + offset
    dy = yy - cy
    dx = xx - cx
    dist = np.sqrt(dy * dy + dx * dx)
    # Anti-alias width: ~1.5 texels expressed in UV units.
    aa = 1.5 / size
    rim = hole * 0.45
    holes = np.clip((hole - dist) / aa + 0.5, 0.0, 1.0)
    rims = np.clip(
        np.clip((hole + rim - dist) / rim, 0.0, 1.0) - holes, 0.0, 1.0)
    color *= 1 - holes[..., None] * 0.88
    # Rim catches a touch of light; the bore goes dark and rough.
    color *= 1 + rims[..., None] * 0.12
    height = height - holes * 0.5 + rims * 0.16
    roughness = roughness + holes * 0.3 - rims * 0.05
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def water_surface(size, rng, base=(0.55, 0.75, 0.85), waves=34, chop=0.35):
    """Tiling water ripple field, Gerstner-style.

    2026-08-13 (player: "the water effect is still lacking, can't we
    borrow how the BeamNG ocean works"). BeamNG's own water shader gets
    its motion from tiling RIPPLE NORMAL MAPS scrolled in several
    directions (see /assets/materials/tileable/water/water_effects/
    ripple*_nm.normal.dds and the italy river_white_water material). Those
    maps are not noise - they are interlocking directional wavefronts, and
    fbm noise cannot fake them: noise gives lumpy blobs with no direction,
    which is exactly why the old map read as "wobbling plastic".

    This sums many directional sine waves with INTEGER wave vectors, so
    the field tiles seamlessly at any texture size, plus a sharpened chop
    term for the fine crosshatch. Amplitude falls with frequency (a real
    wave spectrum), and crests are sharpened - water peaks are narrower
    than its troughs.
    """

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64) / size
    height = np.zeros((size, size))
    weight = 0.0
    # Spectrum calibrated against the game's own ripple_nm.normal.dds
    # (BC5U 512px, decoded and compared 2026-08-13): it is DENSE FINE
    # WIND CHOP with a dominant direction, not big smooth swells - the
    # first pass here was far too low-frequency and read as satin. Sample
    # in polar form so a dominant wind direction can be favoured, then
    # round the wave vector to integers to keep the tile seamless.
    wind = float(rng.random()) * 2.0 * np.pi
    for index in range(waves):
        # Frequency band: fine ripples, spread over roughly 4..17 tiles.
        freq = 4.0 + float(rng.random()) ** 1.3 * 13.0
        # Cluster around the wind direction, with spread.
        angle = wind + float(rng.normal(0.0, 0.65))
        kx = int(round(freq * np.cos(angle)))
        ky = int(round(freq * np.sin(angle)))
        if kx == 0 and ky == 0:
            continue
        mag = float(np.hypot(kx, ky))
        amplitude = 1.0 / (mag ** 1.15)
        phase = float(rng.random()) * 2.0 * np.pi
        height += amplitude * np.sin(2.0 * np.pi * (kx * xx + ky * yy) + phase)
        weight += amplitude
    height /= max(weight, 1e-9)
    # Fine crosshatch chop riding the swell - sampled in polar form too so
    # it does not lay down a regular grid.
    chop_waves = 26
    for index in range(chop_waves):
        freq = 18.0 + float(rng.random()) * 26.0
        angle = float(rng.random()) * 2.0 * np.pi
        kx = int(round(freq * np.cos(angle)))
        ky = int(round(freq * np.sin(angle)))
        if kx == 0 and ky == 0:
            continue
        phase = float(rng.random()) * 2.0 * np.pi
        height += (chop / chop_waves) * np.sin(
            2.0 * np.pi * (kx * xx + ky * yy) + phase)
    lo, hi = height.min(), height.max()
    height = (height - lo) / max(hi - lo, 1e-9)
    # Sharpen crests: real water has narrow peaks and broad troughs.
    height = height ** 1.45

    color = _colorize(base, 0.45 + height * 0.35, 0.07)
    # Crests catch a little foam-white; troughs stay deep.
    color = color * (1 - height[..., None] * 0.12) + height[..., None] * 0.12
    roughness = np.full((size, size), 0.04) + height * 0.03
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def suds_foam(size, rng, base=(0.95, 0.965, 0.98), coverage=0.52):
    """Floating detergent suds: bubble clumps with a patchy alpha mask.

    2026-08-13 (washer water round). The foam used to be an untextured
    sheet spanning nearly the whole waterline, so the player was looking
    at a white LID and almost never at the water - a large part of why the
    water "looked lacking" no matter how good the ripples got. Real suds
    float in broken rafts, so this returns an OPACITY map: big soft clumps
    (low-frequency fbm thresholded) eaten into by bubble-scale noise, with
    the gaps letting the animated water show through.
    """

    rafts = _fbm(size, rng, base_cells=3, octaves=4)
    bubbles = _fbm(size, rng, base_cells=14, octaves=3)
    fine = _value_noise(size, size // 4, rng)

    # Threshold the rafts so `coverage` of the sheet survives.
    cut = float(np.quantile(rafts, 1.0 - coverage))
    mask = np.clip((rafts - cut) * 6.0 + 0.5, 0.0, 1.0)
    # Chew the raft edges with bubble-scale detail so the border is foamy,
    # not a smooth blob outline.
    mask *= np.clip(0.35 + bubbles * 1.15, 0.0, 1.0)
    # Punch a few pinholes through the middle of the rafts.
    mask *= np.clip(0.55 + fine * 0.75, 0.0, 1.0)
    opacity = np.clip(mask, 0.0, 1.0)

    shade = 0.72 + bubbles * 0.28 + fine * 0.12
    color = _colorize(base, np.clip(shade, 0.0, 1.0), 0.03)
    height = bubbles * 0.55 + fine * 0.3
    roughness = np.full((size, size), 0.72) + bubbles * 0.14
    return color.clip(0, 1), height, roughness.clip(0, 1), opacity


def toast_crumb(size, rng, base=(0.82, 0.58, 0.22)):
    crumb = _value_noise(size, size // 3, rng)
    blotch = _fbm(size, rng, base_cells=3, octaves=3)
    color = _colorize(base, 0.35 + crumb * 0.35 + blotch * 0.3, 0.14)
    edge = np.minimum.reduce(
        [
            _stripes(size, 1.0, axis=1),
            1 - _stripes(size, 1.0, axis=1),
            _stripes(size, 1.0, axis=0),
            1 - _stripes(size, 1.0, axis=0),
        ]
    )
    crust = (edge < 0.08).astype(float)
    color = (
        color * (1 - crust[..., None] * 0.45) + np.array([0.4, 0.2, 0.06]) * crust[..., None] * 0.6
    )
    height = crumb * 0.1
    roughness = 0.8 + (blotch - 0.5) * 0.08
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def copper(size, rng, base=(0.545, 0.30, 0.195), rough=0.5,
           oxide=(0.28, 0.16, 0.11), verd=(0.38, 0.46, 0.42)):
    """Worn-penny architectural copper (player round 15: the louver fins
    should read as copper metal, "dull worn penny" chosen over shiny).

    Albedo mottling + vertical runoff streaks + sparse oxide flecks and a
    restrained patina drift in the recesses; metallic itself comes from
    the palette factor. Streaks use the steel_worn column-average idiom
    so they run down the fin, not across it."""

    # First cut rendered as muddy chocolate blotches (probe, build 63):
    # fleck threshold 0.62 x4 gain painted rust continents, streaks
    # vanished under them, and value 0.72 with metallic 0.85 went dark
    # in-engine. Now: bright warm base, dominant vertical runoff +
    # brushed grain, and oxide reduced to true speck scale.
    mottle = _fbm(size, rng, base_cells=4, octaves=4)
    runoff = _fbm(size, rng, base_cells=2, octaves=5)
    runoff = np.tile(runoff.mean(axis=0, keepdims=True), (size, 1))
    grain = _fbm(size, rng, base_cells=10, octaves=3)
    grain = np.tile(grain.mean(axis=0, keepdims=True), (size, 1))
    # Oxide as organic tarnish, not chips (player: "way too blocky
    # digital" - single-octave 48-cell noise thresholded hard renders as
    # rectangular pixel blobs, the concrete family's Minecraft failure
    # all over again). Multi-octave speck field, squared for soft edges,
    # clustered by a broad mask so tarnish pools instead of confetti,
    # capped so the blend never goes full-dark. Plus a fine micro grain
    # so arm's-length close-ups show surface, not smoothness.
    flecks = _fbm(size, rng, base_cells=24, octaves=4)
    cluster = _fbm(size, rng, base_cells=5, octaves=2)
    spots = np.clip((flecks - 0.60) * 2.2, 0.0, 1.0) ** 2
    dark = np.clip(spots * np.clip((cluster - 0.35) * 1.6, 0.0, 1.0), 0.0, 0.55)
    micro = _fbm(size, rng, base_cells=96, octaves=2)
    patina = np.clip((mottle - 0.72) * 3.0, 0.0, 1.0) * 0.10
    value = (0.80 + (mottle - 0.5) * 0.42 + (runoff - 0.5) * 0.34
             + (grain - 0.5) * 0.16 + (micro - 0.5) * 0.10)
    color = np.empty((size, size, 3))
    for channel, b in enumerate(base):
        color[..., channel] = b * value
    # PARAMETERS, defaulting to the original display values so every
    # existing consumer regenerates byte-identical. They were unconditional
    # body literals — the same trap cast_iron's `oxide` carried, and the
    # same one asphalt's guard comment names. Nothing in the pack sets
    # srgb=True on a copper entry yet, so it was latent rather than broken;
    # it is armed for whoever does it first, because a display value
    # re-encoded to sRGB comes out a pale milky tan instead of oxide.
    # A shared family takes a parameter. Third time in this file.
    oxide = tuple(oxide)
    verd = tuple(verd)
    for channel in range(3):
        color[..., channel] = color[..., channel] * (1 - dark) + oxide[channel] * dark
        color[..., channel] = color[..., channel] * (1 - patina) + verd[channel] * patina
    height = ((mottle - 0.5) * 0.08 + (grain - 0.5) * 0.05
              + (micro - 0.5) * 0.03 - dark * 0.03)
    roughness = (rough + (runoff - 0.5) * 0.2 + (grain - 0.5) * 0.1
                 + (micro - 0.5) * 0.08 + dark * 0.15 + (mottle - 0.5) * 0.06)
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def panel_legend(size, rng, labels=(), title="", aspect=2.0,
                 base=(0.055, 0.06, 0.068), ink=(0.92, 0.95, 0.99),
                 title_scale=0.088, label_scale=0.075, frame=True,
                 rules=()):
    """Engraved control-legend plate: near-black brushed field, machined
    hairline frame, cool-white title + per-button labels.

    ``labels`` is a sequence of (u, v, text) or (u, v, text, scale): u
    across the plate, v UP from the plate BOTTOM, both 0..1 in the plate
    face's own frame (the legend sheet in the generator authors exactly
    that UV mapping); the optional 4th element multiplies that label's
    type size (small-print scale marks, group sub-headings). Text is
    drawn at the plate's true aspect and then stretched into the square
    texture - drawing into the square squashes (marquee lesson).

    ``title_scale``/``label_scale`` are type heights as a fraction of the
    PLATE height, so a taller plate does not silently grow the print
    (2026-08-09h: the plate grew 0.95 -> 1.15 m for label room and fixed
    fractions would have eaten the room straight back)."""

    from PIL import ImageDraw, ImageFont

    strip_w = size * 2
    strip_h = max(64, int(strip_w / aspect))
    strip = Image.new("L", (strip_w, strip_h), 0)
    draw = ImageDraw.Draw(strip)
    font_path = None
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf",
                      r"C:\Windows\Fonts\arial.ttf"):
        try:
            ImageFont.truetype(candidate, 20)
            font_path = candidate
            break
        except OSError:
            continue

    def _font(px):
        if font_path:
            return ImageFont.truetype(font_path, px)
        return ImageFont.load_default()

    def _center(text, u, v_bottom, px):
        f = _font(px)
        box = draw.textbbox((0, 0), text, font=f)
        cx = u * strip_w - (box[2] - box[0]) / 2.0 - box[0]
        cy = (1.0 - v_bottom) * strip_h - (box[3] - box[1]) / 2.0 - box[1]
        draw.text((cx, cy), text, fill=255, font=f)

    if title:
        _center(title, 0.5, 0.885, int(strip_h * title_scale))
    for entry in labels:
        u, v, text = entry[0], entry[1], entry[2]
        scale = entry[3] if len(entry) > 3 else 1.0
        _center(text, u, v, max(8, int(strip_h * label_scale * scale)))
    # Optional horizontal rules (v, half_width_frac, thickness_frac):
    # the mid-century builder's-plate divider under a letterspaced brand
    # line (catapult seesaw plate, 2026-08-13).
    for entry in rules:
        rv, half_w, th = entry[0], entry[1], entry[2]
        cy = (1.0 - rv) * strip_h
        draw.rectangle(
            [strip_w * (0.5 - half_w), cy - strip_h * th / 2.0,
             strip_w * (0.5 + half_w), cy + strip_h * th / 2.0],
            fill=230,
        )
    if frame:
        inset = int(strip_h * 0.035)
        draw.rectangle(
            [inset, inset, strip_w - inset, strip_h - inset],
            outline=140, width=max(2, size // 512),
        )
    img = strip.resize((size, size), Image.LANCZOS)
    mask = np.asarray(img, dtype=float) / 255.0
    brush = _fbm(size, rng, base_cells=2, octaves=4)
    brush = np.tile(brush.mean(axis=0, keepdims=True), (size, 1))
    color = np.empty((size, size, 3))
    for channel in range(3):
        field = base[channel] * (0.88 + brush * 0.24)
        color[..., channel] = field * (1 - mask) + ink[channel] * mask
    height = mask * -0.10  # engraved, not embossed
    roughness = 0.38 - mask * 0.1 + (brush - 0.5) * 0.06
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def energy_label(size, rng, cost=480000, lo=210000, hi=740000,
                 kwh=3100000, capacity="19,600 cu ft", aspect=0.74):
    """Stylized US-style EnergyGuide appliance sticker (2026-08-13, player:
    "look at American standards... put it on the back"): the familiar
    bright-yellow card - black header band, estimated yearly energy cost
    as the hero figure, a cost-range scale of similar models with a
    pointer, and the kWh figure below. Fictional brand and fictional
    small print only - this is a prop cue, not a reproduction of the
    regulated label artwork.

    ``aspect`` is width/height of the plate face (<1 = portrait). Drawn at
    true aspect then resized square; plate-face UVs stretch it back."""

    from PIL import ImageDraw, ImageFont

    strip_w = size
    strip_h = int(size / aspect)
    yellow = (250, 205, 20)
    ink = (16, 16, 18)
    img = Image.new("RGB", (strip_w, strip_h), yellow)
    draw = ImageDraw.Draw(img)
    font_path = None
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf",
                      r"C:\Windows\Fonts\arial.ttf"):
        try:
            ImageFont.truetype(candidate, 20)
            font_path = candidate
            break
        except OSError:
            continue

    def _font(px):
        if font_path:
            return ImageFont.truetype(font_path, max(8, int(px)))
        return ImageFont.load_default()

    def _text(text, cx, cy, px, fill, anchor="mm"):
        draw.text((cx, cy), text, fill=fill, font=_font(px), anchor=anchor)

    edge = max(2, size // 256)
    draw.rectangle([0, 0, strip_w - 1, strip_h - 1], outline=ink,
                   width=edge)
    # Black header band with the yellow wordmark, the label's signature.
    band_h = int(strip_h * 0.085)
    draw.rectangle([0, 0, strip_w, band_h], fill=ink)
    _text("EnergyGuide", strip_w * 0.5, band_h * 0.52, band_h * 0.52, yellow)
    # Appliance / maker block under the band, split left-right. Numbers
    # are the REAL giant-drum figures (player 2026-08-13): r 4.2 m x 10 m
    # drum = 554 m3 = 19,600 cu ft; 5.2 m fill = ~360 m3 = 95,000 gal.
    _text("Vehicle Washer", strip_w * 0.06, strip_h * 0.125,
          strip_h * 0.024, ink, anchor="lm")
    _text(f"Capacity: {capacity}", strip_w * 0.06, strip_h * 0.158,
          strip_h * 0.019, (60, 58, 50), anchor="lm")
    _text("MAXSPIN", strip_w * 0.94, strip_h * 0.125,
          strip_h * 0.024, ink, anchor="rm")
    _text("Model WM-9000", strip_w * 0.94, strip_h * 0.158,
          strip_h * 0.019, (60, 58, 50), anchor="rm")
    draw.line([int(strip_w * 0.05), int(strip_h * 0.185),
               int(strip_w * 0.95), int(strip_h * 0.185)], fill=ink,
              width=edge)
    # Hero figure: estimated yearly energy cost.
    _text("Estimated Yearly Energy Cost", strip_w * 0.5, strip_h * 0.235,
          strip_h * 0.026, ink)
    _text(f"${cost:,}", strip_w * 0.5, strip_h * 0.345, strip_h * 0.085,
          ink)
    # Cost range scale of similar models with a drop pointer.
    scale_y = int(strip_h * 0.50)
    sx0, sx1 = int(strip_w * 0.12), int(strip_w * 0.88)
    draw.line([sx0, scale_y, sx1, scale_y], fill=ink, width=edge * 2)
    for tick_x in (sx0, sx1):
        draw.line([tick_x, scale_y - int(strip_h * 0.014),
                   tick_x, scale_y + int(strip_h * 0.014)], fill=ink,
                  width=edge * 2)
    frac = max(0.0, min(1.0, (cost - lo) / max(1, hi - lo)))
    px = int(sx0 + (sx1 - sx0) * frac)
    tri = int(strip_h * 0.026)
    draw.polygon([(px - tri, scale_y - tri * 2), (px + tri, scale_y - tri * 2),
                  (px, scale_y - edge)], fill=ink)
    _text(f"${lo:,}", sx0, scale_y + strip_h * 0.032, strip_h * 0.022, ink)
    _text(f"${hi:,}", sx1, scale_y + strip_h * 0.032, strip_h * 0.022, ink)
    _text("Cost Range of Similar Models", strip_w * 0.5,
          scale_y + strip_h * 0.062, strip_h * 0.02, ink)
    draw.line([int(strip_w * 0.05), int(strip_h * 0.60),
               int(strip_w * 0.95), int(strip_h * 0.60)], fill=ink,
              width=edge)
    # kWh block.
    _text(f"{kwh:,}", strip_w * 0.5, strip_h * 0.665, strip_h * 0.05, ink)
    _text("kWh  Estimated Yearly Electricity Use", strip_w * 0.5,
          strip_h * 0.725, strip_h * 0.021, ink)
    draw.line([int(strip_w * 0.05), int(strip_h * 0.765),
               int(strip_w * 0.95), int(strip_h * 0.765)], fill=ink,
              width=edge)
    # Fictional small print.
    for line_index, line in enumerate((
            "Estimate: 295 loads/yr, 95,000 gallons and 10,500 kWh per",
            "40 C load (heating 360 m3 of water is like that), $0.15/kWh.",
            "Water bill sold separately. 1600 rpm MAX SPIN certified.",
    )):
        _text(line, strip_w * 0.5, strip_h * (0.80 + 0.033 * line_index),
              strip_h * 0.0185, (60, 58, 50))
    draw.rectangle([int(strip_w * 0.0), int(strip_h * 0.905),
                    strip_w, strip_h], fill=ink)
    _text("laundry day is the best day", strip_w * 0.5, strip_h * 0.952,
          strip_h * 0.024, yellow)
    img = img.resize((size, size), Image.LANCZOS)
    color = np.asarray(img, dtype=float) / 255.0
    height = np.zeros((size, size))
    roughness = np.full((size, size), 0.38)
    return color.clip(0, 1), height, roughness, None


def _stamp(
    target: np.ndarray,
    cy: int,
    cx: int,
    radius: float,
    value: float,
    *,
    aspect: float = 1.0,
    angle: float = 0.0,
    falloff: float = 1.0,
) -> None:
    """Accumulate one soft elliptical blob into a tiling field, locally.

    The eggshell family stamps speckles by building a full size x size
    distance field PER SPECK, which is fine for 420 dots at 512 but is
    minutes of numpy at 2048. Everything here is drawn into the (2r+1)
    neighbourhood only and wrapped with modulo indexing, so the map stays
    seamlessly tileable and the cost follows the ink, not the canvas.
    """

    reach = math.ceil(radius * max(1.0, aspect)) + 1
    ys = np.arange(cy - reach, cy + reach + 1) % target.shape[0]
    xs = np.arange(cx - reach, cx + reach + 1) % target.shape[1]
    dy = np.arange(-reach, reach + 1)[:, None].astype(float)
    dx = np.arange(-reach, reach + 1)[None, :].astype(float)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    u = (dx * cos_a + dy * sin_a) / max(radius * aspect, 1e-6)
    v = (-dx * sin_a + dy * cos_a) / max(radius, 1e-6)
    mask = np.clip(1.0 - np.sqrt(u * u + v * v), 0.0, 1.0)
    mask = mask * mask * (3.0 - 2.0 * mask)
    if falloff != 1.0:
        mask = mask**falloff
    block = np.ix_(ys, xs)
    target[block] = np.maximum(target[block], mask * value)


def potato_skin(
    size,
    rng,
    base=(0.545, 0.372, 0.208),
    pale=(0.714, 0.561, 0.355),
    flesh=(0.839, 0.769, 0.573),
    eye=(0.157, 0.102, 0.055),
    soil=(0.271, 0.208, 0.145),
    eyes=17,
    net=1.0,
    net_scale=1.0,
    soil_amount=0.5,
    scuff=0.5,
):
    """Russet potato periderm: corky netting, lenticels, eyes, field soil.

    Built from what actually makes a russet look like a russet, in the order
    the tuber grows it:

    1. TONAL DRIFT. A potato is never one brown. Broad low-frequency banding
       runs from a pale stem end to a darker bud end.
    2. THE NET. Russeting is healed periderm - suberised ridges that close on
       themselves, branch, and never run parallel. That is precisely the
       shape of a LEVEL SET, so the net is the neighbourhood of ``field ==
       0.5`` for band-limited noise at three scales, not a drawn lattice.
       Drawing it as a lattice (the mesh_weave approach) is what makes
       procedural organics read as printed-on fabric.
    3. LENTICELS. The breathing pores: hundreds of sub-millimetre dark
       specks, denser in the net's valleys than on its ridges, because that
       is where the periderm stayed thin.
    4. EYES. Axillary buds in a shallow depression under a raised brow
       ridge, distributed on a loose spiral toward the bud end. The brow is
       a crescent (a disc differenced against an offset disc), which is what
       separates a real eye from a drilled hole.
    5. SOIL AND SCUFF. Field dirt settles in the net valleys; handling rubs
       the periderm off the high points and shows pale flesh under it.

    Height carries all of it so the normal map does the close-range work the
    2048 colour map cannot: ridges up, eyes down, lenticels pricked in.
    """

    drift = _fbm(size, rng, base_cells=3, octaves=4, persistence=0.62)
    # Stem-to-bud gradient, wrapped so the tile still repeats: one full
    # cosine over v rather than a linear ramp with a seam.
    rows = np.arange(size, dtype=float)[:, None]
    axial = np.tile(0.5 - 0.5 * np.cos(2.0 * np.pi * rows / size), (1, size))

    # Cell size is the whole game here. A russet's net cells run roughly
    # 3-6 mm; at 2048 px over a ~1.8 m tuber that is 20-45 px, so the level
    # sets have to be band-limited THERE. The first pass used 9/17/31 cells
    # (57 px cells at 512) and read as pale cloud rather than corky ridge.
    #
    # ``net_scale`` multiplies the cell counts. It exists because the tile is
    # what the swatch looks like, but the OBJECT is what the player sees: on a
    # ~2 m tuber with a single lat-long wrap, net_scale 1.0 puts the cells at
    # roughly 28 cm each and the skin reads as marble veining rather than
    # periderm. Scale it to whatever makes the cells land near 1/25 of the
    # tuber's length, the proportion a real russet has.
    netting = np.zeros((size, size))
    for cells, width, weight in ((21, 0.030, 1.0), (39, 0.021, 0.80), (67, 0.014, 0.55)):
        cells = max(2, round(cells * net_scale))
        field = _fbm(size, rng, base_cells=cells, octaves=2, persistence=0.5)
        netting = np.maximum(
            netting, weight * np.exp(-((field - 0.5) ** 2) / (2.0 * width * width))
        )
    # Sharpen: suberised ridge shoulders are crisp, not gaussian.
    netting = np.clip(netting, 0.0, 1.0) ** 0.72
    # Russeting is not uniform over a tuber - it crowds where the periderm
    # worked hardest and thins to nearly smooth skin elsewhere. Without this
    # the tile is busy edge to edge and reads as a fabric swatch.
    density = _fbm(size, rng, base_cells=3, octaves=3, persistence=0.6)
    netting *= (0.34 + 1.05 * density).clip(0.0, 1.0)
    netting = (netting * net).clip(0.0, 1.0)
    valleys = 1.0 - netting

    lenticels = np.zeros((size, size))
    pore_count = int(size * size / 2200)
    py = rng.integers(0, size, pore_count)
    px = rng.integers(0, size, pore_count)
    pr = rng.uniform(size / 1400.0, size / 480.0, pore_count)
    pa = rng.uniform(0.0, math.pi, pore_count)
    for y, x, radius, angle in zip(py, px, pr, pa, strict=True):
        # Thin periderm (net valleys) keeps its pores; ridges healed over.
        if valleys[y, x] < 0.35:
            continue
        _stamp(
            lenticels,
            int(y),
            int(x),
            float(radius),
            1.0,
            aspect=float(rng.uniform(1.0, 1.9)),
            angle=float(angle),
        )

    bowls = np.zeros((size, size))
    cores = np.zeros((size, size))
    brows = np.zeros((size, size))
    eye_radius = size / 34.0
    for index in range(int(eyes)):
        # Loose phyllotactic spiral: eyes crowd the bud end, never grid.
        t = (index + 0.5) / max(int(eyes), 1)
        cx = int((0.5 + 0.5 * math.cos(index * 2.399963) + rng.uniform(-0.06, 0.06)) % 1.0 * size)
        cy = int((t * 0.92 + 0.04 + rng.uniform(-0.035, 0.035)) % 1.0 * size)
        radius = float(eye_radius * rng.uniform(0.62, 1.25))
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        _stamp(bowls, cy, cx, radius, 1.0, aspect=1.15, angle=angle)
        _stamp(cores, cy, cx, radius * 0.30, 1.0, aspect=1.25, angle=angle)
        # Brow ridge: a disc minus an offset disc leaves the crescent.
        brow = np.zeros((size, size))
        offset = radius * 0.52
        _stamp(brow, cy, cx, radius * 1.22, 1.0, aspect=1.15, angle=angle)
        cut = np.zeros((size, size))
        _stamp(
            cut,
            int(cy + offset * math.cos(angle)),
            int(cx - offset * math.sin(angle)),
            radius * 1.12,
            1.0,
            aspect=1.3,
            angle=angle,
        )
        brows = np.maximum(brows, np.clip(brow - cut * 1.15, 0.0, 1.0))

    dirt = _fbm(size, rng, base_cells=5, octaves=4, persistence=0.6)
    dirt = np.clip((dirt - 0.42) * 2.4, 0.0, 1.0) * (0.35 + 0.65 * valleys) * soil_amount
    rubbed = _fbm(size, rng, base_cells=7, octaves=3, persistence=0.5)
    rubbed = np.clip((rubbed - 0.68) * 4.0, 0.0, 1.0) * netting * scuff
    grain = _value_noise(size, size // 3, rng)

    tone = (0.34 + 0.42 * drift + 0.24 * axial).clip(0.0, 1.0)
    base_rgb = np.array(base, dtype=float)
    pale_rgb = np.array(pale, dtype=float)
    color = base_rgb + (pale_rgb - base_rgb) * tone[..., None]
    # Suberised ridges sit paler and greyer than the skin between them, and
    # the valleys between them sit darker - both halves of the contrast, or
    # the net washes out into the base tone.
    ridge_rgb = pale_rgb * 0.96 + np.array([0.045, 0.040, 0.032])
    color = color * (1.0 - 0.46 * netting[..., None]) + ridge_rgb * 0.46 * netting[..., None]
    color *= (1.0 - 0.16 * (valleys**2))[..., None]
    color *= (0.94 + 0.12 * grain)[..., None]
    color = color * (1.0 - dirt[..., None]) + np.array(soil) * dirt[..., None]
    color = color * (1.0 - rubbed[..., None]) + np.array(flesh) * rubbed[..., None]
    # Eyes: a soft bowl shadow with a small dark bud, not a punched hole.
    eye_mask = np.clip(bowls * 0.34 + cores * 0.86, 0.0, 1.0)
    color = color * (1.0 - eye_mask[..., None]) + np.array(eye) * eye_mask[..., None]
    color = (
        color * (1.0 - 0.55 * lenticels[..., None]) + np.array(eye) * 0.55 * lenticels[..., None]
    )
    # The brow ridge catches light; that highlight is what reads as "eye"
    # rather than "stain" at any distance where the bud itself is a pixel.
    color *= (1.0 + 0.22 * brows)[..., None]

    height = (
        netting * 0.30
        + (drift - 0.5) * 0.16
        + brows * 0.26
        - bowls * 0.52
        - cores * 0.30
        - lenticels * 0.22
        + (grain - 0.5) * 0.05
    )

    # Matte throughout - a potato has no sheen anywhere. The washed-off
    # scuffs are the only slightly smoother patches, and wet-looking dirt
    # the only slightly darker-rougher ones.
    roughness = 0.86 + netting * 0.05 + dirt * 0.04 - rubbed * 0.14 + (grain - 0.5) * 0.05

    return color.clip(0, 1), height, roughness.clip(0, 1), None


def foam_latex(
    size,
    rng,
    base=(0.760, 0.635, 0.470),
    deep=(0.545, 0.405, 0.285),
    mottle=0.42,
    pores=0.55,
    seam=0.32,
    dust=0.30,
    rough=0.78,
    crazing=0.62,
    # Fold scale in METRES of prop, with the tile pitch it is measured
    # against. Both are here rather than derived from `size` because a
    # texel-referenced cell count silently rescales every time the tile
    # moves: when SKIN_METERS_PER_TILE went 2.60 -> 0.65 to square the
    # hand's texels, the folds went 200 mm -> 39 mm and the crazing turned
    # from a wrinkle network into an all-over stucco pebble.
    fold_m=0.10,
    tile_m=0.66,
):
    """Cast foam-latex prop skin - the Jackass 3D giant hand, not a hand.

    The reference is the PROP, not anatomy. A foam-latex appliance is
    whipped, poured into a two-part mould, gelled, baked and pulled, then
    painted with thinned rubber cement. What you see standing next to one
    is four things and no others: a warm sandy tan blotched at the
    half-metre scale where the pigment never fully dispersed in the pour, a
    dense open-cell pore stipple wherever the skin coat went on thin, one
    pale flash line down the mould split, and shop dust in every low spot.
    It is dead matte end to end.

    It is emphatically NOT skin - no pink, no subsurface glow, no dermal
    ridges, no follicle rows - and reaching for "skin" is the failure mode
    here. A glossy pink 8.6 m hand reads as a mannequin; the joke only
    lands if the thing reads as a prop that somebody built.

    Why these four layers and no more: the pores carry every viewing
    distance inside about 3 m, the mottle carries everything past that, the
    seam is the single feature that says CAST rather than "tiled texture",
    and the dust is what stops the other three from looking factory-new. A
    fifth layer would only fight one of them.

    PORE SIZE ARITHMETIC, which is the whole family, and it is worth
    checking rather than believing: this paragraph has been wrong twice,
    both times because the tile pitch moved underneath it.

    high_five maps this tile at the REALISED pitch — `reference / u_tiles`
    per part, which is what the mesh actually gets, NOT the nominal
    SKIN_METERS_PER_TILE it is derived from. That runs 0.637 m on the ring
    finger to 0.679 m on the middle, mean 0.66 m. So at size=2048 one texel
    is 660/2048 = 0.32 mm of prop. The pore field is thresholded
    band-limited noise at a 3.2 px cell pitch with a second pass at 4.6 px,
    plus stamped blowholes 3.7-7.3 px across: call it 3-8 px, i.e.
    1.0-2.4 mm on the prop. That is deliberately LARGER than a scaled-down real cell. The
    honest factor from a 0.19 m hand to an 8.6 m one is 45x, which would put
    a 0.4 mm cell at 0.7 texels and turn the signature of the material into
    aliasing. So the cells are held at the size they appear when you put
    your eye against the real prop. Nobody measures it; everybody sees
    whether a surface has cells or has grain.
    """

    base_rgb = np.asarray(base, dtype=float)
    deep_rgb = np.asarray(deep, dtype=float)

    # 1. PIGMENT DRIFT, two scales. The slow one is the pour itself - latex
    # thickens as a batch sits, so the last of it lays down darker - and the
    # faster one is the brushed colour coat, which never goes on even.
    broad = _fbm(size, rng, base_cells=2, octaves=4, persistence=0.62)
    blotch = _fbm(size, rng, base_cells=5, octaves=4, persistence=0.55)
    pigment = np.clip(0.5 + (broad - 0.5) * 1.30 + (blotch - 0.5) * 0.78, 0.0, 1.0)

    # 2. PORES. Thresholded band-limited noise, NOT a per-texel grain: a
    # uniform grain reads as sandpaper at every distance, whereas open-cell
    # foam is discrete cells with skin between them. Two cell pitches so the
    # sizes vary, and a low-frequency DENSITY field on top - a real cast is
    # cell-rich where the skin coat pulled thin and nearly smooth elsewhere,
    # and without that the tile is busy edge to edge and reads as a swatch.
    density = _fbm(size, rng, base_cells=4, octaves=3, persistence=0.58)
    density = np.clip(0.45 + density * 0.95, 0.0, 1.0)

    fine = _value_noise(size, max(8, round(size / 3.2)), rng)
    coarse = _value_noise(size, max(6, round(size / 4.6)), rng)
    fine_cut = float(np.quantile(fine, 1.0 - 0.36 * pores))
    coarse_cut = float(np.quantile(coarse, 1.0 - 0.15 * pores))
    pore = np.maximum(
        np.clip((fine - fine_cut) / 0.10, 0.0, 1.0) ** 0.80,
        np.clip((coarse - coarse_cut) / 0.13, 0.0, 1.0) ** 0.80 * 0.95,
    )
    pore = np.clip(pore * density, 0.0, 1.0)

    # Blowholes: the handful of larger, oriented, elongated cells that a
    # thresholded isotropic field can never produce. They are what stops the
    # stipple from reading as a screen pattern at close range.
    blow = np.zeros((size, size))
    blow_count = int(size * size * pores / 2400.0)
    if blow_count > 0:
        by = rng.integers(0, size, blow_count)
        bx = rng.integers(0, size, blow_count)
        br = rng.uniform(size / 1100.0, size / 560.0, blow_count)
        ba = rng.uniform(0.0, math.pi, blow_count)
        bs = rng.uniform(1.0, 2.1, blow_count)
        for y, x, radius, angle, stretch in zip(by, bx, br, ba, bs, strict=True):
            if density[y, x] < 0.82:      # crowd them where the fine pores are
                continue
            _stamp(blow, int(y), int(x), float(radius), 1.0,
                   aspect=float(stretch), angle=float(angle), falloff=0.85)

    # 2b. CRAZING. The single most recognisable thing about the reference
    # prop is not its pores, it is the field of long soft wrinkle folds over
    # the whole casting — a skin coat that shrank onto foam and crinkled.
    # The pore stipple is a millimetre feature and disappears past a few
    # metres; the crazing is a 5-15 cm feature and is what carries the read
    # at every distance a driver actually sees this from.
    #
    # It is a LEVEL SET, not more noise: the ridge follows where an fbm
    # crosses its own midpoint, which gives long connected branching folds
    # instead of isotropic blobs. Same construction potato_skin's netting
    # and molded_nylon's crease already use here.
    # CELL COUNT IN METRES, not texels. `size / 120.0` is map-referenced,
    # so when SKIN_METERS_PER_TILE went 2.60 -> 0.65 to square the texels
    # the fold scale silently came with it: 200 mm cells became 39 mm, and
    # with the widened level set on top the coverage went 6% to 56% — an
    # all-over stucco pebble rather than the 5-15 cm folds this family
    # exists to draw. Pinned to the prop, the term is now size-independent,
    # which is what "pinned to the extent" should have meant the first time
    # that phrase was used in this file.
    web = _fbm(size, rng, base_cells=max(4, round(tile_m / fold_m)), octaves=4,
               persistence=0.55)
    # WIDE level sets. At /0.030 the ridge runs measured a median THREE
    # texels — 4-7 mm on the prop — against a docstring promising a 5-15 cm
    # feature, so it read as crackle glaze or lichen rather than as the
    # reference's broad soft wrinkles. The cell SPACING was always right;
    # the ridge width was 20-30x too narrow.
    craze = np.clip(1.0 - np.abs(web - 0.5) / 0.200, 0.0, 1.0) ** 1.0
    # A second, finer network so the folds branch rather than reading as one
    # regular mesh.
    web2 = _fbm(size, rng, base_cells=max(6, round(tile_m / (fold_m * 0.5))), octaves=3,
                persistence=0.50)
    craze = np.clip(
        craze + np.clip(1.0 - np.abs(web2 - 0.5) / 0.100, 0.0, 1.0) ** 1.2 * 0.55,
        0.0,
        1.0,
    ) * crazing

    # 3. THE MOULD SEAM. One flash line at a fixed u so the tile still
    # repeats. It has to be FAINT and BROKEN, and that is not timidity: one
    # seam per tile is one seam every 0.66 m on the prop (and high_five sets
    # seam = 0.0 outright, because its parting line is geometry), and a strong one
    # would read as pinstripes. So it wanders (a periodic column of noise
    # displaces it along v), it is dressed back to nothing over stretches,
    # and at the default seam=0.32 it reads as "there is a seam over there"
    # rather than as a ruled line. Flash rubber squeezed into the mould
    # split cures paler and slightly proud, so it is both lighter and up.
    u_row = ((np.arange(size, dtype=float) + 0.5) / size)[None, :]
    wander = _fbm(size, rng, base_cells=3, octaves=3)[:, :1]
    dressed = _fbm(size, rng, base_cells=2, octaves=3)[:, :1]
    du = ((u_row - 0.29 - (wander - 0.5) * 0.011) + 0.5) % 1.0 - 0.5
    core = np.clip(1.0 - np.abs(du) / 0.0019, 0.0, 1.0)
    core = core * core * (3.0 - 2.0 * core)
    flank = np.clip(1.0 - np.abs(du) / 0.013, 0.0, 1.0) ** 2.0
    live = np.clip((dressed - 0.26) * 2.4, 0.0, 1.0)
    ridge = core * live * seam
    halo = flank * live * seam

    # 4. DUST AND HANDLING. Dust settles in the RECESSES — the pores, the
    # blowholes and the crazing — and nowhere else. Keying it to the low
    # ground of the PIGMENT field instead, which is what this did, put pale
    # near-neutral wash over roughly half the tile in patches unrelated to
    # any surface feature, and it read as mildew.
    relief = np.clip(pore * 0.70 + blow * 0.85 + craze * 0.95, 0.0, 1.0)
    powder = _fbm(size, rng, base_cells=7, octaves=4, persistence=0.55)
    dust_mask = np.clip(relief * (0.30 + powder * 1.10), 0.0, 1.0) * dust

    smudge = np.zeros((size, size))
    for _ in range(6):
        _stamp(
            smudge,
            int(rng.integers(0, size)),
            int(rng.integers(0, size)),
            float(size * rng.uniform(0.055, 0.130)),
            1.0,
            aspect=float(rng.uniform(1.5, 3.2)),
            angle=float(rng.uniform(0.0, math.pi)),
            falloff=2.4,
        )
    smudge = np.clip(smudge * (0.35 + blotch * 0.85), 0.0, 1.0) * dust

    micro = _value_noise(size, max(8, size // 2), rng)
    burnish = np.clip((broad - 0.66) * 3.0, 0.0, 1.0)

    # ONE lerp toward `deep` carries both halves of the brief: `deep` is the
    # colour that settles into recesses, and mottle and cavity are both
    # recesses - one at the half-metre scale, one at the millimetre scale.
    # Splitting them into two separate tints is what makes procedural
    # organics look like two textures multiplied together.
    cavity = np.clip(pore * 0.92 + blow * 0.80 + craze * 0.55, 0.0, 1.0)
    tint = np.clip(
        0.14
        + (pigment - 0.5) * 1.25 * mottle
        + cavity * 0.50
        + (0.5 - micro) * 0.09,
        0.0,
        1.0,
    )
    color = (base_rgb[None, None, :]
             + (deep_rgb - base_rgb)[None, None, :] * tint[..., None])
    # And a straight multiplicative darkening on top of the lerp. `deep` is a
    # fairly light brown, so in the already-pale regions the lerp alone leaves
    # the pores nearly invisible - which is where the first pass lost them.
    color *= (1.0 - 0.14 * cavity)[..., None]
    # AND the crazing gets its own multiply, because a derivative operator
    # cannot see it. _height_to_normal measures slope: a fold 120 texels
    # wide at depth 0.052 is 0.00087/texel while a pore 1.5 texels wide at
    # 0.110 is 0.073/texel — 84x steeper. Measured, the whole crazing layer
    # moved the normal map by 1.6 code values, i.e. deleting the feature
    # entirely would not have shown in a blink test. Amplitude in COLOUR is
    # read directly, and on the reference prop the wrinkles read as VALUE
    # rather than as shading anyway.
    color *= (1.0 - 0.35 * craze)[..., None]

    # MULTIPLICATIVE on the base, not base*k + c. Any additive constant is
    # calibrated for one base brightness, and this family's base has since
    # moved from a pale cream to a dark linear ochre — at which point
    # base*0.62 + 0.145 is no longer dust, it is a wash of something two
    # stops lighter and half as saturated.
    dust_rgb = np.clip(base_rgb * 1.22 + 0.015, 0.0, 1.0)
    dm = dust_mask[..., None]
    color = color * (1.0 - dm) + dust_rgb[None, None, :] * dm
    color *= (1.0 - 0.17 * smudge)[..., None]

    # Same correction as dust_rgb: base*0.70 + 0.30 on the current base is
    # 2x lighter and desaturated from 0.855 to 0.30, so the mould seam went
    # from invisible to a bright near-grey stripe.
    flash_rgb = np.clip(base_rgb * 1.55 + 0.02, 0.0, 1.0)
    sm = np.clip(ridge * 0.55 + halo * 0.12, 0.0, 1.0)[..., None]
    color = color * (1.0 - sm) + flash_rgb[None, None, :] * sm
    color *= (0.965 + micro * 0.07)[..., None]

    height = (
        (broad - 0.5) * 0.038
        + (blotch - 0.5) * 0.018
        + (micro - 0.5) * 0.010
        # Deepened. Measured on the shipped 2048 map the whole normal field
        # carried a std of 2.6 code values and fell below quantisation by
        # mip 3, so the pores existed in colour and nowhere else and read as
        # printed grain at every distance.
        - pore * 0.110
        - blow * 0.085
        - craze * 0.052
        + ridge * 0.075
        + halo * 0.007
        + dust_mask * 0.004
    )

    # A FLAT roughness is what makes CG props look like injection-moulded
    # plastic, and this is the surface the player will stand under. Dust is
    # the roughest thing here, burnished high spots and handling smudges the
    # smoothest, and the seam's flash rubber smoother still because it never
    # took the mould's texture.
    roughness = (
        rough
        + dust_mask * 0.15
        + pore * 0.05
        + craze * 0.16
        + (blotch - 0.5) * 0.07
        + (micro - 0.5) * 0.04
        - smudge * 0.17
        - burnish * 0.09
        - ridge * 0.34
    )
    return color.clip(0, 1), height, roughness.clip(0.06, 1.0), None


def nail_keratin(
    size,
    rng,
    base=(0.845, 0.735, 0.665),
    lunula=(0.925, 0.870, 0.830),
    striate=0.35,
    rough=0.24,
    bed=(0.66, 0.50, 0.30),
):
    """Painted fingernail on a cast prop hand: the only gloss on the prop.

    The reference is a prop nail, which is a nail-plate SHAPE sprayed with
    tinted lacquer, so it borrows a real nail's structure - longitudinal
    striae, a lunula, a paler free edge, a warm blush where the bed shows
    through the plate - and then wears all of it under a thin clear coat
    instead of growing it. That is why it is nearly the only surface in the
    pack with a low roughness: on an 8.6 m foam hand the single specular
    highlight on the nails is what tells you the rest of it is matte on
    purpose rather than matte because nobody lit it.

    NOT isotropic, and barely a tile. The nail-plate UVs run v = proximal
    (cuticle) -> distal (free edge) with u across the plate, so this is a
    one-shot gradient family. It still WRAPS, because everything in this kit
    does and because the seam check is the only cheap way to notice a family
    that quietly stopped tiling:

    - u wraps because every u-dependent term is either an INTEGER-frequency
      sine (the striae) or a function of min(u, 1-u) (the lateral nail
      groove). Both are exactly periodic, not approximately.
    - v wraps because the profile's two ends are made to MEET rather than
      left to chance: the free-edge pale band is faded out before v = 1, the
      lunula is faded in after v = 0, and the last few percent at both ends
      carry the same soft shade term. That last part is not a fudge to pass
      a test - it is the cuticle shadow at one end and the shadow under the
      free edge at the other, and those really are the two darkest rows of a
      real nail.

    Height is deliberately about a quarter of foam_latex's. A nail is
    smooth, and a normal map that fights the gloss is exactly what makes CG
    nails read as moulded plastic shells.
    """

    base_rgb = np.asarray(base, dtype=float)
    lun_rgb = np.asarray(lunula, dtype=float)

    rows = (np.arange(size, dtype=float) + 0.5) / size
    u = ((np.arange(size, dtype=float) + 0.5) / size)[None, :]
    v = (1.0 - rows)[:, None]                   # v samples from the image bottom
    seam_v = np.minimum(v, 1.0 - v)             # wrapped distance to the v seam
    # The lateral nail groove, where the plate disappears under the fold.
    # Being a function of min(u, 1-u) it is its own mirror, so the u seam is
    # exact by construction rather than by luck.
    # 0.09, not 0.035. At 0.035 the plate ended on a hard line 2% of the
    # way in from each edge, so five near-white rectangles sat on the
    # fingertips like sticking plasters. A nail's lateral edge does not end,
    # it goes under a fold — so the band is wide enough to see and the
    # colour is lerped toward the FOAM inside it.
    fold = np.clip(1.0 - np.minimum(u, 1.0 - u) / 0.090, 0.0, 1.0) ** 2.0

    # STRIAE. Irregular spacing is the point, so this is neither one sine nor
    # a _stripes field: it is a short sum of sines at randomly chosen INTEGER
    # cycle counts, which is quasi-periodic to the eye and exactly periodic
    # to the tile. Low frequencies get more amplitude because the coarse
    # ridges are the ones you actually see on a nail; the fine ones only
    # break up the specular. A slow lateral wander keeps them off the ruler.
    wander = (_fbm(size, rng, base_cells=3, octaves=3) - 0.5) * 0.013
    phase_u = u + wander
    striae = np.zeros((size, size))
    weight = 0.0
    for k in np.sort(rng.choice(np.arange(22, 152), size=11, replace=False)):
        amp = 1.0 / (1.0 + float(k) / 42.0)
        striae += amp * np.sin(2.0 * np.pi * (float(k) * phase_u + rng.random()))
        weight += amp
    striae /= max(weight, 1e-9)

    # Transverse growth ripple (also integer harmonics, also exactly
    # periodic) and the plate's transverse arch, which is the one bit of
    # FORM this map carries - the geometry under it is a flat-ish nail plate.
    ripple = np.zeros((size, 1))
    for cycles, amp in ((3, 0.55), (5, 0.30), (9, 0.16)):
        ripple = ripple + amp * np.sin(2.0 * np.pi * (cycles * v + rng.random()))
    ripple /= 1.01
    arch = 0.5 - 0.5 * np.cos(2.0 * np.pi * u)

    # LUNULA. A disc centred BELOW the plate, so its visible edge is a
    # convex arc pointing distally - which is the half-moon's whole shape.
    # Clipped by a proximal fade so the arc floats free of the v seam
    # instead of being cut in half by it.
    lr = np.sqrt((u - 0.5) ** 2 + (v + 0.12) ** 2)
    lun = np.clip((0.30 - lr) / 0.085, 0.0, 1.0)
    lun = lun * lun * (3.0 - 2.0 * lun)
    fade = np.clip(v / 0.055, 0.0, 1.0)
    lun = lun * fade * fade * (3.0 - 2.0 * fade)

    # Free edge: the opaque pale band where the plate has left the bed. Ends
    # before v = 1 (see the wrap note above).
    # A CAST PROP NAIL HAS NO GROWN-OUT FREE EDGE. The band was 22% of the
    # plate at weight 0.80, which painted the near-white lunula colour over
    # the whole distal fifth and is most of why the nails read as white
    # caps. It is kept only as a thin brightening at the very tip.
    rise = np.clip((v - 0.88) / 0.10, 0.0, 1.0)
    tip = rise * rise * (3.0 - 2.0 * rise) * _aa_slab(v, -1.0, 0.955, 0.055)
    shade = np.clip(1.0 - seam_v / 0.055, 0.0, 1.0)
    shade = shade * shade * (3.0 - 2.0 * shade)

    # The bed showing through: warmest in the middle of the plate, gone by
    # both ends. Written as a cosine rather than a gaussian purely so it is
    # zero at the seam on both sides without a clip.
    blush = (0.5 + 0.5 * np.cos(2.0 * np.pi * (v - 0.47))) ** 1.7 * (0.35 + 0.65 * arch)

    grain = _value_noise(size, max(8, size // 2), rng)
    smear = _fbm(size, rng, base_cells=4, octaves=3)
    haze = _fbm(size, rng, base_cells=9, octaves=3)

    warm_rgb = np.clip(base_rgb * np.array([1.050, 0.995, 0.960]), 0.0, 1.0)
    color = (base_rgb[None, None, :]
             + (warm_rgb - base_rgb)[None, None, :] * (blush * 0.62)[..., None])
    pale = np.clip(lun * 0.90 + tip * 0.35, 0.0, 1.0)
    color = color * (1.0 - pale[..., None]) + lun_rgb[None, None, :] * pale[..., None]
    color *= (1.0
              + striae * 0.078 * striate
              + ripple * 0.016
              + (grain - 0.5) * 0.034)[..., None]
    # Dissolve into the bed rather than ending on a line.
    bed_rgb = np.asarray(bed, dtype=float)
    fm = (fold * 0.85)[..., None]
    color = color * (1.0 - fm) + bed_rgb[None, None, :] * fm
    color *= (1.0 - 0.11 * fold)[..., None]
    color *= (1.0 - 0.085 * shade)[..., None]

    height = (
        striae * 0.075 * striate
        + ripple * 0.008
        + arch * 0.014
        + lun * 0.004
        - fold * 0.016
        - shade * 0.008
        + (grain - 0.5) * 0.004
    )

    # Low, but never uniform. A constant low roughness gives a mirror
    # highlight that slides across the nail as the prop swings and reads as
    # chrome; the smear and the fingerprint haze break it into something
    # that stays put. The groove and the shadowed ends go matte because dust
    # collects there and the lacquer never levelled into them.
    roughness = (
        rough
        + (smear - 0.5) * 0.10
        + np.clip((haze - 0.64) * 2.6, 0.0, 1.0) * 0.15
        + shade * 0.10
        + fold * 0.09
        + np.abs(striae) * 0.030 * striate
        - pale * 0.030
    )
    return color.clip(0, 1), height, roughness.clip(0.05, 1.0), None


def slap_pad(size, rng, base=(0.16, 0.16, 0.17), paint=(0.88, 0.88, 0.86),
             warn=(0.94, 0.72, 0.06), aspect=1.0, hand_scale=0.60):
    """One-shot road patch: hazard border and an open right hand, PAINTED.

    Same law as ramp_deck and kick_pad, restated because it keeps getting
    relearned the expensive way: marking GEOMETRY on a drivable surface
    always betrays itself in-engine. Even a 4 mm plate casts a shadow and
    catches edge light, and the player reads that instantly as "a thing
    lying on the road" rather than as a marking. So the border, the keyline
    and the hand are colour and roughness only, the height map carries
    nothing but the asphalt's own aggregate, and the paint lands exactly
    where a stencil crew's would.

    ``aspect`` is width/length (u across the pad, v along it), handled the
    way ramp_deck handles it: every drawn shape is measured in the isotropic
    coordinate (u - 0.5, (v - 0.5)/aspect), so a non-square pad gets a round
    hand rather than a stretched one.

    TILING, which the kit demands of every family and which a one-shot pad
    has to earn: the hazard border is a function of the MIRRORED coordinates
    min(u, 1-u) and min(v, 1-v), so opposite sides are reflections and the
    wrap is exact rather than approximate. That is not a trick to satisfy a
    seam check - it is also why the stripes read as chevrons apexing at the
    middle of each side, instead of as a diagonal ladder that mitres well at
    one corner and badly at the other three.

    THE HAND has to read as a hand at a glance, from a car, at speed. What
    does that work is not outline fidelity; it is (a) the finger LENGTH
    ORDER - middle, ring, index, little - (b) visible gaps between the
    fingertips over bases that merge into the palm, and (c) a thumb that is
    short, fat and thrown out to the side. Five equal spokes read as a
    starfish and five equal capsules read as a comb; both are the failure
    mode here. Drawn as capsules and superellipses evaluated per texel
    rather than through PIL, so the anti-aliasing feather is a fixed number
    of TEXELS at any size instead of whatever a LANCZOS downsample of a 2x
    canvas happens to give. Right hand, palm toward the viewer, thumb on
    the -u side.
    """

    aspect = float(max(aspect, 1e-3))
    base_rgb = np.asarray(base, dtype=float)
    paint_rgb = np.asarray(paint, dtype=float)
    warn_rgb = np.asarray(warn, dtype=float)
    seal_rgb = np.clip(base_rgb * 0.55, 0.0, 1.0)

    # The road under the paint: the same four lines as ``asphalt`` (and as
    # ramp_deck and kick_pad before this). Duplicated rather than called
    # because ``aggregate`` is wanted BY NAME below - the paint has to break
    # over the proud stones, and that is most of what separates worn road
    # marking from a decal sticker.
    aggregate = _value_noise(size, size // 2, rng)
    blotch = _fbm(size, rng, base_cells=3, octaves=4)
    road = _colorize(base, 0.35 + aggregate * 0.4 + blotch * 0.25, 0.16)
    road_rough = 0.88 + (blotch - 0.5) * 0.08

    rows = (np.arange(size, dtype=float) + 0.5) / size
    u = ((np.arange(size, dtype=float) + 0.5) / size)[None, :]
    v = (1.0 - rows)[:, None]
    texel = 1.0 / size
    border = 0.07                       # hazard band, fraction of the u span

    def _ss(t):
        t = np.clip(t, 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    # Isotropic pad coordinates, and the inward depth from the rim measured
    # in the same units. min(edge_v)/aspect makes the band the same number of
    # METRES on all four sides for any aspect.
    px = np.broadcast_to(u - 0.5, (size, size))
    py = np.broadcast_to((v - 0.5) / aspect, (size, size))
    mirror_u = np.minimum(u, 1.0 - u)
    mirror_v = np.minimum(v, 1.0 - v) / aspect
    depth = np.minimum(mirror_u, mirror_v)

    band = 1.0 - _ss((depth - border) / (1.6 * texel) + 0.5)
    keyline = _aa_slab(depth, border + 0.014, border + 0.028, 2.2 * texel)

    # Chevrons: 45 degrees in metres, mirrored, 50% duty, anti-aliased on the
    # phase so they stay clean when the pad is seen edge-on down the road.
    pitch = 22.0
    phase = ((mirror_u + mirror_v) * pitch) % 1.0
    diag = _ss((0.5 - np.abs(phase - 0.5) * 2.0) / (4.0 * pitch * texel) + 0.5)

    # HAND LAYOUT in hand units: +y toward the fingertips, +x toward the
    # little finger, origin near the palm centre. Normalised numerically
    # below so the silhouette's bounding box is exactly `hand_scale` of the
    # inner area, whatever anyone later does to these numbers.
    fingers = (
        # base_x, base_y, length, splay_deg, root_r, tip_r
        (-0.155, 0.030, 0.365, -15.0, 0.058, 0.043),   # index
        (-0.045, 0.070, 0.420, -4.0, 0.060, 0.045),    # middle, the longest
        (0.065, 0.055, 0.385, 8.0, 0.056, 0.042),      # ring
        (0.165, 0.000, 0.300, 21.0, 0.047, 0.036),     # little, the shortest
    )
    thumb = (-0.205, -0.150, 0.265, -52.0, 0.078, 0.055)
    palm = (0.0, -0.140, 0.248, 0.268, 2.7)            # cx, cy, a, b, exponent
    thenar = (-0.175, -0.185, 0.118, 0.150, 2.4)       # the ball of the thumb

    limbs = []
    xs, ys = [], []
    for bx, by, length, deg, r0, r1 in (*fingers, thumb):
        angle = math.radians(deg)
        tx = bx + length * math.sin(angle)
        ty = by + length * math.cos(angle)
        limbs.append((bx, by, tx, ty, r0, r1))
        xs += [bx - r0, bx + r0, tx - r1, tx + r1]
        ys += [by - r0, by + r0, ty - r1, ty + r1]
    for cx, cy, a, b, _n in (palm, thenar):
        xs += [cx - a, cx + a]
        ys += [cy - b, cy + b]
    mid_x = 0.5 * (min(xs) + max(xs))
    mid_y = 0.5 * (min(ys) + max(ys))
    fit = 1.0 / max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)

    inner = max(min(0.5 - border, 0.5 / aspect - border), 0.02)
    scale = max(2.0 * inner * hand_scale * fit, 1e-5)
    lx = px / scale + mid_x
    ly = py / scale + mid_y
    feather = max(1.7 * texel / scale, 1e-6)

    def _capsule(ax, ay, bx, by, r0, r1):
        """Tapered capsule. Constant-radius capsules read as sausages; a
        finger is 35% thinner at the tip than at the knuckle."""
        pax, pay = lx - ax, ly - ay
        bax, bay = bx - ax, by - ay
        h = np.clip((pax * bax + pay * bay) / max(bax * bax + bay * bay, 1e-9),
                    0.0, 1.0)
        return np.hypot(pax - bax * h, pay - bay * h) - (r0 + (r1 - r0) * h)

    def _superellipse(cx, cy, a, b, n):
        s = (np.abs((lx - cx) / a) ** n + np.abs((ly - cy) / b) ** n) ** (1.0 / n)
        return (s - 1.0) * min(a, b)

    def _smin(a, b, k):
        """Polynomial smooth union - the interdigital webbing. A hard min
        leaves a razor notch between the fingers that no real hand has and
        that aliases badly once the pad is a few metres away."""
        h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
        return b + (a - b) * h - k * h * (1.0 - h)

    dist = _capsule(*limbs[0])
    for limb in limbs[1:4]:
        dist = _smin(dist, _capsule(*limb), 0.018)
    dist = _smin(dist, _capsule(*limbs[4]), 0.030)
    dist = _smin(dist, _superellipse(*palm), 0.055)
    dist = _smin(dist, _superellipse(*thenar), 0.070)

    hand = _ss(0.5 - dist / feather)
    # `rim` is 1 well inside the silhouette and falls to 0 at its edge, over
    # a band measured in TEXELS rather than in hand units - a band tied to
    # the hand's size renders as a soft bevel and makes the marking read as
    # an extruded 3D hand lying on the road, which is the exact failure this
    # family exists to avoid. It is applied to COVERAGE rather than to alpha
    # (below) so the thinning is broken up by the same aggregate and chip
    # noise as the rest of the paint. A smooth alpha ramp is a bevel; a
    # ragged one is a roller running out of paint.
    rim = _ss(-dist / max(9.0 * feather, 1e-9))

    # WEAR. Road paint is thin: it sits in the binder between the stones and
    # gets ground off the tops of them, it scuffs in patches, and it is
    # always thinnest at the stencil edge where the roller ran out. Coverage
    # therefore never reaches 1, and the outer rim of the hazard band takes
    # the worst of it because that is where the tyres cross.
    grime = _fbm(size, rng, base_cells=9, octaves=4)
    scuff = _value_noise(size, max(8, size // 14), rng)
    polish = _fbm(size, rng, base_cells=2, octaves=3)
    stone = np.clip((aggregate - 0.56) * 2.2, 0.0, 1.0)
    # Real fresh stencil work loses about 5% of its coverage, at the
    # edges. At threshold 0.70 knocked out at 0.95 this removed 19.6% of the
    # painted hand in ~133 mm holes: measles, not wear.
    chew = np.clip((scuff - 0.80) * 3.4, 0.0, 1.0)
    coverage = np.clip(
        # 0.30 and 0.15, not 0.95 and 0.45: at full knockout this removed
        # 19.6% of the painted hand in ~133 mm holes, which is measles
        # rather than wear. Fresh stencil work loses about 5%, at the edges.
        0.70 + grime * 0.72 + (polish - 0.5) * 0.22 - chew * 0.30 - stone * 0.15,
        0.0,
        1.0,
    )
    border_cov = np.clip(coverage * (0.62 + 0.42 * _ss(depth / max(border, 1e-6))),
                         0.0, 1.0)

    a_seal = band * (1.0 - diag) * border_cov * 0.80
    a_warn = band * diag * border_cov
    a_key = keyline * coverage
    a_hand = hand * np.clip(coverage - (1.0 - rim) * 0.50, 0.0, 1.0)

    color = road
    for rgb, alpha in ((seal_rgb, a_seal), (warn_rgb, a_warn),
                       (paint_rgb, a_key), (paint_rgb, a_hand)):
        m = np.clip(alpha, 0.0, 1.0)[..., None]
        color = color * (1.0 - m) + rgb[None, None, :] * m

    # Paint is smoother than the road it sits on, and worn-through texels get
    # the road's roughness back for free because `painted` goes to zero
    # there - no separate mask, no chance of the two drifting apart.
    painted = np.clip(a_seal + a_warn + a_key + a_hand, 0.0, 1.0)
    paint_rough = (0.44 + (blotch - 0.5) * 0.12 + stone * 0.14
                   + (1.0 - coverage) * 0.10)
    roughness = road_rough * (1.0 - painted) + paint_rough * painted
    # No paint geometry (see the docstring). The one concession is that a
    # thick film fills the voids between the stones slightly, which is a
    # height the paint REMOVES rather than adds.
    height = aggregate * 0.12 * (1.0 - 0.30 * painted)
    return color.clip(0, 1), height, roughness.clip(0.05, 1.0), None


def carbon_weave(size, rng, base=(0.052, 0.055, 0.063), tows=14.0, twill=2,
                 sheen=0.55, rough=0.15, glint=(0.30, 0.34, 0.42)):
    """2x2 twill carbon-fibre laminate under clearcoat.

    Added 2026-08-24 for the Spin Launch tether, which is the one surface
    on that machine the reference material insists on: SpinLaunch's own
    cutaway calls the arm a "high tensile strength composite", and every
    published photograph of it reads as woven prepreg, not as painted
    steel. ``steel_worn`` and ``machined_steel`` are both WRONG here in a
    way that shows at range - they carry metre-scale rolling banding and
    bright drag scuffs, and a 16 m blade skinned in either reads as a
    girder.

    The weave is authored the way the real cloth is woven rather than as
    a checkerboard: each pixel belongs to a warp tow (running along v) and
    a weft tow (along u), one of which is on top. A 2x2 twill steps that
    over/under decision by one tow per row, which is what produces the
    familiar diagonal rib - a plain (``twill=1``) weave gives the
    finer-grained square cloth instead, and both are one argument apart.

    Anisotropy is the whole look: the filaments inside a tow run ALONG
    that tow, so the striations are drawn per-direction and picked up by
    whichever tow is visible. The crown of the visible tow is what catches
    light, so the sheen term rides ``crown`` squared and the same field
    darkens at the tow boundary - that shadow line is what separates the
    weave from a noise texture at reading distance.
    """

    ramp = np.linspace(0.0, tows, size, endpoint=False)
    iu = np.tile(np.floor(ramp)[None, :], (size, 1))
    iv = np.tile(np.floor(ramp)[:, None], (1, size))
    fu = np.tile((ramp % 1.0)[None, :], (size, 1))
    fv = np.tile((ramp % 1.0)[:, None], (1, size))
    period = 2 * twill
    warp_up = (((iu - iv) % period) < twill).astype(float)

    # Tow cross-sections are rounded, so the crown is a half-sine across
    # the tow width and zero at its edges.
    crown_u = np.sin(np.pi * fu)
    crown_v = np.sin(np.pi * fv)
    # Filament striations run ALONG the tow: a warp tow runs down the
    # image, so its filaments vary across u.
    fil_warp = np.abs(_stripes(size, tows * 9.0, axis=1) - 0.5) * 2.0
    fil_weft = np.abs(_stripes(size, tows * 9.0, axis=0) - 0.5) * 2.0
    jitter = _fbm(size, rng, base_cells=6, octaves=3)

    crown = warp_up * crown_u + (1.0 - warp_up) * crown_v
    fil = warp_up * fil_warp + (1.0 - warp_up) * fil_weft
    spec = np.clip(crown, 0.0, 1.0) ** 2.2
    tone = 0.34 + spec * sheen + (fil - 0.5) * 0.18 + (jitter - 0.5) * 0.10
    color = _colorize(base, tone, 0.9)
    for channel in range(3):
        color[..., channel] += spec * glint[channel] * 0.30
    # The boundary between two tows sits in shadow under the clearcoat.
    shadow = np.clip(1.0 - crown, 0.0, 1.0) ** 2
    color *= (1.0 - shadow * 0.45)[..., None]

    height = crown * 0.09 - shadow * 0.04 + (fil - 0.5) * 0.012
    roughness = rough + (1.0 - spec) * 0.11 + shadow * 0.12 + (jitter - 0.5) * 0.04
    return color.clip(0, 1), height, roughness.clip(0, 1), None


# ---------------------------------------------------------------------------
# Tire families (2026-08-24, colossus_tire).
#
# `rubber_tread` already in this kit is a SNEAKER OUTSOLE - gum dots, worn
# centres, a 0.9 base. Skinning a 28 m earthmover radial in it reads as a
# trainer, and none of the five surfaces a real tire actually presents
# (tread rubber, sidewall rubber, inner liner, carcass laminate, bead
# chafer) look like each other. They are different compounds with different
# manufacturing marks, so they are five families here.
#
# What each one is grounded in:
#
#   tread rubber   comes out of a segmented mould, so it carries the mould's
#                  fine grain plus VENT SPEW - the whiskers of rubber forced
#                  into the mould's air vents, snipped but never flush. In
#                  service it takes stone nicks and polishes where it works.
#   sidewall       comes out of a two-piece mould, so it carries a PARTING
#                  LINE, circumferential mould ripple, and (on anything not
#                  factory-fresh) ozone CHECKING - the fine crazing network
#                  that opens on flexing rubber - plus antiozonant BLOOM, the
#                  waxy haze that migrates to the surface and settles in the
#                  recesses. Getting bloom into the recesses and not onto the
#                  crowns is most of what separates rubber from grey plastic.
#   inner liner    is halobutyl cured against a BLADDER, and the bladder's
#                  vent grooves emboss a fine lattice into it. It is dusted
#                  with release agent and it is the only tire surface with a
#                  faint sheen.
#   laminate       is only ever seen at a cut edge: liner, tie gum, casing
#                  plies, cushion, four steel belts, cap ply, undertread,
#                  tread cap - each a band, with the STEEL CORD cross sections
#                  showing as bright dots at their real pitch.
#   bead/chafer    is a woven fabric chafer over hard apex stock, polished
#                  where the rim flange bears on it.
# ---------------------------------------------------------------------------


def _cord_row(size, v_centre, v_half, pitch, radius, phase=0.0):
    """Circular steel-cord cross sections in one laminate band.

    ``pitch`` and ``radius`` are in texture fractions. Cords repeat along u
    and are clipped to the band, which is what makes a belt read as a row of
    wires embedded in gum rather than as a stripe.

    The pitch is SNAPPED to a whole number of repeats across the sheet. An
    authored 0.052 gives 19.2 cords, so the cord straddling the wrap edge is
    cut at the wrong phase and the sheet does not tile - measured as a 5x step
    across the seam. Snapping moves each pitch by under 2%, which no eye can
    see, and closes it exactly.
    """

    repeats = max(1, round(1.0 / max(pitch, 1e-6)))
    pitch = 1.0 / repeats
    u = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[None, :], (size, 1))
    v = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))
    du = ((u / pitch + phase) % 1.0 - 0.5) * pitch
    dv = v - v_centre
    disc = np.sqrt(du * du + dv * dv) / max(radius, 1e-6)
    inside = (np.abs(dv) <= v_half).astype(float)
    return np.clip(1.0 - disc, 0.0, 1.0) * inside


def _band(size, lo, hi, feather=0.006):
    """Soft-edged horizontal band mask over v in [0, 1].

    Built as a DIFFERENCE OF STEPS so abutting bands sum to exactly 1 at every
    shared boundary. The obvious formulation - clip((v-lo)/f) * clip((hi-v)/f)
    - drives both factors to zero on a shared edge, so the accumulated colour
    there collapses to black: measured as a hairline at all seven interfaces
    of the carcass laminate (row means 1.0-3.2 against neighbours near 27).
    """

    v = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))

    def step(edge):
        return np.clip((v - edge) / feather + 0.5, 0.0, 1.0)

    return step(lo) - step(hi)


def _spew(size, rng, count, length=0.018, width=0.0045):
    """Moulded vent spew: short rubber whiskers at random angles.

    Real vent spew is the single cheapest tell that a rubber surface came out
    of a mould rather than out of a texture generator, and it is nearly always
    missing. Each whisker is a capsule with a rounded root.
    """

    field = np.zeros((size, size))
    u = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[None, :], (size, 1))
    v = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))
    for _ in range(int(count)):
        cu = float(rng.uniform(0.0, 1.0))
        cv = float(rng.uniform(0.0, 1.0))
        angle = float(rng.uniform(0.0, math.pi))
        half = length * float(rng.uniform(0.6, 1.4))
        ca, sa = math.cos(angle), math.sin(angle)
        # Wrap the offsets so a whisker crossing the seam stays tileable.
        du = (u - cu + 0.5) % 1.0 - 0.5
        dv = (v - cv + 0.5) % 1.0 - 0.5
        along = du * ca + dv * sa
        across = -du * sa + dv * ca
        along = np.clip(np.abs(along) - half, 0.0, None)
        distance = np.sqrt(along * along + across * across) / width
        field = np.maximum(field, np.clip(1.0 - distance, 0.0, 1.0))
    return field


def _checking(size, rng, cells, strength, octaves=3):
    """Ozone checking: the crazing network that opens in flexing rubber.

    Built as the ridge set of a value-noise field (|n - 0.5| near zero), which
    gives closed, branching, roughly polygonal cracks rather than the parallel
    scratches a stripe field would give.
    """

    noise = _fbm(size, rng, base_cells=cells, octaves=octaves)
    ridge = 1.0 - np.clip(np.abs(noise - 0.5) / 0.055, 0.0, 1.0)
    fine = _fbm(size, rng, base_cells=cells * 2, octaves=2)
    return ridge * (0.45 + fine * 0.55) * strength


def tire_tread(size, rng, base=(0.043, 0.042, 0.041), wear=0.42, nicks=0.55,
               rough=0.62, spew=26, grain=0.55):
    """Moulded tread compound: mould grain, vent spew, stone nicks, polish.

    The LUGS THEMSELVES ARE GEOMETRY on this prop - this family only has to
    supply the compound's surface, which is why it is not a lug pattern. Four
    things are doing the work:

    * mould grain, a very fine isotropic noise, is the base tooth. Tread
      rubber is not smooth and a smooth normal map is the giveaway.
    * vent spew whiskers, sparse and raised.
    * stone nicks: sharp, DARK, high-frequency gouges with raised lips, the
      accumulated damage of rock service. They are cut into the height field
      rather than painted, so grazing light finds them.
    * a broad polish mask that both LIGHTENS and SMOOTHS. Worked rubber
      polishes; unworked rubber in the groove shadows stays matte and dusty.
      Coupling those two channels is what stops the surface reading flat.
    """

    # Frequency budget: at TILE_TREAD = 2.20 m on 1024 px the texel is
    # 2.15 mm, so features down to ~5 mm are resolvable. Round 1 authored its
    # finest tread octave at 34 mm and the normal map measured essentially
    # flat. `fine` now starts at 102 cells (21 mm) and its top octave lands at
    # 5.4 mm, which is the actual grain of a mould plate.
    fine = _fbm(size, rng, base_cells=max(64, size // 10), octaves=3)
    micro = _fbm(size, rng, base_cells=max(96, size // 6), octaves=2)
    # MASK AND AMOUNT ARE SEPARATE. Round 1 multiplied the polish mask by
    # `wear` before using it as a mask, so it capped at 0.42 and the roughness
    # map spanned 0.667..0.827 - perceptually a constant sheet. The mask stays
    # 0..1; `wear` scales the EFFECT.
    pmask = np.clip((_fbm(size, rng, base_cells=3, octaves=3) - 0.35) / 0.5, 0.0, 1.0)
    polish = pmask * wear
    # Decametre band: at TILE_TREAD = 2.2 m a base_cells=1 octave is a 2.2 m
    # feature, which survives every mip level a hero framing uses.
    broad = _fbm(size, rng, base_cells=1, octaves=2)

    nick_field = _fbm(size, rng, base_cells=max(10, size // 40), octaves=3)
    cuts = np.clip((nick_field - (1.0 - 0.16 * nicks)) / 0.06, 0.0, 1.0)
    lips = _blur(cuts, 1.6) * 0.5 - cuts * 0.5
    whiskers = _spew(size, rng, spew)

    height = (
        (fine - 0.5) * 0.75 * grain
        + (micro - 0.5) * 0.26
        - cuts * 0.55
        + lips * 0.22
        + whiskers * 0.42
    )

    # Carbon-black rubber is not neutral: it skews very slightly blue in
    # light, and polished rubber lifts toward grey rather than toward white.
    tone = 0.46 + (fine - 0.5) * 0.30 + (micro - 0.5) * 0.16 + polish * 0.34
    color = _colorize(base, tone, 0.85)
    color[..., 2] *= 1.0 + polish * 0.10
    color *= (1.0 - cuts * 0.42)[..., None]
    color += whiskers[..., None] * 0.018

    # 0.92 unworked, 0.44 on a burnished crown, ~0.98 in a fresh cut - torn
    # rubber is the roughest thing on a tire.
    roughness = (
        0.92 - pmask * wear * 1.15 + cuts * 0.06 + (micro - 0.5) * 0.05
        + (broad - 0.5) * 0.30
    )
    color *= (0.86 + broad * 0.28)[..., None]
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def tire_sidewall(size, rng, base=(0.048, 0.047, 0.049), ripples=104.0,
                  bloom=0.60, checking=0.30, spew=34, parting=0.5,
                  rough=0.52):
    """Moulded sidewall: circumferential ripple, parting line, bloom, checking.

    ``ripples`` runs along V. The generator maps u = arc length (round the
    tire) and v = meridian arc length (out from the bead), so a stripe that
    varies along U has iso-lines of constant u, which are RADIAL spokes.
    Round 1 used axis=1 and put 76 mm radial spokes on the sidewall where a
    real one has concentric ripple; you can see them in the renders. Concentric
    means varying along v, i.e. axis=0.

    ``bloom`` is antiozonant wax and it is the whole trick: it is DEPOSITED IN
    THE RECESSES (low height), so it is masked by the inverse of the height
    field rather than sprayed uniformly. Wax also kills specular, so it lifts
    roughness where it settles.
    """

    ripple = np.abs(_stripes(size, ripples, axis=0) - 0.5) * 2.0
    ripple = ripple * ripple * (3.0 - 2.0 * ripple)
    radial = _fbm(size, rng, base_cells=max(24, size // 16), octaves=4)
    radial = np.tile(radial.mean(axis=1, keepdims=True), (1, size)) * 0.6 + radial * 0.4
    fine = _fbm(size, rng, base_cells=max(96, size // 6), octaves=3)
    # Ozone checking is 1-10 mm apart on real rubber. At 2.54 mm/texel that is
    # resolvable; round 1 authored it at 260 mm, i.e. continent scale.
    crazing = _checking(size, rng, max(48, size // 8), checking, octaves=2)
    whiskers = _spew(size, rng, spew)
    # Decametre band: dirt and water staining sweeping round the disc, plus a
    # dry bead-to-shoulder gradient. This is the only thing on the sidewall
    # that survives being mipped to a whole-tire framing.
    broad = _fbm(size, rng, base_cells=1, octaves=2)
    band = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))

    # Mould parting line: one raised, slightly flashed ridge across the sheet.
    # The parting line runs round the tire, so it is a line of constant v.
    v = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))
    seam_v = 0.5 + (radial[:, :1].mean() - 0.5) * 0.04
    seam = np.exp(-(((v - seam_v) / 0.006) ** 2)) * parting

    height = (
        (ripple - 0.5) * 0.20
        + (radial - 0.5) * 0.30
        + (fine - 0.5) * 0.11
        - crazing * 0.46
        + whiskers * 0.38
        + seam * 0.30
    )

    # A MASK, not a haze. Round 1's `clip(0.5 - height*1.4)` spanned 0.22 to
    # 0.78 over a height field of amplitude +/-0.2 - every texel got some, so
    # the "deposited in the recesses" idea in the docstring above was a flat
    # 17% film. This selects valleys and crack interiors only.
    recess = np.clip((0.02 - height) / 0.10, 0.0, 1.0) ** 1.5
    wax = recess * bloom

    tone = 0.46 + (ripple - 0.5) * 0.18 + (radial - 0.5) * 0.26 + (fine - 0.5) * 0.14
    color = _colorize(base, tone, 0.9)
    color *= (1.0 - crazing * 0.35)[..., None]
    # Bloom is a warm grey haze, not white.
    color = color * (1.0 - wax[..., None] * 0.9) + wax[..., None] * np.array(
        [0.20, 0.18, 0.15]
    ) * 0.9
    color += (whiskers * 0.016 + seam * 0.010)[..., None]

    # Wax kills specular outright, so the bloomed valleys are the matte part
    # and the ripple crowns stay waxy-glossy. That contrast is the whole
    # material read at distance.
    # `band` MUST BE PERIODIC. A 0..1 ramp across v does not wrap, so the
    # sheet's last row meets its first with a step - measured at 35.64 code
    # values, the largest step anywhere in the map, and it crosses the moulded
    # brand type once and the flank three times as a hard sheen line. A
    # triangle wave carries the same bead-to-shoulder gradient and closes.
    roughness = (
        rough + wax * 0.85 + crazing * 0.35 + (radial - 0.5) * 0.10
        + (broad - 0.5) * 0.34 + (1.0 - np.abs(2.0 * band - 1.0)) * 0.14
    )
    color *= (0.84 + broad * 0.30)[..., None]
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def tire_sidewall_print(size, rng, lines=(), base=(0.052, 0.051, 0.053),
                        aspect=6.0, relief=0.55, ink_lift=0.34, rough=0.5):
    """The small-print band: service code, TIN, load and pressure legends.

    Moulded sidewall print is RAISED rubber, the same compound as the sidewall
    - it is not ink. So the text drives the HEIGHT field and only nudges
    colour, because what makes it legible on a real tire is the shadow at the
    letter's foot and the sheen on its crown, not contrast. ``ink_lift`` is
    deliberately small for that reason: crank it and you get a printed decal.

    The strip is drawn at its true ``aspect`` and stretched into the square
    texture afterwards, the marquee lesson - drawing into the square squashes
    the type.
    """

    from PIL import ImageDraw, ImageFont

    lines = tuple(str(line) for line in lines if str(line).strip())
    strip_w = size * 2
    strip_h = max(48, int(strip_w / max(aspect, 0.5)))
    strip = Image.new("L", (strip_w, strip_h), 0)
    draw = ImageDraw.Draw(strip)
    font_path = _font_file()

    def _font(px):
        if font_path:
            return ImageFont.truetype(font_path, max(6, px))
        return ImageFont.load_default()

    if lines:
        rows = len(lines)
        px = int(strip_h / (rows + 0.8) * 0.72)
        for index, text in enumerate(lines):
            font = _font(px)
            box = draw.textbbox((0, 0), text, font=font)
            cx = strip_w / 2.0 - (box[2] - box[0]) / 2.0 - box[0]
            cy = strip_h * (index + 0.62) / (rows + 0.25) - (box[3] - box[1]) / 2.0 - box[1]
            draw.text((cx, cy), text, fill=255, font=font)

    text_mask = np.asarray(
        strip.resize((size, size), Image.LANCZOS), dtype=float
    ) / 255.0
    text_mask = np.clip(text_mask * 1.25, 0.0, 1.0)

    ripple = np.abs(_stripes(size, 96.0, axis=0) - 0.5) * 2.0
    fine = _fbm(size, rng, base_cells=max(96, size // 6), octaves=3)
    crazing = _checking(size, rng, max(48, size // 8), 0.16, octaves=2)

    height = (
        text_mask * relief
        + (ripple - 0.5) * 0.09
        + (fine - 0.5) * 0.10
        - crazing * 0.22
    )
    # Shoulder shadow at the foot of each raised character.
    foot = np.clip(_blur(text_mask, 2.2) - text_mask, 0.0, 1.0)

    tone = 0.46 + (fine - 0.5) * 0.20 + text_mask * ink_lift - foot * 0.22
    color = _colorize(base, tone, 0.9)
    # Raised print is the one part of a sidewall that stays glossy: it is
    # proud, so it never collects the wax the field does.
    roughness = (
        0.86
        - text_mask * 0.40
        + crazing * 0.22
        + foot * 0.10
        + (fine - 0.5) * 0.10
    )
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def tire_liner(size, rng, base=(0.088, 0.092, 0.086), lattice=128.0, talc=0.42,
               splices=2, rough=0.30, cord_pitch=54.0, groove_width=0.10,
               splice_width=0.010):
    """Halobutyl inner liner, cured against a bladder.

    The lattice is the point. A curing bladder is moulded with a shallow vent
    grid so trapped air can escape, and that grid is embossed into every inner
    liner ever made - a fine diamond lattice of grooves, unmistakable once you
    have seen inside a tire. It is the reason the cavity of this prop cannot
    just be dark tread rubber.

    Butyl is also the one tire surface with a slight sheen and a green-grey
    cast, and it carries release-agent dusting (``talc``) plus the raised
    ridges where the liner plies were spliced.

    PITCH MATTERS MORE THAN PATTERN HERE. A real bladder vent grid is 5-20 mm.
    Round 1 ran the lattice at 26 cells on a 2.40 m tile - 92 mm diamonds -
    and paired it with the strongest normal in the set, so the cavity of a
    28 m tire read as a tiled bathroom and actively destroyed the sense of
    scale on the largest interior surface. 128 cells is 18.7 mm, and 128
    divides 1024 so the tile stays exact.

    ``cord_pitch`` adds the other thing a liner shows and round 1 did not: the
    radial casing cords telegraphing through as a faint corduroy running
    ACROSS the tire. It is the detail that says "radial" from the inside.
    """

    u = np.tile(np.linspace(0.0, lattice, size, endpoint=False)[None, :], (size, 1))
    v = np.tile(np.linspace(0.0, lattice, size, endpoint=False)[:, None], (1, size))
    diag_a = np.abs(((u + v) % 1.0) - 0.5) * 2.0
    diag_b = np.abs(((u - v) % 1.0) - 0.5) * 2.0
    groove = np.clip(1.0 - np.minimum(diag_a, diag_b) / groove_width, 0.0, 1.0)

    fine = _fbm(size, rng, base_cells=max(96, size // 6), octaves=3)
    dust = np.clip(
        (_fbm(size, rng, base_cells=max(128, size // 4), octaves=3) - 0.58) / 0.34,
        0.0,
        1.0,
    ) * talc
    # Casing cords telegraphing through the liner: low amplitude, one axis.
    cords = (np.cos(2.0 * math.pi * np.tile(
        np.linspace(0.0, cord_pitch, size, endpoint=False)[None, :], (size, 1)
    )) * 0.5 + 0.5)

    splice = np.zeros((size, size))
    for index in range(int(splices)):
        centre = (index + 0.5) / max(int(splices), 1)
        # WIDE ENOUGH TO SURVIVE A MIP. A 0.010 gaussian is ten texels; the
        # lattice above it is sixteen, so EVERY feature on the largest
        # interior surface in the prop lived within one octave of Nyquist and
        # the whole map halved with each mip level. A ply splice on a real
        # liner is a raised band a few centimetres across, not a hairline.
        offset = (v / max(lattice, 1e-6)) - centre
        splice = np.maximum(splice, np.exp(-((offset / splice_width) ** 2)))

    height = groove * -0.26 + (fine - 0.5) * 0.10 + splice * 0.30 + (cords - 0.5) * 0.045
    tone = (
        0.50 - groove * 0.18 + (fine - 0.5) * 0.20 + dust * 0.30
        + splice * 0.08 + (cords - 0.5) * 0.05
    )
    color = _colorize(base, tone, 0.8)
    # Release dust is a pale mineral grey, and it kills the butyl sheen.
    color = color * (1.0 - dust[..., None] * 0.28) + np.array(
        [0.52, 0.52, 0.50]
    ) * dust[..., None] * 0.28

    # Butyl is the one genuinely semi-gloss surface on a tire; the release
    # dust on top of it is the matte part. That is the contrast.
    broad = _fbm(size, rng, base_cells=1, octaves=2)
    roughness = (
        rough + dust * 0.55 + groove * 0.10 - splice * 0.04 + (broad - 0.5) * 0.26
    )
    color *= (0.88 + broad * 0.24)[..., None]
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def tire_laminate(size, rng, section="tread", cap=(0.046, 0.045, 0.044),
                  liner=(0.105, 0.118, 0.100), cord=(0.62, 0.63, 0.66),
                  fabric=(0.55, 0.48, 0.36), rough=0.55):
    """The carcass in section, as seen at the cut edge of the access port.

    Bands run cavity side to outside. The STEEL CORDS are drawn as circular
    cross sections at their own pitch per band, and that difference between
    bands is the whole reason a cut edge reads as a tire rather than as a
    laminated worktop.

    ``section`` picks WHICH cut. It matters, and round 1 got it wrong in the
    most visible place on the prop: the access port is cut entirely through
    the SIDEWALL, but the band table was a CROWN section - 32% four-belt
    package, a nylon cap ply, an undertread and a tread cap. Belts stopping at
    the shoulder is the definition of a radial; that is what the R in the size
    code means. A belt package showing in a sidewall cut is the loudest
    construction error a tire person can be shown, and it was framed by its
    own hero render two metres from where the player drives past it.

    A sidewall section is: inner liner, tie gum, two radial casing plies,
    cushion gum, sidewall compound. No belts, no cap ply, no tread cap.
    """

    v = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))
    fine = _fbm(size, rng, base_cells=max(12, size // 32), octaves=3)

    if section == "sidewall":
        layers = (
            (0.000, 0.100, liner),                   # inner liner
            (0.100, 0.160, (0.088, 0.082, 0.076)),   # tie gum / squeegee
            (0.160, 0.380, (0.126, 0.120, 0.116)),   # casing ply 1
            (0.380, 0.560, (0.122, 0.116, 0.112)),   # casing ply 2
            (0.560, 0.640, (0.074, 0.071, 0.069)),   # cushion gum
            (0.640, 1.001, (0.052, 0.051, 0.053)),   # sidewall compound
        )
    else:
        layers = (
            (0.000, 0.062, liner),                   # inner liner, butyl
            (0.062, 0.104, (0.088, 0.082, 0.076)),   # tie gum / squeegee
            (0.104, 0.340, (0.126, 0.120, 0.116)),   # casing ply calender stock
            (0.340, 0.398, (0.074, 0.071, 0.069)),   # cushion gum
            (0.398, 0.716, (0.146, 0.140, 0.136)),   # belt package skim
            (0.716, 0.772, fabric),                  # nylon cap ply
            (0.772, 0.858, (0.066, 0.064, 0.062)),   # undertread
            (0.858, 1.001, cap),                     # tread cap
        )
    color = np.zeros((size, size, 3))
    height = np.zeros((size, size))
    for lo, hi, tint in layers:
        mask = _band(size, lo, hi)
        for channel in range(3):
            color[..., channel] += mask * tint[channel]
        # Each interface is a slight step: gum shrinks away from steel.
        height += mask * (0.5 - abs((lo + hi) / 2.0 - 0.5)) * 0.02

    cords = np.zeros((size, size))
    if section == "sidewall":
        # Two radial casing plies and nothing else. Coarse brass-plated cord.
        for centre, phase in ((0.270, 0.0), (0.470, 0.5)):
            cords = np.maximum(cords, _cord_row(size, centre, 0.055, 0.052, 0.019, phase))
        cap_mask = np.zeros((size, size))
    else:
        for centre, phase in ((0.163, 0.0), (0.281, 0.5)):
            cords = np.maximum(cords, _cord_row(size, centre, 0.052, 0.052, 0.019, phase))
        # Four belts: finer cord, denser pitch, the outer pair on a different
        # bias so their sections come out longer.
        for centre, pitch, radius, phase in (
            (0.440, 0.026, 0.0098, 0.0),
            (0.518, 0.026, 0.0098, 0.5),
            (0.596, 0.034, 0.0128, 0.25),
            (0.672, 0.034, 0.0128, 0.75),
        ):
            cords = np.maximum(cords, _cord_row(size, centre, 0.030, pitch, radius, phase))
        cap_mask = _band(size, 0.716, 0.772)

    weave = np.abs(_stripes(size, 96.0, axis=1) - 0.5) * 2.0

    steel = np.clip(cords, 0.0, 1.0)
    for channel in range(3):
        color[..., channel] = (
            color[..., channel] * (1.0 - steel)
            + cord[channel] * steel * (0.72 + fine * 0.5)
        )
        color[..., channel] += cap_mask * weave * fabric[channel] * 0.22

    color *= (0.80 + fine * 0.4)[..., None]
    height += steel * 0.38 - cap_mask * weave * 0.10 + (fine - 0.5) * 0.09
    # Cut rubber is matte and torn; the exposed cord ends are bright metal.
    roughness = 0.88 - steel * 0.55 + cap_mask * 0.06 + (fine - 0.5) * 0.10
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


# warp/weft must DIVIDE the texture size. At 44 over 1024 the cell
# boundaries land mid-pixel, so the boundary that falls on the wrap edge
# carries a half-pixel phase error the interior ones do not - measured as
# an 8.7x step across the seam against neighbouring columns. 64 divides
# every size this kit uses.
def tire_bead(size, rng, base=(0.058, 0.056, 0.054), warp=64, weft=64,
              polish=0.45, rough=0.48):
    """Bead area: woven fabric chafer over hard apex stock, rim-polished.

    The chafer is a real woven cloth calendered into rubber, so the weave
    telegraphs through as a shallow over-under lattice rather than as a
    printed pattern. ``polish`` is the burnished band where the rim flange
    bears - smoother, lighter, and the only part of a tire that ever gets
    shiny by contact.
    """

    ramp_u = np.tile(np.linspace(0.0, float(warp), size, endpoint=False)[None, :], (size, 1))
    ramp_v = np.tile(np.linspace(0.0, float(weft), size, endpoint=False)[:, None], (1, size))
    over = ((np.floor(ramp_u) + np.floor(ramp_v)) % 2 == 0).astype(float)
    crown_u = np.sin(np.pi * (ramp_u % 1.0))
    crown_v = np.sin(np.pi * (ramp_v % 1.0))
    weave = over * crown_u + (1.0 - over) * crown_v

    fine = _fbm(size, rng, base_cells=max(10, size // 40), octaves=3)
    v = np.tile(np.linspace(0.0, 1.0, size, endpoint=False)[:, None], (1, size))
    # PERIODIC. A monotonic ramp across the sheet does not tile, and the bead
    # is a lathed ring: its texture wraps. A raised cosine of the wrapped
    # distance keeps the burnished rim-contact band and closes the seam.
    wrapped = np.minimum(np.abs(v - 0.30), 1.0 - np.abs(v - 0.30))
    burnish = np.clip(1.0 - wrapped / 0.16, 0.0, 1.0) ** 1.6 * polish
    scuff = _streaks(size, rng, 5, length_frac=0.11) * burnish

    height = (weave - 0.5) * 0.40 + (fine - 0.5) * 0.11 - burnish * 0.14
    tone = 0.46 + (weave - 0.5) * 0.24 + (fine - 0.5) * 0.18 + burnish * 0.42
    color = _colorize(base, tone, 0.85)
    color += (burnish * 0.05 + scuff * 0.04)[..., None]
    roughness = (
        np.full((size, size), rough)
        - burnish * 0.24
        + (1.0 - weave) * 0.10
        + (fine - 0.5) * 0.06
    )
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


def diamond_plate(size, rng, base=(0.42, 0.44, 0.47), cells=32.0, lug_angle=38.0,
                  rough=0.42, wear=0.4):
    """Raised-teardrop steel floor plate.

    Two opposed lugs per cell at +-``lug_angle``, alternate rows offset half a
    cell - the standard rolled pattern. Lug crowns take traffic, so they are
    polished and lighter while the field between them stays milled and grubby.

    ``cells`` is the scale-critical knob. Real rolled tread plate has 25-60 mm
    teardrops; at TILE_STEEL = 1.60 m the round-1 default of 5 cells made them
    320 mm, right under the camera on the walkway the player boards from and
    directly beside correctly-scaled handrails. 32 cells is 50 mm, and 32
    divides 1024 exactly so the tile stays clean.
    """

    u = np.tile(np.linspace(0.0, cells, size, endpoint=False)[None, :], (size, 1))
    v = np.tile(np.linspace(0.0, cells, size, endpoint=False)[:, None], (1, size))
    shifted = u + (np.floor(v) % 2.0) * 0.5
    fu = (shifted % 1.0) - 0.5
    fv = (v % 1.0) - 0.5

    bump = np.zeros((size, size))
    for sign, offset in ((1.0, -0.21), (-1.0, 0.21)):
        angle = math.radians(lug_angle) * sign
        ca, sa = math.cos(angle), math.sin(angle)
        du = fu * ca + (fv - offset) * sa
        dv = -fu * sa + (fv - offset) * ca
        distance = np.sqrt((du / 0.30) ** 2 + (dv / 0.10) ** 2)
        bump = np.maximum(bump, np.clip(1.0 - distance, 0.0, 1.0))
    bump = bump ** 0.55

    mill = _fbm(size, rng, base_cells=2, octaves=5)
    mill = np.tile(mill.mean(axis=0, keepdims=True), (size, 1)) * 0.6 + mill * 0.4
    grime = np.clip((_fbm(size, rng, base_cells=5, octaves=4) - 0.45) / 0.4, 0.0, 1.0) * wear

    height = bump * 0.55 + (mill - 0.5) * 0.03
    tone = 0.44 + bump * 0.34 + (mill - 0.5) * 0.22 - grime * 0.26
    color = _colorize(base, tone, 0.85)
    color *= (1.0 - grime[..., None] * 0.30)

    roughness = (
        np.full((size, size), rough)
        - bump * 0.16
        + grime * 0.30
        + (mill - 0.5) * 0.08
    )
    return color.clip(0, 1), height, roughness.clip(0.05, 1), None


FAMILIES = {
    "foam_latex": foam_latex,
    "nail_keratin": nail_keratin,
    "slap_pad": slap_pad,
    "potato_skin": potato_skin,
    "tire_tread": tire_tread,
    "tire_sidewall": tire_sidewall,
    "tire_sidewall_print": tire_sidewall_print,
    "tire_liner": tire_liner,
    "tire_laminate": tire_laminate,
    "tire_bead": tire_bead,
    "diamond_plate": diamond_plate,
    "carbon_weave": carbon_weave,
    "brushed_metal": brushed_metal,
    "energy_label": energy_label,
    "scribed_chrome": scribed_chrome,
    "bakelite": bakelite,
    "painted_metal": painted_metal,
    "plastic_ribs": plastic_ribs,
    "pvc_weave": pvc_weave,
    "canvas": canvas,
    "flag_satin": flag_satin,
    "stamped_mark": stamped_mark,
    "webbing": webbing,
    "molded_nylon": molded_nylon,
    "nobori": nobori,
    "padded_vinyl": padded_vinyl,
    "field_turf": field_turf,
    "field_soil": field_soil,
    "sod_edge": sod_edge,
    "grass_card": grass_card,
    "grass_card_sparse": grass_card_sparse,
    "rubber_tread": rubber_tread,
    "wood_painted": wood_painted,
    "wood": wood,
    "concrete": concrete,
    "marquee": marquee,
    "parlour_field": parlour_field,
    "birch_ply": birch_ply,
    "lamp_bands": lamp_bands,
    "asphalt": asphalt,
    "cast_iron": cast_iron,
    "kick_pad": kick_pad,
    "ramp_deck": ramp_deck,
    "wood_plank": wood_plank,
    "end_grain": end_grain,
    "steel_worn": steel_worn,
    "machined_steel": machined_steel,
    "target_decal": target_decal,
    "stripe_decal": stripe_decal,
    "copper": copper,
    "panel_legend": panel_legend,
    "forged_ball": forged_ball,
    "hazard_chevron": hazard_chevron,
    "eggshell": eggshell,
    "whale_skin": whale_skin,
    "mesh_weave": mesh_weave,
    "straw": straw,
    "drum_perforated": drum_perforated,
    "water_surface": water_surface,
    "suds_foam": suds_foam,
    "toast_crumb": toast_crumb,
}


def external_set(out_dir, base_name: str, example_root, maps: dict) -> dict:
    """Stage checked-in external maps (e.g. baked GLB textures) as a set.

    ``maps`` maps manifest keys (baseColorMap/normalMap/roughnessMap/
    opacityMap) to example-root-relative files. Plain byte copies keep
    reruns deterministic; downstream cooking and materials.json treat the
    result exactly like a generated family.
    """

    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    suffixes = {
        "baseColorMap": ".color.png",
        "normalMap": ".normal.png",
        "roughnessMap": "_roughness.data.png",
        "opacityMap": "_opacity.data.png",
    }
    manifest: dict = {"family": "external"}
    for key, source_rel in maps.items():
        source = Path(example_root) / source_rel
        if not source.is_file():
            raise FileNotFoundError(f"external texture source missing: {source}")
        target_name = f"{base_name}{suffixes[key]}"
        _copy_stable(source, out / target_name)
        manifest[key] = target_name
    return manifest


def _srgb_encode(color: np.ndarray) -> np.ndarray:
    """Linear -> sRGB, the standard piecewise transfer function.

    THE TRANSFER-FUNCTION LAW (round 2, 2026-08-24, colossus_tire). Families
    author LINEAR albedo - `_colorize` multiplies a linear base colour - and
    `_to_image` wrote those floats straight to bytes with no encoding. But
    AGENTS.md has already MEASURED, on engine 0.39.4.0, that a `.color` map is
    decoded as sRGB. So an authored linear 0.043 was being written as byte 11,
    which the engine then decodes as linear 0.0035: twelve times darker than
    authored, and darker than any real material.

    It is worse than a brightness error. Carbon-black rubber authored linear
    occupies about 15 of 256 code values, so a BC1 cook collapses the whole
    albedo to two or three flat colours and every bit of mould grain in the
    colour channel is gone. Encoded, the same rubber spans ~60 code values.

    This is OPT-IN (`srgb=True` per palette entry) rather than a blanket fix:
    the kit is shared by twenty other shipped mods whose look was tuned
    against the un-encoded output, and whose harvested DDS are hashed against
    their current PNG bytes. Correcting them is their own round.
    """

    return np.where(
        color <= 0.0031308,
        color * 12.92,
        1.055 * np.power(np.clip(color, 0.0, None), 1.0 / 2.4) - 0.055,
    )


def build_set(
    out_dir,
    base_name: str,
    family: str,
    *,
    size: int = 512,
    normal_strength: float = 2.0,
    params: dict | None = None,
    srgb: bool = False,
) -> dict:
    """Generate one texture set; returns the map manifest (relative names).

    ``srgb`` encodes the COLOUR map only. Normal and ``_roughness.data`` maps
    are data, not colour, and must stay linear.
    """

    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = _rng(base_name)
    result = FAMILIES[family](size, rng, **(params or {}))
    if len(result) == 5:
        color, height, rough, opacity, emissive = result
    else:
        color, height, rough, opacity = result
        emissive = None
    manifest = {"family": family, "size": size}
    if srgb:
        manifest["srgb"] = True
        color = _srgb_encode(np.clip(color, 0.0, 1.0))
    color_name = f"{base_name}.color.png"
    _save_stable(_to_image(color), out / color_name)
    manifest["baseColorMap"] = color_name
    normal_name = f"{base_name}.normal.png"
    _save_stable(_to_image(_height_to_normal(height, normal_strength)), out / normal_name)
    manifest["normalMap"] = normal_name
    rough_name = f"{base_name}_roughness.data.png"
    _save_stable(_to_image(rough), out / rough_name)
    manifest["roughnessMap"] = rough_name
    if opacity is not None:
        opacity_name = f"{base_name}_opacity.data.png"
        _save_stable(_to_image(opacity), out / opacity_name)
        manifest["opacityMap"] = opacity_name
    if emissive is not None:
        # THE COOKABLE-SUFFIX LAW (round 17, 2026-08-15). The middle suffix is
        # not decoration: BeamNG's TextureCooker picks a DDS format from it, and
        # a map it does not recognise is skipped SILENTLY - no warning, no
        # error, no `.dds`, and a material that references it simply samples
        # nothing. This line used to write `.emissive.png` and that is exactly
        # what happened: measured on engine 0.39.4.0 build 20972, a calibration
        # cell declaring `emissiveMap` -> `<base>.emissive.png` had its
        # `.color`, `.normal` and `_roughness.data` siblings all imported by
        # TextureCooker in the same frame while the `.emissive.png` was never
        # touched. Across the whole shipped install that mistake is
        # unrepresented: of 20,958 shipped textures the middle suffixes are
        # only `.color` (3,945), `.data` (5,420), `.normal` (1,916), the
        # imposter/hdr/depth specials, and bare (7,642) - ZERO files are named
        # `*.emissive.*`, and of 447 stock `emissiveMap` values 376 end
        # `.color.png` and 15 `.data.png`. Stock separates the glow map from the
        # albedo by the BASE name, not the suffix (`autobello_lights_g.color.png`
        # beside `autobello_lights.color.png`) - which is also this kit's own
        # existing precedent for `_roughness.data.png`. So: `_glow.color.png`.
        # `.color` (not `.data`) because a glow map is authored in sRGB and is
        # allowed to be tinted.
        emissive_name = f"{base_name}_glow.color.png"
        if srgb:
            emissive = _srgb_encode(np.clip(emissive, 0.0, 1.0))
        _save_stable(_to_image(emissive), out / emissive_name)
        manifest["emissiveMap"] = emissive_name
    return manifest

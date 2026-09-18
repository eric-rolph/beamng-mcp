"""Orthoimagery conditioning: take the sun out of the base colour.

NAIP is flown mid-day, so every north-facing slope and every crater wall carries the
photographer's sun in the pixels. In the engine that shading is then lit AGAIN by a
different sun, which reads as patches of the wrong tone. ``delight`` fits the baked
sun direction to the DEM, models slope shading plus cast shadows, and divides the
illumination back out (in linear light, with the deepest shadows steered toward the
local lit colour so noise and the blue sky-fill tint do not blow up).
"""

from __future__ import annotations

import math

import numpy as np

from . import heightmap as hm


def _rss_gb() -> float:
    """Resident set in GB, for the phase log below."""

    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1048576.0
    except OSError:
        pass
    return 0.0


def _mem(tag: str) -> None:
    """One line per phase when GIS_MAPS_MEM is set: the de-lighting is the pack's
    memory ceiling and this is how its phases are told apart."""

    import os

    if os.environ.get("GIS_MAPS_MEM"):
        print(f"    [mem] {_rss_gb():6.2f} GB  {tag}", flush=True)


# `np.where(mask, a, b)` evaluates BOTH branches over the whole array before it
# chooses, so the one-line form of each conversion below allocated four to five
# full-size temporaries: at 8192 samples a colour array is 805 MB and the pair of
# conversions was several gigabytes of peak on its own. Each now works in place and
# computes the rare branch only where it applies, in the same order and with the same
# operations, so the result is bit-identical to the `np.where` form.


def srgb_to_linear(rgb_u8: np.ndarray) -> np.ndarray:
    c = rgb_u8.astype("float32")
    c /= 255.0
    toe = c <= 0.04045
    toe_values = c[toe] / 12.92
    c += 0.055
    c /= 1.055
    c **= 2.4
    c[toe] = toe_values
    return c


def linear_to_srgb_u8(lin: np.ndarray) -> np.ndarray:
    s = np.clip(lin, 0.0, 1.0)
    toe = s <= 0.0031308
    toe_values = s[toe] * 12.92
    np.power(s, 1 / 2.4, out=s)
    s *= 1.055
    s -= 0.055
    s[toe] = toe_values
    del toe, toe_values
    s *= 255.0
    return s.round().astype("uint8")


def clamp_highlights(lin: np.ndarray, ceiling: float) -> tuple[np.ndarray, float]:
    """Scale any texel whose brightest channel passes ``ceiling`` down until it does not.

    Returns the image and the share of texels touched; a ceiling of 0 or less is a no-op.
    The scale is one number per texel, so the hue and the saturation stay the ones the
    de-lighting produced and only the brightness moves. Clamping the channel on its own
    would swing the hue of every surface it touched.
    """

    if ceiling <= 0:
        return lin, 0.0
    hi = lin.max(axis=-1)
    over = hi > ceiling
    fraction = float(over.mean())
    if over.any():
        scale = np.where(over, ceiling / np.maximum(hi, 1e-6), 1.0).astype("float32")
        lin *= scale[..., None]
        del scale
    del hi, over
    return lin, fraction


def fit_sun(
    colour_u8: np.ndarray,
    dem: np.ndarray,
    res: float,
    *,
    altitude_range: tuple[float, float] = (30.0, 80.0),
    azimuth_hint: float | None = None,
    azimuth_window: float = 60.0,
) -> dict:
    """Grid-search the sun (azimuth, altitude) whose hillshade best correlates with luminance."""
    _mem("fit_sun")

    from scipy import ndimage

    lum = colour_u8.astype("float32").mean(axis=-1)
    smooth = ndimage.gaussian_filter(dem.astype("float32"), 2.0)
    gy, gx = np.gradient(smooth, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    mask = slope > math.radians(6.0)
    stride = max(1, int(mask.sum() // 300000))
    lum_s = lum[mask].ravel()[::stride]
    slope_s = slope[mask].ravel()[::stride]
    aspect_s = aspect[mask].ravel()[::stride]
    best = (-2.0, 0.0, 45.0)

    def corr(az, alt):
        a, el = math.radians(az), math.radians(alt)
        sh = math.sin(el) * np.cos(slope_s) + math.cos(el) * np.sin(slope_s) * np.cos(a - aspect_s)
        c = np.corrcoef(sh, lum_s)[0, 1]
        return float(c) if np.isfinite(c) else -2.0

    azimuths = (
        np.arange(azimuth_hint - azimuth_window, azimuth_hint + azimuth_window + 1, 10.0)
        if azimuth_hint is not None
        else np.arange(0, 360, 10.0)
    )
    for az in azimuths:
        for alt in np.arange(altitude_range[0], altitude_range[1] + 1, 5.0):
            c = corr(az, alt)
            if c > best[0]:
                best = (c, float(az), float(alt))
    _c0, az0, alt0 = best
    for az in np.arange(az0 - 9, az0 + 10, 2.0):
        for alt in np.arange(alt0 - 4, alt0 + 5, 1.0):
            if not altitude_range[0] <= alt <= altitude_range[1]:
                continue
            c = corr(az, alt)
            if c > best[0]:
                best = (c, float(az % 360), float(alt))
    return {"azimuth_deg": best[1], "altitude_deg": best[2], "correlation": round(best[0], 4)}


def cast_shadows(
    dem: np.ndarray, res: float, azimuth_deg: float, altitude_deg: float
) -> np.ndarray:
    """1 where the sun reaches the ground, 0 in cast shadow (horizon test along the sun line).

    The DEM is rotated so the sun shines along +columns, a running maximum of
    ``h + x * tan(alt) * res`` decides occlusion in O(N^2), then the mask rotates back.
    """
    _mem("cast_shadows")

    from scipy import ndimage

    n = dem.shape[0]
    pad = int(n * 0.21)
    padded = np.pad(dem.astype("float32"), pad, mode="edge")
    # Rotate so that the direction TOWARD the sun is +x (increasing column index).
    # Sun azimuth is compass (0 = north, 90 = east). On screen (+x right, rows down) the
    # sun direction is (sin az, -cos az), i.e. at screen angle 90 - az counter-clockwise
    # from +x; ndimage.rotate turns the image counter-clockwise, so turning it by
    # az - 90 brings that direction onto +x (az 90 -> no rotation, az 0 -> -90).
    angle = azimuth_deg - 90.0
    rotated = ndimage.rotate(padded, angle, reshape=False, order=1, mode="nearest")
    del padded
    k = math.tan(math.radians(altitude_deg)) * res
    m = rotated.shape[1]
    x = np.arange(m, dtype="float32") * k
    # Looking toward the sun means occluders sit at LARGER x. A point x' > x blocks x when
    # h' > h + (x' - x) * tan(alt) * res, i.e. when h' - x'k > h - xk: compare each sample
    # with the suffix maximum of ``h - xk`` over everything sunward of it.
    #
    # Every row is independent once the grid is rotated, so this runs in row blocks. Whole
    # -array temporaries are what put this function at 7 GB on an 8192 sample level and got
    # the build OOM-killed: the rotated grid is padded to 11,632 squared, which is 541 MB
    # a copy, and the plain form holds six or seven of them at once.
    lit = np.empty(rotated.shape, dtype="float32")
    rows = max(1, (1 << 24) // max(1, m))
    for r0 in range(0, rotated.shape[0], rows):
        r1 = min(r0 + rows, rotated.shape[0])
        ray = rotated[r0:r1] - x[None, :]
        suffix_max = np.flip(np.maximum.accumulate(np.flip(ray, axis=1), axis=1), axis=1)
        block = lit[r0:r1]
        # The horizon of column j is the suffix maximum from j+1 onward; the last column
        # has nothing sunward of it and is always lit.
        block[:, :-1] = suffix_max[:, 1:] <= ray[:, :-1] + 0.05
        block[:, -1] = 1.0
    del rotated
    back = ndimage.rotate(lit, -angle, reshape=False, order=1, mode="nearest")
    del lit
    out = back[pad : pad + n, pad : pad + n]
    return np.clip(ndimage.gaussian_filter(out, 1.0), 0.0, 1.0)


def delight(
    colour_u8: np.ndarray,
    dem: np.ndarray,
    res: float,
    *,
    azimuth_deg: float,
    altitude_deg: float,
    strength: float = 0.85,
    ambient: float = 0.32,
    max_gain: float = 2.2,
    shadow_texture_gain: float = 1.0,
    damp_mask: np.ndarray | None = None,
    damp: float = 0.3,
    snow: dict | None = None,
    steep_deg: float = 40.0,
    steep_cap: bool = True,
    steep_cap_lum: float | None = None,
    steep_feather_deg: float = 0.0,
    knee_lum: float = 0.55,
    highlight_ceiling: float = 0.95,
    cover_mask: np.ndarray | None = None,
    match_ring: bool = False,
    shadow_dark_ratio: float | None = None,
    canopy_chm: np.ndarray | None = None,
    canopy_refill: float | None = None,
    exclude_sources: np.ndarray | None = None,
    debug_hook=None,
) -> tuple[np.ndarray, dict]:
    """Return the de-lit RGB8 image plus statistics for the handoff.

    ``snow`` (``min_lum``, ``max_chroma`` in sRGB) marks the flight's snowfields and
    refills them like cast shadow, from the ground around them. Cells steeper than
    ``steep_deg`` are refilled only from lit cells that are as steep (a cliff borrows
    from cliffs, not from the scree on its ledges), and with ``steep_cap`` nothing on
    them is lifted past the median of their lit cells; the cap comes in over
    ``steep_feather_deg`` below ``steep_deg`` so it draws no contour. ``knee_lum`` is
    the linear luminance above which the output is compressed so no gain runs to
    white, and ``highlight_ceiling`` is the linear value no CHANNEL may pass (0.95
    encodes to 249, a texel under the 250 the gates read as blown); set it to 0 to
    leave the highlights alone. With ``cover_mask`` (canopy) a refill under a canopy
    borrows only from the canopy round it and one in the open only from open ground;
    with ``match_ring``
    every refilled field is brought to the mean colour and the grain amplitude of
    its own 10-30 m ring of lit ground. With ``shadow_dark_ratio`` a cell darker
    than that share of its 40 m mean and bluer than green (a cast shadow the
    horizon model never reached) is refilled as cast shadow too. With
    ``canopy_chm`` (a canopy height model on the DEM grid) the crowns' cast
    shadows on the ground between them are refilled as cast shadow too, and with
    ``canopy_refill`` the crowns themselves are refilled from the open ground round
    them at that share of its luminance: the game draws the trees, and the base
    under them is the ground between the trunks, not the crown tops.
    """
    _mem("delight")

    from scipy import ndimage

    if colour_u8.shape[0] != dem.shape[0]:
        from PIL import Image

        dem_r = np.asarray(
            Image.fromarray(dem.astype("float32"), mode="F").resize(
                (colour_u8.shape[1], colour_u8.shape[0]), Image.BILINEAR
            )
        )
        res_r = res * dem.shape[0] / colour_u8.shape[0]
    else:
        dem_r, res_r = dem, res
    smooth = ndimage.gaussian_filter(dem_r.astype("float32"), 1.0)
    shade = hm.hillshade(smooth, res_r, azimuth_deg, altitude_deg)
    visibility = cast_shadows(smooth, res_r, azimuth_deg, altitude_deg)
    # Sky light is what the shadows see, and a crater floor sees less sky than a plain:
    # scale the ambient term by the openness the AO estimate measures.
    # `openness` becomes `sky` in place, and both it and the hillshade are released
    # here rather than at the end of the frame. Written as the one-line expression
    # this held four full-size arrays plus three temporaries at once, and left
    # `shade`, `sky` and `openness` bound for the remaining 600 lines. Each step below
    # is the same operation in the same order on the same values, so `illum` is
    # bit-identical to `sky + (1.0 - sky) * shade * visibility`.
    sky = hm.ambient_occlusion(smooth, res_r, radius_px=max(8, int(40 / res_r)))
    sky *= 0.45
    sky += 0.55
    sky *= ambient
    illum = 1.0 - sky
    illum *= shade
    illum *= visibility
    illum += sky
    del sky
    # `shade` itself is read once more, 550 lines down, and only as `shade > 0.5`.
    # The mask is a byte a sample where the float is four, so it is taken here and the
    # hillshade is freed with the rest of the illumination.
    lit_shade = shade > 0.5
    del shade
    flat = ambient + (1.0 - ambient) * math.sin(math.radians(altitude_deg))
    lin = srgb_to_linear(colour_u8)
    # Minnaert-style calibration: the exponent that best explains the photographed
    # luminance from the modelled illumination (fitted on lit, sloping ground) tells how
    # strongly this image actually shades, instead of assuming a Lambertian 1.0.
    lum = lin.mean(axis=-1)
    gy, gx = np.gradient(smooth, res_r)
    grade = np.hypot(gx, gy)
    del gy, gx  # 268 MB each at 8192 samples, and `grade` is their only reader
    steep = grade > math.tan(math.radians(steep_deg))
    # The cap's weight: 0 a feather below ``steep_deg``, 1 at it (a hard threshold
    # drew a luminance contour along the 40 degree line through the scree).
    if steep_feather_deg > 0:
        slope_deg = np.degrees(np.arctan(grade))
        cap_w = np.clip(
            (slope_deg - (steep_deg - steep_feather_deg)) / steep_feather_deg, 0.0, 1.0
        ).astype("float32")
        del slope_deg
    else:
        cap_w = steep.astype("float32")
    # Snow in the flight: bright and colourless in the raw image. It is not ground and
    # never a source for the refill.
    snow_mask = np.zeros(lum.shape, dtype=bool)
    if snow:
        srgb = colour_u8.astype("float32") / 255.0
        seed_lum = float(snow.get("seed_min_lum", snow.get("min_lum", 0.8)))
        s_lum = srgb.mean(axis=-1)
        snow_mask = (s_lum > seed_lum) & (
            (srgb.max(axis=-1) - srgb.min(axis=-1)) < float(snow.get("max_chroma", 0.06))
        )
        # A seed is also brighter than its own neighbourhood: chalk scree is pale
        # for hectares, a snowfield stands out of the ground around it.
        contrast = float(snow.get("min_contrast", 0.0))
        excess = None
        if contrast > 0:
            around = ndimage.uniform_filter(s_lum, size=max(3, int(60.0 / res_r)), mode="nearest")
            excess = s_lum - around
            snow_mask &= excess > contrast
            del around
        north = snow.get("aspect_north_deg")
        if north is not None:
            # Late-summer snow lies on the faces turned away from the sun: a seed's
            # 10 m-smoothed slope descends within ``aspect_north_deg`` of north, or
            # the ground is flat. Pale scree with the same signature on a
            # south-facing plateau is not snow.
            gy10, gx10 = np.gradient(
                ndimage.gaussian_filter(dem_r.astype("float32"), 10.0 / res_r), res_r
            )
            descent = np.degrees(np.arctan2(-gx10, gy10)) % 360.0  # 0 = toward row 0 (north)
            off_north = np.minimum(descent, 360.0 - descent)
            flat_here = np.hypot(gx10, gy10) < math.tan(math.radians(3.0))
            allowed = (off_north <= float(north)) | flat_here
            any_aspect = snow.get("any_aspect_contrast")
            if any_aspect is not None and excess is not None:
                # A patch that stands far above its ring is snow on any aspect.
                allowed |= excess > float(any_aspect)
            snow_mask &= allowed
            del gy10, gx10, descent, off_north, flat_here, allowed
        relative = snow.get("relative_seed")
        if relative is not None and excess is not None:
            # Old snow in the shade of a plateau's rim is grey in the flight (0.72
            # to 0.77), colourless and smooth, and stands a fifth above its ring:
            # a seed on any aspect at any luminance over ``min_lum``.
            s_lum2 = srgb.mean(axis=-1)
            s_mean = ndimage.uniform_filter(s_lum2, size=5, mode="nearest")
            s_sq = ndimage.uniform_filter(s_lum2 * s_lum2, size=5, mode="nearest")
            smooth5 = np.sqrt(np.maximum(s_sq - s_mean * s_mean, 0.0)) < float(
                relative.get("max_std", 0.02)
            )
            snow_mask |= (
                (s_lum2 >= float(relative.get("min_lum", 0.70)))
                & (excess >= float(relative.get("min_contrast", 0.20)))
                & (
                    (srgb.max(axis=-1) - srgb.min(axis=-1))
                    < float(relative.get("max_chroma", 0.06))
                )
                & smooth5
            )
            del s_lum2, s_mean, s_sq, smooth5
        del excess
        max_std = snow.get("seed_max_std")
        if max_std is not None:
            # Snow is smooth; the cream scree the flight also shows is streaked, so a
            # seed's own 5x5 luminance spread has to be small.
            s_mean = ndimage.uniform_filter(s_lum, size=5, mode="nearest")
            s_sq = ndimage.uniform_filter(s_lum * s_lum, size=5, mode="nearest")
            snow_mask &= np.sqrt(np.maximum(s_sq - s_mean * s_mean, 0.0)) < float(max_std)
            del s_mean, s_sq
        del s_lum
        if exclude_sources is not None:
            # A bright line in the flight along a road is the road, not snow.
            snow_mask &= ~exclude_sources
        # And a bright straight bar anywhere is a cut, a tailings run or a roof.
        snow_mask = _drop_straight_bars(snow_mask, res_r)
        snow_mask = ndimage.binary_dilation(
            snow_mask, iterations=max(1, int(float(snow.get("dilate_m", 2.0)) / res_r))
        )
        del srgb
    sloping = (grade > math.tan(math.radians(6.0))) & (visibility > 0.9) & (lum > 0.02)
    sloping &= ~snow_mask
    if sloping.sum() > 5000:
        xs = np.log(np.maximum(illum[sloping], 1e-3)).ravel()[::13]
        ys = np.log(np.maximum(lum[sloping], 1e-3)).ravel()[::13]
        k = float(np.polyfit(xs, ys, 1)[0])
    else:
        k = 1.0
    k = float(np.clip(k, 0.5, 1.4)) * strength
    gain = np.clip((flat / np.maximum(illum, 0.04)) ** k, 0.45, max_gain).astype("float32")
    if damp_mask is not None:
        # A closed canopy does not shade with the terrain normal: under it the
        # correction is mostly wrong, so it is held to a fraction of itself.
        mask = damp_mask
        if mask.shape != gain.shape:
            from PIL import Image

            mask = (
                np.asarray(
                    Image.fromarray(mask.astype("uint8") * 255).resize(
                        gain.shape[::-1], Image.NEAREST
                    )
                )
                > 127
            )
        gain = np.where(mask, 1.0 + damp * (gain - 1.0), gain).astype("float32")
    corrected = lin * gain[..., None]
    # A soft knee: what the gain lifts past ``knee_lum`` is compressed, so a pale
    # plateau or a bright ledge never runs to white.
    lum_c = corrected.mean(axis=-1)
    knee = np.where(
        lum_c > knee_lum,
        (knee_lum + (lum_c - knee_lum) * 0.4) / np.maximum(lum_c, 1e-4),
        1.0,
    ).astype("float32")
    corrected = corrected * knee[..., None]
    del lum_c, knee
    if snow:
        # Snow the raw image held under the seed threshold on a shaded north face is
        # bright once the gain has lifted it: test the de-lit image too, within
        # reach of the seeds (a lit ledge is not snow because it is bright).
        srgb_c = np.power(np.clip(corrected, 0.0, 1.0), 1.0 / 2.2)
        lifted = (srgb_c.mean(axis=-1) > float(snow.get("min_lum", 0.8))) & (
            (srgb_c.max(axis=-1) - srgb_c.min(axis=-1)) < float(snow.get("max_chroma", 0.06))
        )
        near_seed = ndimage.binary_dilation(
            snow_mask, iterations=max(1, int(float(snow.get("grow_m", 20.0)) / res_r))
        )
        snow_mask |= lifted & near_seed
        del lifted, near_seed
        snow_mask = ndimage.binary_dilation(
            snow_mask, iterations=max(1, int(float(snow.get("dilate_m", 2.0)) / res_r))
        )
        del srgb_c
    # In cast shadow the pixels are mostly sky fill: the chroma is the sky's and the
    # luminance is noise. Replace both with the neighbourhood's lit colour, keeping only
    # the shadowed pixel's RELATIVE texture (its luminance against the shadow's own local
    # mean) so the wall keeps its structure without turning into holes or blue noise.
    # Cast shadow: the horizon test's core, and on the steep faces a wider one (the
    # penumbra on a wall keeps the sky's blue further than on flat ground).
    shadow_core = visibility < 0.6
    shadow_core = ndimage.binary_dilation(shadow_core, iterations=max(1, int(3.0 / res_r)))
    wall_shadow = (visibility < 0.75) & steep
    wall_shadow = ndimage.binary_dilation(wall_shadow, iterations=max(1, int(10.0 / res_r)))
    shadow_core |= wall_shadow & steep
    del wall_shadow
    if canopy_chm is not None:
        chm_r = canopy_chm
        if chm_r.shape != smooth.shape:
            from PIL import Image

            chm_r = np.asarray(
                Image.fromarray(chm_r.astype("float32"), mode="F").resize(
                    smooth.shape[::-1], Image.BILINEAR
                )
            )
        # The crowns' cast shadow on the ground between them: the horizon test on
        # the canopy surface, where the terrain alone is lit and there is no crown.
        canopy_vis = cast_shadows(smooth + np.maximum(chm_r, 0.0), res_r, azimuth_deg, altitude_deg)
        gap_shadow = (canopy_vis < 0.6) & (visibility >= 0.6) & (chm_r < 2.0)
        gap_fill = ndimage.binary_dilation(gap_shadow, iterations=max(1, int(1.0 / res_r)))
        shadow_core |= gap_fill
        canopy_fill = (chm_r >= 2.0) if canopy_refill is not None else None
        del canopy_vis, gap_shadow, chm_r
    else:
        canopy_fill = None
        gap_fill = None
    # Everything above is past its last use, and each of these is 268 MB at 8192
    # samples with `srgb` at 805 MB. Holding them to the end of a 650-line function is
    # most of what put this stage over the OOM killer's line: the names stay bound to
    # the frame long after the arrays stop being read.
    del illum, dem_r, smooth, lum
    if "srgb" in dir():
        del srgb
    # The penumbra: a cell the gain lifts more than 2.5x within 4 m of a field took
    # that lift without being in the mask and shipped as a tan halo tracing every
    # shadow's edge. It is refilled with the field.
    shadow_core |= (gain > 2.5) & ndimage.binary_dilation(
        shadow_core, iterations=max(1, int(4.0 / res_r))
    )
    if shadow_dark_ratio is not None:
        # The reference is the LIT ground of a 60 m window (cells under three
        # quarters of the window mean left out, so a 20 m blob cannot drag its own
        # reference down), and the blue test is relative to that lit ground's
        # blue-to-red; two passes, the second on the ground the first cleaned.
        win = max(3, int(60.0 / res_r))
        lum_c = corrected.mean(axis=-1)
        blob = np.zeros(lum_c.shape, dtype=bool)
        for _pass in range(2):
            around = ndimage.uniform_filter(lum_c, size=win, mode="nearest")
            lit = ((lum_c >= 0.75 * around) & ~blob).astype("float32")
            lit_n = np.maximum(ndimage.uniform_filter(lit, size=win, mode="nearest"), 1e-3)
            lit_mean = ndimage.uniform_filter(lum_c * lit, size=win, mode="nearest") / lit_n
            b_over_r = corrected[..., 2] / np.maximum(corrected[..., 0], 1e-4)
            lit_br = ndimage.uniform_filter(b_over_r * lit, size=win, mode="nearest") / lit_n
            found = (lum_c < float(shadow_dark_ratio) * lit_mean) & (b_over_r > 1.1 * lit_br)
            found = ndimage.binary_fill_holes(ndimage.binary_opening(found, iterations=1))
            blob |= found
            del around, lit, lit_n, lit_mean, b_over_r, lit_br, found
        shadow_core |= ndimage.binary_dilation(blob, iterations=max(1, int(2.0 / res_r)))
        del lum_c, blob

    def neighbourhood(weight: np.ndarray):
        # Lit neighbourhood colour at growing scales, so a shadow wider than the
        # window still finds lit ground to borrow from (never a black hole).
        local, cover = None, None
        for blur in (
            max(16, int(12 / res_r)),
            max(64, int(48 / res_r)),
            max(256, int(192 / res_r)),
        ):
            num = ndimage.uniform_filter(
                corrected * weight[..., None], size=(blur, blur, 1), mode="nearest"
            )
            den = ndimage.uniform_filter(weight, size=blur, mode="nearest")
            candidate = num / np.maximum(den, 1e-3)[..., None]
            if local is None:
                local, cover = candidate, den
            else:
                take = cover < 0.2
                local = np.where(take[..., None], candidate, local)
                cover = np.where(take, den, cover)
        source = weight > 0.9
        fallback = (
            corrected[source].reshape(-1, 3).mean(axis=0)
            if source.any()
            else corrected.reshape(-1, 3).mean(axis=0)
        )
        return np.where((cover < 0.05)[..., None], fallback[None, None, :], local)

    def _saturation(rgb):
        return (rgb.max(axis=-1) - rgb.min(axis=-1)) / np.maximum(rgb.mean(axis=-1), 1e-4)

    cover = None
    if cover_mask is not None:
        cover = cover_mask
        if cover.shape != steep.shape:
            from PIL import Image

            cover = (
                np.asarray(
                    Image.fromarray(cover.astype("uint8") * 255).resize(
                        steep.shape[::-1], Image.NEAREST
                    )
                )
                > 127
            )

    def refill(snow_now: np.ndarray):
        # Weights: what is refilled (shadow cores and snow, feathered, and the
        # crowns where the canopy is refilled), and what may be borrowed from (lit
        # ground at least 10 m clear of any snow, so a big field's own bright rim
        # never re-seeds it).
        fill_mask = shadow_core | snow_now
        if canopy_fill is not None:
            fill_mask = fill_mask | canopy_fill
        fill_w = ndimage.gaussian_filter(
            np.where(fill_mask, 1.0, 0.0).astype("float32"), max(2.0, 2.0 / res_r)
        )
        lit_w = 1.0 - fill_w
        clear = ~ndimage.binary_dilation(snow_now, iterations=max(1, int(10.0 / res_r)))
        if exclude_sources is not None:
            # The flight's own road corridor is never a source: a snow patch beside
            # a bed borrowed the white road and shipped a cream lozenge.
            clear = clear & ~exclude_sources
        source_w = lit_w * clear
        # A steep cell borrows only from lit steep cells and a gentle one from
        # gentle: a shaded cliff comes back as cliff, not as the scree on its ledges.
        # Under a canopy a gentle cell borrows from the canopy round it and in the
        # open from open ground: a snowfield across a forest edge comes back as
        # forest on the one side and meadow on the other, not the mean of both.
        steep_f = steep.astype("float32")
        gentle_w = source_w * (1.0 - steep_f)
        # The tone every refilled cell takes is the lit ground's colour carried in
        # at a scale that grows with the distance from the nearest lit cell (see
        # _carry_tone): the ring's own patches run into a field's edge and fade to
        # the neighbourhood's mean deep inside, continuously. A steep cell borrows
        # only from lit steep cells and a gentle one from gentle: a shaded cliff
        # comes back as cliff, not as the scree on its ledges. Under a canopy a
        # gentle cell borrows from the canopy round it and in the open from open
        # ground: a snowfield across a forest edge comes back as forest on the one
        # side and meadow on the other, not the mean of both.
        if cover is None:
            local = _carry_tone(corrected, gentle_w, res_r)
        elif canopy_fill is not None:
            # The crowns are targets, not sources: every gentle cell borrows from
            # the open ground, and a crown takes it at the duff's darkening.
            local = _carry_tone(corrected, gentle_w * (1.0 - cover.astype("float32")), res_r)
            local = np.where(
                (canopy_fill & ~snow_now)[..., None], local * float(canopy_refill), local
            )
        else:
            cover_f = cover.astype("float32")
            local = np.where(
                cover[..., None],
                _carry_tone(corrected, gentle_w * cover_f, res_r),
                _carry_tone(corrected, gentle_w * (1.0 - cover_f), res_r),
            )
            del cover_f
        # The steep population joins the gentle one over a 4 m feather, not at a
        # hard line (the two came out as butting flat polygons).
        steep_w = ndimage.gaussian_filter(steep_f, max(1.0, 2.0 / res_r))
        local = (
            local * (1.0 - steep_w[..., None])
            + _carry_tone(corrected, source_w * steep_f, res_r) * steep_w[..., None]
        ).astype("float32")
        del steep_w, gentle_w
        # The shadow's own structure is measured against a 40 m mean (a 12 m one
        # took the meadow-against-forest and scree-against-turf patches out with
        # the sun and left every big field one tone).
        blur = max(16, int(40 / res_r))
        own_l = corrected.mean(axis=-1)
        # The field's own local mean is taken over the field's interior (the mask
        # eroded 3 m): the fill mask carries a dilated rim of lit cells ten times
        # brighter than the shadow, and with them in the mean every cell within a
        # window of the edge read dark relative to it, so every field came back
        # 10-20 % darker than its ring, most at its edges. A field too small to
        # have an interior keeps the whole-mask mean.
        core = fill_mask
        core_w = core.astype("float32")
        own_mean = ndimage.uniform_filter(own_l * core_w, size=blur, mode="nearest") / np.maximum(
            ndimage.uniform_filter(core_w, size=blur, mode="nearest"), 1e-3
        )
        inner_w = ndimage.binary_erosion(core, iterations=max(1, int(3.0 / res_r))).astype(
            "float32"
        )
        inner_den = ndimage.uniform_filter(inner_w, size=blur, mode="nearest")
        inner_mean = ndimage.uniform_filter(
            own_l * inner_w, size=blur, mode="nearest"
        ) / np.maximum(inner_den, 1e-3)
        own_mean = np.where(inner_den > 0.05, inner_mean, own_mean)
        del core, core_w, inner_w, inner_den, inner_mean
        # Cast shadow keeps its own relative texture at full amplitude. Snow has
        # none worth keeping, so it takes the lit ground's grain carried in from
        # the ring round the field along jittered boundary vectors (random patches
        # made a checkerboard, a mirrored edge made stripes), by cover where a
        # canopy mask is given.
        own_tex = np.clip(
            1.0 + shadow_texture_gain * (own_l / np.maximum(own_mean, 1e-4) - 1.0), 0.5, 1.4
        )
        # And the shadow's own chroma structure (the trees against the meadow, the
        # turf against the scree): each channel's share of the luminance against
        # its 40 m mean over the field's interior, so the sky's cast goes with the
        # mean and the ground's own colour differences stay, faded to nothing
        # where the shadow is too dark to have measured any.
        own_share = corrected / np.maximum(own_l[..., None], 1e-4)
        core_w = ndimage.binary_erosion(fill_mask, iterations=max(1, int(3.0 / res_r))).astype(
            "float32"
        )
        share_den = np.maximum(ndimage.uniform_filter(core_w, size=blur, mode="nearest"), 1e-3)
        chroma_tex = np.empty_like(own_share)
        for ch in range(3):
            share_mean = (
                ndimage.uniform_filter(own_share[..., ch] * core_w, size=blur, mode="nearest")
                / share_den
            )
            chroma_tex[..., ch] = np.clip(
                own_share[..., ch] / np.maximum(share_mean, 1e-3), 0.7, 1.4
            )
        del own_share, core_w, share_den
        confidence = np.clip(own_l / 0.03, 0.0, 1.0)[..., None]
        chroma_tex = 1.0 + (chroma_tex - 1.0) * confidence
        chroma_tex = np.where((shadow_core & ~snow_now)[..., None], chroma_tex, 1.0).astype(
            "float32"
        )
        del confidence
        source = source_w > 0.9
        # The lit ground's grain for the snow: its luminance against a 12 m mean,
        # the pale stipple kept (a 1.15 clip had halved it).
        base_l = ndimage.uniform_filter(own_l, size=max(16, int(12 / res_r)), mode="nearest")
        hp = np.clip(own_l / np.maximum(base_l, 1e-4), 0.5, 1.6)
        del base_l
        # A cast shadow's own grain under 2 m is the flight's noise floor, not the
        # ground's (every big shadow shipped at half its ring's grain): under 2 m
        # it takes the lit ground's grain carried in from the ring, and keeps its
        # own structure above that.
        fine_base = ndimage.gaussian_filter(own_l, max(0.5, 1.0 / res_r))
        fine_hp = np.clip(own_l / np.maximum(fine_base, 1e-4), 0.6, 1.5)
        shadow_only = shadow_core & ~snow_now
        fine_carry = _propagate(fine_hp, source & clear, shadow_only, res_r, rng_seed=9)
        own_tex = np.where(
            shadow_only,
            np.clip(
                1.0 + shadow_texture_gain * (fine_base / np.maximum(own_mean, 1e-4) - 1.0),
                0.5,
                1.4,
            )
            * fine_carry,
            own_tex,
        ).astype("float32")
        del fine_base, fine_hp, fine_carry, shadow_only
        if cover is None:
            snow_tex = _propagate(hp, source & clear, snow_now, res_r, rng_seed=5)
        else:
            # A snowfield is one surface whatever stands in it: its grain is the
            # open ground's (by cover it came back as a khaki-and-mint camouflage of
            # crown duff and meadow in 10-20 m blobs).
            snow_tex = _propagate(hp, source & clear & ~cover, snow_now, res_r, rng_seed=6)
        texture = np.where(snow_now, snow_tex, own_tex)
        del snow_tex
        fields = None
        if match_ring:
            # The fields matched to their rings are the terrain's shadows and the
            # snow: a crown's shadow in a gap merges with the terrain shadow round it
            # into one blob whose busy gap cells stood in for the whole field's
            # grain, and the terrain shadow shipped at half its ring's.
            terrain_fill = shadow_core | snow_now
            if gap_fill is not None:
                terrain_fill = terrain_fill & ~(gap_fill & ~snow_now)
            fields = _ring_fields(terrain_fill, source, res_r)
            del terrain_fill
            # A field with under 50 lit cells in its 10-30 m annulus has no ring, and
            # every matching step below then leaves it exactly as it was - so the
            # whole contract silently does not apply to it. That is the failure this
            # records: a field dark enough and wide enough to read as a blotch is a
            # field whose surroundings are likely also shadow, which is precisely
            # when `has_ring` goes false. Without the count, a skipped field is
            # indistinguishable in the handoff from a field that was matched and
            # came out badly.
            ring_reports.append(
                {
                    "fields": int(fields["count"]),
                    "with_ring": int(np.asarray(fields["has_ring"]).sum()),
                }
            )
            texture = _match_amplitude(texture, hp, fields)
        del hp
        recoloured = local * texture[..., None] * chroma_tex
        del chroma_tex
        # A neighbourhood mean is greyer than the ground it averages: give the
        # refill the saturation the lit ground around it actually has.
        sat_blur = max(64, int(48 / res_r))
        lit_sat = ndimage.uniform_filter(
            _saturation(corrected) * source_w, size=sat_blur, mode="nearest"
        ) / np.maximum(ndimage.uniform_filter(source_w, size=sat_blur, mode="nearest"), 1e-3)
        boost = np.clip(lit_sat / np.maximum(_saturation(recoloured), 1e-3), 1.0, 2.0)
        lum_r = recoloured.mean(axis=-1, keepdims=True)
        recoloured = lum_r + (recoloured - lum_r) * boost[..., None]
        if fields is not None:
            # Every field lands on the mean colour of its own ring: not 10-20 %
            # darker and cooler, not pinned at a one-sided cap.
            recoloured = _match_mean(recoloured, corrected, fields)
        result = corrected * (1 - fill_w[..., None]) + recoloured * fill_w[..., None]
        if fields is not None:
            # And on its ring's grain, band by band (under 2 m and 2-8 m): a
            # shadow's own relative texture has no sun in it and the carried grain
            # is blended, so both came out a third as strong as the ring's.
            result, ratios = _match_bands(result, fields, fill_w, res_r)
            grain_ratios.append(ratios)
            result = _clamp_to_ring(result, corrected, fields, fill_w)
        if debug_hook is not None:
            debug_hook("refill", result, fields)
        return result, local, fill_w

    grain_ratios: list[np.ndarray] = []
    ring_reports: list[dict] = []
    out, local_lit, fill_w_last = refill(snow_mask)

    def _fill_kinds(snow_now: np.ndarray) -> np.ndarray:
        # 1 cast shadow of the terrain, 2 snow, 3 a crown's shadow in a gap, 4 a
        # crown itself: the level stage measures 1 and 2 against open ground.
        kinds = np.where(shadow_core, 1, 0)
        if gap_fill is not None:
            kinds = np.where(gap_fill, 3, kinds)
        kinds = np.where(snow_now, 2, kinds)
        if canopy_fill is not None:
            kinds = np.where(canopy_fill, 4, kinds)
        return kinds.astype("uint8")

    fill_last = _fill_kinds(snow_mask)
    if snow:
        # The refill can leave white where a field's rim seeded it: detect on the
        # result and refill again until nothing bright and colourless is left.
        reach = max(1, int(float(snow.get("grow_m", 20.0)) / res_r))
        edge_contrast = float(snow.get("edge_contrast", 0.06))
        for _round in range(3):
            srgb_o = np.power(np.clip(out, 0.0, 1.0), 1.0 / 2.2)
            o_lum = srgb_o.mean(axis=-1)
            still = (o_lum > float(snow.get("min_lum", 0.8))) & (
                (srgb_o.max(axis=-1) - srgb_o.min(axis=-1)) < float(snow.get("max_chroma", 0.06))
            )
            # The field's edges go with the field: a cell that still stands a little
            # above its neighbourhood next to snow is snow too.
            around = ndimage.uniform_filter(o_lum, size=max(3, int(60.0 / res_r)), mode="nearest")
            still |= ((o_lum - around) > edge_contrast) & (
                (srgb_o.max(axis=-1) - srgb_o.min(axis=-1)) < float(snow.get("max_chroma", 0.06))
            )
            del srgb_o, o_lum, around
            # Only what lies within reach of snow already found grows the mask: a
            # pale plateau or a lit ledge is not snow because it is bright.
            still &= ndimage.binary_dilation(snow_mask, iterations=reach)
            still = ndimage.binary_dilation(
                still, iterations=max(1, int(float(snow.get("dilate_m", 2.0)) / res_r))
            )
            new = still & ~snow_mask
            if new.sum() < 50:
                break
            if (snow_mask | still).mean() > float(snow.get("max_fraction", 0.02)):
                break  # a refill that wants more than the cap is eating ground, not snow
            snow_mask |= still
            out, local_lit, fill_w_last = refill(snow_mask)
            fill_last = _fill_kinds(snow_mask)
    if debug_hook is not None:
        debug_hook("after_refills", out, None)
    # No black holes: whatever a refill or a cap left near zero takes a third of
    # the lit neighbourhood instead -- but only where that is BRIGHTER than what the
    # cell already has.
    #
    # A FLOOR ONLY FLOORS WHEN ITS TRIGGER AND ITS WRITE SHARE A REFERENCE. The two
    # floors below now satisfy that, each triggering on a fraction of the lit
    # neighbourhood and writing that same fraction of it (`lum_o < 0.25 * lit_l` writing
    # `0.25 * local_lit`), so the written value is the very quantity the trigger compared
    # against and cannot land below it -- but only since the clamp came off `lit_l` below;
    # read that note before trusting the word "construction" here. This one triggered on
    # an ABSOLUTE 0.02 and wrote
    # a RELATIVE `local_lit * 0.35`, and nothing connects the two: it darkened a cell
    # whenever `0.35 * lit_l < out.mean`, which is every lit neighbourhood under
    # 0.02 / 0.35 = 0.0571. The floor against black holes was writing one.
    #
    # It is also the only writer between the refill and the encode that satisfies all
    # three conjuncts of `under_gain_floor_untouched` at once: it is not the refill, so
    # the cell still reads untouched; its written value is under 0.02, far below any
    # `floor_lum`; and a third of a dark neighbourhood over a brighter source is far
    # under 0.45. So it is that gate's writer, and it can put a texel under the
    # near-black threshold the finished base is gated on. Measured on a uniformly dark
    # synthetic scene: near black 37% of the source and 56% of the OUTPUT, this floor
    # accounting for every darkened cell and the two below it for none, in a scene where
    # the clamp below never bound. Gated, 0%.
    # Tested by `test_the_anti_black_floor_never_darkens_a_cell`.
    #
    # The two are SEPARABLE and only share this writer: swept independently, a scene can
    # reach 2,786 breach cells with the near-black fraction still at exactly zero. So a
    # green `under_gain_floor_untouched` is not evidence that a map's black ground is
    # fixed, and neither number stands in for the other.
    #
    # The gate is on luminance rather than per channel, so a rescued cell still takes the
    # lit neighbourhood's COLOUR and not a channel-wise maximum of two tones. Skipping
    # the write cannot darken anything either: where it is skipped `out.mean` is already
    # at or above `0.35 * lit_l`, hence above the `0.25 * lit_l` the floor below would
    # write, so `out >= 0.25 * local_lit` still holds everywhere after this block.
    #
    # Memory: the comparison is held as two SINGLE-channel arrays and the write keeps
    # the transient `local_lit * 0.35` it always had, so the peak here is what it was.
    # A full-size `lit_third` to compare and then write would be 200 MB at 4096 samples
    # against a stage peak near 250 MB, which is the ceiling this stage already runs at.
    lum_dark = out.mean(axis=-1)
    lit_third_lum = local_lit.mean(axis=-1) * 0.35
    dark = (lum_dark < 0.02) & (lit_third_lum > lum_dark)
    out = np.where(dark[..., None], local_lit * 0.35, out)
    del lum_dark, lit_third_lum, dark
    # And a relative floor: nothing sits under a quarter of the lit neighbourhood's
    # luminance (the shaded side of a spruce crown is near black in the flight, and
    # a base seen between the trunks is ground, not a black blotch). Such a cell
    # takes the lit neighbourhood's colour at the floor's luminance. The reference
    # is the lit neighbourhood, not a window mean a wide blob would drag down.
    lum_o = out.mean(axis=-1)
    # The reference is UNCLAMPED, because the writes below are `local_lit * 0.25` and
    # `local_lit * 0.4` and a floor only floors when its trigger and its write share one.
    # This read `np.maximum(local_lit.mean(axis=-1), 1e-4)` while both writes stayed
    # unclamped, so wherever the guard bound, the trigger compared against a brighter
    # neighbourhood than the write delivered and the floor darkened -- the same defect as
    # the floor above, one guard further down. Worked through: at a neighbourhood mean of
    # 6.0e-05 the guard reports 1.0e-04, a cell the floor above had just set to 2.1e-05
    # trips a trigger of 2.5e-05, and the write puts it at 1.5e-05, a factor of 0.714.
    #
    # LATENT, not observed: it needs a lit neighbourhood under 0.25e-4 / 0.35 = 7.14e-05,
    # which no scene in the suite reaches, and `seen`'s 0.01 source cut keeps such cells
    # out of `under_gain_floor_untouched` anyway, so no gate here would have reported it.
    # It was found by two readers checking the sibling floors' exoneration against the
    # guard rather than against the intent -- and the exoneration was conditional, which
    # is why it is repaired structurally rather than bounded. Nothing divided by `lit_l`:
    # it is only ever multiplied by a fraction and compared, so the guard bought nothing
    # here and its only effect was to break the reference it was standing next to.
    lit_l = local_lit.mean(axis=-1)
    under = lum_o < 0.25 * lit_l
    out = np.where(under[..., None], local_lit * 0.25, out)
    if canopy_fill is not None:
        # A crown refilled from shaded ground was near black: a crown sits at no
        # less than four tenths of the lit ground round it.
        crown_dark = canopy_fill & (lum_o < 0.4 * lit_l)
        out = np.where(crown_dark[..., None], local_lit * 0.4, out)
        del crown_dark
    del lum_o, under, lit_l
    # No sky on the walls, nor on a refilled field: a cell bluer than the lit ground
    # around it takes that ground's chroma at its own luminance (a steep wall, or
    # a refill whose carry ran from a bluer ring).
    lit_lum = local_lit.mean(axis=-1, keepdims=True)
    lit_mean = np.maximum(lit_lum, 1e-4)
    lit_ratio = local_lit / lit_mean
    own_br = out[..., 2] / np.maximum(out[..., 0], 1e-4)
    lit_br = lit_ratio[..., 2] / np.maximum(lit_ratio[..., 0], 1e-4)
    blue = (steep | (fill_last > 0)) & (out[..., 2] > 0.95 * out[..., 0]) & (own_br > 1.05 * lit_br)
    del own_br, lit_br
    out = np.where(blue[..., None], out.mean(axis=-1, keepdims=True) * lit_ratio, out)
    # Whether that write was the luminance-preserving one it is written as. `lit_ratio` has
    # channel-mean exactly 1 only while `local_lit.mean` clears the 1e-4 guard above; below
    # it the `np.maximum` clamps the DENOMINATOR and this line stops holding luminance and
    # becomes a straight multiply by `local_lit.mean / 1e-4` - 0.10 at 1e-5, 0.02 at 2e-6.
    # Nothing recorded that, so the de-cast was eliminated as luminance-preserving on a
    # reading of its intent rather than of its guard. The contract is that the guard never
    # binds where this writes, so the number is a share and its only healthy value is zero.
    # Measured on `lit_lum`, the reference BEFORE the guard clamps it - not on `lit_mean`.
    # `lit_mean` is the `np.maximum` output, so it can never read under 1e-4 and a share
    # taken from it is zero on every input, healthy or not. That is this pack's own recurring
    # defect (a correction upstream of the threshold that judges it) and it was caught here
    # by the negative control below rather than by review.
    under_guard = lit_lum[..., 0] < 1e-4
    decast_written = under_guard & blue
    decast_guard = {
        "cells_under_guard": round(float(under_guard.mean()), 6),
        "written_under_guard": round(float(decast_written.mean()), 6),
    }
    del lit_lum, lit_mean, lit_ratio, blue, under_guard
    if debug_hook is not None:
        debug_hook("after_floors_blue", out, None)
    cap_lum = None
    if steep_cap:
        # Nothing on a steep face is lifted past what its lit faces measure: the
        # gain that brings a shaded wall back must not make it paler than a lit one.
        lit_steep = steep & (visibility > 0.9) & lit_shade & ~snow_mask
        if lit_steep.sum() > 2000:
            lum_o = out.mean(axis=-1)
            cap_lum = float(np.median(lum_o[lit_steep]))
            if steep_cap_lum is not None:
                # The author's own ceiling (the lit median of a cliff seen from above
                # is the scree on its ledges, not the wall).
                cap_lum = min(cap_lum, float(steep_cap_lum))
            over = (cap_w > 0) & (lum_o > cap_lum)
            scale = np.where(
                over, (cap_lum + (lum_o - cap_lum) * 0.3) / np.maximum(lum_o, 1e-4), 1.0
            ).astype("float32")
            scale = 1.0 - cap_w * (1.0 - scale)
            out = out * scale[..., None]
            del lum_o, scale
    # And nothing reaches white, per channel. The soft knee above compresses on MEAN
    # luminance, but it is a single CHANNEL that hits the 8-bit wall, so a warm surface
    # saturates its red while its mean sits well under the knee: measured on the shipped
    # bases, every clipped texel of Factory Butte's caprock and Meteor Crater's
    # east-facing limestone is clipped in red alone or in red and green, never in all
    # three, in blobs of 4-1200 texels rather than the specks a resampling artefact
    # leaves. Scaling the whole texel by the ceiling over its own brightest channel
    # holds its hue and its saturation and darkens only what the 8-bit wall would have
    # thrown away. Last thing before the encode, so no refill, floor or cap re-lifts it.
    out, over_ceiling = clamp_highlights(out, highlight_ceiling)
    # What this stage did to each cell, end to end. Every reducing step above is clipped
    # -- the gain floors at 0.45, the knee and the steep cap cannot take a cell below
    # their own reference, the refill's floors hold one at a quarter of the lit
    # neighbourhood -- and nothing measures their product. `gain_p05` is the ILLUMINATION
    # gain, which is the model's intent rather than the result, so a cell can ship at a
    # fiftieth of what the flight photographed with every recorded number inside its own
    # bound. That is this pack's recurring defect (a stage recording what it produced and
    # not what it consumed), and these two numbers close it for the de-lighting.
    #
    # Memory: the source luminance is summed a channel at a time from `colour_u8`, which
    # is still bound, rather than re-forming `lin`. Three single-channel float32 arrays
    # are live at the peak (source, output, ratio), about 200 MB at 4096 samples against
    # a stage peak near 250 MB; the source is freed as soon as the ratio exists and the
    # output luminance as soon as the breach mask does, and the percentiles run on the
    # same stride `source_colour_stats` uses rather than on a full copy. This is where
    # the pack meets its memory ceiling, so nothing here outlives its last read.
    src_lum = np.zeros(out.shape[:2], dtype="float32")
    for _ch in range(3):
        src_lum += srgb_to_linear(colour_u8[..., _ch])
    src_lum /= 3.0
    out_lum = out.mean(axis=-1)
    # Only where there was something to darken: a cell the flight already photographed
    # near black says nothing about this stage, and dividing by it manufactures outliers.
    seen = src_lum > 0.01
    composed = out_lum / np.maximum(src_lum, 1e-4)
    del src_lum
    # The one bound that needs no population behind it. A cell the refill did not touch
    # is `source * gain`, then the knee and the steep cap -- and both of those are
    # one-sided pulls toward their own reference, so a cell that has been through either
    # ends at or above `min(knee_lum, cap_lum)`. A cell that ships DARKER than that has
    # been through neither, which leaves the gain as its only writer, and the gain is
    # clipped at 0.45. So an untouched dark cell under 0.45 of its source is not a tuning
    # question: some writer is outside the contract every clip in here is meant to give.
    untouched = seen & (fill_w_last < 0.01)
    floor_lum = min(float(knee_lum), float(cap_lum) if cap_lum is not None else float(knee_lum))
    breach = untouched & (out_lum < floor_lum) & (composed < 0.45)
    del out_lum
    sample = composed[::4, ::4][seen[::4, ::4]]
    stats = {
        "highlight_ceiling_fraction": round(over_ceiling, 6),
        # The de-lighting's own end-to-end effect, over the cells the flight gave it
        # something to work with (`seen`), and what it did where it had no licence to.
        "composed_ratio": {
            "p01": round(float(np.percentile(sample, 1)), 4) if sample.size else None,
            "p50": round(float(np.percentile(sample, 50)), 4) if sample.size else None,
            "under_0_25": round(float((seen & (composed < 0.25)).mean()), 6),
            "under_gain_floor_untouched": round(float(breach.mean()), 6),
            # The count, because the bound is exactly 0.0: a fraction of 7e-06 cannot say
            # whether that is one edge cell or a real artefact, and the count can.
            "under_gain_floor_untouched_cells": int(breach.sum()),
        },
        # What the refill BORROWED, against the lit ground it borrowed from. `_carry_tone`
        # normalises by the donor weight it found, so its own arithmetic says the donors
        # were THERE and never what they were worth: a field ringed by ground this stage
        # has itself left dark refills to dark, the anti-black floors then write a quarter
        # of that same dark tone, and every clip upstream stays inside its bound. This is
        # the number that would say so, as a share of the median the lit ground shipped at.
        "refill_carry_ratio": _carry_ratio(local_lit, fill_w_last, out),
        # Whether the blue de-cast held luminance where it wrote (see decast_guard above).
        "decast_guard": decast_guard,
        # How many refilled fields ring matching could actually reach (last refill).
        "refill_ring_cover": ring_reports[-1] if ring_reports else None,
        "snow_fraction": round(float(snow_mask.mean()), 4),
        # The 2-8 m grain of every refilled field over its ring's, after the match
        # (area-weighted p10 and median over the fields of the last refill).
        "refill_grain_ratio": (
            {
                "p10": round(float(np.percentile(grain_ratios[-1], 10)), 3),
                "p50": round(float(np.percentile(grain_ratios[-1], 50)), 3),
            }
            if grain_ratios and grain_ratios[-1].size
            else None
        ),
        "steep_fraction": round(float(steep.mean()), 4),
        "steep_cap_lum": round(cap_lum, 4) if cap_lum is not None else None,
        "sun_azimuth_deg": round(float(azimuth_deg), 1),
        "sun_altitude_deg": round(float(altitude_deg), 1),
        "minnaert_k": round(k, 3),
        "cast_shadow_fraction": round(float((visibility < 0.5).mean()), 4),
        "gain_p05": round(float(np.percentile(gain, 5)), 3),
        "gain_p95": round(float(np.percentile(gain, 95)), 3),
        # The refilled cells (1 cast shadow, 2 snow), for the level stage to measure
        # every field against its ring on the shipped base.
        "_refill_mask": fill_last,
    }
    shipped = linear_to_srgb_u8(out)
    # Does the de-cast's unguarded write land on the cells that ship black? A share across
    # maps is a correlation; this is the per-cell question on one map. Taken on THIS stage's
    # own encode, which is NOT the shipped base - `paint_road_beds`, `enforce_bed_contrast`,
    # `refill_match` and the shipping clamp all write after it - so `near_black_here` and the
    # level stage's `near_black_fraction` are different numbers, and a gap between them is
    # itself the answer to where the black is made.
    near_black_here = shipped.max(axis=-1) < 13
    here = int(near_black_here.sum())
    decast_guard["near_black_here"] = round(float(near_black_here.mean()), 6)
    decast_guard["near_black_written_under_guard"] = (
        round(float((near_black_here & decast_written).sum() / here), 6) if here else None
    )
    del near_black_here, decast_written
    return shipped, stats


def _carry_ratio(local_lit: np.ndarray, fill_w: np.ndarray, out: np.ndarray) -> dict | None:
    """The refill's carried tone over the lit ground's own median, at the low end.

    The carry is a weighted mean of the lit donors and its normaliser is a weight, not a
    value, so nothing in the refill notices donors that are themselves dark. Reported as
    a ratio rather than a level so it reads the same on a pale desert and a dark pit."""

    refilled = fill_w > 0.5
    lit = fill_w < 0.01
    if not refilled.any() or not lit.any():
        return None
    lum = local_lit.mean(axis=-1)
    reference = float(np.median(out.mean(axis=-1)[lit][::4]))
    if reference <= 1e-4:
        return None
    sample = lum[refilled][::4] / reference
    del lum
    return {
        "p01": round(float(np.percentile(sample, 1)), 4),
        "p50": round(float(np.percentile(sample, 50)), 4),
        "under_0_1": round(float((sample < 0.1).mean()), 6),
    }


def layer_colour_stats(
    colour_u8: np.ndarray, layer: np.ndarray, materials: list[str]
) -> dict[str, list[float]]:
    """Mean linear RGB of the imagery under each terrain layer (for detail-tint matching)."""
    _mem("layer_colour_stats")

    if colour_u8.shape[0] != layer.shape[0]:
        from PIL import Image

        layer_r = np.asarray(
            Image.fromarray(layer.astype("uint8")).resize(
                (colour_u8.shape[1], colour_u8.shape[0]), Image.NEAREST
            )
        )
    else:
        layer_r = layer
    lin = srgb_to_linear(colour_u8)
    out = {}
    for index, name in enumerate(materials):
        mask = layer_r == index
        if mask.sum() < 100:
            out[name] = [0.5, 0.5, 0.5]
            continue
        out[name] = [round(float(v), 4) for v in lin[mask].mean(axis=0)]
    return out


def _carry_tone(
    corrected: np.ndarray, weight: np.ndarray, res_m: float, *, scale: float = 0.8
) -> np.ndarray:
    """The colour of the ``weight`` (lit) cells carried everywhere at a scale that grows
    with the distance from the nearest lit cell: at the edge of a field the tone is
    the ring's own 4 m mean, 20 m in it is a 16 m mean, 100 m in a 64 m one. A
    normalised Gaussian at each of six scales, blended per cell between the two
    scales round ``scale`` x its distance, so the carry is continuous everywhere:
    no nearest-cell facets (a big field came back as a mosaic of flat polygons, one
    per ring cell), no field-wide mean; the ring's 10-50 m structure runs a little
    way in and fades to the neighbourhood's mean deep inside. A scale with no lit
    support at a cell hands the cell to the next coarser one."""

    from scipy import ndimage

    sigmas_m = (4.0, 8.0, 16.0, 32.0, 64.0, 128.0)
    dist = ndimage.distance_transform_edt(weight < 0.5) * res_m
    want = np.clip(scale * dist, sigmas_m[0], sigmas_m[-1])
    del dist
    pos = np.log2(want / sigmas_m[0]).astype("float32")
    del want
    lo = np.floor(pos).astype("int8")
    frac = (pos - lo).astype("float32")
    del pos
    out = np.zeros(corrected.shape, dtype="float32")
    w = weight.astype("float32")
    for i, s in enumerate(sigmas_m):
        sig = max(0.5, s / res_m)
        # The coarse scales are filtered on a grid decimated to an eighth of the
        # sigma (a 128 m Gaussian on every metre of a 4 km map was the build's
        # slowest step by far) and brought back bilinearly: the tone at those
        # scales is smooth by construction.
        dec = int(min(8, max(1, sig // 8)))
        den = _gaussian_decimated(w, sig, dec)
        if i < len(sigmas_m) - 1:
            # No lit ground within reach at this scale: the next scale takes it.
            bump = (lo == i) & (den < 0.02)
            lo[bump] = i + 1
            frac[bump] = 0.0
            del bump
        share = np.where(lo == i, 1.0 - frac, 0.0) + np.where(lo == i - 1, frac, 0.0)
        share = share.astype("float32")
        if not share.any():
            continue
        inv = share / np.maximum(den, 1e-3)
        del den
        for ch in range(3):
            out[..., ch] += _gaussian_decimated(corrected[..., ch] * w, sig, dec) * inv
        del inv, share
    del lo, frac, w
    return out


def _gaussian_decimated(field: np.ndarray, sigma_px: float, dec: int) -> np.ndarray:
    """``gaussian_filter(field, sigma_px)`` computed on a grid decimated ``dec`` times
    (box means) and brought back bilinearly; ``dec`` 1 is the plain filter."""

    from scipy import ndimage

    if dec <= 1:
        return ndimage.gaussian_filter(field, sigma_px)
    n0, n1 = field.shape
    p0, p1 = (-n0) % dec, (-n1) % dec
    padded = np.pad(field, ((0, p0), (0, p1)), mode="edge") if (p0 or p1) else field
    small = padded.reshape(padded.shape[0] // dec, dec, padded.shape[1] // dec, dec).mean(
        axis=(1, 3)
    )
    small = ndimage.gaussian_filter(small.astype("float32"), sigma_px / dec)
    back = ndimage.zoom(small, dec, order=1, mode="nearest", grid_mode=True)
    return back[:n0, :n1].astype("float32")


def _propagate(
    hp: np.ndarray, source: np.ndarray, target: np.ndarray, res_m: float, *, rng_seed: int = 11
) -> np.ndarray:
    """The high-pass ratio ``hp`` of the ``source`` cells carried into the ``target``
    cells: each target cell takes the source cell nearest to a jittered position (a
    smooth two-scale jitter, 3 m at 3 m and 6 m at 12 m, so the grain stays coherent
    and no ray into the field comes from one ring cell for long), seams blended over
    2 m; 1 elsewhere."""

    from scipy import ndimage

    out = np.ones(hp.shape, dtype="float32")
    if not target.any() or not source.any():
        return out
    rows, cols = np.nonzero(target)
    pad = int(40.0 / res_m)
    r0, r1 = max(int(rows.min()) - pad, 0), min(int(rows.max()) + pad + 1, hp.shape[0])
    c0, c1 = max(int(cols.min()) - pad, 0), min(int(cols.max()) + pad + 1, hp.shape[1])
    src = source[r0:r1, c0:c1]
    tgt = target[r0:r1, c0:c1]
    if not src.any():
        return out
    _dist, (ir, ic) = ndimage.distance_transform_edt(~src, return_indices=True)
    del _dist
    rng = np.random.default_rng(rng_seed)

    def smooth_noise(sigma_m: float, amp_m: float) -> np.ndarray:
        field = ndimage.gaussian_filter(
            rng.standard_normal(tgt.shape).astype("float32"), max(0.5, sigma_m / res_m)
        )
        return field * (amp_m / res_m / max(float(field.std()), 1e-6))

    jr = smooth_noise(3.0, 3.0) + smooth_noise(12.0, 6.0)
    jc = smooth_noise(3.0, 3.0) + smooth_noise(12.0, 6.0)
    tr, tc = np.nonzero(tgt)
    pr = np.clip(np.round(tr + jr[tr, tc]).astype(int), 0, tgt.shape[0] - 1)
    pc = np.clip(np.round(tc + jc[tr, tc]).astype(int), 0, tgt.shape[1] - 1)
    del jr, jc
    filled = np.zeros(tgt.shape, dtype="float32")
    filled[tr, tc] = hp[r0:r1, c0:c1][ir[pr, pc], ic[pr, pc]]
    del ir, ic, pr, pc
    sigma = max(0.5, 1.0 / res_m)
    tgt_f = tgt.astype("float32")
    blend = ndimage.gaussian_filter(filled * tgt_f, sigma) / np.maximum(
        ndimage.gaussian_filter(tgt_f, sigma), 1e-3
    )
    out[r0:r1, c0:c1] = np.where(tgt, blend, 1.0)
    return out


def _ring_fields(fill: np.ndarray, source: np.ndarray, res_m: float) -> dict:
    """Label the refilled fields and give each its ring: the ``source`` cells 10-30 m
    outside it (nearest-field assignment), for matching a field to the ground round
    it. ``count`` fields, ``labels`` over the fill, ``ring_labels`` over the ring."""

    from scipy import ndimage

    labels, count = ndimage.label(fill)
    if not count:
        return {"count": 0}
    dist, (ir, ic) = ndimage.distance_transform_edt(~fill, return_indices=True)
    ring = (dist > 10.0 / res_m) & (dist <= 30.0 / res_m) & source
    del dist
    ring_labels = np.where(ring, labels[ir, ic], 0).astype(labels.dtype)
    del ir, ic
    index = np.arange(1, count + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ring_n = ndimage.sum(ring.astype("float32"), ring_labels, index)
    return {
        "count": count,
        "labels": labels,
        "ring_labels": ring_labels,
        "index": index,
        "has_ring": ring_n >= 50,
    }


def _match_amplitude(texture: np.ndarray, hp: np.ndarray, fields: dict) -> np.ndarray:
    """Scale each field's grain (``texture`` about 1) to the spread its ring's ``hp``
    has, so a refill is neither flatter nor busier than the ground round it."""

    from scipy import ndimage

    if not fields["count"]:
        return texture
    index = fields["index"]
    with np.errstate(invalid="ignore", divide="ignore"):
        own = ndimage.standard_deviation(texture, fields["labels"], index)
        ring = ndimage.standard_deviation(hp, fields["ring_labels"], index)
    gain = np.where(fields["has_ring"] & (own > 1e-3), ring / np.maximum(own, 1e-3), 1.0)
    lut = np.concatenate([[1.0], np.clip(gain, 0.5, 2.0)]).astype("float32")
    return np.clip(1.0 + (texture - 1.0) * lut[fields["labels"]], 0.4, 1.6)


def _match_bands(
    rgb: np.ndarray, fields: dict, fill_w: np.ndarray, res_m: float
) -> tuple[np.ndarray, np.ndarray]:
    """Scale each field's luminance grain in two bands (under 2 m, 2-8 m) to the rms
    its ring has in the same band, measured over the field's interior (6 m in from
    its edge, so the edge itself is not counted as grain) and applied as a
    multiplicative correction over the feathered fill. Returns (rgb, the 2-8 m
    ratio of every field's interior to its ring measured after the match, one
    value per field cell, for the handoff)."""

    from scipy import ndimage

    empty = np.zeros(0, dtype="float32")
    if not fields["count"]:
        return rgb, empty
    index = fields["index"]
    labels, ring_labels = fields["labels"], fields["ring_labels"]
    interior = ndimage.binary_erosion(labels > 0, iterations=max(1, int(6.0 / res_m)))
    labels_in = np.where(interior, labels, 0)
    del interior
    s1, s4 = max(0.5, 1.0 / res_m), max(1.0, 4.0 / res_m)

    def bands(lum):
        g1 = ndimage.gaussian_filter(lum, s1)
        g4 = ndimage.gaussian_filter(lum, s4)
        return lum - g1, g1 - g4, g4

    def rms_ratio(band):
        # The field's interior rms over its ring's; a field with no interior
        # (under 8 m across) is measured whole.
        with np.errstate(invalid="ignore", divide="ignore"):
            own_in = np.sqrt(ndimage.mean(band * band, labels_in, index))
            own_all = np.sqrt(ndimage.mean(band * band, labels, index))
            ring = np.sqrt(ndimage.mean(band * band, ring_labels, index))
        own = np.where(np.isfinite(own_in), own_in, own_all)
        ok = fields["has_ring"] & np.isfinite(own) & (own > 1e-4) & np.isfinite(ring)
        return np.where(ok, ring / np.maximum(own, 1e-4), 1.0), ok

    lum = rgb.mean(axis=-1)
    fine, mid, g4 = bands(lum)
    # And the 8-32 m band (the ground's patches), against a 16 m smooth.
    g16 = ndimage.gaussian_filter(lum, max(2.0, 16.0 / res_m))
    coarse = g4 - g16
    del g16
    correction = np.zeros(lum.shape, dtype="float32")
    for band, cap in ((fine, 3.0), (mid, 4.0), (coarse, 3.0)):
        gain, _ok = rms_ratio(band)
        lut = np.concatenate([[1.0], np.clip(gain, 1.0, cap)]).astype("float32")
        correction += (lut[labels] - 1.0) * band
    # Over the field's own cells only (the fill's 2 m feather reaches the dark edge
    # of a crown beside a gap, which a 0.3 floor then took to black), and never
    # below half the local level.
    factor = np.where(
        labels > 0, np.clip(1.0 + correction / np.maximum(g4, 1e-3), 0.5, 2.5), 1.0
    ).astype("float32")
    del correction, fine, mid, g4
    out = rgb * factor[..., None]
    # Measured after the match, on the result.
    _fine2, mid2, _g = bands(out.mean(axis=-1))
    gain_after, ok = rms_ratio(mid2)
    del mid2
    after = np.where(ok, 1.0 / np.maximum(gain_after, 1e-4), 1.0).astype("float32")
    lut_after = np.concatenate([[1.0], after]).astype("float32")
    cells = labels_in > 0
    return out, lut_after[labels_in[cells]] if cells.any() else empty


def _clamp_to_ring(
    rgb: np.ndarray,
    lit_rgb: np.ndarray,
    fields: dict,
    fill_w: np.ndarray,
    *,
    max_lum_dev: float = 0.06,
    max_chroma_dev: float = 0.02,
) -> np.ndarray:
    """Hard-clamp every field's mean to its ring's, after the band match: its mean
    luminance to within ``max_lum_dev`` and its mean position on both chroma axes
    (excess green 2G-R-B and blue-minus-red) to within ``max_chroma_dev``.

    The per-channel ratio match runs before the band correction and is bounded, so a
    field could still land a tenth pale or a tenth green: the refills came back as
    dusty-rose banding through the tundra and pale lozenges beside the roads. The
    chroma corrections are luminance-preserving shifts, so the clamp cannot undo the
    luminance one."""

    from scipy import ndimage

    if not fields["count"]:
        return rgb
    index = fields["index"]
    labels, ring_labels = fields["labels"], fields["ring_labels"]
    ok = fields["has_ring"]
    out = rgb

    def means(image, lab):
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.stack([ndimage.mean(image[..., ch], lab, index) for ch in range(3)], axis=-1)

    for axis in ("exg", "br"):
        field = means(out, labels)
        ring = means(lit_rgb, ring_labels)
        if axis == "exg":
            own = 2 * field[:, 1] - field[:, 0] - field[:, 2]
            theirs = 2 * ring[:, 1] - ring[:, 0] - ring[:, 2]
        else:
            own = field[:, 2] - field[:, 0]
            theirs = ring[:, 2] - ring[:, 0]
        excess = np.where(ok & np.isfinite(own) & np.isfinite(theirs), own - theirs, 0.0)
        over = np.clip(np.abs(excess) - max_chroma_dev, 0.0, None) * np.sign(excess)
        # A luminance-preserving shift along the axis: for excess green, green moves
        # by -a and red and blue by +a/2 each; for blue-red, blue and red by -+a/2.
        step = over / (3.0 if axis == "exg" else 1.0)
        lut = np.concatenate([[0.0], np.clip(step, -0.08, 0.08)]).astype("float32")
        shift = lut[labels]
        if axis == "exg":
            delta = np.stack([shift * 0.5, -shift, shift * 0.5], axis=-1)
        else:
            delta = np.stack([shift * 0.5, np.zeros_like(shift), -shift * 0.5], axis=-1)
        out = out + delta * fill_w[..., None]
        del field, ring, shift, delta
    field_l = np.stack([ndimage.mean(out.mean(axis=-1), labels, index)], axis=-1)[:, 0]
    ring_l = np.stack([ndimage.mean(lit_rgb.mean(axis=-1), ring_labels, index)], axis=-1)[:, 0]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(ok & (field_l > 1e-4), field_l / np.maximum(ring_l, 1e-4), 1.0)
    ratio = np.where(np.isfinite(ratio), ratio, 1.0)
    want = np.clip(ratio, 1.0 - max_lum_dev, 1.0 + max_lum_dev)
    gain = np.where(ratio > 1e-4, want / np.maximum(ratio, 1e-4), 1.0)
    lut_g = np.concatenate([[1.0], np.clip(gain, 0.7, 1.4)]).astype("float32")
    g = lut_g[labels]
    return out * (1.0 + (g - 1.0) * fill_w)[..., None]


def _drop_straight_bars(
    mask: np.ndarray, res_m: float, *, min_area_m2: float = 400.0
) -> np.ndarray:
    """Drop every component of ``mask`` that is a straight bar: one whose cells fill
    more than three quarters of their own principal-axis box while that box is over
    three times as long as it is wide. A snowfield lies in a hollow and has a ragged
    outline; a cut, a tailings run or a roof line in the flight is a bar."""

    from scipy import ndimage

    labels, count = ndimage.label(mask)
    if not count:
        return mask
    out = mask.copy()
    min_cells = max(16, int(min_area_m2 / (res_m * res_m)))
    for sl, k in zip(ndimage.find_objects(labels), range(1, count + 1), strict=False):
        if sl is None:
            continue
        cells = labels[sl] == k
        area = int(cells.sum())
        if area < min_cells:
            continue
        rr, cc = np.nonzero(cells)
        pts = np.stack([rr - rr.mean(), cc - cc.mean()], axis=1).astype("float64")
        cov = pts.T @ pts / max(area, 1)
        _vals, vecs = np.linalg.eigh(cov)
        proj = pts @ vecs
        ext = proj.max(axis=0) - proj.min(axis=0) + 1.0
        long_e, short_e = float(ext.max()), float(max(ext.min(), 1e-6))
        if long_e / short_e >= 3.0 and area / (long_e * short_e) > 0.75:
            out[sl][cells] = False
    return out


def _match_mean(refill_rgb: np.ndarray, lit_rgb: np.ndarray, fields: dict) -> np.ndarray:
    """Bring each field's mean RGB to its ring's mean RGB (luminance and chromaticity
    together), so a refill sits on the ground round it at 1.00, not 0.85 and cooler."""

    from scipy import ndimage

    if not fields["count"]:
        return refill_rgb
    index = fields["index"]
    out = refill_rgb
    for ch in range(3):
        with np.errstate(invalid="ignore", divide="ignore"):
            field_mean = ndimage.mean(refill_rgb[..., ch], fields["labels"], index)
            ring_mean = ndimage.mean(lit_rgb[..., ch], fields["ring_labels"], index)
        ratio = np.where(
            fields["has_ring"] & (field_mean > 1e-4), ring_mean / np.maximum(field_mean, 1e-4), 1.0
        )
        # A correction on the carry, not the carry itself: the tone runs in from
        # the ring cell by cell, so a field-wide shift past a quarter would only
        # push both ends of a field across two grounds toward their average.
        lut = np.concatenate([[1.0], np.clip(ratio, 0.8, 1.25)]).astype("float32")
        out[..., ch] = out[..., ch] * lut[fields["labels"]]
    return out


def paint_lakes(
    colour_u8: np.ndarray,
    dem: np.ndarray,
    res: float,
    *,
    rgb,
    max_lum: float = 0.1,
    min_area_m2: float = 400.0,
    max_slope_deg: float = 2.0,
    cyan_excess: float | None = None,
    cyan_min_lum: float = 0.35,
    cyan_max_slope_deg: float | None = None,
    flat_rms_m: float | None = None,
    cyan_grow_m: float = 0.0,
    cyan_edge_m: float = 0.0,
    exclude: np.ndarray | None = None,
) -> tuple[np.ndarray, int, np.ndarray]:
    """Flat, near-black blobs in the imagery are water seen at a dark angle: paint them
    the colour the lit lake shows (``rgb``, sRGB), with a little of their own grain.
    With ``cyan_excess`` the flat, bright blobs whose green and blue both stand that
    far above red (a tailings pond in the flight's turquoise) are painted the same."""
    _mem("paint_lakes")

    from scipy import ndimage

    srgb = colour_u8.astype("float32") / 255.0
    lum = srgb.mean(axis=-1)
    gy, gx = np.gradient(ndimage.gaussian_filter(dem.astype("float32"), 2.0), res)
    flat = np.degrees(np.arctan(np.hypot(gx, gy))) < max_slope_deg
    dark = (lum < max_lum) & flat
    if cyan_excess is not None:
        red = srgb[..., 0]
        # A tailings pond's lidar surface is not flat (settled tailings, a berm):
        # its own slope limit, looser than a lake's.
        cyan_flat = flat
        if cyan_max_slope_deg is not None:
            cyan_flat = np.degrees(np.arctan(np.hypot(gx, gy))) < cyan_max_slope_deg
        cyan = (
            (srgb[..., 1] > red + cyan_excess)
            & (srgb[..., 2] > red + cyan_excess)
            & (lum > cyan_min_lum)
            & cyan_flat
        )
        if cyan_grow_m > 0:
            # The shallow edge that fails the excess is the pond too.
            cyan = ndimage.binary_dilation(cyan, iterations=max(1, int(cyan_grow_m / res)))
        dark |= cyan
    del srgb
    if flat_rms_m is not None:
        # A lidar surface flat to the centimetre over a patch this size is water
        # whatever colour the flight gave it (a tarn read as green ground): cells
        # whose 5 m neighbourhood is flat to ``flat_rms_m`` about a 6 m smooth,
        # in patches of ``min_area_m2``, grown back 2 m at the shore.
        resid = dem.astype("float32") - ndimage.gaussian_filter(dem.astype("float32"), 6.0 / res)
        local_rms = np.sqrt(
            ndimage.uniform_filter(resid * resid, size=max(3, int(5.0 / res)), mode="nearest")
        )
        still = (local_rms < flat_rms_m) & (np.degrees(np.arctan(np.hypot(gx, gy))) < 1.5)
        if exclude is not None:
            # A lidar-flat snowfield is not water.
            still &= ~exclude
        lab_s, n_s = ndimage.label(still)
        if n_s:
            idx = np.arange(1, n_s + 1)
            area_s = ndimage.sum(still, lab_s, idx) * res * res
            # And water lies in a hollow: a flat patch whose ground is not under
            # the ground of its own 5-15 m ring by a hand is a bench or a snow
            # surface the lidar saw, not a lake.
            dist_s, (ir, ic) = ndimage.distance_transform_edt(lab_s == 0, return_indices=True)
            ring_s = (dist_s > 5.0 / res) & (dist_s <= 15.0 / res)
            ring_lab = np.where(ring_s, lab_s[ir, ic], 0)
            del dist_s, ir, ic, ring_s
            with np.errstate(invalid="ignore"):
                body_z = ndimage.mean(dem.astype("float32"), lab_s, idx)
                ring_z = ndimage.mean(dem.astype("float32"), ring_lab, idx)
            hollow = np.isfinite(ring_z) & (body_z <= ring_z - 0.05)
            del ring_lab
            water = np.nonzero((area_s >= min_area_m2) & hollow)[0] + 1
            if water.size:
                dark |= ndimage.binary_dilation(
                    np.isin(lab_s, water), iterations=max(1, int(2.0 / res))
                )
        del resid, local_rms, still, lab_s
    labels, count = ndimage.label(dark)
    empty = np.zeros(lum.shape, dtype=bool)
    if not count:
        return colour_u8, 0, empty
    areas = ndimage.sum(dark, labels, np.arange(1, count + 1)) * res * res
    keep = np.isin(labels, np.nonzero(areas >= min_area_m2)[0] + 1)
    if not keep.any():
        return colour_u8, 0, empty
    keep = ndimage.binary_dilation(keep, iterations=1)
    if cyan_excess is not None and cyan_edge_m > 0:
        # The shallow edge of a pond, within ``cyan_edge_m`` of it and still half
        # as turquoise as the pond, is the pond too (a mint ring round a teal disc
        # is neither water nor ground).
        srgb2 = colour_u8.astype("float32") / 255.0
        red2 = srgb2[..., 0]
        edge = (
            (srgb2[..., 1] > red2 + cyan_excess / 2.0)
            & (srgb2[..., 2] > red2 + cyan_excess / 2.0)
            & (lum > cyan_min_lum * 0.8)
            & ndimage.binary_dilation(keep, iterations=max(1, int(cyan_edge_m / res)))
        )
        keep = ndimage.binary_fill_holes(keep | edge)
        del srgb2, red2, edge
    out = colour_u8.astype("float32")
    grain = np.clip(1.0 + 0.5 * (lum[keep] - lum[keep].mean()), 0.7, 1.3)[:, None]
    out[keep] = np.asarray(rgb, dtype="float32")[None, :] * 255.0 * grain
    return np.clip(out, 0, 255).astype("uint8"), int(keep.sum()), keep


def _knee(rgb_255: np.ndarray, start: float = 0.85 * 255.0) -> np.ndarray:
    """A soft knee on sRGB values: what a pull lifts past ``start`` is compressed to
    a third of its excess, so no cell runs to white."""

    # On the brightest channel, so a red shift cannot push red alone over white.
    top = rgb_255.max(axis=-1, keepdims=True)
    scale = np.where(top > start, (start + (top - start) * 0.33) / np.maximum(top, 1e-3), 1.0)
    return rgb_255 * scale.astype("float32")


def pull_layers(
    colour_u8: np.ndarray,
    layer: np.ndarray,
    targets: dict[int, tuple[list[float], float]],
    *,
    texel_m: float = 1.0,
    tapers: dict[int, float] | None = None,
    lum_gate: tuple[float, float] = (0.6, 1.25),
    windows: dict[int, float] | None = None,
    max_br: dict[int, float] | None = None,
    lum_gates: dict[int, tuple[float, float]] | None = None,
) -> tuple[np.ndarray, dict]:
    """Scale each listed layer's colour so its mean moves ``weight`` of the way from
    the photographed mean to the palette base (sRGB), texture untouched: a plateau
    the flight saw as chalk comes to the grey-brown rubble it is, with its grain.
    A layer with a ``tapers`` entry fades its pull in over that many metres inside
    its boundary (no tone step on a contour); cells outside ``lum_gate`` times the
    layer's median luminance (a white spoil field, a black shadow) are left alone."""
    _mem("pull_layers")

    from scipy import ndimage

    out = colour_u8.astype("float32")
    stats = {}
    for lid, (base, weight) in targets.items():
        where = layer == lid
        if where.sum() < 100:
            continue
        mean = out[where].reshape(-1, 3).mean(axis=0) / 255.0
        target = mean * (1.0 - weight) + np.asarray(base, dtype="float64") * weight
        # An additive shift, not a gain: the cells the flat-field already lifted
        # move by the same amount as the rest and nothing runs to white.
        shift = ((target - mean) * 255.0).astype("float32")
        w = where.astype("float32")
        window_m = (windows or {}).get(lid)
        gain = None
        if window_m:
            # Per window, not per layer: one layer-wide shift left a pale corner
            # pale, so each ``window_m`` window's own mean moves ``weight`` of the
            # way to the base. The luminance moves as a gain (an additive shift
            # sized for a chalk window took the brown patches in it to black),
            # the chroma as a shift.
            size = max(8, int(float(window_m) / max(texel_m, 1e-6)))
            den = np.maximum(ndimage.uniform_filter(w, size=size, mode="nearest"), 1e-3)
            local = np.stack(
                [
                    ndimage.uniform_filter(out[..., ch] * w, size=size, mode="nearest") / den
                    for ch in range(3)
                ],
                axis=-1,
            )
            base_255 = np.asarray(base, dtype="float32") * 255.0
            local_lum = np.maximum(local.mean(axis=-1), 1.0)
            wanted_lum = local_lum * (1.0 - weight) + float(base_255.mean()) * weight
            gain = np.clip(wanted_lum / local_lum, 0.5, 1.6).astype("float32")
            chroma_target = base_255 - float(base_255.mean())
            chroma_local = local - local_lum[..., None]
            shift = ((chroma_target[None, None, :] - chroma_local) * weight).astype("float32")
            del den, local, local_lum, wanted_lum, chroma_local
        taper = (tapers or {}).get(lid)
        if taper:
            dist = ndimage.distance_transform_edt(where) * texel_m
            w = np.clip(dist / float(taper), 0.0, 1.0).astype("float32") * w
        lum = out.mean(axis=-1) / 255.0
        med = float(np.median(lum[where]))
        gate = tuple((lum_gates or {}).get(lid, lum_gate))
        w = np.where((lum < gate[0] * med) | (lum > gate[1] * med), 0.0, w)
        br_cap = (max_br or {}).get(lid)
        if br_cap:
            # Only what the flight already shows warm is pulled to the rubble's
            # red: a grey spoil field (blue-to-red 0.9) keeps its grey rather than
            # turning pink at the same luminance.
            br = out[..., 2] / np.maximum(out[..., 0], 1e-3)
            w = np.where(br >= float(br_cap), 0.0, w)
            del br
        sel = w > 0
        if gain is not None:
            g = (1.0 + (gain[sel] - 1.0) * w[sel])[:, None]
            out[sel] = _knee(out[sel] * g + shift[sel] * w[sel][:, None])
        else:
            out[sel] = _knee(out[sel] + shift[None, :] * w[sel][:, None])
        stats[str(int(lid))] = {
            "mean_before": [round(float(v), 3) for v in mean],
            "mean_after": [round(float(v), 3) for v in target],
        }
    return np.clip(out, 0, 255).astype("uint8"), stats


def pull_regions(
    colour_u8: np.ndarray, dem: np.ndarray, regions: list[dict], texel_m: float = 1.0
) -> tuple[np.ndarray, dict]:
    """By elevation band, every layer alike: each ``window_m`` window's luminance is
    brought to the target's (a windowed flat-field, so the summit is not left pale
    because the band's far side is dark), the band's mean colour to the target's
    colour, the grain kept. The summit plateau the flight saw as chalk (rock, refill
    and outcrop together) comes to the tone its photographs show."""
    _mem("pull_regions")

    from scipy import ndimage

    out = colour_u8.astype("float32")
    stats = []
    for region in regions:
        lo = float(region.get("min_elevation", -1e9))
        hi = float(region.get("max_elevation", 1e9))
        weight = float(region.get("weight", 1.0))
        window_px = max(8, int(float(region.get("window_m", 200.0)) / max(texel_m, 1e-6)))
        where = (dem >= lo) & (dem < hi)
        if where.sum() < 100:
            continue
        target = np.asarray(region["target"], dtype="float64")
        target_lum = float(target.mean())
        # The band's edge is feathered over ``elevation_feather_m`` (a 20 m feather
        # drew the 3,780 m contour as a tone seam through every hollow and knoll).
        ef = float(region.get("elevation_feather_m", 20.0))
        feather = np.clip((dem - lo) / ef, 0.0, 1.0) * np.clip((hi - dem) / ef, 0.0, 1.0)
        feather = feather.astype("float32")
        # Windowed luminance: the local mean of the band's own cells.
        lum = out.mean(axis=-1) / 255.0
        w = where.astype("float32")
        local = ndimage.uniform_filter(lum * w, size=window_px, mode="nearest") / np.maximum(
            ndimage.uniform_filter(w, size=window_px, mode="nearest"), 1e-3
        )
        wanted = local * (1.0 - weight) + target_lum * weight
        factor = np.clip(wanted / np.maximum(local, 1e-3), 0.5, 1.6).astype("float32")
        f = 1.0 + (factor - 1.0) * feather
        out = out * f[..., None]
        # Then the colour: the band's mean channel ratios to the target's.
        mean = out[where].reshape(-1, 3).mean(axis=0) / 255.0
        ratio = target / np.maximum(mean, 1e-3)
        ratio = ratio / max(float(ratio.mean()), 1e-3)  # chroma only, luminance is done
        f_rgb = 1.0 + (ratio.astype("float32")[None, None, :] - 1.0) * feather[..., None]
        out = _knee(out * f_rgb)
        after = out[where].reshape(-1, 3).mean(axis=0) / 255.0
        stats.append(
            {
                "min_elevation": lo,
                "cells": int(where.sum()),
                "window_m": float(region.get("window_m", 200.0)),
                "mean_before": [round(float(v), 3) for v in mean],
                "mean_after": [round(float(v), 3) for v in after],
            }
        )
    return np.clip(out, 0, 255).astype("uint8"), stats


def aspect_flatfield(
    colour_u8: np.ndarray,
    dem: np.ndarray,
    res: float,
    layer: np.ndarray,
    layer_ids: list[int],
    *,
    bins: int = 8,
    min_slope_deg: float = 8.0,
    strength: float = 1.0,
    mode: str = "aspect",
    sun: tuple[float, float] | None = None,
    target: str = "mean",
    max_factor: float = 1.8,
    aspect_pass: float = 0.0,
    chroma: bool = False,
    exclude: np.ndarray | None = None,
) -> tuple[np.ndarray, dict]:
    """Equalise the mean brightness of a layer across slope aspects.

    ``exclude`` marks cells the de-lighting refilled (cast shadow, snow, crowns):
    they are already the lit ground's tone, so they neither weigh in a bin's mean
    nor take its factor (a shadow field on a north slope was lifted a second time
    by its bin and shipped a fifth brighter than its ring).

    With ``chroma`` each bin's mean channel shares (red, green and blue over the
    luminance) are brought to the layer's best-lit bins' shares as well, at the
    luminance the bin already has: the sky's lilac on a slope the sun did not reach
    is a chroma the flight baked in exactly as it baked the shade.

    ``target="lit"`` equalises each layer to the mean of its three best-lit bins
    instead of its all-bin mean, so a rock layer the flight lit comes out as its lit
    self (the cream of a sunlit ledge), not as the average of lit and shaded.
    ``aspect_pass`` > 0 adds a final pass binned by compass octant at that strength,
    for what the incidence bins leave.

    ``mode="incidence"`` bins on the cosine of the angle between the ground normal and
    the fitted sun (``sun`` = (azimuth, altitude) in degrees) instead of on aspect: a
    steep north wall and a gentle north slope then share a bin only when they were lit
    alike, which is what the residual the de-lighting left behind depends on.

    Whatever sun the de-lighting could not model (an east wall left 25 % darker than
    its west twin) shows up as a brightness that depends on aspect alone within one
    material; the same rock on a slope faces every way with the same albedo, so each
    aspect bin is scaled (in linear light, chroma untouched) to the layer's mean.
    Bins are interpolated around the circle so no seam appears between them, and the
    factor fades in over the first ten degrees of slope so flats stay as they were.
    """
    _mem("aspect_flatfield")

    from scipy import ndimage

    smooth = ndimage.gaussian_filter(dem.astype("float32"), 2.0)
    gy, gx = np.gradient(smooth, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    aspect = np.arctan2(gx, -gy) % (2 * np.pi)  # 0 = north-facing, clockwise
    ramp = np.clip((slope - min_slope_deg) / 6.0, 0.0, 1.0).astype("float32")
    circular = mode != "incidence"
    if circular:
        key = aspect / (2 * np.pi)  # 0..1 round the compass
    else:
        if sun is None:
            raise ValueError("incidence flat-field needs the fitted sun (azimuth, altitude)")
        az = math.radians(float(sun[0]))
        alt = math.radians(float(sun[1]))
        s = np.array([math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)])
        norm = np.sqrt(gx * gx + gy * gy + 1.0)
        # Rows run south, so the northward slope is -gy.
        incidence = (-gx * s[0] + gy * s[1] + s[2]) / norm
        key = np.clip((incidence + 1.0) / 2.0, 0.0, 1.0)  # 0 = facing away, 1 = facing the sun
    linear = srgb_to_linear(colour_u8)
    lum = linear.mean(axis=-1)
    out = linear.copy()
    stats: dict = {"mode": mode}
    for lid in layer_ids:
        member = (layer == lid) & (slope > min_slope_deg)
        if exclude is not None:
            member &= ~exclude
        if member.sum() < 1000:
            continue
        if circular:
            lo_key, hi_key = 0.0, 1.0
        else:
            # Bins over the whole incidence the layer spans: the steep north faces
            # are a percent of a scree layer and sit alone at the low end, and they
            # are exactly the cells that still carry the sun.
            lo_key, hi_key = np.percentile(key[member], [0.02, 99.98])
            hi_key = max(float(hi_key), float(lo_key) + 1e-3)
        keyn = np.clip((key - lo_key) / (hi_key - lo_key), 0.0, 1.0)
        bin_index = np.minimum((keyn * bins).astype(int), bins - 1)
        where = layer == lid
        if exclude is not None:
            where &= ~exclude
        f_total = np.ones(lum.shape, dtype="float32")
        factors = np.ones(bins)
        means = None
        counts = np.zeros(bins, dtype=int)
        # Two populations, the gentle ground and the faces over 35 degrees, each
        # equalised across its own incidence bins to its own mean: steep tundra may
        # well be a different albedo from the flat, but the sun must not be what
        # tells a north face from a south one. Two passes each: the interpolation
        # between bins with very different factors leaves a residual on the first.
        steep_cells = slope > 35.0
        equalised = [False, False]
        for which, population in enumerate((member & ~steep_cells, member & steep_cells)):
            if population.sum() < 5000:
                continue
            equalised[which] = True
            pop_counts = np.array([int((population & (bin_index == b)).sum()) for b in range(bins)])
            counts = counts + pop_counts
            overall = float(lum[population].mean())
            if target == "lit":
                first = np.array(
                    [
                        float(lum[population & (bin_index == b)].mean())
                        if pop_counts[b] >= 200
                        else np.nan
                        for b in range(bins)
                    ]
                )
                lit_bins = np.sort(first[np.isfinite(first)])[-3:]
                if lit_bins.size:
                    overall = float(lit_bins.mean())
            for _pass in range(2):
                current = (linear * f_total[..., None]).mean(axis=-1)
                pass_means = np.array(
                    [
                        float(current[population & (bin_index == b)].mean())
                        if pop_counts[b] >= 200
                        else np.nan
                        for b in range(bins)
                    ]
                )
                if means is None:
                    means = pass_means
                pass_factors = np.where(
                    np.isfinite(pass_means), overall / np.maximum(pass_means, 1e-4), 1.0
                )
                pass_factors = np.clip(pass_factors, 1.0 / max_factor, max_factor)
                factors = factors * pass_factors
                # Linear interpolation of the bin factors: round the circle for
                # aspect, clamped at the two ends for incidence.
                if circular:
                    pos = (keyn * bins - 0.5) % bins
                    lo = np.floor(pos).astype(int) % bins
                    hi = (lo + 1) % bins
                else:
                    pos = np.clip(keyn * bins - 0.5, 0.0, bins - 1.0)
                    lo = np.floor(pos).astype(int)
                    hi = np.minimum(lo + 1, bins - 1)
                frac = (pos - np.floor(pos)).astype("float32")
                f = pass_factors[lo] * (1 - frac) + pass_factors[hi] * frac
                f = 1.0 + (f - 1.0) * strength * ramp
                f_total = np.where(population, f_total * f.astype("float32"), f_total)
        if means is None:
            continue
        # The passes multiply: it is the whole correction that is clamped, so no
        # bin is lifted or dropped past ``max_factor`` however many passes ran.
        f_total = np.clip(f_total, 1.0 / max_factor, max_factor)
        if aspect_pass > 0 and not circular:
            # What the incidence bins leave (a wall the model lit alike from two
            # sides that the flight did not): one pass round the compass.
            asp = np.minimum((aspect / (2 * np.pi) * 8).astype(int), 7)
            for population in (member & ~steep_cells, member & steep_cells):
                if population.sum() < 5000:
                    continue
                current = (linear * f_total[..., None]).mean(axis=-1)
                a_means = np.array(
                    [
                        float(current[population & (asp == b)].mean())
                        if (population & (asp == b)).sum() >= 200
                        else np.nan
                        for b in range(8)
                    ]
                )
                goal = float(current[population].mean())
                a_factors = np.where(np.isfinite(a_means), goal / np.maximum(a_means, 1e-4), 1.0)
                a_factors = np.clip(a_factors, 1.0 / max_factor, max_factor)
                pos = (aspect / (2 * np.pi) * 8 - 0.5) % 8
                lo = np.floor(pos).astype(int) % 8
                hi = (lo + 1) % 8
                frac = (pos - np.floor(pos)).astype("float32")
                f = a_factors[lo] * (1 - frac) + a_factors[hi] * frac
                f = 1.0 + (f - 1.0) * aspect_pass * ramp
                f_total = np.where(population, f_total * f.astype("float32"), f_total)
            f_total = np.clip(f_total, 1.0 / max_factor, max_factor)
        chroma_gain = None
        if chroma:
            chroma_gain = _chroma_by_bin(
                linear, f_total, member & ~steep_cells, bin_index, keyn, bins, circular, ramp
            )
            f_rgb = f_total[where][:, None] * chroma_gain[where]
            lifted = linear[where] * f_rgb
            del f_rgb, chroma_gain
        else:
            lifted = linear[where] * f_total[where][:, None]
        # A soft knee above 0.7 linear on the brightest channel: nothing the
        # flat-field lifts reaches white in any channel (a knee on the luminance
        # let a red-heavy ledge clip in red while its mean sat under the knee).
        l_lum = lifted.max(axis=-1)
        knee = np.where(l_lum > 0.7, (0.7 + (l_lum - 0.7) * 0.15) / np.maximum(l_lum, 1e-4), 1.0)
        out[where] = lifted * knee[:, None].astype("float32")
        after = out.mean(axis=-1)
        gentle = member & ~steep_cells
        means_after = np.array(
            [
                float(after[gentle & (bin_index == b)].mean())
                if (gentle & (bin_index == b)).sum() >= 200
                else np.nan
                for b in range(bins)
            ]
        )
        finite = means_after[np.isfinite(means_after)]
        steep_member = member & steep_cells
        steep_after = np.array(
            [
                float(after[steep_member & (bin_index == b)].mean())
                if (steep_member & (bin_index == b)).sum() >= 200
                else np.nan
                for b in range(bins)
            ]
        )
        steep_finite = steep_after[np.isfinite(steep_after)]
        clipped = float((out[where].max(axis=-1) >= 0.995).mean()) if where.any() else 0.0
        stats[str(int(lid))] = {
            "clipped_fraction": round(clipped, 5),
            # A spread is reported only for a population that was equalised (5,000
            # cells or more); a cliff layer has almost no gentle cells, a forest
            # floor almost no steep ones.
            "after_spread_steep": round(
                float(steep_finite.max() / max(steep_finite.min(), 1e-4)), 3
            )
            if equalised[1] and steep_finite.size >= 2
            else None,
            "bin_counts": [int(c) for c in counts],
            "key_range": [round(float(lo_key), 3), round(float(hi_key), 3)],
            "bin_means_before": [round(float(v), 3) if np.isfinite(v) else None for v in means],
            "bin_means_after": [
                round(float(v), 3) if np.isfinite(v) else None for v in means_after
            ],
            "after_spread": round(float(finite.max() / max(finite.min(), 1e-4)), 3)
            if equalised[0] and finite.size >= 2
            else None,
            "factors": [round(float(v), 3) for v in factors],
        }
    return linear_to_srgb_u8(out), stats


def _chroma_by_bin(
    linear: np.ndarray,
    f_total: np.ndarray,
    population: np.ndarray,
    bin_index: np.ndarray,
    keyn: np.ndarray,
    bins: int,
    circular: bool,
    ramp: np.ndarray,
) -> np.ndarray:
    """Per-channel gains (n, n, 3) that bring each incidence bin's mean channel shares
    to the shares of the population's three best-lit bins, interpolated between
    bins like the luminance factors and normalised so the luminance is unchanged."""

    if population.sum() < 5000:
        return np.ones(linear.shape, dtype="float32")
    current = linear * f_total[..., None]
    lum = np.maximum(current.mean(axis=-1), 1e-4)
    shares = current / lum[..., None]
    del current
    bin_share = np.full((bins, 3), np.nan)
    bin_lum = np.full(bins, np.nan)
    for b in range(bins):
        cells = population & (bin_index == b)
        if cells.sum() >= 200:
            bin_share[b] = shares[cells].reshape(-1, 3).mean(axis=0)
            bin_lum[b] = float(lum[cells].mean())
    finite = np.isfinite(bin_lum)
    if finite.sum() < 2:
        return np.ones(linear.shape, dtype="float32")
    lit = np.argsort(np.where(finite, bin_lum, -1.0))[-3:]
    lit = [b for b in lit if finite[b]]
    target = bin_share[lit].mean(axis=0)
    gains = np.where(finite[:, None], target[None, :] / np.maximum(bin_share, 1e-3), 1.0)
    gains = np.clip(gains, 0.85, 1.18)
    if circular:
        pos = (keyn * bins - 0.5) % bins
        lo = np.floor(pos).astype(int) % bins
        hi = (lo + 1) % bins
    else:
        pos = np.clip(keyn * bins - 0.5, 0.0, bins - 1.0)
        lo = np.floor(pos).astype(int)
        hi = np.minimum(lo + 1, bins - 1)
    frac = (pos - np.floor(pos)).astype("float32")[..., None]
    g = gains[lo] * (1 - frac) + gains[hi] * frac
    g = 1.0 + (g - 1.0) * ramp[..., None]
    # The luminance stays the bin's own: the gains are renormalised by the cell's
    # share-weighted mean.
    norm = np.maximum((g * shares).mean(axis=-1, keepdims=True), 1e-4)
    del shares, pos, lo, hi, frac
    return np.where(population[..., None], g / norm, 1.0).astype("float32")


def pull_chroma(
    colour_u8: np.ndarray,
    layer: np.ndarray,
    ids: list[int],
    target_br: float,
    window_m: float,
    texel_m: float,
    *,
    tolerance: float = 1.05,
    near_layer: int | None = None,
    within_m: float = 120.0,
    saturation_gain: float = 1.0,
    lum_gate: tuple[float, float] = (0.6, 1.25),
) -> tuple[np.ndarray, int]:
    """On the named layers, where the blue-to-red of a ``window_m`` neighbourhood
    exceeds ``target_br`` by ``tolerance``, scale the chroma so it meets the target,
    luminance untouched (the near-rim ejecta read lilac-grey where every photograph
    has it rust-brown); cells outside ``lum_gate`` times the layers' median luminance
    (a white spoil field) are left alone. With ``near_layer`` the chroma within
    ``within_m`` of that layer is raised by ``saturation_gain``, tapered, so the
    ejecta reads rust beside the rubble. Returns (colour, cells pulled)."""
    _mem("pull_chroma")

    from scipy import ndimage

    on = np.isin(layer, ids)
    if not on.any():
        return colour_u8, 0
    lin = srgb_to_linear(colour_u8)
    win = max(3, int(window_m / texel_m))
    on_f = on.astype("float32")
    # The ratio is read in sRGB (the photographs' and the critic's measure).
    srgb = colour_u8.astype("float32") / 255.0
    br = srgb[..., 2] / np.maximum(srgb[..., 0], 1e-3)
    del srgb
    local = ndimage.uniform_filter(br * on_f, size=win, mode="nearest") / np.maximum(
        ndimage.uniform_filter(on_f, size=win, mode="nearest"), 1e-3
    )
    lum_s = colour_u8.astype("float32").mean(axis=-1) / 255.0
    med = float(np.median(lum_s[on]))
    gated = on & (lum_s >= lum_gate[0] * med) & (lum_s <= lum_gate[1] * med)
    over = gated & (local > tolerance * target_br)
    lum = lin.mean(axis=-1, keepdims=True)
    out = lin.copy()
    if over.any():
        # Scale the blue channel's excess over red down to the target ratio (in
        # linear light the sRGB ratio's scale is raised to 2.2), then put the
        # luminance back.
        k = np.where(over, np.clip(target_br / np.maximum(local, 1e-4), 0.5, 1.0) ** 2.2, 1.0)
        out[..., 2] = lin[..., 2] * k
        out[..., 1] = lin[..., 1] * (0.5 + 0.5 * k)  # green follows blue halfway
        lum2 = out.mean(axis=-1, keepdims=True)
        out = out * (lum / np.maximum(lum2, 1e-4))
        out = np.where(over[..., None], out, lin)
    if near_layer is not None and saturation_gain != 1.0:
        near = layer == near_layer
        if near.any():
            dist = ndimage.distance_transform_edt(~near) * texel_m
            taper = np.clip(1.0 - dist / within_m, 0.0, 1.0) * gated
            # The gain is a shift of the window's mean chroma, the same for every
            # cell in it: a per-cell gain sent the tan soil orange and left the
            # grey Kaibab patches in it grey (an ochre blotch beside mauve ground).
            lum_o = out.mean(axis=-1, keepdims=True)
            chroma = out - lum_o
            g_f = gated.astype("float32")
            den = np.maximum(ndimage.uniform_filter(g_f, size=win, mode="nearest"), 1e-3)
            mean_chroma = np.stack(
                [
                    ndimage.uniform_filter(chroma[..., ch] * g_f, size=win, mode="nearest") / den
                    for ch in range(3)
                ],
                axis=-1,
            )
            shift = mean_chroma * ((saturation_gain - 1.0) * taper)[..., None]
            out = np.clip(out + shift, 0.0, 1.0)
            del chroma, g_f, den, mean_chroma, shift
    return linear_to_srgb_u8(out), int(over.sum())

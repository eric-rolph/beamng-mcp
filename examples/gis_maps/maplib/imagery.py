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


def srgb_to_linear(rgb_u8: np.ndarray) -> np.ndarray:
    c = rgb_u8.astype("float32") / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb_u8(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0.0, 1.0)
    s = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return (s * 255.0).round().astype("uint8")


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

    from scipy import ndimage

    lum = colour_u8.astype("float32").mean(axis=-1)
    smooth = ndimage.gaussian_filter(dem.astype("float64"), 2.0)
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
    k = math.tan(math.radians(altitude_deg)) * res
    m = rotated.shape[1]
    x = np.arange(m, dtype="float32") * k
    # Looking toward the sun means occluders sit at LARGER x. A point x' > x blocks x when
    # h' > h + (x' - x) * tan(alt) * res, i.e. when h' - x'k > h - xk: compare each sample
    # with the suffix maximum of ``h - xk`` over everything sunward of it.
    ray = rotated - x[None, :]
    suffix_max = np.flip(np.maximum.accumulate(np.flip(ray, axis=1), axis=1), axis=1)
    horizon = np.concatenate(
        [suffix_max[:, 1:], np.full((rotated.shape[0], 1), -np.inf, dtype="float32")], axis=1
    )
    lit = (horizon <= ray + 0.05).astype("float32")
    back = ndimage.rotate(lit, -angle, reshape=False, order=1, mode="nearest")
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
    cover_mask: np.ndarray | None = None,
    match_ring: bool = False,
    shadow_dark_ratio: float | None = None,
    canopy_chm: np.ndarray | None = None,
    canopy_refill: float | None = None,
) -> tuple[np.ndarray, dict]:
    """Return the de-lit RGB8 image plus statistics for the handoff.

    ``snow`` (``min_lum``, ``max_chroma`` in sRGB) marks the flight's snowfields and
    refills them like cast shadow, from the ground around them. Cells steeper than
    ``steep_deg`` are refilled only from lit cells that are as steep (a cliff borrows
    from cliffs, not from the scree on its ledges), and with ``steep_cap`` nothing on
    them is lifted past the median of their lit cells; the cap comes in over
    ``steep_feather_deg`` below ``steep_deg`` so it draws no contour. ``knee_lum`` is
    the linear luminance above which the output is compressed so no gain runs to
    white. With ``cover_mask`` (canopy) a refill under a canopy borrows only from the
    canopy round it and one in the open only from open ground; with ``match_ring``
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
    smooth = ndimage.gaussian_filter(dem_r.astype("float64"), 1.0)
    shade = hm.hillshade(smooth, res_r, azimuth_deg, altitude_deg)
    visibility = cast_shadows(smooth, res_r, azimuth_deg, altitude_deg)
    # Sky light is what the shadows see, and a crater floor sees less sky than a plain:
    # scale the ambient term by the openness the AO estimate measures.
    openness = hm.ambient_occlusion(smooth, res_r, radius_px=max(8, int(40 / res_r)))
    sky = ambient * (0.55 + 0.45 * openness)
    illum = sky + (1.0 - sky) * shade * visibility
    flat = ambient + (1.0 - ambient) * math.sin(math.radians(altitude_deg))
    lin = srgb_to_linear(colour_u8)
    # Minnaert-style calibration: the exponent that best explains the photographed
    # luminance from the modelled illumination (fitted on lit, sloping ground) tells how
    # strongly this image actually shades, instead of assuming a Lambertian 1.0.
    lum = lin.mean(axis=-1)
    gy, gx = np.gradient(smooth, res_r)
    grade = np.hypot(gx, gy)
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
        shadow_core |= ndimage.binary_dilation(gap_shadow, iterations=max(1, int(1.0 / res_r)))
        canopy_fill = (chm_r >= 2.0) if canopy_refill is not None else None
        del canopy_vis, gap_shadow, chm_r
    else:
        canopy_fill = None
    if shadow_dark_ratio is not None:
        lum_c = corrected.mean(axis=-1)
        around = ndimage.uniform_filter(lum_c, size=max(3, int(20.0 / res_r)), mode="nearest")
        blob = (lum_c < float(shadow_dark_ratio) * around) & (
            corrected[..., 2] >= corrected[..., 1]
        )
        blob = ndimage.binary_opening(blob, iterations=1)
        shadow_core |= ndimage.binary_dilation(blob, iterations=max(1, int(2.0 / res_r)))
        del lum_c, around, blob

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
        source_w = lit_w * clear
        # A steep cell borrows only from lit steep cells and a gentle one from
        # gentle: a shaded cliff comes back as cliff, not as the scree on its ledges.
        # Under a canopy a gentle cell borrows from the canopy round it and in the
        # open from open ground: a snowfield across a forest edge comes back as
        # forest on the one side and meadow on the other, not the mean of both.
        steep_f = steep.astype("float32")
        gentle_w = source_w * (1.0 - steep_f)
        if cover is None:
            local = neighbourhood(gentle_w)
        elif canopy_fill is not None:
            # The crowns are targets, not sources: every gentle cell borrows from
            # the open ground, and a crown takes it at the duff's darkening.
            local = neighbourhood(gentle_w * (1.0 - cover.astype("float32")))
            local = np.where(canopy_fill[..., None], local * float(canopy_refill), local)
        else:
            cover_f = cover.astype("float32")
            local = np.where(
                cover[..., None],
                neighbourhood(gentle_w * cover_f),
                neighbourhood(gentle_w * (1.0 - cover_f)),
            )
            del cover_f
        local = np.where(steep[..., None], neighbourhood(source_w * steep_f), local).astype(
            "float32"
        )
        del gentle_w
        blur = max(16, int(12 / res_r))
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
            1.0 + shadow_texture_gain * (own_l / np.maximum(own_mean, 1e-4) - 1.0), 0.5, 1.15
        )
        source = source_w > 0.9
        base_l = ndimage.uniform_filter(own_l, size=blur, mode="nearest")
        hp = np.clip(own_l / np.maximum(base_l, 1e-4), 0.6, 1.15)
        del base_l
        if cover is None:
            snow_tex = _propagate(hp, source & clear, snow_now, res_r, rng_seed=5)
        else:
            snow_tex = _propagate(
                hp, source & clear & cover, snow_now & cover, res_r, rng_seed=5
            ) * _propagate(hp, source & clear & ~cover, snow_now & ~cover, res_r, rng_seed=6)
        texture = np.where(snow_now, snow_tex, own_tex)
        del snow_tex
        fields = None
        if match_ring:
            fields = _ring_fields(shadow_core | snow_now, source, res_r)
            texture = _match_amplitude(texture, hp, fields)
        del hp
        recoloured = local * texture[..., None]
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
        return result, local, fill_w

    grain_ratios: list[np.ndarray] = []
    out, local_lit, _fill_w = refill(snow_mask)
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
            out, local_lit, _fill_w = refill(snow_mask)
    # No black holes: whatever a refill or a cap left near zero takes a third of
    # the lit neighbourhood instead.
    dark = out.mean(axis=-1) < 0.02
    out = np.where(dark[..., None], local_lit * 0.35, out)
    # And a relative floor: nothing sits under a quarter of the lit neighbourhood's
    # luminance (the shaded side of a spruce crown is near black in the flight, and
    # a base seen between the trunks is ground, not a black blotch). Such a cell
    # takes the lit neighbourhood's colour at the floor's luminance. The reference
    # is the lit neighbourhood, not a window mean a wide blob would drag down.
    lum_o = out.mean(axis=-1)
    lit_l = np.maximum(local_lit.mean(axis=-1), 1e-4)
    under = lum_o < 0.25 * lit_l
    out = np.where(under[..., None], local_lit * 0.25, out)
    del lum_o, under, lit_l
    # No sky on the walls: a steep cell bluer than the lit ground around it takes
    # that ground's chroma at its own luminance.
    lit_mean = np.maximum(local_lit.mean(axis=-1, keepdims=True), 1e-4)
    lit_ratio = local_lit / lit_mean
    own_br = out[..., 2] / np.maximum(out[..., 0], 1e-4)
    lit_br = lit_ratio[..., 2] / np.maximum(lit_ratio[..., 0], 1e-4)
    blue = steep & (out[..., 2] > 0.95 * out[..., 0]) & (own_br > 1.05 * lit_br)
    del own_br, lit_br
    out = np.where(blue[..., None], out.mean(axis=-1, keepdims=True) * lit_ratio, out)
    del lit_mean, lit_ratio, blue
    cap_lum = None
    if steep_cap:
        # Nothing on a steep face is lifted past what its lit faces measure: the
        # gain that brings a shaded wall back must not make it paler than a lit one.
        lit_steep = steep & (visibility > 0.9) & (shade > 0.5) & ~snow_mask
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
    stats = {
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
    }
    return linear_to_srgb_u8(out), stats


def layer_colour_stats(
    colour_u8: np.ndarray, layer: np.ndarray, materials: list[str]
) -> dict[str, list[float]]:
    """Mean linear RGB of the imagery under each terrain layer (for detail-tint matching)."""

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
    its ring has in the same band, measured over the field's interior (4 m in from
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
    interior = ndimage.binary_erosion(labels > 0, iterations=max(1, int(4.0 / res_m)))
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
    correction = np.zeros(lum.shape, dtype="float32")
    for band, cap in ((fine, 3.0), (mid, 4.0)):
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
        lut = np.concatenate([[1.0], np.clip(ratio, 0.5, 2.0)]).astype("float32")
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
) -> tuple[np.ndarray, int]:
    """Flat, near-black blobs in the imagery are water seen at a dark angle: paint them
    the colour the lit lake shows (``rgb``, sRGB), with a little of their own grain.
    With ``cyan_excess`` the flat, bright blobs whose green and blue both stand that
    far above red (a tailings pond in the flight's turquoise) are painted the same."""

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
        dark |= (
            (srgb[..., 1] > red + cyan_excess)
            & (srgb[..., 2] > red + cyan_excess)
            & (lum > cyan_min_lum)
            & cyan_flat
        )
    del srgb
    labels, count = ndimage.label(dark)
    if not count:
        return colour_u8, 0
    areas = ndimage.sum(dark, labels, np.arange(1, count + 1)) * res * res
    keep = np.isin(labels, np.nonzero(areas >= min_area_m2)[0] + 1)
    if not keep.any():
        return colour_u8, 0
    keep = ndimage.binary_dilation(keep, iterations=1)
    out = colour_u8.astype("float32")
    grain = np.clip(1.0 + 0.5 * (lum[keep] - lum[keep].mean()), 0.7, 1.3)[:, None]
    out[keep] = np.asarray(rgb, dtype="float32")[None, :] * 255.0 * grain
    return np.clip(out, 0, 255).astype("uint8"), int(keep.sum())


def _knee(rgb_255: np.ndarray, start: float = 0.85 * 255.0) -> np.ndarray:
    """A soft knee on sRGB values: what a pull lifts past ``start`` is compressed to
    a third of its excess, so no cell runs to white."""

    # On the brightest channel, so a red shift cannot push red alone over white.
    top = rgb_255.max(axis=-1, keepdims=True)
    scale = np.where(top > start, (start + (top - start) * 0.33) / np.maximum(top, 1e-3), 1.0)
    return rgb_255 * scale.astype("float32")


def pull_layers(
    colour_u8: np.ndarray, layer: np.ndarray, targets: dict[int, tuple[list[float], float]]
) -> tuple[np.ndarray, dict]:
    """Scale each listed layer's colour so its mean moves ``weight`` of the way from
    the photographed mean to the palette base (sRGB), texture untouched: a plateau
    the flight saw as chalk comes to the grey-brown rubble it is, with its grain."""

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
        out[where] = _knee(out[where] + shift[None, :])
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
        feather = np.clip((dem - lo) / 20.0, 0.0, 1.0) * np.clip((hi - dem) / 20.0, 0.0, 1.0)
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
) -> tuple[np.ndarray, dict]:
    """Equalise the mean brightness of a layer across slope aspects.

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

    from scipy import ndimage

    smooth = ndimage.gaussian_filter(dem.astype("float64"), 2.0)
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
        lifted = linear[where] * f_total[where][:, None]
        # A soft knee above 0.7 linear: nothing the flat-field lifts reaches white.
        l_lum = lifted.mean(axis=-1)
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

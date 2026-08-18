"""Resource icon for the beamng.com listing (96 x 96 PNG).

A 96 px badge is far too small to survive a downscaled render of the
building - the louvers alias into mush and the marquee is illegible. So
this is drawn: a head-on stylisation of the real elevation (white flowing
canopy, copper louvered drum, dark entrance mouth, hazard ramp) with an
amber spin arc, supersampled 8x and box-filtered down.

Run:  ./.venv/Scripts/python.exe \
        examples/giant_props/gforce_centrifuge/authoring/make_resource_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 8
OUT = 96
S = OUT * SS
C = S / 2.0

# Palette lifted from the shipped materials so the icon reads as the mod.
STEEL_TOP = (44, 52, 62)
STEEL_BOT = (22, 26, 32)
COPPER = (146, 79, 50)
COPPER_LIT = (178, 104, 66)
SLAT = (74, 38, 25)
CANOPY = (236, 238, 240)
CANOPY_SHADE = (188, 194, 200)
MOUTH = (16, 19, 24)
AMBER = (255, 168, 40)
HAZ_Y = (228, 172, 26)
HAZ_K = (26, 26, 28)
RIM = (198, 122, 74)


def _px(v: float) -> float:
    """Fraction of the icon (0..1) -> supersampled pixels."""
    return v * S


def main() -> None:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- circular badge with a vertical steel gradient ------------------
    grad = Image.new("RGB", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.point((0, y), tuple(
            int(STEEL_TOP[i] + (STEEL_BOT[i] - STEEL_TOP[i]) * t)
            for i in range(3)))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(
        [_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)], fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # --- amber spin arrow: the machine's one job -----------------------
    ring = [_px(0.078), _px(0.078), S - _px(0.078), S - _px(0.078)]
    d.arc(ring, start=196, end=300, fill=AMBER + (170,), width=int(_px(0.026)))
    d.arc(ring, start=210, end=300, fill=AMBER + (255,), width=int(_px(0.026)))
    # arrowhead on the leading (clockwise) end of the sweep
    ar = C - _px(0.078) - _px(0.013)
    aa = math.radians(300)
    hx, hy = C + ar * math.cos(aa), C + ar * math.sin(aa)
    tx, ty = -math.sin(aa), math.cos(aa)
    nx, ny = math.cos(aa), math.sin(aa)
    hl, hw = _px(0.058), _px(0.031)
    d.polygon([(hx + tx * hl, hy + ty * hl),
               (hx - nx * hw, hy - ny * hw),
               (hx + nx * hw, hy + ny * hw)], fill=AMBER + (255,))

    # --- flowing canopy roof ------------------------------------------
    # Wide flattened dome; the real shell is a white swoop over the drum.
    cx = C
    roof_y = _px(0.315)
    roof_half = _px(0.405)
    dome = _px(0.085)
    pts = []
    steps = 64
    for i in range(steps + 1):
        t = i / steps
        x = cx - roof_half + 2.0 * roof_half * t
        # flattened cosine dome, wider than tall
        y = roof_y - dome * math.cos((t - 0.5) * math.pi) ** 0.7
        pts.append((x, y))
    pts += [(cx + roof_half, roof_y + _px(0.055)),
            (cx - roof_half, roof_y + _px(0.055))]
    d.polygon(pts, fill=CANOPY)
    # underside shadow band so the roof reads as a solid slab
    d.polygon([(cx - roof_half, roof_y + _px(0.030)),
               (cx + roof_half, roof_y + _px(0.030)),
               (cx + roof_half, roof_y + _px(0.055)),
               (cx - roof_half, roof_y + _px(0.055))], fill=CANOPY_SHADE)

    # --- copper louvered drum ------------------------------------------
    band_top = roof_y + _px(0.055)
    band_bot = _px(0.735)
    half = _px(0.385)
    d.rectangle([cx - half, band_top, cx + half, band_bot], fill=COPPER)
    # lit left flank -> the drum is round, not a flat wall
    d.rectangle([cx - half, band_top, cx - half + _px(0.075), band_bot],
                fill=COPPER_LIT)
    d.rectangle([cx + half - _px(0.055), band_top, cx + half, band_bot],
                fill=SLAT)

    # vertical louver slats
    n = 17
    for i in range(n):
        t = (i + 0.5) / n
        x = cx - half + 2.0 * half * t
        # skip the slats the entrance would eat
        if abs(x - cx) < _px(0.115):
            continue
        d.rectangle([x - _px(0.010), band_top + _px(0.020),
                     x + _px(0.010), band_bot - _px(0.020)], fill=SLAT)

    # --- entrance mouth -------------------------------------------------
    mw = _px(0.105)
    mouth_top = band_top + _px(0.045)
    d.rectangle([cx - mw, mouth_top, cx + mw, band_bot], fill=MOUTH)
    d.pieslice([cx - mw, mouth_top - mw * 0.9, cx + mw, mouth_top + mw * 0.9],
               start=180, end=360, fill=MOUTH)
    # Amber throat glow: the drum is lit and running. Stacked rectangles
    # of rising warmth read as a gradient once the 8x buffer comes down.
    glow_h = _px(0.115)
    layers = 12
    for i in range(layers):
        t = i / (layers - 1)
        y0 = band_bot - glow_h * (1.0 - t)
        y1 = band_bot - glow_h * (1.0 - t) + glow_h / layers + _px(0.004)
        w = mw * (0.50 + 0.34 * t)
        col = tuple(int(MOUTH[k] + (AMBER[k] - MOUTH[k]) * (t ** 1.6))
                    for k in range(3))
        d.rectangle([cx - w, y0, cx + w, y1], fill=col)

    # --- hazard ramp ----------------------------------------------------
    ramp_top = band_bot
    ramp_bot = _px(0.885)
    top_half = mw * 1.02
    bot_half = _px(0.225)
    ramp = [(cx - top_half, ramp_top), (cx + top_half, ramp_top),
            (cx + bot_half, ramp_bot), (cx - bot_half, ramp_bot)]
    d.polygon(ramp, fill=HAZ_Y)

    # black chevrons, clipped to the ramp trapezoid
    stripes = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    step = _px(0.055)
    x = -S
    while x < 2 * S:
        sd.polygon([(x, 0), (x + step * 0.5, 0),
                    (x + step * 0.5 + S, S), (x + S, S)], fill=HAZ_K + (255,))
        x += step
    rmask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(rmask).polygon(ramp, fill=255)
    img.paste(stripes, (0, 0), Image.composite(
        rmask, Image.new("L", (S, S), 0), rmask))
    d = ImageDraw.Draw(img)

    # --- badge rim -------------------------------------------------------
    d.ellipse([_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)],
              outline=RIM, width=int(_px(0.022)))

    # --- resolve ---------------------------------------------------------
    # Clip everything back inside the badge, then box-filter down.
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    out = out.filter(ImageFilter.GaussianBlur(radius=SS * 0.18))
    out = out.resize((OUT, OUT), Image.LANCZOS)

    dest = Path(__file__).resolve().parent / "resource_icon_96.png"
    out.save(dest)
    big = Path(__file__).resolve().parent / "resource_icon_preview_384.png"
    Image.open(dest).resize((384, 384), Image.NEAREST).save(big)
    print(f"wrote {dest} ({out.size[0]}x{out.size[1]})")
    print(f"wrote {big} (4x preview)")


if __name__ == "__main__":
    main()

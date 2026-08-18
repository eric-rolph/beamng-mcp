"""Resource icon for the beamng.com listing (96 x 96 PNG).

A 96 px badge cannot survive a downscaled render of this machine: the
lattice derrick turns to grey noise and the plank reads as a stick. So
the icon is drawn instead - a side elevation of the one idea the mod
sells, in the shipped palette so it reads as the same object:

    car on the low end, forty tons about to land on the high end.

Everything is laid out in fractions of the icon, drawn 8x, then box
filtered down. Run:

    ./.venv/Scripts/python.exe \
        examples/giant_props/catapult_seesaw/authoring/make_resource_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 8
OUT = 96
S = OUT * SS
C = S / 2.0

# Palette eyeballed off the shipped renders rather than the linear
# material colours - the texture families modulate those a long way, and
# what matters is that the badge matches what the player sees in game.
SKY_TOP = (132, 160, 188)
SKY_BOT = (54, 66, 82)
RED = (198, 44, 34)
RED_DARK = (132, 26, 20)
WOOD = (158, 104, 58)
WOOD_LIT = (188, 132, 80)
WOOD_DARK = (104, 64, 34)
IRON = (30, 31, 34)
IRON_LIT = (62, 64, 68)
WHITE = (240, 240, 237)
AMBER = (255, 176, 48)
CAR = (206, 214, 222)
CAR_DARK = (128, 140, 152)


def _px(v: float) -> float:
    """Fraction of the icon (0..1) -> supersampled pixels."""
    return v * S


def _rot_rect(cx, cy, half_len, half_thick, ang):
    """Corners of a rectangle centred at (cx, cy), rotated by ang."""
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for dx, dy in ((-half_len, -half_thick), (half_len, -half_thick),
                   (half_len, half_thick), (-half_len, half_thick)):
        out.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
    return out


def main() -> None:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # --- badge: vertical sky gradient ----------------------------------
    grad = Image.new("RGB", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.point((0, y), tuple(
            int(SKY_TOP[i] + (SKY_BOT[i] - SKY_TOP[i]) * t) for i in range(3)))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(
        [_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)], fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # Plank geometry: car end LOW on the left, weight end HIGH on the
    # right - the machine's rest pose, and the pose the story starts in.
    ang = math.radians(-15.0)
    pcx, pcy = _px(0.500), _px(0.640)
    half_len, half_thick = _px(0.345), _px(0.038)

    # --- launch trail: where the car is about to go --------------------
    # PIL's arc() cannot taper and its bounding box has to run mostly
    # off-canvas to get this sweep, which left nothing but the arrowhead
    # inside the badge. A Bezier swept with a shrinking width draws the
    # comet trail directly, and drawing it BEFORE the car lets the car
    # cover its base so it reads as coming off the roof.
    p0, p1, p2 = (0.262, 0.556), (0.128, 0.452), (0.170, 0.196)
    left, right = [], []
    steps = 48
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        bx = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        by = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        tx = 2 * u * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
        ty = 2 * u * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
        norm = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / norm, tx / norm
        w = (0.030 * (1.0 - t) + 0.009 * t) / 2.0
        left.append((_px(bx + nx * w), _px(by + ny * w)))
        right.append((_px(bx - nx * w), _px(by - ny * w)))
    d.polygon(left + right[::-1], fill=AMBER + (215,))
    # arrowhead, aimed along the tangent at the tip
    tipx, tipy = _px(p2[0]), _px(p2[1])
    tx = p2[0] - p1[0]
    ty = p2[1] - p1[1]
    norm = math.hypot(tx, ty) or 1.0
    tx, ty = tx / norm, ty / norm
    hl, hw = _px(0.072), _px(0.040)
    d.polygon([(tipx + tx * hl, tipy + ty * hl),
               (tipx - ty * hw, tipy + tx * hw),
               (tipx + ty * hw, tipy - tx * hw)], fill=AMBER + (255,))

    # --- fulcrum ---------------------------------------------------------
    apex_y = pcy + _px(0.030)
    d.polygon([(C, apex_y - _px(0.020)),
               (C - _px(0.105), _px(0.855)),
               (C + _px(0.105), _px(0.855))], fill=RED)
    d.polygon([(C, apex_y - _px(0.020)),
               (C - _px(0.105), _px(0.855)),
               (C - _px(0.030), _px(0.855))], fill=RED_DARK)
    d.rectangle([C - _px(0.150), _px(0.855), C + _px(0.150), _px(0.900)],
                fill=(196, 198, 200))

    # --- plank ------------------------------------------------------------
    d.polygon(_rot_rect(pcx, pcy, half_len, half_thick, ang), fill=WOOD)
    # lit top face + a shadowed belly, so it reads as a solid timber
    d.polygon(_rot_rect(pcx, pcy - half_thick * 0.60, half_len,
                        half_thick * 0.40, ang), fill=WOOD_LIT)
    d.polygon(_rot_rect(pcx, pcy + half_thick * 0.72, half_len,
                        half_thick * 0.28, ang), fill=WOOD_DARK)
    # steel end bands
    for end in (-1, 1):
        bx = pcx + end * (half_len - _px(0.030)) * math.cos(ang)
        by = pcy + end * (half_len - _px(0.030)) * math.sin(ang)
        d.polygon(_rot_rect(bx, by, _px(0.016), half_thick * 1.12, ang),
                  fill=(150, 158, 165))

    # --- the forty-ton weight, hanging over the high end ------------------
    wx = pcx + (half_len - _px(0.075)) * math.cos(ang)
    wy = pcy + (half_len - _px(0.075)) * math.sin(ang) - _px(0.150)
    ww, wh = _px(0.130), _px(0.098)
    # inverted frustum, like the real casting
    d.polygon([(wx - ww, wy - wh), (wx + ww, wy - wh),
               (wx + ww * 0.72, wy + wh), (wx - ww * 0.72, wy + wh)],
              fill=IRON)
    d.polygon([(wx - ww, wy - wh), (wx - ww + _px(0.030), wy - wh),
               (wx - ww * 0.72 + _px(0.026), wy + wh),
               (wx - ww * 0.72, wy + wh)], fill=IRON_LIT)
    # the "40 TON" line, as a legible bar rather than unreadable glyphs
    d.rectangle([wx - _px(0.070), wy - _px(0.022),
                 wx + _px(0.070), wy + _px(0.004)], fill=WHITE)
    # lifting lug + the two fall dashes above it
    d.rectangle([wx - _px(0.014), wy - wh - _px(0.030),
                 wx + _px(0.014), wy - wh], fill=IRON_LIT)
    for i, dy in enumerate((0.060, 0.115)):
        half_w = _px(0.011 - i * 0.003)
        d.rectangle([wx - half_w, wy - wh - _px(dy + 0.052),
                     wx + half_w, wy - wh - _px(dy + 0.014)],
                    fill=WHITE + (170 - i * 60,))

    # --- the car, parked on the low end -----------------------------------
    cx2 = pcx - (half_len - _px(0.105)) * math.cos(ang)
    cy2 = pcy - (half_len - _px(0.105)) * math.sin(ang) - _px(0.052)
    bw, bh = _px(0.088), _px(0.026)
    d.polygon(_rot_rect(cx2, cy2, bw, bh, ang), fill=CAR)
    # cabin
    ca, sa = math.cos(ang), math.sin(ang)
    roof = []
    for dx, dy in ((-bw * 0.52, -bh), (bw * 0.30, -bh),
                   (bw * 0.14, -bh * 2.5), (-bw * 0.34, -bh * 2.5)):
        roof.append((cx2 + dx * ca - dy * sa, cy2 + dx * sa + dy * ca))
    d.polygon(roof, fill=CAR_DARK)
    for dx in (-bw * 0.56, bw * 0.56):
        wxx = cx2 + dx * ca - bh * sa
        wyy = cy2 + dx * sa + bh * ca
        d.ellipse([wxx - _px(0.020), wyy - _px(0.020),
                   wxx + _px(0.020), wyy + _px(0.020)], fill=IRON)

    # --- rim ---------------------------------------------------------------
    d.ellipse([_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)],
              outline=RED, width=int(_px(0.024)))

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    out = out.filter(ImageFilter.GaussianBlur(radius=SS * 0.18))
    out = out.resize((OUT, OUT), Image.LANCZOS)

    here = Path(__file__).resolve().parent
    dest = here / "resource_icon_96.png"
    out.save(dest)
    big = here / "resource_icon_preview_384.png"
    Image.open(dest).resize((384, 384), Image.NEAREST).save(big)
    print(f"wrote {dest} ({out.size[0]}x{out.size[1]})")
    print(f"wrote {big} (4x preview)")


if __name__ == "__main__":
    main()

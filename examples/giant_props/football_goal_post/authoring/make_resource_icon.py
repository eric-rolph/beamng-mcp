"""Resource icon for the beamng.com listing (96 x 96 PNG).

THE COMPOSITE-OR-DRAW CALL, and this prop lands on the other side of it
from the boot. The rule from the boot's badge is that you composite the
real mesh when the subject is one big high-contrast form whose details
survive a downscale, and draw it when they do not. A goal post is a big
form made entirely of THIN LINES: the crossbar is a 5 in tube on an 18 ft
6 in span, so at 96 px across it is 1.6 pixels wide, and the uprights are
narrower still. A render of it downscales to grey haze on grey haze.

So the badge is drawn, at deliberately unreal stroke widths — the goal
post as a pictogram rather than as a photograph. Everything else is the
mod's own palette, taken from the shipped materials: safety yellow, the
blue pad, the mown turf, the red directional flags.

Run (no dependency on the Blender generator — nothing is composited):

    ./.venv/Scripts/python.exe \
        examples/giant_props/football_goal_post/authoring/make_resource_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 8
OUT = 96
S = OUT * SS

# Palette lifted from spec.PALETTE so the badge reads as the mod.
SKY_TOP = (74, 106, 140)
SKY_BOT = (150, 178, 196)
TURF = (34, 78, 30)
TURF_DARK = (24, 58, 22)
CHALK = (226, 232, 226)
YELLOW = (238, 178, 12)
YELLOW_LIT = (255, 208, 62)
YELLOW_DARK = (176, 126, 6)
PAD_BLUE = (34, 46, 118)
PAD_LIT = (62, 78, 158)
FLAG_RED = (188, 42, 36)
RIM = (28, 34, 30)


def _px(v: float) -> float:
    """Fraction of the icon (0..1) -> supersampled pixels."""
    return v * S


def _pt(x: float, y: float) -> tuple[float, float]:
    return (_px(x), _px(y))


def _bar(draw, x0, y0, x1, y1, width, body, lit):
    """A painted tube: the colour, plus a thin lit edge along one side.

    One highlight line is the whole difference between a flat stick and a
    round pipe at this size — there is no room for a gradient.
    """

    draw.line([_pt(x0, y0), _pt(x1, y1)], fill=body, width=int(_px(width)))
    inset = width * 0.28
    if abs(x1 - x0) < abs(y1 - y0):          # upright: highlight the left
        draw.line([_pt(x0 - inset, y0), _pt(x1 - inset, y1)],
                  fill=lit, width=int(_px(width * 0.26)))
    else:                                     # crossbar: highlight the top
        draw.line([_pt(x0, y0 - inset), _pt(x1, y1 - inset)],
                  fill=lit, width=int(_px(width * 0.26)))


def main() -> None:
    here = Path(__file__).resolve().parent
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # --- circular badge: sky over turf -----------------------------------
    horizon = 0.660
    grad = Image.new("RGB", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        if t < horizon:
            k = t / horizon
            gd.point((0, y), tuple(
                int(SKY_TOP[i] + (SKY_BOT[i] - SKY_TOP[i]) * k) for i in range(3)))
        else:
            k = (t - horizon) / (1.0 - horizon)
            gd.point((0, y), tuple(
                int(TURF[i] + (TURF_DARK[i] - TURF[i]) * k) for i in range(3)))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(
        [_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)], fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # Mown stripes and a hash line: three strokes that say "football field"
    # and stop the lower third reading as a plain green wedge.
    #
    # ImageDraw does NOT blend — it writes the RGBA tuple straight into the
    # pixel — so anything meant to be translucent has to be drawn on its own
    # layer and composited. Drawn directly, these came out as hard white
    # bands, a barcode across the turf.
    turf_fx = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    fx = ImageDraw.Draw(turf_fx)
    for y0, y1 in ((0.700, 0.762), (0.830, 0.902)):
        fx.rectangle([_pt(0.0, y0), _pt(1.0, y1)], fill=CHALK + (24,))
    fx.line([_pt(0.10, 0.934), _pt(0.90, 0.934)],
            fill=CHALK + (110,), width=int(_px(0.014)))
    img = Image.alpha_composite(img, turf_fx)
    d = ImageDraw.Draw(img)

    # --- the goal post ----------------------------------------------------
    # Straight on, filling the badge. Stroke widths are ~5x scale: at 96 px
    # the honest 5 in tube is under two pixels and simply is not there.
    crossbar_y = 0.545
    upright_w = 0.062
    # The uprights stop at y 0.125, not 0.085: the badge is a CIRCLE, and at
    # 0.085 its half-width is 0.279, so an upright at x 0.215 was being cut
    # off by the rim mask instead of standing inside it.
    for x in (0.215, 0.785):
        _bar(d, x, 0.128, x, crossbar_y, upright_w, YELLOW, YELLOW_LIT)
    _bar(d, 0.180, crossbar_y, 0.820, crossbar_y, 0.058, YELLOW, YELLOW_LIT)
    # End caps: the stamped discs, and the reason the bar reads as capped
    # rather than sawn off.
    for x in (0.180, 0.820):
        r = 0.040
        d.ellipse([_pt(x - r, crossbar_y - r), _pt(x + r, crossbar_y + r)],
                  fill=YELLOW, outline=YELLOW_DARK, width=int(_px(0.008)))

    # Directional flags at the tips.
    for x, flip in ((0.215, 1.0), (0.785, -1.0)):
        d.polygon(_poly_flag(x, flip), fill=FLAG_RED)

    # --- gooseneck and pedestal -------------------------------------------
    # The offset pedestal is what makes this a GOOSENECK post rather than a
    # pair of poles in the ground, so it gets real weight in the badge.
    d.line([_pt(0.500, crossbar_y + 0.006), _pt(0.500, 0.605),
            _pt(0.520, 0.650), _pt(0.520, 0.700)],
           fill=YELLOW, width=int(_px(0.052)), joint="curve")
    _bar(d, 0.520, 0.690, 0.520, 0.905, 0.100, PAD_BLUE, PAD_LIT)
    # Strap bands across the pad.
    for y in (0.745, 0.815, 0.880):
        d.line([_pt(0.470, y), _pt(0.570, y)],
               fill=(16, 16, 20, 235), width=int(_px(0.016)))

    # Contact shadow so the pad sits on the turf.
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [_pt(0.430, 0.885), _pt(0.615, 0.935)], fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=SS * 1.4))
    base = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(base)
    _bar(d, 0.520, 0.690, 0.520, 0.905, 0.100, PAD_BLUE, PAD_LIT)
    for y in (0.745, 0.815, 0.880):
        d.line([_pt(0.470, y), _pt(0.570, y)],
               fill=(16, 16, 20, 235), width=int(_px(0.016)))

    # --- badge rim ---------------------------------------------------------
    d.ellipse([_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)],
              outline=RIM, width=int(_px(0.026)))

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    out = out.filter(ImageFilter.GaussianBlur(radius=SS * 0.16))
    out = out.resize((OUT, OUT), Image.LANCZOS)

    dest = here / "resource_icon_96.png"
    out.save(dest)
    big = here / "resource_icon_preview_384.png"
    Image.open(dest).resize((384, 384), Image.NEAREST).save(big)
    print(f"wrote {dest} ({out.size[0]}x{out.size[1]})")
    print(f"wrote {big} (4x preview)")


def _poly_flag(x, flip):
    """The 4 in x 42 in directional flag streaming off an upright tip."""

    return [
        _pt(x, 0.135),
        _pt(x + flip * 0.100, 0.159),
        _pt(x + flip * 0.095, 0.190),
        _pt(x, 0.170),
    ]


if __name__ == "__main__":
    main()

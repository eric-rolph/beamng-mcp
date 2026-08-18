"""Resource icon for the beamng.com listing (96 x 96 PNG).

The centrifuge badge had to be drawn from scratch — a 96 px downscale of a
whole building aliases into mush. A boot is the opposite case: one big
high-contrast form whose read-me details (lug row, collar roll, lace
tongue) survive the downscale intact. So this composites the real mesh.

`icon_source_boot.png` is written by the Blender generator
(`render_icon_source` in blender/create_boot_of_doom.py): the boot alone,
cocked 16 degrees on its hinge, orthographic side-on, on transparency. The
badge, the kick pad, the red X and the punt streaks are drawn around it,
supersampled 8x and box-filtered down.

Run (after the generator, so the source render is current):

    ./.venv/Scripts/python.exe \
        examples/giant_props/boot_of_doom/authoring/make_resource_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 8
OUT = 96
S = OUT * SS

# Palette lifted from the shipped materials so the badge reads as the mod.
SHOP_TOP = (48, 43, 38)
SHOP_BOT = (25, 22, 20)
PAD = (62, 64, 67)
PAD_EDGE = (206, 208, 210)
RED = (198, 56, 48)
AMBER = (255, 172, 48)
RIM = (172, 104, 62)

# Where the boot sits in the badge. The source render is square with the
# boot centred, so this is a scale plus an offset, both in icon fractions.
BOOT_SCALE = 0.86
BOOT_OFFSET = (0.0, -0.050)


def _px(v: float) -> float:
    """Fraction of the icon (0..1) -> supersampled pixels."""
    return v * S


def _pt(x: float, y: float) -> tuple[float, float]:
    return (_px(x), _px(y))


def _poly(points):
    return [_pt(x, y) for x, y in points]


def main() -> None:
    here = Path(__file__).resolve().parent
    source_path = here / "icon_source_boot.png"
    if not source_path.is_file():
        raise SystemExit(
            f"missing {source_path.name} — run the Blender generator first"
        )

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # --- circular badge, dark leather-shop gradient ----------------------
    grad = Image.new("RGB", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.point((0, y), tuple(
            int(SHOP_TOP[i] + (SHOP_BOT[i] - SHOP_TOP[i]) * t)
            for i in range(3)))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(
        [_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)], fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # --- kick pad: the painted X, drawn BEHIND the boot ------------------
    # The sole crops the top of the X, which is what selling the mod needs:
    # the boot is standing over the mark, about to punt whatever parks on it.
    pad = [(0.060, 0.735), (0.940, 0.735), (1.010, 0.960), (-0.010, 0.960)]
    d.polygon(_poly(pad), fill=PAD)
    # Faint front lip only. A bright full-width edge here reads as a horizon
    # and the boot ends up levitating over a shelf.
    d.line([_pt(0.300, 0.735), _pt(0.760, 0.735)],
           fill=PAD_EDGE + (60,), width=int(_px(0.008)))
    xw = int(_px(0.050))
    for (x0, y0), (x1, y1) in (((0.330, 0.782), (0.660, 0.916)),
                               ((0.680, 0.782), (0.350, 0.916))):
        d.line([_pt(x0, y0), _pt(x1, y1)], fill=RED, width=xw)

    # Contact shadow: grounds the boot on the pad instead of floating it.
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [_pt(0.105, 0.700)[0], _pt(0, 0.700)[1],
         _pt(0.900, 0.812)[0], _pt(0, 0.812)[1]], fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=SS * 1.6))
    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img)

    # --- punt streaks off the toe, drawn behind the boot ------------------
    # The toe swings up and downrange; these mark where the car goes.
    for offset, start, length, alpha, width in (
        (0.775, 0.395, 0.135, 235, 0.028),
        (0.855, 0.375, 0.180, 235, 0.028),
        (0.930, 0.400, 0.115, 140, 0.024),
    ):
        d.line([_pt(offset, start), _pt(offset + 0.026, start - length)],
               fill=AMBER + (alpha,), width=int(_px(width)))

    # --- the boot itself ---------------------------------------------------
    boot = Image.open(source_path).convert("RGBA")
    size = int(S * BOOT_SCALE)
    boot = boot.resize((size, size), Image.LANCZOS)
    img.alpha_composite(
        boot,
        (int((S - size) / 2 + _px(BOOT_OFFSET[0])),
         int((S - size) / 2 + _px(BOOT_OFFSET[1]))),
    )
    d = ImageDraw.Draw(img)

    # --- badge rim ---------------------------------------------------------
    d.ellipse([_px(0.012), _px(0.012), S - _px(0.012), S - _px(0.012)],
              outline=RIM, width=int(_px(0.024)))

    # --- resolve -----------------------------------------------------------
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    out = out.filter(ImageFilter.GaussianBlur(radius=SS * 0.16))
    out = out.resize((OUT, OUT), Image.LANCZOS)

    dest = here / "resource_icon_96.png"
    out.save(dest)
    big = here / "resource_icon_preview_384.png"
    Image.open(dest).resize((384, 384), Image.NEAREST).save(big)
    print(f"wrote {dest} ({out.size[0]}x{out.size[1]})")
    print(f"wrote {big} (4x preview)")


if __name__ == "__main__":
    main()

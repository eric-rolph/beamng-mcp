"""Author the UI app's preview tile (app.png), deterministically.

The Add-App browser (ui/appSelector/general.lua) lists an app without a
preview just fine — it substitutes /ui/images/appDefault.png — but a stock-
looking tile is how the app reads as a first-class citizen in the grid
(v2.4, 2026-08-29: the player went looking for the app and could not tell
it from the noise). Stock previews are small PNGs in the app folder; this
one is a scorched russet on a dark card with its steam wisp, drawn with
PIL primitives only so the bytes are reproducible from the seed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 200  # stock app.png tiles are small; the grid scales them anyway
OUT = Path(__file__).resolve().parents[1] / "assets" / "ui" / "hotPotatoTuner" / "app.png"


def main() -> None:
    rng = np.random.default_rng(4747)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Card: near-black with a faint amber floor glow, rounded like the grid.
    draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=18, fill=(24, 22, 20, 255))
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((30, 120, SIZE - 30, SIZE + 40), fill=(255, 120, 20, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # The tuber: fat ellipse, slight tilt via two stacked ellipses.
    body = (38, 78, SIZE - 38, 160)
    draw.ellipse(body, fill=(148, 104, 62, 255), outline=(96, 64, 36, 255), width=3)
    # Scorched crown.
    draw.ellipse((70, 74, 130, 104), fill=(70, 48, 30, 255))
    # Russet speckle + eyes.
    for _ in range(90):
        x = float(rng.uniform(46, SIZE - 46))
        y = float(rng.uniform(86, 152))
        cx, cy = (body[0] + body[2]) / 2, (body[1] + body[3]) / 2
        if ((x - cx) / 62) ** 2 + ((y - cy) / 38) ** 2 > 0.86:
            continue
        r = float(rng.uniform(0.8, 2.2))
        shade = int(rng.uniform(70, 110))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(shade, int(shade * 0.68), int(shade * 0.42), 255))
    for ex, ey in ((66, 108), (118, 132), (140, 102)):
        draw.arc((ex, ey, ex + 14, ey + 9), start=200, end=340, fill=(84, 56, 32, 255), width=3)

    # Steam wisp off the crown: three blurred curls.
    steam = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(steam)
    for i, (x0, amp) in enumerate(((92, 9), (104, 12), (84, 7))):
        points = [
            (x0 + amp * np.sin(t * 3.1 + i * 1.7), 78 - t * (34 + 8 * i))
            for t in np.linspace(0.0, 1.0, 24)
        ]
        sdraw.line([(float(px), float(py)) for px, py in points],
                   fill=(235, 235, 235, 150), width=5, joint="curve")
    steam = steam.filter(ImageFilter.GaussianBlur(2.6))
    img = Image.alpha_composite(img, steam)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(OUT, format="PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

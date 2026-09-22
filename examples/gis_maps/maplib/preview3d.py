"""Software renders for review: shapes (painter's algorithm) and terrain fly-through views.

Nothing here ships; the critic loop and the DESIGN ledgers use these images to look at
the level the way a player would, without a game install in the loop.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def _look_at(eye: np.ndarray, target: np.ndarray, up=(0.0, 0.0, 1.0)):
    f = target - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, np.asarray(up, dtype="float64"))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return f, r, u


_TILED: dict[int, object] = {}


def _tiled(image):
    """The texture repeated 2x2 so UVs up to one full repeat past the edge stay inside."""

    from PIL import Image

    key = id(image)
    if key not in _TILED:
        w, h = image.size
        mosaic = Image.new("RGBA", (w * 2, h * 2))
        for dx in (0, w):
            for dy in (0, h):
                mosaic.paste(image, (dx, dy))
        _TILED[key] = mosaic
    return _TILED[key]


def _solve_affine(dst: np.ndarray, src: np.ndarray):
    """Affine (a, b, c, d, e, f) mapping output pixels ``dst`` to texture pixels ``src``."""

    m = np.column_stack([dst, np.ones(3)])
    sol = np.linalg.solve(m, src)  # (3, 2): columns are x and y coefficients
    return (sol[0, 0], sol[1, 0], sol[2, 0], sol[0, 1], sol[1, 1], sol[2, 1])


def _paste_textured_triangle(image, poly, shade: float, texture, uv_px: np.ndarray, alpha_ref: int):
    from PIL import Image, ImageChops, ImageDraw

    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, y0 = int(max(0, math.floor(min(xs)))), int(max(0, math.floor(min(ys))))
    x1, y1 = (
        int(min(image.width, math.ceil(max(xs)) + 1)),
        int(min(image.height, math.ceil(max(ys)) + 1)),
    )
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    try:
        a, b, c, d, e, f = _solve_affine(np.asarray(poly, dtype="float64"), uv_px)
    except np.linalg.LinAlgError:
        return
    box = (x1 - x0, y1 - y0)
    warped = texture.transform(
        box,
        Image.AFFINE,
        data=(a, b, c + a * x0 + b * y0, d, e, f + d * x0 + e * y0),
        resample=Image.BILINEAR,
    )
    mask = Image.new("L", box, 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in poly], fill=255)
    alpha = warped.getchannel("A").point(lambda v: 255 if v >= alpha_ref else 0)
    mask = ImageChops.multiply(mask, alpha)
    rgb = np.asarray(warped.convert("RGB")).astype("float32") * shade
    image.paste(Image.fromarray(rgb.clip(0, 255).astype("uint8")), (x0, y0), mask)


def render_mesh(
    meshes,
    path: Path,
    *,
    size: tuple[int, int] = (640, 480),
    yaw_deg: float = 35.0,
    pitch_deg: float = 18.0,
    fov_deg: float = 40.0,
    ground: bool = True,
    background=(140, 172, 205),
    textures: dict | None = None,
    transparent: bool = False,
    alpha_ref: int = 96,
) -> Path:
    """Painter's-algorithm render of a list of ``meshgen.Mesh`` (Z-up).

    ``textures`` maps a material name to an (r, g, b) tuple for flat shading or to a
    dict ``{"image": PIL RGBA, "colour": (r, g, b)}``: with an image the triangles are
    texture-mapped through the mesh UVs and alpha-tested at ``alpha_ref`` like the
    game's card materials.
    """

    from PIL import Image, ImageDraw

    visible = [m for m in meshes if m.material]
    allp = np.concatenate([m.positions for m in visible])
    centre = (allp.max(axis=0) + allp.min(axis=0)) / 2.0
    radius = float(np.linalg.norm(allp.max(axis=0) - allp.min(axis=0))) / 2.0
    dist = radius / math.tan(math.radians(fov_deg / 2)) * 1.15
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    eye = centre + dist * np.array(
        [math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)]
    )
    f, r, u = _look_at(eye, centre)
    w, h = size
    focal = (h / 2) / math.tan(math.radians(fov_deg / 2))
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    if transparent:
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        ground = False
    else:
        image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image, "RGBA")

    def project(p):
        d = p - eye
        z = d @ f
        x = d @ r
        y = d @ u
        return np.stack(
            [w / 2 + focal * x / np.maximum(z, 1e-3), h / 2 - focal * y / np.maximum(z, 1e-3)],
            axis=1,
        ), z

    tris = []
    if ground:
        g = radius * 1.6
        quad = np.array([[-g, -g, 0], [g, -g, 0], [g, g, 0], [-g, g, 0]]) + np.array(
            [centre[0], centre[1], 0.0]
        )
        pts, z = project(quad)
        draw.polygon([tuple(p) for p in pts], fill=(120, 108, 92, 255))
    for m in visible:
        pts, z = project(m.positions)
        tri = m.triangles
        a, b, c = m.positions[tri[:, 0]], m.positions[tri[:, 1]], m.positions[tri[:, 2]]
        n = np.cross(b - a, c - a)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        shade = np.clip(np.abs(n @ light), 0, 1) * 0.75 + 0.25
        depth = (z[tri[:, 0]] + z[tri[:, 1]] + z[tri[:, 2]]) / 3.0
        tex = textures.get(m.material) if textures else None
        image_tex = tex.get("image") if isinstance(tex, dict) else None
        if isinstance(tex, dict):
            col = np.array(tex.get("colour", (0.6, 0.6, 0.6)))
        else:
            col = np.array(tex if tex is not None else (0.6, 0.6, 0.6))
        uv_px = None
        if image_tex is not None and m.uvs is not None and len(m.uvs) == len(m.positions):
            # Meshes tile their textures (rock UVs run to 2): draw from a 2x2 mosaic and
            # bring every triangle's UVs down to its own first repeat.
            image_tex = _tiled(image_tex)
            uv_px = np.column_stack(
                [m.uvs[:, 0] * image_tex.width / 2, (1.0 - m.uvs[:, 1]) * image_tex.height / 2]
            )
        for k in np.argsort(-depth):
            if depth[k] <= 0:
                continue
            p0, p1, p2 = pts[tri[k, 0]], pts[tri[k, 1]], pts[tri[k, 2]]
            poly = [(p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1])]
            if uv_px is not None:
                uv = uv_px[tri[k]].copy()
                uv -= np.floor(
                    uv.min(axis=0) / np.array([image_tex.width / 2, image_tex.height / 2])
                ) * np.array([image_tex.width / 2, image_tex.height / 2])
                # Cards are lit from both sides; keep them brighter than facets.
                tris.append((depth[k], poly, None, (image_tex, uv, 0.55 + 0.45 * shade[k])))
            else:
                rgb = tuple(int(255 * min(1, v * shade[k])) for v in col)
                tris.append((depth[k], poly, rgb, None))
    for _, poly, rgb, textured in sorted(tris, key=lambda t: -t[0]):
        if textured is None:
            draw.polygon(poly, fill=(*rgb, 255))
        else:
            image_tex, uv, shade_k = textured
            _paste_textured_triangle(image, poly, shade_k, image_tex, uv, alpha_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def render_terrain_view(
    dem: np.ndarray,
    colour: np.ndarray,
    res: float,
    *,
    eye_xy: tuple[float, float],
    heading_deg: float,
    path: Path,
    size: tuple[int, int] = (960, 540),
    eye_height: float = 2.0,
    fov_deg: float = 70.0,
    max_distance: float = 2500.0,
    sprites: list[dict] | None = None,
    sky=(150, 185, 225),
    sun_azimuth_deg: float = 225.0,
    sun_altitude_deg: float = 40.0,
    detail: dict | None = None,
) -> Path:
    """Voxel-space (column ray-march) render of a north-up DEM with a colour map.

    ``eye_xy`` and heading are in the level frame (metres east/north of centre, heading
    0 = north, clockwise). ``sprites`` are dicts with ``x, y, z, w, h, rgba`` (an RGBA
    uint8 image) drawn as billboards depth-sorted into the terrain. ``detail`` is
    ``{"layer": int map, "tiles": [(rgb, tile_m), ...], "fade_m": 120}``: the
    terrain's own detail textures, tiled in world metres over the base colour and faded
    out with distance the way the game blends them.
    """

    from PIL import Image

    from . import heightmap as hm

    n = dem.shape[0]
    half = n * res / 2.0
    w, h = size
    shade = hm.hillshade(dem, res, sun_azimuth_deg, sun_altitude_deg)
    lit = np.clip(colour.astype("float32") / 255.0 * (0.45 + 0.75 * shade[..., None]), 0, 1)

    layer = detail.get("layer") if detail else None
    tiles = detail.get("tiles", []) if detail else []
    fade_m = float(detail.get("fade_m", 120.0)) if detail else 0.0

    def sample(x, y, d=np.inf):
        col = np.clip((x + half) / res - 0.5, 0, n - 1.001)
        row = np.clip((half - y) / res - 0.5, 0, n - 1.001)
        c0, r0 = col.astype(int), row.astype(int)
        c1, r1 = np.minimum(c0 + 1, n - 1), np.minimum(r0 + 1, n - 1)
        fc, fr = (col - c0)[:, None], (row - r0)[:, None]
        w00, w01, w10, w11 = (1 - fc) * (1 - fr), fc * (1 - fr), (1 - fc) * fr, fc * fr
        z = (
            dem[r0, c0] * w00[:, 0]
            + dem[r0, c1] * w01[:, 0]
            + dem[r1, c0] * w10[:, 0]
            + dem[r1, c1] * w11[:, 0]
        )
        rgb = lit[r0, c0] * w00 + lit[r0, c1] * w01 + lit[r1, c0] * w10 + lit[r1, c1] * w11
        if layer is not None and d < fade_m:
            idx = layer[r0, c0]
            # Per channel: a detail tile carries the material's colour, not just its
            # brightness, and a luminance factor threw that away.
            factor = np.ones((z.size, 3), dtype="float32")
            for li, (tile, tile_m) in enumerate(tiles):
                m = idx == li
                if m.any():
                    s_px = tile.shape[0]
                    tu = ((x[m] / tile_m) % 1.0 * s_px).astype(int)
                    tv = ((-y[m] / tile_m) % 1.0 * s_px).astype(int)
                    sampled = tile[tv, tu]
                    factor[m] = sampled if sampled.ndim == 2 else sampled[:, None]
            rgb = rgb * (1.0 + (factor - 1.0) * 0.7 * (1.0 - d / fade_m))
        return z, np.clip(rgb, 0, 1)

    ex, ey = eye_xy
    ez = float(sample(np.array([ex]), np.array([ey]))[0][0]) + eye_height
    heading = math.radians(heading_deg)
    fov = math.radians(fov_deg)
    focal = (w / 2) / math.tan(fov / 2)
    frame = np.zeros((h, w, 3), dtype="float32")
    frame[:] = np.asarray(sky, dtype="float32") / 255.0
    depth = np.full((h, w), np.inf, dtype="float32")
    ybuf = np.full(w, h, dtype="int64")  # lowest drawn row per column (screen y grows down)
    xs = (np.arange(w) - w / 2 + 0.5) / focal  # tangent of the horizontal angle
    dirs_x = np.sin(heading) + xs * math.cos(heading)
    dirs_y = math.cos(heading) - xs * math.sin(heading)
    fog = np.asarray(sky, dtype="float32") / 255.0
    d = 0.4
    while d < max_distance:
        px = ex + dirs_x * d
        py = ey + dirs_y * d
        z, rgb = sample(px, py, d)
        screen_y = (h / 2 - focal * (z - ez) / d).astype(int)
        screen_y = np.clip(screen_y, 0, h)
        f = min(1.0, (d / max_distance) ** 1.5) * 0.85
        col = rgb * (1 - f) + fog[None, :] * f
        for c in np.nonzero(screen_y < ybuf)[0]:
            frame[screen_y[c] : ybuf[c], c] = col[c]
            depth[screen_y[c] : ybuf[c], c] = d
            ybuf[c] = screen_y[c]
        d += max(0.15, d * 0.012)  # fine steps at the wheels, coarser far away
    image = Image.fromarray((frame * 255).round().astype("uint8"))
    if sprites:
        order = sorted(sprites, key=lambda s: -math.hypot(s["x"] - ex, s["y"] - ey))
        for s in order:
            dx, dy = s["x"] - ex, s["y"] - ey
            forward = dx * math.sin(heading) + dy * math.cos(heading)
            right = dx * math.cos(heading) - dy * math.sin(heading)
            if forward < 1.0 or forward > max_distance:
                continue
            sx = w / 2 + focal * right / forward
            sy_bottom = h / 2 - focal * (s["z"] - ez) / forward
            sw = focal * s["w"] / forward
            sh = focal * s["h"] / forward
            if sw < 1 or sx < -sw or sx > w + sw:
                continue
            x0, y0 = int(sx - sw / 2), int(sy_bottom - sh)
            box_w, box_h = max(1, int(sw)), max(1, int(sh))
            # Occlusion: skip sprites whose base is behind terrain already drawn there.
            cx, cy = int(np.clip(sx, 0, w - 1)), int(np.clip(sy_bottom - 1, 0, h - 1))
            if depth[cy, cx] < forward * 0.85:
                continue
            f = min(1.0, (forward / max_distance) ** 1.5) * 0.85
            spr = Image.fromarray(s["rgba"]).resize((box_w, box_h))
            arr = np.asarray(spr).astype("float32")
            arr[..., :3] = arr[..., :3] * (1 - f) + fog * 255 * f
            spr = Image.fromarray(arr.round().astype("uint8"), "RGBA")
            image.paste(spr, (x0, y0), spr)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path

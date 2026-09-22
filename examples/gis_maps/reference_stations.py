"""Camera stations along a map's main route, paired with Google links for the same view.

The gates and the critic sheets both read the generator's own arrays. Neither can see
what the engine draws, and neither has ever stood on the road. A play-test found the
mirrored base texture, and a play-test found the two-by-two tiling; this is the same
channel made systematic.

Each station is a point on the route with a heading taken from the road's own tangent,
so "looking down the road" means the same thing in both pictures. For each one the
script prints the level coordinates a render should use, and the two Google URLs that
put a human at the same place:

    aerial 3D   /maps/@{lat},{lon},{alt}a,{fov}y,{heading}h,{tilt}t/data=!3m1!1e3
    Street View /maps/@?api=1&map_action=pano&viewpoint={lat},{lon}&heading=&pitch=&fov=

Google's imagery is a reference for a person to look at, not a source this pack reads,
redistributes or derives geometry from. Nothing it shows enters the build except as a
written finding in the must-do list, which is then satisfied from the public-domain
data the pack already cites.

    python examples/gis_maps/reference_stations.py black_bear_pass --every 250
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent


def load_spec(map_key: str):
    loader = importlib.util.spec_from_file_location(
        f"gis_spec_{map_key}", PACK_ROOT / map_key / "spec.py"
    )
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def route_points(map_key: str, name_contains: str | None) -> list[tuple[float, float]]:
    """The ordered centreline of the route: the named way if there is one, else the
    longest drivable way in the extract."""

    data = json.loads((PACK_ROOT / map_key / "data" / "osm" / "roads.json").read_text())
    ways = [w for w in data["elements"] if w.get("type") == "way" and w.get("geometry")]
    named = [
        w
        for w in ways
        if name_contains and name_contains.lower() in (w.get("tags", {}).get("name") or "").lower()
    ]
    chosen = named or [
        max(
            (w for w in ways if w.get("tags", {}).get("motor_vehicle") != "no"),
            key=lambda w: len(w["geometry"]),
        )
    ]
    runs = [[(float(g["lat"]), float(g["lon"])) for g in w["geometry"]] for w in chosen]
    # The named route is several ways in no particular order, and either way round.
    # Chain them greedily by whichever free end is nearest, so the stations walk the
    # road instead of jumping between the pass and the switchbacks.
    chain = runs.pop(0)
    while runs:
        candidates = []
        for i, r in enumerate(runs):
            candidates.append((haversine_m(chain[-1], r[0]), i, False, True))
            candidates.append((haversine_m(chain[-1], r[-1]), i, True, True))
            candidates.append((haversine_m(chain[0], r[-1]), i, False, False))
            candidates.append((haversine_m(chain[0], r[0]), i, True, False))
        _gap, idx, flip, append = min(candidates)
        run = runs.pop(idx)
        if flip:
            run = run[::-1]
        chain = chain + run if append else run + chain
    return chain


def oriented(pts, start_lat: float, start_lon: float):
    """Walk the chain from the end nearest the given point (the top of the climb)."""

    if haversine_m(pts[0], (start_lat, start_lon)) <= haversine_m(pts[-1], (start_lat, start_lon)):
        return pts
    return pts[::-1]


def inside(fp, lat: float, lon: float) -> bool:
    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", f"EPSG:{fp.epsg}", [lon], [lat])
    return fp.west <= xs[0] <= fp.east and fp.south <= ys[0] <= fp.north


def level_xy(fp, lat: float, lon: float) -> tuple[float, float]:
    """Level coordinates: the footprint's centre is the origin, +x east, +y north."""

    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", f"EPSG:{fp.epsg}", [lon], [lat])
    cx, cy = fp.center
    return (round(xs[0] - cx, 1), round(ys[0] - cy, 1))


def aerial_url(lat, lon, heading, alt=300, fov=35, tilt=70) -> str:
    return (
        f"https://www.google.com/maps/@{lat:.6f},{lon:.6f},{alt}a,{fov}y,"
        f"{heading:.2f}h,{tilt}t/data=!3m1!1e3"
    )


def pano_url(lat, lon, heading, pitch=0, fov=80) -> str:
    return (
        f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}"
        f"&heading={heading:.2f}&pitch={pitch}&fov={fov}"
    )


DRIVABLE = ("track", "service", "tertiary", "unclassified", "residential", "secondary")


def latlon(fp, x: float, y: float) -> tuple[float, float]:
    """Back out of the footprint's projection into WGS84."""

    from rasterio.warp import transform

    lons, lats = transform(f"EPSG:{fp.epsg}", "EPSG:4326", [x], [y])
    return (lats[0], lons[0])


def drivable_nodes(map_key: str) -> list[tuple[float, float]]:
    data = json.loads((PACK_ROOT / map_key / "data" / "osm" / "roads.json").read_text())
    out = []
    for w in data["elements"]:
        if w.get("type") != "way" or not w.get("geometry"):
            continue
        if (w.get("tags", {}).get("highway") or "") not in DRIVABLE:
            continue
        out.extend((float(g["lat"]), float(g["lon"])) for g in w["geometry"])
    return out


def ring_stations(fp, map_key: str, radius_m: float, count: int, snap_m: float) -> list[dict]:
    """Stations evenly spaced round a circle about the footprint centre, each looking in.

    A crater is not a route: what a person judges is the bowl seen from the rim, so the
    heading is the bearing to the centre rather than a road's tangent. Each station is
    pulled onto the nearest drivable node within `snap_m` where there is one, so it
    stands on a track a vehicle can reach instead of hanging over the wall.
    """

    cx, cy = fp.center
    clat, clon = latlon(fp, cx, cy)
    nodes = drivable_nodes(map_key)
    stations = []
    for k in range(count):
        theta = math.radians(360.0 * k / count)
        lat, lon = latlon(fp, cx + radius_m * math.sin(theta), cy + radius_m * math.cos(theta))
        snapped = ""
        if nodes:
            near = min(nodes, key=lambda n: haversine_m((lat, lon), n))
            if haversine_m((lat, lon), near) <= snap_m:
                lat, lon = near
                snapped = "on a track"
        if not inside(fp, lat, lon):
            continue
        heading = bearing_deg((lat, lon), (clat, clon))
        stations.append(
            {
                "n": len(stations) + 1,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "heading_deg": round(heading, 2),
                "level_xy": level_xy(fp, lat, lon),
                "near": f"rim {360 * k // count:03d} deg" + (f", {snapped}" if snapped else ""),
                "aerial": aerial_url(lat, lon, heading),
                "pano": pano_url(lat, lon, heading),
            }
        )
    return stations


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("map_key")
    ap.add_argument("--every", type=float, default=250.0, help="metres between stations")
    ap.add_argument("--route-name", default=None, help="substring of the OSM way name")
    ap.add_argument(
        "--ring",
        type=float,
        default=None,
        help="metres: also ring the footprint centre at this radius, every station looking in",
    )
    ap.add_argument("--ring-count", type=int, default=16, help="stations round the ring")
    ap.add_argument("--snap", type=float, default=120.0, help="pull a ring station onto a track")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    sys.path.insert(0, str(PACK_ROOT))
    from maplib.gis_sources import Footprint

    spec = load_spec(args.map_key)
    site = spec.SITE
    fp = Footprint.from_center(
        site["center_lat"],
        site["center_lon"],
        site["epsg"],
        site["size_px"] * site["square_size_m"],
    )
    pts = [p for p in route_points(args.map_key, args.route_name) if inside(fp, *p)]
    if len(pts) < 2:
        raise SystemExit("no route inside the footprint")
    # Station 1 is the top of the climb: the default spawn, else the first spawn.
    spawns = getattr(spec, "SPAWNS", []) or []
    head = next((s for s in spawns if s.get("default")), spawns[0] if spawns else None)
    if head:
        pts = oriented(pts, float(head["lat"]), float(head["lon"]))

    stations = (
        ring_stations(fp, args.map_key, args.ring, args.ring_count, args.snap) if args.ring else []
    )
    carried = args.every  # emit one at the very start
    for i in range(len(pts) - 1):
        carried += haversine_m(pts[i], pts[i + 1])
        if carried < args.every:
            continue
        carried = 0.0
        # heading from a 60 m chord, so a single jittered node does not swing it
        ahead = i
        run = 0.0
        while ahead + 1 < len(pts) and run < 60.0:
            run += haversine_m(pts[ahead], pts[ahead + 1])
            ahead += 1
        lat, lon = pts[i]
        heading = bearing_deg(pts[i], pts[ahead])
        stations.append(
            {
                "n": len(stations) + 1,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "heading_deg": round(heading, 2),
                "level_xy": level_xy(fp, lat, lon),
                "aerial": aerial_url(lat, lon, heading),
                "pano": pano_url(lat, lon, heading),
            }
        )

    # Every authored spawn is a station too, at its own heading: those are the places a
    # person starts, so they are where a wrong tree line or kerb is seen first. One
    # already within 80 m of a route station is not repeated.
    for sp in spawns:
        lat, lon = float(sp["lat"]), float(sp["lon"])
        if not inside(fp, lat, lon):
            continue
        if any(haversine_m((lat, lon), (st["lat"], st["lon"])) < 80 for st in stations):
            continue
        heading = float(sp.get("heading_deg", 0.0))
        stations.append(
            {
                "n": 0,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "heading_deg": round(heading, 2),
                "level_xy": level_xy(fp, lat, lon),
                "aerial": aerial_url(lat, lon, heading),
                "pano": pano_url(lat, lon, heading),
                "spawn": sp["name"],
                "near": sp.get("label") or sp["name"],
            }
        )
    stations.sort(key=lambda st: (st["n"] == 0, st["n"]))
    for i, st in enumerate(stations, 1):
        st["n"] = i

    places = {p["name"]: p for p in getattr(spec, "TRAIL_FEATURES", [])}
    for st in stations:
        near = min(
            places.values(),
            key=lambda p: haversine_m((st["lat"], st["lon"]), (p["lat"], p["lon"])),
            default=None,
        )
        if (
            near
            and "spawn" not in st
            and "near" not in st
            and haversine_m((st["lat"], st["lon"]), (near["lat"], near["lon"])) < 150
        ):
            st["near"] = near["name"]

    out = (
        Path(args.out)
        if args.out
        else (PACK_ROOT / args.map_key / "authoring" / "reference_stations.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "map": args.map_key,
                "every_m": args.every,
                "ring_m": args.ring,
                "stations": stations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(stations)} stations every {args.every:g} m -> {out}")
    for st in stations:
        tag = f"  ({st['near']})" if "near" in st else ""
        print(
            f"  {st['n']:>2}  {st['lat']:.5f},{st['lon']:.5f}  "
            f"hdg {st['heading_deg']:>6.1f}  xy {st['level_xy']}{tag}"
        )
    write_markdown(
        out.with_suffix(".md"), args.map_key, spec, stations, args.every, args.ring, args.snap
    )
    print(f"  -> {out.with_suffix('.md')}")


HOW_ROUTE = """\
Camera stations along the route, every {every:g} m, with the heading taken from the road's
own tangent so "looking down the road" means the same thing in both pictures. Station 1 is
the top of the climb and the numbering follows the drive."""

HOW_RING = """\
Camera stations on a {ring:g} m ring about the level's centre, each one looking in, then
the approach road every {every:g} m with the heading from its own tangent. A crater is not a
route: what a person judges is the bowl seen from the rim, so the ring comes first and every
ring station is pulled onto a track where one runs within {snap:g} m of it."""

HEADER = """# {title} - reference stations

{how}

`level xy` is where a render of our own map should put the camera: the footprint's centre
is the origin, +x east, +y north. Regenerate this sheet with:

    python examples/gis_maps/reference_stations.py {argv}

**How this is used.** A station is handed over, both links are opened, and what the eye
finds wrong with ours becomes a row in the must-do list with the generator change that
would satisfy it. Google's imagery is a reference for a person to look at. It is never
fetched, stored, redistributed, or used to derive geometry, colour or placement, and
nothing it shows enters the build except as a written finding. Every fix is implemented
from the public-domain and ODbL sources this pack already cites: USGS 3DEP lidar and its
point cloud, USGS NAIP orthoimagery, and OpenStreetMap.

## Stations

| # | where | lat, lon | heading | level xy | aerial 3D | street view |
| --- | --- | --- | --- | --- | --- | --- |
"""

MUSTDO = """
## Must-do list

Filled in from what the stations show. A row closes when it is a spec or generator change
in the tree - the rule the critic ledger already uses.

| # | station | finding | what changes in the generator | status |
| --- | --- | --- | --- | --- |
| | | | | |
"""


def write_markdown(
    path: Path, map_key: str, spec, stations, every: float, ring=None, snap: float = 120.0
) -> None:
    rows = []
    for st in stations:
        where = st.get("near", "")
        if st.get("spawn"):
            where = f"**{where}** (spawn)"
        rows.append(
            f"| {st['n']} | {where} | {st['lat']:.5f}, {st['lon']:.5f} | "
            f"{st['heading_deg']:.0f} deg | {st['level_xy'][0]:.0f}, {st['level_xy'][1]:.0f} | "
            f"[3D]({st['aerial']}) | [pano]({st['pano']}) |"
        )
    title = getattr(spec, "DISPLAY_NAME", map_key)
    how = (
        HOW_RING.format(ring=ring, every=every, snap=snap)
        if ring
        else HOW_ROUTE.format(every=every)
    )
    argv = " ".join(a if " " not in a else f'"{a}"' for a in sys.argv[1:])
    path.write_text(
        HEADER.format(title=title, how=how, argv=argv) + "\n".join(rows) + "\n" + MUSTDO,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

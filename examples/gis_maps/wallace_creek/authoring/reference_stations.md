# Carrizo Plain - Wallace Creek - reference stations

Camera stations along the route, every 250 m, with the heading taken from the road's
own tangent so "looking down the road" means the same thing in both pictures. Station 1 is
the top of the climb and the numbering follows the drive.

`level xy` is where a render of our own map should put the camera: the footprint's centre
is the origin, +x east, +y north. Regenerate this sheet with:

    python examples/gis_maps/reference_stations.py wallace_creek --every 250

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
| 1 |  | 35.27995, -119.83611 | 179 deg | -1863, 2047 | [3D](https://www.google.com/maps/@35.279953,-119.836105,300a,35y,178.88h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.279953,-119.836105&heading=178.88&pitch=0&fov=80) |
| 2 |  | 35.27800, -119.83596 | 140 deg | -1856, 1830 | [3D](https://www.google.com/maps/@35.278001,-119.835960,300a,35y,140.28h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.278001,-119.835960&heading=140.28&pitch=0&fov=80) |
| 3 |  | 35.27572, -119.83510 | 156 deg | -1785, 1574 | [3D](https://www.google.com/maps/@35.275720,-119.835102,300a,35y,156.10h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.275720,-119.835102&heading=156.10&pitch=0&fov=80) |
| 4 |  | 35.27384, -119.83406 | 158 deg | -1697, 1363 | [3D](https://www.google.com/maps/@35.273843,-119.834062,300a,35y,158.13h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.273843,-119.834062&heading=158.13&pitch=0&fov=80) |
| 5 |  | 35.27202, -119.83259 | 136 deg | -1569, 1157 | [3D](https://www.google.com/maps/@35.272020,-119.832593,300a,35y,135.93h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.272020,-119.832593&heading=135.93&pitch=0&fov=80) |
| 6 |  | 35.26954, -119.82978 | 128 deg | -1320, 875 | [3D](https://www.google.com/maps/@35.269544,-119.829777,300a,35y,127.64h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.269544,-119.829777&heading=127.64&pitch=0&fov=80) |
| 7 |  | 35.26724, -119.82720 | 152 deg | -1093, 613 | [3D](https://www.google.com/maps/@35.267240,-119.827203,300a,35y,151.58h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.267240,-119.827203&heading=151.58&pitch=0&fov=80) |
| 8 |  | 35.26564, -119.82564 | 139 deg | -956, 432 | [3D](https://www.google.com/maps/@35.265642,-119.825641,300a,35y,139.23h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.265642,-119.825641&heading=139.23&pitch=0&fov=80) |
| 9 |  | 35.26356, -119.82427 | 154 deg | -838, 197 | [3D](https://www.google.com/maps/@35.263557,-119.824269,300a,35y,154.30h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.263557,-119.824269&heading=154.30&pitch=0&fov=80) |
| 10 |  | 35.26061, -119.82194 | 134 deg | -636, -136 | [3D](https://www.google.com/maps/@35.260608,-119.821944,300a,35y,134.42h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.260608,-119.821944&heading=134.42&pitch=0&fov=80) |
| 11 |  | 35.25845, -119.82033 | 121 deg | -496, -380 | [3D](https://www.google.com/maps/@35.258455,-119.820329,300a,35y,120.89h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.258455,-119.820329&heading=120.89&pitch=0&fov=80) |
| 12 |  | 35.25661, -119.81888 | 154 deg | -370, -588 | [3D](https://www.google.com/maps/@35.256606,-119.818885,300a,35y,154.21h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.256606,-119.818885&heading=154.21&pitch=0&fov=80) |
| 13 |  | 35.25469, -119.81755 | 147 deg | -254, -805 | [3D](https://www.google.com/maps/@35.254686,-119.817548,300a,35y,147.04h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.254686,-119.817548&heading=147.04&pitch=0&fov=80) |
| 14 |  | 35.25284, -119.81511 | 130 deg | -39, -1016 | [3D](https://www.google.com/maps/@35.252840,-119.815113,300a,35y,130.04h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.252840,-119.815113&heading=130.04&pitch=0&fov=80) |
| 15 |  | 35.25147, -119.81281 | 130 deg | 167, -1174 | [3D](https://www.google.com/maps/@35.251472,-119.812807,300a,35y,129.78h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.251472,-119.812807&heading=129.78&pitch=0&fov=80) |
| 16 |  | 35.24992, -119.81032 | 128 deg | 389, -1352 | [3D](https://www.google.com/maps/@35.249925,-119.810316,300a,35y,128.36h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.249925,-119.810316&heading=128.36&pitch=0&fov=80) |
| 17 |  | 35.24896, -119.80874 | 132 deg | 529, -1463 | [3D](https://www.google.com/maps/@35.248956,-119.808741,300a,35y,132.18h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.248956,-119.808741&heading=132.18&pitch=0&fov=80) |
| 18 |  | 35.24724, -119.80652 | 136 deg | 726, -1660 | [3D](https://www.google.com/maps/@35.247238,-119.806516,300a,35y,136.15h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.247238,-119.806516&heading=136.15&pitch=0&fov=80) |
| 19 |  | 35.24455, -119.80341 | 136 deg | 1000, -1965 | [3D](https://www.google.com/maps/@35.244554,-119.803410,300a,35y,136.34h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.244554,-119.803410&heading=136.34&pitch=0&fov=80) |
| 20 | **wallace_creek_offset** (spawn) | 35.27170, -119.82750 | 135 deg | -1106, 1109 | [3D](https://www.google.com/maps/@35.271700,-119.827500,300a,35y,135.00h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.271700,-119.827500&heading=135.00&pitch=0&fov=80) |
| 21 | **elkhorn_scarp** (spawn) | 35.25500, -119.80500 | 315 deg | 888, -802 | [3D](https://www.google.com/maps/@35.255000,-119.805000,300a,35y,315.00h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.255000,-119.805000&heading=315.00&pitch=0&fov=80) |
| 22 | **plain_west** (spawn) | 35.26500, -119.83000 | 90 deg | -1355, 372 | [3D](https://www.google.com/maps/@35.265000,-119.830000,300a,35y,90.00h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=35.265000,-119.830000&heading=90.00&pitch=0&fov=80) |

## Must-do list

Filled in from what the stations show. A row closes when it is a spec or generator change
in the tree - the rule the critic ledger already uses.

| # | station | finding | what changes in the generator | status |
| --- | --- | --- | --- | --- |
| | | | | |

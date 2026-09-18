# Factory Butte Badlands - reference stations

Camera stations along the route, every 250 m, with the heading taken from the road's
own tangent so "looking down the road" means the same thing in both pictures. Station 1 is
the top of the climb and the numbering follows the drive.

`level xy` is where a render of our own map should put the camera: the footprint's centre
is the origin, +x east, +y north. Regenerate this sheet with:

    python examples/gis_maps/reference_stations.py factory_butte --every 250

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
| 1 |  | 38.36209, -110.92202 | 67 deg | -1921, -1988 | [3D](https://www.google.com/maps/@38.362093,-110.922019,300a,35y,66.90h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.362093,-110.922019&heading=66.90&pitch=0&fov=80) |
| 2 |  | 38.36545, -110.91200 | 68 deg | -1046, -1615 | [3D](https://www.google.com/maps/@38.365449,-110.911998,300a,35y,68.19h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.365449,-110.911998&heading=68.19&pitch=0&fov=80) |
| 3 |  | 38.36617, -110.90887 | 84 deg | -773, -1535 | [3D](https://www.google.com/maps/@38.366167,-110.908866,300a,35y,84.18h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.366167,-110.908866&heading=84.18&pitch=0&fov=80) |
| 4 |  | 38.36605, -110.90541 | 105 deg | -470, -1548 | [3D](https://www.google.com/maps/@38.366046,-110.905406,300a,35y,105.18h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.366046,-110.905406&heading=105.18&pitch=0&fov=80) |
| 5 |  | 38.36519, -110.90043 | 81 deg | -36, -1642 | [3D](https://www.google.com/maps/@38.365195,-110.900429,300a,35y,81.23h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.365195,-110.900429&heading=81.23&pitch=0&fov=80) |
| 6 |  | 38.36546, -110.89897 | 70 deg | 92, -1613 | [3D](https://www.google.com/maps/@38.365456,-110.898966,300a,35y,69.70h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.365456,-110.898966&heading=69.70&pitch=0&fov=80) |
| 7 |  | 38.36696, -110.89290 | 87 deg | 622, -1445 | [3D](https://www.google.com/maps/@38.366962,-110.892901,300a,35y,87.48h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.366962,-110.892901&heading=87.48&pitch=0&fov=80) |
| 8 |  | 38.36683, -110.88972 | 104 deg | 900, -1460 | [3D](https://www.google.com/maps/@38.366826,-110.889721,300a,35y,104.24h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.366826,-110.889721&heading=104.24&pitch=0&fov=80) |
| 9 |  | 38.36636, -110.88791 | 118 deg | 1058, -1511 | [3D](https://www.google.com/maps/@38.366361,-110.887905,300a,35y,117.59h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.366361,-110.887905&heading=117.59&pitch=0&fov=80) |
| 10 |  | 38.36495, -110.88297 | 82 deg | 1490, -1667 | [3D](https://www.google.com/maps/@38.364950,-110.882966,300a,35y,82.48h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.364950,-110.882966&heading=82.48&pitch=0&fov=80) |
| 11 |  | 38.36472, -110.87911 | 126 deg | 1827, -1692 | [3D](https://www.google.com/maps/@38.364725,-110.879106,300a,35y,126.32h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.364725,-110.879106&heading=126.32&pitch=0&fov=80) |
| 12 | **butte_base** (spawn) | 38.38000, -110.90500 | 60 deg | -436, 0 | [3D](https://www.google.com/maps/@38.380000,-110.905000,300a,35y,60.00h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.380000,-110.905000&heading=60.00&pitch=0&fov=80) |
| 13 | **badlands_south** (spawn) | 38.36600, -110.89500 | 0 deg | 439, -1552 | [3D](https://www.google.com/maps/@38.366000,-110.895000,300a,35y,0.00h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.366000,-110.895000&heading=0.00&pitch=0&fov=80) |
| 14 | **wash_west** (spawn) | 38.38500, -110.91800 | 90 deg | -1572, 554 | [3D](https://www.google.com/maps/@38.385000,-110.918000,300a,35y,90.00h,70t/data=!3m1!1e3) | [pano](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.385000,-110.918000&heading=90.00&pitch=0&fov=80) |

## Must-do list

Filled in from what the stations show. A row closes when it is a spec or generator change
in the tree - the rule the critic ledger already uses.

| # | station | finding | what changes in the generator | status |
| --- | --- | --- | --- | --- |
| | | | | |

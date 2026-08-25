"""Parametric anatomical hand for Charlie's High Five.

Not a sculpt and not an imported hero mesh: every vertex here is a closed
form of the human proportions in ``spec.py`` times ``HAND_SCALE``. That is
the same law the Colossus tire runs under, and it buys three things the
boot's imported GLB could not have:

* **Exact creases.** A palmar crease is POSITIONAL — it belongs at a named
  place on a named eminence — so a tiling skin map cannot put it there. As
  an analytic dip in the surface radius it lands exactly where the
  anatomy says, in geometry, where it catches real light at any distance.
* **Perfect quad topology and metric UVs.** The surface is a (s, theta)
  grid, so the UVs are computed, not projected: no smart-project islands,
  no seams through the palm, and a texel density that is true in metres.
  The boot's remesh-then-smart-project path could give neither.
* **Separable digits with invisible joints.** Each digit is its own closed
  solid whose proximal cap is a SPHERE CONCENTRIC WITH ITS JOINT PIVOT.
  Rotating a sphere about its own centre moves no surface point, so the
  digit can flex any amount without opening a gap at the knuckle — which
  is what makes the twitch possible at all. The visible line where the
  ball meets the palm is the MCP crease, and that is where a real hand has
  one.

Local frame used throughout this module (right-handed, det +1):

    +x = u   proximal -> distal
    +y = n   dorsal -> volar (out of the palm)
    +z = v   ulnar -> radial (toward the thumb)

Section angle ``theta`` is measured from +z (the radial edge) toward +y
(the palm), so theta = 0 is the thumb side, 90 the palm, 180 the little
finger side and 270 the back of the hand.

The caller transforms the finished meshes into the authored frame with
``spec.U_REST / N_REST / V_REST``; nothing in here knows about the road.
"""

from __future__ import annotations

import math

try:                                # pragma: no cover - Blender path
    import bmesh
    import bpy
    from mathutils import Matrix, Vector
except ImportError:                     # pragma: no cover - offline path
    # THE GEOMETRY MUST BE TESTABLE WITHOUT BLENDER.
    #
    # PalmSurface and DigitSurface are pure analytic maths — the only thing
    # tying them to Blender was the Vector they return. Every defect this
    # module has shipped (the folded sections, the tip poles that were
    # segments, the palm emerging between the knuckles) was a property of
    # those functions and NOT of the mesh assembly around them, and each one
    # was found by eye on a render because the gates could not reach the
    # code. So the maths imports standalone and the mesh builders are the
    # only thing that needs bpy.
    bmesh = None
    bpy = None
    Matrix = None

    class Vector:                       # noqa: D101 - minimal stand-in
        __slots__ = ("x", "y", "z")

        def __init__(self, values=(0.0, 0.0, 0.0)):
            self.x, self.y, self.z = (float(value) for value in values)

        def __getitem__(self, index):
            return (self.x, self.y, self.z)[index]

        def __iter__(self):
            return iter((self.x, self.y, self.z))

        def __add__(self, other):
            return Vector((self.x + other.x, self.y + other.y, self.z + other.z))

        def __sub__(self, other):
            return Vector((self.x - other.x, self.y - other.y, self.z - other.z))

        def __mul__(self, scalar):
            return Vector((self.x * scalar, self.y * scalar, self.z * scalar))

        __rmul__ = __mul__

        def __truediv__(self, scalar):
            return Vector((self.x / scalar, self.y / scalar, self.z / scalar))

        def __neg__(self):
            return Vector((-self.x, -self.y, -self.z))

        @property
        def length(self):
            return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

        def dot(self, other):
            return self.x * other.x + self.y * other.y + self.z * other.z

        def cross(self, other):
            return Vector(
                (
                    self.y * other.z - self.z * other.y,
                    self.z * other.x - self.x * other.z,
                    self.x * other.y - self.y * other.x,
                )
            )

        def normalized(self):
            length = self.length or 1.0
            return self / length

        def lerp(self, other, factor):
            return self + (other - self) * factor

        def copy(self):
            return Vector((self.x, self.y, self.z))

TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Small maths
# ---------------------------------------------------------------------------


def _smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _curve(keys: list[tuple[float, float]], x: float) -> float:
    """Monotone piecewise interpolation with a smoothstep ease per span.

    Linear spans put a visible crease at every key on a 4 m surface; a
    cubic through all keys overshoots and puts a bulge where the anatomy
    has none. Easing INSIDE each span keeps the curve C1 at the keys and
    strictly inside the key values, which is the property that matters
    here — a palm may not be wider anywhere than the widest number in
    spec.py.
    """

    if x <= keys[0][0]:
        return keys[0][1]
    if x >= keys[-1][0]:
        return keys[-1][1]
    for (x0, y0), (x1, y1) in zip(keys, keys[1:]):
        if x0 <= x <= x1:
            span = x1 - x0
            return _lerp(y0, y1, _smoothstep((x - x0) / span if span else 0.0))
    return keys[-1][1]


def _superellipse(theta: float, half_a: float, half_b: float, exponent: float):
    """Point on a superellipse, ``a`` along +z(cos) and ``b`` along +y(sin).

    A limb cross-section is not an ellipse: it is flatter on the broad
    faces and tighter at the edges. exponent > 2 squares it up. At 2.0
    this degenerates to the ellipse, which is what a generated hand that
    reads as a balloon animal is made of.
    """

    c, s = math.cos(theta), math.sin(theta)
    power = 2.0 / exponent
    a = half_a * math.copysign(abs(c) ** power, c)
    b = half_b * math.copysign(abs(s) ** power, s)
    return a, b


def _bump(x: float, centre: float, width: float) -> float:
    """Unit-height Gaussian, clamped to zero past 3 sigma so a bulge on one
    eminence cannot leak measurably onto the other."""

    if width <= 0.0:
        return 0.0
    t = (x - centre) / width
    if abs(t) > 3.0:
        return 0.0
    return math.exp(-t * t)


#: Fraction of a phalanx over which its joint's flexion is applied. The
#: joint is a condyle with a radius, not a hinge point; turning the whole
#: angle at one station makes the section frame jump and the surface fold
#: through itself. 0.25 of a phalanx is about 0.3 m on this hand.
JOINT_ARC_FRACTION = 0.25


def _soft_max(a: float, b: float, k: float) -> float:
    """Smooth maximum: `max(a, b)` rounded over a band of width ~k.

    Exceeds the true maximum by at most k*ln2, at a == b. Used to union
    the metacarpal-head spheres, where a hard max would cut a crease into
    the skin along every place two heads cross.
    """

    if k <= 0.0:
        return max(a, b)
    return max(a, b) + k * math.log1p(math.exp(-abs(a - b) / k))


def _angular_bump(theta: float, centre: float, width: float) -> float:
    """_bump on the circle: the shortest signed angular distance, so a
    bulge authored at theta=350 does not vanish for a vertex at theta=10."""

    delta = (theta - centre + math.pi) % TWO_PI - math.pi
    return _bump(delta, 0.0, width)


def _segment_distance(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _polyline_distance(px: float, py: float, points) -> float:
    best = float("inf")
    for a, b in zip(points, points[1:]):
        best = min(best, _segment_distance(px, py, a[0], a[1], b[0], b[1]))
    return best


def _rodrigues(vector: Vector, axis: Vector, angle: float) -> Vector:
    """Same formula as spec._rotate and the runtime's Lua ``rodrigues``.

    Deliberately not mathutils' quaternion: this module, spec.py and the
    generated Lua all have to agree about which way a positive angle
    turns, and three transcriptions of one explicit formula can be diffed.
    """

    c, s = math.cos(angle), math.sin(angle)
    return vector * c + axis.cross(vector) * s + axis * (axis.dot(vector) * (1.0 - c))


# ---------------------------------------------------------------------------
# Mesh assembly from a parametric surface
# ---------------------------------------------------------------------------


def _parting_seam(spec, theta: float, along: float, divisions: int) -> float:
    """Flash-line height at this section angle, in metres, 0 where trimmed.

    A two-part mould splits on the SILHOUETTE, so the line sits at theta = 0
    and theta = pi — the radial and ulnar edges — and runs the whole length
    of whatever it is on. The amplitude is dressed back over stretches by a
    smooth function of the distance along the piece: a mould shop trims the
    flash and never gets all of it, and an undressed line the full length of
    an 8.6 m hand reads as a moulding strip rather than as a defect.
    """

    # Sigma in COLUMNS of whatever grid is being built, so the bead is
    # the same shape on the palm's 192 and a digit's 112 instead of the
    # same ANGLE, which on radii of 2.20 m and 0.53 m is not the same
    # feature at all. See spec.FLASH_WIDTH_COLUMNS.
    width = math.radians(spec.FLASH_WIDTH_COLUMNS * 360.0 / divisions)
    ridge = _angular_bump(theta, 0.0, width) + _angular_bump(theta, math.pi, width)
    if ridge <= 0.0:
        return 0.0
    # Two incommensurate periods, so the dressing never repeats over the
    # length of a hand and no two digits get the same pattern.
    dress = 0.5 + 0.5 * math.sin(along * 2.3 + 0.7) * math.sin(along * 0.61 + 2.1)
    dress = 1.0 - spec.FLASH_DRESS * dress
    return spec._mm(spec.FLASH_PROUD_MM) * ridge * max(0.0, dress)


#: name -> number of edges marked sharp, so a gate can prove the parting
#: seam was actually creased rather than silently skipped.
_SHARP_EDGE_COUNTS: dict = {}


def _grid_to_object(
    name: str,
    rings: list[list[Vector]],
    uvs: list[list[tuple[float, float]]],
    *,
    cap_start: bool,
    cap_end: bool,
    material=None,
    sharp_columns: tuple = (),
):
    """Bridge a list of equal-length rings into a closed quad shell.

    The seam column is DUPLICATED (rings carry ``divisions + 1`` points,
    first and last coincident in space) so the UV can run 0 -> 1 without
    a wrapped face. A shared seam vertex would force one face to sample
    the whole map backwards, which on a 1.15 m foam tile is a visible
    smear straight down the hand.
    """

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")

    verts: list[list] = []
    for ring in rings:
        verts.append([bm.verts.new(point) for point in ring])
    bm.verts.ensure_lookup_table()
    # index_update, not just ensure_lookup_table: a freshly created BMVert
    # carries index -1 until this runs, so a degeneracy test written against
    # .index silently rejected EVERY face and exported a mesh of nothing but
    # its end caps.
    bm.verts.index_update()

    columns = len(rings[0])
    for index, (lower, upper) in enumerate(zip(verts, verts[1:])):
        for column in range(columns - 1):
            corners = (
                lower[column],
                upper[column],
                upper[column + 1],
                lower[column + 1],
            )
            # Degenerate rows (a pole ring) collapse to shared vertices;
            # skip the faces that would be zero-area rather than letting
            # bmesh raise on a duplicate face.
            # Pole rings collapse several columns onto one point; those faces
            # are zero-area on one edge and legal (it is how a UV sphere
            # closes). Only a face that reuses the SAME vertex is dropped.
            if len({corner.index for corner in corners}) < 3:
                continue
            try:
                face = bm.faces.new(corners)
            except ValueError:
                continue
            texcoords = (
                uvs[index][column],
                uvs[index + 1][column],
                uvs[index + 1][column + 1],
                uvs[index][column + 1],
            )
            for loop, texcoord in zip(face.loops, texcoords):
                loop[uv_layer].uv = texcoord

    def _cap(ring_verts, texcoords, flip: bool):
        unique = []
        for vertex in ring_verts[:-1]:
            if vertex not in unique:
                unique.append(vertex)
        if len(unique) < 3:
            return
        try:
            face = bm.faces.new(tuple(reversed(unique)) if flip else tuple(unique))
        except ValueError:
            return
        centre_u = sum(coord[0] for coord in texcoords[:-1]) / (len(texcoords) - 1)
        for loop in face.loops:
            loop[uv_layer].uv = (centre_u, texcoords[0][1])
        bmesh.ops.triangulate(bm, faces=[face])

    if cap_start:
        _cap(verts[0], uvs[0], flip=True)
    if cap_end:
        _cap(verts[-1], uvs[-1], flip=False)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # The mould parting line, as an explicit sharp edge along the crest
    # column. `sharp_columns` are indices into the ring; the edges marked
    # are the ones running from ring to ring at that column, i.e. down the
    # length of the piece, which is where a flash line runs.
    if sharp_columns:
        marked = 0
        for column in sharp_columns:
            for lower, upper in zip(verts, verts[1:]):
                if column >= len(lower):
                    continue
                edge = bm.edges.get((lower[column], upper[column]))
                if edge is not None:
                    edge.smooth = False
                    marked += 1
        _SHARP_EDGE_COUNTS[name] = marked
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        mesh.materials.append(material)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        # SMOOTH, with the seam meridians marked sharp EXPLICITLY above —
        # not shade_auto_smooth(38 degrees) like add_loft.
        #
        # An angle test DISCOVERS which edges are sharp, and on this mesh
        # it discovers nonsense: the cap is a single-pole dome over a 3.2:1
        # section, so in one patch of the radial-volar quadrant the two
        # parameter directions run within 11 degrees of each other (1.6 at
        # worst, against an 89.7 median). Those quads are slivers, their
        # face normals are numerically undefined, and an angle test fed
        # undefined normals splits them — which rendered as a blocky
        # staircase across the thenar. add_loft can use the angle test
        # because machined plate has well-conditioned faces; this cannot.
        #
        # The parting line is at a KNOWN column, so it does not need
        # discovering. Marking it and smoothing everything else gives the
        # crisp arris without inventing edges out of noise. The creases do
        # not need it either: at 0.309 m wide they span about nine faces,
        # and smooth shading does not erase a groove wider than a face — it
        # only erases an arris. That was the real reason the 0.115 m crease
        # was invisible, and widening it is what fixed it.
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    obj.select_set(False)
    return obj


# ---------------------------------------------------------------------------
# The palm
# ---------------------------------------------------------------------------


class PalmSurface:
    """Analytic volume of the palm, wrist and hypothenar.

    The thenar eminence deliberately is NOT here: the muscles of the ball
    of the thumb move with the thumb, so they belong to the thumb part.
    The palm keeps only a shoulder on its radial side for the thumb's mass
    to land against, and the line where the two meet is the thenar crease
    — which is where a real hand has one, so the join reads as anatomy
    rather than as two objects.
    """

    #: Ring columns the seam is sized against. build_palm overwrites this
    #: with the grid it is actually building, so the two cannot drift.
    seam_divisions = 192

    def __init__(self, spec):
        self.spec = spec
        mm = spec._mm
        self.u_wrist_end = -mm(54.0)        # cut stump, buried in the collar
        # The LOFT ends short of the knuckle line; the distal cap covers the
        # remaining 18 mm (human) out to the metacarpal arc. Ending the loft
        # AT the arc left the cap 30 mm long on a 1.94 m half-width, which is
        # not a rounded end, it is a cliff — measured, and it looked like a
        # chopped loaf.
        self.u_knuckle = spec.PALM_LENGTH - mm(18.0)
        self.half_w = [
            (self.u_wrist_end, mm(24.0)),
            (-mm(36.0), mm(28.5)),
            (-mm(17.0), mm(32.5)),          # the styloid flare
            (0.0, spec.WRIST_WIDTH / 2.0),
            (mm(34.0), mm(36.5)),
            (mm(60.0), mm(41.5)),
            (mm(76.0), mm(43.4)),
            (self.u_knuckle, spec.PALM_WIDTH / 2.0),
        ]
        self.half_t = [
            (self.u_wrist_end, mm(20.5)),
            (-mm(36.0), mm(20.0)),
            (-mm(17.0), mm(19.4)),
            (0.0, spec.PALM_THICK_WRIST / 2.0),
            (mm(34.0), mm(16.2)),
            (mm(60.0), mm(14.6)),
            (mm(76.0), mm(13.6)),
            (self.u_knuckle, spec.PALM_THICK_MCP / 2.0),
        ]
        # A palm is boxier at the knuckles than at the wrist: the
        # metacarpal heads square the section off, the carpus rounds it.
        self.exponent = [(self.u_wrist_end, 2.15), (0.0, 2.35), (self.u_knuckle, 2.75)]

        # Metacarpal-head arc, as (v, u) pairs sorted by v, used to shape
        # the distal cap so the index knuckle sits further forward than the
        # little one — the single silhouette cue that says "hand".
        arc = []
        for name in spec.FINGER_ORDER:
            du, dv, _ = spec.mcp_local(name)
            arc.append((dv, du))
        self.mcp_arc = sorted(arc)
        self.web_mid = [
            ((a[0] + b[0]) / 2.0, min(a[1], b[1]))
            for a, b in zip(self.mcp_arc, self.mcp_arc[1:])
        ]
        # THE FIRST WEB SPACE. mcp_arc is the four fingers, so zipping it
        # against itself gives three webs and the thumb-index space — the
        # biggest and most visible fold on a hand — was never in the system
        # at all.
        # A web is not a dip. Between two fingers the skin runs FORWARD on the
        # palm side — that is the fold you pinch — and RETREATS on the back of
        # the hand, which is why you can see the knuckles from behind and not
        # from in front. One term, opposite signs, chosen by theta.
        # 6.0, not 12.0. See point(): 12 mm asked for more web than the
        # knuckle envelope has room for, and the clamp that used to cut the
        # difference back out cut a staircase into the skin doing it.
        self.web_forward = mm(6.0)
        self.web_back = mm(9.0)
        self.web_width = mm(13.0)
        # Past the outer metacarpals the palm rounds off instead of running
        # on square; without this the radial corner is a bare shelf sticking
        # out beyond the index knuckle.
        self.corner_inner = spec.PALM_WIDTH / 2.0 * 0.80
        self.corner_retreat = mm(8.0)

        # Palmar creases in (u, v) metres, converted from the human-mm
        # endpoints in the spec. Each entry is (points, half_width, depth).
        self.creases = []
        crease_w = mm(spec.CREASE_WIDTH_MM)
        crease_d = mm(spec.CREASE_DEPTH_MM)
        for _name, start, end in spec.PALM_CREASES:
            points = []
            for step in range(9):
                t = step / 8.0
                v_mm = _lerp(start[0], end[0], t)
                u_mm = _lerp(start[1], end[1], t)
                # A real crease bows; a straight chord across a 4 m palm
                # looks scribed. Bow it toward the fingers by an eighth of
                # its own length.
                bow = math.sin(math.pi * t) * 0.125
                span = math.hypot(end[0] - start[0], end[1] - start[1])
                points.append(
                    (spec.PALM_LENGTH + mm(u_mm + bow * span), mm(v_mm))
                )
            self.creases.append((points, crease_w, crease_d))

        # THE KNUCKLE ENVELOPE. Each finger's proximal cap is a sphere on
        # its MCP pivot; together they are what the palm's distal cap hides
        # behind. Precomputed here so point() can CLAMP to them rather than
        # hoping a tuned amplitude stays behind them — two rounds of tuning
        # the amplitude failed, because pushing the palm forward to fill the
        # web exposes the palm, it does not swallow the digits.
        self.balls = []
        for name in spec.FINGER_ORDER:
            du, dv, dn = spec.mcp_local(name)
            radius = (
                spec._mm(spec.FINGER_DIAMETER_MM[name]) / 2.0
                * (1.0 + spec.MCP_HEAD_SWELL)
            )
            self.balls.append((du, dv, dn, radius))
        # AND THE THUMB. Built from FINGER_ORDER this list had four entries,
        # so `ball_limit` returned -inf across the whole radial side: the
        # clamp suppressed the web bulge there and left the thumb shell
        # intersecting the palm's flank uncontrolled, which is a hard-edged
        # flap visible from the driver's seat.
        #
        # Its METACARPAL HEAD, not THUMB_ROOT_MM — the CMC is 76 mm proximal
        # of the knuckle line and covers nothing there. Walk the thumb ray to
        # THUMB_METACARPAL_FRAC of its length, which is where the head is.
        cmc_u, cmc_v, cmc_n = spec.thumb_cmc_local()
        ray = _to_local(spec, spec.DIGIT_RAYS["thumb"])
        along = spec._mm(spec.THUMB_LENGTH_MM) * spec.THUMB_METACARPAL_FRAC
        self.thumb_head = (
            cmc_u + ray.x * along,
            cmc_v + ray.z * along,
            cmc_n + ray.y * along,
            spec._mm(spec.THUMB_DIAMETER_MM) / 2.0 * (1.0 + spec.MCP_HEAD_SWELL),
        )
        # AND IT IS DELIBERATELY *NOT* IN self.balls, nor in web_mid.
        #
        # It was, for one round, on the reasoning that the first web space
        # needed a covering ball like the other three. It does not, and it
        # cannot have one: the thumb metacarpal head sits at u = 2.19 with a
        # radius of 0.81, so it tops out at u = 2.99 — 0.85 m SHORT of where
        # the distal cap even begins at u_knuckle = 3.84. It can never cover
        # a cap point, so `ball_limit` returned -inf across the whole first
        # web space and the clamp forced the fold to zero; and the web_mid it
        # implied sat at v = 2.01, outside the palm's own half-width of 1.94.
        # Five entries in a list, no geometric effect whatsoever.
        #
        # The thumb-index web is not in the cap AT ALL. The cap is u
        # 3.84-4.76; this web lives on the palm's radial FLANK around
        # u 2.2-3.4, which is radius()'s territory. See the thenar web term
        # there. Three rounds were spent trying to build it in cap_shape,
        # which is structurally the wrong function.

        # Where the distal cap converges. A parameterised closed surface has
        # to have a pole somewhere; this one is put a little past the MIDDLE
        # metacarpal head, which is inside that head's ball and therefore
        # inside the one digit guaranteed to cover it.
        middle_u = dict((v, u) for v, u in self.mcp_arc)[
            sorted(self.mcp_arc, key=lambda pair: abs(pair[0]))[0][0]
        ]
        self.cap_mean = middle_u + mm(3.0)
        self.cap_length = self.cap_mean - self.u_knuckle

    # -- profile ----------------------------------------------------------

    def ball_limit(self, v: float, n: float) -> float:
        """Furthest u the palm may reach at (v, n) and stay hidden.

        The SMOOTH union of the metacarpal heads' distal reaches, continued
        outside each sphere so the function is defined and continuous
        everywhere — where no knuckle covers the point the limit falls away
        below the dome, and the clamp zeroes the bulge, which is the same
        outcome the old -inf produced without the cliff that came with it.
        """

        best = None
        for du, dv, dn, radius in self.balls:
            offset = radius * radius - (v - dv) ** 2 - (n - dn) ** 2
            # THE SPHERE'S REACH CONTINUED OUTSIDE ITSELF, not -inf.
            #
            # Returning -inf where no ball covered the point made this a
            # STEP: one station inside a ball kept its web bulge and the
            # next station outside had it deleted outright, so the cap
            # dropped 0.17-0.26 m for a single row and climbed straight
            # back out. A one-row crater, with adjacent facet normals at
            # 173 degrees — the surface folded back on itself. It survived
            # three rounds because _grid_to_object smooth-shaded across it
            # and the fold was invisible; it appeared the moment the hand
            # got the same 38-degree auto-smooth as every other mesh.
            #
            # `du + sqrt(offset)` already tends to `du` as the point
            # approaches the boundary from inside, so continuing it as
            # `du - sqrt(-offset)` outside is the same function either
            # side. The limit now falls away smoothly, `headroom` crosses
            # zero instead of jumping to it, and the clamp still forbids
            # the palm emerging between two knuckles — which was the whole
            # point of it. A limit has to be a limit, not a switch.
            reach = du + math.copysign(math.sqrt(abs(offset)), offset)
            # A SMOOTH union, not `max`. The maximum of a set of spheres is
            # continuous but CREASED along every pairwise crossover, and the
            # clamp makes the surface follow this function exactly wherever
            # it binds — so those creases were being cut into the palm. On
            # the volar cap the limit ran 4.773 down to 4.676 and then
            # jumped back to 4.755 in one station as the max handed over
            # from one metacarpal head to the next: a V-notch 0.079 m deep,
            # inherited by the skin, adjacent facets at 172 degrees.
            #
            # Between two knuckles a hand has WEBBING, which is a fillet
            # standing slightly proud of both heads — which is precisely
            # what a soft-max gives, and it exceeds the hard max by at most
            # k*ln2 = 0.14 m. So the anatomy and the arithmetic want the
            # same function here, and the crease was never anything but an
            # artefact of writing the union the easy way.
            best = reach if best is None else _soft_max(best, reach, self.spec._mm(4.5))
        return best if best is not None else float("-inf")

    def cap_shape(self, theta: float, v: float) -> float:
        """How much further than the plain dome the palm reaches, in metres.

        This is the webbing and the rounded corners, and it is shaped so it
        CANNOT tent: the caller multiplies it by sin(phi)*cos(phi), which is
        zero at the knuckle ring and zero again at the pole, so every column
        still converges on one point however this varies with theta.

        The first version drove the cap's END POINT per theta off the
        metacarpal arc instead, which gave every column its own pole and
        folded the surface into hard triangular tents between the fingers.
        The second version deleted the tent by deleting the shaping — and
        then never called this function at all, so the fingers came out of
        a bare egg with no fold between them. This is the third.
        """

        volar = max(0.0, math.sin(theta))
        dorsal = max(0.0, -math.sin(theta))
        web = 0.0
        for v_mid, _u_mid in self.web_mid:
            web += _bump(v, v_mid, self.web_width)
        # Palm skin runs FORWARD between the knuckles — that is the fold you
        # pinch — and retreats on the back of the hand, which is why the
        # knuckles show from behind and not from in front.
        reach = web * (self.web_forward * volar - self.web_back * dorsal)
        # Past the outer metacarpals the palm rounds off instead of running
        # on square.
        span = max(1e-6, self.spec.PALM_WIDTH / 2.0 - self.corner_inner)
        reach -= self.corner_retreat * _smoothstep(
            (abs(v) - self.corner_inner) / span
        )
        return reach

    def cap_limit(self, v: float, theta: float = math.pi / 2.0) -> float:
        """Absolute distal reach at ``v``, for tests and for reporting."""

        arc = self.mcp_arc
        if v <= arc[0][0]:
            u = arc[0][1]
        elif v >= arc[-1][0]:
            u = arc[-1][1]
        else:
            u = arc[-1][1]
            for (v0, u0), (v1, u1) in zip(arc, arc[1:]):
                if v0 <= v <= v1:
                    u = _lerp(u0, u1, _smoothstep((v - v0) / (v1 - v0)))
                    break
        return u + self.cap_shape(theta, v)

    def radius(self, u: float, theta: float, *, with_flash: bool = True) -> tuple[float, float]:
        """Half-extents (radial, volar) of the section at ``u``, before the
        cap falloff. Returned as a pair so the superellipse stays honest
        about a palm being twice as wide as it is thick."""

        spec = self.spec
        mm = spec._mm
        half_a = _curve(self.half_w, u)
        half_b = _curve(self.half_t, u)
        exponent = _curve(self.exponent, u)
        a, b = _superellipse(theta, half_a, half_b, exponent)

        volar = max(0.0, math.sin(theta))
        dorsal = max(0.0, -math.sin(theta))
        ulnar = max(0.0, -math.cos(theta))
        radial = max(0.0, math.cos(theta))

        scale = 1.0
        # Hypothenar eminence: the pad along the little-finger edge. Peaks
        # volar-ulnar and dies out before the dorsal side, because there is
        # no muscle on the back of the hand.
        scale += (
            0.135
            * _angular_bump(theta, math.radians(133.0), math.radians(46.0))
            * _bump(u, mm(52.0), mm(42.0))
        )
        # THE FIRST WEB SPACE, built here on the flank because that is where
        # it is. The thumb metacarpal head sits at (u 2.19, v 2.95, n 1.17)
        # — a metre outside the palm's 1.94 half-width — and this term is
        # what reaches out to meet it. At 0.075 it was a token shoulder an
        # order of magnitude too small to bridge the gap, so the thumb
        # cylinder met an unswelled flank at a near-tangent angle, which is
        # exactly what produces a thin hard-edged sliver.
        #
        # Centred on the thumb head's own bearing rather than on a guessed
        # 34 degrees: atan2(n, v) of the head is 21.6 degrees.
        #
        # 0.75 is MEASURED, not chosen. 0.60 buried the shells by only 12%
        # of the ball radius, which still crosses them at about 28 degrees
        # and leaves a small hard-edged tab. A reviewer asked for 0.85 to
        # reach a -0.25 m overlap at a 46-degree crossing; swept, 0.85
        # actually lands at -0.330 m and 0.75 lands at -0.2471 m for a
        # 46.2-degree crossing — so 0.75 is the value that delivers the
        # geometry the request was justified by, and 0.85 was the estimate
        # standing in for it. Above ~0.90 the flank swells past 3.28 m and
        # the palm starts eating the thenar instead of meeting it.
        thumb_u, thumb_v, thumb_n, _thumb_r = self.thumb_head
        scale += (
            0.75
            * _angular_bump(theta, math.atan2(thumb_n, thumb_v), math.radians(36.0))
            * _bump(u, thumb_u, mm(30.0))
        )
        # The palmar hollow. A flat palm is the giveaway of a generated
        # hand; the cup sits slightly ulnar of centre and distal of middle.
        scale -= (
            0.105
            * _angular_bump(theta, math.radians(97.0), math.radians(34.0))
            * _bump(u, mm(72.0), mm(24.0))
        )
        # Dorsal metacarpal ridges: the extensor tendons standing proud
        # between the metacarpals. Four shallow ridges, strongest near the
        # knuckles, gone by the wrist.
        for index, name in enumerate(spec.FINGER_ORDER):
            _du, dv, _dn = spec.mcp_local(name)
            half_a_knuckle = _curve(self.half_w, self.u_knuckle)
            ratio = max(-1.0, min(1.0, dv / half_a_knuckle))
            ridge_theta = math.pi + math.acos(max(-1.0, min(1.0, -ratio)))
            scale += (
                (0.075 - 0.008 * index)
                * dorsal
                * _angular_bump(theta, ridge_theta, math.radians(13.0))
                * _bump(u, mm(78.0), mm(30.0))
            )
        # Wrist tendons on the volar side, and the ulnar styloid knob.
        scale += 0.030 * volar * _bump(u, -mm(14.0), mm(11.0))
        scale += 0.055 * ulnar * _bump(u, -mm(9.0), mm(9.0))
        scale += 0.020 * radial * _bump(u, -mm(11.0), mm(10.0))

        a *= scale
        b *= scale

        # The parting line. Added AFTER the eminences so it rides over them
        # the way real flash does, and signed off cos(theta) so it stands
        # proud on both edges rather than pulling one of them in.
        flash = _parting_seam(spec, theta, u, self.seam_divisions) if with_flash else 0.0
        if flash > 0.0:
            a += math.copysign(flash, math.cos(theta) if abs(math.cos(theta)) > 1e-9 else 1.0)

        # Creases, applied along the surface INWARD, only on the volar
        # side, and faded where the palm turns over the edge so a life
        # line does not wrap round onto the back of the hand.
        if volar > 0.02:
            # 0.30 at the equator rising to 1.0 at the volar pole. A plain
            # volar**1.35 took the distal transverse crease down to 20% of
            # its depth at the ulnar end — where it is most visible on the
            # reference — because that end sits at theta ~= 162 degrees.
            mask = 0.30 + 0.70 * volar ** 1.2
            v_here = a
            for points, width, depth in self.creases:
                distance = _polyline_distance(u, v_here, points)
                if distance < width * 3.0:
                    # ^4, not ^2. A gaussian over a 0.2 m half-width is a
                    # dish with a shallow gradient, and smooth shading
                    # averages the normals straight across it — a 39%
                    # dent that whispers. The quartic keeps a flat floor
                    # and steepens the walls, which is what a crease is.
                    dip = depth * math.exp(-((distance / width) ** 4)) * mask
                    b -= dip
        return a, b

    def point(self, s: float, theta: float, *, with_flash: bool = True) -> Vector:
        """Surface point. ``s`` runs 0 at the cut stump to 1 at the tip of
        the distal cap; the cap portion is reparameterised per-theta so the
        knuckle arc and the webs come out of the same expression."""

        cap_start = 0.74
        if s <= cap_start:
            u = _lerp(self.u_wrist_end, self.u_knuckle, s / cap_start)
            a, b = self.radius(u, theta, with_flash=with_flash)
            return Vector((u, b, a))

        # THE DISTAL CAP IS A PLAIN HALF-ELLIPSOID, and that is a decision.
        #
        # The first version drove the cap's reach per-theta off the
        # metacarpal arc, so the palm itself carried the knuckle arc and the
        # webs. It pleated: every theta had its own end point, the ring had
        # to converge on one of them, and the surface folded into hard
        # triangular tents between the fingers (measured on the web
        # elevations, and unmissable).
        #
        # The arc does not need to be here. The five DIGITS each carry a
        # metacarpal-head ball (MCP_HEAD_SWELL) at their own pivot, and those
        # balls are tangent to each other and fatter than the palm is thick,
        # so the row of heads IS the knuckle arc — measured coverage runs
        # v +1.63 to -2.31 against a palm half-width of 1.94. Whatever the
        # palm does under them is invisible. So it does the one thing that
        # cannot pleat: it closes smoothly on a single pole, and that pole is
        # placed inside the middle head's ball.
        frac = (s - cap_start) / (1.0 - cap_start)
        # WITHOUT the flash, which is re-added below at full height.
        a0, b0 = self.radius(self.u_knuckle, theta, with_flash=False)
        phi = frac * math.pi / 2.0
        # The only asymmetry kept is the real one: palm skin runs further
        # forward between the knuckles than the skin on the back of the hand
        # does. sin(phi)*cos(phi) vanishes at BOTH ends, so it bulges the
        # flank of the dome without moving the pole and cannot tent.
        shrink = math.cos(phi)
        a, b = a0 * shrink, b0 * shrink
        # THE FLASH DOES NOT SHRINK WITH THE DOME. It was folded into a0
        # and then scaled by `shrink` along with the section, so the bead
        # faded out toward the pole exactly where the cap turns over — the
        # crest dihedral fell to 26.8 degrees over stations 178-189 while
        # the rest of the meridian held 48. A mould gap is a constant; the
        # fin it leaves is the same height wherever the parting plane cuts,
        # and the one place it must NOT thin is where the form rolls away
        # from the camera and the line is all you can see of the edge.
        #
        # ...but it MUST still vanish into the pole. Held at full height all
        # the way, the bead does not collapse when the ring does: the cap
        # ended on a SEGMENT 0.126 m long instead of a point, with seam
        # facets at 155-165 degrees over the last six stations. That is the
        # flat triangular beak DigitSurface.point describes at length and
        # test_digit_tips_converge_on_a_point asserts against — reproduced
        # on the one part that test does not cover, by the fix for the
        # opposite problem. So the taper is confined to the last 8% of the
        # cap rather than smeared over all of it as `shrink` was doing.
        cap_flash = (
            _parting_seam(self.spec, theta, self.u_knuckle, self.seam_divisions)
            if with_flash else 0.0
        )
        cap_flash *= _smoothstep(min(1.0, (1.0 - frac) / 0.08))
        if cap_flash > 0.0:
            cosine = math.cos(theta)
            a += math.copysign(cap_flash, cosine if abs(cosine) > 1e-9 else 1.0)
        dome = self.cap_length * math.sin(phi)
        shaped = self.cap_shape(theta, a0) * (math.sin(phi) * math.cos(phi))
        # NO SAMPLE-TIME CLAMP. There was one, and it was the single
        # worst thing in this file.
        #
        # It limited the bulge to `ball_limit` wherever that bound, which
        # makes the SURFACE track a level set of a function that knows
        # nothing about the grid. Walking a column weaves in and out of the
        # binding region, so the volar cap came out as a ragged staircase
        # with adjacent facets up to 177 degrees apart — a fold, in the
        # skin, for three rounds, invisible only because _grid_to_object
        # smooth-shaded across it. Softening the min made it worse (a
        # soft-min undershoots zero, which stepped the whole cap back at
        # the loft junction); softening the union helped the notch but not
        # the tracking; reducing the amplitude under the clamp did nothing
        # at all, 226 quads to 170 across a 3x sweep.
        #
        # The constraint was never sample-time. `web_forward` at 12 mm
        # simply asked for more bulge than the knuckle envelope has room
        # for, and the clamp was cutting the difference back out again at
        # every sample. At 6 mm the envelope is satisfied BY CONSTRUCTION
        # — measured excess -0.008 m against the 0.02 m the gate allows —
        # and the staircase is gone: 15 quads over the auto-smooth angle,
        # worst 46 degrees, all of them real web edges.
        #
        # `ball_limit` stays, because the gate uses it to check exactly
        # this property. A limit is for ASSERTING against, not for
        # dragging a surface along.
        return Vector((self.u_knuckle + dome + shaped, b, a))


def build_palm(spec, name: str, material, *, divisions: int = 192, stations: int = 224):
    """Closed palm/wrist shell as one quad grid, with metric UVs."""

    surface = PalmSurface(spec)
    surface.seam_divisions = divisions
    tile = spec.SKIN_METERS_PER_TILE
    rings: list[list[Vector]] = []
    uvs: list[list[tuple[float, float]]] = []

    # ONE ring is measured to choose the tile COUNT, and then every ring
    # carries its own perimeter. The count is rounded to a whole number so
    # the duplicated seam column lands exactly one tile from its twin — the
    # entire reason the seam column is duplicated in the first place.
    reference = 0.0
    samples = 96
    for step in range(samples):
        theta = TWO_PI * step / samples
        a, b = surface.radius(surface.u_knuckle * 0.55, theta)
        reference += math.hypot(a, b) * TWO_PI / samples
    u_tiles = max(1, round(reference / tile))

    previous = None
    length = 0.0
    for station in range(stations + 1):
        s = station / stations
        ring = []
        for column in range(divisions + 1):
            theta = TWO_PI * (column % divisions) / divisions
            ring.append(surface.point(s, theta))
        centre = Vector((ring[0].x, 0.0, 0.0))
        rings.append(ring)
        # Per-ring perimeter: a wrist is ~82% of the widest section, so a
        # single circumference for all 224 stations stretched the pores by
        # nearly a fifth from one end of the palm to the other.
        perimeter = sum((b - a).length for a, b in zip(ring, ring[1:])) or 1e-6
        scale = perimeter / max(reference, 1e-6)
        if previous is not None:
            length += (centre - previous).length / scale
        previous = centre
        # THE PER-RING COMPENSATION GOES IN V, NOT IN U.
        #
        # In u it broke the seam it was meant to serve: for the duplicated
        # seam column to land one tile from its twin, u_tiles * scale must
        # be a WHOLE number, and it only is on the one ring where scale is
        # exactly 1. Everywhere else the seam sat a fraction of a tile out,
        # and because scale varies along the piece the fraction varied too —
        # so the constant seam LINE became a smear that opened and closed.
        #
        # The two goals genuinely conflict on a tapering closed surface with
        # one chart: u can be seamless or constant-density, not both.
        # Seamless wins, and the density moves to v, which has no seam to
        # break. Dividing the arc step by scale keeps texels SQUARE at every
        # station: the pore SIZE drifts gently along the piece, which nobody
        # sees, while the stretch and the seam, which everybody sees, both
        # go away.
        # v divided by the part's OWN realised pitch (reference/u_tiles),
        # not by the nominal tile: u-density is u_tiles/perimeter and
        # v-density was reference/(perimeter*tile), so texels were only
        # square where round(reference/tile) happened to equal
        # reference/tile. Measured, the middle finger's were 23% wider than
        # tall and the thumb's 29% taller than wide — in opposite
        # directions, on the same hand.
        uvs.append(
            [
                (u_tiles * (column / divisions), length * u_tiles / reference)
                for column in range(divisions + 1)
            ]
        )
    return _grid_to_object(
        name, rings, uvs, cap_start=True, cap_end=False, material=material,
        # The two mould meridians: theta = 0 and theta = pi. Column 0 is
        # the duplicated seam column, so its twin at `divisions` is the
        # same place and gets marked too — otherwise the line is crisp on
        # one side of the UV seam and soft on the other.
        sharp_columns=(0, divisions // 2, divisions),
    )


# ---------------------------------------------------------------------------
# Digits
# ---------------------------------------------------------------------------


class DigitSurface:
    """One finger or thumb as a swept solid with a ball-ended root.

    The spine is walked joint by joint: each flexion is applied to the
    running direction BEFORE its segment is laid down, so the curl
    accumulates exactly the way a finger's does. Sections are superellipses
    that flatten dorsally under the nail and carry a volar pulp pad that
    grows toward the tip.
    """

    #: Ring columns the seam is sized against; build_digit overwrites it.
    seam_divisions = 112

    def __init__(
        self,
        spec,
        *,
        pivot: Vector,
        ray: Vector,
        axis: Vector,
        segments: list[float],
        curls: list[float],
        diameter: float,
        is_thumb: bool = False,
        thenar: float = 0.0,
    ):
        self.spec = spec
        self.pivot = pivot
        self.axis = axis.normalized()
        self.radius0 = diameter / 2.0
        self.is_thumb = is_thumb
        self.thenar = thenar
        self.total = sum(segments)

        # Sample the spine densely so arc length, direction and section
        # frame all come from one walk.
        # THE CURL IS SPREAD OVER THE JOINT, not applied at a point.
        #
        # It used to turn the direction by the whole flexion angle and then
        # lay the phalanx down straight, which made the direction field
        # piecewise-constant — and, worse, emitted the last sample of one
        # segment and the first of the next at the SAME arc length. So
        # frame()'s `span` was zero there and its lerp was a no-op: the
        # section frame rotated instantaneously at every joint, and the
        # volar surface stepped 65-123 mm BACKWARD against a station pitch
        # of 21-33 mm. That is not a sharp crease, it is the strip passing
        # through itself, on all five digits at both joints, with facet
        # normals 179.9 degrees apart. Smooth shading hid every bit of it.
        #
        # Turning through the joint over a window instead is also the
        # anatomy: a finger bends around a condyle of real radius, it does
        # not hinge on a mathematical point. Arc lengths now increase
        # strictly, so frame() interpolates as it always meant to.
        self.spine: list[tuple[float, Vector, Vector]] = []
        position = pivot.copy()
        direction = ray.normalized()
        travelled = 0.0
        per_segment = 48
        self.spine.append((0.0, position.copy(), direction.copy()))
        for length, curl in zip(segments, curls):
            step_length = length / per_segment
            turning = max(1, round(per_segment * JOINT_ARC_FRACTION))
            for step in range(1, per_segment + 1):
                if step <= turning:
                    direction = _rodrigues(
                        direction, self.axis, curl / turning
                    ).normalized()
                position = position + direction * step_length
                travelled += step_length
                self.spine.append((travelled, position.copy(), direction.copy()))
        # Joint boundaries as fractions along the whole digit, for the
        # knuckle swells and the flexion creases.
        self.joints = []
        running = 0.0
        for length in segments[:-1]:
            running += length
            self.joints.append(running / self.total)

    # -- profile ----------------------------------------------------------

    def frame(self, t: float) -> tuple[Vector, Vector, Vector, Vector]:
        """(position, direction, width axis, volar axis) at fraction t."""

        target = t * self.total
        lo, hi = self.spine[0], self.spine[-1]
        for a, b in zip(self.spine, self.spine[1:]):
            if a[0] <= target <= b[0]:
                lo, hi = a, b
                break
        span = hi[0] - lo[0]
        blend = (target - lo[0]) / span if span > 1e-9 else 0.0
        position = lo[1].lerp(hi[1], blend)
        direction = lo[2].lerp(hi[2], blend).normalized()
        width = self.axis
        volar = width.cross(direction).normalized()
        return position, direction, width, volar

    def profile(self, t: float, theta: float) -> tuple[float, float]:
        """SIGNED section coordinates at fraction t and angle theta.

        Not half-extents: _superellipse already folds the angle in, so the
        pair returned is the offset along (width, volar) directly. Treating
        it as a radius and multiplying by cos/sin again mirrors the whole
        dorsal half onto the volar one, and every digit came out as a flat
        half-tube a third of its proper width.
        """

        spec = self.spec
        mm = spec._mm
        if self.is_thumb:
            taper = _curve(
                [(0.0, 1.34), (0.16, 1.18), (0.42, 1.05), (0.70, 1.00),
                 (0.90, 0.95), (1.0, 0.86)],
                t,
            )
        else:
            # Near-cylindrical on purpose. Measured on the reference prop
            # the middle finger is 0.267 of its own length thick at the
            # base and still 0.244 at the tip; the first taper took it from
            # 0.233 to 0.187, which is a cone, and the fingers read spindly
            # against a palm this wide.
            taper = _curve(
                [(0.0, 1.0), (0.20, 0.975), (0.45, 0.950), (0.62, 0.935),
                 (0.77, 0.920), (0.90, 0.905), (1.0, 0.88)],
                t,
            )
        scale = taper
        # Knuckle swells at every interphalangeal joint. A finger without
        # them is a hose.
        for index, joint in enumerate(self.joints):
            scale += (0.085 - 0.012 * index) * _bump(t, joint, 0.045)
        # The metacarpal head, at t = 0, is the biggest of them: it is wider
        # than the phalanx behind it, it is what stands proud as a knuckle,
        # and — because the proximal ball inherits this profile — it is what
        # covers the palm's distal end so the two never show a gap.
        scale += spec.MCP_HEAD_SWELL * _bump(t, 0.0, 0.075)
        # Thenar mass, thumb only: the ball of the thumb is a muscle, so it
        # is on the volar-radial quadrant of the metacarpal and nowhere
        # else. Modelled here rather than on the palm because it MOVES with
        # the thumb.
        if self.thenar > 0.0:
            scale += (
                self.thenar
                * _angular_bump(theta, math.radians(70.0), math.radians(62.0))
                * _bump(t, 0.20, 0.20)
            )

        half = self.radius0 * scale
        exponent = _curve([(0.0, 2.1), (0.5, 2.35), (1.0, 2.6)], t)
        # A finger is slightly wider than deep, and flatter on the back.
        a, b = _superellipse(theta, half * 1.03, half * 0.97, exponent)

        volar = max(0.0, math.sin(theta))
        dorsal = max(0.0, -math.sin(theta))
        # Volar pulp: the pad grows toward the tip, which is what makes a
        # fingertip read as soft.
        b *= 1.0 + 0.20 * volar * _curve([(0.0, 0.2), (0.5, 0.5), (0.86, 1.0), (1.0, 0.8)], t)
        # The nail BED: not just a flattening, a real recess, so the plate
        # sits IN the finger. Without it the nail is a chiclet glued on.
        bed = _curve([(0.0, 0.0), (0.72, 0.2), (0.86, 1.0), (1.0, 1.0)], t)
        b *= 1.0 - 0.13 * dorsal * bed
        b -= (
            self.radius0 * 0.055 * bed
            * _angular_bump(theta, 3.0 * math.pi / 2.0, math.radians(50.0))
        )

        # The parting line runs the digit too, from its root over the tip.
        flash = _parting_seam(spec, theta, t * self.total, self.seam_divisions)
        if flash > 0.0:
            a += math.copysign(flash, math.cos(theta) if abs(math.cos(theta)) > 1e-9 else 1.0)

        # Flexion creases across the volar side of each joint, plus the
        # doubled crease at the base. Straight out of spec.JOINT_CREASES,
        # whose fractions are measured on the digit chain.
        if volar > 0.02:
            mask = 0.30 + 0.70 * volar ** 1.15
            for fraction, width_mm, depth_mm in spec.JOINT_CREASES:
                # Fractions are authored against a three-phalanx finger; a
                # two-phalanx thumb uses its own joints instead.
                if self.is_thumb and fraction > 0.1:
                    continue
                distance = abs(t - fraction) * self.total
                width = mm(width_mm)
                if distance < width * 3.0:
                    b -= mm(depth_mm) * math.exp(-((distance / width) ** 4)) * mask
            # NO second loop over self.joints. PHALANX_SPLIT (0.45, 0.32,
            # 0.23) makes self.joints exactly [0.45, 0.77], which are two of
            # the three fractions spec.JOINT_CREASES already carries — so
            # creasing both stacked a doubled groove on the PIP and DIP and
            # left the MCP shallowest, which is backwards, and put a groove
            # in the middle of each knuckle swell. Sausage links. The thumb
            # gets its own two joints instead, because its chain is a
            # metacarpal plus two phalanges and JOINT_CREASES is authored
            # against a finger.
            if self.is_thumb:
                for joint in self.joints:
                    distance = abs(t - joint) * self.total
                    width = mm(3.6)
                    if distance < width * 3.0:
                        b -= mm(2.0) * math.exp(-((distance / width) ** 4)) * mask
        return a, b

    def point(self, s: float, theta: float) -> Vector:
        """Surface point. ``s`` in [0, 1] covers the proximal BALL, the
        shaft and the tip dome in one parameter."""

        ball = 0.13
        tip = 0.90
        if s < ball:
            # Hemisphere centred exactly on the joint pivot. Rotating this
            # about the pivot moves no surface point, which is the whole
            # reason the digit can be a separate part at all: the line
            # where it emerges from the palm stays put however far it
            # flexes, so the knuckle never opens a gap.
            frac = s / ball
            angle = (1.0 - frac) * math.pi / 2.0
            _position, direction, width, volar = self.frame(0.0)
            a, b = self.profile(0.0, theta)
            ring = math.cos(angle)
            return (
                self.pivot
                - direction * (math.sin(angle) * self.radius0)
                + width * (a * ring)
                + volar * (b * ring)
            )
        if s <= tip:
            t = (s - ball) / (tip - ball)
            position, _direction, width, volar = self.frame(t)
            a, b = self.profile(t, theta)
            return position + width * a + volar * b

        frac = (s - tip) / (1.0 - tip)
        position, direction, width, volar = self.frame(1.0)
        a, b = self.profile(1.0, theta)
        angle = frac * math.pi / 2.0
        ring = math.cos(angle)
        # A fingertip is not a hemisphere: it reaches further on the volar
        # (pulp) side than over the nail. But the ASYMMETRY MUST VANISH AT
        # THE POLE, and getting that wrong is the same mistake the palm cap
        # made and documents at length.
        #
        # The first version was `direction * sin(angle) * reach(theta)`.
        # At angle = pi/2 the ring collapses, so every column lands on
        # `position + direction * reach(theta)` — and reach depended on
        # theta, so the pole was not a point, it was a segment 0.30*r0 long
        # (159 mm on the index, 192 mm on the thumb). Every digit ended in a
        # flat triangular beak on its volar side.
        #
        # sin(angle)*cos(angle) is zero at BOTH ends, so the pulp still
        # bulges on the flank of the dome and every column converges on one
        # point. test_digit_tips_converge_on_a_point asserts it.
        reach = self.radius0 * (
            0.95 * math.sin(angle)
            + 0.30 * max(0.0, math.sin(theta)) * math.sin(angle) * math.cos(angle)
        )
        return (
            position
            + direction * reach
            + width * (a * ring)
            + volar * (b * ring)
        )


def build_digit(
    spec, name: str, surface: DigitSurface, material, *, divisions=112, stations=176
):
    surface.seam_divisions = divisions
    tile = spec.SKIN_METERS_PER_TILE
    # 2*pi*radius0 is neither the digit's perimeter nor constant along it:
    # the metacarpal head swells 26% and the shaft tapers to 88%, and the
    # volar pulp is not in the circle at all. Same treatment as the palm —
    # a whole number of tiles around, and each ring measured.
    reference = TWO_PI * surface.radius0
    u_tiles = max(1, round(reference / tile))
    rings: list[list[Vector]] = []
    uvs: list[list[tuple[float, float]]] = []
    previous = None
    length = 0.0
    for station in range(stations + 1):
        s = station / stations
        ring = [
            surface.point(s, TWO_PI * (column % divisions) / divisions)
            for column in range(divisions + 1)
        ]
        centre = sum(ring[:-1], Vector((0.0, 0.0, 0.0))) / max(1, len(ring) - 1)
        rings.append(ring)
        perimeter = sum((b - a).length for a, b in zip(ring, ring[1:])) or 1e-6
        scale = perimeter / max(reference, 1e-6)
        if previous is not None:
            length += (centre - previous).length / scale
        previous = centre
        # Same law as the palm; see build_palm.
        uvs.append(
            [
                (u_tiles * (column / divisions), length * u_tiles / reference)
                for column in range(divisions + 1)
            ]
        )
    return _grid_to_object(
        name, rings, uvs, cap_start=False, cap_end=False, material=material,
        sharp_columns=(0, divisions // 2, divisions),
    )


def build_nail(spec, name: str, surface: DigitSurface, material, *, divisions=44, stations=34):
    """The nail plate, sampled off the digit's OWN surface and pushed out
    along its own normal.

    Sampling the same analytic function the finger is built from is what
    guarantees the nail sits ON the finger — a separately-authored plate
    would float or sink the moment any profile constant changed. The plate
    is a closed slab: top face proud of the bed, a skirt down to it, and
    the bed itself as the underside.
    """

    mm = spec._mm
    proud = mm(spec.NAIL_PROUD_MM)
    wrap = math.radians(spec.NAIL_WRAP_DEG)
    length = mm(spec.NAIL_LENGTH_MM)
    inset = mm(spec.NAIL_INSET_MM)

    # Fractions along the digit that bracket the nail: it ends `inset`
    # short of the fingertip so the pulp shows past it.
    s_end = 0.90 - inset / surface.total
    s_start = s_end - length / surface.total
    dorsal = 3.0 * math.pi / 2.0

    def sample(su: float, sv: float):
        """su across the nail (-1..1), sv along it (0..1)."""

        s = _lerp(s_start, s_end, sv)
        theta = dorsal + su * wrap / 2.0
        base = surface.point(s, theta)
        step_t = 0.004
        step_a = 0.02
        du = surface.point(min(1.0, s + step_t), theta) - surface.point(
            max(0.0, s - step_t), theta
        )
        dv = surface.point(s, theta + step_a) - surface.point(s, theta - step_a)
        normal = dv.cross(du)
        if normal.length < 1e-9:
            normal = Vector((0.0, -1.0, 0.0))
        normal.normalize()
        # Point the normal away from the spine.
        position, _direction, _width, _volar = surface.frame(s)
        if normal.dot(base - position) < 0.0:
            normal = -normal
        return base, normal

    # A nail is thickest in the middle and thins to nothing at its edges,
    # otherwise it reads as a fingernail-shaped tile stuck on.
    def lift(su: float, sv: float) -> float:
        edge = 1.0 - min(1.0, abs(su)) ** 3.0
        # A nail emerges from a FOLD, so the proximal fifth of the plate
        # climbs out of the bed rather than starting proud of it.
        root = _smoothstep(min(1.0, sv / 0.20))
        free = 1.0 - 0.25 * _smoothstep(max(0.0, (sv - 0.86) / 0.14))
        return proud * edge * root * free

    top_rings: list[list[Vector]] = []
    bed_rings: list[list[Vector]] = []
    uvs: list[list[tuple[float, float]]] = []
    for station in range(stations + 1):
        sv = station / stations
        # The free edge of a nail is an arc, not a straight cut.
        top_row, bed_row, uv_row = [], [], []
        for column in range(divisions + 1):
            su = -1.0 + 2.0 * column / divisions
            arc = 1.0 - 0.22 * (su * su)
            base, normal = sample(su, sv * arc)
            bed_row.append(base + normal * (proud * 0.06))
            top_row.append(base + normal * lift(su, sv * arc))
            uv_row.append((0.5 + 0.5 * su, sv))
        top_rings.append(top_row)
        bed_rings.append(bed_row)
        uvs.append(uv_row)

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    top = [[bm.verts.new(point) for point in row] for row in top_rings]
    bed = [[bm.verts.new(point) for point in row] for row in bed_rings]
    bm.verts.ensure_lookup_table()
    # index_update, not just ensure_lookup_table: a freshly created BMVert
    # carries index -1 until this runs, so a degeneracy test written against
    # .index silently rejected EVERY face and exported a mesh of nothing but
    # its end caps.
    bm.verts.index_update()

    def quad(a, b, c, d, coords):
        try:
            face = bm.faces.new((a, b, c, d))
        except ValueError:
            return
        for loop, coord in zip(face.loops, coords):
            loop[uv_layer].uv = coord

    for row in range(stations):
        for column in range(divisions):
            quad(
                top[row][column], top[row + 1][column],
                top[row + 1][column + 1], top[row][column + 1],
                (uvs[row][column], uvs[row + 1][column],
                 uvs[row + 1][column + 1], uvs[row][column + 1]),
            )
            quad(
                bed[row][column + 1], bed[row + 1][column + 1],
                bed[row + 1][column], bed[row][column],
                (uvs[row][column + 1], uvs[row + 1][column + 1],
                 uvs[row + 1][column], uvs[row][column]),
            )
    for row in range(stations):
        quad(
            top[row][0], bed[row][0], bed[row + 1][0], top[row + 1][0],
            (uvs[row][0], uvs[row][0], uvs[row + 1][0], uvs[row + 1][0]),
        )
        quad(
            bed[row][divisions], top[row][divisions],
            top[row + 1][divisions], bed[row + 1][divisions],
            (uvs[row][divisions], uvs[row][divisions],
             uvs[row + 1][divisions], uvs[row + 1][divisions]),
        )
    for column in range(divisions):
        quad(
            bed[0][column], top[0][column], top[0][column + 1], bed[0][column + 1],
            (uvs[0][column], uvs[0][column], uvs[0][column + 1], uvs[0][column + 1]),
        )
        quad(
            top[stations][column], bed[stations][column],
            bed[stations][column + 1], top[stations][column + 1],
            (uvs[stations][column], uvs[stations][column],
             uvs[stations][column + 1], uvs[stations][column + 1]),
        )

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        mesh.materials.append(material)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        # The angle test is kept HERE and nowhere else in this module.
        #
        # It is wrong for the palm and the digits — see _grid_to_object,
        # whose cap carries sliver quads whose face normals are noise, and
        # which an angle test duly split into a staircase. A nail plate is
        # neither: it is a small well-conditioned grid whose rim is a real
        # geometric edge standing proud of the bed, exactly what an angle
        # test is for.
        #
        # (This comment used to argue the opposite and cite the palmar
        # creases, which are now 0.309 m wide and read under plain smooth
        # shading. Left as a marker: the reasoning that put auto-smooth on
        # the hand was reversed, and only the nail kept it.)
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        try:
            bpy.ops.object.shade_smooth()
        except Exception:
            pass
    obj.select_set(False)
    return obj


# ---------------------------------------------------------------------------
# Digit factory
# ---------------------------------------------------------------------------


def _to_local(spec, authored) -> Vector:
    """Authored-frame direction -> this module's hand-local (u, n, v).

    The two frames are related by an orthonormal basis, so projecting is
    just three dot products. Going through here means spec.py owns every
    ray and axis and the generator cannot hold a second opinion about any
    of them.
    """

    vector = Vector(authored)
    return Vector(
        (
            vector.dot(Vector(spec.U_REST)),
            vector.dot(Vector(spec.N_REST)),
            vector.dot(Vector(spec.V_REST)),
        )
    ).normalized()


def digit_surfaces(spec) -> dict[str, DigitSurface]:
    """Every digit's swept solid, in the hand-local frame."""

    mm = spec._mm
    surfaces: dict[str, DigitSurface] = {}

    for name in spec.FINGER_ORDER:
        du, dv, dn = spec.mcp_local(name)
        # Local frame: +x = u, +y = n, +z = v. Splay turns the ray about the
        # palm normal; the sign lives in spec.finger_ray_dir, and it is
        # projected in here rather than repeated, for the reason given on
        # the thumb below.
        ray = _to_local(spec, spec.DIGIT_RAYS[name])
        axis = _to_local(spec, spec.DIGIT_AXES[name])
        total = mm(spec.FINGER_LENGTH_MM[name])
        segments = [total * share for share in spec.PHALANX_SPLIT]
        curls = [math.radians(value) for value in spec.FINGER_CURL_DEG[name]]
        surfaces[name] = DigitSurface(
            spec,
            pivot=Vector((du, dn, dv)),
            ray=ray,
            axis=axis,
            segments=segments,
            curls=curls,
            diameter=mm(spec.FINGER_DIAMETER_MM[name]),
        )

    du, dv, dn = spec.thumb_cmc_local()
    # Projected from spec, never re-derived here. Both files used to build
    # the thumb frame independently and they drifted: the mesh took the
    # corrected palmar sign and the pronation, spec.py — which is what gets
    # formatted into the shipped Lua — kept neither, so the runtime flexed
    # the thumb about an axis that was not even perpendicular to its shaft.
    ray = _to_local(spec, spec.DIGIT_RAYS["thumb"])
    axis = _to_local(spec, spec.DIGIT_AXES["thumb"])
    total = mm(spec.THUMB_LENGTH_MM)
    metacarpal = total * spec.THUMB_METACARPAL_FRAC
    rest = total - metacarpal
    segments = [metacarpal, rest * spec.THUMB_SPLIT[0], rest * spec.THUMB_SPLIT[1]]
    curls = [math.radians(-6.0)] + [math.radians(value) for value in spec.THUMB_CURL_DEG]
    surfaces["thumb"] = DigitSurface(
        spec,
        pivot=Vector((du, dn, dv)),
        ray=ray,
        axis=axis,
        segments=segments,
        curls=curls,
        diameter=mm(spec.THUMB_DIAMETER_MM),
        is_thumb=True,
        thenar=0.62,
    )
    return surfaces


def hand_to_world(spec) -> Matrix:
    """Hand-local (u, n, v) -> authored frame, translated to the wrist.

    Columns are u, n, v IN THAT ORDER because (u, n, v) is right-handed
    while (u, v, n) is not: n = v x u, so u x v = -n and a [u|v|n] matrix
    would be a reflection that inverts every normal on the prop.
    """

    u = Vector(spec.U_REST)
    n = Vector(spec.N_REST)
    v = Vector(spec.V_REST)
    basis = Matrix((
        (u.x, n.x, v.x),
        (u.y, n.y, v.y),
        (u.z, n.z, v.z),
    )).to_4x4()
    return Matrix.Translation(Vector(spec.WRIST_POINT)) @ basis

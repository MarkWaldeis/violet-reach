"""Driftward: eroded limestone, exposed fault planes and a wind-swept summit."""
import math
import random

import bpy
from mathutils import Vector, noise

import vrlib
import vrmat

SEED = 86347
TOP, KEEL = 149, 0
RX, RY = 125, 77
N = 448

# Depth, width. The throat retreats under an overhang before the oblique keel.
PROFILE = (
    (0, 1), (.06, 1.025), (.14, .98), (.23, .92), (.34, .77),
    (.47, .64), (.57, .57), (.68, .43), (.77, .34),
    (.87, .25), (.94, .14), (1, 0),
)
# Depth, thickness, projection in metres, azimuth, lateral extent.
BEDS = (
    (.041, .023, 5.8, .5, 2.0), (.106, .046, 8.4, 1.1, 1.5),
    (.168, .018, 3.7, -1.5, 1.3), (.224, .050, 10.5, -1.0, 1.8),
    (.272, .022, 4.4, 2.2, 1.4), (.349, .038, 8.2, .3, 1.45),
    (.405, .016, 2.7, 2.2, 1.45), (.487, .056, 7.5, 2.8, 1.6),
    (.591, .027, 5.5, -.8, 1.3), (.665, .061, 7.1, .7, 1.2),
    (.796, .034, 4.7, -2.5, 1.6),
)
# Fault grooves split the beds into uneven promontories, rather than closed rings.
FAULTS = (
    (-2.84, .034, 8.3, -.73), (-2.08, .056, 12.5, .76), (-1.24, .030, 9.8, -.45),
    (-.43, .026, 7.2, .44), (.43, .053, 16, .57), (1.29, .029, 8.7, -.41),
    (2.04, .068, 14, -.48), (2.61, .027, 6.5, .34),
)


def smooth(t):
    t = min(1, max(0, t))
    return t * t * (3 - 2 * t)


def angle_delta(a, b):
    return math.atan2(math.sin(a - b), math.cos(a - b))


def n3(x, y, z):
    return noise.noise(Vector((x, y, z)), noise_basis="PERLIN_ORIGINAL")


def voronoi_seam(x, y, z):
    distances, _ = noise.voronoi(Vector((x, y, z)))
    return distances[1] - distances[0]


def palette():
    return {name: data["linear_rgb"] for name, data in vrmat.load_palette().items()}


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def tint(material, attribute, strength, name):
    # Retain the library's mineral grain/roughness; add metre-scale geological colour.
    mat = vrmat.get(material).copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    socket = nodes["Principled BSDF"].inputs["Base Color"]
    color = nodes.new("ShaderNodeAttribute")
    color.attribute_name = attribute
    blend = nodes.new("ShaderNodeMixRGB")
    blend.inputs[0].default_value = strength
    links.new(socket.links[0].from_socket, blend.inputs[1])
    links.new(color.outputs["Color"], blend.inputs[2])
    links.new(blend.outputs[0], socket)
    return mat


class Mesh:
    def __init__(self):
        self.verts, self.faces, self.colors = [], [], []

    def object(self, name, material, color_name=None):
        data = bpy.data.meshes.new(name)
        data.from_pydata(self.verts, [], self.faces)
        data.update()
        data.materials.append(material)
        data.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        if color_name:
            layer = data.color_attributes.new(name=color_name, type="FLOAT_COLOR", domain="POINT")
            layer.data.foreach_set("color", [channel for rgb in self.colors for channel in (*rgb, 1)])
        return vrlib.link_to_source(bpy.data.objects.new(name, data))

    def rings(self, count, sides, sample, start, end):
        """Append a closed shell, sampled from its upper to its lower pole."""
        base = len(self.verts)
        for i in range(count):
            for j in range(sides):
                point, color = sample(i, j)
                self.verts.append(point)
                self.colors.append(color)
        for i in range(count - 1):
            row = base + i * sides
            for j in range(sides):
                k = (j + 1) % sides
                self.faces.append((row + j, row + j + sides, row + k + sides, row + k))
        a, b = len(self.verts), len(self.verts) + 1
        self.verts.extend((start[0], end[0]))
        self.colors.extend((start[1], end[1]))
        row = base + (count - 1) * sides
        for j in range(sides):
            k = (j + 1) % sides
            self.faces.extend(((a, base + j, base + k), (row + j, b, row + k)))


def footprint(a):
    r = 1 + .153 * math.cos(3*a + .47) + .081 * math.sin(5*a - .8)
    r += .073 * math.cos(2*a + 1.8) + .036 * math.sin(8*a + .4)
    r -= .19 * math.exp(-(angle_delta(a, .96) / .25) ** 2)
    r -= .15 * math.exp(-(angle_delta(a, -2.20) / .32) ** 2)
    u, v = math.cos(a), math.sin(a)
    r += .075*n3(2.8*u, 2.8*v, 17) + .013*n3(16*u, 16*v, 19) + .006*n3(33*u, 33*v, 28)
    return r * RX * math.cos(a), r * RY * math.sin(a)


def summit(x, y):
    ridge = 6.8 * math.exp(-((x + 51) / 51)**2 - ((y - 29) / 25)**2)
    swale = -5.2 * math.exp(-((x - 17) / 39)**2 - ((y + 10) / 40)**2)
    return (TOP + .022*x - .040*y + ridge + swale + 4.5*n3(x/37, y/37, 6)
            + 1.4*n3(x/12, y/12, 9) + .32*n3(x/2.4, y/2.4, 16))


def bed_color(p, lith, cavity, x, y, z):
    patina = n3(x/8, y/7, z/13)
    veins = n3(x/2.8, y/2.8, z/1.1)
    oxidized = mix(p["canyon_strata"], p["sandstone"], smooth(.31 + .71*patina))
    dry = mix(oxidized, p["canyon_chalk"], smooth(.38 + 1.1*lith + .51*patina))
    dark = mix(p["canyon_strata"], p["shore_wet"], .77)
    tone = mix(dry, dark, min(.83, cavity*.72 + smooth(-patina*2.5)*.51))
    return tuple(v * (.90 + .43 * veins) for v in tone)


def profile(t):
    for (a, r0), (b, r1) in zip(PROFILE, PROFILE[1:]):
        if t <= b:
            f = (t-a)/(b-a)
            return r0 + (r1-r0) * (.64*f + .36*smooth(f))
    return 0


def face(p, edge, a, t):
    ex, ey = edge
    u = profile(t)
    tx = -14*math.sin(math.pi*t) + 31*t*t
    ty = 22*t*(1-t) - 22*t*t
    x, y = ex*u + tx, ey*u + ty
    z = TOP*(1-t) + KEEL*t + (summit(ex, ey) - TOP)*(1-t)**2
    # Bed tilt, gentle undulation, interruptions and breakouts at the faults.
    bed_z = t + (.066*x - .045*y + 3.2*n3(x/65, y/51, 3))/(TOP-KEEL)
    ramp = smooth(t/.04) * smooth((1-t)/.14)
    ridge, lith, groove = 0, 0, 0
    for level, width, height, centre, spread in BEDS:
        q = (bed_z-level)/width
        if -.38 < q < 1.28:
            emergence = math.exp(-.8*(angle_delta(a, centre)/spread)**2)
            pinch = .49 + .51*smooth(.65 + n3(x/23, y/20, level*41))
            shelf = smooth((q+.38)/.32) * (1 - smooth((q-.18)/1.1))
            ridge += height * shelf * pinch * emergence
            lith += .78 * shelf * emergence - .43 * smooth((q-.57)/.68)
    for bearing, width, depth, lean in FAULTS:
        fault = angle_delta(a, bearing + lean*t + .043*math.sin(31*t+bearing))
        groove += depth * math.exp(-.68*(fault/width)**2) * (.51+.49*smooth(.5+1.1*n3(t*5, bearing, 26)))
    cells = voronoi_seam(x/16, y/15, z/34)
    rifts = 1 - smooth(cells/.20)
    wet = rifts*.40 + groove/18
    spur = 0
    for direction, level, weight, spread in ((-.62, .43, 9.8, .34), (1.34, .57, 15, .44),
                                             (2.86, .35, 11, .41), (-2.38, .72, 12, .48)):
        az = angle_delta(a, direction - .43*t)
        spur += weight * math.exp(-(az/spread)**2 - ((t-level)/.188)**2)
    displacement = ridge + spur - groove - 4.2*rifts
    displacement += 5.5*n3(x/14, y/14, z/27) + 1.9*n3(x/5.5, y/5.5, z/6.8)
    chips = voronoi_seam(x/4.4, y/4.1, z/5.9)
    broken = smooth((.13-chips)/.13) * smooth(.62 + 1.6*n3(x/8, y/8, z/9))
    displacement += 1.02*n3(x/2.1, y/2.1, z/2.1) + .35*n3(x*.89, y*.89, z*.89) - 1.15*broken
    x += math.cos(a)*displacement*ramp
    y += math.sin(a)*displacement*ramp
    return (x, y, z), bed_color(p, lith, wet+.43*broken, x, y, z)


def turf_color(p, x, y, r):
    scatter = n3(x/10, y/11, 26)
    slope = n3(x/26, y/23, 17)
    grain = n3(x/2.6, y/2.6, 11)
    bare = smooth((scatter + .4*slope + .19*grain - .1)*2.55 + smooth((r-.77)/.23)*.63)
    grit = mix(p["soil"], p["canyon_strata"], .46)
    turf = mix(p["moss"], p["grass_green"], smooth(.65 + 1.25*slope))
    turf = mix(turf, p["grass_dry"], smooth(.39 + .8*scatter))
    return tuple(v*(1.22+.24*grain) for v in mix(turf, grit, bare))


def massif(p):
    rock, grass = Mesh(), Mesh()
    angles = [i*math.tau/N for i in range(N)]
    edges = [footprint(a) for a in angles]
    # Keep the same crown perimeter on both surfaces so the contact never opens.
    rings = 328
    for i in range(rings):
        for j, a in enumerate(angles):
            pos, color = face(p, edges[j], a, i/rings)
            rock.verts.append(pos)
            rock.colors.append(color)
        if i:
            row = (i-1)*N
            for j in range(N):
                k = (j+1) % N
                rock.faces.append((row+j, row+j+N, row+k+N, row+k))
    rock.verts.append((31, -22, KEEL))
    rock.colors.append(p["shore_wet"])
    row = (rings-1)*N
    rock.faces.extend((row+j, rings*N, row+(j+1)%N) for j in range(N))

    grass.verts.append((0, 0, summit(0, 0)))
    grass.colors.append(turf_color(p, 0, 0, 0))
    for i in range(1, 78):
        r = i/77
        row = 1 + (i-1)*N
        for j, (ex, ey) in enumerate(edges):
            x, y = ex*r, ey*r
            grass.verts.append((x, y, summit(x, y)))
            grass.colors.append(turf_color(p, x, y, r))
            k = (j+1) % N
            grass.faces.append((row+j, row+k, row+k-N, row+j-N) if i > 1 else (0, row+j, row+k))
    rock_mat = tint("canyon_layered", "lithology", .88, "Driftward | limestone, seams and mineral patina")
    turf_mat = tint("grass_ground", "meadow", .86, "Driftward | turf, exposed soil and dry hummocks")
    # One watertight core, with a separate material on the summit faces.
    offset = len(rock.verts)
    rock.verts.extend(grass.verts[:-N])
    rock.colors.extend([p["canyon_strata"]] * (len(grass.verts) - N))
    summit_start = len(rock.faces)
    inner = len(grass.verts) - N
    rock.faces.extend(tuple(offset+i if i < inner else i-inner for i in f) for f in grass.faces)
    core = rock.object("Driftward / continuous crown and faulted limestone keel", rock_mat, "lithology")
    core.data.materials.append(turf_mat)
    for poly in list(core.data.polygons)[summit_start:]:
        poly.material_index = 1
    colors = [(*p["soil"], 1)] * offset + [(*c, 1) for c in grass.colors[:-N]]
    for i, c in enumerate(grass.colors[-N:]):
        colors[i] = (*c, 1)
    color_attr = core.data.color_attributes.new(name="meadow", type="FLOAT_COLOR", domain="POINT")
    color_attr.data.foreach_set("color", [v for c in colors for v in c])
    return rock_mat


def outcrop(mesh, p, centre, dims, rng, sides, rings, yaw, taper, tilt, cleavage=0):
    seed = rng.uniform(21, 900)
    ca, sa = math.cos(yaw), math.sin(yaw)
    dx, dy, dz = dims
    phase = rng.uniform(0, math.tau)

    def sample(i, j):
        t = (i+1) / (rings+1)
        lat = math.pi*t
        a = j*math.tau/sides
        u, v, w = math.sin(lat)*math.cos(a), math.sin(lat)*math.sin(a), math.cos(lat)
        joint = voronoi_seam(u*2.2+seed, v*2.2, w*1.4)
        erode = 1 - smooth(joint/.31)
        bedding = math.sin((18 + 5*math.sin(phase))*(w+.14*u) + 1.8*n3(u*2, v*2+seed, w))
        r = (1 + .27*n3(u*2+seed, v*2, w*2) + .11*n3(u*5, v*5+seed, w*5)
             + .039*n3(u*12, v*12, w*12+seed) - .16*erode + (.092-.055*cleavage)*bedding
             + .12*math.cos(3*a+phase)*math.sin(lat)) * (1 + taper*w)
        normal = u*math.cos(phase)+v*math.sin(phase)
        plane = .88 + .24*w - .27*cleavage
        if normal > .2:
            limit = plane/normal
            c = max(0, .08-abs(limit-r))
            r = min(r, limit) - c*c/.32
        x, y = r*u*dx + tilt*w*dx, r*v*dy
        z = dz*(w + .10*n3(4*u, 4*v, 4*w+seed)*math.sin(lat))
        pos = (centre[0]+ca*x-sa*y, centre[1]+sa*x+ca*y, centre[2]+z)
        color = bed_color(p, bedding*.52, erode*.64, *pos)
        return pos, color

    def pole(sign):
        x = sign * tilt*dx
        return (centre[0]+ca*x, centre[1]+sa*x, centre[2]+sign*dz), p["canyon_strata"]

    mesh.rings(rings, sides, sample, pole(1), pole(-1))


def wood_tube(mesh, path, widths, sides=8):
    base = len(mesh.verts)
    for k, pt in enumerate(path):
        axis = (path[min(k+1, len(path)-1)] - path[max(k-1, 0)]).normalized()
        xaxis = axis.cross(Vector((.29, -.71, .52))).normalized()
        yaxis = axis.cross(xaxis)
        for j in range(sides):
            a = math.tau*j/sides
            mesh.verts.append(pt + widths[k]*(math.cos(a)*xaxis + math.sin(a)*yaxis))
        if k:
            row = base + (k-1)*sides
            for j in range(sides):
                m = (j+1) % sides
                mesh.faces.append((row+j, row+m, row+m+sides, row+j+sides))
    last = base + (len(path)-1)*sides
    mesh.faces.extend((tuple(reversed(range(base, base+sides))), tuple(range(last, last+sides))))


def canopy(mesh, p, pos, size, rng):
    sz, seed = size, rng.uniform(20, 700)
    stretch = rng.uniform(.59, .81)
    dark, light = p["leaf_shadow"], p["leaf_green"]

    def sample(i, j):
        theta = (i+1)*math.pi/13
        phi = j*math.tau/18
        x, y, z = math.sin(theta)*math.cos(phi), math.sin(theta)*math.sin(phi), math.cos(theta)
        grain = n3(x*7, y*7+seed, z*7)
        r = 1 + .32*n3(x*2.1+seed, y*2.1, z*2.1) + .16*grain
        color = mix(dark, tuple(v*1.72 for v in light), smooth(.63 + .43*z + .42*grain))
        return pos + Vector((x*r*sz, y*r*sz, z*r*sz*stretch)), color

    mesh.rings(12, 18, sample, (pos+Vector((0, 0, sz*stretch)), light),
               (pos-Vector((0, 0, sz*stretch)), dark))


def tree(wood, leaves, p, x, y, height, rng):
    foot = Vector((x, y, summit(x, y)-.22))
    lean = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * height*.22
    fork = foot + Vector((0, 0, height*.48)) + lean*.41
    top = foot + Vector((0, 0, height*.91)) + lean
    wood_tube(wood, [foot, foot.lerp(fork, .40), fork, fork.lerp(top, .60), top],
              [height*k for k in (.068, .048, .036, .026, .009)])
    crown = rng.uniform(.225, .33)*height
    canopy(leaves, p, top, crown*.9, rng)
    phase = rng.uniform(0, math.tau)
    for j in range(rng.randint(4, 6)):
        a = phase + j*1.62 + rng.uniform(-.4, .4)
        end = top + Vector((math.cos(a)*crown, math.sin(a)*crown, -crown*rng.uniform(.18, .85)))
        start = fork.lerp(top, rng.uniform(.02, .46))
        bend = start.lerp(end, .55) + Vector((.12, -.14, crown*.3))
        wood_tube(wood, [start, bend, end], [height*.029, height*.016, height*.0045], 7)
        canopy(leaves, p, end, crown*rng.uniform(.56, .83), rng)
        if j % 2:
            canopy(leaves, p, end.lerp(top, .35)+Vector((.27, 0, crown*.63)), crown*.45, rng)


def cover(p, rng, stone_mat):
    wood, leaves, floaters, rubble, blades = Mesh(), Mesh(), Mesh(), Mesh(), Mesh()
    for x, y, h in ((-70, 21, 8), (-58, 29, 10), (-58, 13, 7), (-42, 22, 9),
                    (-31, 11, 6.5), (-45, -2, 6), (35, -30, 8), (46, -22, 10.5),
                    (62, -20, 7), (43, -11, 7), (85, 13, 6.5), (76, 24, 7.2),
                    (54, 30, 6.2), (9, 49, 8.4), (21, 44, 6.3)):
        tree(wood, leaves, p, x, y, h, rng)
    for x, y, sx, sy in ((-56, 15, 16, 12), (51, -21, 14, 12), (-3, -35, 18, 12),
                         (3, 43, 21, 8), (82, 13, 14, 11), (-88, -22, 14, 13)):
        for _ in range(13):
            a, b = x+rng.uniform(-sx, sx), y+rng.uniform(-sy, sy)
            s = rng.uniform(.62, 1.75)
            canopy(leaves, p, Vector((a, b, summit(a, b)+.35*s)), s, rng)
        for _ in range(17):
            a, b = x+rng.uniform(-sx, sx), y+rng.uniform(-sy, sy)
            r = rng.uniform(.30, 2.3)**1.25
            outcrop(rubble, p, (a, b, summit(a, b)-.21*r), (r, r*.73, r*.68),
                    rng, 24, 16, rng.uniform(0, math.tau), -.24, rng.uniform(-.3, .3))
        for _ in range(110):
            a, b = x+rng.uniform(-1.4*sx, 1.4*sx), y+rng.uniform(-1.4*sy, 1.4*sy)
            if ((a/RX)**2+(b/RY)**2)**.5 > .76:
                continue
            for _ in range(rng.randint(3, 7)):
                x0, y0 = a+rng.uniform(-.48, .48), b+rng.uniform(-.48, .48)
                z = summit(x0, y0)-.05
                h, w = rng.uniform(.22, .73), rng.uniform(.027, .077)
                phase = rng.uniform(0, math.tau)
                dx, dy = math.cos(phase)*w, math.sin(phase)*w
                i = len(blades.verts)
                blades.verts.extend(((x0-dx, y0-dy, z), (x0+dx, y0+dy, z),
                                    (x0+.25*h-dx*.48, y0+.03*h-dy*.48, z+h*.64),
                                    (x0+.25*h+dx*.48, y0+.03*h+dy*.48, z+h*.64),
                                    (x0+.48*h, y0+.08*h, z+h)))
                blades.faces.extend(((i, i+1, i+3, i+2), (i+2, i+3, i+4)))

    # Several coherent slips cling to the cliff; the detached pieces share its bedding.
    for a, depth, sx, sy, sz in ((-.83, .34, 16, 10, 24), (.20, .33, 12, 10, 17),
                                 (1.47, .47, 10, 9, 22), (-2.44, .32, 15, 14, 26),
                                 (2.78, .20, 16, 9, 16), (-1.44, .64, 9, 8, 21)):
        pt, _ = face(p, footprint(a), a, depth)
        centre = (pt[0]-5*math.cos(a), pt[1]-5*math.sin(a), pt[2]+3)
        outcrop(rubble, p, centre, (sx, sy, sz), rng, 80, 55, a-.2, .41, .58)

    for centre, dims, yaw, taper, tilt, cleavage in (
        ((-147, 16, 113), (15, 12, 26), .63, .29, -.45, .78),
        ((-162, 3, 83), (7.8, 4.4, 5.8), 1.31, -.22, .34, .61),
        ((144, -35, 127), (15, 7, 18), .89, .36, .47, 1),
        ((150, -51, 98), (6.7, 3.2, 5.1), 2.5, -.10, -.43, .42),
        ((-39, -77, 73), (5.8, 4.3, 12.5), -.67, .23, .46, .75),
        ((67, 13, 29), (6.2, 2.7, 6.5), -.18, .52, -.37, .88),
    ):
        outcrop(floaters, p, centre, dims, rng, 80, 65, yaw, taper, tilt, cleavage)

    for bearing, width, length in ((.30, .17, 11), (-.33, .13, 17), (1.83, .11, 12), (-2.58, .14, 14)):
        for _ in range(rng.randint(4, 7)):
            a = bearing + rng.uniform(-width, width)
            depth = rng.uniform(.014, .045)
            start_xyz, _ = face(p, footprint(a), a, depth)
            length_i = rng.uniform(.36, 1.0)*length
            radius = rng.uniform(.18, .42)
            path = []
            for i in range(10):
                t = i/9
                x, y, z = start_xyz
                cliff, _ = face(p, footprint(a), a, depth + length_i/149*t)
                wall = (cliff[0]-x)*math.cos(a) + (cliff[1]-y)*math.sin(a)
                slack = 1.3*math.sin(t*2.8)*math.sin(a*13) + 4.2*t*t
                drift = wall*(1-.55*t) + slack - 1.2 + 2.7*smooth(t/.36)
                x += math.cos(a)*drift + 1.6*t*math.sin(a*6+5*t)
                y += math.sin(a)*drift + 1.3*t*math.cos(a*4+4*t)
                path.append(Vector((x, y, z-length_i*t)))
            wood_tube(wood, path, [radius*(1-.97*i/9)**.79 for i in range(10)])
            if rng.random() < .65:
                parent = path[4]
                twig = [parent, parent.lerp(path[7], .5)+Vector((.62, .22, -.2)),
                        path[8]+Vector((1.87, .58, -.5))]
                wood_tube(wood, twig, [radius*.52, radius*.23, radius*.036], 6)

    wood.object("Summit trunks and exposed roots", vrmat.get("tree_bark"))
    leaves.object("Wind-shaped canopies and brush", tint("foliage_leaf", "leaf_tone", .82,
                                                         "Driftward | olive foliage"), "leaf_tone")
    blades.object("Summit meadow blades", vrmat.get("grass_ground"))
    rubble.object("Talus and partly detached fault spurs", stone_mat, "lithology")
    floaters.object("Six detached and rotated limestone fragments", stone_mat, "lithology")


def build():
    p = palette()
    stone_mat = massif(p)
    cover(p, random.Random(SEED), stone_mat)
    scene = bpy.context.scene
    scene["vr_review_floating"] = True
    ex, ey = -36, -44
    scene["vr_review_figure"] = (ex, ey, summit(ex, ey)-.03)
    scene["vr_review_turn"] = (0, 0, 89, 247, 12, 530)
    scene["vr_closeup_upper"] = (-45, -52, 144, -116, 29, 126)
    scene["vr_closeup_base"] = (8, -5, 53, -118, -6, 180)

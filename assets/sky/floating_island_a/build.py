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
    (.075, .101, 10.8, -.3, 2.6), (.241, .093, 12.6, -1.32, 2.25),
    (.405, .101, 10.5, 1.8, 2.22), (.572, .084, 8.1, -2.42, 2.0),
    (.733, .088, 6.4, -.88, 1.9),
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
    if material == "grass_ground":
        blend.blend_type = "MULTIPLY"
    blend.inputs[0].default_value = strength
    base = socket.links[0].from_socket
    if material == "grass_ground":
        links.new(color.outputs["Color"], blend.inputs[1])
        links.new(base, blend.inputs[2])
    else:
        links.new(base, blend.inputs[1])
        links.new(color.outputs["Color"], blend.inputs[2])
    result = blend.outputs[0]
    if material in {"grass_ground", "canyon_layered"}:
        coords = next(n for n in nodes if n.type == "TEX_COORD")
        grain = nodes.new("ShaderNodeTexNoise")
        grain.inputs["Scale"].default_value = 1.55 if material == "grass_ground" else .96
        grain.inputs["Detail"].default_value = 3.4
        links.new(coords.outputs["Object"], grain.inputs["Vector"])
        shade = nodes.new("ShaderNodeMapRange")
        shade.inputs["From Min"].default_value = .29
        shade.inputs["From Max"].default_value = .71
        shade.inputs["To Min"].default_value = .58 if material == "grass_ground" else .73
        shade.inputs["To Max"].default_value = 1.26 if material == "grass_ground" else 1.15
        links.new(grain.outputs["Fac"], shade.inputs["Value"])
        mottling = nodes.new("ShaderNodeMixRGB")
        mottling.blend_type = "MULTIPLY"
        mottling.inputs[0].default_value = 1
        links.new(result, mottling.inputs[1])
        links.new(shade.outputs["Result"], mottling.inputs[2])
        result = mottling.outputs[0]
    links.new(result, socket)
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
    patina = n3(x/14, y/13, z/16)
    veins = n3(x/3.7, y/3.7, z/.84)
    limestone = mix(p["canyon_strata"], p["sandstone"], .22 + .19*patina)
    dry = mix(limestone, p["canyon_chalk"], smooth(.36 + lith + .20*patina))
    shaded = mix(p["canyon_strata"], p["soil"], .51)
    tone = mix(dry, shaded, min(.74, cavity*.70))
    return tuple(v * (1 + .24 * veins) for v in tone)


def profile(t):
    for (a, r0), (b, r1) in zip(PROFILE, PROFILE[1:]):
        if t <= b:
            f = (t-a)/(b-a)
            return r0 + (r1-r0) * (.64*f + .36*smooth(f))
    return 0


def lip(q):
    return smooth((q+.07)/.22) * (1-.23*smooth((q-.35)/.56)) * (1-smooth((q-.91)/.18))


def face(p, edge, a, t):
    ex, ey = edge
    u = profile(t)
    tx = -14*math.sin(math.pi*t) + 31*t*t
    ty = 22*t*(1-t) - 22*t*t
    x, y = ex*u + tx, ey*u + ty
    z = TOP*(1-t) + KEEL*t + (summit(ex, ey) - TOP)*(1-t)**2
    # Bed tilt, gentle undulation, interruptions and breakouts at the faults.
    bed_z = t + (.026*x - .020*y + 2.1*n3(x/57, y/51, 3))/(TOP-KEEL)
    bed_z += .015*math.sin(3*a+.4)*smooth(t/.12)
    ramp = smooth(t/.04) * smooth((1-t)/.14)
    ridge, lith, cavity, groove = 0, 0, 0, 0
    for i, (level, width, height, centre, spread) in enumerate(BEDS):
        offset = .009*math.sin(4*a + i*2.3) + .013*n3(x/24, y/21, i+4)
        offset += .003*n3(x/5, y/5, i+7)
        q = (bed_z-level+offset)/width
        if -.23 < q < 1.36:
            emergence = .44 + .56*math.exp(-.9*(angle_delta(a, centre)/spread)**2)
            pinch = .54 + .46*smooth(.69 + 1.9*n3(x/23, y/20, level*41))
            shelf = lip(q)
            chip = smooth(.5+1.6*n3(x/6, y/6, i*11)) * smooth(.44 + 1.8*n3(x/14, y/13, i*7))
            bedding = math.sin(39*q + 4.2*n3(x/22, y/20, i) + .65*n3(x/6, y/5, i))
            rim = .82*chip*math.exp(-((q-.94)/.23)**2) + .15*bedding*shelf*chip
            ridge += height * shelf * pinch * emergence - rim
            lith += (.52, .27, .45, .14, .32)[i]*shelf + .31*math.exp(-((q-.12)/.24)**2)
            cavity += .56*math.exp(-((q-1.10)/.17)**2)
    for bearing, width, depth, lean in FAULTS:
        fault = angle_delta(a, bearing + .65*lean*t + .012*math.sin(21*t+bearing))
        groove += depth * max(0, 1-abs(fault)/(1.6*width)) * (.58+.42*smooth(.5+n3(t*5, bearing, 26)))
    cells = voronoi_seam(x/16, y/15, z/34)
    rifts = 1 - smooth(cells/.20)
    wet = cavity + rifts*.18 + groove/19
    spur = 0
    for direction, level, weight, spread in ((-.62, .43, 9.8, .34), (1.34, .57, 15, .44),
                                             (2.86, .35, 11, .41), (-2.38, .72, 12, .48)):
        az = angle_delta(a, direction - .43*t)
        spur += .62*weight * math.exp(-(az/spread)**2 - ((t-level)/.188)**2)
    displacement = ridge + spur - groove - .88*rifts
    displacement += 1.4*n3(x/14, y/14, z/27) + .51*n3(x/5.5, y/5.5, z/6.8)
    chips = voronoi_seam(x/4.4, y/4.1, z/5.9)
    broken = smooth((.13-chips)/.13) * smooth(.62 + 1.6*n3(x/8, y/8, z/9))
    displacement += .39*n3(x/2.1, y/2.1, z/2.1) + .16*n3(x*.89, y*.89, z*.89) - .53*broken
    for bearing, reach, anchor, slope in ((-2.5, .24, .23, -.23), (-1.79, .24, .36, .19),
                                         (-.80, .27, .63, -.12), (.48, .20, .29, .34),
                                         (1.54, .26, .41, -.17), (2.52, .19, .67, .30)):
        normal = bearing + slope*(t-anchor)
        delta = angle_delta(a, normal)
        if abs(delta) < reach:
            bx, by = footprint(normal)
            ca, sa = math.cos(normal), math.sin(normal)
            plane = u*(bx*ca+by*sa) + ridge - 6.9*math.exp(-((t-anchor)/.36)**2)
            cut = ((x-tx)*ca+(y-ty)*sa-plane)/math.cos(delta)
            displacement -= max(0, displacement+cut)*smooth((reach-abs(delta))/.070)
    soil_depth = (.014 + .005*math.sin(8*a-.3) + .005*n3(ex/17, ey/17, 7))
    soil = 1-smooth((t-soil_depth)/.005)
    displacement = displacement*(1-soil) + (.7 + 2.1*n3(ex/18, ey/18, t*70))*soil
    x += math.cos(a)*displacement*ramp
    y += math.sin(a)*displacement*ramp
    rock = bed_color(p, lith, wet+.25*broken, x, y, z)
    earth = mix(p["bark"], p["soil"], .59 + .36*n3(x/2.6, y/2.6, z*1.8))
    return (x, y, z), mix(rock, earth, soil)


def turf_color(p, x, y, r):
    scatter = n3(x/10, y/11, 26)
    slope = n3(x/26, y/23, 17)
    grain = n3(x/2.6, y/2.6, 11)
    bare = .64*smooth((scatter + .27*slope + .27*grain - .14)*3.1)
    bare += .23*smooth((r-.93)/.07)
    grit = mix(p["soil"], p["canyon_strata"], .22)
    turf = mix(p["moss"], p["grass_green"], smooth(.80 + .69*slope))
    turf = mix(turf, p["grass_dry"], .27*smooth(.48 + .9*scatter))
    return tuple(v*(1.93+.34*grain) for v in mix(turf, grit, bare))


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
    rock_mat = tint("canyon_layered", "lithology", .80, "Driftward | limestone, seams and mineral patina")
    turf_mat = tint("grass_ground", "meadow", .45, "Driftward | turf, exposed soil and dry hummocks")
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


def outcrop(mesh, p, centre, dims, rng, sides, rings, yaw, taper, tilt, cleavage=0, turf=False):
    seed = rng.uniform(21, 900)
    ca, sa = math.cos(yaw), math.sin(yaw)
    dx, dy, dz = dims
    phase = rng.uniform(0, math.tau)
    planes = []
    for i in range(5):
        a = phase + i*math.tau/5 + rng.uniform(-.24, .24)
        planes.append((math.cos(a), math.sin(a), rng.uniform(-.25, .37), rng.uniform(.48, .75)))
    cap = .69 if turf else .85
    cap_color = mix(p["grass_green"], p["moss"], .28)

    def sample(i, j):
        t = (i+1) / (rings+1)
        lat = math.pi*t
        a = j*math.tau/sides
        u, v, w = math.sin(lat)*math.cos(a), math.sin(lat)*math.sin(a), math.cos(lat)
        joint = voronoi_seam(u*2.2+seed, v*2.2, w*1.4)
        erode = 1 - smooth(joint/.25)
        bedding = sum(lip((level-w-.16*u+.042*v)/.29) for level in (.63, .11, -.48))
        r = (1 + .09*n3(u*2+seed, v*2, w*2)) * (1 + taper*w)
        for px, py, lean, setback in planes:
            dot = px*u + py*v + lean*w
            if dot > .25:
                r = min(r, (setback + .24*(1-cleavage))/dot)
        r *= (1 + .13*bedding + .022*n3(u*5, v*5+seed, w*5) - .025*erode
              + .012*n3(u*11, v*11, w*11+seed))
        x, y = r*u*dx + tilt*w*dx, r*v*dy
        z = dz*(min(w, cap+.13*u-.08*v) + .028*n3(4*u, 4*v, 4*w+seed)*math.sin(lat))
        pos = (centre[0]+ca*x-sa*y, centre[1]+sa*x+ca*y, centre[2]+z)
        color = bed_color(p, bedding*.61, erode*.32, *pos)
        if turf and w > cap-.12:
            earth = mix(p["soil"], color, 1-smooth((w-cap+.12)/.08))
            color = mix(earth, cap_color, smooth((w-cap+.035)/.08))
        return pos, color

    def pole(sign):
        x = sign * tilt*dx
        color = cap_color if sign > 0 and turf else p["canyon_strata"]
        return (centre[0]+ca*x, centre[1]+sa*x, centre[2]+(cap if sign > 0 else -1)*dz), color

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


def blade(mesh, x, y, z, h, w, az, outward):
    dx, dy = math.cos(az)*w, math.sin(az)*w
    bx, by = outward
    i = len(mesh.verts)
    mesh.verts.extend(((x-dx, y-dy, z), (x+dx, y+dy, z),
                       (x+.41*bx-dx*.48, y+.41*by-dy*.48, z+h*.63),
                       (x+.41*bx+dx*.48, y+.41*by+dy*.48, z+h*.63),
                       (x+bx, y+by, z+h)))
    mesh.faces.extend(((i, i+1, i+3, i+2), (i+2, i+3, i+4)))


def cover(p, rng, stone_mat):
    wood, leaves, floaters, rubble, blades = Mesh(), Mesh(), Mesh(), Mesh(), Mesh()
    for x, y, h in ((-73, 22, 8), (-63, 27, 10), (-63, 13, 7), (-51, 22, 9),
                    (-52, 9, 6.5), (-32, -37, 8), (-47, -43, 10.5), (-56, -31, 7),
                    (-45, -29, 7), (65, 13, 6.5), (76, 19, 10.2), (79, 9, 7.2),
                    (61, 23, 6.2), (59, 14, 8.4), (86, 23, 6.3)):
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
        for _ in range(430):
            a, b = x+rng.uniform(-1.4*sx, 1.4*sx), y+rng.uniform(-1.4*sy, 1.4*sy)
            if ((a/RX)**2+(b/RY)**2)**.5 > .76:
                continue
            for _ in range(rng.randint(3, 7)):
                x0, y0 = a+rng.uniform(-.48, .48), b+rng.uniform(-.48, .48)
                z = summit(x0, y0)-.05
                h, w = rng.uniform(.22, .73), rng.uniform(.027, .077)
                phase = rng.uniform(0, math.tau)
                blade(blades, x0, y0, z, h, w, phase, (.48*h, .08*h))

    for i in range(740):
        a = i*math.tau/740 + rng.uniform(-.008, .008)
        ex, ey = footprint(a)
        if rng.random() > .35 + .64*smooth(.57 + n3(ex/7, ey/7, 12)):
            continue
        for _ in range(rng.randint(5, 12)):
            r = rng.uniform(.988, .998)
            x, y = r*ex+rng.uniform(-.35, .35), r*ey+rng.uniform(-.35, .35)
            h = rng.uniform(.21, .89)
            extension = rng.uniform(.22, 1.22)
            blade(blades, x, y, summit(x, y)-.12, h, rng.uniform(.032, .10),
                  rng.uniform(0, math.tau), (extension*math.cos(a), extension*math.sin(a)))

    # Several coherent slips cling to the cliff; the detached pieces share its bedding.
    for a, depth, sx, sy, sz in ((-.83, .34, 15, 9, 17), (.20, .33, 12, 10, 12),
                                 (1.47, .47, 10, 9, 14), (-2.44, .32, 15, 14, 18),
                                 (2.78, .20, 13, 7, 11), (-1.44, .64, 7, 7, 16)):
        pt, _ = face(p, footprint(a), a, depth)
        centre = (pt[0]-5*math.cos(a), pt[1]-5*math.sin(a), pt[2]+3)
        outcrop(rubble, p, centre, (sx, sy, sz), rng, 80, 55, a-.2, .41, .58, .82)

    for centre, dims, yaw, taper, tilt, cleavage in (
        ((-147, 16, 113), (15, 12, 26), .63, .29, -.45, .78),
        ((-162, 3, 83), (7.8, 4.4, 5.8), 1.31, -.22, .34, .61),
        ((144, -35, 127), (15, 7, 18), .89, .36, .47, 1),
        ((150, -51, 98), (6.7, 3.2, 5.1), 2.5, -.10, -.43, .42),
        ((-39, -77, 73), (5.8, 4.3, 12.5), -.67, .23, .46, .75),
        ((67, 13, 29), (6.2, 2.7, 6.5), -.18, .52, -.37, .88),
    ):
        outcrop(floaters, p, centre, dims, rng, 80, 65, yaw, taper, tilt, cleavage, turf=dims[0]>12)

    for bearing, width, length in ((.30, .17, 11), (-.33, .13, 12), (1.83, .11, 12),
                                   (-2.58, .14, 10), (-2.03, .19, 13), (-1.56, .14, 9)):
        for _ in range(rng.randint(4, 7)):
            a = bearing + rng.uniform(-width, width)
            depth = rng.uniform(.006, .013)
            start_xyz, _ = face(p, footprint(a), a, depth)
            length_i = rng.uniform(.36, 1.0)*length
            radius = rng.uniform(.21, .44)
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
    scene["vr_closeup_upper"] = (-41, -51, 146, -112, 28, 104)
    scene["vr_closeup_base"] = (8, -5, 58, -118, -5, 170)

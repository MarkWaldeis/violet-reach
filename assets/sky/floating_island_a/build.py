"""Driftward Plateau: jointed chalk bedding beneath a wind-shaped meadow."""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise

import vrlib
import vrmat

SEED = 86347
TAU = math.tau
TOP = 147
RIM_WALL = []


class Mesh:
    def __init__(self):
        self.vertices = []
        self.faces = []

    def face(self, points):
        start = len(self.vertices)
        self.vertices.extend(points)
        self.faces.append(tuple(range(start, len(self.vertices))))

    def object(self, name, material, smooth=False):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append((meadow_material() if material == "grass_ground" else vrmat.get(material))
                                 if isinstance(material, str) else material)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.0001)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = smooth
        return vrlib.link_to_source(obj)


def meadow_material():
    cached = bpy.data.materials.get("Driftward meadow patches")
    if cached is not None:
        return cached
    mat = vrmat.get("grass_ground").copy()
    mat.name = "Driftward meadow patches"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coords = next(node for node in nodes if node.type == "TEX_COORD")
    patch = nodes.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = .045
    patch.inputs["Detail"].default_value = 2
    links.new(coords.outputs["Object"], patch.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    colors = vrmat.load_palette()
    for element, key in zip(ramp.color_ramp.elements, ("grass_green", "grass_dry")):
        element.color = (*colors[key]["linear_rgb"], 1)
    ramp.color_ramp.elements[0].position = .28
    ramp.color_ramp.elements[1].position = .78
    links.new(patch.outputs["Fac"], ramp.inputs["Fac"])
    bsdf = nodes["Principled BSDF"]
    original = bsdf.inputs["Base Color"].links[0].from_socket
    blend = nodes.new("ShaderNodeMixRGB")
    blend.inputs[0].default_value = .7
    links.new(original, blend.inputs[1])
    links.new(ramp.outputs["Color"], blend.inputs[2])
    links.new(blend.outputs[0], bsdf.inputs["Base Color"])
    return mat


def crown_material(index):
    name = "Driftward olive crown %d" % index
    cached = bpy.data.materials.get(name)
    if cached is not None:
        return cached
    mat = vrmat.get("foliage_leaf").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    original = bsdf.inputs["Base Color"].links[0].from_socket
    colors = vrmat.load_palette()
    olive = colors["grass_green"]["linear_rgb"]
    moss = colors["moss"]["linear_rgb"]
    t = .15+index*.12
    blend = nodes.new("ShaderNodeMixRGB")
    blend.inputs[0].default_value = .67+index*.025
    links.new(original, blend.inputs[1])
    blend.inputs[2].default_value = tuple(a*(1-t)+b*t for a, b in zip(olive, moss))+(1,)
    links.new(blend.outputs[0], bsdf.inputs["Base Color"])
    return mat


def outline(a):
    return 1 + .075*math.sin(3*a+.7) + .045*math.sin(7*a-1.1) + .023*math.sin(17*a)


def edge(a, scale=1, shift=(0, 0), phase=0):
    r = outline(a) * scale * (1 + .08*math.sin(2*a+phase) + .035*math.sin(11*a+phase))
    for angle, width, depth in ((.52, .17, .23), (2.14, .13, .27), (3.77, .18, .20), (4.91, .14, .30)):
        delta = abs(math.atan2(math.sin(a-angle), math.cos(a-angle)))
        r -= scale*depth*max(0, 1-delta/width)
    return Vector((132*r*math.cos(a)+shift[0], 89.5*r*math.sin(a)+shift[1], 0))


def summit(x, y):
    fade = max(0, 1-((x/132)**2+(y/89.5)**2))
    return TOP+2.0+fade*(2.3+2.0*math.sin(x*.045+y*.028)+1.7*math.cos(y*.065-x*.023))


def cell_value(p, scale, seed):
    _, cells = noise.voronoi(p*scale + Vector((seed, seed*.731, -seed*.37)))
    c = cells[0]
    return (math.sin(c.x*127.1+c.y*311.7+c.z*74.7)*43758.5453) % 1 - .5


def clip_plane(poly, normal, limit):
    result = []
    for p, q in zip(poly, poly[1:]+poly[:1]):
        dp, dq = p.dot(normal)-limit, q.dot(normal)-limit
        if dp <= 0:
            result.append(p)
        if (dp < 0) != (dq < 0):
            result.append(p+(q-p)*(dp/(dp-dq)))
    return result


def wall_fractures(mesh, corners, seed):
    rng = random.Random(seed)
    low_a, low_b, high_b, high_a = corners
    width = (low_b-low_a).length
    height = max((high_a-low_a).length, (high_b-low_b).length)
    if width < .15 or height < .2:
        mesh.face(corners)
        return
    normal = (low_b-low_a).cross(high_a-low_a).normalized()
    uv = [Vector((0, 0)), Vector((width, 0)), Vector((width, height)), Vector((0, height))]
    pivot = Vector((width*rng.uniform(.28, .72), height*rng.uniform(.3, .7)))
    centre = low_a.lerp(low_b, pivot.x/width).lerp(high_a.lerp(high_b, pivot.x/width), pivot.y/height)
    centre += normal*rng.uniform(.2, min(1, width*.12))
    grooves = [(rng.uniform(.12, .88)*width, rng.uniform(.18, .65), rng.uniform(.12, .65))
               for _ in range(rng.randint(0, 2) if width > 2 else 0)]
    beds = [(rng.uniform(.2, .8)*height, rng.uniform(.12, .3), rng.uniform(.08, .18))
            for _ in range(1 if height > 5 and rng.random() < .15 else 0)]
    xs = sorted({0, width, *[min(width, max(0, x+d)) for x, w, _ in grooves for d in (-w, 0, w)]})
    ys = sorted({0, height, *[min(height, max(0, y+d)) for y, w, _ in beds for d in (-w, 0, w)]})
    world = (low_a, low_b, high_b, high_a)
    for facet in range(4):
        j = (facet+1)%4
        tri = [uv[facet], uv[j], pivot]
        a, b, c = tri
        det = (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)

        def point(p):
            q = p
            u = ((q.x-a.x)*(c.y-a.y)-(q.y-a.y)*(c.x-a.x))/det
            v = ((b.x-a.x)*(q.y-a.y)-(b.y-a.y)*(q.x-a.x))/det
            base = world[facet]+(world[j]-world[facet])*u+(centre-world[facet])*v
            depth = sum(d*max(0, 1-abs(p.x-x)/w) for x, w, d in grooves)
            depth += sum(d*max(0, 1-abs(p.y-y)/w) for y, w, d in beds)
            fade = max(0, min(1, p.x/.3, (width-p.x)/.3, p.y/.3, (height-p.y)/.3))
            return base-normal*depth*fade

        local = tri
        for x0, x1 in zip(xs, xs[1:]):
            for y0, y1 in zip(ys, ys[1:]):
                poly = local
                for n, limit in ((Vector((-1, 0)), -x0), (Vector((1, 0)), x1),
                                 (Vector((0, -1)), -y0), (Vector((0, 1)), y1)):
                    poly = clip_plane(poly, n, limit)
                    if len(poly) < 3:
                        break
                if len(poly) >= 3:
                    mesh.face([point(p) for p in poly])


def strata(name, z0, z1, scale, shift, index, material="canyon_layered", origin=(0, 0)):
    mesh, fallen = Mesh(), Mesh()
    rng = random.Random(SEED+index*193)
    phase = .4*math.sin(index*1.73)
    perimeter = 710*scale
    boundaries = [0]
    while boundaries[-1] < TAU:
        boundaries.append(min(TAU, boundaries[-1]+rng.uniform(7 if index == 11 else 3, 15)/max(1, perimeter)*TAU))
    columns = []
    for i in range(len(boundaries)-1):
        a, b = boundaries[i:i+2]
        push = rng.uniform(-3, 2.2)*min(1, scale*4)
        if index == 11:
            push *= .4
        if rng.random() < .08 and scale > .1:
            push -= rng.uniform(4, 9)
        tilt = Vector((rng.uniform(-.8, .8), rng.uniform(-.8, .8), 0))
        row_low, row_high = [], []
        for fraction in (0, .14, .83, 1):
            angle = a+(b-a)*fraction
            p = edge(angle, scale, shift, phase)
            p.x += origin[0]
            p.y += origin[1]
            radial = Vector((math.cos(angle), math.sin(angle), 0))
            notch = -1.6*min(1, scale*5) if fraction in (0, 1) else push
            p += radial*notch
            wave = math.sin(3*angle+.6)+.65*math.sin(7*angle+index*.9)
            top = z1 + (0 if index == 0 else wave*.85)
            bottom = z0 + (0 if index == 0 else 1.8*math.sin(2*angle+index*.7))
            if index in (5, 8, 10):
                top -= (z1-z0)*.68*max(0, math.cos(angle-index))**6
            high = p+Vector((0, 0, top))
            low = p+tilt+Vector((0, 0, min(bottom, top-1)))
            if fraction in (.14, .83):
                chip = rng.uniform(.15, min(1.5, (top-bottom)*.14))
                high -= radial*rng.uniform(.15, .8)+Vector((0, 0, chip))
                low += radial*rng.uniform(-.45, .3)+Vector((0, 0, rng.uniform(.05, .6)))
            if index == 0:
                low.x = shift[0]+origin[0]+(low.x-shift[0]-origin[0])*.025
                low.y = shift[1]+origin[1]+(low.y-shift[1]-origin[1])*.025
            row_low.append(low)
            row_high.append(high)
        columns.append((row_low, row_high))
        if index == 11:
            RIM_WALL.append((a, b, row_low, row_high, i))
        for j in range(3):
            wall_fractures(mesh, (row_low[j], row_low[j+1], row_high[j+1], row_high[j]),
                       SEED+index*1301+i*37+j)
        if scale > .35 and rng.random() < .09:
            p = row_low[1].lerp(Vector((shift[0]+origin[0], shift[1]+origin[1], row_low[1].z)), .035)
            p.z += 1.2
            hull(fallen, p, (rng.uniform(1.8, 3.5), 2.2, rng.uniform(1, 2.8)), rng, 12)
    for i, (low, high) in enumerate(columns):
        prev_low, prev_high = columns[i-1]
        mesh.face((prev_low[-1], low[0], high[0], prev_high[-1]))
        centre_low = Vector((shift[0]+origin[0], shift[1]+origin[1], z0))
        centre_high = Vector((shift[0]+origin[0], shift[1]+origin[1], z1))
        for j in range(3):
            mesh.face((centre_high, high[j], high[j+1]))
            mesh.face((centre_low, low[j+1], low[j]))
        mesh.face((centre_high, prev_high[-1], high[0]))
        mesh.face((centre_low, low[0], prev_low[-1]))
    obj = mesh.object(name, material)
    if fallen.faces:
        fallen.object(name+" fallen column blocks", material)
    return obj


def hull(mesh, centre, size, rng, count=16):
    bm = bmesh.new()
    for _ in range(count):
        p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        bm.verts.new(tuple(centre[i]+p[i]*size[i] for i in range(3)))
    result = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
    for face in bm.faces:
        mesh.face([v.co.copy() for v in face.verts])
    bm.free()


def boulder(mesh, base, centre, size, rng):
    bm = bmesh.new()
    stretch = Vector((rng.uniform(.8, 1.25), rng.uniform(.65, 1), rng.uniform(.65, 1)))
    for _ in range(rng.randint(17, 24)):
        p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized()
        p *= size*rng.uniform(.7, 1.15)
        p = Vector((p.x*stretch.x+p.z*.24, p.y*stretch.y, p.z*stretch.z))
        bm.verts.new(Vector(centre)+p)
    bmesh.ops.convex_hull(bm, input=list(bm.verts))
    for face in bm.faces:
        poly = [v.co.copy() for v in face.verts]
        level = centre[2]+size*.18
        for target, normal, limit in ((mesh, Vector((0, 0, -1)), -level),
                                      (base, Vector((0, 0, 1)), level)):
            clipped = clip_plane(poly, normal, limit)
            if len(clipped) >= 3:
                target.face(clipped)
    bm.free()


def branch(mesh, start, end, radius):
    axis = (end-start).normalized()
    u = axis.cross(Vector((0, 1, .1))).normalized()
    v = axis.cross(u)
    rings = [[p+(u*math.cos(i*TAU/7)+v*math.sin(i*TAU/7))*r for i in range(7)]
             for p, r in ((start, radius), (end, radius*.45))]
    for i in range(7):
        j = (i+1)%7
        mesh.face((rings[0][i], rings[0][j], rings[1][j], rings[1][i]))
    mesh.face(list(reversed(rings[0])))
    mesh.face(rings[1])


def blob(mesh, centre, size, seed, flat=False):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1)
    for v in bm.verts:
        p = v.co.copy()
        if flat and p.z > .25:
            p.z = .25+(p.z-.25)*.45
        variation = 1+.10*noise.noise(p*3.1+Vector((seed*.13, 4, 7)))
        v.co = Vector(centre)+Vector((p.x*size[0], p.y*size[1], p.z*size[2]))*variation
    for face in bm.faces:
        mesh.face([v.co.copy() for v in face.verts])
    bm.free()


def blade(mesh, start, direction, length, width, bend):
    side = Vector((-direction.y, direction.x, 0)).normalized()*width
    rings = []
    for i in range(5):
        t = i/4
        centre = start+direction*(length*t)+bend*(t*t)
        rings.append((centre-side*(1-t), centre+side*(1-t)))
    for i in range(3):
        mesh.face((rings[i][0], rings[i][1], rings[i+1][1], rings[i+1][0]))
    mesh.face((rings[3][0], rings[3][1], rings[4][0]))


def rim_point(angle, z):
    angle %= TAU
    for a, b, low, high, index in RIM_WALL:
        if a <= angle <= b:
            t = (angle-a)/(b-a)
            fractions = (0, .14, .83, 1)
            j = next(i for i in range(3) if t <= fractions[i+1])
            u = (t-fractions[j])/(fractions[j+1]-fractions[j])
            bottom, top = low[j].lerp(low[j+1], u), high[j].lerp(high[j+1], u)
            v = max(0, min(1, (z-bottom.z)/(top.z-bottom.z)))
            corners = (low[j], low[j+1], high[j+1], high[j])
            width = (corners[1]-corners[0]).length
            height = max((corners[3]-corners[0]).length, (corners[2]-corners[1]).length)
            normal = (corners[1]-corners[0]).cross(corners[3]-corners[0]).normalized()
            rng = random.Random(SEED+11*1301+index*37+j)
            pivot = Vector((width*rng.uniform(.28, .72), height*rng.uniform(.3, .7)))
            centre = corners[0].lerp(corners[1], pivot.x/width).lerp(
                corners[3].lerp(corners[2], pivot.x/width), pivot.y/height)
            centre += normal*rng.uniform(.2, min(1, width*.12))
            uv = (Vector((0, 0)), Vector((width, 0)), Vector((width, height)), Vector((0, height)))
            q = Vector((u*width, v*height))
            p = bottom.lerp(top, v)
            for facet in range(4):
                k = (facet+1)%4
                x, y, c = uv[facet], uv[k], pivot
                det = (y.x-x.x)*(c.y-x.y)-(y.y-x.y)*(c.x-x.x)
                f = ((q.x-x.x)*(c.y-x.y)-(q.y-x.y)*(c.x-x.x))/det
                g = ((y.x-x.x)*(q.y-x.y)-(y.y-x.y)*(q.x-x.x))/det
                if f >= -.0001 and g >= -.0001 and f+g <= 1.0001:
                    p = corners[facet]+(corners[k]-corners[facet])*f+(centre-corners[facet])*g
                    break
            p.z = z
            return p+Vector((math.cos(angle)*.08, math.sin(angle)*.08, 0))
    raise ValueError("Summit wall must precede turf")


def turf_edge(angle):
    rng = random.Random(SEED+int((angle % TAU)/TAU*640)*73)
    p = edge(angle, 1.006)
    p += Vector((math.cos(angle), math.sin(angle), 0))*rng.uniform(-3, 1.2)
    return p


def turf():
    soil, grass, drapes, blades, exposed = Mesh(), Mesh(), Mesh(), Mesh(), Mesh()
    exposed_tops = Mesh()
    n, rings = 640, 50
    for i in range(n):
        a, b = TAU*i/n, TAU*(i+1)/n
        pa, pb = turf_edge(a), turf_edge(b)
        za, zb = summit(pa.x, pa.y), summit(pb.x, pb.y)
        rng_edge = random.Random(SEED+i*73)
        bottom_a = za-rng_edge.uniform(.4, 3)
        bottom_b = zb-rng_edge.uniform(.4, 3)
        overhang = .5+max(0, math.sin(31*a))*1
        sa = pa-Vector((math.cos(a), math.sin(a), 0))*overhang
        sb = pb-Vector((math.cos(b), math.sin(b), 0))*overhang
        gap = math.sin(23*a+.3) > .78
        if not gap:
            soil.face(((sa.x, sa.y, bottom_a), (sb.x, sb.y, bottom_b),
                   (sb.x, sb.y, zb), (sa.x, sa.y, za)))
            soil.face(((sa.x, sa.y, bottom_a), (sb.x, sb.y, bottom_b),
                   (pb.x, pb.y, zb-.2), (pa.x, pa.y, za-.2)))
            grass.face(((sa.x, sa.y, za-.2), (sb.x, sb.y, zb-.2),
                    (pb.x, pb.y, zb-.2), (pa.x, pa.y, za-.2)))
        for j in range(rings):
            pts = []
            for angle, r in ((a, j/rings), (b, j/rings), (b, (j+1)/rings), (a, (j+1)/rings)):
                p = (pa if angle == a else pb)*r
                pts.append((p.x, p.y, summit(p.x, p.y)))
            if j == 0:
                grass.face((pts[0], pts[2], pts[3]))
            elif not (gap and j >= rings-2):
                grass.face(pts)
        if gap:
            top = []
            for p, r in ((pa, .96), (pb, .96), (pb, 1), (pa, 1)):
                q = p*r
                q.z = summit(q.x, q.y)
                top.append(q)
            bottom = [p-Vector((0, 0, 2.4)) for p in top]
            bottom[2] = rim_point(b, bottom[2].z)
            bottom[3] = rim_point(a, bottom[3].z)
            exposed_tops.face(top)
            exposed.face(list(reversed(bottom)))
            for k in range(4):
                l = (k+1)%4
                wall_fractures(exposed, (bottom[k], bottom[l], top[l], top[k]), SEED+i*17+k)
            foot_a, foot_b = rim_point(a, TOP-3), rim_point(b, TOP-3)
            wall_fractures(exposed, (foot_b, foot_a, bottom[3], bottom[2]), SEED+i*19)
    rng = random.Random(SEED+82)
    for _ in range(145):
        a = rng.uniform(0, TAU)
        width, length, thickness = rng.uniform(1.4, 3.6), rng.uniform(3.5, 5), rng.uniform(.2, .5)
        normal = Vector((math.cos(a), math.sin(a), 0))
        fronts, backs = [], []
        p0 = turf_edge(a)
        angular_width = width/max(60, math.hypot(p0.x, p0.y))
        torn = [rng.uniform(-.65, .5) for _ in range(11)]
        for j in range(9):
            t = j/8
            front, back = [], []
            for k in range(11):
                u = k/10
                angle = a+(u*2-1)*angular_width*(1-.10*t)+.0015*math.sin(t*8+a)
                z = summit(p0.x, p0.y)-.2-t*(length+torn[k])
                p = rim_point(angle, z)
                lip = turf_edge(angle)
                lip.z = z
                p = lip.lerp(p, min(1, t/.35))
                radial = Vector((math.cos(angle), math.sin(angle), 0))
                front.append(p+radial*thickness)
                back.append(p)
            fronts.append(front)
            backs.append(back)
        for j in range(8):
            for k in range(10):
                drapes.face((fronts[j][k], fronts[j][k+1], fronts[j+1][k+1], fronts[j+1][k]))
                drapes.face((backs[j][k+1], backs[j][k], backs[j+1][k], backs[j+1][k+1]))
            for k in (0, 10):
                drapes.face((fronts[j][k], backs[j][k], backs[j+1][k], fronts[j+1][k]))
        for j in (0, 8):
            for k in range(10):
                drapes.face((fronts[j][k], fronts[j][k+1], backs[j][k+1], backs[j][k]))
        for _ in range(150):
            u = rng.uniform(0, 10)
            k = min(9, int(u))
            t = rng.uniform(.8, 1)
            p = fronts[8][k].lerp(fronts[8][k+1], u-k)+Vector((0, 0, (1-t)*length))
            blade(blades, p, (normal*.10+Vector((0, 0, -.995))).normalized(),
                  rng.uniform(.5, 2.5), rng.uniform(.025, .065), normal*rng.uniform(.12, .4))
    soil.object("Jagged soil bedding rim", "forest_soil")
    exposed.object("Limestone exposed through slumped turf bites", "canyon_layered")
    exposed_tops.object("Grey weathered tops of solid rim blocks", "monument_weathered")
    grass.object("Undulating meadow", "grass_ground")
    drapes.object("Thin torn turf curtains hugging the cliff", "grass_ground")
    blades.object("Opaque tapered rim grass curtains", "grass_ground")
    cover = Mesh()
    for _ in range(32000):
        a, r = rng.uniform(0, TAU), math.sqrt(rng.random())*.985
        p = edge(a, r)
        if noise.noise(Vector((p.x*.065, p.y*.065, 13))) < -.32:
            continue
        p.z = summit(p.x, p.y)-.04
        for _ in range(rng.randint(4, 7)):
            angle = rng.uniform(0, TAU)
            direction = Vector((math.cos(angle)*.17, math.sin(angle)*.17, .98))
            blade(cover, p+Vector((rng.uniform(-.16, .16), rng.uniform(-.16, .16), 0)),
                  direction, rng.uniform(.17, .62), rng.uniform(.015, .035),
                  Vector((math.cos(angle)*.20, math.sin(angle)*.20, -.07)))
    cover.object("Dense irregular meadow tuft patches", "grass_ground")


def vegetation():
    rng = random.Random(SEED+3)
    trunks, stones, stone_bases, stone_grass = Mesh(), Mesh(), Mesh(), Mesh()
    crowns, shrubs = [Mesh() for _ in range(6)], [Mesh() for _ in range(4)]
    for cx, cy, number in ((-70, 20, 15), (-35, -26, 12), (56, 25, 16), (14, 43, 10), (86, -14, 7)):
        for _ in range(number):
            x, y = rng.gauss(cx, 12), rng.gauss(cy, 9)
            h = rng.uniform(4.8, 12.7)
            variant = rng.randrange(6)
            umbrella = rng.random() < .65
            start = Vector((x, y, summit(x, y)-.3))
            fork = start+Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), h*.61))
            branch(trunks, start, fork, h*.045)
            for _ in range(rng.randint(3, 5) if umbrella else rng.randint(2, 4)):
                a = rng.uniform(0, TAU)
                reach = rng.uniform(.25, .43) if umbrella else rng.uniform(.12, .27)
                tip = fork+Vector((math.cos(a)*h*reach, math.sin(a)*h*reach,
                                   h*(rng.uniform(.23, .30) if umbrella else rng.uniform(.15, .40))))
                branch(trunks, fork, tip, h*.018)
                size = (h*rng.uniform(.27, .37), h*rng.uniform(.22, .32), h*rng.uniform(.17, .22)) if umbrella else (
                    h*rng.uniform(.20, .27), h*rng.uniform(.18, .28), h*rng.uniform(.23, .33))
                blob(crowns[variant], tip, size, rng.randrange(10000), flat=umbrella)
                if rng.random() < .45:
                    blob(crowns[variant], tip+Vector((h*.12, -h*.1, 0)),
                         (h*.19, h*.17, h*.13 if umbrella else h*.22), rng.randrange(10000), flat=umbrella)
    for cx, cy in ((-91, -20), (39, -34), (5, 27), (80, 6), (-24, 12)):
        for _ in range(18):
            x, y = rng.gauss(cx, 5), rng.gauss(cy, 4)
            s = rng.uniform(.6, 1.8)
            variant = rng.randrange(4)
            for _ in range(rng.randint(2, 5)):
                blob(shrubs[variant], (x+rng.uniform(-s*.5, s*.5), y+rng.uniform(-s*.5, s*.5), summit(x, y)+s*.4),
                     (s*rng.uniform(.5, .9), s*rng.uniform(.4, .8), s*rng.uniform(.4, .9)),
                     rng.randrange(10000), flat=variant == 0)
    for cx, cy in ((-87, -34), (-4, -47), (34, -5), (-21, 26), (93, 30), (7, 5)):
        for i in range(rng.randint(4, 8)):
            x, y = rng.gauss(cx, 3), rng.gauss(cy, 2)
            s = rng.uniform(1.9, 2.8) if i < 2 else rng.uniform(.5, 1.25)
            boulder(stones, stone_bases, (x, y, summit(x, y)-s*.15), s, rng)
            for _ in range(48):
                a = rng.uniform(0, TAU)
                p = Vector((x+math.cos(a)*s*rng.uniform(.75, 1.2),
                            y+math.sin(a)*s*rng.uniform(.65, 1), 0))
                p.z = summit(p.x, p.y)-.04
                blade(stone_grass, p, Vector((math.cos(a)*.2, math.sin(a)*.2, .98)),
                      rng.uniform(.25, .8), rng.uniform(.025, .055), Vector((.1, .1, -.1)))
    for _ in range(15):
        a = rng.uniform(0, TAU)
        p = edge(a, rng.uniform(.96, 1.015))
        p.z = rng.uniform(141, 146)
        hull(stones, p, (rng.uniform(2, 5), rng.uniform(2, 4), rng.uniform(2, 4)), rng, 10)
    trunks.object("Forked acacia trunks", "tree_bark")
    for i, crown in enumerate(crowns):
        crown.object("Varied olive umbrellas and rounded crowns %d" % i, crown_material(i), smooth=True)
    for i, shrub in enumerate(shrubs):
        shrub.object("Varied shrub clusters %d" % i, crown_material(i+1), smooth=True)
    stones.object("Half buried angular blocks and ledge falls", "canyon_layered")
    stone_bases.object("Weathered lower fracture planes", "monument_weathered")
    stone_grass.object("Tufts around sunken stones", "grass_ground")


def fragments():
    rng = random.Random(SEED+17)
    for i, (x, y, z, scale) in enumerate(((-151, 9, 114, .105), (149, -30, 123, .12))):
        for j, (lo, hi, width, shift) in enumerate(((z-19, z-12, scale*.45, (3, 1)),
                                                   (z-13, z-6, scale*.82, (1, -1)),
                                                   (z-7, z, scale, (0, 0)))):
            strata("Floating mini massif %d bed %d" % (i, j), lo, hi, width, shift, 20+i*3+j,
                   origin=(x, y))
        cap, soil = Mesh(), Mesh()
        phase = .4*math.sin((22+i*3)*1.73)
        rim = [edge(j*TAU/90, scale, phase=phase)+Vector((x, y, z+1.5)) for j in range(90)]
        cap.face(rim)
        for j in range(90):
            k = (j+1)%90
            soil.face((rim[j], rim[k], rim[k]-Vector((0, 0, 1.3)), rim[j]-Vector((0, 0, 1.3))))
        cap.object("Thin meadow cap %d" % i, "grass_ground")
        soil.object("Fragment soil lip %d" % i, "forest_soil")
        keel = Mesh()
        rings = []
        for t, radius in ((0, scale*.42), (.55, scale*.29), (1, scale*.025)):
            rings.append([edge(j*TAU/7, radius)+Vector((x+3+t*2, y+1-t, z-19-t*7)) for j in range(7)])
        for j in range(2):
            for k in range(7):
                keel.face((rings[j][k], rings[j][(k+1)%7], rings[j+1][(k+1)%7], rings[j+1][k]))
        keel.face(list(reversed(rings[0])))
        keel.face(rings[-1])
        keel.object("Short broken fragment keel %d" % i, "canyon_layered")
    blocks = Mesh()
    hull(blocks, (129, 62, 94), (11, 7, 8), rng, 11)
    hull(blocks, (126, 60, 90), (7, 6, 7), rng, 9)
    blocks.object("Detached angular multi fracture chunk", "canyon_layered")


def build():
    RIM_WALL.clear()
    # Unequal bed heights and lateral migration carry the keel away from the summit centre.
    beds = ((.5, 9, .016, (-40, 8)), (8, 18, .031, (-37, 7)),
            (17, 29, .054, (-35, 7)), (28, 42, .089, (-30, 5)),
            (40, 56, .145, (-25, 4)), (54, 73, .215, (-17, 6)),
            (71, 91, .32, (-11, 8)), (89, 107, .46, (-5, 8)),
            (105, 120, .65, (3, 5)), (118, 130, .80, (6, 2)),
            (128, 139, .91, (3, 0)), (137, 147, 1, (0, 0)))
    for i, (lo, hi, width, shift) in enumerate(beds):
        strata("Jointed chalk bed %02d" % i, lo, hi, width, shift, i,
               "monument_weathered" if i in (3, 7) else "canyon_layered")
    rng = random.Random(SEED+90)
    spurs = Mesh()
    for centre, size in (((-59, 12, 97), (13, 14, 25)), ((49, 25, 112), (12, 13, 20))):
        hull(spurs, centre, size, rng, 13)
    spurs.object("Secondary hanging fault spurs", "canyon_layered")
    turf()
    vegetation()
    fragments()
    scene = bpy.context.scene
    scene["vr_review_floating"] = True
    scene["vr_review_figure"] = (-38, -40, summit(-38, -40))
    scene["vr_review_turn"] = (0, 0, 86, 247, 16, 600)
    scene["vr_closeup_upper"] = (-35, -53, 147, 247, 22, 115)
    scene["vr_closeup_base"] = (-22, 2, 46, 247, 5, 195)

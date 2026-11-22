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
        obj.data.materials.append(vrmat.get(material) if isinstance(material, str) else material)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.0001)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = bool(smooth)
        if smooth == "rock":
            mesh.set_sharp_from_angle(angle=math.radians(30))
        return vrlib.link_to_source(obj)


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
    nx, ny = max(1, math.ceil(width/.4)), max(1, math.ceil(height/.4))
    xs = sorted({*[width*i/nx for i in range(nx+1)],
                 *[min(width, max(0, x+d)) for x, w, _ in grooves for d in (-w, 0, w)]})
    ys = sorted({*[height*i/ny for i in range(ny+1)],
                 *[min(height, max(0, y+d)) for y, w, _ in beds for d in (-w, 0, w)]})
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
            relief = fractured_relief(base, seed)
            return base+normal*(relief-depth)*fade

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
                    points = [point(p) for p in poly]
                    for k in range(1, len(points)-1):
                        mesh.face((points[0], points[k], points[k+1]))


def fractured_relief(p, seed):
    offset = Vector((seed*.137, seed*.073, seed*.191))
    q = Vector((p.x*.81+p.y*.59, p.y*.81-p.x*.59, p.z))
    large = fracture_field(Vector((q.x*.23, q.y*.23, q.z*.105))+offset, seed)
    steps = fracture_field(q*(.8+(seed % 17)*.013)+offset*1.71, seed+73)
    grain = fracture_field(q*4.3+offset*2.37, seed+191)
    return large*2.6+math.floor(steps*2)*.32+grain*.055


def fracture_field(p, seed):
    cell = [math.floor(v) for v in p]
    fraction = [p[i]-cell[i] for i in range(3)]
    order = sorted(range(3), key=lambda i: fraction[i], reverse=True)
    values = []
    for k in range(4):
        values.append((math.sin(cell[0]*127.1+cell[1]*311.7+cell[2]*74.7+seed)*43758.5453) % 1*2-1)
        if k < 3:
            cell[order[k]] += 1
    a, b, c = (fraction[i] for i in order)
    return values[0]*(1-a)+values[1]*(a-b)+values[2]*(b-c)+values[3]*c


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
    obj = mesh.object(name, material, smooth="rock")
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
    phase = rng.uniform(0, TAU)
    lean = rng.uniform(-.6, .6)
    sx, sy = rng.uniform(.65, 1.05), rng.uniform(.55, .9)
    corners = ((-1, -rng.uniform(.3, .75)), (-rng.uniform(.3, .8), -1),
               (rng.uniform(.3, .8), -1), (1, -rng.uniform(.3, .75)),
               (1, rng.uniform(.3, .75)), (rng.uniform(.3, .8), 1),
               (-rng.uniform(.3, .8), 1), (-1, rng.uniform(.3, .75)))
    chipped = rng.randrange(8)
    for upper in (False, True):
        taper = rng.uniform(.75, .95) if upper else 1
        for i, (x, y) in enumerate(corners):
            x, y = x*sx*taper, y*sy*taper
            z = .48+.25*x-.2*y if upper else -.55+.08*x
            if upper and i == chipped:
                z -= rng.uniform(.18, .35)
            x, z = x*math.cos(lean)+z*math.sin(lean), z*math.cos(lean)-x*math.sin(lean)
            p = Vector((math.cos(phase)*x-math.sin(phase)*y,
                        math.sin(phase)*x+math.cos(phase)*y, z))*size
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
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1)
    for v in bm.verts:
        p = v.co.copy()
        if flat:
            p.z *= .75
        variation = 1+.4*noise.noise(p*4.7+Vector((seed*.13, 4, 7)))+.16*noise.noise(p*13+Vector((1, seed, 4)))
        v.co = Vector(centre)+Vector((p.x*size[0], p.y*size[1], p.z*size[2]))*variation
    for face in bm.faces:
        mesh.face([v.co.copy() for v in face.verts])
    bm.free()


def leafy_mass(mesh, centre, size, seed):
    rng = random.Random(seed)
    blob(mesh, centre, size, seed)
    for _ in range(rng.randint(5, 9)):
        direction = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-.65, 1))).normalized()
        p = Vector(centre)+Vector((direction.x*size[0], direction.y*size[1], direction.z*size[2]))*.85
        scale = rng.uniform(.23, .46)
        blob(mesh, p, tuple(s*scale for s in size), rng.randrange(100000))


def meadow_paths():
    paths = []
    for controls in (((-98, -25), (-65, -53), (-18, -12), (51, -24)),
                     ((-30, -29), (5, -15), (-7, 45), (70, 36))):
        controls = [Vector((x, y, 0)) for x, y in controls]
        path = []
        for i in range(97):
            t = i/96
            p = controls[0]*(1-t)**3+controls[1]*(3*t*(1-t)**2)+controls[2]*(3*t*t*(1-t))+controls[3]*t**3
            path.append(p)
        paths.append(path)
    return paths


def ground_features():
    rng = random.Random(SEED+391)
    worn, damp, stems = Mesh(), Mesh(), Mesh()
    flowers = [Mesh() for _ in range(3)]
    for path in meadow_paths():
        for i in range(len(path)-1):
            a, b = path[i:i+2]
            side = Vector((-(b-a).y, (b-a).x, 0)).normalized()
            points = []
            for p, sign in ((a, -1), (b, -1), (b, 1), (a, 1)):
                width = .65+.25*math.sin(p.x*.6+p.y*.3)
                q = p+side*(width*sign)
                q.z = summit(q.x, q.y)+.045
                points.append(q)
            worn.face(points)
    for cx, cy, radius in ((-48, 3, 7), (30, 17, 6), (63, -12, 4), (-12, 48, 5), (-78, 30, 4)):
        n = 48
        ring = []
        for i in range(n):
            a = i*TAU/n
            r = radius*(1+.17*math.sin(a*5+cx)+.12*math.sin(a*9+cy))
            ring.append(Vector((cx+math.cos(a)*r, cy+math.sin(a)*r*.65, 0)))
        for i in range(n):
            pts = [Vector((cx, cy, 0)), ring[i].copy(), ring[(i+1)%n].copy()]
            for p in pts:
                p.z = summit(p.x, p.y)+.025
            damp.face(pts)
    for _ in range(38):
        x, y = rng.uniform(-97, 97), rng.uniform(-50, 50)
        variant = rng.randrange(3)
        for _ in range(rng.randint(18, 40)):
            p = Vector((rng.gauss(x, .85), rng.gauss(y, .65), 0))
            p.z = summit(p.x, p.y)
            tip = p+Vector((rng.uniform(-.08, .08), rng.uniform(-.08, .08), rng.uniform(.24, .5)))
            branch(stems, p, tip, .012)
            radius = rng.uniform(.055, .105)
            for k in range(5):
                a = k*TAU/5
                side = Vector((-math.sin(a), math.cos(a), 0))*radius*.38
                end = tip+Vector((math.cos(a)*radius, math.sin(a)*radius, -.025))
                flowers[variant].face((tip, end-side, end+side))
    worn.object("Winding worn meadow footpaths", "dirt_path")
    damp.object("Irregular damp ground hollows", "forest_soil")
    stems.object("Fine wildflower stems", "grass_ground")
    for mesh, material in zip(flowers, ("monument_white", "sandstone", "violet_crystal")):
        mesh.object("Small meadow flower clumps "+material, material)


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
    u = (angle % TAU)/TAU*96
    i, t = int(u), u % 1
    t = t*t*(3-2*t)
    x = random.Random(SEED+(i % 96)*73).uniform(-4, 2.5)
    y = random.Random(SEED+((i+1) % 96)*73).uniform(-4, 2.5)
    p = edge(angle, 1.006)
    p += Vector((math.cos(angle), math.sin(angle), 0))*(x+(y-x)*t)
    return p


def turf():
    soil, grass, blades, exposed = Mesh(), Mesh(), Mesh(), Mesh()
    n, rings = 640, 50
    for i in range(n):
        a, b = TAU*i/n, TAU*(i+1)/n
        pa, pb = turf_edge(a), turf_edge(b)
        za, zb = summit(pa.x, pa.y), summit(pb.x, pb.y)
        gap = math.sin(23*a+.3)+.35*math.sin(47*a) > .57
        if not gap:
            profiles = []
            for angle, p, z in ((a, pa, za), (b, pb, zb)):
                radial = Vector((math.cos(angle), math.sin(angle), 0))
                depth = .3+1.2*(.5+.5*math.sin(39*angle+.7)*math.cos(17*angle))
                bulge = -.45+.16*math.sin(51*angle)
                profile = []
                for inset, drop in ((-1.25, .12), (-.4, .12), (bulge, depth*.32),
                                    (bulge-.15, depth*.78), (-.9, depth), (-1.4, depth*.8)):
                    profile.append(p+radial*inset+Vector((0, 0, -drop+z)))
                profiles.append(profile)
            for k in range(6):
                l = (k+1)%6
                soil.face((profiles[0][k], profiles[1][k], profiles[1][l], profiles[0][l]))
            previous = a-TAU/n
            if math.sin(23*previous+.3)+.35*math.sin(47*previous) > .57:
                soil.face(list(reversed(profiles[0])))
            if math.sin(23*b+.3)+.35*math.sin(47*b) > .57:
                soil.face(profiles[1])
            curls = []
            for angle, p, z in ((a, pa, za), (b, pb, zb)):
                radial = Vector((math.cos(angle), math.sin(angle), 0))
                curl = .15+.5*(.5+.5*math.sin(29*angle+.3))
                curls.append([p+radial*inset+Vector((0, 0, z-drop))
                              for inset, drop in ((0, 0), (.1, curl*.25), (-.05, curl*.7), (-.4, curl))])
            for k in range(3):
                grass.face((curls[0][k], curls[1][k], curls[1][k+1], curls[0][k+1]))
        for j in range(rings):
            pts = []
            for angle, r in ((a, j/rings), (b, j/rings), (b, (j+1)/rings), (a, (j+1)/rings)):
                p = (pa if angle == a else pb)*r
                pts.append((p.x, p.y, summit(p.x, p.y)))
            if j == 0:
                grass.face((pts[0], pts[2], pts[3]))
            else:
                grass.face(pts)
        if gap:
            top_a, top_b = pa.copy(), pb.copy()
            top_a.z, top_b.z = za-.12, zb-.12
            wall_fractures(exposed, (rim_point(a, TOP-2), rim_point(b, TOP-2), top_b, top_a), SEED+i*19)
    rng = random.Random(SEED+82)
    for _ in range(195):
        a = rng.uniform(0, TAU)
        width, length = rng.uniform(.7, 3), rng.uniform(.6, 4.5)
        normal = Vector((math.cos(a), math.sin(a), 0))
        p0 = turf_edge(a)
        angular_width = width/max(60, math.hypot(p0.x, p0.y))
        for _ in range(rng.randint(45, 370)):
            angle = a+rng.uniform(-1, 1)*angular_width
            p = turf_edge(angle)+normal*rng.uniform(-.3, .45)
            p.z = summit(p.x, p.y)-rng.uniform(.03, .35)
            direction = (normal*rng.uniform(.18, .4)+Vector((rng.uniform(-.08, .08), rng.uniform(-.08, .08), -.95))).normalized()
            blade(blades, p, direction, length*rng.uniform(.3, 1.15),
                  rng.uniform(.009, .028), normal*rng.uniform(.12, .65)+Vector((0, 0, -.15)))
    soil.object("Soft irregular soil overhangs", "forest_soil", smooth=True)
    for vertex in exposed.vertices:
        vertex.z = min(vertex.z, summit(vertex.x, vertex.y)-.25)
    exposed.object("Limestone exposed through slumped turf bites", "canyon_layered", smooth="rock")
    grass.object("Undulating meadow", "grass_ground")
    blades.object("Opaque tapered rim grass curtains", "grass_ground")
    cover = Mesh()
    path_points = [p for path in meadow_paths() for p in path]
    for _ in range(32000):
        a, r = rng.uniform(0, TAU), math.sqrt(rng.random())*.985
        p = edge(a, r)
        density = noise.noise(Vector((p.x*.065, p.y*.065, 13)))
        if density < -.12 or any((p-q).length_squared < .85**2 for q in path_points):
            continue
        p.z = summit(p.x, p.y)-.04
        for _ in range(rng.randint(5, 12)):
            angle = rng.uniform(0, TAU)
            direction = Vector((math.cos(angle)*.17, math.sin(angle)*.17, .98))
            blade(cover, p+Vector((rng.uniform(-.16, .16), rng.uniform(-.16, .16), 0)),
                  direction, rng.uniform(.22, .9), rng.uniform(.015, .035),
                  Vector((math.cos(angle)*.20, math.sin(angle)*.20, -.07)))
    cover.object("Dense irregular meadow tuft patches", "grass_ground")


def vegetation():
    rng = random.Random(SEED+3)
    trunks, stones, stone_bases, stone_grass = Mesh(), Mesh(), Mesh(), Mesh()
    crowns, shrubs = [Mesh() for _ in range(6)], [Mesh() for _ in range(4)]
    for cx, cy, number in ((-64, 17, 16), (-24, -23, 11), (43, 29, 18)):
        for _ in range(number):
            x, y = rng.gauss(cx, 9), rng.gauss(cy, 7)
            h = rng.uniform(5.2, 11)
            variant = rng.randrange(6)
            tree_type = rng.randrange(3)
            start = Vector((x, y, summit(x, y)-.3))
            bend = start+Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), h*.25))
            fork = bend+Vector((rng.uniform(-1.1, 1.1), rng.uniform(-1.1, 1.1), h*.23))
            branch(trunks, start, bend, h*.037)
            branch(trunks, bend, fork, h*.029)
            phase = rng.uniform(0, TAU)
            limbs = rng.randint(2, 4)
            for limb in range(limbs):
                a = phase+limb*TAU/limbs+rng.uniform(-.35, .35)
                reach = rng.uniform(.3, .52) if tree_type != 1 else rng.uniform(.17, .3)
                tip = fork+Vector((math.cos(a)*h*reach, math.sin(a)*h*reach,
                                   h*rng.uniform(.18, .38 if tree_type == 1 else .28)))
                branch(trunks, fork, tip, h*.018)
                for _ in range(rng.randint(3, 6)):
                    direction = rng.uniform(0, TAU)
                    reach = rng.uniform(.08, .22)*h
                    centre = tip+Vector((math.cos(direction)*reach, math.sin(direction)*reach,
                                         rng.uniform(-.06, .16)*h))
                    branch(trunks, tip, centre, h*.006)
                    s = h*rng.uniform(.075, .145)
                    leafy_mass(crowns[variant], centre,
                               (s*rng.uniform(.8, 1.45), s*rng.uniform(.7, 1.2),
                                s*(rng.uniform(.6, .95) if tree_type == 0 else rng.uniform(.85, 1.5))),
                               rng.randrange(100000))
    for cx, cy in ((-91, -20), (39, -34), (5, 27), (80, 6), (-24, 12)):
        for _ in range(18):
            x, y = rng.gauss(cx, 5), rng.gauss(cy, 4)
            s = rng.uniform(.6, 1.8)
            variant = rng.randrange(4)
            for _ in range(rng.randint(2, 5)):
                leafy_mass(shrubs[variant], (x+rng.uniform(-s*.5, s*.5), y+rng.uniform(-s*.5, s*.5), summit(x, y)+s*.4),
                     (s*rng.uniform(.5, .9), s*rng.uniform(.4, .8), s*rng.uniform(.4, .9)),
                     rng.randrange(10000))
    for cx, cy in ((-87, -34), (-4, -47), (34, -5), (-21, 26), (93, 30), (7, 5)):
        for i in range(rng.randint(2, 6)):
            x, y = rng.gauss(cx, 3), rng.gauss(cy, 2)
            s = rng.uniform(2.4, 3) if i < 3 else rng.uniform(.5, 1.7)
            boulder(stones, stone_bases, (x, y, summit(x, y)-s*.02), s, rng)
            for _ in range(48):
                a = rng.uniform(0, TAU)
                p = Vector((x+math.cos(a)*s*rng.uniform(.75, 1.2),
                            y+math.sin(a)*s*rng.uniform(.65, 1), 0))
                p.z = summit(p.x, p.y)-.04
                blade(stone_grass, p, Vector((math.cos(a)*.2, math.sin(a)*.2, .98)),
                      rng.uniform(.25, .8), rng.uniform(.025, .055), Vector((.1, .1, -.1)))
    for x, y in ((-7, -19), (76, -30), (-109, 8), (15, 6)):
        s = rng.uniform(.8, 1.8)
        boulder(stones, stone_bases, (x, y, summit(x, y)-s*.02), s, rng)
    trunks.object("Forked acacia trunks", "tree_bark")
    for i, crown in enumerate(crowns):
        crown.object("Open irregular leafy canopies %d" % i, "foliage_leaf", smooth=True)
    for i, shrub in enumerate(shrubs):
        shrub.object("Varied leafy shrub masses %d" % i, "foliage_leaf", smooth=True)
    stones.object("Half buried fractured weathered limestone", "mossy_rock")
    stone_bases.object("Weathered lower fracture planes", "mossy_rock")
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
    ground_features()
    vegetation()
    fragments()
    scene = bpy.context.scene
    scene["vr_review_floating"] = True
    scene["vr_review_figure"] = (0, 0, -1000)
    scene["vr_review_turn"] = (0, 0, 86, 247, 16, 600)
    scene["vr_closeup_upper"] = (-35, -53, 147, 247, 22, 115)
    scene["vr_closeup_base"] = (-22, 2, 46, 247, 5, 195)

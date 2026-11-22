"""Doppelt gefiederte Farnrosette mit durchgehend gebogenen Wedeln."""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise

import vrlib
import vrmat

UP = Vector((0, 0, 1))


class Mesh:
    def __init__(self):
        self.vertices, self.faces, self.indices = [], [], []

    def face(self, points, material):
        start = len(self.vertices)
        self.vertices.extend(points)
        self.faces.append(tuple(range(start, len(self.vertices))))
        self.indices.append(material)

    def tube(self, points, radius, material, sides=5):
        start = len(self.vertices)
        for i, point in enumerate(points):
            direction = (points[min(i+1, len(points)-1)]-points[max(0, i-1)]).normalized()
            axis = direction.cross(Vector((0, 1, 0))).normalized()
            other = direction.cross(axis)
            r = radius*(1-.75*i/(len(points)-1))
            for j in range(sides):
                a = math.tau*j/sides
                self.vertices.append(point+r*(axis*math.cos(a)+other*math.sin(a)))
            if i:
                for j in range(sides):
                    a, b = start+(i-1)*sides+j, start+(i-1)*sides+(j+1)%sides
                    self.faces.append((a, b, b+sides, a+sides))
                    self.indices.append(material)
        for face in (tuple(start+j for j in reversed(range(sides))),
                     tuple(start+(len(points)-1)*sides+j for j in range(sides))):
            self.faces.append(face)
            self.indices.append(material)

    def object(self, name, materials):
        if not self.faces:
            return None
        data = bpy.data.meshes.new(name)
        data.from_pydata(self.vertices, [], self.faces)
        data.update()
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000001)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        remaining = set(bm.faces)
        while remaining:
            component = [remaining.pop()]
            stack = component[:]
            while stack:
                face = stack.pop()
                for edge in face.edges:
                    for neighbour in edge.link_faces:
                        if neighbour in remaining:
                            remaining.remove(neighbour)
                            component.append(neighbour)
                            stack.append(neighbour)
            if all(edge.is_manifold for face in component for edge in face.edges):
                reference = component[0].verts[0].co.copy()
                volume = 0
                for face in component:
                    a = face.verts[0].co-reference
                    for j in range(1, len(face.verts)-1):
                        b, c = face.verts[j].co-reference, face.verts[j+1].co-reference
                        volume += a.dot(b.cross(c))
                if volume < 0:
                    bmesh.ops.reverse_faces(bm, faces=component)
        bm.to_mesh(data)
        bm.free()
        obj = bpy.data.objects.new(name, data)
        for material in materials:
            data.materials.append(material)
        for face, index in zip(data.polygons, self.indices):
            face.material_index = index
            face.use_smooth = True
        return vrlib.link_to_source(obj)



SEED = 82719
FROND_SLOTS = 12


def materials():
    palette = vrmat.load_palette()
    result = []
    for name, library, first, second, blend, gain in [
        ("Olivbasis", "foliage_leaf", "grass_green", "grass_dry", .55, 1.8),
        ("Olivlaub", "foliage_leaf", "grass_green", "grass_dry", .55, 2.1),
        ("Lichtspitzen", "foliage_leaf", "grass_green", "grass_dry", .55, 2.8),
        ("Kronenoliv", "foliage_leaf", "grass_green", "grass_dry", .7, 1.5),
        ("Blattachsen", "foliage_leaf", "grass_green", "grass_dry", .55, 1.4),
    ]:
        material = vrmat.get(library).copy()
        material.name = name
        bsdf = material.node_tree.nodes["Principled BSDF"]
        socket = bsdf.inputs["Base Color"]
        for link in list(socket.links):
            material.node_tree.links.remove(link)
        socket.default_value = (*(gain*(a*(1-blend)+b*blend) for a, b in zip(
            palette[first]["linear_rgb"], palette[second]["linear_rgb"])), 1)
        bsdf.inputs["Specular IOR Level"].default_value = .2
        result.append(material)
    return result


def pinnule(mesh, root, direction, normal, length, width, material):
    along = direction.normalized()
    across = normal.cross(along).normalized()
    outline = [(0, 0), (.12, -.8), (.32, -1), (.43, -.75), (.62, -1),
               (.85, -.85), (1, -.35), (1, .35), (.85, .85), (.62, 1),
               (.43, .75), (.32, 1), (.12, .8)]
    points = [root+along*(x*length)+across*(y*width)
              +normal*(length*(.06*y*y-.13*x*x)) for x, y in outline]
    centre = root+along*length*.45+normal*length*.025
    for i in range(len(points)):
        mesh.face([centre, points[i], points[(i+1)%len(points)]], material)



def ground_contact(radius, rise, seed, wet=False):
    rise = .022
    rng = random.Random(seed)
    vertices, faces, indices = [], [], []
    def face(points, material):
        start = len(vertices)
        vertices.extend(points)
        faces.append(tuple(range(start, len(vertices))))
        indices.append(material)
    def blade(points, width, side, material, twist):
        rows = []
        count = len(points)-1
        for i, point in enumerate(points):
            t = i/count
            tangent = (points[min(i+1, count)]-points[max(0, i-1)]).normalized()
            across = (side-tangent*side.dot(tangent)).normalized()
            normal = across.cross(tangent).normalized()
            across = across*math.cos(twist*t)+normal*math.sin(twist*t)
            normal = across.cross(tangent).normalized()
            w = width*(.35+.65*min(1, t/.15))*(1-t)**.75
            rows.append([point-across*w*.5, point+normal*w*.24, point+across*w*.5])
        for i in range(count):
            for j in range(2):
                if i == count-1:
                    face([rows[i][j], rows[i+1][j], rows[i][j+1]], material)
                else:
                    face([rows[i][j], rows[i+1][j], rows[i+1][j+1], rows[i][j+1]], material)
    phase = rng.uniform(0, math.tau)
    def height(t, a):
        relief = noise.noise(Vector((radius*t*math.cos(a)*9, radius*t*math.sin(a)*9, (seed%67)*.37)))
        return max(-.045, rise*(1-t*t)+.012*relief*math.sin(math.pi*t)-.045*t**3+.012*math.sin(17*a+phase)*t*t)
    def point(j, k):
        a, t = j*math.tau/64, k/10
        r = radius*t*(1+.13*math.sin(3*a+phase)+.12*math.sin(9*a-phase)+.07*math.sin(17*a+phase))
        return Vector((r*math.cos(a), r*math.sin(a), height(t, a)))
    def soil_material(t, a):
        return 4 if wet and t < .8 and noise.noise(Vector((math.cos(a)*t*9, math.sin(a)*t*9, 3))) > -.2 else 0
    for j in range(64):
        face([Vector((0, 0, rise)), point(j, 1), point(j+1, 1)], soil_material(.05, j*math.tau/64))
        for k in range(1, 10):
            face([point(j, k), point(j, k+1), point(j+1, k+1), point(j+1, k)], soil_material((k+.5)/10, j*math.tau/64))
        bottom = Vector((point(j, 10).x, point(j, 10).y, -.055))
        next_bottom = Vector((point(j+1, 10).x, point(j+1, 10).y, -.055))
        face([point(j, 10), bottom, next_bottom, point(j+1, 10)], 0)
        face([Vector((0, 0, -.055)), next_bottom, bottom], 0)
    count = 720 if radius > .8 else 240 if radius > .3 else 48
    for i in range(count):
        a = rng.uniform(0, math.tau)
        t = rng.uniform(.50, 1.08)
        r = radius*t*(1+.13*math.sin(3*a+phase)+.12*math.sin(9*a-phase)+.07*math.sin(17*a+phase))
        root = Vector((r*math.cos(a), r*math.sin(a), max(-.004, height(t, a)-.012)))
        direction = Vector((math.cos(a+rng.uniform(-.8, .8)), math.sin(a+rng.uniform(-.8, .8)), 0)).normalized()
        length = rng.uniform(.22, .50)*min(1, radius/.5)
        points = [root]
        for j in range(8):
            u = (j+.5)/8
            angle = .3+2.5*u**1.7
            points.append(points[-1]+(direction*math.sin(angle)+UP*math.cos(angle))*(length/8))
        blade(points, rng.uniform(.006, .014), UP.cross(direction), 2 if i%5 == 0 else 1, rng.uniform(-.4, .4))
    for i in range(240 if radius > .8 else 90 if radius > .3 else 32):
        a = rng.uniform(0, math.tau)
        t = rng.uniform(.10, 1.15)
        p = point(a*64/math.tau, t*10)+UP*.004
        direction = Vector((math.cos(a+1), math.sin(a+1), 0))
        length = rng.uniform(.045, .12)*min(1, radius/.25)
        points = [p+direction*(length*u)+UP*(.006*math.sin(math.pi*u)) for u in (0, .2, .4, .6, .8, 1)]
        blade(points, length*.24, UP.cross(direction), 2, rng.uniform(.5, 1.5))
    for i in range(9 if wet else 12):
        a, t = rng.uniform(0, math.tau), rng.uniform(.45, 1.03)
        centre = point(a*64/math.tau, t*10)
        size = rng.uniform(.008, .023)*min(1.5, radius/.3)
        centre.z = max(-.018, centre.z)-size*.45
        scale = Vector((size, size*rng.uniform(.65, 1.2), size*.55))
        rings = [[centre+Vector((math.cos(a)*math.sin(v)*scale.x, math.sin(a)*math.sin(v)*scale.y, math.cos(v)*scale.z))
                  for a in [math.tau*j/10 for j in range(10)]] for v in (math.pi/4, math.pi/2, math.pi*3/4)]
        for j in range(10):
            face([centre+UP*scale.z, rings[0][j], rings[0][(j+1)%10]], 3)
            for k in range(2):
                face([rings[k][j], rings[k+1][j], rings[k+1][(j+1)%10], rings[k][(j+1)%10]], 3)
            face([centre-UP*scale.z, rings[-1][(j+1)%10], rings[-1][j]], 3)
    def twig(points, width, material):
        rings = []
        for i, p in enumerate(points):
            tangent = (points[min(i+1, len(points)-1)]-points[max(0, i-1)]).normalized()
            side = tangent.cross(Vector((0, 1, .2))).normalized()
            normal = tangent.cross(side)
            rings.append([p+width*(1-.65*i/(len(points)-1))*(side*math.cos(j*math.tau/6)+normal*math.sin(j*math.tau/6)) for j in range(6)])
        face(list(reversed(rings[0])), material)
        for r, s in zip(rings, rings[1:]):
            for j in range(6):
                face([r[j], r[(j+1)%6], s[(j+1)%6], s[j]], material)
        face(rings[-1], material)
    for i in range(22 if radius > .8 else 12):
        a, t = rng.uniform(0, math.tau), rng.uniform(.12, 1.1)
        p = point(a*64/math.tau, t*10)+UP*.003
        direction = Vector((math.cos(a+1), math.sin(a+1), 0))
        length = rng.uniform(.04, .18)*min(1.5, radius/.25)
        twig([p+direction*(length*u)+UP*(.004*math.sin(math.pi*u)) for u in (0, .3, .7, 1)], .0025, 2)
    if radius < .3:
        for i in range(7):
            a = i*2.39996
            radial = Vector((math.cos(a), math.sin(a), 0))
            p = radial*.025
            twig([p, p+radial*.012+UP*.022, p+radial*.030+UP*rng.uniform(.025, .045)], .003, 2)
        for i in range(3):
            a = i*2.39996+.6
            radial = Vector((math.cos(a), math.sin(a), 0))
            p = radial*.04
            points = [p+UP*(.055*j/8) for j in range(9)]
            for j in range(1, 22):
                t = j/21
                r = .014*(1-t*.75)
                points.append(p+radial*(.014-r*math.cos(t*math.tau*1.15))+UP*(.055+r*math.sin(t*math.tau*1.15)))
            twig(points, .0025, 1)
    palette = vrmat.load_palette()
    mats = []
    for library, first, second, mix, gain in [
        ("forest_soil", "soil", "bark", .2, 1.0),
        ("grass_ground", "grass_green", "grass_dry", .55, 2.1),
        ("grass_ground", "grass_dry", "bark", .18, 1.9),
        ("river_stones", "shore_wet", "soil", .35, 1.0),
        ("forest_soil", "soil", "bark", .4, .65),
    ]:
        mat = vrmat.get(library).copy()
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        for socket in ("Base Color", "Normal", "Roughness"):
            for link in list(bsdf.inputs[socket].links):
                mat.node_tree.links.remove(link)
        bsdf.inputs["Base Color"].default_value = (*(gain*(x*(1-mix)+y*mix) for x, y in zip(
            palette[first]["linear_rgb"], palette[second]["linear_rgb"])), 1)
        bsdf.inputs["Specular IOR Level"].default_value = .16
        bsdf.inputs["Roughness"].default_value = .72 if wet and gain < .8 else .94
        mats.append(mat)
    mesh = Mesh()
    mesh.vertices, mesh.faces, mesh.indices = vertices, faces, indices
    mesh.object("Bodensaum_Gras_und_Streu", mats)


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    for i in range(FROND_SLOTS):
        if i in (0, 7):
            continue
        angle = i*2.39996+rng.uniform(-.18, .18)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        side = UP.cross(radial)
        base = radial*rng.uniform(.012, .033)+UP*rng.uniform(-.006, -.002)
        if i % 3 == 0:
            length, start_angle, end_angle, power = rng.uniform(.74, .81), rng.uniform(.9, 1.03), 2.12, 1.6
        elif i % 3 == 1:
            length, start_angle, end_angle, power = rng.uniform(.86, .9), rng.uniform(.525, .58), 1.75, 2.2
        else:
            length, start_angle, end_angle, power = rng.uniform(.78, .86), rng.uniform(.7, .85), 1.95, 1.9
        frond_length = length
        def rachis(t):
            point = base.copy()
            for k in range(32):
                u = t*(k+.5)/32
                angle = start_angle+(end_angle-start_angle)*u**power
                point += (radial*math.sin(angle)+UP*math.cos(angle))*(frond_length*t/32)
            return point
        stem_material = 4
        mesh.tube([rachis(j/24) for j in range(25)], .0037, stem_material, 6)
        for j in range(16):
            t = .08+j*.90/15
            u = (t-.08)/.92
            profile = max(.04, (u/.3)**.5 if u < .3 else ((1-u)/.7)**.85)
            for sign in (-1, 1):
                root = rachis(t+sign*.002)
                tangent = (rachis(t+.001)-rachis(t-.001)).normalized()
                normal = side.cross(tangent).normalized()
                if normal.z < 0:
                    normal.negate()
                roll = .08*math.sin(t*7+i)
                rolled_side = side*math.cos(roll)+normal*math.sin(roll)
                axis = (rolled_side*sign*.85+tangent*.5).normalized()
                normal = rolled_side.cross(tangent).normalized()
                lateral = normal.cross(axis).normalized()
                length = rng.uniform(.115, .135)*profile
                def pinna(v):
                    return root+axis*(length*v)-UP*(length*.15*v*v)
                mesh.tube([pinna(k/5) for k in range(6)], max(.00024, .0012*profile), stem_material, 4)
                material = 2 if t > .68 else 1 if t > .25 else 0
                for k in range(5):
                    v = .10+k*.16
                    for hand in (-1, 1):
                        attachment = pinna(v+hand*.025+rng.uniform(-.018, .018))
                        direction = lateral*hand*.85+axis*rng.uniform(.55, .75)+normal*rng.uniform(-.1, .1)
                        size = length*.38*math.sin(math.pi*v)**.45*rng.uniform(.88, 1.12)
                        pinnule(mesh, attachment, direction, normal, size,
                                size*rng.uniform(.155, .175), material)
                pinnule(mesh, pinna(.86), axis-UP*.15, normal, length*.15, length*.035, material)
        pinnule(mesh, rachis(.975), (rachis(1)-rachis(.97)).normalized(), UP,
                .018, .004, 2)
    for i in range(4):
        angle = rng.uniform(0, math.tau)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        base = radial*rng.uniform(.02, .045)-UP*.004
        height = rng.uniform(.12, .20)
        points = [base+UP*(height*j/12)+radial*(.018*(j/12)**2) for j in range(13)]
        centre = points[-1]+radial*.025
        for j in range(1, 33):
            t = j/32
            angle = math.pi+math.tau*1.3*t
            radius = .025*(1-.72*t)
            points.append(centre+radial*(radius*math.cos(angle))+UP*(radius*math.sin(angle)))
        mesh.tube(points, .0032, 1, 6)
        for j in (19, 24, 29):
            pinnule(mesh, points[j], radial+UP*.3, UP, .009, .003, 2)
    mesh.object("Doppelt_gefiederte_Wedel", materials())

    ground_contact(0.16, 0.035, SEED+921, wet=False)

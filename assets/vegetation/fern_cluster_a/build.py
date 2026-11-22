"""Doppelt gefiederte Farnrosette mit durchgehend gebogenen Wedeln."""
import math
import random

import bmesh
import bpy
from mathutils import Vector

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
FRONDS = 12


def materials():
    palette = vrmat.load_palette()
    result = []
    for name, library, first, second, blend, gain in [
        ("Olivbasis", "foliage_leaf", "grass_green", "grass_dry", .55, 1.8),
        ("Olivlaub", "foliage_leaf", "grass_green", "grass_dry", .55, 2.1),
        ("Lichtspitzen", "foliage_leaf", "grass_green", "grass_dry", .55, 2.8),
        ("Altfarn", "tree_bark", "bark", "soil", .3, 1.2),
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


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    for i in range(FRONDS):
        angle = i*2.39996+rng.uniform(-.18, .18)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        side = UP.cross(radial)
        base = radial*rng.uniform(.012, .033)+UP*rng.uniform(-.006, -.002)
        older = i in (0, 7)
        if older:
            length, start_angle, end_angle, power = rng.uniform(.64, .71), .9, 2.7, 2.4
        elif i % 3 == 0:
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
            if older:
                point += side*(.035*math.sin(math.pi*t*t))
            return point
        stem_material = 3 if older else 4
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
                roll = 1.3*t*t if older else .08*math.sin(t*7+i)
                rolled_side = side*math.cos(roll)+normal*math.sin(roll)
                axis = (rolled_side*sign*.85+tangent*.5).normalized()
                normal = rolled_side.cross(tangent).normalized()
                lateral = normal.cross(axis).normalized()
                length = rng.uniform(.115, .135)*profile*(.75 if older else 1)
                def pinna(v):
                    return root+axis*(length*v)-UP*(length*.15*v*v)
                mesh.tube([pinna(k/5) for k in range(6)], max(.00024, .0012*profile), stem_material, 4)
                material = 3 if older else (2 if t > .68 else 1 if t > .25 else 0)
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
                .018, .004, 3 if older else 2)
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
    for _ in range(11):
        angle = rng.uniform(0, math.tau)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        base = radial*rng.uniform(.006, .025)-UP*.006
        mesh.tube([base, base+radial*.008+UP*rng.uniform(.018, .04)], .003, 3, 5)
    mesh.object("Doppelt_gefiederte_Wedel", materials())

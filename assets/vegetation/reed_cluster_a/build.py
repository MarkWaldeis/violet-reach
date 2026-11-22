"""Schilfhorst mit gefächerten Halmen, überhängenden Blättern und braunen Samenständen."""
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
        return vrlib.link_to_source(obj)


def materials():
    palette = vrmat.load_palette()
    result = []
    for name, library, first, second, blend, gain in [
        ("Basis", "foliage_leaf", "leaf_green", "moss", .35, 1.1),
        ("Gruen", "foliage_leaf", "grass_green", "moss", .25, 1.35),
        ("Spitzen", "foliage_leaf", "grass_green", "moss", .20, 1.9),
        ("Stroh", "grass_ground", "grass_dry", "accent_ochre", .23, 1.1),
        ("Samen", "tree_bark", "bark", "accent_ochre", .22, 1.0),
    ]:
        material = vrmat.get(library).copy()
        material.name = name
        socket = material.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
        for link in list(socket.links):
            material.node_tree.links.remove(link)
        socket.default_value = (*(gain*(a*(1-blend)+b*blend) for a, b in zip(
            palette[first]["linear_rgb"], palette[second]["linear_rgb"])), 1)
        result.append(material)
    return result


def blade(mesh, points, width, side, dry=False, twist=0, straw_tip=False):
    for i in range(len(points)-1):
        t0, t1 = i/(len(points)-1), (i+1)/(len(points)-1)
        rows = []
        for point, t in ((points[i], t0), (points[i+1], t1)):
            axis = (side*math.cos(twist*t)+UP*math.sin(twist*t)).normalized()
            w = width*(1-t)**.8*min(1, .18+t*6)
            rows.append([point-axis*w, point+UP*w*.22, point+axis*w])
        material = 3 if dry or (straw_tip and t0 >= .8) else min(2, int((t0+t1)*1.5))
        for j in range(2):
            face_points = [rows[0][j], rows[1][j], rows[0][j+1]] if t1 == 1 else [
                rows[0][j], rows[1][j], rows[1][j+1], rows[0][j+1]]
            mesh.face(face_points, material)

SEED = 61139
STEMS = 31


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    plumes = {2, 7, 13, 20, 27}
    for i in range(STEMS):
        angle = rng.uniform(0, math.tau)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        side = UP.cross(radial)
        centre = Vector((-.055, .025, 0)) if i%3 else Vector((.08, -.04, 0))
        base = centre+Vector((rng.gauss(0, .055), rng.gauss(0, .04), -.025))
        height = rng.uniform(1.08, 1.77)
        lean = height*math.tan(rng.uniform(0, math.radians(15)))
        broken = i%11 == 0
        def stem(t):
            z = height*t
            if broken and t > .68:
                z -= height*(t-.68)*1.5
            return base+radial*(lean*t*t+(.25*max(0,t-.68) if broken else 0))+UP*z
        mesh.tube([stem(j/8) for j in range(9)], rng.uniform(.005,.009), 3 if i%6 == 0 else 1, 6)
        for j in range(5):
            t0 = .06+j*.135+rng.uniform(-.025,.025)
            root = stem(t0)
            leaf_angle = angle+j*2.39996+rng.uniform(-.35, .35)
            outward = Vector((math.cos(leaf_angle), math.sin(leaf_angle), 0))
            length = rng.uniform(.40,.75)*(1-.25*t0)
            points = [root+outward*(length*t**1.25)+UP*(length*(1.3*t-1.45*t*t)) for t in [k/7 for k in range(8)]]
            blade(mesh, points, rng.uniform(.014,.025), UP.cross(outward), i%9 == 0, .25, i%3 == 0)
        if i in plumes and not broken:
            top = stem(1)
            mesh.tube([top-UP*.015, top+UP*.22], .0035, 4, 6)
            for j in range(24):
                a = j*2.39996
                t = j/24
                root = top+UP*(.01+.19*t)
                direction = Vector((math.cos(a), math.sin(a), .6))
                length = .065*math.sin(math.pi*(t*.85+.08))
                tip = root+direction*length+UP*.015
                mesh.tube([root, root+direction*length*.55, tip], .0018, 4, 5)
                rings = []
                for z in (-.707, 0, .707):
                    rings.append([tip+Vector((.007*math.sqrt(1-z*z)*math.cos(k*math.tau/6),
                                              .007*math.sqrt(1-z*z)*math.sin(k*math.tau/6),
                                              .018*z)) for k in range(6)])
                for ring in range(2):
                    for k in range(6):
                        mesh.face([rings[ring][k], rings[ring][(k+1)%6],
                                   rings[ring+1][(k+1)%6], rings[ring+1][k]], 4)
                for k in range(6):
                    mesh.face([tip-UP*.018, rings[0][(k+1)%6], rings[0][k]], 4)
                    mesh.face([tip+UP*.018, rings[2][k], rings[2][(k+1)%6]], 4)
    mesh.object("Schilfhalme_Blaetter_Samen", materials())

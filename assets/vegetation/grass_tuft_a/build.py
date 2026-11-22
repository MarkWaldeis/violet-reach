"""Sparsames Grasbüschel aus 96 geknickten, gefalteten und gedrehten Blattspreiten."""
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


def materials():
    palette = vrmat.load_palette()
    result = []
    for name, library, first, second, blend, gain in [
        ("Basis", "foliage_leaf", "leaf_green", "moss", .35, 1.1),
        ("Gruen", "foliage_leaf", "grass_green", "moss", .25, 1.35),
        ("Spitzen", "foliage_leaf", "grass_green", "moss", .20, 1.9),
        ("Stroh", "grass_ground", "grass_dry", "accent_ochre", .23, 1.1),
        ("Samen", "tree_bark", "bark", "soil", .22, 1.0),
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


def blade(mesh, points, width, side, dry=False, twist=0):
    for i in range(len(points)-1):
        t0, t1 = i/(len(points)-1), (i+1)/(len(points)-1)
        rows = []
        for point, t in ((points[i], t0), (points[i+1], t1)):
            axis = (side*math.cos(twist*t)+UP*math.sin(twist*t)).normalized()
            w = width*(1-t)**.8*(.35+.65*min(1, t*4))
            rows.append([point-axis*w, point+UP*w*.22, point+axis*w])
        material = 3 if dry else 1
        for j in range(2):
            face_points = [rows[0][j], rows[1][j], rows[0][j+1]] if t1 == 1 else [
                rows[0][j], rows[1][j], rows[1][j+1], rows[0][j+1]]
            mesh.face(face_points, material)

SEED = 39017
BLADES = 96


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    dry_blades = set(rng.sample(range(BLADES), 18))
    for i in range(BLADES):
        angle = i*2.39996+rng.uniform(-.3, .3)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        side = UP.cross(radial)
        base = radial*(.065*math.sqrt(rng.random()))-UP*rng.uniform(.006, .018)
        length = rng.uniform(.45, .78)
        bent = i%9 == 0
        if bent:
            length *= .72
        lean = rng.uniform(.16, .24)
        curve = rng.uniform(.06, .10) if not bent else .24
        points = []
        for j in range(8):
            t = j/7
            z = length*(t-(.18 if not bent else .62)*t**3)
            points.append(base+radial*(length*(lean*t+curve*t*t))+side*(.012*math.sin(t*math.pi))+UP*z)
        blade(mesh, points, rng.uniform(.006, .012), side, i in dry_blades, rng.uniform(-.6,.6))
    mesh.object("Grashalme", materials())

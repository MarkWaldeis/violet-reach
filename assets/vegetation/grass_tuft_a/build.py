"""Dichter Wiesenhorst mit schmalen gefalteten, individuell gebogenen Halmen."""
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



SEED = 91823
BLADES = 156

def materials():
    palette = vrmat.load_palette()
    result = []
    for name, library, first, second, blend, gain in [
        ("Olivbasis", "foliage_leaf", "grass_green", "grass_dry", .55, 1.8),
        ("Olivlaub", "foliage_leaf", "grass_green", "grass_dry", .55, 2.1),
        ("Lichtspitzen", "foliage_leaf", "grass_green", "grass_dry", .55, 2.8),
        ("Trockenes_Gras", "grass_ground", "grass_dry", "bark", .12, 1.7),
        ("Alte_Blattbasen", "tree_bark", "bark", "grass_dry", .25, 1.5),
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
        for node in material.node_tree.nodes:
            if node.type == "BUMP":
                node.inputs["Distance"].default_value = .00025
        result.append(material)
    result.append(vrmat.get("forest_soil").copy())
    return result


def leaf(mesh, points, width, side, material, dry_tip=False, twist=0):
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
        index = 3 if dry_tip and i/count >= .72 else material
        for j in range(2):
            if i == count-1:
                mesh.face([rows[i][j], rows[i+1][j], rows[i][j+1]], index)
            else:
                mesh.face([rows[i][j], rows[i+1][j], rows[i+1][j+1], rows[i][j+1]], index)


def collar(mesh, radius, material, phase):
    n = 40
    def point(j, t, bottom=False):
        a = math.tau*j/n
        r = radius*t*(1+.14*math.sin(3*a+phase)+.09*math.cos(7*a-phase))
        z = -.03 if bottom else .014*(1-t)**1.1-.018*t**3
        return Vector((math.cos(a)*r, math.sin(a)*r, z))
    centre = Vector((0, 0, .014))
    for j in range(n):
        mesh.face([centre, point(j, .25), point(j+1, .25)], material)
        for k in range(1, 4):
            mesh.face([point(j, k/4), point(j, (k+1)/4),
                       point(j+1, (k+1)/4), point(j+1, k/4)], material)
        mesh.face([point(j, 1), point(j, 1, True), point(j+1, 1, True), point(j+1, 1)], material)
        mesh.face([Vector((0, 0, -.03)), point(j+1, 1, True), point(j, 1, True)], material)


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    bases = [Vector((.045*math.cos(i*2.4), .045*math.sin(i*2.4), .006)) for i in range(7)]
    for i in range(BLADES):
        root = bases[i%len(bases)]+Vector((rng.uniform(-.032, .032), rng.uniform(-.032, .032), 0))
        angle = rng.uniform(0, math.tau)
        outward = Vector((math.cos(angle), math.sin(angle), 0))
        side = UP.cross(outward)
        length = rng.uniform(.48, .65) if i % 6 == 0 else rng.uniform(.15, .38)
        tilt = rng.uniform(.08, .4)
        bend = rng.uniform(.65, 2.6)
        exponent = rng.uniform(1.2, 1.8)
        if length > .45:
            tilt = min(tilt, .18)
            bend = min(bend, (.22/length-tilt)*(exponent+1))
        if i < 12:
            length, tilt, bend, exponent = rng.uniform(.22, .36), .28, 3.4, 1.1
        points = [root]
        for j in range(10):
            start, end = (j/10)**.7, ((j+1)/10)**.7
            t = (start+end)*.5
            a = tilt+bend*t**exponent
            p = points[-1]+(outward*math.sin(a)+UP*math.cos(a))*(length*(end-start))
            p.z = max(.005, p.z)
            points.append(p)
        dry = i % 10 == 0
        dry_tip = i % 10 == 5
        sunlit = outward.x+outward.y > .85 and length > .35
        material = 3 if dry else 2 if sunlit else 1
        leaf(mesh, points, rng.uniform(.0038, .0095), side, material,
             dry_tip, rng.uniform(-.5, .5))
    for i in range(14):
        root = bases[i%len(bases)]+Vector((rng.uniform(-.025, .025), rng.uniform(-.025, .025), -.003))
        direction = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 1)).normalized()
        mesh.tube([root+direction*(j*.012) for j in range(4)], rng.uniform(.0012, .002), 4, 5)
    for i in range(12):
        angle = rng.uniform(0, math.tau)
        outward = Vector((math.cos(angle), math.sin(angle), 0))
        root = outward*rng.uniform(.03, .07)+UP*.006
        points = [root+outward*(t*.10)+UP*(.012*math.sin(math.pi*t))
                  for t in (0, .2, .4, .6, .8, 1)]
        leaf(mesh, points, rng.uniform(.003, .005), UP.cross(outward), 3, twist=.3)
    collar(mesh, .10, 5, rng.uniform(0, math.tau))
    mesh.object("Gefaltete_Wiesenhalme_und_Bodenkragen", materials())

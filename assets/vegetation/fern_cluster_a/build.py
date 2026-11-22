"""Farnhorst mit zwölf gebogenen Wedeln und einzeln gelappten Fiederblättchen."""
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
            w = width*(1-t)**.8
            rows.append([point-axis*w, point+UP*w*.22, point+axis*w])
        material = 3 if dry else min(2, int((t0+t1)*1.5))
        for j in range(2):
            face_points = [rows[0][j], rows[1][j], rows[0][j+1]] if t1 == 1 else [
                rows[0][j], rows[1][j], rows[1][j+1], rows[0][j+1]]
            mesh.face(face_points, material)

SEED = 82719
FRONDS = 15


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    for i in range(FRONDS):
        angle = i*2.39996+rng.uniform(-.2, .2)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        side = UP.cross(radial)
        base = radial*rng.uniform(.015, .045)+UP*.025
        older = i in (3, 11)
        outer = i % 3 == 0 or older
        spread = rng.uniform(.53, .66) if outer else rng.uniform(.27, .44)
        height = rng.uniform(.19, .30) if outer else rng.uniform(.54, .76)
        if not outer and i % 3 == 1:
            spread, height = rng.uniform(.43, .53), rng.uniform(.43, .56)
        def rachis(t):
            return base+radial*(spread*t**.9)+UP*(height*math.sin(math.pi*.72*t)-.07*t**5)
        mesh.tube([rachis(j*.995/24) for j in range(25)], .0045, 0)
        for j in range(26):
            t = .12+j*(.875/25)
            profile = ((t-.08)/.27)**.55 if t < .35 else ((1-t)/.65)**.5
            length = rng.uniform(.095, .12)*profile
            for sign in (-1, 1):
                root = rachis(t+sign*.007)
                tangent = (rachis(t+.001)-rachis(t-.001)).normalized()
                along = (side*sign*math.sqrt(3)+tangent).normalized()
                across = (tangent-along*tangent.dot(along)).normalized()
                outline = [(0, 0)]
                for k in range(1, 18):
                    x = k/18
                    width = .011*profile*math.sin(math.pi*x)**.7*(.88 if k%2 else 1)
                    outline.append((x, -width))
                outline.append((1, 0))
                for k in reversed(range(1, 18)):
                    x = k/18
                    width = .011*profile*math.sin(math.pi*x)**.7*(.88 if k%2 else 1)
                    outline.append((x, width))
                points = [root+along*(x*length)+across*y-UP*(length*.09*x*x) for x,y in outline]
                centre = root+along*length*.48+UP*length*(.025-.09*.48**2)
                material = 3 if older else min(2, int(t*3))
                for k in range(len(points)):
                    mesh.face([centre, points[k], points[(k+1)%len(points)]], material)
    for i in range(4):
        a = i*math.tau/4
        radial = Vector((math.cos(a), math.sin(a), 0))
        points = [radial*.035+UP*(.025+.16*j/10) for j in range(7)]
        points += [radial*(.035+.025*math.sin(j*math.pi/8))+UP*(.121+.025*math.cos(j*math.pi/8)) for j in range(9)]
        mesh.tube(points, .006, 0)
    for i in range(13):
        angle = rng.uniform(0, math.tau)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        base = Vector((rng.gauss(0, .018), rng.gauss(0, .018), .006))
        height = rng.uniform(.03, .065)
        mesh.tube([base, base+radial*.012+UP*height*.65,
                   base+radial*.025+UP*height], rng.uniform(.004, .008), 4, 6)
    mesh.vertices = [vertex-UP*.025 for vertex in mesh.vertices]
    mesh.object("Farnwedel_und_Fiederblaetter", materials())

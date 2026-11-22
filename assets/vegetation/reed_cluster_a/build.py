"""Ufer-Schilfhorst mit Knoten, Blattscheiden und verzweigten Federrispen."""
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

    def tube(self, points, radius, material, sides=5, end_scale=.25):
        start = len(self.vertices)
        for i, point in enumerate(points):
            direction = (points[min(i+1, len(points)-1)]-points[max(0, i-1)]).normalized()
            axis = direction.cross(Vector((0, 1, 0))).normalized()
            other = direction.cross(axis)
            r = radius*(1-(1-end_scale)*i/(len(points)-1))
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



SEED = 46931
CULMS = 27

def materials():
    palette = vrmat.load_palette()
    result = []
    for name, library, first, second, blend, gain in [
        ("Olivbasis", "foliage_leaf", "grass_green", "grass_dry", .55, 1.8),
        ("Olivlaub", "foliage_leaf", "grass_green", "grass_dry", .55, 2.1),
        ("Lichtspitzen", "foliage_leaf", "grass_green", "grass_dry", .55, 2.8),
        ("Trockenes_Gras", "grass_ground", "grass_dry", "bark", .12, 1.7),
        ("Alte_Blattbasen", "tree_bark", "bark", "grass_dry", .25, 1.5),
        ("Rispenschatten", "tree_bark", "bark", "grass_dry", .6, 2.2),
        ("Rispenlicht", "grass_ground", "grass_dry", "accent_ochre", .12, 1.7),
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
    soil = vrmat.get("forest_soil").copy()
    soil.name = "Feuchter_Uferschlamm"
    bsdf = soil.node_tree.nodes["Principled BSDF"]
    socket = bsdf.inputs["Base Color"]
    for link in list(socket.links):
        soil.node_tree.links.remove(link)
    socket.default_value = (*( .9*(a*.55+b*.45) for a, b in zip(
        palette["soil"]["linear_rgb"], palette["bark"]["linear_rgb"])), 1)
    roughness = bsdf.inputs["Roughness"]
    for link in list(roughness.links):
        soil.node_tree.links.remove(link)
    roughness.default_value = .3
    for link in list(bsdf.inputs["Normal"].links):
        soil.node_tree.links.remove(link)
    bsdf.inputs["Specular IOR Level"].default_value = .4
    result.insert(5, soil)
    return result


def leaf(mesh, points, width, side, material, dry_tip=False, twist=0, root_scale=.35):
    rows = []
    count = len(points)-1
    for i, point in enumerate(points):
        t = i/count
        tangent = (points[min(i+1, count)]-points[max(0, i-1)]).normalized()
        across = (side-tangent*side.dot(tangent)).normalized()
        normal = across.cross(tangent).normalized()
        across = across*math.cos(twist*t)+normal*math.sin(twist*t)
        normal = across.cross(tangent).normalized()
        w = width*(root_scale+(1-root_scale)*min(1, t/.15))*(1-t)**.75
        rows.append([point-across*w*.5, point+normal*w*.24, point+across*w*.5])
    for i in range(count):
        index = 3 if dry_tip and i/count >= .72 else material
        for j in range(2):
            if i == count-1:
                mesh.face([rows[i][j], rows[i+1][j], rows[i][j+1]], index)
            else:
                mesh.face([rows[i][j], rows[i+1][j], rows[i+1][j+1], rows[i][j+1]], index)


def collar(mesh, radius, material, phase):
    n = 64
    def point(j, t, bottom=False):
        a = math.tau*j/n
        r = radius*t*(1+.22*math.sin(3*a+phase)+.12*math.cos(5*a-phase)+.06*math.sin(8*a+1.2))
        z = -.04 if bottom else .016*(1-t)**1.5+.004*math.sin(2*a+.4)*(1-t)*math.sin(math.pi*t)-.022*t**3
        return Vector((math.cos(a)*r+.025*t*t, math.sin(a)*r-.015*t*t, z))
    centre = Vector((0, 0, .016))
    for j in range(n):
        mesh.face([centre, point(j, .2), point(j+1, .2)], material)
        for k in range(1, 5):
            mesh.face([point(j, k/5), point(j, (k+1)/5),
                       point(j+1, (k+1)/5), point(j+1, k/5)], material)
        mesh.face([point(j, 1), point(j, 1, True), point(j+1, 1, True), point(j+1, 1)], material)
        mesh.face([Vector((.025, -.015, -.04)), point(j+1, 1, True), point(j, 1, True)], material)



def panicle(mesh, base, wind, length, rng):
    across_wind = UP.cross(wind)
    def axis(t):
        return base+UP*(length*(t-.45*t**3))+wind*(length*.65*t*t)
    mesh.tube([axis(j/16) for j in range(17)], .0015, 6, 6, .16)
    for j in range(22):
        t = .07+j*.88/21
        angle = j*2.39996+rng.uniform(-.45, .45)
        radial = wind*math.cos(angle)+across_wind*math.sin(angle)
        root = axis(t)
        extent = length*rng.uniform(.22, .29)*math.sin(math.pi*t)**.7
        def branch(v):
            return root+radial*(extent*v)+UP*(length*(.15*v-.12*v*v))+wind*(.018*v*v)
        material = 7 if t > .82 else 6
        positions = [.24+k*.2+rng.uniform(-.035, .035) for k in range(4)]
        samples = sorted(set([k/8 for k in range(9)]+positions))
        mesh.tube([branch(v) for v in samples], rng.uniform(.00045, .0007),
                  material, 4, .12)
        for v in positions:
            origin = branch(v)
            direction = (radial*.65+UP*.6+across_wind*rng.uniform(-.65, .65)).normalized()
            twig_length = rng.uniform(.018, .033)*(1-.35*t)
            tip = origin+direction*twig_length-wind*.003
            def twig(u):
                return origin.lerp(tip, u)+UP*(.008*u*(1-u))
            attachments = [.2+q*.22 for q in range(4)]
            mesh.tube([twig(u) for u in sorted(set([0, .5, 1]+attachments))],
                      .00025, material, 3, .15)
            for u in attachments:
                p = twig(u)
                side = UP.cross(direction).normalized()
                hand = -1 if u < .5 else 1
                along = (direction+side*(hand*rng.uniform(.2, .5))).normalized()
                size = rng.uniform(.012, .020)
                points = [p, p+along*size*.5+UP*.0005, p+along*size]
                width = rng.uniform(.0025, .0035)
                leaf(mesh, points, width, side, material, root_scale=.025)
                end = points[-1]
                awn = along*rng.uniform(.008, .016)+wind*.002
                mesh.face([end, end+awn+side*.000065, end+awn-side*.000065], material)
                tangent = (points[-1]-points[0]).normalized()
                across = (side-tangent*side.dot(tangent)).normalized()
                normal = across.cross(tangent).normalized()
                root_hair = points[1]+normal*(width*.5**.75*.24)
                for fan in (-1, -.5, 0, .5, 1):
                    hair = along*rng.uniform(.018, .033)+side*(fan*.012)+wind*.004
                    mesh.face([root_hair, root_hair+hair+side*.00035,
                               root_hair+hair-side*.00035], material)


def build():
    rng = random.Random(SEED)
    mesh = Mesh()
    wind = Vector((.8, .6, 0))
    for i in range(CULMS):
        root = Vector((max(-.15, min(.15, rng.gauss(0, .067))),
                       max(-.13, min(.13, rng.gauss(0, .055))), -.012))
        angle = rng.uniform(0, math.tau)
        outward = Vector((math.cos(angle), math.sin(angle), 0))
        headed = i % 7 in (0, 2, 4)
        height = rng.uniform(1.20, 1.66) if headed else rng.uniform(.95, 1.62)
        bent, broken = i == 5, i == 19
        if bent or broken:
            height = rng.uniform(.85, 1.2)
        lean = math.tan(rng.uniform(math.radians(5), math.radians(18.5)))*height
        radius = rng.uniform(.0035, .0075)
        def culm(t):
            point = root+UP*(height*t)+outward*(lean*t**1.25)+wind*(.015*t*t)
            if bent or broken:
                point += (outward-UP)*(.24*height*t**4)
            return point
        end = .78 if broken else 1
        mesh.tube([culm(end*j/16) for j in range(17)], radius, 0, 8, .55)
        plane = angle+rng.uniform(-.5, .5)
        for j in range(6):
            t = .14+j*.135+rng.uniform(-.014, .014)
            if t+.075 > end:
                continue
            node_radius = radius*(1-.45*t)
            mesh.tube([culm(t-.004), culm(t+.004)], node_radius*1.35, 0, 8, 1)
            mesh.tube([culm(t), culm(t+.035), culm(t+.075)], node_radius*1.2, 1, 7, .65)
            a = plane+j*math.pi+rng.uniform(-.25, .25)
            direction = Vector((math.cos(a), math.sin(a), 0))
            origin = culm(t)+direction*node_radius*.85
            length = rng.uniform(.32, .60)*(1-.28*j/5)
            points = [origin]
            for k in range(10):
                u = (k+.5)/10
                tilt = .3+2.8*u**1.4
                p = points[-1]+(direction*math.sin(tilt)+UP*math.cos(tilt))*(length/10)
                p.z = max(.006, p.z)
                points.append(p)
            material = 2 if direction.x+direction.y > .8 else 1
            leaf(mesh, points, rng.uniform(.018, .033), UP.cross(direction), material,
                 dry_tip=(i+j) % 7 == 0, twist=rng.uniform(-.35, .35), root_scale=.05)
        if headed:
            panicle(mesh, culm(1), wind, rng.uniform(.27, .32), rng)
        elif not broken:
            points = [culm(.86+.22*u)+outward*(.012*u*u)
                      for u in (0, .2, .4, .6, .8, 1)]
            leaf(mesh, points, rng.uniform(.017, .021), UP.cross(outward), 1, twist=.2, root_scale=.05)
        else:
            tip = culm(end)
            for hand in (-1, 1):
                mesh.tube([tip, tip+outward*(hand*.004)+UP*.014], radius*.24, 3, 4, .3)
    for i in range(9):
        angle = rng.uniform(0, math.tau)
        outward = Vector((math.cos(angle), math.sin(angle), 0))
        root = outward*rng.uniform(.03, .12)
        height = rng.uniform(.06, .25)
        reach = rng.uniform(.06, .18)
        mesh.tube([root+outward*(reach*t)+UP*(height*t*(1-.45*t))
                   for t in (0, .25, .5, .75, 1)], rng.uniform(.0025, .004), 4, 6, .7)
    collar(mesh, .23, 5, rng.uniform(0, math.tau))
    mesh.object("Schilfhalme_Blattscheiden_und_Federrispen", materials())

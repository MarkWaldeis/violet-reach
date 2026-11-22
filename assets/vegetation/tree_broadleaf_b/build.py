"""Verzweigter Laubbaum; Meter, Z oben, opake Blattspreiten an Endzweigen."""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise

import vrlib
import vrmat

SEED = 23871
TARGETS = 1150
SCAFFOLDS = 2
YOUNG = False
BOLE = [(0, 0, -.04), (.17, 0, .9), (.36, 0, 1.9), (.53, 0, 2.75)]
BASE_RADIUS, FORK_RADIUS = .31, .23
LEAN, ROOT_RIDGES = .53/2.75, 6
ROOT_RINGS = [(-.055, .35, .35), (.06, .32, .31), (.25, .30, .20), (.55, .29, .10), (.95, .28, .01)]
ENVELOPE = [
    ((1.6, -.5, 5.5), (2.1, 2.7, 2.4)),
    ((2.5, .5, 7.3), (2.7, 3.1, 2.8)),
    ((2.3, .2, 9.1), (2.0, 2.4, 1.9)),
    ((-.2, .4, 6.4), (1.5, 2.4, 1.9)),
    ((3.4, -1.1, 8.2), (1.7, 1.9, 1.9)),
]
GAPS = [((-.7, -1.8, 8.0), 1.2), ((4.8, 1.8, 6.4), 1.1)]
CROWN_CENTRE = (2.1, 0)
TWIG_RADIUS, REMESH_THRESHOLD, VOXEL_SIZE = .0055, .035, .025
LEAVES_PER_TWIG, LEAF_LENGTH = (22, 32), (.18, .29)
EXPOSURE_DISTANCE, BARK_RELIEF = 1.1, .020

UP = Vector((0, 0, 1))


def mesh_object(name, vertices, faces, materials, indices=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
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
    for polygon in data.polygons:
        polygon.use_smooth = name != "Einzelblaetter"
        if indices is not None:
            polygon.material_index = indices[polygon.index]
    return vrlib.link_to_source(obj)


def bezier(points, t):
    u = 1-t
    return u**3*points[0]+3*u*u*t*points[1]+3*u*t*t*points[2]+t**3*points[3]


def tangent(points, t):
    u = 1-t
    return (3*u*u*(points[1]-points[0])+6*u*t*(points[2]-points[1])+3*t*t*(points[3]-points[2])).normalized()


class Tubes:
    def __init__(self):
        self.vertices, self.faces = [], []

    def add(self, points, r0, r1, sides=7, steps=7):
        offset = len(self.vertices)
        axis = tangent(points, 0).orthogonal().normalized()
        for i in range(steps+1):
            t = i/steps
            centre = bezier(points, t)
            direction = tangent(points, t)
            axis = axis-direction*axis.dot(direction)
            axis = axis.normalized() if axis.length > .001 else direction.orthogonal().normalized()
            other = direction.cross(axis).normalized()
            radius = r0*(1-t)+r1*t
            for j in range(sides):
                a = math.tau*j/sides
                self.vertices.append(centre+radius*(axis*math.cos(a)+other*math.sin(a)))
            if i:
                for j in range(sides):
                    a, b = offset+(i-1)*sides+j, offset+(i-1)*sides+(j+1)%sides
                    self.faces.append((a, b, b+sides, a+sides))
        self.faces.extend([tuple(offset+j for j in reversed(range(sides))),
                           tuple(offset+steps*sides+j for j in range(sides))])

    def object(self, name, material):
        if self.faces:
            return mesh_object(name, self.vertices, self.faces, [material])


def foliage_materials():
    """Copy foliage_leaf; palette-only colour mixes, opaque library BSDF unchanged."""
    palette = vrmat.load_palette()
    materials = []
    for name, colour, strength, gain in [("Schatten", "leaf_green", .55, 1.0),
                                    ("Innenlaub", "grass_green", .50, 1.0),
                                    ("Sonnenlaub", "grass_green", 1.0, 2.2),
                                    ("Oliveflecken", "grass_green", 1.0, 2.5)]:
        material = vrmat.get("foliage_leaf").copy()
        material.name = "broadleaf_"+name
        nt = material.node_tree
        socket = nt.nodes["Principled BSDF"].inputs["Base Color"]
        original = socket.links[0].from_socket
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.inputs[0].default_value = strength
        green = palette[colour]["linear_rgb"]
        moss = palette["moss"]["linear_rgb"]
        tint = tuple((a*.8+b*.2)*gain for a, b in zip(green, moss)) if gain > 1 else green
        mix.inputs[2].default_value = (*tint, 1)
        if gain > 1:
            texture = nt.nodes.new("ShaderNodeTexNoise")
            texture.inputs["Scale"].default_value = .45/EXPOSURE_DISTANCE
            texture.inputs["Detail"].default_value = 1
            coordinates = nt.nodes.new("ShaderNodeTexCoord")
            nt.links.new(coordinates.outputs["Object"], texture.inputs["Vector"])
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            for element, value in zip(ramp.color_ramp.elements, (.8, 1.08)):
                element.color = (*(c*value for c in tint), 1)
            nt.links.new(texture.outputs["Fac"], ramp.inputs[0])
            nt.links.new(ramp.outputs["Color"], mix.inputs[2])
        nt.links.new(original, mix.inputs[1])
        nt.links.new(mix.outputs[0], socket)
        materials.append(material)
    return materials


def envelope_score(point):
    return min(sum(((point[i]-centre[i])/size[i])**2 for i in range(3))
               for centre, size in ENVELOPE)


def canopy_top(point):
    top = point.z
    for centre, size in ENVELOPE:
        xy = ((point.x-centre[0])/size[0])**2+((point.y-centre[1])/size[1])**2
        if xy < 1:
            top = max(top, centre[2]+size[2]*math.sqrt(1-xy))
    return top


def attractors(rng):
    lower = [min(c[i]-s[i] for c, s in ENVELOPE) for i in range(3)]
    upper = [max(c[i]+s[i] for c, s in ENVELOPE) for i in range(3)]
    points = []
    for _ in range(TARGETS*100):
        p = Vector(tuple(rng.uniform(lower[i], upper[i]) for i in range(3)))
        boundary = 1+.13*noise.noise(p*.93+Vector((4, 8, 2)))
        if envelope_score(p) > boundary:
            continue
        if any((p-Vector(centre)).length < radius for centre, radius in GAPS):
            continue
        points.append(p)
        if len(points) == TARGETS:
            return points
    raise RuntimeError("Wachstumshuelle lieferte zu wenige Attraktoren")


def partition(points, count):
    if len(points) <= count:
        return [[p] for p in points]
    centres = [points[0]]
    for _ in range(count-1):
        centres.append(max(points, key=lambda p: min((p-c).length_squared for c in centres)))
    for _ in range(5):
        groups = [[] for _ in centres]
        for point in points:
            nearest = min(range(len(centres)), key=lambda i: (point-centres[i]).length_squared)
            groups[nearest].append(point)
        groups = [group for group in groups if group]
        centres = [sum(group, Vector())/len(group) for group in groups]
    return groups


class Branch:
    def __init__(self, points, start, incoming, depth, rng):
        terminal = len(points) == 1
        centre = sum(points, Vector())/len(points)
        fraction = 1.0 if terminal else [.38, .45, .58, .72, .86][min(depth, 4)]
        end = start.lerp(centre, fraction)
        direction = (end-start).normalized()
        if direction.length < .1:
            direction = incoming
        angle = math.acos(max(-1, min(1, direction.dot(incoming))))
        lateral = direction-incoming*direction.dot(incoming)
        if lateral.length < .01:
            lateral = incoming.cross(Vector((0, 1, 0)))
        lateral.normalize()
        angle = max(math.radians(30), min(math.radians(70), angle))
        departure = incoming*math.cos(angle)+lateral*math.sin(angle)
        length = max(.06, (end-start).length)
        lift = UP*length*(.16 if depth < 2 else .10)
        self.points = [start, start+departure*length*.36,
                       end-direction*length*.30+lift, end]
        self.children = []
        if not terminal:
            count = len(points) if depth >= 3 else min(5, len(points))
            for group in partition(points, count):
                self.children.append(Branch(group, end, tangent(self.points, 1), depth+1, rng))
            self.end_radius = math.sqrt(sum(child.radius**2 for child in self.children))
            self.radius = self.end_radius*1.035
        else:
            self.radius = TWIG_RADIUS
            self.end_radius = TWIG_RADIUS*.23
        self.depth = depth


def root_flare(bark):
    vertices, faces = [], []
    sides = 96
    for z, core, flare in ROOT_RINGS:
        for j in range(sides):
            a = math.tau*j/sides
            r = core+flare*max(0, math.cos(ROOT_RIDGES*a+.3))**4
            shift = Vector((LEAN*max(z, 0), 0, 0))
            vertices.append(Vector((r*math.cos(a), r*math.sin(a), z))+shift)
    for i in range(len(ROOT_RINGS)-1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.append((a, b, b+sides, a+sides))
    faces.extend([tuple(reversed(range(sides))),
                  tuple((len(ROOT_RINGS)-1)*sides+j for j in range(sides))])
    return mesh_object("Wurzelanlauf", vertices, faces, [bark])


def spray(branch, rng, vertices, faces, indices):
    centre = bezier(branch.points, .65)
    interior = canopy_top(centre)-centre.z > EXPOSURE_DISTANCE*1.8
    count = rng.randint(10, 16) if interior else rng.randint(*LEAVES_PER_TWIG)
    depth = canopy_top(centre)-centre.z
    sun_direction = Vector((-.35, -.5, .79))
    exposed = envelope_score(centre+sun_direction*EXPOSURE_DISTANCE) > .98
    patch = noise.noise(centre*(.35/EXPOSURE_DISTANCE)+Vector((3, 0, 7)))
    local = min(ENVELOPE, key=lambda e: sum(((centre[i]-e[0][i])/e[1][i])**2 for i in range(3)))
    local_height = (centre.z-local[0][2])/local[1][2]
    upper_outer = local_height > -.12 and envelope_score(centre) > .32
    bright = exposed or upper_outer or depth < EXPOSURE_DISTANCE*(1.4+patch*.3)
    material = (3 if patch > .12 else 2) if bright else (1 if depth < EXPOSURE_DISTANCE*2 else 0)
    for k in range(count):
        t = .22+.77*(k+.5)/count
        stem = bezier(branch.points, t)
        forward = tangent(branch.points, t)
        angle = k*2.39996+rng.uniform(-.3, .3)
        axis = forward.cross(UP)
        if axis.length < .05:
            axis = Vector((1, 0, 0))
        axis.normalize()
        side = forward.cross(axis).normalized()
        radial = axis*math.cos(angle)+side*math.sin(angle)
        outward = Vector((stem.x-CROWN_CENTRE[0], stem.y-CROWN_CENTRE[1], .4)).normalized()
        along = (forward*.45+radial*.85+outward*.25+UP*rng.uniform(.05, .4)).normalized()
        normal = (UP*.85+radial*.45+outward*.2).normalized()
        across = normal.cross(along).normalized()
        normal = along.cross(across).normalized()
        if normal.z < 0:
            normal.negate()
            across.negate()
        length = rng.uniform(*LEAF_LENGTH)
        petiole = stem+along*length*.14
        offset = len(vertices)
        width = length*rng.uniform(.28, .40)
        for x, y in [(0, 0), (.23, -.70), (.52, -1), (.81, -.65),
                     (1, 0), (.81, .65), (.52, 1), (.23, .70)]:
            cup = .07*length*y*y-.11*length*x*x
            vertices.append(petiole+along*length*x+across*width*y+normal*cup)
        vertices.append(petiole+along*length*.49+normal*length*.045)
        # Keep the geometry random stream stable across colour changes.
        rng.random()
        for j in range(8):
            faces.append((offset+j, offset+(j+1)%8, offset+8))
            indices.append(material)
        p = len(vertices)
        vertices.extend([stem, petiole-across*.002, petiole+across*.002])
        faces.append((p, p+1, p+2))
        indices.append(4)


def emit(branch, thick, thin, rng, leaves):
    sides = 12 if branch.radius >= .08 else (8 if branch.radius >= .035 else 5)
    steps = 10 if branch.radius >= .035 else 4
    batch = thick if branch.radius >= REMESH_THRESHOLD else thin
    batch.add(branch.points, branch.radius, branch.end_radius, sides, steps)
    if not branch.children:
        spray(branch, rng, *leaves)
    for child in branch.children:
        emit(child, thick, thin, rng, leaves)


def build():
    rng = random.Random(SEED)
    bark = vrmat.get("tree_bark").copy()
    bark.name = "broadleaf_bark_furrows"
    # World-aligned metre coordinates retain the library's longitudinal bark grain.
    for node in bark.node_tree.nodes:
        if node.type == "BUMP" and node.inputs["Distance"].default_value > .001:
            node.inputs["Distance"].default_value = BARK_RELIEF
            node.inputs["Strength"].default_value = .65
    materials = foliage_materials()+[bark]
    thick, thin = Tubes(), Tubes()
    thick.add([Vector(p) for p in BOLE], BASE_RADIUS, FORK_RADIUS, 28, 32)
    root_flare(bark)
    if not YOUNG:
        centre = Vector(BOLE[-1])-UP*.06
        vertices, faces = [], []
        sides, rings = 32, 16
        for i in range(rings+1):
            latitude = -.5*math.pi+math.pi*(i+.01)/(rings+.02)
            for j in range(sides):
                angle = math.tau*j/sides
                r = FORK_RADIUS*1.06*math.cos(latitude)
                vertices.append(centre+Vector((r*math.cos(angle), r*math.sin(angle), FORK_RADIUS*1.45*math.sin(latitude))))
        for i in range(rings):
            for j in range(sides):
                a, b = i*sides+j, i*sides+(j+1)%sides
                faces.append((a, b, b+sides, a+sides))
        faces.extend([tuple(reversed(range(sides))), tuple(rings*sides+j for j in range(sides))])
        mesh_object("Gabelkragen", vertices, faces, [bark])
    points = attractors(rng)
    roots = []
    if YOUNG:
        leader = [Vector((.02, 0, 1.95)), Vector((.18, -.06, 3.4)),
                  Vector((-.12, .1, 5.1)), Vector((.12, 0, 6.65))]
        thick.add(leader, .10, .012, 12, 32)
        for group in partition(points, 7):
            centre = sum(group, Vector())/len(group)
            t = max(.025, min(.80, (centre.z-2.65)/4.7))
            start = bezier(leader, t)
            roots.append(Branch(group, start, tangent(leader, t), 0, rng))
    else:
        groups = [[] for _ in range(SCAFFOLDS)]
        for point in points:
            if SCAFFOLDS == 2:
                index = 0 if point.x < 1.0 else 1
            else:
                angle = math.atan2(point.y, point.x)
                index = int(((angle+.35) % math.tau)/math.tau*SCAFFOLDS)
            groups[index].append(point)
        start = Vector(BOLE[-1])
        for group in groups:
            if group:
                roots.append(Branch(group, start, UP, 0, rng))
    vertices, faces, indices = [], [], []
    for branch in roots:
        emit(branch, thick, thin, rng, (vertices, faces, indices))
    thick.object("Stamm_und_Starkaeste", bark)
    wood = vrlib.source_objects()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in wood:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = wood[-1]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = "Holz_verschmolzen"
    remesh = obj.modifiers.new("Astkragen", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = VOXEL_SIZE
    remesh.use_smooth_shade = True
    bpy.ops.object.modifier_apply(modifier=remesh.name)
    smooth = obj.modifiers.new("Weiche_Astansaetze", "SMOOTH")
    smooth.factor, smooth.iterations = .8, 8
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    for vertex in obj.data.vertices:
        vertex.co.z = max(-.055, vertex.co.z)
    thin.object("Feinaeste_und_Zweige", bark)
    mesh_object("Einzelblaetter", vertices, faces, materials, indices)
    print("VR_BRANCHES", {"terminal_twigs": TARGETS, "leaves": len(indices)//9,
                          "pipe_model": "parent end radius squared = sum child start radii squared"}, flush=True)

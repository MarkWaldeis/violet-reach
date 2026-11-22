"""Verzweigter Laubbaum; Meter, Z oben, opake Blattspreiten an Endzweigen."""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise
from mathutils.kdtree import KDTree

import vrlib
import vrmat

SEED = 23871
TARGETS = 1250
BOLE = [(0, 0, -.04), (.13, -.01, .75), (.27, .01, 1.5), (.40, 0, 2.25)]
BASE_RADIUS = .48
CLUSTERS = [
    [((2.1, .625, 9.65), (1.3, 2.0625, 1.25)),
     ((2.9, 1.0, 7.8), (1.7, 2.125, 1.3)),
     ((2.5, -.625, 5.3), (1.8, 2.0, 1.1)),
     ((3.6, -.5, 6.8), (1.3, 1.625, .9))],
    [((-.8, -.25, 7.3), (1.35, 1.875, 1.0)),
     ((-1.3, -.875, 5.5), (1.35, 1.75, 1.0)),
     ((-.25, -1.5, 3.9), (1.45, 1.5625, .95))],
]
ENVELOPE = [ellipsoid for cluster in CLUSTERS for ellipsoid in cluster]
GAPS = [((1.1, -.2, 6.4), .75), ((.5, .5, 8.7), .7)]
CROWN_CENTRE = (1.4, 0)
TWIG_RADIUS, REMESH_THRESHOLD, VOXEL_SIZE = .0062, .035, .032
LEAVES_PER_TWIG, LEAF_LENGTH = (22, 30), (.14, .24)
EXPOSURE_DISTANCE, BARK_RELIEF = 1.0, .010

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
        self.frames = []

    def add(self, points, r0, r1, sides=7, steps=7, radius_at=None):
        offset = len(self.vertices)
        axis = tangent(points, 0).orthogonal().normalized()
        for i in range(steps+1):
            t = i/steps
            centre = bezier(points, t)
            direction = tangent(points, t)
            axis = axis-direction*axis.dot(direction)
            axis = axis.normalized() if axis.length > .001 else direction.orthogonal().normalized()
            other = direction.cross(axis).normalized()
            radius = radius_at(t, centre) if radius_at else r0*(1-t)+r1*t
            self.frames.append((centre, direction, axis.copy(), radius, max(6, round(math.tau*r0/.11))))
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
    """Copy foliage_leaf; warm grass-palette colour floor, reduced sky specular."""
    palette = vrmat.load_palette()
    materials = []
    for name, colour, strength, gain in [("Schatten", "grass_green", 1.0, 1.8),
                                    ("Innenlaub", "grass_green", 1.0, 2.1),
                                    ("Sonnenlaub", "grass_green", 1.0, 2.8),
                                    ("Oliveflecken", "grass_green", 1.0, 3.1)]:
        material = vrmat.get("foliage_leaf").copy()
        material.name = "broadleaf_"+name
        nt = material.node_tree
        socket = nt.nodes["Principled BSDF"].inputs["Base Color"]
        nt.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = .2
        original = socket.links[0].from_socket
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.inputs[0].default_value = strength
        green = palette[colour]["linear_rgb"]
        dry = palette["grass_dry"]["linear_rgb"]
        tint = tuple((a*.45+b*.55)*gain for a, b in zip(green, dry))
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


def ellipsoid_score(point, centre, size):
    x, y, z = ((point[i]-centre[i])/size[i] for i in range(3))
    return x*x+y*y+(z**4 if z < 0 else z*z)


def envelope_score(point):
    return min(ellipsoid_score(point, centre, size) for centre, size in ENVELOPE)


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
        if len(points) < TARGETS*.12:
            centre, size = rng.choice((CLUSTERS[0][2], CLUSTERS[1][2]))
            p = Vector(tuple(centre[i]+rng.uniform(-1, 1)*size[i] for i in range(3)))
        boundary = 1+.24*noise.noise(p*.93+Vector((4, 8, 2)))
        if envelope_score(p) > boundary:
            continue
        if len(points) % 11 == 0:
            centre, _ = min(ENVELOPE, key=lambda e: ellipsoid_score(p, *e))
            outward = Vector((p.x-centre[0], p.y-centre[1], 0))
            if outward.length > .01:
                p += outward.normalized()*rng.uniform(.2, .55)
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
        fraction = 1.0 if terminal else [.58, .45, .58, .72, .86][min(depth, 4)]
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
        lift = UP*length*(.16 if depth < 2 else .22)
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


def side_growth(curve, rng):
    for i, t in enumerate((.50, .60, .70, .80, .90)):
        start = bezier(curve, t)
        outward = Vector((start.x, start.y, 0)).normalized()
        across = UP.cross(outward)
        tip = start+outward*rng.uniform(.55, .95)+across*((-1)**i)*.65
        tip.z -= rng.uniform(.05, .25)
        points = []
        for _ in range(10):
            point = tip+Vector((rng.uniform(-.4, .4), rng.uniform(-.4, .4),
                                rng.uniform(-.3, .35)))
            if not any((point-Vector(c)).length < r for c, r in GAPS):
                points.append(point)
        if points:
            yield t, points


def root_flare(wood, rng):
    for i in range(4):
        angle = i*2.39996+rng.uniform(-.3, .3)
        along = Vector((math.cos(angle), math.sin(angle), 0))
        bend = Vector((math.cos(angle+.25), math.sin(angle+.25), 0))
        reach = rng.uniform(.8, 1.35)*0.65
        height = rng.uniform(.9, 1.5)*0.65
        wood.add([along*(reach*.14)+UP*height, along*(reach*.36)+UP*(height*.74),
                  bend*(reach*.82)+UP*(height*.16), bend*reach-UP*.32],
                 rng.uniform(.29, .37)*0.65, rng.uniform(.085, .12)*0.65, 28, 36)


def displace_bark(obj, frames):
    subdivision = obj.modifiers.new("Rindengeometrie", "SUBSURF")
    subdivision.subdivision_type = "SIMPLE"
    subdivision.levels = 1
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=subdivision.name)
    tree = KDTree(len(frames))
    for i, (centre, *_rest) in enumerate(frames):
        tree.insert(centre, i)
    tree.balance()
    obj.data.update()
    normals = [vertex.normal.copy() for vertex in obj.data.vertices]
    for vertex, normal in zip(obj.data.vertices, normals):
        if vertex.co.z < .015:
            continue
        _, index, _ = tree.find(vertex.co)
        centre, direction, axis, radius, bands = frames[index]
        radial = vertex.co-centre
        other = direction.cross(axis).normalized()
        angle = math.atan2(radial.dot(other), radial.dot(axis))
        wander = .3*noise.noise(vertex.co*.8+Vector((2, 7, 4)))
        relief = (.004*math.cos(angle*bands+wander)
                  + .001*math.cos(angle*bands*2+1.4+wander))
        fade = min(1, (vertex.co.z-.015)/.08, radius/.16)
        vertex.co += normal*relief*fade
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    moss = vrmat.get("tree_bark").copy()
    moss.name = "broadleaf_moos_Wetterseite"
    socket = moss.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    for link in list(socket.links):
        moss.node_tree.links.remove(link)
    palette = vrmat.load_palette()
    socket.default_value = (*(a*.20+b*.80 for a, b in zip(
        palette["moss"]["linear_rgb"], palette["bark"]["linear_rgb"])), 1)
    obj.data.materials.append(moss)
    weather = Vector((-.9, -.4, 0)).normalized()
    for polygon in obj.data.polygons:
        centre = polygon.center
        radial = Vector((centre.x, centre.y, 0))
        if radial.length < .1:
            continue
        patch = noise.noise(centre*4.5+Vector((1, 8, 3)))
        if (.08 < centre.z < .65 and radial.length < 1.35
                and radial.normalized().dot(weather) > .65 and patch > 0
                and polygon.normal.z > .25):
            polygon.material_index = len(obj.data.materials)-1


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
    hanging = local_height < -.1
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
        along = (forward*.45+radial*.85+outward*.25
                 + UP*(rng.uniform(.05, .4)-(.65 if hanging else 0))).normalized()
        normal = (UP*.85+radial*.45+outward*.2).normalized()
        across = normal.cross(along).normalized()
        normal = along.cross(across).normalized()
        if normal.z < 0:
            normal.negate()
            across.negate()
        length = rng.uniform(*LEAF_LENGTH)
        petiole = stem+along*length*.14
        offset = len(vertices)
        width = length*rng.uniform(.13, .21)
        for x, y in [(0, 0), (.17, -.62), (.48, -1), (.74, -.55),
                     (1, 0), (.74, .55), (.48, 1), (.17, .62)]:
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



def ground_contact(radius, rise, seed, wet=False):
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
        return rise*(1-t*t)**2+min(.04, rise*.5)*relief*math.sin(math.pi*t)-.045*t**3
    def point(j, k):
        a, t = j*math.tau/64, k/10
        r = radius*t*(1+.18*math.sin(3*a+phase)+.09*math.sin(5*a-phase))
        return Vector((r*math.cos(a), r*math.sin(a), height(t, a)))
    for j in range(64):
        face([Vector((0, 0, rise)), point(j, 1), point(j+1, 1)], 0)
        for k in range(1, 10):
            face([point(j, k), point(j, k+1), point(j+1, k+1), point(j+1, k)], 0)
        bottom = Vector((point(j, 10).x, point(j, 10).y, -.055))
        next_bottom = Vector((point(j+1, 10).x, point(j+1, 10).y, -.055))
        face([point(j, 10), bottom, next_bottom, point(j+1, 10)], 0)
        face([Vector((0, 0, -.055)), next_bottom, bottom], 0)
    count = 360 if radius > .8 else 240 if radius > .3 else 48
    for i in range(count):
        a = (i%13)*2.39996+rng.uniform(-.12, .12)
        t = .64+.018*(i%13)+rng.uniform(-.06, .06)
        r = radius*t*(1+.18*math.sin(3*a+phase)+.09*math.sin(5*a-phase))
        root = Vector((r*math.cos(a), r*math.sin(a), max(-.004, height(t, a)-.012)))
        direction = Vector((math.cos(a+rng.uniform(-.8, .8)), math.sin(a+rng.uniform(-.8, .8)), 0)).normalized()
        length = rng.uniform(.16, .40)*min(1, radius/.5)
        points = [root]
        for j in range(8):
            u = (j+.5)/8
            angle = .3+2.5*u**1.7
            points.append(points[-1]+(direction*math.sin(angle)+UP*math.cos(angle))*(length/8))
        blade(points, rng.uniform(.006, .014), UP.cross(direction), 2 if i%5 == 0 else 1, rng.uniform(-.4, .4))
    for i in range(58 if radius > .3 else 16):
        a = rng.uniform(0, math.tau)
        t = rng.uniform(.25, .85)
        p = point(a*64/math.tau, t*10)+UP*.004
        direction = Vector((math.cos(a+1), math.sin(a+1), 0))
        length = rng.uniform(.045, .12)*min(1, radius/.25)
        points = [p+direction*(length*u)+UP*(.025*math.sin(math.pi*u)) for u in (0, .2, .4, .6, .8, 1)]
        blade(points, length*.24, UP.cross(direction), 2, rng.uniform(.5, 1.5))
    for i in range(9 if wet else 12):
        a, t = rng.uniform(0, math.tau), rng.uniform(.45, 1.03)
        centre = point(a*64/math.tau, t*10)
        size = rng.uniform(.012, .036)*min(1.5, radius/.3)
        centre.z = max(-.008, centre.z)-size*.2
        scale = Vector((size, size*rng.uniform(.65, 1.2), size*.55))
        rings = [[centre+Vector((math.cos(a)*math.sin(v)*scale.x, math.sin(a)*math.sin(v)*scale.y, math.cos(v)*scale.z))
                  for a in [math.tau*j/10 for j in range(10)]] for v in (math.pi/4, math.pi/2, math.pi*3/4)]
        for j in range(10):
            face([centre+UP*scale.z, rings[0][j], rings[0][(j+1)%10]], 3 if wet else 0)
            for k in range(2):
                face([rings[k][j], rings[k+1][j], rings[k+1][(j+1)%10], rings[k][(j+1)%10]], 3 if wet else 0)
            face([centre-UP*scale.z, rings[-1][(j+1)%10], rings[-1][j]], 3 if wet else 0)
    palette = vrmat.load_palette()
    mats = []
    for library, first, second, mix, gain in [
        ("forest_soil", "soil", "grass_dry", .5, 1.3),
        ("grass_ground", "grass_green", "grass_dry", .55, 2.1),
        ("grass_ground", "grass_dry", "bark", .18, 1.9),
        ("river_stones", "shore_wet", "soil", .35, 1.0),
    ]:
        mat = vrmat.get(library).copy()
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        for socket in ("Base Color", "Normal", "Roughness"):
            for link in list(bsdf.inputs[socket].links):
                mat.node_tree.links.remove(link)
        bsdf.inputs["Base Color"].default_value = (*(gain*(x*(1-mix)+y*mix) for x, y in zip(
            palette[first]["linear_rgb"], palette[second]["linear_rgb"])), 1)
        bsdf.inputs["Specular IOR Level"].default_value = .16
        bsdf.inputs["Roughness"].default_value = .38 if wet and library in ("forest_soil", "river_stones") else .88
        mats.append(mat)
    obj = mesh_object("Bodensaum_Gras_und_Streu", vertices, faces, mats, indices)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()


def build():
    rng = random.Random(SEED)
    bark = vrmat.get("tree_bark").copy()
    bark.name = "broadleaf_bark_furrows"
    for node in bark.node_tree.nodes:
        if node.type == "BUMP" and node.inputs["Distance"].default_value > .001:
            node.inputs["Distance"].default_value = BARK_RELIEF
            node.inputs["Strength"].default_value = .65
    materials = foliage_materials()+[bark]
    thick, thin = Tubes(), Tubes()
    root_flare(thick, random.Random(SEED+263))
    points = attractors(rng)
    roots = []
    fork = Vector(BOLE[-1])
    scaffolds = [
        [fork, Vector((1.0, .15, 4.2)), Vector((1.9, .5, 7.1)), Vector((2.1, .5, 10.0))],
        [fork, Vector((-.5, -.8, 3.6)), Vector((-1.1, -.6, 5.5)), Vector((-.5, -.2, 7.8))],
    ]
    for curve in scaffolds:
        for point in curve[1:3]:
            point.x += rng.uniform(-.16, .16)
            point.y += rng.uniform(-.16, .16)
    groups = [[] for _ in CLUSTERS]
    for point in points:
        index = min(range(len(CLUSTERS)), key=lambda k: min(
            ellipsoid_score(point, c, r) for c, r in CLUSTERS[k]))
        groups[index].append(point)
    scaffold_radii = []
    for cluster, group, curve in zip(CLUSTERS, groups, scaffolds):
        lower = min(c[2]-r[2] for c, r in cluster)
        upper = max(c[2]+r[2] for c, r in cluster)
        attachments = []
        for t, secondary in side_growth(curve, rng):
            branch = Branch(secondary, bezier(curve, t), tangent(curve, t), 1, rng)
            roots.append(branch)
            attachments.append((t, branch.radius))
        for secondary in partition(group, 7):
            centre = sum(secondary, Vector())/len(secondary)
            t = .35+.55*max(0, min(1, (centre.z-lower)/(upper-lower)))
            branch = Branch(secondary, bezier(curve, t), tangent(curve, t), 1, rng)
            roots.append(branch)
            attachments.append((t, branch.radius))
        def radius_at(t, centre):
            return math.sqrt(.018**2+sum(radius**2*max(0, min(1, (position+.06-t)/.12))
                                       for position, radius in attachments))
        radius = radius_at(0, fork)
        scaffold_radii.append(radius)
        thick.add(curve, radius, .018, 24, 64, radius_at=radius_at)
    fork_radius = math.sqrt(sum(radius**2 for radius in scaffold_radii))
    def trunk_radius(t, centre):
        z = max(0, centre.z)
        if z < 1.3:
            return .275+(BASE_RADIUS-.275)*(1-z/1.3)**2
        return .275+(fork_radius-.275)*(z-1.3)/(BOLE[-1][2]-1.3)
    thick.add([Vector(p) for p in BOLE], BASE_RADIUS, fork_radius, 40, 80,
              radius_at=trunk_radius)
    thick.add([Vector((.28, 0, 1.6)), Vector((.32, 0, 1.9)),
               Vector((.53, .02, 2.5)), Vector((.68, .04, 3.0))],
              .18, .18, 32, 40,
              radius_at=lambda t, centre: .18+.075*math.sin(math.pi*t))
    print("VR_PROPORTIONS", {"dbh_m": .55, "fork_radius_m": round(fork_radius, 3),
                             "primary_diameters_m": [round(2*r, 3) for r in scaffold_radii]},
          flush=True)
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
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                          plane_co=Vector((0, 0, -.055)), plane_no=UP,
                          clear_inner=True, clear_outer=False, dist=1e-6)
    bmesh.ops.holes_fill(bm, edges=[edge for edge in bm.edges if edge.is_boundary], sides=0)
    remaining = set(bm.verts)
    components = []
    while remaining:
        component = {remaining.pop()}
        stack = list(component)
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    component.add(other)
                    stack.append(other)
        components.append(component)
    main = max(components, key=len)
    bmesh.ops.delete(bm, geom=[v for c in components if c is not main for v in c], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    displace_bark(obj, thick.frames)
    thin.object("Feinaeste_und_Zweige", bark)
    mesh_object("Einzelblaetter", vertices, faces, materials, indices)
    print("VR_BRANCHES", {"terminal_twigs": TARGETS, "leaves": len(indices)//9,
                          "pipe_model": "parent end radius squared = sum child start radii squared"}, flush=True)

    ground_contact(1.0, 0.24, SEED+921, wet=False)

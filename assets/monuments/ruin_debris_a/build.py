"""A fallen pair of limestone shaft drums and surrounding architectural rubble."""
import math
import random

import bpy
from mathutils import Euler, Vector
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat


def limestone(name):
    local_name = f"ruin_debris_a.{name}"
    mat = bpy.data.materials.get(local_name)
    if mat is not None:
        return mat
    mat = vrmat.get(name).copy()
    mat.name = local_name
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    surface = nodes["Principled BSDF"]
    weathered = name == "monument_weathered"
    palette = vrmat.load_palette()
    white = palette["monument_white"]["linear_rgb"]
    patina = palette["stone_weathered"]["linear_rgb"]
    pores = next(n for n in nodes if n.type == "TEX_VORONOI")
    pores.inputs["Scale"].default_value = 32
    grain = nodes.new("ShaderNodeValToRGB")
    grain.color_ramp.elements[0].position = .11
    grain.color_ramp.elements[0].color = (*(v * .74 for v in white), 1)
    grain.color_ramp.elements[1].position = .34
    grain.color_ramp.elements[1].color = (*white, 1)
    links.new(pores.outputs["Distance"], grain.inputs["Fac"])
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = .31 if weathered else .14
    tone = nodes.new("ShaderNodeMixRGB")
    strength = .68 if weathered else .34
    tone.inputs["Color1"].default_value = (*(a * (1-strength) + b * strength for a, b in zip(white, patina)), 1)
    links.new(ao.outputs["AO"], tone.inputs["Fac"])
    links.new(grain.outputs["Color"], tone.inputs["Color2"])
    links.new(tone.outputs["Color"], surface.inputs["Base Color"])
    bump = surface.inputs["Normal"].links[0].from_node
    bump.inputs["Strength"].default_value = .67
    bump.inputs["Distance"].default_value = .021
    roughness = surface.inputs["Roughness"].links[0].from_node
    roughness.inputs["To Min"].default_value = .77
    roughness.inputs["To Max"].default_value = .94
    return mat


def stone(name, vertices, faces, position, rotation, material, smooth=(), old_faces=(), lift=-.026):
    # Seat each piece after rotation, so fractured tips do not hang above the ground.
    matrix = Euler(rotation).to_matrix()
    transformed = [matrix @ Vector(vertex) for vertex in vertices]
    low = min(v.z for v in transformed)
    x, y = position
    vertices = [(v.x + x, v.y + y, v.z - low + lift) for v in transformed]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(material))
    if old_faces:
        obj.data.materials.append(limestone("monument_weathered"))
    for polygon in mesh.polygons:
        polygon.use_smooth = polygon.index in smooth
        polygon.material_index = int(polygon.index in old_faces)
    mesh.set_sharp_from_angle(angle=math.radians(35))
    return obj


def drum(name, position, rotation, r, h, cracked, rng):
    n = 288
    vertices, faces = [], []
    def fault(x, y):
        return (.25*x - .13*y + .29*min(0, x + .47*y + .35*r)
                - .33*max(0, .60*x-y-.30*r) + .11*abs(.84*x+.34*y-.18*r))

    levels = (0, .014, .049, .13, .24, .37, .52, .66, .78, .88, .944, .98, 1)
    rows = len(levels)
    for k, t in enumerate(levels):
        for j in range(n):
            a = math.tau * j / n
            phase = j * 12 / n
            slot = abs(phase-round(phase))/.345
            flutes = .128 * math.sqrt(max(0,1-slot*slot)) if cracked else 0
            radius = r * (1 - .055 * t) - flutes
            radius += .003 * math.cos(17 * a - t * 5)
            if not cracked:
                radius += r * (.15 if .13 <= t <= .24 else .09 if .78 <= t <= .88 else 0)
            radius -= (.025 * r if k in (0, rows - 1) else 0)
            if cracked and k >= rows-3:
                for center, depth, arc in ((.57,.21,.34), (2.61,.11,.19), (4.09,.27,.63)):
                    off = abs(math.remainder(a-center,math.tau))
                    radius -= depth * max(0,1-off/arc) * (k-rows+4)/3
            z = h * (t - .5) + (fault(radius*math.cos(a),radius*math.sin(a)) * t if cracked else 0)
            vertices.append((radius * math.cos(a), radius * math.sin(a), z))
    for i in range(rows - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    smooth = range(len(faces))
    faces.append(tuple(reversed(range(n))))
    damaged = len(faces)
    if cracked:
        rim = (rows - 1) * n
        outline = [Vector((x,y)) for x,y,_ in vertices[rim:]]
        points = outline[:]
        for i in range(-7,8):
            for j in range(-7,8):
                x = r*(i*.119+rng.uniform(-.046,.046))
                y = r*(j*.122+rng.uniform(-.046,.046))
                if math.hypot(x,y) < .69*r:
                    points.append(Vector((x,y)))
        coords, _, pieces, source_ids, _, _ = delaunay_2d_cdt(points, [], [tuple(range(n))], 1, 1e-6)
        indices = []
        for (x,y), ids in zip(coords, source_ids):
            if ids and ids[0] < n:
                indices.append(rim + ids[0])
                continue
            trough = max(0, .64 - math.hypot(x/r-.16,(y/r+.13)*1.32))
            step = min(0, -.105+1.34*abs(y-.25*x+.17*r))
            z = h/2 + fault(x,y) - .43*r*trough + step + rng.uniform(-.025,.025)
            indices.append(len(vertices))
            vertices.append((x,y,z))
        faces.extend(tuple(indices[j] for j in face) for face in pieces)
    else:
        faces.append(tuple(range((rows - 1) * n, rows * n)))
    stone(name, vertices, faces, position, rotation, "monument_white", smooth,
          range(damaged, len(faces)) if cracked else ())


def rubble(name, position, dims, rng, dressed, lift=-.025):
    w, d, h = (a / 2 for a in dims)
    vertices = []
    shape = ((-.87,-1),(.71,-1),(1,-.81),(1,.68),(.73,1),(-.85,1),(-1,.83),(-1,-.88))
    for j, z in enumerate((-h, -.92*h, .66*h, h)):
        for a, b in shape:
            f = (.97,1,1.04 if dressed else 1,.96 if dressed else 1)[j]
            cut = (.28*max(0, a+.51*b) - .24*max(0,-b-a)) if j>1 else 0
            vertices.append((w*(f*a + rng.uniform(-.016,.016)+(.12*max(0,b) if j>1 else 0)),
                             d*(f*b + rng.uniform(-.018,.018)),
                             z + h*(cut + (rng.uniform(-.12,.12) if j==3 else 0))))
    faces = [tuple(reversed(range(8)))]
    for k in range(3):
        for j in range(8):
            a, b = 8 * k + j, 8 * k + (j + 1) % 8
            faces.append((a, b, b + 8, a + 8))
    faces.extend(((24,25,26,27), (24,27,28,29), (24,29,30,31)))
    obj = stone(name, vertices, faces, position, (rng.uniform(-.22, .22), rng.uniform(-.17, .17),
                                                  rng.uniform(-math.pi, math.pi)),
                "monument_white" if dressed else "monument_weathered",
                old_faces=range(len(faces)-3,len(faces)) if dressed else (), lift=lift)
    bevel = obj.modifiers.new("Small edge losses", "BEVEL")
    bevel.width, bevel.segments = min(dims) * .026, 2
    bevel.angle_limit = math.radians(19)
    obj.modifiers.new("Broad face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(7301)
    drum("Fractured fluted drum", (-1.73,-.40), (1.36,.25,1.83), 1.13, 2.18, True, rng)
    drum("Separated shaft drum", (.72,.22), (1.39,-.34,1.91), 1.02, 1.57, True, rng)
    drum("Broken neck moulding", (2.47,.77), (.99,.16,1.15), .81, .59, False, rng)
    rubble("Dislodged cornice shingle wedged on shaft", (.85,-.39), (.91,.52,.26), rng, True, lift=.42)
    for i, (x, y, a, b, c) in enumerate((
        (-2.65, 1.37, 1.36, .93, .72), (-3.38, .16, 1.08, .76, .61),
        (-.47, -1.99, 1.56, .84, .62), (.82, -1.29, .99, .77, .47),
        (-.82, 1.89, .9, .82, .43), (2.99, 1, .94, .66, .51),
        (2.41, -2.21, 1.27, .62, .46), (3.65, -.12, .70, .56, .36),
        (-2.68, -1.93, .57, .51, .31), (.17, .32, .70, .52, .32),
    )):
        rubble(f"Fallen ashlar {i}", (x, y), (a, b, c), rng, i not in (1, 4, 8))
    for i, (x, y) in enumerate(((-3.4, -1.43), (-3.68, -.72), (-1.94, -2.42), (-.97, -2.57),
                               (.28, -2.3), (1.28, -2.32), (3.36, -1.84), (3.75, -.93),
                               (3.37, .61), (2.94, 1.78), (1.98, 2.52), (.14, 2.61),
                               (-.96, 2.4), (-2.05, 2.1), (-3.22, 1.95), (-.25, .79),
                               (.78, -.6), (1.63, -.89), (-.44, 1.35))):
        a = rng.uniform(.14, .39)
        rubble(f"Spall {i}", (x, y), (a, a * rng.uniform(.61, .89), a * rng.uniform(.35, .65)), rng, False)

"""A fallen pair of limestone shaft drums and surrounding architectural rubble."""
import math
import random

import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat


def limestone(name):
    if name in ("mossy_rock", "dirt_path", "grass_ground"):
        return vrmat.get(name)
    local_name = f"ruin_debris_a.{name}"
    mat = bpy.data.materials.get(local_name)
    if mat is not None:
        return mat
    mat = vrmat.get(name).copy()
    mat.name = local_name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]
    cool = tuple(c*k for c,k in zip(cream, (.88, .94, 1.065)))
    pale = tuple(c*k for c,k in zip(cream, (1.035, 1.001, .945)))
    seam = palette["stone_weathered"]["linear_rgb"]
    coords = next(node for node in nodes if node.type == "TEX_COORD").outputs["Object"]

    def noise(scale, detail, vector=coords):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(source, low, high, colors):
        node = nodes.new("ShaderNodeValToRGB")
        for stop, pos, color in zip(node.color_ramp.elements, (low, high), colors):
            stop.position, stop.color = pos, (*color, 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, a, b):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, float):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, value in zip(node.inputs[1:3], (a,b)):
            if isinstance(value, tuple):
                socket.default_value = (*value,1)
            else:
                links.new(value, socket)
        return node.outputs["Color"]

    variation = noise(.87, 3)
    tone = ramp(variation, .23, .79, (cool, pale))
    random_tone = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(.18, tone, ramp(random_tone, 0, 1, (cool, pale)))
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    old = name == "monument_weathered"
    ao.inputs["Distance"].default_value = .19 if old else .065
    joint = tuple(.74*a+.26*b for a,b in zip(seam, cream))
    tone = mix(ao.outputs["AO"], joint, tone)
    if old:
        patina = palette["monument_shadow"]["linear_rgb"]
        weathered = tuple(.38*a+.62*b for a,b in zip(seam,patina))
        tone = mix(.48, tone, ramp(noise(2.3, 3), .28, .68, (weathered, pale)))
    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), .16, .86, ((.72,.72,.72),(.93,.93,.93))), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .023
    bump.inputs["Strength"].default_value = .42
    links.new(noise(10, 2), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return mat


def stone(name, vertices, faces, position, rotation, material, smooth=(), lift=-.026):
    # Seat each piece after rotation, so fractured tips do not hang above the ground.
    matrix = Euler(rotation).to_matrix()
    transformed = [matrix @ Vector(vertex) for vertex in vertices]
    low = min(v.z for v in transformed)
    x, y = position
    burial_scale = -.059 / lift if lift < -.059 else 1
    vertices = []
    for v in transformed:
        z = v.z - low + lift
        vertices.append((v.x + x, v.y + y, z if z >= 0 else z * burial_scale))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(material))
    for polygon in mesh.polygons:
        polygon.use_smooth = polygon.index in smooth
    mesh.set_sharp_from_angle(angle=math.radians(35))
    return obj


def drum(name, position, rotation, r, h, cracked, rng):
    n = 512
    phase_variation = rng.uniform(0,math.tau)
    vertices, faces = [], []
    def fault(x, y):
        return (.25*x - .13*y + .29*min(0, x + .47*y + .35*r)
                - .33*max(0, .60*x-y-.30*r) + .11*abs(.84*x+.34*y-.18*r))

    levels = (0, .014, .049, .08, .112, .16, .21, .255, .31, .37, .43, .50, .56, .62,
              .69, .74, .78, .83, .88, .92, .944, .98, 1)
    rows = len(levels)
    for k, t in enumerate(levels):
        for j in range(n):
            a = math.tau * j / n
            phase = j*16/n
            slot = abs(phase-round(phase))/.36
            flute_run = min(1,8.7*t,.20+4.6*(1-t))
            flutes = r*.237*(1-slot**4)**.69*flute_run if cracked and slot < 1 else 0
            radius = r * (1 - .055 * t) - flutes
            radius += (.011*math.sin(7*a+phase_variation+4*t) + .004*math.cos(17*a-t*5)
                       + .003*math.sin(37*a+19*t))
            if not cracked:
                bell = .11+.52*math.sin(math.pi*min(1,t/.78)/2)**2
                fillet = .11*math.exp(-((t-.12)/.078)**2)+.115*math.exp(-((t-.78)/.052)**2)
                radius += r*(bell+fillet+.10*math.cos(a*8)*math.sin(math.pi*t)**2)
            radius -= (.025 * r if k in (0, rows - 1) else 0)
            if k >= rows-3:
                for center, depth, arc in ((.57,.21,.34), (2.61,.11,.19), (4.09,.27,.63)):
                    off = abs(math.remainder(a-center,math.tau))
                    radius -= depth * max(0,1-off/arc) * (k-rows+4)/3 * (1 if cracked else .42)
            z = h * (t - .5) + (fault(radius*math.cos(a),radius*math.sin(a)) * t if cracked else 0)
            vertices.append((radius * math.cos(a), radius * math.sin(a), z))
    for i in range(rows - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    smooth = range(len(faces))
    faces.append(tuple(reversed(range(n))))
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
            cap = max(0,1-math.hypot(x,y)/r)
            broken_plane=.17*abs(.62*x+.12*y+.10*r)-.24*max(0,.31*x-y+.16*r)
            z = h/2+fault(x,y)+cap*(broken_plane+.043*math.sin(18*x+9*y)+.011*math.sin(37*y-26*x))
            z += cap*rng.uniform(-.014,.014)
            indices.append(len(vertices))
            vertices.append((x,y,z))
        faces.extend(tuple(indices[j] for j in face) for face in pieces)
    else:
        faces.append(tuple(range((rows - 1) * n, rows * n)))
    stone(name, vertices, faces, position, rotation, "monument_white", smooth,
          lift=-.30 if cracked else -.27)


def rubble(name, position, dims, rng, dressed, lift=-.13, material=None):
    w, d, h = (a / 2 for a in dims)
    vertices = []
    shape = ((-.87,-1),(.71,-1),(1,-.81),(1,.68),(.73,1),(-.85,1),(-1,.83),(-1,-.88))
    notch = int(abs(position[0]*21 + position[1]*15)) % len(shape)
    for j, z in enumerate((-h, -.92*h, .66*h, h)):
        for i, (a, b) in enumerate(shape):
            f = (.97,1,1.04 if dressed else 1,.96 if dressed else 1)[j]
            cut = (.28*max(0, a+.51*b) - .24*max(0,-b-a)) if j>1 else 0
            if j == 3 and i == notch:
                f -= .14
                cut -= .22
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
                material or ("monument_white" if dressed else "monument_weathered"), lift=lift)
    bevel = obj.modifiers.new("Small edge losses", "BEVEL")
    bevel.width, bevel.segments = min(dims) * .026, 2
    bevel.angle_limit = math.radians(19)
    obj.modifiers.new("Broad face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(7301)
    drum("Main shaft on the fall line", (-2.11,-.38), (1.48,.13,1.78), 1.10, 2.42, True, rng)
    drum("Separated shaft on the fall line", (.49,.16), (1.50,-.15,1.71), .94, 1.76, True, rng)
    drum("Fallen bell capital with torus and astragal", (2.58,.64), (1.35,.16,1.73), .83, .84, False, rng)
    rubble("Broken abacus slab", (3.42,1.22), (1.14,.79,.37), rng, True, lift=-.17)
    for i,(x,y) in enumerate(((-2.23,-1.09),(-.90,-.64),(-.21,.71),(.83,-.58),(2.42,-.05),(2.98,1.35))):
        rubble(f"Ground contact and scree {i}", (x,y), (1.0,.66,.38), rng, False,
               lift=-.20, material="dirt_path" if i%2 else "mossy_rock")
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
    orient=Matrix.Rotation(math.radians(62),4,"Z")
    for obj in vrlib.source_objects():
        obj.data.transform(orient)

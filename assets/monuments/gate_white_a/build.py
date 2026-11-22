"""Floodmark Gate: three orders of limestone above a worn ford threshold."""

import math
import random

import bmesh
import bpy
from mathutils import Vector

import vrlib
import vrmat


SPRING = 15.4
INNER = 12.2


def weathering(mat):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    geom = nodes.new("ShaderNodeNewGeometry")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geom.outputs["Position"], xyz.inputs[0])
    normal = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geom.outputs["Normal"], normal.inputs[0])

    def wire(value, socket):
        if isinstance(value, (float, int, tuple)):
            socket.default_value = value
        else:
            links.new(value, socket)

    def op(mode, a, b=0):
        node = nodes.new("ShaderNodeMath")
        node.operation = mode
        wire(a, node.inputs[0])
        wire(b, node.inputs[1])
        return node.outputs[0]

    def ramp(value, lo, hi, start, end):
        node = nodes.new("ShaderNodeMapRange")
        node.interpolation_type = "SMOOTHERSTEP"
        for socket, arg in zip(node.inputs, (value, lo, hi, start, end)):
            wire(arg, socket)
        return node.outputs[0]

    def noise(stretch, detail):
        vec = nodes.new("ShaderNodeVectorMath")
        vec.operation = "MULTIPLY"
        links.new(geom.outputs["Position"], vec.inputs[0])
        vec.inputs[1].default_value = stretch
        n = nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1
        n.inputs["Detail"].default_value = detail
        links.new(vec.outputs["Vector"], n.inputs["Vector"])
        return n.outputs["Fac"]

    def multiply_color(mask, tint):
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        links.new(mask, mix.inputs[0])
        links.new(surface.inputs["Base Color"].links[0].from_socket, mix.inputs[1])
        mix.inputs[2].default_value = tint
        links.new(mix.outputs[0], surface.inputs["Base Color"])

    z, y = xyz.outputs["Z"], op("ABSOLUTE", xyz.outputs["Y"])
    rain = ramp(noise((1.65, 2.75, .15), 2), .20, .80, .18, 1)
    impost = op("MULTIPLY", ramp(z, 8.6, 12.55, 0, 1), ramp(z, 12.72, 13.65, 1, 0))
    crown = op("MULTIPLY", ramp(y, .55, 3.15, 1, 0), ramp(z, 26.35, 31.3, 0, 1))
    multiply_color(op("MULTIPLY", rain, op("MAXIMUM", impost, crown)), (.18, .14, .096, 1))

    foot = op("MULTIPLY", ramp(y, 11.6, 12.5, 0, 1), ramp(z, .18, 2.35, 1, 0))
    broken_edge = op("ADD", z, op("MULTIPLY", noise((1.1,1.1,1.4), 2), .82))
    band = op("MULTIPLY", foot, ramp(broken_edge, 1.29, 2.32, .99, .27))
    multiply_color(band, (.23, .34, .21, 1))
    lichen = ramp(noise((6.0,6.0,5.7), 3), .47, .72, 0, 1)
    multiply_color(op("MULTIPLY", lichen, foot), (.39, .64, .23, 1))

    worn_width = op("ADD", y, op("MULTIPLY", noise((.38,.55,1.0), 2), 1.6))
    tread = op("MULTIPLY", ramp(worn_width, 2.0, 6.65, 1, 0), ramp(z, .87, 1.13, 1, 0))
    tread = op("MULTIPLY", tread, ramp(normal.outputs["Z"], .74, .98, 0, 1))
    multiply_color(tread, (.39, .35, .29, 1))
    rough = surface.inputs["Roughness"]
    subtract = op("SUBTRACT", rough.links[0].from_socket, op("MULTIPLY", tread, .48))
    links.new(subtract, rough)
    bump = surface.inputs["Normal"].links[0].from_node
    if bump.type == "BUMP":
        links.new(ramp(tread, 0, 1, bump.inputs["Strength"].default_value, .05), bump.inputs["Strength"])


def finish():
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]
    shades = []
    for i in range(12):
        mat = vrmat.get("monument_white").copy()
        mat.name = f"Dressed limestone | bed {i + 1:02}"
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        surface = nodes["Principled BSDF"]
        old_color = surface.inputs["Base Color"].links[0].from_socket
        tone = .58 + .043 * i
        warm = math.sin(1.93 * i)
        color = tuple(c * tone * s for c, s in zip(cream, (1 + .080 * warm, 1, 1 - .147 * warm)))
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs[0].default_value = .73
        mix.inputs[2].default_value = (*color, 1)
        links.new(old_color, mix.inputs[1])
        links.new(mix.outputs[0], surface.inputs["Base Color"])
        surface.inputs["Specular IOR Level"].default_value = .23
        old_normal = surface.inputs["Normal"].links[0].from_socket
        coords = next(node for node in nodes if node.type == "TEX_COORD")
        grit = nodes.new("ShaderNodeTexNoise")
        grit.inputs["Scale"].default_value = 8
        grit.inputs["Detail"].default_value = 3
        links.new(coords.outputs["Object"], grit.inputs["Vector"])
        relief = nodes.new("ShaderNodeBump")
        relief.inputs["Strength"].default_value = .31
        relief.inputs["Distance"].default_value = .022
        links.new(old_normal, relief.inputs["Normal"])
        links.new(grit.outputs["Fac"], relief.inputs["Height"])
        links.new(relief.outputs["Normal"], surface.inputs["Normal"])
        weathering(mat)
        shades.append(mat)
    mortar = vrmat.get("monument_weathered").copy()
    mortar.name = "Recessed silty lime mortar"
    surface = mortar.node_tree.nodes["Principled BSDF"]
    source = surface.inputs["Base Color"].links[0].from_socket
    multiply = mortar.node_tree.nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs[0].default_value = 1
    multiply.inputs[2].default_value = (.28, .29, .19, 1)
    mortar.node_tree.links.new(source, multiply.inputs[1])
    mortar.node_tree.links.new(multiply.outputs[0], surface.inputs["Base Color"])
    weathering(mortar)
    foot = vrmat.get("monument_weathered").copy()
    foot.name = "Damp limestone plinths"
    weathering(foot)
    return shades, mortar, foot


def mesh(name, verts, faces, mat, cuts=(), rounding=0, curved=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(-y, x, z) for x, y, z in verts], [], faces)
    data.update()
    if cuts or rounding:
        bm = bmesh.new()
        bm.from_mesh(data)
        for point, normal in cuts:
            x, y, z = point
            nx, ny, nz = normal
            result = bmesh.ops.bisect_plane(
                bm, geom=[*bm.verts, *bm.edges, *bm.faces], dist=1e-6,
                plane_co=(-y, x, z), plane_no=(-ny, nx, nz), clear_outer=True,
            )
            rim = [edge for edge in result["geom_cut"]
                   if isinstance(edge, bmesh.types.BMEdge) and edge.is_valid and edge.is_boundary]
            if rim:
                bmesh.ops.holes_fill(bm, edges=rim)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    data.materials.append(mat)
    if rounding:
        for face in data.polygons:
            face.use_smooth = True
        bevel = obj.modifiers.new("Weathered arrises", "BEVEL")
        bevel.width, bevel.segments, bevel.angle_limit = rounding, 3, .20
        if not curved:
            obj.modifiers.new("Broad dressed faces", "WEIGHTED_NORMAL")
    return obj


def ashlar(name, x0, x1, y0, y1, z0, z1, mat, rng, wear=.08, shift=(0, 0), beds=(),
           pitch=(0,0)):
    dx, dy = shift
    px, py = pitch
    verts = [(a + dx*j, b + dy*j, z + j*(px*(a-(x0+x1)*.5)+py*(b-(y0+y1)*.5)))
             for j, z in enumerate((z0, z1))
             for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7)] + [
        (i, (i + 1) % 4, (i + 1) % 4 + 4, i + 4) for i in range(4)
    ]
    cuts = list(beds)
    if wear:
        for _ in range(1 + (rng.random() < .33)):
            sx, sy, sz = (rng.choice((-1, 1)) for _ in range(3))
            depth = rng.uniform(wear * .66, wear * 2.85)
            x = (x0 if sx < 0 else x1) + dx * (sz > 0)
            y = (y0 if sy < 0 else y1) + dy * (sz > 0)
            cuts.append(((x - sx * depth, y, z0 if sz < 0 else z1),
                         (sx, rng.uniform(.4, 1.3) * sy, rng.uniform(.58, 1.7) * sz)))
        if z1-z0 > .54 and rng.random() < .31:
            sy = rng.choice((-1,1))
            yy = y0 if sy < 0 else y1
            xx = rng.uniform(x0,x1)
            end = rng.uniform(.08,.20)
            cuts.append(((xx, yy+dy - sy*end, z1), (rng.uniform(-.16,.16),sy,1.07)))
    return mesh(name, verts, faces, mat, cuts, wear * rng.uniform(.48, .74))


def ring(name, lo, hi, profile, mat, rounding, rng):
    steps = max(5, math.ceil((hi - lo) * 130))
    n = len(profile)
    verts = []
    phase = rng.uniform(0, math.tau) if rounding else 0
    for j in range(steps + 1):
        u = j / steps
        t = lo + (hi - lo) * u
        for r, y in profile:
            erosion = math.sin(math.pi * u)**2 if rounding else 0
            dr = erosion * (.044 * math.sin(6*u + .55*y + phase) + .014 * math.sin(13*u + y))
            dy = erosion * (.043 * math.sin(7*u + r + phase) + .011 * math.sin(18*u + 2*r))
            verts.append(((r+dr) * math.cos(t), y+dy, SPRING + (r+dr) * math.sin(t)))
    faces = [tuple(reversed(range(n)))]
    faces.extend((j * n + k, j * n + (k + 1) % n,
                  (j + 1) * n + (k + 1) % n, (j + 1) * n + k)
                 for j in range(steps) for k in range(n))
    faces.append(tuple(range(steps * n, (steps + 1) * n)))
    cuts = ()
    if rounding and rng.random() < .66:
        t = rng.choice((lo, hi))
        dr = rng.uniform(.11, .41)
        side = rng.choice((-1, 1))
        r, y = max(profile, key=lambda p: p[0] + .095 * p[1] * side)
        offset = -1 if t == lo else 1
        c, s = math.cos(t), math.sin(t)
        cuts = (((c * (r - dr), y, SPRING + s * (r - dr)),
                 (c - offset * s, side * rng.uniform(.44, .91), s + offset * c)),)
    obj = mesh(name, verts, faces, mat, cuts, rounding, curved=True)
    if rounding:
        obj.data.set_sharp_from_angle(angle=.26)
    elif not cuts:
        for face in obj.data.polygons[1:-1]:
            face.use_smooth = True


def arch(shades, mortar, rng):
    ring("Continuous mortar backing", -.004, math.pi + .004,
         [(INNER + .085, -3.35), (17.44, -3.35), (17.44, 3.35), (INNER + .085, 3.35)],
         mortar, 0, rng)
    profiles = (
        ("Through voussoir", [(INNER, -3.68), (INNER + .25, -3.93), (14.04, -3.93),
                              (14.16, -3.66), (14.16, 3.66), (14.04, 3.93),
                              (INNER + .25, 3.93), (INNER, 3.68)], 21, .098),
        ("Main archivolt", [(14.02, -3.88), (14.26, -4.38), (14.51, -4.61),
                            (16.39, -4.61), (16.65, -4.26), (16.65, 4.26),
                            (16.39, 4.61), (14.51, 4.61), (14.26, 4.38), (14.02, 3.88)], 19, .105),
        ("Drip mould", [(16.63, -4.04), (16.70, -4.39), (16.87, -4.69), (17.15, -4.80),
                        (17.36, -4.62), (17.55, -4.23), (17.61, -3.66), (17.61, 3.66),
                        (17.55, 4.23), (17.36, 4.62), (17.15, 4.80), (16.87, 4.69),
                        (16.70, 4.39), (16.63, 4.04)], 27, .056),
    )
    for order, profile, count, radius in profiles:
        # A continuous lime bed behind each face order closes the angular joints.
        inner, outer = min(r for r, _ in profile), max(r for r, _ in profile)
        mid = (inner+outer)*.5
        bed = [(mid+(r-mid)*.89,y*.946) for r,y in profile]
        ring(f"{order} recessed beds", 0, math.pi, bed, mortar, 0, rng)
        angles = [0] + [(i + rng.uniform(-.28, .28)) * math.pi / count for i in range(1, count)] + [math.pi]
        for i, (a, b) in enumerate(zip(angles, angles[1:])):
            front = rng.uniform(-.068, .049)
            key = i == count // 2 and order == "Main archivolt"
            stone = [(r + (max(0, r - 14.15) * .092 if key else 0),
                      y + math.copysign(front + (.28 if key else 0), y)) for r, y in profile]
            ring(f"{order} {i + 1:02}" if not key else "Crown keystone",
                 a + .0021, b - .0021, stone, rng.choice(shades), radius, rng)


def cushion(sign, shades, rng):
    n = 120
    profile = ((12.66,2.53,3.94,.27),(12.82,2.53,4.00,.26),
               (12.97,2.59,4.02,.24),(13.09,2.66,4.04,.22),
               (13.24,2.66,4.04,.22),(13.32,2.54,3.89,.37),
               (13.45,2.56,3.93,.38),(13.62,2.64,4.05,.36),
               (13.94,2.81,4.27,.30),(14.24,2.96,4.52,.23),
               (14.45,3.02,4.64,.19),(14.55,2.99,4.65,.19),
               (14.66,3.10,4.74,.16),(14.82,3.12,4.74,.15),
               (14.97,3.04,4.62,.16),(15.10,3.08,4.65,.15),
               (15.37,3.08,4.65,.15),(15.415,3.02,4.60,.16))
    phase = rng.uniform(0,math.tau)
    verts = []
    for z,a,b,exponent in profile:
        for j in range(n):
            angle = math.tau*j/n
            co, si = math.cos(angle), math.sin(angle)
            scale = 1 + .009*math.sin(11*angle+phase)*math.sin(z*1.3)
            verts.append((sign*(14.79+a*scale*math.copysign(abs(co)**exponent,co)),
                          b*scale*math.copysign(abs(si)**exponent,si), z))
    faces = [tuple(reversed(range(n)))]
    faces.extend((k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j)
                 for k in range(len(profile)-1) for j in range(n))
    end = n*(len(profile)-1)
    faces.append(tuple(range(end,end+n)))
    cuts = (((sign*17.69,-4.38,15.31),(sign*.68,-1,.42)),
            ((sign*12.02,4.35,14.96),(-sign*.85,1,.24)))
    obj = mesh("Chamfered cushion impost", verts, faces, rng.choice(shades[4:11]), cuts, .056, True)
    obj.data.set_sharp_from_angle(angle=.43)


def pier(sign, shades, mortar, foot, rng):
    def interval(a, b):
        return (a, b) if sign > 0 else (-b, -a)

    # The battered lower wall carries a coved square impost which meets all three orders.
    courses = [(-.052, .57, 11.62, 18.82, 4.98), (.57, 1.18, 11.77, 18.60, 4.80),
               (1.18, 1.71, 11.94, 18.36, 4.57), (1.71, 3.11, 12.18, 18.09, 4.29),
               (3.11, 4.67, 12.20, 17.96, 4.18), (4.67, 6.28, 12.20, 17.81, 4.10),
               (6.28, 7.98, 12.20, 17.67, 4.02), (7.98, 9.45, 12.20, 17.55, 3.97),
               (9.45, 11.22, 12.20, 17.44, 3.91), (11.22, 12.75, 12.20, 17.37, 3.89)]
    offsets = [0]*4+[rng.uniform(-.23,.23) for _ in range(len(courses)-4)]+[0]
    for i, (z0, z1, x0, x1, depth) in enumerate(courses):
        z0, z1 = z0 + offsets[i], z1 + offsets[i+1]
        a, b = interval(x0, x1)
        label = f"{'North' if sign > 0 else 'South'} pier bed {i + 1:02}"
        ashlar(label + " lime core", a + .15, b - .15, -depth + .14, depth - .14,
               z0, z1 + (.04 if i == len(courses) - 1 else .10), mortar, rng, 0)
        mid = (a + b) / 2
        ycut = rng.uniform(-.76, .76)
        for j, (f, g) in enumerate(((-depth, ycut - .022), (ycut + .022, depth))):
            cuts = [a, mid + (-1 if (i + j) % 2 else 1) * rng.uniform(.43, 1.10), b]
            for k, (lo, hi) in enumerate(zip(cuts, cuts[1:])):
                face_offset = rng.uniform(-.070, .059)
                early = i < 2 or (i == 2 and rng.random() < .60)
                stone = foot if early else rng.choice(shades)
                ashlar(f"{label} ashlar {j * 2 + k + 1}", lo + (.037 if k else 0),
                       hi - (.037 if not k else 0), f + face_offset, g + face_offset,
                       z0 + (.022 if i else 0), z1 - .022, stone, rng,
                       rng.uniform(.115,.185), shift=(rng.uniform(-.025,.025),rng.uniform(-.031,.031)),
                       pitch=(rng.uniform(-.008,.008),rng.uniform(-.008,.008)))
    cushion(sign, shades, rng)


def threshold_verge(rng):
    soil, grass = vrmat.get("forest_soil"), vrmat.get("grass_ground")
    for side in (-1,1):
        phase = rng.uniform(0,math.tau)
        verts = []
        n = 58
        for j in range(5):
            u = j/4
            for k in range(n):
                x = -13.6 + 27.2*k/(n-1)
                reach = (.55+.89*math.sin(math.pi*k/(n-1))**.8) * (1+.43*math.sin(x*.61+phase))
                y = side*(7.16 + reach*u + .11*math.sin(x*1.26+phase))
                z = .13*(1-u)**1.2*(1+.31*math.sin(x*.84+phase))-.034
                verts.append((x,y,z))
        faces = [(j*n+k,j*n+k+1,(j+1)*n+k+1,(j+1)*n+k)
                 for j in range(4) for k in range(n-1)]
        obj = mesh("Soil and turf feathering the paved approach", verts,
                   faces if side > 0 else [f[::-1] for f in faces], grass)
        obj.data.materials.append(soil)
        for poly in obj.data.polygons:
            poly.use_smooth = True
            poly.material_index = int(math.sin(poly.index*.18+phase) > .55)


def turf(sign, shades, rng):
    centre = sign * 15.8
    soil, grass = vrmat.get("forest_soil"), vrmat.get("grass_ground")
    mats = (soil, grass, vrmat.get("foliage_leaf"))
    n = 80
    coords = []
    for u in (.30, .57, .78, .92, 1):
        for j in range(n):
            t = j * math.tau / n
            wobble = 1 + .08 * math.sin(3 * t + sign) + .06 * math.cos(7 * t - sign)
            x = centre + 6.7 * u * wobble * math.cos(t)
            y = 8.2 * u * wobble * math.sin(t)
            h = .75 * (1 - u) ** 1.31 * (1 + .32 * math.sin(4 * t)) - .035
            coords.append((x, y, h))
    faces = [tuple(range(n))]
    faces.extend((n*i+j, n*(i+1)+j, n*(i+1)+(j+1)%n, n*i+(j+1)%n)
                 for i in range(4) for j in range(n))
    sod = mesh("Irregular soil and turf apron", coords, faces, grass)
    sod.data.materials.append(soil)
    for f in sod.data.polygons:
        f.use_smooth = True
        t = (f.index-1) * math.tau/n
        if math.sin(5*t+sign) + .57*math.sin(9*t-sign) > .93:
            f.material_index = 1
    leaves, blades = [], []
    clusters = [rng.uniform(0, math.tau) for _ in range(12)]
    moss = vrmat.get("mossy_rock")
    for i in range(138):
        t = rng.choice(clusters) + rng.uniform(-.19, .19)
        u = rng.uniform(.69, .88)
        wobble = 1 + .08 * math.sin(3 * t + sign) + .06 * math.cos(7 * t - sign)
        x = centre + 6.7 * u * wobble * math.cos(t)
        y = 8.2 * u * wobble * math.sin(t)
        if abs(x) < 12.1 or (abs(x - centre) < 3.32 and abs(y) < 4.9):
            continue
        z = .75 * (1 - u) ** 1.31 * (1 + .32 * math.sin(4 * t)) - .055
        if i % 3 == 0:
            s = rng.uniform(.17, .66)
            ashlar("Limestone scatter", x - s, x + s, y - .61*s, y + .56*s, max(z - .06, -.052),
                   z + s * .58, moss if i % 9 == 0 else rng.choice(shades), rng,
                   min(.17, .43*s), (.17*s, -.12*s))
        if i % 2 == 0 and abs(y) > 4.35:
            py = math.copysign(rng.uniform(4.62,4.99),y)
            s = rng.uniform(.14,.43)
            if abs(x-centre) < 2.95:
                ashlar("Moss cushions at damp plinth joint", x-s, x+s, py-.26, py+.26,
                       .42, .56+rng.uniform(.03,.14), moss, rng, .095)
        for _ in range(rng.randint(6, 13)):
            a = rng.uniform(0, math.tau)
            xx, yy = x + rng.uniform(-.19, .19), y + rng.uniform(-.19, .19)
            h, w = rng.uniform(.21, .59), rng.uniform(.025, .071)
            dx, dy = math.cos(a), math.sin(a)
            k = len(leaves)
            leaves.extend(((xx-w*dy, yy+w*dx, z), (xx+w*dy, yy-w*dx, z),
                           (xx + h*.19*dx, yy + h*.19*dy, z + h*.67),
                           (xx + h*.52*dx, yy + h*.52*dy, z + h)))
            blades.extend(((k,k+1,k+2),(k,k+2,k+3)))
    mesh("Clumps of ford sedge and grass", leaves, blades, mats[2])


def threshold(shades, mortar, rng):
    ys = [-7.38, -6.18, -4.72, -3.20, -1.49, .20, 1.66, 3.27, 4.83, 6.28, 7.41]
    for i, (front, back) in enumerate(zip(ys, ys[1:])):
        tier = min(i, len(ys) - i - 2, 3)
        h = .19 + .17 * tier
        ashlar("Rammed dirt beneath paving", -12.34, 12.34, front, back, -.054,
               h - .12, mortar, rng, 0)
        count = rng.choice((9,10,11))
        positions = [-12.58] + [-12.58 + j * 25.16/count + rng.uniform(-.65, .65)
                                for j in range(1,count)] + [12.58]
        for j, (left, right) in enumerate(zip(positions, positions[1:])):
            part = f"Threshold slab {i + 1}.{j + 1}"
            z = h + rng.uniform(-.030, .035)
            mat = rng.choice(shades)
            lo, hi = left + rng.uniform(.032,.048), right - rng.uniform(.030,.047)
            f, g = front + rng.uniform(.026,.052), back - rng.uniform(.026,.059)
            pitch = (rng.uniform(-.026,.026),rng.uniform(-.039,.039))
            if rng.random() < .24:
                x, y = rng.uniform(lo + .3, hi - .3), (f + g) * .5
                normal = Vector((1, rng.uniform(-.66, .66), .20)).normalized()
                point = Vector((x, y, z))
                for sign in (-1, 1):
                    ashlar(part + f" fracture {sign}", lo, hi, f, g, -.052, z, mat, rng, .084,
                           beds=((point - normal * sign * .019, normal * sign),), pitch=pitch)
            else:
                ashlar(part, lo, hi, f, g, -.052, z, mat, rng, rng.uniform(.094,.166), pitch=pitch)


def build():
    rng = random.Random(87013)
    shades, mortar, foot = finish()
    threshold(shades, mortar, rng)
    threshold_verge(rng)
    for side in (-1, 1):
        pier(side, shades, mortar, foot, rng)
        turf(side, shades, rng)
    arch(shades, mortar, rng)

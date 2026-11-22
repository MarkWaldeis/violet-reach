"""Floodmark Gate: raked limestone piers carrying an asymmetric round crown."""
import math
import random

import bpy
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat


def limestone(name):
    if name in ("mossy_rock", "dirt_path", "grass_ground"):
        return vrmat.get(name)
    local_name = f"gate_white_a.{name}"
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

    variation = noise(.37, 3)
    tone = ramp(variation, .23, .79, (cool, pale))
    random_tone = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(.18, tone, ramp(random_tone, 0, 1, (cool, pale)))
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    old = name == "monument_weathered"
    ao.inputs["Distance"].default_value = .42 if old else .14
    joint = tuple(.74*a+.26*b for a,b in zip(seam, cream))
    tone = mix(ao.outputs["AO"], joint, tone)
    if old:
        patina = palette["monument_shadow"]["linear_rgb"]
        weathered = tuple(.38*a+.62*b for a,b in zip(seam,patina))
        tone = mix(.77, tone, ramp(noise(1.24, 3), .42, .69, (weathered, pale)))
    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), .16, .86, ((.72,.72,.72),(.93,.93,.93))), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .023
    bump.inputs["Strength"].default_value = .42
    links.new(noise(10, 2), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return mat


def make_stone(name, vertices, faces, stone, smooth=()):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(stone))
    for i in smooth:
        mesh.polygons[i].use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(23))
    return obj


def ashlar(name, bottom, top, foot, head, depth, cut, wear, rng, stone, y=0):
    vertices = []
    lost_corner = int(abs(top * 27 + head[0] * 14)) % 8
    for i, (z, (left, right), scale) in enumerate(((bottom, foot, .995),
                                                   (bottom + wear * .7, foot, 1),
                                                   (top - wear, head, 1),
                                                   (top, head, .993))):
        half = depth / 2 * (1 - .02 * i)
        s = cut
        mid = (left + right) / 2
        outline = [(left + s, -half), (right - s, -half), (right, -half + s),
                   (right, half - s), (right - s, half), (left + s, half),
                   (left, half - s), (left, -half + s)]
        for j, (x, dy) in enumerate(outline):
            spall = .042 if i == 3 and j == lost_corner and bottom > .1 else 0
            x -= (x - mid) * spall
            dy *= 1 - spall
            vertices.append((mid + (x - mid) * scale + rng.uniform(-wear, wear) * .45,
                             y + dy * scale + rng.uniform(-wear, wear) * .55,
                             z - wear * 1.6 * bool(spall)
                             + (rng.uniform(-wear, wear) * .39 if i in (0, 3) and bottom > .1 else 0)))
    faces = [tuple(reversed(range(8)))]
    faces.extend((8 * i + j, 8 * i + (j + 1) % 8,
                  8 * (i + 1) + (j + 1) % 8, 8 * (i + 1) + j)
                 for i in range(3) for j in range(8))
    faces.extend(((24, 25, 26, 27), (24, 27, 28, 29), (24, 29, 30, 31)))
    obj = make_stone(name, vertices, faces, stone, range(1, 25))
    bevel = obj.modifiers.new("Stone arrises", "BEVEL")
    bevel.width, bevel.segments = min(wear * .29, .056), 2
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(22)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


SPRING = 18.05
HALF_SPAN = 11.60
APEX_RISE = 16.25
ARCH_FRONT = ((.04, -4.66), (.09, -5.05), (.33, -5.35), (.54, -5.35), (.65, -5.10),
              (.86, -5.10), (1.04, -5.53), (1.40, -5.55), (1.61, -5.26), (1.86, -4.90),
              (2.68, -4.90), (2.89, -5.33), (3.06, -5.55), (3.38, -5.56), (3.59, -5.23),
              (4.10, -4.97), (4.54, -4.47), (4.71, -3.97))
ARCH_SECTION = ARCH_FRONT + tuple((r, -y) for r, y in reversed(ARCH_FRONT))


def arch_stone(name, positions, section, rng, stone, flip, key=False, dressed=True):
    outline = []
    for (a,b),(c,d) in zip(section, section[1:]+section[:1]):
        count = max(1, math.ceil(math.hypot(c-a,d-b)/.30))
        outline.extend((a+(c-a)*j/count,b+(d-b)*j/count) for j in range(count))
    phase = rng.uniform(0,math.tau)
    vertices = []
    caps = ([],[])
    for i, (side,t) in enumerate(positions):
        u = i/(len(positions)-1)
        bed = min(u,1-u)
        theta = math.pi*t/2
        for radial, y in outline:
            lip = math.exp(-((y-4.95*math.cos(phase))/.42)**2) * max(0,1-bed*9)
            mottled = (.015*math.sin(y*2.1+phase)*math.sin(u*6)
                       +.007*math.cos(y*8.1-u*18)+.003*math.sin(y*15+5*u))
            if dressed:
                y -= .090*lip*math.tanh(3*y)
                y += math.copysign(1,y)*mottled*min(1,abs(y))
                radial *= 1-.009*math.sin(phase+10*u)*math.sin(math.pi*u)
            radial *= 1-.19*math.sin(theta)
            if key:
                radial += .84*(radial/4.71)*math.sin(theta)**5
                y *= 1.11
            x = side*(HALF_SPAN+radial)*math.cos(theta) + .24*math.sin(theta)**2
            z = SPRING+(APEX_RISE+radial)*math.sin(theta)
            vertices.append((x,y*(1-.08*t),z))
            if i in (0,len(positions)-1):
                caps[0 if i==0 else 1].append(Vector((radial,y)))
    n = len(outline)
    faces = []
    for i in range(len(positions)-1):
        for j in range(n):
            a,b = i*n+j, i*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
    smooth = range(len(faces))
    for end, points in enumerate(caps):
        _,_,triangles,original,_,_ = delaunay_2d_cdt(points,[],[tuple(range(n))],1,1e-8)
        start = (len(positions)-1)*n if end else 0
        for face in triangles:
            indices = [original[j][0] for j in face]
            a,b,c = (points[j] for j in indices)
            if ((b-a).cross(c-a) < 0) == bool(end):
                indices.reverse()
            faces.append(tuple(start+j for j in indices))
    obj = make_stone(name, vertices, [tuple(reversed(f)) for f in faces] if flip else faces,
                     stone, smooth)
    obj.data.set_sharp_from_angle(angle=math.radians(30))


def round_course(name, x, profile, rng, stone):
    n = 240
    phase = rng.uniform(0,math.tau)
    vertices = []
    for z, radius in profile:
        for j in range(n):
            a = math.tau*j/n
            chip = max(0,1-abs(math.remainder(a-phase,math.tau))/.14)
            chip *= max(0,1-min(z-profile[0][0],profile[-1][0]-z)/.29)
            r = radius-.23*chip + .034*math.sin(7*a+.47*z+phase)
            r += .018*math.cos(19*a-.52*z)+.006*math.sin(37*a+z)
            vertices.append((x+r*math.cos(a),r*math.sin(a),z))
    faces = [tuple(reversed(range(n)))]
    for i in range(len(profile)-1):
        for j in range(n):
            a,b=i*n+j,i*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
    faces.append(tuple(range(len(vertices)-n,len(vertices))))
    obj = make_stone(name, vertices, faces, stone, range(1,len(faces)-1))
    obj.data.set_sharp_from_angle(angle=math.radians(37))


def build():
    rng = random.Random(6327)
    white, old = "monument_white", "monument_weathered"
    ashlar("One solid passage floor and pier foundation", -.31, .39, (-24.1,24.1), (-23.9,23.9),
           16.6, 1.39, .092, rng, white)
    for sign, label in ((-1,"West"), (1,"East")):
        x = sign*17.41
        round_course(f"{label} buried circular plinth", x, [(-.29,7.3),(.34,7.43),(.72,7.43),
                     (1.02,7.18),(1.24,6.68),(1.53,6.63),(1.65,6.29)], rng, old)
        round_course(f"{label} torus at the foot", x, [(1.63,6.31),(1.74,6.49),(1.94,6.54),
                     (2.12,6.42),(2.23,6.05)], rng, white)
        levels = (2.22,5.78,8.09,11.25,14.96,16.73) if sign == -1 else (2.22,4.79,8.42,11.83,14.32,16.73)
        for i,(lo,hi) in enumerate(zip(levels,levels[1:])):
            r0,r1 = 5.96-.27*(lo-2.2)/15,5.96-.27*(hi-2.2)/15
            profile = [(lo+.012,r0-.035),(lo+.045,r0)]
            profile += [(lo+(hi-lo)*j/13,r0+(r1-r0)*j/13) for j in range(1,13)]
            profile += [(hi-.044,r1),(hi-.012,r1-.035)]
            round_course(f"{label} round pier drum {i+1}",x,profile,rng,white)
            if i:
                round_course(f"{label} pale recessed pier bedding {i}",x,[(lo-.031,r0-.093),
                             (lo+.031,r0-.093)],rng,white)
        round_course(f"{label} moulded round impost",x,[(16.69,5.66),(16.87,5.94),(17.09,5.96),
                     (17.31,6.23),(17.64,6.45),(17.95,6.52),(18.12,6.44)],rng,white)
        for j in range(6):
            angle = (math.pi*.11 + math.pi*.29*j)*sign
            px = x+7.23*math.cos(angle)
            py = 7.24*math.sin(angle)
            r = rng.uniform(.56,1.04)
            ashlar(f"{label} weather below round foot {j}",.31,rng.uniform(.45,.60),
                   (px-r,px+r),(px-r*.81,px+r*.89),r*1.13,r*.26,.027,rng,
                   "mossy_rock" if j%3 else "dirt_path", y=py)

    bed = ((.14,-4.40),(4.13,-4.11),(4.13,4.11),(.14,4.40))
    arch_stone("Recessed solid white limestone arch bedding",
               [(-1,j/90) for j in range(91)]+[(1,j/90) for j in range(89,-1,-1)],
               bed,rng,white,True,dressed=False)
    for side,label,cuts in ((-1,"West",(0,.142,.245,.375,.507,.622,.762,.876)),
                            (1,"East",(0,.121,.258,.354,.477,.612,.745,.876))):
        for i,(lo,hi) in enumerate(zip(cuts,cuts[1:])):
            lo,hi = lo+.0014,hi-.0014
            arch_stone(f"{label} round-arch voussoir {i+1}",[(side,lo+(hi-lo)*j/26) for j in range(27)],
                       ARCH_SECTION,rng,white,side==-1)
    crown=.878
    arch_stone("Projecting saddle keystone",[(-1,crown+(1-crown)*j/36) for j in range(37)]+
               [(1,crown+(1-crown)*j/36) for j in range(35,-1,-1)],ARCH_SECTION,rng,white,True,key=True)

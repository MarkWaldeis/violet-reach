"""Tidebone Crossing: two limestone vaults rising from fractured bedrock."""

import math
import random

import bmesh
import bpy
from mathutils import Vector

import vrlib
import vrmat


def mesh(name, vertices, faces, mat, solid=True, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    data.update()
    if solid:
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    data.materials.append(mat)
    for poly in data.polygons:
        poly.use_smooth = smooth
    return obj


def loft(name, rings, mat, smooth=True):
    n = len(rings[0])
    faces = [tuple(reversed(range(n)))]
    for i in range(len(rings) - 1):
        a, b = i*n, (i+1)*n
        faces.extend((a+j, a+(j+1)%n, b+(j+1)%n, b+j) for j in range(n))
    end = (len(rings)-1)*n
    faces.append(tuple(range(end, end+n)))
    obj = mesh(name, [p for ring in rings for p in ring], faces, mat, smooth=smooth)
    obj.data.polygons[0].use_smooth = obj.data.polygons[-1].use_smooth = False
    return obj


def pale_stone(name, i, root=False):
    mat = vrmat.get("monument_white").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    source = bsdf.inputs["Base Color"].links[0].from_socket
    base = vrmat.load_palette()["monument_white"]["linear_rgb"]
    hue = math.sin(i * 2.12)
    tone = (.81 if root else .92) + .017 * (i % 9)
    tint = tuple(v * tone * s for v, s in zip(base, (1+.041*hue, 1-.010*hue, 1-.067*hue)))
    mix = nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = .56 if root else .76
    mix.inputs[2].default_value = (*tint, 1)
    links.new(source, mix.inputs[1])
    links.new(mix.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Specular IOR Level"].default_value = .24
    return mat


def bedding():
    mat = vrmat.get("monument_weathered").copy()
    mat.name = "Silt in recessed joints"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    old = surface.inputs["Base Color"].links[0].from_socket
    node = nodes.new("ShaderNodeMixRGB")
    node.blend_type = "MULTIPLY"
    node.inputs[0].default_value = 1
    node.inputs[2].default_value = (.65, .60, .50, 1)
    links.new(old, node.inputs[1])
    links.new(node.outputs[0], surface.inputs["Base Color"])
    return mat


def path(*points):
    controls = [Vector(p) for p in points]

    def sample(t):
        i = min(math.floor(t * (len(controls) - 1) / 3), (len(controls) - 4) // 3)
        t = t * (len(controls) - 1) / 3 - i
        a, b, c, d = controls[3*i:3*i+4]
        u = 1-t
        position = u**3*a + 3*u*u*t*b + 3*u*t*t*c + t**3*d
        tangent = ((b-a)*u*u + (c-b)*2*u*t + (d-c)*t*t).normalized()
        return position, tangent

    return sample


def smoothstep(t):
    t = max(0, min(1, t))
    return t*t*(3-2*t)


def vault(name, spine, width, depth, stones, mortar, rng, free=False):
    stations = [0, .079, .165, .251, .343, .435, .532, .647, .769, .878, .945, 1]
    stations = [v + rng.uniform(-.020, .020) if i not in (0, len(stations)-1) else v
                for i, v in enumerate(stations)]
    across = Vector((0, 1, 0)) if name != "Tributary vault" else Vector((-.91, .415, 0))
    twist = rng.uniform(0, math.tau)
    n = 112

    def section(t, inset, wear, phase=0):
        centre, tangent = spine(t)
        normal = tangent.cross(across).normalized()
        side = normal.cross(tangent).normalized()
        flare = (1-smoothstep(t/.22)) + ((smoothstep((t-.78)/.22)) if not free else 0)
        taper = (1 - .30*t) if free else (1 - .25*math.sin(math.pi*t)**2)
        end = math.sqrt(max(.000004, 1-smoothstep((t-.87)/.13)**2)) if free else 1
        a = (width*taper + flare*.94) * end
        b = (depth*taper + flare*.69) * end
        curve = .076 * math.sin(math.pi*t) * math.sin(twist + math.tau*t)
        ring = []
        for j in range(n):
            angle = j*math.tau/n
            k = angle + curve
            outer, lateral = math.cos(k), math.sin(k)
            # Long flutes following the same angular phase through every bed.
            flute = sum(math.exp(-(math.remainder(k-c, math.tau)/s)**2)
                        for c, s in ((.92,.18), (1.48,.21), (2.26,.19), (3.96,.18), (4.95,.23), (5.51,.17)))
            shape = 1 + .082*math.cos(3*k+.33) + .057*math.cos(5*k-.35) - .146*flute
            grain = wear * (math.sin(4*k+phase)*math.cos(2*k-phase) + .41*math.sin(11*k+phase))
            nr = math.copysign(abs(outer)**.82, outer) * a
            sr = math.copysign(abs(lateral)**.86, lateral) * b
            ring.append(centre + (normal*nr + side*sr)*(shape-inset+grain))
        return ring

    for i, (lo, hi) in enumerate(zip(stations, stations[1:])):
        phase = rng.uniform(0, math.tau)
        gap = .00024 if not free else .00041
        a, b = lo + (gap if i else 0), hi - (gap if hi < 1 else 0)
        steps = max(8, math.ceil((b-a)*315))
        rings = []
        for j in range(steps+1):
            u = j / steps
            t = a + (b-a)*u
            rounded = .0030 * (1 - smoothstep(min(u,1-u)*51))
            local_wear = .0048 * math.sin(math.pi*u)**2
            rings.append(section(t, rounded, local_wear, phase))
        obj = loft(f"{name} | bed {i+1:02}", rings, rng.choice(stones))
        if i in (0, 1, 8) or (free and i == 10):
            u = rng.uniform(.10,.78)
            t = a + (b-a)*u
            middle, tangent = spine(t)
            az = rng.choice((17,37,66,91)) + rng.randint(-4,4)
            edge = section(t, 0, 0)[az]
            normal = (edge - middle).normalized()
            centre = edge - normal * rng.uniform(.09,.27)
            spall(obj, centre, normal, tangent, rng)
        if hi < 1:
            loft(f"{name} | recessed lime bed {i+1:02}",
                 [section(hi + k*gap, .014, 0) for k in (-1.5, -.7, 0, .7, 1.5)], mortar)


def rock_ring(x, y, ax, ay, z, fac, phase, bedding_offset=0):
    ring = []
    for j in range(104):
        a = math.tau * j / 104
        zlayer = .18 * math.sin(a*2+phase) + .26 * math.cos(a*3-phase)
        cliff = .058 * math.cos(5*a+phase) + .028 * math.sin(11*a-phase)
        cleft = sum(d * math.exp(-(math.remainder(a-c, math.tau)/w)**2)
                    for c, d, w in ((phase,.115,.095),(phase+2.6,.17,.12),(phase-1.8,.14,.076)))
        stratified = .033 * math.sin(13*a + z*.76) + .022 * math.cos(19*a - z*1.4)
        scale = fac * (1 + cliff - cleft + stratified)
        ring.append((x + ax*scale*math.cos(a), y + ay*scale*math.sin(a),
                     max(-.054, z + bedding_offset + zlayer*smoothstep((z-.1)/1.9))))
    return ring


def cut_plane(obj, point, normal):
    x, y, z = point
    nx, ny, nz = normal
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    cut = bmesh.ops.bisect_plane(
        bm, geom=[*bm.verts, *bm.edges, *bm.faces], dist=1e-5,
        plane_co=(-y, x, z), plane_no=(-ny, nx, nz), clear_outer=True,
    )
    rim = [edge for edge in cut["geom_cut"]
           if isinstance(edge, bmesh.types.BMEdge) and edge.is_valid and edge.is_boundary]
    for face in bmesh.ops.holes_fill(bm, edges=rim)["faces"]:
        face.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()


def spall(obj, centre, normal, tangent, rng):
    lateral = tangent.cross(normal).normalized()
    rings = []
    for length, radius, depth in ((-.71,.18,.06),(-.35,.84,-.09),
                                  (.18,1,-.16),(.62,.42,.04),(.81,.11,.12)):
        row = []
        for i in range(9):
            a = i*math.tau/9
            row.append(centre + tangent*length +
                       lateral*(.44*radius*math.cos(a)) +
                       normal*(depth + .49*radius*math.sin(a) + rng.uniform(-.034,.034)))
        rings.append(row)
    cutter = loft("Temporary spall tool", rings, vrmat.get("forest_soil"), smooth=False)
    carve(obj, cutter)
    bpy.data.objects.remove(cutter, do_unlink=True)
    obj.data.set_sharp_from_angle(angle=.63)


def through_passage(x, y):
    shape = [(x-1.79,-.058), (x+1.79,-.058), (x+1.79,2.21)]
    shape.extend((x + 1.79*math.cos(t*math.pi/48), 2.21+1.79*math.sin(t*math.pi/48))
                 for t in range(1,49))
    return loft("Temporary tunnel tool", [[(px, y+d, z) for px, z in shape] for d in (-20,20)],
                vrmat.get("forest_soil"), smooth=False)


def carve(obj, cutter):
    mod = obj.modifiers.new("Carved passage", "BOOLEAN")
    mod.object, mod.operation, mod.solver = cutter, "DIFFERENCE", "EXACT"
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def outcrop(name, x, y, ax, ay, h, stones, mortar, rng, tunnel=False, lean=(1, 0)):
    phase = rng.uniform(0, math.tau)
    zlevels = [0, .065, .159, .226, .341, .481, .556, .713, .851, 1]
    steps = [h*v + (rng.uniform(-.34, .34) if 0 < i < len(zlevels)-1 else -.054 if not i else 0)
             for i, v in enumerate(zlevels)]
    cutter = through_passage(x-.5, y) if tunnel else None
    for i, (low, high) in enumerate(zip(steps, steps[1:])):
        flake = rng.uniform(.012, .061)
        forming = rng.uniform(.96, 1.045)

        def section(z, f, scale=forming):
            u = max(0, z/h)
            fac = (1 - .65*u**.79) * scale * f
            return rock_ring(x + lean[0]*u, y + lean[1]*u, ax, ay, z, fac, phase)

        if i:
            bed = loft(f"{name} | silty bedding {i:02}",
                       [section(low + d, .885, 1) for d in (-.19,-.05,.05,.16)], mortar)
            if cutter and low < 4.35:
                carve(bed, cutter)
        layers = ((0,.955),(.052,1),(.17,1+flake),(.32,1.025),(.58,1.01),
                  (.77,.987),(.94,.968),(1,.935))
        rings = [section((low+.023 if i else low) + (high-low-.048)*t, f) for t, f in layers]
        mat = vrmat.get("monument_weathered") if i < 2 else rng.choice(stones)
        stone = loft(f"{name} | broken limestone bank {i+1:02}", rings, mat)
        if i < len(steps)-2:
            a = phase + rng.uniform(-math.pi, math.pi)
            z = low + (high-low)*.63
            u = max(0, z/h)
            fac = (1 - .65*u**.79) * forming * rng.uniform(.81,.89)
            cut_plane(stone, (x+lean[0]*u+ax*fac*math.cos(a), y+lean[1]*u+ay*fac*math.sin(a), z),
                      (math.cos(a), math.sin(a), rng.uniform(.25,.80)))
        if cutter and low < 4.35:
            carve(stone, cutter)
        stone.data.set_sharp_from_angle(angle=.59)
        bevel = stone.modifiers.new("Softened exposed fractures", "BEVEL")
        bevel.width, bevel.segments, bevel.angle_limit = .065, 3, .39
    if cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)


def scree(name, x, y, z, size, stone, rng):
    n = rng.randint(6, 9)
    phase = rng.uniform(0, math.tau)
    spread = [rng.uniform(.71, 1.22) for _ in range(n)]
    rings = []
    for h, radius, skew in ((-.27,.69,0), (.03,1,.05), (.39,.79,.13), (.67,.44,.19)):
        ring = []
        for i in range(n):
            a = phase + i*math.tau/n
            ring.append((x+size*(spread[i]*radius*math.cos(a)+skew),
                         y+size*(.77*spread[i]*radius*math.sin(a)-skew*.41),
                         max(-.052, z+size*(h+rng.uniform(-.079,.079)))))
        rings.append(ring)
    obj = loft(name, rings, stone, smooth=False)
    bevel = obj.modifiers.new("Worn fracture edges", "BEVEL")
    bevel.width, bevel.segments = size*.037, 2
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=bevel.name)
    lift = max(0, -.055 - min(v.co.z for v in obj.data.vertices))
    if lift:
        for vertex in obj.data.vertices:
            vertex.co.z += lift


def apron(x, y, ax, ay, stones, rng, tunnel=False):
    phase = rng.uniform(0, math.tau)
    n = 98

    def surface(u, a):
        edge = 1 + .088*math.sin(3*a+phase) + .043*math.cos(7*a-phase)
        raise_by = (.95 + .25 * math.sin(4*a+phase))*(1-u)**1.33
        px = x+ax*edge*u*math.cos(a)
        if tunnel:
            raise_by *= .055 + .945*smoothstep((abs(px-(x-.5))-1.63)/1.1)
        return (px, y+ay*edge*u*math.sin(a), raise_by-.033)

    stations = (.04,.12,.20,.30,.41,.52,.63,.73,.83,.92,1) if tunnel else (.36,.58,.70,.82,.91,1)
    rings = [[surface(u,j*math.tau/n) for j in range(n)] for u in stations]
    faces = [tuple(range(n))]
    faces.extend((i*n+j, (i+1)*n+j, (i+1)*n+(j+1)%n, i*n+(j+1)%n)
                 for i in range(len(rings)-1) for j in range(n))
    soil, grass = vrmat.get("forest_soil"), vrmat.get("grass_ground")
    ground = mesh("Irregular root soil and turf", [p for row in rings for p in row], faces, grass,
                  solid=False, smooth=True)
    ground.data.materials.append(soil)
    for poly in ground.data.polygons:
        a = (poly.index-1)*math.tau/n
        if poly.index == 0 or math.sin(5*a+phase)+.63*math.cos(9*a-phase) > 1:
            poly.material_index = 1
    blades, faces = [], []
    for _ in range(13):
        a0, u0 = rng.uniform(0,math.tau), rng.uniform(.65,.89)
        for i in range(rng.randint(9, 18)):
            a, u = a0 + rng.uniform(-.16,.16), min(.96, u0 + rng.uniform(-.10,.10))
            px, py, pz = surface(u, a)
            if tunnel and abs(px-(x-.5)) < 2.03:
                continue
            if i % 4 == 0:
                scree("Weathered foot rubble", px, py, pz-.026, rng.uniform(.22,.93),
                      rng.choice(stones) if i%8 else vrmat.get("monument_weathered"), rng)
            for _ in range(rng.randint(4, 10)):
                xx, yy = px + rng.uniform(-.22,.22), py + rng.uniform(-.22,.22)
                h, w, ta = rng.uniform(.14,.58), rng.uniform(.02,.077), rng.uniform(0, math.tau)
                dx, dy = math.cos(ta), math.sin(ta)
                start = len(blades)
                base = max(-.054,pz-.052)
                blades.extend(((xx-w*dy,yy+w*dx,base),(xx+w*dy,yy-w*dx,base),
                               (xx+.23*h*dx,yy+.23*h*dy,pz+.61*h),
                               (xx+.47*h*dx,yy+.47*h*dy,pz+h)))
                faces.extend(((start,start+1,start+2),(start,start+2,start+3)))
    mesh("Clumped grass among limestone scree", blades, faces, vrmat.get("foliage_leaf"), solid=False)


def passage_floor(x, y, stones, rng):
    for i in range(23):
        py = y + (i-11)*1.22
        for j in range(3):
            px = x + (j-1)*1.02 + rng.uniform(-.085,.085)
            z = .094 + .37 * max(0, 1-(abs(i-11)/12)**3)
            outline = [(-.49,-.51),(-.36,-.58),(.42,-.58),(.49,-.37),
                       (.45,.56),(-.33,.57),(-.49,.44)]
            skew = rng.uniform(-.17,.17)
            loft("Worn passage paving",
                 [[(px + dx + dy*skew, py + dy, zz + (rng.uniform(-.031,.031) if zz > 0 else 0))
                   for dx, dy in outline] for zz in (-.049,z-.047,z)],
                 rng.choice(stones), smooth=False)


def passage_lining(x, y, stones, mortar, rng):
    def shell(name, front, back, inner, outer, mat, gap=0):
        def section(r, a, py):
            return x+r*math.cos(a), py, 2.21+r*math.sin(a)

        for i, side in enumerate((-1,1)):
            side_profile = [(x+side*r, z) for r,z in
                            ((inner,-.054),(outer,-.054),(outer,2.21),(inner,2.21))]
            loft(f"{name} jamb {i+1}",
                 [[(px, py, z) for px,z in side_profile] for py in (front,back)], mat, smooth=False)
        if gap:
            angles = [0] + [(j+rng.uniform(-.16,.16))*math.pi/11 for j in range(1,11)] + [math.pi]
        else:
            angles = [0,math.pi]
        for i,(a,b) in enumerate(zip(angles,angles[1:])):
            n = max(6, math.ceil((b-a)*34))
            profile = ((inner,front),(outer,front),(outer,back),(inner,back))
            obj = loft(f"{name} arch stone {i+1}",
                       [[section(r,a+gap+(b-a-2*gap)*j/n,py) for r,py in profile]
                        for j in range(n+1)], rng.choice(stones) if gap else mat)
            obj.data.set_sharp_from_angle(angle=.34)
            if gap:
                bevel = obj.modifiers.new("Eroded passage arrises", "BEVEL")
                bevel.width, bevel.segments, bevel.angle_limit = .045, 3, .25

    for i in range(14):
        front = y-10.77+i*1.55
        back = front+1.55
        shell("Lining bed", front, back, 1.624, 2.02, mortar)
        shell(f"Limestone lining bay {i+1:02}", front+.018, back-.018, 1.57, 1.99, rng.choice(stones), .006)


def build():
    rng = random.Random(410903)
    stone = [pale_stone(f"Rib limestone | bed {i:02}", i) for i in range(13)]
    root = [pale_stone(f"Root limestone | layer {i:02}", i+3, root=True) for i in range(11)]
    mortar = bedding()
    main = path((-44,-8,3.0),(-43,-11,48),(-25,-13,77.4),
                (1,-8,77.5),(27,-3,77.6),(52,-5,49),(44,-5,3.0))
    branch = path((-22,-41,2.8),(-29,-37,35),(-15,-19,60.5),
                  (-4,4,63),(7,27,65.5),(11,43,36),(19,47,2.8))
    relic = path((47,2.0,3.1),(58,1.5,22),(52,13,38),(35,17,46))
    vault("High tide vault", main, 3.25, 2.63, stone, mortar, rng)
    vault("Tributary vault", branch, 2.6, 2.14, stone, mortar, rng)
    vault("Broken seaward rib", relic, 2.65, 2.11, stone, mortar, rng, free=True)
    for name,x,y,ax,ay,h,tunnel,lean in (
        ("Inner headland",-44,-8,10.6,10.3,16.8,False,(2,-1)),
        ("Passage bedrock",45,-2,12.9,11.7,18.7,True,(2,-.8)),
        ("Upstream root",-22,-41,8.0,8.6,12.2,False,(-1.5,1.4)),
        ("Downstream root",19,47,8.8,9.5,14.6,False,(-1.9,-1.8)),
        ("Seaward root",50,4,7.8,8.3,12.7,False,(3,0)),
    ):
        outcrop(name, x, y, ax, ay, h, root, mortar, rng, tunnel, lean)
        apron(x, y, ax*1.29, ay*1.34, root, rng, tunnel)
        if tunnel:
            passage_lining(x-.50, y, root, mortar, rng)
            passage_floor(x-.50, y, root, rng)

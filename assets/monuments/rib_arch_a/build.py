"""Tidebone Crossing: the eroded remains of a limestone ribcage."""

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

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


def pale_stone(name, i):
    mat = vrmat.get("monument_white").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    source = bsdf.inputs["Base Color"].links[0].from_socket
    base = vrmat.load_palette()["monument_white"]["linear_rgb"]
    hue = math.sin(i * 2.12)
    tone = .70 + .033 * (i % 11)
    tint = tuple(v * tone * s for v, s in zip(base, (1+.052*hue, 1-.015*hue, 1-.087*hue)))
    mix = nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = .76
    mix.inputs[2].default_value = (*tint, 1)
    links.new(source, mix.inputs[1])
    dirt = nodes.new("ShaderNodeAttribute")
    dirt.attribute_name = "Runnel"
    mineral = nodes.new("ShaderNodeMixRGB")
    links.new(dirt.outputs["Fac"], mineral.inputs[0])
    links.new(mix.outputs[0], mineral.inputs[1])
    mud = vrmat.load_palette()["stone_weathered"]["linear_rgb"]
    mineral.inputs[2].default_value = (*(v*.38 for v in mud), 1)
    links.new(mineral.outputs[0], bsdf.inputs["Base Color"])
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


def vault(name, spine, width, depth, stones, mortar, rng, broken, tunnel_at=None):
    stations = [0, .30+rng.uniform(-.036,.036), .55+rng.uniform(-.043,.043),
                .76+rng.uniform(-.033,.033), 1]
    phase = rng.uniform(0, math.tau)
    n = 144
    flutes = [(math.tau*j/9+rng.uniform(-.18,.18), rng.uniform(.065,.208),
               rng.uniform(.11,.35), rng.uniform(0, math.tau)) for j in range(9)]
    scars = [(rng.uniform(lo+.018,hi-.018), math.tau*j/4+rng.uniform(-.34,.34),
              rng.uniform(.012,.022), rng.uniform(.12,.23), rng.uniform(.095,.18), j%3==0)
             for lo,hi in zip(stations,stations[1:]) for j in range(4)]
    shelves = [(rng.uniform(.014,.22), rng.uniform(0, math.tau), rng.uniform(.19,.53),
                rng.uniform(-.15,.15), rng.uniform(.05,.14)) for _ in range(16)]

    def section(t, inset=0):
        centre, tangent = spine(t)
        normal = tangent.cross(Vector((0,1,0))).normalized()
        side = normal.cross(tangent).normalized()
        foot = math.exp(-t/.091)
        a = width*(1-.65*t)**1.10 + width*.92*foot
        b = depth*(1-.54*t)**1.08 + depth*(1.02+.34*math.sin(phase))*foot
        tip = math.sqrt(max(.00035, 1-smoothstep((t-.909)/.091)**2)) if not broken else 1
        ring, stain = [], []
        for j in range(n):
            k = math.tau*j/n + .12*math.sin(phase+3*t)
            channel, dirt = 0, 0
            for c, w, amount, seed in flutes:
                axis = c + .063*math.sin(12*t+seed) + .042*math.sin(27*t+seed)
                g = math.exp(-(math.remainder(k-axis,math.tau)/w)**2)
                flow = .44 + .56*math.sin(8*t+seed)**2
                channel += g*amount*(.61+.39*foot)*flow
                wet = (.39+.61*math.sin(11*t+seed)**4) * (.40 + .60*foot)
                dirt = max(dirt, g**2 * wet * (2.5*amount))
            for z, c, length, breadth, amount, crack in scars:
                u = (t-z)/length
                if abs(u) > 1.2:
                    continue
                drift = (.067*math.sin(4*u) if crack else .052*u)
                v = math.remainder(k-c-drift,math.tau)/(breadth*(.47 if crack else 1))
                erosion = max(0, 1-u*u-v*v)**1.4
                channel += erosion*amount*(1.22 if crack else 1)
                dirt = max(dirt, erosion*.54)
            for z, c, breadth, slope, drop in shelves:
                v = math.remainder(k-c, math.tau)/breadth
                u = t-z-slope*v*breadth
                if abs(v) < 1 and -.012 < u < .036:
                    shelf = (1-v*v)**1.7*smoothstep((u+.012)/.013)*(1-smoothstep(u/.036))
                    channel += drop*shelf
                    dirt = max(dirt, shelf*.49)
            buttress = foot*(.16*math.cos(3*k+phase)+.16*math.cos(5*k-phase))
            foliation = (.025+.025*foot)*math.sin(9*k+31*t+phase)+.023*math.sin(17*k-66*t)
            foliation += (.012+.019*foot)*math.sin(27*k+77*t+phase)*math.sin(19*t+3*k)
            gully = .058 * math.sin(3*k+phase) * math.cos(34*t+1.9*math.sin(k))
            scale = (1 + buttress + .104*math.cos(3*k-.7) + foliation + gully - channel - inset)*tip
            nr = math.copysign(abs(math.cos(k))**.80, math.cos(k)) * a
            sr = math.copysign(abs(math.sin(k))**.87, math.sin(k)) * b
            point = centre + scale*(normal*nr + side*sr)
            point.z = max(-.054, point.z)
            ring.append(point)
            stain.append(min(.72, dirt + .42*foot**2*max(0,math.sin(7*k+phase))))
        return ring, stain

    cutter = through_passage(*tunnel_at) if tunnel_at else None
    for i, (lo, hi) in enumerate(zip(stations, stations[1:])):
        a, b = lo + (.00048 if i else 0), hi - (.00048 if hi < 1 else 0)
        steps = math.ceil(238*(b-a))
        samples = [section(a+(b-a)*j/steps, .004*(1-smoothstep(min(j,steps-j)/1.4)))
                   for j in range(steps+1)]
        obj = loft(f"{name} | limestone reach {i+1}", [ring for ring, _ in samples],
                   stones[(rng.randrange(len(stones)) + 3*i) % len(stones)])
        attribute = obj.data.attributes.new("Runnel", "FLOAT", "POINT")
        attribute.data.foreach_set("value", [m for _, masks in samples for m in masks])
        if cutter and not i:
            carve(obj, cutter)
        if broken and hi == 1:
            p, tangent = spine(.992)
            edge, _ = section(.977)
            across = (edge[23]-p).normalized()
            cut_plane(obj, p, tangent + across*rng.uniform(.58,.92))
            bevel = obj.modifiers.new("Rounded broken crest", "BEVEL")
            bevel.width, bevel.segments, bevel.angle_limit = .10, 3, .56
        if hi < 1:
            loft(f"{name} | recessed bed {i+1}",
                 [section(hi+d,.016)[0] for d in (-.00078,0,.00078)], mortar)
    if cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)


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


def through_passage(x, y):
    shape = [(x-1.79,-.058), (x+1.79,-.058), (x+1.79,2.21)]
    shape.extend((x + 1.79*math.cos(t*math.pi/48), 2.21+1.79*math.sin(t*math.pi/48))
                 for t in range(1,49))
    return loft("Temporary tunnel tool", [[(px, y+d, z) for px, z in shape] for d in (-20,20)],
                vrmat.get("forest_soil"), smooth=False)


def carve(obj, cutter):
    mod = obj.modifiers.new("Erosion cut", "BOOLEAN")
    mod.object, mod.operation, mod.solver = cutter, "DIFFERENCE", "EXACT"
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=mod.name)


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
        raise_by = (1.65 + .65 * math.sin(4*a+phase))*(1-u)**1.25
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
        row,j = divmod(poly.index-1,n)
        a = j*math.tau/n
        if poly.index == 0 or math.sin(5*a+phase+.84*row)+.72*math.cos(9*a-phase-.39*row) > 1:
            poly.material_index = 1
    blades, faces = [], []
    for _ in range(18):
        a0, u0 = rng.uniform(0,math.tau), rng.uniform(.65,.89)
        for i in range(rng.randint(9, 18)):
            a, u = a0 + rng.uniform(-.16,.16), min(.96, u0 + rng.uniform(-.10,.10))
            px, py, pz = surface(u, a)
            if tunnel and abs(px-(x-.5)) < 2.03:
                continue
            if i % 4 == 0:
                scree("Weathered foot rubble", px, py, pz-.026, rng.uniform(.32,1.55),
                      rng.choice(stones) if i%8 else vrmat.get("monument_weathered"), rng)
            for _ in range(rng.randint(4, 10)):
                xx, yy = px + rng.uniform(-.22,.22), py + rng.uniform(-.22,.22)
                h, w, ta = rng.uniform(.23,.72), rng.uniform(.029,.087), rng.uniform(0, math.tau)
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

    for i in range(9):
        front = y-7.07+i*1.55
        back = front+1.55
        shell("Lining bed", front, back, 1.624, 2.02, mortar)
        shell(f"Limestone lining bay {i+1:02}", front+.018, back-.018, 1.57, 1.99, rng.choice(stones), .006)


def build():
    stone = [pale_stone(f"Rib limestone | bed {i:02}", i) for i in range(13)]
    mortar = bedding()
    for i,(row,height,reach,broken) in enumerate((
        (-45,48,18,True),(-27,65,36,False),(-9,78,47,False),
        (9,79,51,False),(27,70,43,False),(45,49,25,True),
    )):
        rng = random.Random(410903 + 209*i)
        x = -21 + rng.uniform(-4.1,4.1)
        y = row + rng.uniform(-1.7,1.7)
        drift = rng.uniform(-7.5,7.5)
        width, depth = rng.uniform(3.75,5.1), rng.uniform(2.65,3.37)
        crest = x+reach
        spine = path((x,y,-.054),(x,y,height*.62),
                     (crest-reach*rng.uniform(.48,.65), y+drift*.26, height),
                     (crest,y+drift,height*(.92 if broken else .991)))
        tunnel = (x-.5,y) if i == 0 else None
        vault(f"Rib {i+1:02}", spine, width, depth, stone, mortar, rng, broken, tunnel)
        apron(x, y, width*2.88, depth*3.65, stone, rng, bool(tunnel))
        if tunnel:
            passage_lining(*tunnel, stone, mortar, rng)
            passage_floor(*tunnel, stone, rng)
    rotation = Matrix.Rotation(math.radians(-36), 3, "Z")
    for obj in vrlib.source_objects():
        obj.data.transform(rotation.to_4x4())

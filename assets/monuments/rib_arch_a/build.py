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
    old_mix = nodes.new("ShaderNodeMixRGB")
    old_mix.blend_type = "MULTIPLY"
    old_mix.inputs[0].default_value = .42
    hue = math.sin(i*2.12)
    old_mix.inputs[2].default_value = (.92+.07*hue, .94, .97-.09*hue, 1)
    links.new(source, old_mix.inputs[1])
    tone = nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "Stone bed"
    beds = nodes.new("ShaderNodeMixRGB")
    beds.blend_type = "MULTIPLY"
    links.new(tone.outputs["Fac"], beds.inputs[0])
    links.new(old_mix.outputs[0], beds.inputs[1])
    beds.inputs[2].default_value = (.77, .79, .82, 1)
    dirt = nodes.new("ShaderNodeAttribute")
    dirt.attribute_name = "Runnel"
    mineral = nodes.new("ShaderNodeMixRGB")
    mineral.blend_type = "MULTIPLY"
    links.new(dirt.outputs["Fac"], mineral.inputs[0])
    links.new(beds.outputs[0], mineral.inputs[1])
    mineral.inputs[2].default_value = (.33, .37, .26, 1)
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


def vault(name, spine, width, depth, mat, rng, tunnel_at=None):
    phase = rng.uniform(0, math.tau)
    n, steps = 112, 300
    flutes = [(math.tau*j/9+rng.uniform(-.17,.17), rng.uniform(.08,.27),
               rng.uniform(.032,.116), rng.uniform(0,math.tau)) for j in range(9)]
    gouges = [(rng.uniform(.04,.96), rng.uniform(0,math.tau), rng.uniform(.009,.035),
               rng.uniform(.11,.42), rng.uniform(.045,.22), rng.uniform(-5,5)) for _ in range(72)]
    rings, soil, beds = [], [], []
    for i in range(steps+1):
        t = i/steps
        centre, tangent = spine(t)
        normal = tangent.cross(Vector((0,1,0))).normalized()
        side = normal.cross(tangent).normalized()
        rise = math.sin(math.pi*t)**.72
        foot = (1-rise)**2
        a = width*(1-.55*rise)* (1+.10*math.sin(phase+5*t))
        b = depth*(1-.43*rise)* (1+.12*math.cos(phase-3*t))
        row = []
        local_gouges = [(p,k,l,w,d,g) for p,k,l,w,d,g in gouges if abs(p-t) < l]
        for j in range(n):
            k = math.tau*j/n + .10*math.sin(phase+7*t)
            channel, stain = 0, 0
            for angle, span, amount, seed in flutes:
                v = math.remainder(k-angle-.10*math.sin(14*t+seed),math.tau)/span
                runnel = math.exp(-v*v)*(.5+.5*math.sin(t*17+seed)**2)
                channel += amount*runnel
                stain = max(stain, .22*runnel*(.45+.55*foot))
            for p, angle, length, breadth, depth_cut, slant in local_gouges:
                u = (t-p)/length
                v = math.remainder(k-angle-slant*(t-p)-.035*math.sin(8*u),math.tau)/breadth
                chip = max(0, 1-abs(u)**1.3-abs(v)**1.8)
                channel += depth_cut*chip
                stain = max(stain, chip*.24)
            rocking = .054*math.sin(3*k+phase+6*t)+.033*math.sin(7*k-10*t+phase)
            edge = .021*math.sin(13*k+46*t)*math.sin(9*k+17*t)+.013*math.cos(23*k-64*t+phase)
            co, si = math.cos(k), math.sin(k)
            pt = centre + (1+rocking+edge-channel)*(
                normal*(a*math.copysign(abs(co)**.81,co)) +
                side*(b*math.copysign(abs(si)**.86,si)))
            pt.z = max(-.052,pt.z)
            row.append(pt)
            soil.append(min(.75, stain + foot*(.37+.17*math.sin(5*k+phase+6*t))))
            beds.append(.48+.26*math.sin(21*t+2*k+phase)+.18*math.cos(9*t-3*k))
        rings.append(row)
    obj = loft(name, rings, mat)
    for attr, values in (("Runnel",soil), ("Stone bed",beds)):
        data = obj.data.attributes.new(attr, "FLOAT", "POINT")
        data.data.foreach_set("value", values)
    if tunnel_at:
        cutter = through_passage(*tunnel_at, mat)
        carve(obj, cutter)
        bpy.data.objects.remove(cutter, do_unlink=True)


def knuckle(name, x, y, depth, width, mat, stones, rng, tunnel=None):
    n = 18
    phase = rng.uniform(0,math.tau)
    angles = [math.tau*(i+.25*rng.random())/n+phase for i in range(n)]
    radial = [rng.uniform(.86,1.13) for _ in angles]
    crown = rng.uniform(10.0,14.1)
    lean_x, lean_y = rng.uniform(-.85,.85), rng.uniform(-1.05,1.05)
    rings = []
    for height, spread in ((0,1),(.24,1.02),(.52,.81),(.77,.66),(1,.43)):
        row = []
        for i,a in enumerate(angles):
            s = spread*radial[i]*rng.uniform(.95,1.04)
            rz = crown*height + (rng.uniform(-1.28,1.28) if height else -.052)
            row.append((x+width*s*math.cos(a)+lean_x*height,
                        y+depth*s*math.sin(a)+lean_y*height, rz))
        rings.append(row)
    faces = [tuple(reversed(range(n)))]
    for level in range(len(rings)-1):
        for j in range(n):
            a,b = level*n+j,level*n+(j+1)%n
            faces.extend(((a,b,b+n),(a,b+n,a+n)) if (level+j)%2 else ((a,b,a+n),(b,b+n,a+n)))
    end = (len(rings)-1)*n
    faces.append(tuple(range(end,end+n)))
    obj = mesh(name, [p for row in rings for p in row], faces, mat)
    for a, dip in ((phase,.58),(phase+2.34,.82),(phase+4.72,.65)):
        c, s = math.cos(a), math.sin(a)
        cut_plane(obj, (x+width*.74*c,y+depth*.74*s,crown*.52), (c,s,dip))
    if tunnel:
        cutter = through_passage(*tunnel, mat)
        carve(obj, cutter)
        bpy.data.objects.remove(cutter, do_unlink=True)
    dirt = obj.data.attributes.new("Runnel", "FLOAT", "POINT")
    dirt.data.foreach_set("value", [.62*(1-smoothstep(v.co.z/10)) for v in obj.data.vertices])
    bevel = obj.modifiers.new("Worn breaks in the limestone", "BEVEL")
    bevel.width, bevel.segments, bevel.angle_limit = .19, 3, .31
    for a in (phase+.95,phase+2.76,phase+4.91):
        px, py = x+width*math.cos(a)*1.03, y+depth*math.sin(a)
        if not tunnel or abs(px-tunnel[0]) > 3.45:
            scree("Broken footing knuckle | detached stone", px, py, .82,
                  rng.uniform(3.25,4.95), rng.choice(stones), rng)


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


def through_passage(x, y, mat):
    shape = [(x-1.79,-.058), (x+1.79,-.058), (x+1.79,2.21)]
    shape.extend((x + 1.79*math.cos(t*math.pi/48), 2.21+1.79*math.sin(t*math.pi/48))
                 for t in range(1,49))
    return loft("Temporary tunnel tool", [[(px, y+d, z) for px, z in shape] for d in (-20,20)],
                mat, smooth=False)


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


def center_footprint(objects):
    ground = [obj for obj in objects if obj.name.startswith("Irregular root soil and turf")]
    lo, hi = vrlib.world_bounds(ground)
    shift = Matrix.Translation((-(lo.x+hi.x)/2, -(lo.y+hi.y)/2, 0))
    for obj in objects:
        obj.data.transform(shift)
    return shift


def build():
    stone = [pale_stone(f"Limestone | local bed {i+1}", i) for i in range(7)]
    footing = pale_stone("Limestone | fractured footing", 6)
    mortar = bedding()
    for i,(row,height,span) in enumerate(((-31,64,32),(0,77.2,39),(31,69,35))):
        rng = random.Random(410903+209*i)
        left, right = -span+rng.uniform(-3,3), span+rng.uniform(-3,3)
        ly, ry = row+rng.uniform(-3.2,3.2), row+rng.uniform(-3.2,3.2)
        crest_x, crest_y = rng.uniform(-4.4,4.4), row+rng.uniform(-3.1,3.1)
        half_crown = rng.uniform(15,22)
        spine = path((left,ly,-.052),(left-7,ly-2,height*.49),
                     (crest_x-half_crown,crest_y,height),(crest_x,crest_y,height),
                     (crest_x+half_crown,crest_y,height),(right+5,ry+3,height*.49),
                     (right,ry,-.052))
        tunnel = (right-.50,ry) if i == 0 else None
        vault(f"Rib arch {i+1:02} | joined limestone limbs", spine, rng.uniform(5.2,6.0),
              rng.uniform(4.6,5.5), stone[i], rng, tunnel)
        for j,(x,y) in enumerate(((left,ly),(right,ry))):
            passage = tunnel if j else None
            width, depth = rng.uniform(8.2,9.5), rng.uniform(8.1,9.3)
            knuckle(f"Rib arch {i+1:02} | footing {j+1}", x, y, depth, width, footing, stone, rng, passage)
            apron(x, y, width*1.32, depth*1.39, stone, rng, bool(passage))
        if tunnel:
            passage_foot = Vector((-ry, right, 0))
            passage_lining(*tunnel, stone, mortar, rng)
            passage_floor(*tunnel, stone, rng)
    rotation = Matrix.Rotation(math.radians(-74), 4, "Z")
    objects = vrlib.source_objects()
    for obj in objects:
        obj.data.transform(rotation)
    shift = center_footprint(objects)
    foot = shift @ rotation @ passage_foot
    figure = shift @ rotation @ (passage_foot + Vector((12,7,0)))
    bpy.context.scene["vr_review_figure"] = (figure.x, figure.y)
    bpy.context.scene["vr_review_hero"] = (-24, 10, .85, -10)
    bpy.context.scene["vr_review_base"] = (*foot.xy, 5.8, -65, 21, .30)

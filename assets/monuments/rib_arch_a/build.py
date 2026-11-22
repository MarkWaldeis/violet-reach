"""Tidebone Crossing: the eroded remains of a limestone ribcage."""

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.noise import noise_vector

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
    surface = nodes["Principled BSDF"]
    cream = vrmat.load_palette()["monument_white"]["linear_rgb"]
    warm = math.sin(i*2.12)
    tint = (1+.045*warm,.985,.965-.076*warm)
    ivory = tuple(c*t for c,t in zip(cream,tint))
    diffuse = surface.inputs["Base Color"]
    honed = nodes.new("ShaderNodeMixRGB")
    honed.inputs[0].default_value = .90
    honed.inputs[2].default_value = (*ivory,1)
    links.new(diffuse.links[0].from_socket,honed.inputs[1])
    attributes = {}
    for attribute_name in ("Stone bed", "Rain runnel", "Foot patina"):
        attr = nodes.new("ShaderNodeAttribute")
        attr.attribute_name = attribute_name
        attributes[attribute_name] = attr.outputs["Fac"]

    def stained(base, mask, color):
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = "MULTIPLY"
        links.new(mask, node.inputs[0])
        links.new(base, node.inputs[1])
        node.inputs[2].default_value = (*color,1)
        return node.outputs[0]

    tone = stained(honed.outputs[0], attributes["Stone bed"], (.79,.80,.75))
    tone = stained(tone, attributes["Rain runnel"], (.38,.32,.23))
    tone = stained(tone, attributes["Foot patina"], (.32,.41,.24))
    links.new(tone, diffuse)
    surface.inputs["Specular IOR Level"].default_value = .23
    coords = nodes.new("ShaderNodeTexCoord")
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 74
    grain.inputs["Detail"].default_value = 1.4
    links.new(coords.outputs["Object"], grain.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .014
    bump.inputs["Strength"].default_value = .28
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
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


def atmospheres(obj, masks):
    for name, values in zip(("Stone bed", "Rain runnel", "Foot patina"), masks):
        attr = obj.data.attributes.new(name, "FLOAT", "POINT")
        attr.data.foreach_set("value", values)


def limb(name, spine, width, thickness, stone, rng, direction):
    n, steps = 128, 230
    phi = rng.uniform(0,math.tau)
    ridges = [(j*math.tau/3+rng.uniform(-.33,.33),rng.uniform(.23,.41),rng.uniform(.49,.79))
              for j in range(3)]
    fractures = [(rng.uniform(.09,.92),rng.uniform(0,math.tau),rng.uniform(.013,.043),
                  rng.uniform(.10,.22),rng.uniform(.12,.36),rng.uniform(-7,7)) for _ in range(35)]
    rings, beds, rain, grime = [], [], [], []
    for i in range(steps+1):
        t = i/steps
        p, axis = spine(t)
        outer = direction*axis.cross(Vector((0,1,0))).normalized()
        side = direction*outer.cross(axis).normalized()
        sinuous = math.sin(math.pi*t)**2
        p += (side*(1.38*math.sin(7*t+phi)) + outer*(.83*math.cos(9*t+phi)))*sinuous
        twist = .26*math.sin(3.2*t+phi)+direction*.19*t
        turn = outer*math.cos(twist)+side*math.sin(twist)
        flank = side*math.cos(twist)-outer*math.sin(twist)
        taper = (1-.65*t)**1.22
        overlap = 1-.47*smoothstep((t-.86)/.14)
        a = width*taper*overlap
        b = thickness*(1-.52*t)**1.08*overlap
        row = []
        active = [(s,k,l,w,d,g) for s,k,l,w,d,g in fractures if abs(s-t) < l]
        for j in range(n):
            k = math.tau*j/n
            co, si = math.cos(k),math.sin(k)
            swell = (1.04*math.cos(2*k+2.2*t+phi)+.52*math.sin(4*k-15*t+phi))
            swell *= (.58+.42*math.sin(15*t+k+phi)**2)*(1-.76*t)
            erosion, runoff = 0, 0
            for c, breadth, dep in ridges:
                drift = .24*math.sin(5*t+phi+c)+.13*math.sin(13*t+c)
                v = math.remainder(k-c-drift, math.tau)/breadth
                g = math.exp(-v*v)*(.65+.35*math.cos(9*t+c)**2)
                erosion += dep*g
                runoff = max(runoff,(.21+.56*max(0,co))*g)
            for s,c,length,breadth,depth,g in active:
                u = (t-s)/length
                v = math.remainder(k-c-g*(t-s)-.034*math.sin(7*u),math.tau)/breadth
                fracture = max(0, 1-abs(u)**1.55-abs(v))
                erosion += depth*fracture
                runoff = max(runoff,.25*fracture)
            mid = .07*math.sin(17*k-53*t+phi)*math.cos(7*k+31*t)
            stroke = max(-.46,swell-erosion+mid)*(1-.77*smoothstep((t-.80)/.2))
            pt = p + turn*((a+stroke)*math.copysign(abs(co)**.80,co))
            pt += flank*((b+stroke*.53)*math.copysign(abs(si)**.93,si))
            pt.z = max(-.052,pt.z)
            row.append(pt)
            beds.append(.49+.23*math.sin(14*t+2*k+phi)+.19*math.cos(5*t-k))
            rain.append(min(.79,runoff*(.70+.30*math.sin(11*t+k+phi)**2)))
            grime.append((1-smoothstep((pt.z-1.7)/13))*(.62+.23*math.sin(7*k+phi)**2))
        rings.append(row)
    obj = loft(name, rings, stone)
    atmospheres(obj, (beds,rain,grime))
    p, axis = spine(.993)
    cut_plane(obj, p, axis + Vector((0,.47*direction,.39)))
    bevel = obj.modifiers.new("Worn scarf tip", "BEVEL")
    bevel.width, bevel.segments, bevel.angle_limit = .084, 3, .73


def knuckle(name, x, y, depth, width, stone, rng, lean):
    n, levels = 124, 79
    phase = rng.uniform(0,math.tau)
    crown = rng.uniform(11.8,15.4)
    breaks = [(phase+i*math.tau/6+rng.uniform(-.19,.19),rng.uniform(.66,.87),rng.uniform(.14,.42))
              for i in range(6)]
    chips = [(rng.uniform(.19,.87),rng.uniform(0,math.tau),rng.uniform(.13,.36),rng.uniform(.10,.26),
              rng.uniform(.40,.96)) for _ in range(27)]
    rings, beds, rain, patina = [], [], [], []
    for i in range(levels+1):
        t = i/levels
        row = []
        taper = 1-.18*t-.24*t**3-.26*smoothstep((t-.75)/.25)
        for j in range(n):
            a = math.tau*j/n
            c, s = math.cos(a), math.sin(a)
            radius = taper + (.059*math.sin(3*a+phase)+.042*math.sin(5*a-phase))*(1-.4*t)
            radius += .024*math.sin(11*a+8*t+phase)*math.cos(6*t)
            for phi, reach, slope in breaks:
                face = math.cos(a-phi)
                if face > .2:
                    plane = (reach+slope*(.26-t))/face
                    blend = max(0,.020-abs(plane-radius))/.020
                    radius = min(radius,plane)-.005*blend*blend
            z = (crown+1.9*lean*c)*t+1.37*math.sin(2*a+phase)*t*t+.26*math.cos(7*a-phase)*t
            px = x+width*radius*c+lean*t*2.85
            py = y+depth*radius*s+1.2*t*math.sin(phase)
            p = Vector((px,py,z))
            grain = noise_vector(p*.88).x*.13+noise_vector(p*3.1).y*.034
            gouge = 0
            for h,c0,b,l,dep in chips:
                u = (t-h)/l
                if abs(u) >= 1:
                    continue
                v = math.remainder(a-c0-.08*u,math.tau)/b
                gouge = max(gouge,dep*max(0,1-abs(u)-v*v))
            cut = grain-gouge
            z = -.051 if i == 0 else max(-.051,z-.051)
            row.append((px+c*cut,py+s*cut,z))
            beds.append(.49+.31*math.sin(a*3.1+t*7+phase))
            rain.append(.46*max(0,math.sin(a*13+phase+t))**3*smoothstep(t/.67))
            wet_line = 4.0+.74*math.sin(a*4+phase)+.50*math.cos(a*8)
            patina.append((1-smoothstep((z-wet_line+.62)/3.25))*(.67+.30*noise_vector(p*1.85).y))
        rings.append(row)
    obj = loft(name,rings,stone)
    atmospheres(obj,(beds,rain,patina))


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


def apron(x, y, ax, ay, rng):
    phase = rng.uniform(0, math.tau)
    n = 98

    def surface(u, a):
        edge = 1 + .088*math.sin(3*a+phase) + .043*math.cos(7*a-phase)
        bank = 3.1 + .64*math.sin(4*a+phase) + .35*math.sin(9*a-phase)
        raise_by = bank*(1-smoothstep((u-.29)/.71))
        px = x+ax*edge*u*math.cos(a)
        return (px, y+ay*edge*u*math.sin(a), raise_by-.033)

    stations = (.22,.32,.41,.50,.58,.66,.74,.82,.89,.95,1)
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
    rubble = (vrmat.get("mossy_rock"), vrmat.get("monument_weathered"), vrmat.get("forest_soil"))
    for _ in range(21):
        a0, u0 = rng.uniform(0,math.tau), rng.uniform(.52,.86)
        for i in range(rng.randint(9, 18)):
            a, u = a0 + rng.uniform(-.16,.16), min(.96, u0 + rng.uniform(-.10,.10))
            px, py, pz = surface(u, a)
            if i % 4 == 0:
                size = rng.uniform(.18,.64)
                scree("Sunk weathered foot rubble", px, py, pz-.27*size, size,
                      rng.choice(rubble), rng)
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




def center_footprint(objects):
    ground = [obj for obj in objects if obj.name.startswith("Irregular root soil and turf")]
    lo, hi = vrlib.world_bounds(ground)
    shift = Matrix.Translation((-(lo.x+hi.x)/2, -(lo.y+hi.y)/2, 0))
    for obj in objects:
        obj.data.transform(shift)
    return shift


def build():
    footing = pale_stone("Limestone | wet fractured buttresses", 6)
    for i,(row,height,span) in enumerate(((-31,64,32),(0,77,39),(31,69,35))):
        rng = random.Random(410903+209*i)
        crest_x = rng.uniform(-3.7,3.7)
        crest_y = row+rng.uniform(-2.4,2.4)
        for j,side in enumerate((-1,1)):
            x = side*span+rng.uniform(-2.9,2.9)
            y = row+rng.uniform(-3.1,3.1)
            crown = height+(1 if j else -1)*rng.uniform(.35,.85)
            drift = rng.uniform(-3.8,4.8)
            spine = path((x,y,-.052),(x+side*rng.uniform(3.7,10.7),y+drift,height*.41),
                         (crest_x+side*rng.uniform(15,23),crest_y+side*3.1,crown+1.9),
                         (crest_x-side*rng.uniform(3.6,5.1),crest_y-side*.95,crown))
            part = f"Rib {i+1:02}.{j+1}"
            stone = pale_stone(f"Limestone | {part}",3*i+j)
            limb(part,spine,rng.uniform(6.25,7.15),rng.uniform(4.1,4.85),stone,rng,side)
            width, depth = rng.uniform(9.7,11.2),rng.uniform(8.4,9.8)
            knuckle(f"{part} | fractured buttress",x,y,depth,width,footing,rng,side)
            apron(x,y,width*1.28,depth*1.49,rng)
            if i == 0 and j == 1:
                foreground = Vector((-y,x,0))
                foreground_depth = depth
    rotation = Matrix.Rotation(math.radians(-74),4,"Z")
    objects = vrlib.source_objects()
    for obj in objects:
        obj.data.transform(rotation)
    shift = center_footprint(objects)
    foot = shift @ rotation @ foreground
    figure = shift @ rotation @ (foreground+Vector((foreground_depth*1.49+1,8,0)))
    bpy.context.scene["vr_review_figure"] = (figure.x,figure.y)
    bpy.context.scene["vr_review_hero"] = (-24,10,.85,-10)
    bpy.context.scene["vr_review_base"] = (*foot.xy,5.8,-65,21,.30)

"""Tidebone Crossing: the eroded remains of a limestone ribcage."""

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
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


def pale_stone(name, i, buttress=False):
    mat = vrmat.get("monument_white").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    cream = vrmat.load_palette()["monument_white"]["linear_rgb"]
    warm = math.sin(i*2.12)
    tint = (.78,.71,.60) if buttress else (1+.045*warm,.985,.965-.076*warm)
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

    bed_tint = (.50,.43,.33) if buttress else (.79,.80,.75)
    foot_tint = (.18,.24,.12) if buttress else (.32,.41,.24)
    coords = nodes.new("ShaderNodeTexCoord")
    bed_mask = attributes["Stone bed"]
    if buttress:
        bed_noise = nodes.new("ShaderNodeTexNoise")
        bed_noise.inputs["Scale"].default_value = .83
        bed_noise.inputs["Detail"].default_value = 3.2
        links.new(coords.outputs["Object"], bed_noise.inputs["Vector"])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs[0].default_value = .16
        links.new(bed_noise.outputs["Fac"], mix.inputs[1])
        links.new(bed_mask, mix.inputs[2])
        bed_mask = mix.outputs[0]
    tone = stained(honed.outputs[0], bed_mask, bed_tint)
    tone = stained(tone, attributes["Rain runnel"], (.38,.32,.23))
    tone = stained(tone, attributes["Foot patina"], foot_tint)
    links.new(tone, diffuse)
    surface.inputs["Specular IOR Level"].default_value = .23
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 74
    grain.inputs["Detail"].default_value = 1.4
    links.new(coords.outputs["Object"], grain.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .014
    bump.inputs["Strength"].default_value = .28
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    if buttress:
        pits = nodes.new("ShaderNodeTexNoise")
        pits.inputs["Scale"].default_value = 7.2
        pits.inputs["Detail"].default_value = 2.7
        links.new(coords.outputs["Object"], pits.inputs["Vector"])
        worn = nodes.new("ShaderNodeBump")
        worn.inputs["Distance"].default_value = .19
        worn.inputs["Strength"].default_value = .55
        links.new(pits.outputs["Fac"], worn.inputs["Height"])
        links.new(worn.outputs["Normal"], bump.inputs["Normal"])
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


def buttresses(name, x, y, stone, rng, side):
    phase = (math.radians(-73) if side == 1 else math.radians(107)) + rng.uniform(-.16,.16)
    lobes = []
    count = rng.choice((3,3,4))
    for index in range(count):
        az = phase + math.tau*index/count + rng.uniform(-.18,.18)
        outward = Vector((math.cos(az),math.sin(az),0))
        lateral = Vector((-outward.y,outward.x,0))
        origin = Vector((x,y,0))
        reach, width = rng.uniform(10.8,13.9), rng.uniform(5.2,7.2)
        height = rng.uniform(15.0,18.5) if index == 0 else rng.uniform(11.6,15.6)
        breaks = [(rng.uniform(.05,.9), rng.uniform(.28,.68), rng.uniform(.10,.22),
                   rng.uniform(.12,.25), rng.uniform(.28,.72)) for _ in range(22)]
        rings = []
        for i in range(61):
            t = i/60
            taper = 1-.32*t-.32*t*t
            row = []
            for j in range(104):
                a = j*math.tau/104
                c, s = math.cos(a), math.sin(a)
                swell = 1+.060*math.sin(3*a+index)+.055*math.sin(5*a-4*t)
                p = origin + outward*(6.3-1.9*t+reach*taper*swell*c)
                p += lateral*(width*taper*swell*s+1.35*t*math.sin(index+1))
                p.z = max(-.051,t*height + .71*t*math.cos(2*a+index)-.051)
                noise = noise_vector(p*.49).x*.73+noise_vector(p*2.9).y*.16+noise_vector(p*10).x*.028
                for centre, level, breadth, rise, depth in breaks:
                    v = abs(math.remainder(a-centre,math.tau))/breadth
                    u = abs(t-level)/rise
                    if u+v < 1:
                        noise -= depth*smoothstep((1-u-v)*3)
                p += outward*(noise*c)+lateral*(noise*s)
                row.append(p)
            rings.append(row)
        obj = loft(f"{name} | splayed buttress {index+1}",rings,stone)
        for elevation, distance, lean, skew in (
            (.55,1.16,.78,-.44), (.75,.89,.99,.18), (.42,.96,.15,.97),
            (.64,.91,.58,-.94), (.31,1.26,-.18,.21),
        ):
            point = origin + outward*(distance*reach) + Vector((0,0,elevation*height))
            normal = outward + lateral*(skew+rng.uniform(-.13,.13)) + Vector((0,0,lean))
            cut_plane(obj, point, normal, fracture=True)

        masks = ([],[],[])
        for vertex in obj.data.vertices:
            p = vertex.co
            z = p.z
            bed = .5+.24*math.sin(z*1.6+p.x*.19-p.y*.12)+.21*noise_vector(p*.53).x
            runnel = .38*smoothstep((noise_vector(Vector((p.x*.89,p.y*.89,z*.16))).y+.34)/.84)
            wet_height = 6.2 + 1.6*noise_vector(p*.32).x
            wet = .91*(1-smoothstep((z-wet_height+1.30)/5.0))
            masks[0].append(bed)
            masks[1].append(runnel)
            masks[2].append(wet)
        atmospheres(obj,masks)
        bevel = obj.modifiers.new("Worn fracture arrises", "BEVEL")
        bevel.width, bevel.segments, bevel.angle_limit = .13, 3, .42
        lobes.append(obj)
    return lobes


def cut_plane(obj, point, normal, fracture=False):
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
        if fracture:
            for edge in face.edges:
                edge.smooth = False
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


def bank_material():
    mat = vrmat.get("grass_ground").copy()
    mat.name = "Root bank | turf breaking into damp loam"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = .36
    noise.inputs["Detail"].default_value = 4
    links.new(nodes.new("ShaderNodeTexCoord").outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .32
    ramp.color_ramp.elements[0].color = (.079,.064,.036,1)
    ramp.color_ramp.elements[1].position = .65
    ramp.color_ramp.elements[1].color = (.17,.205,.071,1)
    ramp.color_ramp.elements.new(.45).color = (.10,.092,.047,1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], surface.inputs["Base Color"])
    return mat


def apron(x, y, ax, ay, turf, lobes, rng):
    phase = rng.uniform(0, math.tau)
    n = 164

    def surface(u, a):
        edge = 1+.14*math.sin(3*a+phase)+.10*math.cos(7*a-phase)+.046*math.sin(17*a+phase)
        bank = 4.45+.82*math.sin(3*a+phase)+.69*math.sin(8*a-phase)
        px, py = x+ax*edge*u*math.cos(a), y+ay*edge*u*math.sin(a)
        taper = 1-smoothstep((u-.25)/.75)
        rise = taper*(bank+.66*noise_vector(Vector((px*.71,py*.71,phase))).x)
        return (px,py,rise-.051)

    stations = [i/32 for i in range(1,33)]
    rings = [[surface(u,j*math.tau/n) for j in range(n)] for u in stations]
    faces = [tuple(range(n))]
    faces.extend((i*n+j, (i+1)*n+j, (i+1)*n+(j+1)%n, i*n+(j+1)%n)
                 for i in range(len(rings)-1) for j in range(n))
    mesh("Irregular root soil and turf", [p for row in rings for p in row], faces, turf,
         solid=False, smooth=True)
    trees = [BVHTree.FromPolygons([v.co for v in obj.data.vertices],
                                [p.vertices for p in obj.data.polygons]) for obj in lobes]
    rubble = vrmat.get("mossy_rock")
    plants = [([],[]),([],[])]
    for cluster in range(94):
        a0 = rng.uniform(0,math.tau)
        u0 = rng.uniform(.84,1.02) if cluster < 37 else rng.uniform(.28,.91)
        for i in range(rng.randint(4, 9)):
            a, u = a0 + rng.uniform(-.11,.11), min(1.07,u0+rng.uniform(-.055,.055))
            px, py, pz = surface(u, a)
            hits = [tree.ray_cast((-py,px,22),(0,0,-1))[0] for tree in trees] if u < .87 else []
            top = max((hit.z for hit in hits if hit is not None), default=pz)
            ledge = top > pz+.14
            if top > pz+2.5 or (u > .96 and rng.random() < smoothstep((u-.96)/.12)*.9):
                continue
            if i == 0 and cluster % 2 == 0 and not ledge and u < .94:
                size = rng.uniform(.29,.83)
                scree("Sunk dirty limestone chips", px, py, pz-.29*size, size, rubble, rng)
            kind = int(ledge or cluster % 3 == 0)
            blades, faces = plants[kind]
            for _ in range(rng.randint(5, 11)):
                ta = rng.uniform(0,math.tau)
                dx, dy = math.cos(ta), math.sin(ta)
                h, w = (rng.uniform(.10,.34),rng.uniform(.035,.092)) if kind else (
                    rng.uniform(.23,.75),rng.uniform(.035,.083))
                xx, yy = px+rng.uniform(-.17,.17), py+rng.uniform(-.17,.17)
                base = max(0 if u > .9 else -.051,top-.075)
                start = len(blades)
                blades.extend(((xx-w*dy,yy+w*dx,base),(xx+w*dy,yy-w*dx,base),
                               (xx+.21*h*dx,yy+.21*h*dy,base+.59*h),
                               (xx+.52*h*dx,yy+.52*h*dy,base+h)))
                faces.extend(((start,start+1,start+2),(start,start+2,start+3)))
    for (blades,faces), name, mat in zip(plants, ("Feathered bank grass","Moss on damp ledges"),
                                        ("foliage_leaf","mossy_rock")):
        mesh(name, blades, faces, vrmat.get(mat), solid=False)


def center_footprint(objects):
    ground = [obj for obj in objects if obj.name.startswith("Irregular root soil and turf")]
    lo, hi = vrlib.world_bounds(ground)
    shift = Matrix.Translation((-(lo.x+hi.x)/2, -(lo.y+hi.y)/2, 0))
    for obj in objects:
        obj.data.transform(shift)
    return shift


def build():
    footing = pale_stone("Limestone | wet fractured buttresses", 6, buttress=True)
    turf = bank_material()
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
            ground_rng = random.Random(15427+53*i+j)
            lobes = buttresses(part,x,y,footing,ground_rng,side)
            apron(x,y,ground_rng.uniform(18.8,21.0),ground_rng.uniform(17.3,19.7),turf,lobes,ground_rng)
            if i == 0 and j == 1:
                foreground = Vector((-y,x,0))
    rotation = Matrix.Rotation(math.radians(-74),4,"Z")
    objects = vrlib.source_objects()
    for obj in objects:
        obj.data.transform(rotation)
    shift = center_footprint(objects)
    foot = shift @ rotation @ foreground
    figure = foot+Vector((23,-16,0))
    bpy.context.scene["vr_review_figure"] = (figure.x,figure.y)
    bpy.context.scene["vr_review_hero"] = (-24,10,.85,-10)
    bpy.context.scene["vr_review_base"] = (*foot.xy,6.5,-54,23,.34)

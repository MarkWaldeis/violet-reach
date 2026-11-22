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


def pale_stone(name, i):
    mat = vrmat.get("monument_white").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    cream = vrmat.load_palette()["monument_white"]["linear_rgb"]
    warm = math.sin(i*2.12)
    tint = (.87+.11*warm,.85+.075*warm,.77+.075*warm)
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

    coords = nodes.new("ShaderNodeTexCoord")
    vector = coords.outputs["Object"]
    tone = stained(honed.outputs[0], attributes["Stone bed"], (.61,.56,.47))
    tone = stained(tone, attributes["Rain runnel"], (.37,.29,.20))
    foot = attributes["Foot patina"]
    tone = stained(tone, foot, (.43,.46,.32))
    lichen = nodes.new("ShaderNodeTexNoise")
    lichen.inputs["Scale"].default_value = .92
    lichen.inputs["Detail"].default_value = 3
    links.new(vector, lichen.inputs["Vector"])
    spots = nodes.new("ShaderNodeValToRGB")
    spots.color_ramp.elements[0].position = .49
    spots.color_ramp.elements[1].position = .68
    links.new(lichen.outputs["Fac"], spots.inputs["Fac"])
    mask = nodes.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    links.new(spots.outputs["Color"], mask.inputs[0])
    links.new(foot, mask.inputs[1])
    tone = stained(tone, mask.outputs[0], (.34,.43,.20))
    links.new(tone, diffuse)
    surface.inputs["Specular IOR Level"].default_value = .18
    links.remove(surface.inputs["Roughness"].links[0])
    surface.inputs["Roughness"].default_value = .87
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 31
    grain.inputs["Detail"].default_value = 1.4
    links.new(vector, grain.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .035
    bump.inputs["Strength"].default_value = .47
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    pits = nodes.new("ShaderNodeTexNoise")
    pits.inputs["Scale"].default_value = 3.4
    pits.inputs["Detail"].default_value = 2.1
    links.new(vector, pits.inputs["Vector"])
    worn = nodes.new("ShaderNodeBump")
    worn.inputs["Distance"].default_value = .24
    worn.inputs["Strength"].default_value = .50
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


def limb(name, spine, width, thickness, stone, rng, direction, broken):
    n, steps = 160, 350
    phi = rng.uniform(0,math.tau)
    ridges = [(j*math.tau/3+rng.uniform(-.33,.33),rng.uniform(.23,.41),rng.uniform(.49,.79))
              for j in range(3)]
    fractures = [(rng.uniform(.08,.94),rng.uniform(0,math.tau),rng.uniform(.014,.050),
                  rng.uniform(.21,.55),rng.uniform(.24,.95),rng.uniform(-7,7)) for _ in range(35)]
    root_rng = random.Random(phi)
    breaks = [(phi+i*math.tau/4+root_rng.uniform(-.28,.28),root_rng.uniform(.72,.92),
               root_rng.uniform(.24,.60)) for i in range(4)]
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
        pulses = .19*math.sin(15*t+phi)+.11*math.sin(34*t-phi)+.047*math.sin(65*t+phi)
        a = width*taper*overlap*(1+pulses)
        b = thickness*(1-.52*t)**1.08*overlap*(1-.78*pulses+.11*math.cos(23*t+phi))
        power = .63+.17*math.sin(12*t+phi)+.12*math.sin(27*t)
        root = (1-smoothstep((t-.032)/.235))*(1-.41*smoothstep(t/.23))
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
                g = math.exp(-v*v)*(.57+.43*math.cos(13*t+c)**2)
                erosion += 1.65*dep*g
                runoff = max(runoff,(.56+.34*max(0,co))*g)
            for s,c,length,breadth,depth,g in active:
                u = (t-s)/length
                v = math.remainder(k-c-g*(t-s)-.034*math.sin(7*u),math.tau)/breadth
                fracture = smoothstep((1-abs(u)**1.3-abs(v))*3.8)
                erosion += depth*fracture
                runoff = max(runoff,.55*fracture)
            flare = (1+.28*math.cos(3*k+phi)+.16*math.sin(5*k-2*phi))*root
            tx = (a+8.3*flare)*math.copysign(abs(co)**power,co)
            fy = (b+7.6*flare)*math.copysign(abs(si)**(power+.08),si)
            relief = (swell-erosion)*(1-.62*smoothstep((t-.82)/.18))
            for angle, reach, rake in breaks:
                c, s = math.cos(angle),math.sin(angle)
                projected = c*tx+s*fy
                plane = (8.2+3.2*root)*reach-rake*p.z
                trim = max(0,projected-plane)*root
                tx -= trim*c
                fy -= trim*s
            out = turn*tx + flank*fy
            out.z *= smoothstep(p.z/11)
            pt = p+out
            coarse = noise_vector(pt*.70).x
            broken_surface = noise_vector(pt*2.9).y
            relief += coarse*(.41+.59*root)+broken_surface*(.26+.10*root)
            relief += .023*noise_vector(pt*18).x
            pt += (turn*co+flank*si)*relief
            pt.z = -.052 if i == 0 else max(-.052,pt.z)
            row.append(pt)
            beds.append(.39+.20*math.sin(21*t+2*k+phi)+.23*coarse+.21*root)
            streak = noise_vector(Vector((pt.x*.91,pt.y*.91,pt.z*.13))).y
            rain.append(min(.90,runoff*(.62+.38*math.sin(11*t+k+phi)**2)+.55*max(0,streak+.11)))
            grime.append((1-smoothstep((pt.z-5.8)/22))*(.81+.25*coarse))
        rings.append(row)
    obj = loft(name, rings, stone)
    atmospheres(obj, (beds,rain,grime))
    if broken:
        p, axis = spine(.979)
        cut_plane(obj, p, axis + Vector((0,.73*direction,.46)), fracture=True)
    else:
        p, axis = spine(.996)
        cut_plane(obj, p, axis + Vector((0,.43*direction,.28)))
    bevel = obj.modifiers.new("Worn scarf tip", "BEVEL")
    bevel.width, bevel.segments, bevel.angle_limit = .084, 3, .73
    return obj


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
    noise.inputs["Scale"].default_value = .22
    noise.inputs["Detail"].default_value = 4
    links.new(nodes.new("ShaderNodeTexCoord").outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .32
    ramp.color_ramp.elements[0].color = (.098,.097,.043,1)
    ramp.color_ramp.elements[1].position = .66
    ramp.color_ramp.elements[1].color = (.145,.171,.070,1)
    ramp.color_ramp.elements.new(.43).color = (.115,.131,.054,1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], surface.inputs["Base Color"])
    return mat


def apron(x, y, ax, ay, turf, root, rng):
    phase = rng.uniform(0, math.tau)
    n = 164

    def surface(u, a):
        edge = 1+.16*math.sin(3*a+phase)+.12*math.cos(7*a-phase)+.050*math.sin(17*a+phase)
        bank = 4.8+1.21*math.sin(3*a+phase)+.77*math.sin(8*a-phase)
        px, py = x+ax*edge*u*math.cos(a), y+ay*edge*u*math.sin(a)
        taper = 1-smoothstep((u-.24)/.76)
        w = noise_vector(Vector((px*.44,py*.44,phase)))
        rise = taper*(bank+1.04*w.x)
        rise += .38*w.y*smoothstep((u-.47)/.24)*(1-smoothstep((u-.76)/.24))
        rise = max(0,rise)
        return (px,py,rise-.051)

    stations = [i/32 for i in range(1,33)]
    rings = [[surface(u,j*math.tau/n) for j in range(n)] for u in stations]
    faces = [tuple(range(n))]
    faces.extend((i*n+j, (i+1)*n+j, (i+1)*n+(j+1)%n, i*n+(j+1)%n)
                 for i in range(len(rings)-1) for j in range(n))
    mesh("Irregular root soil and turf", [p for row in rings for p in row], faces, turf,
         solid=False, smooth=True)
    tree = BVHTree.FromPolygons([v.co for v in root.data.vertices],
                                [p.vertices for p in root.data.polygons])
    rubble = vrmat.get("mossy_rock")
    plants = [([],[]),([],[])]
    for cluster in range(131):
        a0 = rng.uniform(0,math.tau)
        u0 = rng.uniform(.78,1.05) if cluster < 65 else rng.uniform(.33,.89)
        for i in range(rng.randint(4, 9)):
            a, u = a0 + rng.uniform(-.11,.11), min(1.07,u0+rng.uniform(-.055,.055))
            px, py, pz = surface(u, a)
            hit = tree.ray_cast((-py,px,19),(0,0,-1))[0] if u < .87 else None
            top = max(pz,hit.z) if hit is not None else pz
            ledge = top > pz+.14
            if top > pz+2.5 or (u > .89 and rng.random() < smoothstep((u-.89)/.18)*.93):
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
            root = limb(part,spine,rng.uniform(6.25,7.15),rng.uniform(4.1,4.85),
                        stone,rng,side,broken=(i,j) in ((0,1),(2,0)))
            ground_rng = random.Random(15427+53*i+j)
            apron(x,y,ground_rng.uniform(18.8,21.0),ground_rng.uniform(17.3,19.7),turf,root,ground_rng)
            if i == 0 and j == 1:
                foreground = Vector((-y,x,0))
    rotation = Matrix.Rotation(math.radians(-74),4,"Z")
    objects = vrlib.source_objects()
    for obj in objects:
        obj.data.transform(rotation)
    shift = center_footprint(objects)
    foot = shift @ rotation @ foreground
    figure = foot+Vector((27,-22,0))
    bpy.context.scene["vr_review_figure"] = (figure.x,figure.y)
    bpy.context.scene["vr_review_hero"] = (-29,9,.81,-10)
    bpy.context.scene["vr_review_base"] = (*foot.xy,6.5,-54,23,.34)

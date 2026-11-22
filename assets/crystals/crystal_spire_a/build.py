"""A long mineral blade along an exposed, faulted bedding plane."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import vrlib
import vrmat


def mesh(name, rings, material, rounding):
    n = len(rings[0])
    pointed = len(rings[-1]) == 1
    sections = len(rings)-int(pointed)
    faces = [tuple(reversed(range(n)))]
    for level in range(sections - 1):
        a = level * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a+i, a+j, a+j+n, a+i+n))
    if pointed:
        a=(sections-1)*n
        faces.extend((a+i,a+(i+1)%n,a+n) for i in range(n))
    else:
        faces.append(tuple(range((sections-1)*n,sections*n)))
    data = bpy.data.meshes.new(name)
    data.from_pydata([p for ring in rings for p in ring], [], faces)
    data.update()
    ob = vrlib.link_to_source(bpy.data.objects.new(name, data))
    data.materials.append(vrmat.get(material) if isinstance(material,str) else material)
    if rounding:
        bevel = ob.modifiers.new("Weathered arrises", "BEVEL")
        bevel.width, bevel.segments = rounding, 3
        bevel.limit_method = "ANGLE"
    return ob


def fissure_bank(name, outline, surface, fall, phase):
    cx = sum(x for x, _ in outline) / len(outline)
    cy = sum(y for _, y in outline) / len(outline)
    rows = ((-.044,.22,1.00,0),(.20,.39,.97,.043),(.373,.52,1.003,-.052),
            (.504,.675,.93,.075),(.653,.84,.84,.029),(.823,1.00,.78,.123))
    for j,(low,high,spread,offset) in enumerate(rows):
        rings = []
        for z,s in ((low,.94),(low*.79+high*.21,1),(.23*low+.77*high,1.012),(high,.965)):
            ring = []
            for i,(x,y) in enumerate(outline):
                joint = fall*(.08+.22*(i%3==1))*max(0,z) if abs(x)<.78 else 0
                shelf = .055*math.sin(i*1.96+phase)
                elevation = z if z<=0 else z*surface[i]+shelf*(.15+.85*z)
                radius = spread*s*(1+.039*math.sin(i*2.7+j))
                ring.append((cx+radius*(x-cx)+offset*fall+joint,cy+radius*(y-cy)+offset*.28,
                             elevation))
            rings.append(ring)
        ob = mesh(f"{name} / offset bed {j+1}",rings,"monument_white",.017)
        ob.data.materials.append(vrmat.get("monument_weathered"))
        for face in ob.data.polygons[1:len(outline)+1]:
            face.material_index = 1


def mineral_finish(variant):
    key = f"Violet / opaque chalcedony facet {variant}"
    if bpy.data.materials.get(key):
        return bpy.data.materials[key]
    mat = vrmat.get("violet_crystal").copy()
    mat.name = key
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for node in list(nodes):
        if node.type not in {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}:
            nodes.remove(node)
    bsdf.inputs["Roughness"].default_value = (.34,.29,.26,.32,.27,.31)[variant]
    bsdf.inputs["Coat Weight"].default_value = .055
    bsdf.inputs["Specular IOR Level"].default_value = .31
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "inclusions"

    def scalar(operation, a, b):
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        for socket,value in zip(node.inputs,(a,b)):
            if isinstance(value,(float,int)):
                socket.default_value = value
            else:
                links.new(value,socket)
        return node.outputs[0]

    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 14
    links.new(coord,grain.inputs["Vector"])
    field = scalar("ADD",attr.outputs["Fac"],scalar("MULTIPLY",grain.outputs["Fac"],.11))
    palette = vrmat.load_palette()
    r,g,b = palette["violet_body"]["linear_rgb"]
    gain = (.20,.49,.76,.31,.60,.39)[variant]
    dark = (r*gain*1.26,g*gain*.80,b*gain*.76,1)
    band = (r*(gain*.72+.34)*1.48,g*(gain*.70+.38),b*(gain*.63+.26)*.85,1)
    color = nodes.new("ShaderNodeValToRGB")
    color.color_ramp.elements[0].position = .09
    color.color_ramp.elements[0].color = dark
    color.color_ramp.elements[1].position = .94
    color.color_ramp.elements[1].color = band
    links.new(field,color.inputs[0])
    links.new(color.outputs["Color"],bsdf.inputs["Base Color"])
    links.new(color.outputs["Color"],bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = .025
    return mat


def cleft_material(edge):
    key = "Violet / healed fracture" if edge else "Violet / mineral seam"
    if bpy.data.materials.get(key):
        return bpy.data.materials[key]
    mat = mineral_finish(0).copy()
    mat.name = key
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    for name in ("Base Color","Emission Color"):
        socket = bsdf.inputs[name]
        nt.links.remove(socket.links[0])
    bsdf.inputs["Base Color"].default_value = (.039,.009,.066,1) if edge else (.28,.067,.38,1)
    bsdf.inputs["Emission Color"].default_value = (.63,.16,.73,1)
    bsdf.inputs["Emission Strength"].default_value = .0 if edge else .51
    return mat


def fissures(name, rotation, rings, radius, sections, sides, phase):
    corners = len(rings[0])
    verts, faces, tones = [], [], []
    for i,side in enumerate(sides):
        right = (side+1)%corners
        a,b = rings[sections[i]][side],rings[sections[i]][right]
        c,d = rings[sections[i]+1][side],rings[sections[i]+1][right]
        normal = (b-a).cross(c-a).normalized()
        start = len(verts)
        for j in range(23):
            t = j/22
            s = .13+.77*t
            w = .22+.52*t+.19*math.sin(math.pi*t)+.035*math.sin(t*23+phase)
            width = (.011+.055*math.sin(math.pi*t))*(.82+.18*math.cos(t*31))
            for shift in (-1,-.38,.38,1):
                u = w+width*shift
                verts.append(a.lerp(b,u).lerp(c.lerp(d,u),s)+normal*radius*.003)
            if j:
                k = start+j*4
                for m in range(3):
                    faces.append((k-4+m,k-3+m,k+1+m,k+m))
                    tones.append(int(m!=1))
    data = bpy.data.meshes.new(name+" fracture mineralization")
    data.from_pydata(verts,[],faces)
    data.update()
    data.materials.append(cleft_material(False))
    data.materials.append(cleft_material(True))
    for poly,tone in zip(data.polygons,tones):
        poly.material_index = tone
    fissure = vrlib.link_to_source(bpy.data.objects.new(data.name,data))
    fissure.matrix_world = rotation


def prismatic_growth(name, base, height, radius, lean, phase, rng, outline_kind=0, broken=False):
    axis = Vector((*lean,1)).normalized()
    u = Vector((0,1,0)).cross(axis).normalized()
    v = axis.cross(u)
    rotation = Matrix((u,v,axis)).transposed().to_4x4()
    rotation.translation = Vector(base)
    corners = 4 if outline_kind==2 else 6
    profile = [Vector((radius*math.cos(phase+i*math.tau/corners),
                       radius*math.sin(phase+i*math.tau/corners)*(.63 if outline_kind else .88),0))
               for i in range(corners)]
    first = rng.uniform(.22,.40)
    second = rng.uniform(.49,.66)
    shift = rng.choice((-1,1))
    levels = (
        (0,.80,0,0),(.085,1,0,0),
        (first,1,0,.013),(first+.032,.90,.048*shift,.013),
        (second,.90,.048*shift,.019),(second+.048,.76,-.027*shift,.019),
        (.78,.76,-.027*shift,.037),(.89,.51,.08,.026))
    rings = []
    for k,(f,s,drift,rake) in enumerate(levels):
        ring = [p*s+Vector((radius*drift,0,height*(f+rake*math.sin(i*math.tau/corners+phase))))
                for i,p in enumerate(profile)]
        rings.append(ring)
    if broken:
        rings.append([p*.33+Vector((radius*.18,-radius*.08,
                      height*(.97+.035*math.cos(i*math.tau/corners+phase))))
                      for i,p in enumerate(profile)])
    else:
        rings.append([Vector((radius*.27,-radius*.035,height))])
    ob = mesh(name,rings,mineral_finish(0),min(.005,radius*.016))
    ob.matrix_world = rotation
    for tone in range(1,6):
        ob.data.materials.append(mineral_finish(tone))
    for poly in ob.data.polygons[1:]:
        row,col = divmod(poly.index-1,corners)
        poly.material_index = ((col*5+int(phase*2))%6 if row<6 else
                               (col*3+row+int(phase*3))%6)
        if broken and row == len(rings)-1:
            poly.material_index = 4

    # An opaque section of the growth volume: oblique shells narrow into the stone at each end.
    # A mesh attribute keeps their buried, curved silhouettes independent of the outer growth steps.
    if height>=.34:
        mesh_data = ob.data
        bm = bmesh.new()
        bm.from_mesh(mesh_data)
        bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=11 if radius>=.2 else 4,
                                  use_grid_fill=True)
        layer = bm.verts.layers.float.new("inclusions")
        pools = [(rng.uniform(.24,.35),.011,.42), (rng.uniform(.44,.55),.028,.86),
                 (rng.uniform(.65,.76),.020,.66),(.91,.014,.32)]
        for vertex in bm.verts:
            x,y,z = vertex.co
            ax = z/height
            across = (x*.81+y*.55)/radius
            depth = (x*-.55+y*.81)/radius
            envelope = max(.0,1.05-across*across*.92)
            field = 0
            for center,width,gain in pools:
                dist = abs(ax-center-depth*.064-across*across*.058)
                field = max(field,gain*envelope*max(0,1-dist/(width*(.35+.65*envelope))))
            vertex[layer] = field
        bm.to_mesh(mesh_data)
        bm.free()
        mesh_data.update()

    if radius>=.20:
        target = math.radians(68)
        camera = Vector((math.cos(target),math.sin(target),.23))
        face_order = sorted(range(corners),key=lambda i:camera.dot(rotation.to_3x3() @
                            (profile[i]+profile[(i+1)%corners]).normalized()),reverse=True)
        fissures(name,rotation,rings,radius,(1,3,5),(face_order[0],face_order[1],face_order[0]),phase)


def blade(name, base, width, height, lean, roll, rng):
    prismatic_growth(name,base,height,width,lean,roll,rng,int(width<.70),
                     name in {"Main spire","Broken secondary blade","Back seam tongue"})


def talus(rng, index, x, y, r, h, z):
    n = rng.choice((5,6,7,8,9))
    angles = [i*math.tau/n + rng.uniform(-.16,.16) for i in range(n)]
    outline = [rng.uniform(.67, 1.18) for _ in angles]
    yaw, width, shear = rng.uniform(0,math.tau),rng.uniform(.49,.91),rng.uniform(-.46,.45)
    rings = [[(x+r*(s*outline[i]*math.cos(a+yaw)+shear*f), y+r*width*s*outline[i]*math.sin(a+yaw),
               max(-.051,z+(f+.30*f*math.sin(a+yaw))*h)) for i,a in enumerate(angles)]
             for f,s in ((-.12,.75),(.10,1),(.42,.995),(.49,.86),(.54,.94),(.85,.91),(1,.67))]
    mesh(f"Fault scree {index:02}",rings,("monument_white","monument_white","monument_weathered")[index%3],
         min(.021,r*.07))


def fracture_collar(rng):
    for i in range(21):
        a = i*math.tau/21+rng.uniform(-.12,.12)
        r = rng.uniform(.73,1.02)*(1-.2*math.sin(a))
        x,y = .11+math.cos(a)*r,-.29+math.sin(a)*r
        z = .18+.23*max(0,-math.cos(a))
        size = rng.uniform(.15,.35)
        talus(rng,i+145,x,y,size,size*rng.uniform(.85,1.95),z)


def build():
    rng = random.Random(761308)
    fissure_bank("Uplifted west bank", [(-3.3,.08),(-2.51,-1.17),(-1.47,-1.75),(-.65,-1.9),
                 (-.16,-.97),(-.35,-.18),(.02,.66),(-.12,1.45),(-1.02,1.86),(-2.13,1.48),(-3.01,.98)],
                 [.26,.43,.65,1.18,1.66,1.59,1.58,1.35,.90,.48,.32], -1, .65)
    fissure_bank("Downthrown east bank", [(.61,-1.67),(1.45,-1.52),(2.47,-1.35),(3.08,-.58),
                 (3.13,.38),(2.32,1.29),(1.25,1.66),(.31,1.46),(.60,.73),(.29,.08),(.53,-.67)],
                 [.67,.49,.37,.21,.37,.42,.67,.97,1.07,.99,.93], 1, .27)
    blade("Main spire", (-.03,-.31,.53), .78, 6.94, (.15,.075), .19, rng)
    blade("Broken secondary blade", (-.09,.31,.63), .43, 3.74, (-.31,.23), .71, rng)
    blade("Downthrown fang", (.41,.07,.53), .42, 2.83, (.52,-.16), .86, rng)
    blade("Front seam tongue", (.04,-.86,.41), .27, 1.62, (-.17,-.62), .30, rng)
    blade("Back seam tongue", (.29,.81,.37), .24, 1.37, (.30,.48), 1.1, rng)
    blade("Accreted shoulder of the spire", (.63,-.46,2.57), .21, 1.63, (.28,-.05), .78,rng)
    blade("Short prism on the rear arris", (-.18,.13,2.39), .18, 1.99, (-.015,.25), .26,rng)
    fracture_collar(rng)
    for i in range(113):
        a = rng.uniform(0, math.tau)
        if i%3:
            a = rng.choice((.4,2.76,3.91,5.18))+rng.gauss(0,.23)
        rf = rng.uniform(.77, 1.08)
        x, y = 2.98*rf*math.cos(a), 1.75*rf*math.sin(a)
        r = .037+.26*rng.random()**2 if i>10 else rng.uniform(.29,.57)
        talus(rng,i,x,y,r,r*rng.uniform(.39,.89),-.012)
    for i in range(12):
        y = -.97 + i*.177
        x = .16+.14*math.sin(y*3.6)
        talus(rng, i+59, x,y,rng.uniform(.15,.29),rng.uniform(.24,.53),0)
        if i % 3 == 0:
            blade(f"Seam splinter {i:02}", (x,y,.21), rng.uniform(.065,.13), rng.uniform(.30,.72),
                  (rng.uniform(-.4,.4),rng.uniform(-.35,.35)),rng.uniform(0,math.tau),rng)
    yaw = Matrix.Rotation(math.radians(-48),4,"Z")
    for ob in vrlib.source_objects():
        ob.matrix_world = yaw @ ob.matrix_world
    bpy.context.scene["vr_closeup_upper"] = (.42,-.67,5.66,65,8,8.42)

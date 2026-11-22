"""A long mineral blade along an exposed, faulted bedding plane."""
import math
import random

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
        ob = mesh(f"{name} / offset bed {j+1}",rings,"canyon_layered" if j%3!=1 else "monument_white",.017)
        ob.data.materials.append(vrmat.get("monument_weathered"))
        for face in ob.data.polygons[1:len(outline)+1]:
            face.material_index = 1


def mineral_finish(variant):
    key = "Violet / axial inclusions " + str(variant)
    existing = bpy.data.materials.get(key)
    if existing:
        return existing
    mat = vrmat.get("violet_crystal").copy()
    mat.name = key
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for name in ("Base Color","Normal","Emission Strength"):
        socket = bsdf.inputs[name]
        for link in list(socket.links):
            links.remove(link)
    bsdf.inputs["Roughness"].default_value = .31+.02*variant
    bsdf.inputs["Coat Weight"].default_value = .18
    bsdf.inputs["IOR"].default_value = 1.49
    bsdf.inputs["Emission Strength"].default_value = .065
    coord = nodes.new("ShaderNodeTexCoord").outputs["Generated"]

    def scale(vector, factors):
        op = nodes.new("ShaderNodeVectorMath")
        op.operation = "MULTIPLY"
        links.new(vector,op.inputs[0])
        op.inputs[1].default_value = factors
        return op.outputs[0]

    def remap(source, a, b, colors):
        r = nodes.new("ShaderNodeValToRGB")
        for k,(position,color) in enumerate(zip((a,b),colors)):
            r.color_ramp.elements[k].position = position
            r.color_ramp.elements[k].color = color
        links.new(source,r.inputs[0])
        return r.outputs[0]

    cells = nodes.new("ShaderNodeTexVoronoi")
    cells.inputs["Scale"].default_value = 1.8
    links.new(scale(coord,(4.3,4.3,1.2)),cells.inputs["Vector"])
    veins = nodes.new("ShaderNodeTexNoise")
    veins.inputs["Scale"].default_value = 1
    links.new(scale(coord,(28,28,1.7)),veins.inputs["Vector"])
    bands = nodes.new("ShaderNodeTexWave")
    bands.bands_direction = "Z"
    bands.wave_profile = "TRI"
    bands.inputs["Scale"].default_value = 1.48
    bands.inputs["Distortion"].default_value = .25
    links.new(coord,bands.inputs["Vector"])
    pal = vrmat.load_palette()
    warm = (.91,1.0,1.08)[variant]
    def violet(name, exposure):
        r,g,b = pal[name]["linear_rgb"]
        return (r*1.48*warm*exposure,g*.91*exposure,b*.89*exposure,1)

    body = remap(cells.outputs["Distance"],.18,.76,
                 (violet("violet_body",1.02),violet("violet_shadow",1.06)))
    for field, weight, low in ((veins.outputs["Fac"],.32,.59),(bands.outputs["Fac"],.39,.67)):
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = weight
        links.new(body,mix.inputs[1])
        links.new(remap(field,.15,.73,((low,low*.97,low,1),(1,1,1,1))),mix.inputs[2])
        body = mix.outputs[0]
    links.new(body,bsdf.inputs["Base Color"])
    links.new(body,bsdf.inputs["Emission Color"])
    return mat


def cleft_material():
    key = "Violet / buried fissure glow"
    if bpy.data.materials.get(key):
        return bpy.data.materials[key]
    mat = mineral_finish(1).copy()
    mat.name = key
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    for name in ("Base Color","Emission Color"):
        socket = bsdf.inputs[name]
        nt.links.remove(socket.links[0])
    bsdf.inputs["Base Color"].default_value = (.31,.077,.50,1)
    bsdf.inputs["Emission Color"].default_value = (.63,.15,.79,1)
    bsdf.inputs["Emission Strength"].default_value = .57
    return mat


def prismatic_growth(name, base, height, radius, lean, phase, rng, outline_kind=0):
    axis = Vector((*lean,1)).normalized()
    u = Vector((0,1,0)).cross(axis).normalized()
    v = axis.cross(u)
    rotation = Matrix((u,v,axis)).transposed().to_4x4()
    rotation.translation = Vector(base)
    corners = 4 if outline_kind==2 else 6
    profile = [Vector((radius*math.cos(phase+i*math.tau/corners),
                       radius*math.sin(phase+i*math.tau/corners)*(.59 if outline_kind else .85),0))
               for i in range(corners)]
    widths=(1.0,1.12,.74)
    irregularity=rng.uniform(.89,1.17)
    levels = ((0,.76,0,0),(.08,1,0,0),(.235,1,0,0),(.243,1.034,0,0),
              (.263,1.034,0,0),(.277,.955,.022,0),(.43,.955,.022,0),
              (.432,.997,.005,0),(.453,.997,.005,0),(.466,.887,.058,0),
              (.575,.887,.058,0),(.582,.925,.049,0),(.601,.925,.049,0),
              (.621,.855,.064,0),(.743,.855,.064,0),
              (.815,.855,.064,.85),(.907,.41,.18,.33))
    rings = []
    pinch = rng.randrange(corners)
    for k,(f,s,drift,termination) in enumerate(levels):
        ring = []
        for i,p in enumerate(profile):
            spread=1+(s-1)*widths[outline_kind]
            variation=math.sin(i*1.8+phase)*.014*math.sin(math.pi*f) if 1<k<15 else 0
            axial=f+(irregularity-1)*f*(1-f)*.73+variation
            q=p*spread+Vector((radius*drift,0,height*(axial+termination*.069*math.sin(i*1.53+phase))))
            if i==pinch and k in (10,11,12):
                q.x-=p.x*.115
                q.y-=p.y*.115
            ring.append(q)
        rings.append(ring)
    rings.append([Vector((radius*.23,-radius*.035,height))])
    ob = mesh(name,rings,mineral_finish(1),min(.004,radius*.014))
    ob.matrix_world = rotation
    for tone in (0,2):
        ob.data.materials.append(mineral_finish(tone))
    for f in ob.data.polygons:
        if 0<f.index<len(ob.data.polygons)-1:
            col,row=(f.index-1)%corners,(f.index-1)//corners
            f.material_index = (2,0,1,0,1,2)[col] if row not in (2,4,6,8,10,12) else 2

    if radius<.20:
        return
    for side,k in ((0,1),(corners-2,6),(corners-1,10)):
        def face_point(t,w):
            row = min(len(rings)-2,int(t))
            local = t-row
            right=(side+1)%corners
            p=rings[row][side].lerp(rings[row][right],w)
            q=rings[row+1][side].lerp(rings[row+1][right],w)
            normal=(rings[row][right]-rings[row][side]).cross(rings[row+1][side]-rings[row][side]).normalized()
            return p.lerp(q,local)+normal*radius*.004
        verts, faces = [], []
        for j in range(15):
            q = j/14
            t = k+q*3.85
            w=.37+.13*math.sin(3.6*q+side)+.049*math.sin(27*q+side)
            taper=.003+.019*math.sin(math.pi*q)
            verts.extend((face_point(t,w-taper),face_point(t,w+taper)))
            if j:
                a=j*2
                faces.append((a-2,a-1,a+1,a))
        data=bpy.data.meshes.new(name+" cleft")
        data.from_pydata(verts,[],faces)
        data.update()
        data.materials.append(cleft_material())
        fissure=vrlib.link_to_source(bpy.data.objects.new(name+" / faint mineral fissure",data))
        fissure.matrix_world=rotation


def blade(name, base, width, height, lean, roll, rng):
    prismatic_growth(name,base,height,width,lean,roll,rng,int(width<.70))


def talus(rng, index, x, y, r, h, z):
    n = rng.choice((5,6,7,8,9))
    angles = [i*math.tau/n + rng.uniform(-.16,.16) for i in range(n)]
    outline = [rng.uniform(.67, 1.18) for _ in angles]
    yaw, width, shear = rng.uniform(0,math.tau),rng.uniform(.49,.91),rng.uniform(-.46,.45)
    rings = [[(x+r*(s*outline[i]*math.cos(a+yaw)+shear*f), y+r*width*s*outline[i]*math.sin(a+yaw),
               max(-.051,z+(f+.30*f*math.sin(a+yaw))*h)) for i,a in enumerate(angles)]
             for f,s in ((-.12,.75),(.10,1),(.42,.995),(.49,.86),(.54,.94),(.85,.91),(1,.67))]
    mesh(f"Fault scree {index:02}",rings,("canyon_layered","monument_white","monument_weathered")[index%3],
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

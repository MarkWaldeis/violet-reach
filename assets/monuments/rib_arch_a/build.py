"""A dominant limestone vault and capped blades on a shared court."""
import math
import random

import bpy
from mathutils import Matrix, Vector

import vrlib
import vrmat


def limestone(name):
    if name in ("mossy_rock", "dirt_path", "grass_ground"):
        return vrmat.get(name)
    local_name = f"rib_arch_a.{name}"
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
        tone = mix(.48, tone, ramp(noise(2.3, 3), .28, .68, (weathered, pale)))
    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), .16, .86, ((.72,.72,.72),(.93,.93,.93))), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .023
    bump.inputs["Strength"].default_value = .42
    links.new(noise(10, 2), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return mat


def mesh(name, vertices, faces, stone):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(stone))
    return obj


PROFILE = (
    (.09, -.72), (.15, -.58), (.22, -.40), (.42, -.40), (.48, -.32),
    (.50, -.19), (.50, .17), (.47, .28), (.42, .35), (.25, .41), (0, .43),
    (-.25, .41), (-.42, .35), (-.47, .28), (-.50, .17), (-.50, -.19),
    (-.48, -.32), (-.42, -.40), (-.22, -.40), (-.15, -.58), (-.09, -.72),
)


def rib(name, spine, width, depth, rng):
    white = "monument_white"
    cuts = [0]
    while cuts[-1] < .88:
        cuts.append(min(.93,cuts[-1]+rng.uniform(.058,.112)))
    if cuts[-1]>.90:
        cuts.pop()
    cuts.append(1)
    run = list(zip(cuts,cuts[1:]))
    phase = rng.uniform(0,math.tau)

    def sweep(label, lo, hi, inset, final=False):
        slots = 26 if not inset else 130
        loss_site = rng.randrange(len(PROFILE))
        vertices = []
        for row in range(slots+1):
            u = row/slots
            t = lo+(hi-lo)*u
            point = spine(t)
            tangent = (spine(t+.0001)-spine(t-.0001)).normalized()
            flank = Vector((0,1,0))
            normal = tangent.cross(flank).normalized()
            flank = normal.cross(tangent).normalized()
            flare = (.19*math.exp(-((t-.07)/.11)**2)+.19*math.exp(-((t-.94)/.13)**2)
                     + (.14*math.exp(-((u-.66)/.46)**4) if final else 0))
            size = (1+flare) * (.925 if inset else 1)
            for j,(a,b) in enumerate(PROFILE):
                k = abs(math.remainder(j-loss_site,len(PROFILE)))
                spall = max(0,1-k/2.6)*max(0,1-u*6)*.11 if not inset else 0
                ridge = (.015*math.sin(phase+4*j+u*5)+.008*math.sin(9*j+u*18)
                         + .004*math.sin(17*j-u*43)) if not inset else 0
                dressing = .018*math.sin(3*j+u*16+phase)*math.sin(math.pi*u) if not inset else 0
                vertices.append(point+(flank*a*width+normal*b*depth)*size*(1-spall+ridge+dressing))
        n=len(PROFILE)
        faces=[tuple(reversed(range(n)))]
        for i in range(slots):
            for j in range(n):
                a,b=i*n+j,i*n+(j+1)%n
                faces.append((a,b,b+n,a+n))
        faces.append(tuple(range(len(vertices)-n,len(vertices))))
        obj = mesh(label,vertices,faces,white)
        for poly in obj.data.polygons[1:-1]:
            poly.use_smooth = True
        obj.data.set_sharp_from_angle(angle=math.radians(25))

    sweep(f"{name} pale solid seam core",.003,.995,True)
    for i,(lo,hi) in enumerate(run):
        gap = rng.uniform(.00027,.00052)
        sweep(f"{name} {'capstone' if i==len(run)-1 else 'segment'} {i+1}",
              lo+(gap if lo else 0),hi-(gap if hi<1 else 0),False,i==len(run)-1)


def foundation(name, x, y, width, depth, bands, rng, stone):
    n=54
    phase=rng.uniform(0,math.tau)
    vertices=[]
    for z,sx,sy in bands:
        for j in range(n):
            a=math.tau*j/n
            ca,sa=math.cos(a),math.sin(a)
            peen = 1+.022*math.sin(7*a+phase+.3*z)+.009*math.sin(18*a+.6*z)+.004*math.cos(27*a-z)
            outline_x=math.copysign(abs(ca)**.66,ca)*width*.5
            outline_y=math.copysign(abs(sa)**.66,sa)*depth*.5
            vertices.append((x+outline_x*peen*sx,y+outline_y*peen*sy,z))
    faces=[tuple(reversed(range(n)))]
    for i in range(len(bands)-1):
        for j in range(n):
            a,b=i*n+j,i*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
    faces.append(tuple(range(len(vertices)-n,len(vertices))))
    obj=mesh(name,vertices,faces,stone)
    for poly in obj.data.polygons[1:-1]:
        poly.use_smooth=True
    obj.data.set_sharp_from_angle(angle=math.radians(38))


def review_figure(x,y,z):
    guide = bpy.data.collections.new("Scale reference • not part of the asset")
    bpy.context.scene.collection.children.link(guide)
    cloth = bpy.data.materials.new("Scale reference vermilion")
    cloth.diffuse_color = (.52,.024,.018,1)
    cloth.use_nodes = True
    cloth.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = cloth.diffuse_color

    def limb(a,b,r0,r1):
        p,q = Vector((x+a[0],y+a[1],z+a[2])),Vector((x+b[0],y+b[1],z+b[2]))
        d = q-p
        bpy.ops.mesh.primitive_cone_add(vertices=16,radius1=r0,radius2=r1,depth=d.length,location=(p+q)*.5)
        obj=bpy.context.object
        obj.rotation_euler=d.to_track_quat("Z","Y").to_euler()
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        guide.objects.link(obj)
        obj.data.materials.append(cloth)

    limb((0,0,.79),(0,0,1.51),.225,.188)
    limb((0,0,1.49),(0,0,1.79),.116,.089)
    for side in (-1,1):
        limb((.098*side,0,.85),(.127*side,.02*side,.014),.082,.063)
        limb((.13*side,0,1.45),(.255*side,.04,1.05),.086,.061)


def build():
    rng=random.Random(38445)
    white,old="monument_white","monument_weathered"
    foundation("Common buried court",0,0,77,66,[(-.30,1,1),(.38,1,1),(.56,.97,.98)],rng,old)
    foundation("Shared crowned inner court",0,-3,65,49,[(.48,1,1),(.72,1,1),(1.02,.95,.96)],rng,white)
    for side in (-1,1):
        x=side*25
        foundation(f"Buried splayed root block {side}",x,0,22,48,
                   [(-.25,1,1),(.85,1,1),(1.42,.98,.98),(2.9,.92,.955)],rng,old)
        foundation(f"Weathered recessed root collar {side}",x,0,21,46,
                   [(2.89,.964,.995),(3.27,.948,.978),(3.57,.952,.981),(4.13,.946,.976)],rng,old)
        foundation(f"Massive rising limestone root body {side}",x,0,21,46,
                   [(4.10,.946,.976),(4.40,.946,.966),(6.70,.92,.91),
                    (8.95,.87,.86),(11.70,.74,.79),(13.10,.66,.74),(13.67,.62,.68)],rng,white)
        for j in range(12):
            y=-25+4.5*j
            px=x+side*rng.uniform(8.8,10.9)
            r=rng.uniform(1.4,2.7)
            foundation(f"Root ground talus {side} {j}",px,y,r,rng.uniform(1.8,3.7),
                       [(-.20,1,1),(.18,1,1),(rng.uniform(.28,.75),.67,.70)],rng,
                       "mossy_rock" if j%3 else "dirt_path")
    def arch(t):
        return Vector((-25.5*math.cos(math.pi*t),-5+2.8*math.sin(math.pi*t),11.6+62*math.sin(math.pi*t)))
    rib("Dominant through arch",arch,9.8,9.6,rng)
    for i,(x,y,side,reach,h,fan,w,d) in enumerate((
            (-25,-16,1,32,54,-7,8.3,7.1),(25,11,-1,25,46,9,7.7,6.0),
            (-25,8,1,12,32,7,6.5,5.6))):
        def blade(t):
            return Vector((x+side*(reach*max(0,t)**2.3-4*math.sin(math.pi*t)),
                           y+fan*max(0,t)**1.5,10.7+h*math.sin(1.37*t)))
        rib(f"Capped fan blade {i+1}",blade,w,d,rng)

    for side in (-1,1):
        foundation(f"Walk gate embedded pier {side}",side*4.3,-27.0,4.6,7.2,
                   [(-.18,1,1),(.43,1,1),(1.1,.95,.96),(2.75,.85,.93),(3.22,.83,.88)],rng,old)
    def portal(t):
        return Vector((-4.25*math.cos(math.pi*t),-27,2.94+4.3*math.sin(math.pi*t)))
    rib("Pedestrian outer-court vault",portal,5.8,2.28,rng)
    foundation("Entry walk sill",0,-32.7,6.2,7.7,[(-.19,1,1),(.17,1,1),(.31,.92,.96)],rng,white)
    orient=Matrix.Rotation(math.pi/2,4,"Z")
    for obj in vrlib.source_objects():
        obj.data.transform(orient)
    review_figure(34.5,-1.1,.31)

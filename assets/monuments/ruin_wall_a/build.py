"""A fractured retaining wall with surviving steps up to its rear walk."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    if name in ("mossy_rock", "dirt_path", "grass_ground"):
        return vrmat.get(name)
    local_name = f"ruin_wall_a.{name}"
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

    variation = noise(.87, 3)
    tone = ramp(variation, .23, .79, (cool, pale))
    random_tone = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(.18, tone, ramp(random_tone, 0, 1, (cool, pale)))
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    old = name == "monument_weathered"
    ao.inputs["Distance"].default_value = .19 if old else .065
    joint = tuple(.74*a+.26*b for a,b in zip(seam, cream))
    tone = mix(ao.outputs["AO"], joint, tone)
    if old:
        patina = palette["monument_shadow"]["linear_rgb"]
        weathered = tuple(.38*a+.62*b for a,b in zip(seam,patina))
        tone = mix(.76, tone, ramp(noise(2.3, 3), .40, .68, (weathered, pale)))
    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), .16, .86, ((.72,.72,.72),(.93,.93,.93))), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .023
    bump.inputs["Strength"].default_value = .42
    links.new(noise(10, 2), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return mat


def ashlar(name, bounds, rng, material, break_at=None, end_cut=0):
    x0,x1,y0,y1,z0,z1=bounds
    z0=max(-.059,z0)
    length,depth=x1-x0,y1-y0
    phase=rng.uniform(0,math.tau)
    bevel=min(.075,length*.17,depth*.17)
    corners=((x0+bevel,y0),(x1-bevel,y0),(x1,y0+bevel),(x1,y1-bevel),
             (x1-bevel,y1),(x0+bevel,y1),(x0,y1-bevel),(x0,y0+bevel))
    perimeter=[]
    for (a,b),(c,d) in zip(corners,corners[1:]+corners[:1]):
        count=max(1,math.ceil(math.hypot(c-a,d-b)/.095))
        perimeter.extend((a+(c-a)*i/count,b+(d-b)*i/count) for i in range(count))
    levels=16
    verts=[]
    for row in range(levels+1):
        t=row/levels
        for x,y in perimeter:
            u=(x-x0)/length
            v=(y-y0)/depth
            profile=math.sin(math.pi*t)
            loss=max(0,1-abs(u-.77-.095*math.sin(2*phase))/ .18)
            loss*=max(0,1-abs(v-.12)/.62)
            head=z1
            if break_at:
                run=u+.32*(v-.5)
                fault = .59+.27*math.sin(phase)
                head-=break_at*(.06+.53*abs(run-fault)+.20*abs(v-.28)+.46*max(0,u-v))
                head-=break_at*.42*max(0,1-abs(run-.36-.17*math.cos(phase))*2.7)
            head -= min(.105,(z1-z0)*.18)*loss
            head=max(z0+min(.065,(z1-z0)*.55),head)
            surface_t = 1 if break_at else t
            wear=(.009+.006*math.sin(8*x+3*y+phase+3*surface_t)
                  +.003*math.cos(22*x-14*y+17*surface_t)+.001*math.sin(43*y+37*surface_t))
            shrink=1-wear*(1 if break_at else profile)-.025*loss*surface_t**3
            x=(x0+x1)/2+(x-(x0+x1)/2)*shrink
            y=(y0+y1)/2+(y-(y0+y1)/2)*shrink
            if end_cut:
                side = max(0,2*u-1 if end_cut>0 else 1-2*u)
                cut = .22+.46*abs(surface_t-.47+.27*(v-.5))+.28*max(0,1-abs(v-.42)*4)
                x -= math.copysign(min(abs(end_cut),length*.37),end_cut)*side*cut
            verts.append((x,y,z0+(head-z0)*t))
    n=len(perimeter)
    faces=[tuple(reversed(range(n)))]
    for row in range(levels):
        for j in range(n):
            a,b=row*n+j,row*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
    top=len(verts)-n
    verts.append(((x0+x1)/2,(y0+y1)/2,sum(p[2] for p in verts[top:])/n))
    faces.extend((top+j,top+(j+1)%n,len(verts)-1) for j in range(n))
    data=bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces)
    data.update()
    obj=bpy.data.objects.new(name,data)
    vrlib.link_to_source(obj)
    data.materials.append(limestone(material))
    for face in data.polygons[1:1+levels*n]:
        face.use_smooth=True
    data.set_sharp_from_angle(angle=math.radians(24))


def build():
    rng=random.Random(13052)
    white,old="monument_white","monument_weathered"
    ashlar("Buried uninterrupted footing",(-5.08,5.03,-2.04,.14,-.25,.27),rng,old)

    def remnant(label, rows, side):
        for j,(z0,z1,limits,top_break) in enumerate(rows):
            x0,x1=limits[0],limits[-1]
            spall = side*(.11+.22*abs(math.sin(j*1.48+.5)))
            ashlar(f"{label} {j+1} solid recessed lime hearting",
                   (x0+.11,x1-.11,-1.54,-.29,z0-.016,z1-.004),rng,white,top_break,spall*.6)
            ashlar(f"{label} {j+1} recessed stone joint bed",
                   (x0+.057,x1-.061,-1.98,-.012,z0-.021,z0+.013),rng,white,end_cut=spall*.82)
            for i,(a,b) in enumerate(zip(limits,limits[1:])):
                y=-2.04+(.092 if (j,i) in ((2,1),(0,2)) else 0)
                if (j,i) in ((1,0),(3,1)):
                    y-=.117
                fracture=top_break*rng.uniform(.66,1.55) if top_break else None
                exposed = spall if (i==0 and side<0) or (i==len(limits)-2 and side>0) else 0
                ashlar(f"{label} face ashlar {j+1}.{i+1}",(a+.016,b-.019,y,-1.54,z0+.012,z1),
                       rng,old if j==0 else white,fracture,exposed)
                ashlar(f"{label} rear ashlar {j+1}.{i+1}",(a+.017,b-.016,-.29,.04,z0+.012,z1-.018),
                       rng,old if j==0 else white,fracture,exposed)

    remnant("West broken upright",[
        (.24,.97,(-4.95,-3.98,-2.73,-1.80),None),
        (.97,1.70,(-4.94,-3.67,-2.31,-1.84),None),
        (1.70,2.36,(-4.88,-4.16,-2.92,-1.87),None),
        (2.36,3.17,(-4.89,-3.84,-2.79,-2.05),None),
        (3.17,3.94,(-4.76,-3.59,-2.82,-2.39),None),
        (3.94,4.65,(-4.74,-4.02,-3.23,-2.62),None),
        (4.65,5.34,(-4.69,-4.07,-3.51),.83)],1)
    remnant("Tall freestanding central fracture",[
        (.24,.93,(-1.31,-.24,.85,1.90),None),
        (.93,1.67,(-1.12,-.03,.93,1.73),None),
        (1.67,2.31,(-.94,.06,1.17),None),
        (2.31,3.05,(-.58,.13,1.10),None),
        (3.05,3.69,(-.21,.36,.91),.72)],-1)
    remnant("East fractured return",[
        (.24,.92,(2.92,4.05,4.97),None),
        (.92,1.64,(3.13,3.72,4.92),None),
        (1.64,2.32,(3.23,4.34,4.91),None),
        (2.32,3.04,(3.61,4.04,4.91),None),
        (3.04,3.74,(3.84,4.32,4.92),None),
        (3.74,4.62,(4.18,4.91),.87)],-1)
    ashlar("Solid lower terrace bed",(-4.94,4.94,-.09,2.36,-.14,.30),rng,old)
    tread_depth,tread_count=.72,5
    terrace_edge=2.77-(tread_count-1)*tread_depth
    for i in range(tread_count):
        x0=2.77-i*tread_depth
        ashlar(f"Rear terrace tread {i+1}",(x0,x0+tread_depth,.16,2.27,.285,.50+i*.19),rng,white)
    ashlar("Solid upper terrace bed",(-4.97,terrace_edge+.045,-.09,2.30,.24,1.22),rng,white)
    for i,(a,b) in enumerate(zip((-4.97,-3.79,-2.65,-1.73),(-3.79,-2.65,-1.73,terrace_edge))):
        ashlar(f"Upper terrace paving {i+1}",(a+.012,b-.01,.12,2.38,1.23,1.36),rng,white,.12)

    for i,(x,y,length,depth,height) in enumerate((
            (-2.37,-2.48,1.09,.74,.49),(-1.33,-3.06,.79,.68,.44),(-.09,-2.43,.92,.66,.62),
            (1.31,-2.93,1.44,.76,.64),(2.15,-2.31,.70,.56,.39),(3.11,-2.68,1.13,.71,.54),
            (4.24,-2.48,.66,.55,.41),(-3.78,-2.60,.73,.56,.35),(2.25,.43,.67,.39,.32))):
        ashlar(f"Supported fallen matching ashlar {i+1}",(x-length/2,x+length/2,y-depth/2,y+depth/2,
               -.14,height),rng,white,.54*height)
    for i in range(23):
        x=rng.uniform(-4.8,4.8)
        y=-2.15-rng.uniform(.15,1.14)
        w=rng.uniform(.14,.37)
        ashlar(f"Buried foot rubble {i+1}",(x-w,x+w,y-w*.52,y+w*.63,-.15,rng.uniform(.06,.23)),
               rng,"mossy_rock" if i%4==0 else "dirt_path" if i%5==0 else old,.11)

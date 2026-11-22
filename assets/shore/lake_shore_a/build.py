"""A scalloped lake margin with a submerged shelf, sand and an undercut turf bank."""
import math
import random

import bpy
from mathutils import Vector

import vrlib
import vrmat


def mesh(name, verts, faces, materials, source=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    for mat in materials:
        data.materials.append(vrmat.get(mat) if isinstance(mat, str) else mat)
    ob = bpy.data.objects.new(name, data)
    if not source:
        bpy.context.scene.collection.objects.link(ob)
        ob["vr_review_context"] = True
        return ob
    return vrlib.link_to_source(ob)


def waterline(x):
    return -2.4 + .015*x*x + .38*math.sin(.43*x) + .10*math.sin(1.17*x+.53)


def bank_foot(x):
    return 3.58+.53*math.sin(x*.60+.8)+.27*math.sin(x*1.42-.7)


def smooth(t):
    t = min(1,max(0,t))
    return t*t*(3-2*t)


def height(x, d):
    wet = .075*d + .011*d*(1+math.sin(x*1.2-d*3.1))
    bank = bank_foot(x)
    amp = .40+.20*(.5+.5*math.sin(.68*x+.4))
    ledge = amp*smooth((d-bank)/(.85+.13*math.cos(x*1.6)))
    ripple = (.043*math.sin(x*1.15+d*4)+.020*math.sin(x*3.86-d*7))*smooth((d-1.5)/2)
    return -.047*math.tanh(-wet/.047) if wet<0 else wet+ledge+ripple


def finish(name, template, colors, roughness):
    mat = vrmat.get(template).copy()
    mat.name = name
    nodes,links = mat.node_tree.nodes,mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    socket = bsdf.inputs["Base Color"]
    coord=nodes.new("ShaderNodeTexCoord")
    noise=nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.3
    noise.inputs["Detail"].default_value = 5
    links.new(coord.outputs["Object"],noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    for el, color in zip(ramp.color_ramp.elements,colors):
        el.color = (*color,1)
    links.new(noise.outputs["Fac"],ramp.inputs[0])
    mix=nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = .82
    links.new(socket.links[0].from_socket,mix.inputs[1])
    links.new(ramp.outputs[0],mix.inputs[2])
    links.new(mix.outputs[0],socket)
    for link in list(bsdf.inputs["Roughness"].links):
        links.remove(link)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def distance_attribute(ob, distances, name):
    attr = ob.data.attributes.new(name,"FLOAT","POINT")
    attr.data.foreach_set("value",distances)


def transitions(mat, layers):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for layer, channel in layers:
        mask = nodes.new("ShaderNodeAttribute")
        mask.attribute_name = channel
        src = layer.node_tree
        mapping = {}
        for old in src.nodes:
            if old.type in {"BSDF_PRINCIPLED","OUTPUT_MATERIAL"}:
                continue
            new = nodes.new(old.bl_idname)
            mapping[old.name] = new
            for key in ("operation","blend_type","distance","feature","noise_dimensions"):
                if hasattr(old,key):
                    setattr(new,key,getattr(old,key))
            for i, socket in enumerate(old.inputs):
                if hasattr(socket,"default_value"):
                    new.inputs[i].default_value = socket.default_value
            if old.type=="VALTORGB":
                for a,b in zip(old.color_ramp.elements,new.color_ramp.elements):
                    b.position,b.color = a.position,a.color
        for link in src.links:
            if link.to_node.name in mapping and link.from_node.name in mapping:
                i=list(link.from_node.outputs).index(link.from_socket)
                j=list(link.to_node.inputs).index(link.to_socket)
                links.new(mapping[link.from_node.name].outputs[i],mapping[link.to_node.name].inputs[j])
        for socket_name in ("Base Color","Roughness"):
            socket = bsdf.inputs[socket_name]
            src_socket = src.nodes["Principled BSDF"].inputs[socket_name]
            mix = nodes.new("ShaderNodeMixRGB")
            links.new(mask.outputs["Fac"],mix.inputs[0])
            if socket.is_linked:
                links.new(socket.links[0].from_socket,mix.inputs[1])
            else:
                mix.inputs[1].default_value = (socket.default_value,)*3+(1,)
            if src_socket.is_linked:
                ls = src_socket.links[0].from_socket
                links.new(mapping[ls.node.name].outputs[ls.name],mix.inputs[2])
            else:
                mix.inputs[2].default_value = (src_socket.default_value,)*3+(1,)
            links.new(mix.outputs[0],socket)


def ground(sand,wet,earth,turf):
    nx,ny = 164,76
    vertices,faces = [],[]
    wetness,soil,grass = [],[],[]
    for j in range(ny+1):
        t = j/ny
        for i in range(nx+1):
            x = (i/nx-.5)*20.4
            d = -1.62+t*(7.98+.27*math.sin(.65*x)+.14*math.sin(1.8*x))
            y = waterline(x)+d
            bank = bank_foot(x)
            edge = bank+.79+.23*math.sin(x*1.6)+.13*math.cos(x*4.6+d)
            wet_end = 1.58+.24*math.sin(x*.68)+.10*math.sin(x*2.8+d*3)
            vertices.append((x,y,height(x,d)))
            wetness.append(1-smooth((d-wet_end+.48)/.71))
            soil.append(smooth((d-bank+.14+.09*math.sin(x*5.4+d*4))/.45))
            grass.append(smooth((d-edge+.18)/(.54+.11*math.sin(x*4))))
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i
            faces.append((a,a+1,a+nx+2,a+nx+1))
    rim = list(range(nx+1))
    rim.extend(j*(nx+1)+nx for j in range(1,ny+1))
    rim.extend(ny*(nx+1)+i for i in range(nx-1,-1,-1))
    rim.extend(j*(nx+1) for j in range(ny-1,0,-1))
    base = len(vertices)
    vertices.extend((vertices[i][0],vertices[i][1],-.059) for i in rim)
    for a,k in enumerate(rim):
        b=(a+1)%len(rim)
        faces.append((rim[b],k,base+a,base+b))
    faces.append(tuple(reversed(range(base,len(vertices)))))
    ob = mesh("Continuous sediment and turf profile",vertices,faces,(sand,earth))
    for pol in ob.data.polygons:
        pol.use_smooth = pol.index<nx*ny
        pol.material_index = int(not pol.use_smooth)
    for vals,name in ((wetness,"wet"),(soil,"soil"),(grass,"turf")):
        distance_attribute(ob,vals+[0]*len(rim),name)
    transitions(sand,((wet,"wet"),(earth,"soil"),(turf,"turf")))


def cobble(name,x,d,s,h,mat,rng):
    y = waterline(x)+d
    z0 = height(x,d)-.20*h
    n = rng.choice((6,7,8,10))
    yaw,ratio = rng.uniform(0,math.tau),rng.uniform(.51,.93)
    a = [yaw+i*math.tau/n+rng.uniform(-.18,.18) for i in range(n)]
    radii = [rng.uniform(.73,1.13) for _ in a]
    laminae = [rng.uniform(-.19,.13) for _ in a]
    dx,dy = rng.uniform(-.5,.5),rng.uniform(-.46,.46)
    levels = [(-.60,.66),(-.25,.96),(.10,1),(.32,.98),(.76,.82),(1,.64)]
    verts,faces = [],[tuple(reversed(range(n)))]
    scar = rng.randrange(n)
    for j,(v,r) in enumerate(levels):
        for i,(ang,r0) in enumerate(zip(a,radii)):
            f = r*r0*(.78 if i==scar and j>=3 else 1)
            z=z0+h*(v+laminae[i])
            verts.append((x+s*f*math.cos(ang)+dx*h*v,
                          y+s*f*math.sin(ang)*ratio+dy*h*v,
                          -.056*math.tanh(-z/.056) if z<0 else z))
        if j:
            k=(j-1)*n
            faces.extend((k+i,k+(i+1)%n,k+n+(i+1)%n,k+n+i) for i in range(n))
    faces.append(tuple(range(len(verts)-n,len(verts))))
    ob = mesh(name,verts,faces,(mat,))
    bevel = ob.modifiers.new("Water-softened fracture edges","BEVEL")
    bevel.width,bevel.segments = min(.019,s*.061,h*.105),3 if s>.35 else 2
    bevel.harden_normals = True


def grasses(rng):
    verts,faces,tones = [],[],[]
    pockets = [(-9.1,4.94,25,.62),(-7.95,5.65,35,.44),(-6.6,4.37,24,.90),
               (-4.65,5.14,46,.73),(-3.2,5.78,36,1.14),(-1.0,5.67,26,.59),
               (1.48,5.0,40,1.03),(3.4,4.48,26,.77),(5.6,5.72,48,.53),
               (6.85,5.1,16,1.44),(8.0,5.77,40,.79),(9.1,5.43,32,.65)]
    for cx,cd,count,size in pockets:
        for _ in range(count):
            t = rng.random()**1.6
            a = rng.uniform(0,math.tau)
            x = cx+t*math.cos(a)*rng.uniform(.4,1.14)
            d = cd+t*math.sin(a)*.58
            if d<bank_foot(x)+.76 or abs(x)>10.04:
                continue
            y,z = waterline(x)+d,height(x,d)-.017
            for j in range(rng.randint(4,13)):
                a = rng.uniform(0,math.tau)
                h = size*rng.uniform(.09,.46)
                w = rng.uniform(.008,.026)
                lean = h*rng.uniform(.28,.92)
                u,v = math.cos(a),math.sin(a)
                k = len(verts)
                for f,g in ((0,1),(.48,.77),(.83,.40)):
                    ex,ey = x+u*lean*f*f,y+v*lean*f*f
                    verts.extend(((ex-v*w*g,ey+u*w*g,z+h*f),
                                  (ex+v*w*g,ey-u*w*g,z+h*f*.96)))
                verts.append((x+u*lean,y+v*lean,z+h))
                faces.extend(((k,k+1,k+3,k+2),(k+2,k+3,k+5,k+4),(k+4,k+5,k+6)))
                tones.extend([int(rng.random()<.22)]*3)
    ob = mesh("Grouped sedges and dry leaf blades",verts,faces,("grass_ground","foliage_leaf"))
    for face, tone in zip(ob.data.polygons,tones):
        face.material_index = tone


def exposed_roots(rng):
    verts,faces = [],[]
    for cx in (-7.2,-4.1,.6,3.7,7.8):
        for j in range(rng.randint(9,16)):
            x = cx+rng.uniform(-.42,.42)
            d = bank_foot(x)+rng.uniform(.53,.84)
            length = rng.uniform(.26,.57)
            shift = rng.uniform(-.19,.22)
            k = len(verts)
            for section in range(6):
                t = section/5
                xi,di = x+shift*t+.025*math.sin(7*t),d-length*t
                center = Vector((xi,waterline(xi)+di-.018,height(xi,di)+.021-.050*t))
                r = (.014+.010*(j%3))*((1-t)*.80+.20)
                verts.extend(center+Vector((r*math.cos(a*math.tau/5),0,r*math.sin(a*math.tau/5)))
                             for a in range(5))
                if section:
                    b=k+(section-1)*5
                    faces.extend((b+a,b+5+a,b+5+(a+1)%5,b+(a+1)%5) for a in range(5))
            faces.append(tuple(k+25+a for a in range(5)))
    mesh("Exposed branching turf-root curtains",verts,faces,("tree_bark",))


def review_water():
    water = vrmat.get("water_opaque")
    verts,faces = [],[]
    nx = 120
    for i in range(nx+1):
        x = 20.4*(i/nx-.5)
        y=waterline(x)
        verts.extend(((x,y-4.9,0),(x,y-2.1,0),(x,y+.085,0)))
        if i:
            a = (i-1)*3
            faces.extend(((a,a+3,a+4,a+1),(a+1,a+4,a+5,a+2)))
    mesh("Review lake plane at Z=0 (not source)",verts,faces,(water,),False)
    scene=bpy.context.scene
    scene["vr_closeup_upper"] = (-2.6,waterline(-2.6)+.52,.14,243,36,10.3)
    scene["vr_closeup_base"] = (3.2,waterline(3.2)+3.23,.41,238,26,12.0)


def build():
    rng = random.Random(66539)
    sand = finish("Dry sand / warm and fine","dirt_path",((.29,.191,.101),(.54,.40,.24)),.87)
    wet_key=vrmat.load_palette()["shore_wet"]["linear_rgb"]
    wet_tone=tuple(a*b for a,b in zip(wet_key,(1.32,.91,.56)))
    wet = finish("shore_wet / saturated sand","dirt_path",(wet_tone,(.24,.154,.079)),.45)
    earth = finish("Open bank / umber soil","forest_soil",((.080,.044,.024),(.179,.106,.052)),.94)
    turf = vrmat.get("grass_ground")
    pale = finish("Dry shale / buff grey","canyon_layered",((.19,.16,.12),(.43,.39,.31)),.89)
    tide = finish("shore_wet / submerged slate","river_stones",((.078,.078,.068),(.21,.19,.15)),.39)
    ground(sand,wet,earth,turf)
    for i,(x,d,s,h) in enumerate(((-8.7,.24,.70,.24),(-8.07,.86,.48,.18),(-7.2,.43,.35,.16),
                                  (-3.6,.76,.35,.12),(-2.7,-.08,.68,.29),(-1.89,.43,.52,.19),
                                  (2.78,.08,.59,.24),(3.57,1.08,.79,.27),(4.37,.39,.30,.14),
                                  (7.32,-.05,.55,.22),(8.06,.61,.60,.22),(-7.6,4.6,.61,.24),
                                  (-5.13,3.63,.54,.22),(.96,4.39,.43,.18),(1.61,4.02,.68,.29),
                                  (7.86,4.82,.61,.29),(8.66,5.27,.45,.23))):
        cobble(f"Fractured bank cobble {i+1:02}",x,d,s,h,tide if d<1.32 else pale,rng)
    for i in range(420):
        cluster=(-8.25,-2.54,3.35,7.62)[i%4]
        if i<294:
            x,d=cluster+rng.gauss(0,.53),rng.gauss(.72,.42)
        elif i<345:
            x,d=rng.uniform(-9.9,9.9),rng.uniform(1.07,2.91)
        else:
            x=rng.uniform(-9.8,9.8)
            d=bank_foot(x)+rng.uniform(-.51,.61)
        s=rng.uniform(.023,.078)*(2.2 if i%11==0 else 1)
        cobble(f"Water-sorted shingle {i+1:03}",x,d,s,s*rng.uniform(.29,.61),tide if d<1.32 else pale,rng)
    grasses(rng)
    exposed_roots(rng)
    review_water()

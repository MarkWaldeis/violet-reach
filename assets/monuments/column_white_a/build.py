"""An eighteen-metre survey column, with reeded arrises and weathered drum joints."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    if name in ("mossy_rock", "dirt_path", "grass_ground"):
        return vrmat.get(name)
    local_name = f"column_white_a.{name}"
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
        tone = mix(.73, tone, ramp(noise(2.3, 3), .39, .68, (weathered, pale)))
    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), .16, .86, ((.72,.72,.72),(.93,.93,.93))), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .023
    bump.inputs["Strength"].default_value = .42
    links.new(noise(10, 2), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return mat


def turn_stone(name, profile, rng, stone, fluted=False, sides=512, damage=(), petal=0, phase=0):
    verts = []
    for z, radius, cut in profile:
        span = (z-profile[0][0])/(profile[-1][0]-profile[0][0])
        for i in range(sides):
            a = math.tau*i/sides
            sector = i*16/sides
            distance = abs(sector-round(sector))/.362
            flute = ((1-distance**4)**.72 if distance < 1 else 0) * cut if fluted else 0
            r = radius-flute
            r += (.010*math.sin(7*a+.8*z+phase)+.004*math.cos(23*a-z*2)+.002*math.sin(43*a+z*3)) * math.sin(math.pi*span)
            r += petal*math.sin(math.pi*span)**2 * (.52+.48*math.cos(8*a))**3
            for ca,cz,arc,height,loss,slope in damage:
                u = (z-cz)/height
                fault = ca+slope*u+.05*math.sin(5*u)
                edge = abs(math.remainder(a-fault,math.tau))/arc
                r -= loss*max(0,1-abs(u))*max(0,1-edge)
            verts.append((r*math.cos(a),r*math.sin(a),z))
    faces = [tuple(reversed(range(sides)))]
    for k in range(len(profile)-1):
        for j in range(sides):
            a,b = k*sides+j,k*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
    faces.append(tuple(range(len(verts)-sides,len(verts))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj = bpy.data.objects.new(name,mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(stone))
    for face in mesh.polygons[1:-1]:
        face.use_smooth=True
    mesh.set_sharp_from_angle(angle=math.radians(38))


def build():
    rng=random.Random(66517)
    white,old="monument_white","monument_weathered"
    turn_stone("Weathered buried foot", [(-.21,2.48,0),(.12,2.49,0),(.25,2.49,0),(.43,2.44,0),
               (.53,2.37,0),(.60,2.27,0)], rng, old, damage=((.33,.40,.26,.32,.25,.2),(2.1,.51,.28,.26,.19,.22)))
    turn_stone("Chipped lower torus and scotia",[(.59,2.25,0),(.66,2.30,0),(.76,2.34,0),(.86,2.31,0),
               (.98,2.21,0),(1.07,2.00,0),(1.16,1.94,0),(1.24,1.96,0),(1.31,2.01,0),
               (1.39,1.96,0),(1.50,1.73,0)],rng,white,damage=((.74,.84,.23,.31,.24,.17),(-1.3,1.13,.14,.25,.18,-.30)))
    heights=(1.48,2.94,5.42,7.61,9.05,11.94,13.76,15.53,16.51)

    def radii(z):
        t=(z-1.48)/15.03
        depth=.255*min(1,max(0,t)*12,max(0,1-t)*11)
        return 1.70-.61*t+.103*math.sin(math.pi*t),depth

    for i,(lo,hi) in enumerate(zip(heights,heights[1:])):
        z0,z1=lo+.009,hi-.009
        phase=rng.uniform(0,math.tau)
        samples=sorted({z0,z0+.025,z1-.025,z1,*(z0+(z1-z0)*j/43 for j in range(1,43))})
        profile=[]
        for z in samples:
            radius,depth=radii(z)
            edge=.018 if z in (z0,z1) else 0
            profile.append((z,radius-edge,depth))
        alpha=(.62,1.14,-.71,.56,2.12,.44,-1.75,.9)[i]
        loss=(.18,.08,.17,.10,.20,.10,.15,.13)[i]
        damage=((alpha,z1,.24,.25,loss,.20),
                (alpha+.30,lo+.54*(hi-lo),.071,.48*(hi-lo),.102,.41),
                (alpha-1.4,lo+.25*(hi-lo),.115,.24,.09,-.17))
        turn_stone(f"Aligned shaft drum {i+1}",profile,rng,white,True,damage=damage,phase=phase)
        radius,depth=radii(lo)
        turn_stone(f"Recessed fluted bedding {i+1}",[(lo-.018,radius-.066,depth),
                   (lo+.018,radius-.066,depth)],rng,old,True,phase=0)
    turn_stone("Necking and raised double neck ring",[(16.49,1.09,0),(16.57,1.15,0),(16.63,1.23,0),
               (16.76,1.23,0),(16.82,1.16,0),(16.93,1.16,0),(16.99,1.31,0),(17.11,1.31,0)],rng,white,
               damage=((.58,16.76,.18,.16,.17,.26),))
    turn_stone("Deep ribbed bell echinus",[(17.09,1.20,0),(17.18,1.22,0),(17.29,1.25,0),(17.40,1.32,0),
               (17.53,1.44,0),(17.68,1.61,0),(17.81,1.82,0),(17.91,1.98,0),(17.99,2.01,0)],
               rng,white,petal=.25,damage=((.9,17.90,.16,.24,.14,-.42),))
    turn_stone("Deep stepped abacus",[(17.97,2.02,0),(18.04,2.13,0),(18.13,2.18,0),
               (18.29,2.18,0),(18.36,2.09,0)],rng,white,damage=((.49,18.33,.18,.24,.22,-.25),))
    for i in range(9):
        a=.27+i*.63
        x,y=2.45*math.cos(a),2.45*math.sin(a)
        local=rng.uniform(.12,.33)
        n=12
        verts=[(x+local*s*math.cos(j*math.tau/n),y+local*s*math.sin(j*math.tau/n),z)
               for z,s in ((-.14,1),(.06,1),(.14,.57)) for j in range(n)]
        polygons=[tuple(reversed(range(n)))]+[(k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j)
                  for k in range(2) for j in range(n)]+[tuple(range(2*n,3*n))]
        data=bpy.data.meshes.new(f"Root talus {i}")
        data.from_pydata(verts,[],polygons)
        obj=bpy.data.objects.new(data.name,data)
        vrlib.link_to_source(obj)
        data.materials.append(limestone("mossy_rock" if i%3 else "dirt_path"))

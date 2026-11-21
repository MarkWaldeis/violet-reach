"""A broken limestone plateau, hanging over a tapered sequence of bedding planes."""
import math
import random

import bpy

import vrlib
import vrmat


MATERIALS = ("canyon_layered", "monument_weathered", "mossy_rock", "grass_ground", "forest_soil")


def mesh(name, rings, bands, smooth_from=None):
    n = len(rings[0])
    faces = [tuple(reversed(range(n)))]
    for j in range(len(rings)-1):
        a, b = j*n, (j+1)*n
        for i in range(n):
            k = (i+1) % n
            faces.append((a+i,a+k,b+k,b+i))
    faces.append(tuple(range((len(rings)-1)*n,len(rings)*n)))
    data = bpy.data.meshes.new(name)
    data.from_pydata([v for ring in rings for v in ring], [], faces)
    data.update()
    for material in MATERIALS:
        data.materials.append(vrmat.get(material))
    for poly in data.polygons[1:-1]:
        j, i = divmod(poly.index-1,n)
        poly.material_index = bands[j][i] if isinstance(bands[j],list) else bands[j]
        poly.use_smooth = smooth_from is not None and j >= smooth_from
    data.polygons[-1].material_index = 3 if smooth_from is not None else 0
    return vrlib.link_to_source(bpy.data.objects.new(name, data))


def outline(vertices, divisions, rng):
    result = []
    for i,(x,y) in enumerate(vertices):
        xx,yy = vertices[(i+1)%len(vertices)]
        for j in range(divisions):
            t = j/divisions
            shift = rng.uniform(-.022,.024) if j else 0
            result.append(((x+(xx-x)*t)*(1+shift),(y+(yy-y)*t)*(1+shift)))
    return result


def turf_z(x,y):
    summit = 21*math.exp(-((x+.29)**2*4.7+(y-.14)**2*7.8))
    shoulder = 8*math.exp(-((x+.37)**2*8+(y+.40)**2*8))
    basin = 9*math.exp(-((x-.33)**2*16+(y+.21)**2*13))
    return 132+5.0*x-2.4*y+summit+shoulder-basin+1.9*math.sin(3*x+2*y)*math.sin(3*y)


def plateau(rng):
    perimeter = outline([(1,.05),(.84,.38),(.66,.45),(.62,.68),(.15,.94),(-.31,.92),
                         (-.67,.68),(-.93,.38),(-1,-.18),(-.82,-.67),(-.39,-1),
                         (.04,-.99),(.43,-.75),(.59,-.49),(.46,-.24),(.79,-.16)], 7,rng)
    strata = [
        (  0,.11,-39,-13,0),(  5,.20,-39,-13,0),( 11,.27,-37,-12,0),
        ( 13,.245,-35,-12,1),( 18,.32,-35,-10,0),( 24,.37,-34,-10,0),
        ( 27,.367,-32,-10,1),( 29,.40,-32,-10,0),( 35,.46,-30,-10,0),
        ( 39,.48,-28,-10,0),( 41,.461,-27,-9,1),( 44,.505,-27,-8,1),
        ( 48,.53,-25,-8,0),( 55,.580,-24,-8,0),( 57,.562,-25,-8,1),
        ( 59,.596,-22,-8,0),( 66,.63,-18,-9,0),( 70,.67,-16,-8,0),
        ( 72,.651,-16,-8,1),( 75,.71,-13,-8,1),( 78,.752,-13,-8,0),
        ( 87,.783,-11,-7,0),( 92,.811,-9,-4,0),( 94,.782,-9,-3,1),
        ( 97,.829,-8,-3,1),(100,.883,-5,-2,0),(106,.906,-4,-2,0),
        (109,.905,-3,-2,1),(113,.939,-2,-1,0),(126,.967,0,0,0),
        (131,.988,0,0,0),(133,1.0,0,0,2),(135,.957,0,0,2),
    ]
    rings, bands = [], []
    heights = [0.11*x+.059*math.sin(4*x+2*y)+.08*math.cos(5*y) for x,y in perimeter]
    for j,(z,r,dx,dy,mat) in enumerate(strata):
        row = []
        for i,(x,y) in enumerate(perimeter):
            fault = .010*math.sin(i*2.38)+.020*math.sin(i*.58 + .036*z)+.011*math.cos(i*.2-z*.11)
            fault += .061*math.tanh(2.7*math.sin(i*.24 + z*.016))*math.sin(z*.036)
            if z>108:
                fault *= .6
            s = r*(1+fault)
            px,py = x*s+dx/140,y*s+dy/91
            edge = min(1,max(0,(z-102)/33))
            zw = (1-edge)*(z + min(z*.4,25)*heights[i]+min(z*.6,1.8)*math.sin(i*.71+z*.077))
            row.append((140*px,91*py,zw+edge*(turf_z(px,py)+z-135)))
        rings.append(row)
        if j:
            bands.append([mat if mat!=1 or math.sin(i*.099+j*.31)>-.23 else 0 for i in range(len(perimeter))])
    start = len(rings)-1
    for step in range(1,21):
        r = 1-step/21
        turf = []
        for i,(px,py,_) in enumerate(rings[start]):
            x,y = px*r/140,py*r/91
            turf.append((140*x,91*y,turf_z(x,y)))
        rings.append(turf)
        bands.append([3 if step>2 or math.sin(i*.31+step)>.05 else 4 for i in range(len(perimeter))])
    mesh("Main plateau / bedrock and grassy escarpment",rings,bands,start)


def shard(name, x, y, z, rx, ry, h, yaw, rng, cap=False):
    p = outline([(1,.12),(.55,.83),(-.38,1),(-.90,.62),(-1,-.41),(-.38,-.92),(.51,-.89)],3,rng)
    heights = [rng.uniform(-.10,.10) for _ in p]
    shape = [(0,.15),( .12,.27),(.22,.41),(.26,.38),(.34,.58),(.47,.63),(.50,.59),(.57,.71),
             (.69,.78),(.73,.75),(.79,.91),(.91,.97),(.95,1),(1,.92),(1.04,.72),(1.06,.39)]
    cr,sr = math.cos(yaw),math.sin(yaw)
    rings = []
    for i,(t,s) in enumerate(shape):
        rings.append([(x+s*(rx*u*cr-ry*v*sr)+(t-1)*.29*rx,
                       y+s*(rx*u*sr+ry*v*cr)-(t-1)*.18*ry,
                       z+h*(t+heights[j]*min(1,t*3)+.021*t*math.sin(j*.83+i*.39))) for j,(u,v) in enumerate(p)])
    mesh(name,rings,[3 if cap and i>=13 else (1 if i in (2,5,8,11) else 0) for i in range(len(rings)-1)],
         13 if cap else None)


def build():
    rng = random.Random(970146)
    plateau(rng)
    for i, args in enumerate(((154,24,62,19,18,55,-.28,True), (129,38,48,9,10,26,.31,False),
                              (141,55,42,6,5,19,.68,False),(-135,-47,48,14,8,43,-.6,False),
                              (-156,-43,40,7,6,18,.9,False),(-123,-62,34,4,5,12,-.2,False),
                              (54,-73,58,26,10,54,-.31,False),(84,-71,79,22,11,48,-.33,False),
                              (-75,-63,63,18,11,64,-.5,False),(17,70,63,30,11,62,.21,False),
                              (-91,55,78,25,12,56,-.49,False))):
        shard(f"Fractured bedding block {i+1:02}",*args[:-1],rng,args[-1])
    for i in range(38):
        cx,cy = ((-53,-4),(12,26),(45,-27))[i%3]
        x,y = cx+rng.uniform(-21,21), cy+rng.uniform(-11,11)
        z = turf_z(x/140,y/91)
        s = rng.uniform(.75,2.5) if i%6 else rng.uniform(4.4,6.5)
        shard(f"Summit outcrop {i+1:02}",x,y,z-s*.34,s,s*rng.uniform(.58,.94),s*rng.uniform(.8,1.7),
              rng.uniform(0,math.tau),rng)

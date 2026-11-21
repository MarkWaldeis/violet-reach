"""A shallow lake margin: low wet shingle, sand, and a scalloped meadow bank."""
import math
import random

import bpy

import vrlib
import vrmat


def make_mesh(name, verts, faces, materials):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    for name_ in materials:
        data.materials.append(vrmat.get(name_))
    return vrlib.link_to_source(bpy.data.objects.new(name, data))


def shoreline(x):
    return -2.38 + .014*x*x + .47*math.sin(.37*x) + .13*math.sin(1.15*x+.53)


def margin(x):
    return 4.10 + .58*math.sin(.5*x+.91) + .22*math.sin(1.32*x+.3)


def height(x, t):
    if t < .13:
        land = -.049 + .051*t/.13
    elif t < .60:
        land = .002 + (t-.13)/.47*.20
    else:
        s = (t-.60)/.40
        land = .20 + .77*s*s*(3-2*s)
    rel = (.042*math.sin(x*.83+t*8)+.031*math.cos(x*1.66+t*14)+.013*math.sin(x*3.8+t*18))
    end = min(1,max(0,(10.1-abs(x))/1.0))
    bank = min(1,max(0,(1-t)/.13))
    taper = end*bank
    shoulder = .018*max(0, t-.5)
    return max(-.049,shoulder+taper*(land+rel*min(1,t*2.4)*(.4+.6*t)-shoulder)
               - .049*max(0,1-t/.13)*(1-taper))


def ground():
    nx, ny = 100, 40
    vertices, faces, indices = [], [], []
    for j in range(ny+1):
        t = j/ny
        for i in range(nx+1):
            s = i/nx
            x = (s-.50)*20.6 + .39*math.sin(t*5.8+.2)*math.cos(s*math.pi)
            y = shoreline(x)+t*(margin(x)-shoreline(x))
            vertices.append((x,y,height(x,t)))
    for j in range(ny):
        for i in range(nx):
            a = j*(nx+1)+i
            faces.append((a,a+1,a+nx+2,a+nx+1))
            x,t = (i/nx-.5)*20.6,(j+.5)/ny
            green = .69 + .085*math.sin(x*.59)+.043*math.sin(1.91*x+.31)+.028*math.cos(3.26*x)
            fluctuation = .021*math.sin(6.8*x+j*1.66)+.014*math.cos(11.6*x-j*.87)
            indices.append(0 if t<green+fluctuation else
                           (1 if t<green+.035 and math.sin(2.7*x+j*.63)>.46 else 2))
    rim = list(range(nx+1))
    rim.extend(j*(nx+1)+nx for j in range(1,ny+1))
    rim.extend(ny*(nx+1)+i for i in range(nx-1,-1,-1))
    rim.extend(j*(nx+1) for j in range(ny-1,0,-1))
    start = len(vertices)
    vertices.extend((vertices[i][0],vertices[i][1],-.055) for i in rim)
    for a,k in enumerate(rim):
        b=(a+1)%len(rim)
        faces.append((rim[b],k,start+a,start+b))
        indices.append(0 if a<nx else 1)
    faces.append(tuple(reversed(range(start,len(vertices)))))
    indices.append(1)
    ob = make_mesh("Continuous sand-to-turf shore profile",vertices,faces,
                   ("dirt_path","forest_soil","grass_ground"))
    for poly,material in zip(ob.data.polygons,indices):
        poly.material_index = material
        poly.use_smooth = poly.index < nx*ny


def stone(name, x, t, size, h, yaw, rng, material):
    y = shoreline(x)+t*(margin(x)-shoreline(x))
    z = height(x,t)-.07*h
    n = 9
    angle = [yaw+i*math.tau/n+rng.uniform(-.12,.12) for i in range(n)]
    width = [rng.uniform(.78,1.13) for _ in angle]
    pitch = [rng.uniform(-.23,.10) for _ in angle]
    vertices, faces = [], [tuple(reversed(range(n)))]
    cy = rng.uniform(.53,.83)
    for row,(f,r) in enumerate(((-.52,.57),(-.24,.82),(.04,1),(.31,.975),(.62,.86),(.87,.64),(1,.36))):
        for i,a in enumerate(angle):
            vertices.append((x+size*(r*width[i]*math.cos(a)-f*.11),
                             y+size*(r*width[i]*math.sin(a)*cy+f*.13),
                             max(-.055,z+h*(f+pitch[i]*r*max(.2,f)))))
        if row:
            a,b=(row-1)*n,row*n
            faces.extend((a+i,a+(i+1)%n,b+(i+1)%n,b+i) for i in range(n))
    faces.append(tuple(range(len(vertices)-n,len(vertices))))
    ob = make_mesh(name,vertices,faces,(material,))
    for poly in ob.data.polygons:
        poly.use_smooth = True


def tussocks(rng):
    verts, faces = [], []
    for cx,t0,density in ((-8.2,.84,24),(-6,.79,39),(-3.4,.93,24),(.2,.82,42),
                          (3.3,.75,33),(6.1,.88,44),(8.5,.80,29)):
        for _ in range(density):
            s = rng.uniform(0,math.tau)
            r = rng.uniform(.05,1)
            x = cx+1.28*r*math.cos(s)
            t = t0+.072*r*math.sin(s)
            y = shoreline(x)+t*(margin(x)-shoreline(x))
            z = height(x,t)-.019
            for j in range(rng.randint(4,10)):
                az = rng.uniform(0,math.tau)
                l = rng.uniform(.085,.29)
                w = rng.uniform(.008,.024)
                lean = l*rng.uniform(.26,.75)
                dx,dy = math.cos(az),math.sin(az)
                u,v = -dy*w,dx*w
                a = len(verts)
                verts.extend(((x-u,y-v,z),(x+u,y+v,z),
                              (x+dx*lean*.43+u*.58,y+dy*lean*.43+v*.58,z+l*.65),
                              (x+dx*lean*.43-u*.58,y+dy*lean*.43-v*.58,z+l*.65),
                              (x+dx*lean,y+dy*lean,z+l)))
                faces.extend(((a,a+1,a+2,a+3),(a+3,a+2,a+4)))
    make_mesh("Reedlike grass tufts on dry bank",verts,faces,("grass_ground",))


def build():
    rng = random.Random(66539)
    ground()
    for i,(x,t,s,h) in enumerate(((-8.35,.17,.69,.38),(-7.85,.23,.51,.32),(-6.86,.11,.46,.23),
                                   (-3.58,.20,.43,.27),(-2.82,.13,.60,.28),(-2.34,.18,.81,.38),
                                   (2.76,.14,.67,.31),(3.58,.25,.89,.43),(4.37,.13,.38,.24),
                                   (7.42,.22,.42,.24),(8.05,.16,.61,.29),(-7.70,.84,.55,.29),
                                   (-5.54,.74,.44,.22),(.99,.76,.57,.27),(1.68,.80,.72,.39),
                                   (7.74,.75,.64,.40),(8.61,.88,.41,.29))):
        stone(f"Bank cobble {i+1:02}",x,t,s,h,rng.uniform(0,math.tau),rng,
              "river_stones" if t<.3 else "mossy_rock")
    for i in range(213):
        band = rng.random()
        cx = (-8,-3,3.5,7.7)[i%4]
        if band<.73:
            x,t = cx+rng.uniform(-1.26,1.26),rng.uniform(.086,.36)
        elif band<.89:
            x,t = rng.uniform(-9.65,9.65),rng.uniform(.21,.58)
        else:
            x,t = rng.uniform(-9.65,9.65),rng.uniform(.73,.92)
        s = rng.uniform(.027,.13)*(1.7 if i%7==0 else 1)
        stone(f"Shingle {i+1:03}",x,t,s,s*rng.uniform(.36,.9),rng.uniform(0,math.tau),rng,
              "river_stones" if t<.32 else ("canyon_layered" if t<.68 else "mossy_rock"))
    tussocks(rng)

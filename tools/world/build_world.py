"""Deterministic metre-scale world. Run with Blender; no third-party packages beyond numpy."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import struct
import sys
import time
import zlib

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'world'
SEED = 73129
AXES = 'Runtime: X east, Y up, Z south; Blender (x,y,z) = runtime (x,-z,y). Distances in metres.'
REGIONS = [
    ('lyrenschlucht', 'Lyrenschlucht', (-2450, 2200), 'Grüne Schlucht mit hohen Felspfeilern; Säulenruinen und violette Kristallnester.'),
    ('aschgrat', 'Aschgrat-Canyon', (1900, 2350), 'Gewundener tiefer Einschnitt im Hochplateau; künftige Bogenbrücken und Felsentore.'),
    ('dornengang', 'Dornengang', (-2200, -2450), 'Enger Pass zwischen steilen Graten; Wächtertore und Kristallspitzen.'),
    ('weisswall', 'Weißwall', (-2400, 0), 'Lange helle Steilstufe mit Wasserfall; Platz für ein weißes Monumentaltor.'),
    ('mondsichel', 'Mondsichel', (2500, -1000), 'Sichelförmiger Bergkamm um ein grünes Tal; Aussichtstempel auf dem Grat.'),
    ('spiegelsee', 'Spiegelsee', (450, -1250), 'Rundes Seebecken, Wiesen und Wald; sanfter zentraler Wanderstart, Uferpavillon.'),
]


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def noise(x, y, scale, salt=0):
    x, y = x / scale, y / scale
    ix, iy = np.floor(x), np.floor(y)
    u, v = x - ix, y - iy
    u, v = u*u*(3-2*u), v*v*(3-2*v)
    def hashed(a, b):
        q = np.sin(a*127.1 + b*311.7 + SEED + salt*19.3)*43758.5453
        return q - np.floor(q)
    return ((hashed(ix, iy)*(1-u) + hashed(ix+1, iy)*u)*(1-v)
            + (hashed(ix, iy+1)*(1-u) + hashed(ix+1, iy+1)*u)*v)*2-1


def terrain(x, y):
    wx = x + 160*noise(x, y, 1100, 11)
    wy = y + 160*noise(x, y, 1100, 12)
    h = np.full(np.broadcast_shapes(x.shape, y.shape), 275, dtype=np.float32)
    for scale, amp in [(1800, 120), (850, 75), (360, 32), (150, 14), (65, 6), (25, 2)]:
        h += amp*noise(wx, wy, scale, int(scale))
    # Elevated northern plateau with a 200–400 m incision.
    plateau = np.exp(-((wx-1800)/2000)**4-((wy-2300)/1500)**4)
    h += 340*plateau
    canyon_x = 1750 + 420*np.sin(wy/530) + 140*np.sin(wy/230)
    h -= 335*np.exp(-((wx-canyon_x)/175)**4)*plateau
    # Pillar gorge: broad floor, separated tapered towers.
    g = np.exp(-((wx+2350)/1050)**4-((wy-2150)/1100)**4)
    h -= 85*g
    crag_x,crag_y = x+18*noise(x,y,85,22),y+18*noise(x,y,85,23)
    for px, py, radius, height in [(-2900,2400,120,340),(-2380,2650,100,390),(-1910,2300,140,310),(-2650,1700,115,370),(-2070,1550,95,340),(-3100,1950,85,300),(-1600,2900,110,350),(-2250,2050,80,280)]:
        h += height*np.exp(-(((crag_x-px)**2+(crag_y-py)**2)/radius**2)**1.3)
    # Long west-facing plateau edge; the crossing river drops through this wall.
    wall = np.exp(-((y-50)/1550)**6)
    edge = -1450 + 100*np.sin(y/450)
    h += 280*(1-np.tanh((wx-edge)/65))/2*wall
    # Two continuous, knuckled ridges flank a narrow southern pass.
    path = -2150 + 190*np.sin(y/390)
    band = np.exp(-((y+2400)/1250)**6)
    for offset in (-330, 330):
        h += 330*np.exp(-((wx-path-offset)/180)**2)*band*(0.85+0.15*noise(x,y,260,7))
    # An open crescent: arc ends taper rather than close into a crater.
    dx, dy = wx-2350, wy+1150
    r = np.sqrt(dx*dx+dy*dy)
    angle = np.arctan2(dy, dx)
    arc = np.clip((angle+2.2)/0.5,0,1)*np.clip((2.7-angle)/0.5,0,1)
    h += 400*np.exp(-((r-1000-65*noise(wx,wy,300,5))/190)**2)*arc
    # Pleasant gently rolling centre; no mountains at the walking spawn.
    meadow = np.exp(-((x-50)/900)**4-((y+200)/1000)**4)
    h = h*(1-meadow) + (210+18*noise(x,y,500,4))*meadow
    # Irregular mountain backdrop, entirely inside the world extent.
    rim = np.clip((np.maximum(abs(wx),abs(wy))-3250)/850,0,1)
    h += rim**1.6*(560+240*(1-abs(noise(wx,wy,430,90)))+90*(1-abs(noise(wx,wy,150,91))))
    rough = np.clip((h-380)/200,0,1)
    h += rough*(20*noise(x,y,95,71)+9*noise(x,y,35,72))
    return h.astype(np.float32)


def region_indices(x, y):
    wx = x+190*noise(x,y,740,41)
    wy = y+190*noise(x,y,740,42)
    distances = [((wx-c[0])/sx)**2+((wy-c[1])/sy)**2 for (_,_,c,_),sx,sy in zip(REGIONS,[1,1,1,0.85,1,1.3],[1,1,1,0.85,1,1.15])]
    return np.argmin(distances,axis=0).astype(np.uint8)+1


def smooth_path(controls):
    # Catmull-Rom in XY; linear height interpolation preserves monotonicity.
    a = np.asarray(controls, dtype=float)
    result = []
    for i in range(len(a)-1):
        p0,p1,p2,p3 = a[max(0,i-1)],a[i],a[i+1],a[min(len(a)-1,i+2)]
        steps = max(2, int(np.linalg.norm(p2[:2]-p1[:2])/35))
        for t in np.linspace(0,1,steps,endpoint=False):
            xy = .5*((2*p1[:2])+(-p0[:2]+p2[:2])*t+(2*p0[:2]-5*p1[:2]+4*p2[:2]-p3[:2])*t*t+(-p0[:2]+3*p1[:2]-3*p2[:2]+p3[:2])*t**3)
            result.append([*xy, *((1-t)*p1[2:]+t*p2[2:])])
    return np.array(result+[a[-1].tolist()])


def hydrology():
    rivers = [
        ('Weißfall', [(-3250,650,450,24),(-2400,450,440,30),(-1640,350,420,32),(-1410,300,280,33),(-1150,200,235,35),(-450,-450,210,38),(200,-1150,185,42),(650,-1630,180,46)]),
        ('Aschenlauf', [(2200,3300,355,20),(1910,2800,310,24),(1330,2400,290,26),(1410,1900,270,28),(1800,1300,245,32),(1200,500,220,35),(1100,-500,195,40),(1000,-1460,180,46)]),
        ('Dornbach', [(-2300,-1550,288,18),(-2100,-2150,250,22),(-1700,-2950,220,28),(-650,-2800,200,32),(550,-2150,180,38)]),
        ('Spiegelstrom', [(1200,-2050,180,46),(1700,-2500,170,52),(2100,-2800,153,55),(2550,-3000,140,58),(3100,-3400,125,62),(3600,-3900,110,65),(3800,-4096,100,70)]),
    ]
    lakes = [('Spiegelsee',900,-1900,520,180),('Hirschweiher',-650,-2800,190,200),('Aschenauge',1910,2800,160,310)]
    paths = [(n,smooth_path(p)) for n,p in rivers]
    for _,p in paths:
        distance = np.r_[0,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
        tangent = np.gradient(p[:,:2],axis=0)
        normal = np.column_stack((-tangent[:,1],tangent[:,0]))
        normal /= np.linalg.norm(normal,axis=1)[:,None]
        meander = (55*np.sin(distance/185)+21*np.sin(distance/79))*np.sin(np.pi*distance/distance[-1])**2
        p[:,:2] += normal*meander[:,None]
        p[:,3] *= 1.6*(1+.18*np.sin(distance/125)+.09*np.sin(distance/51))
        for _,cx,cy,r,level in lakes:
            inside = np.hypot(p[:,0]-cx,p[:,1]-cy)<r*.98
            p[inside,2] = level
        p[:,2] = np.minimum.accumulate(p[:,2])
    return paths, lakes


def carve(h, axis, rivers, lakes):
    spacing = float(axis[1]-axis[0])
    xx,yy = np.meshgrid(axis,axis)
    for _,cx,cy,r,level in lakes:
        d = np.sqrt((xx-cx)**2+(yy-cy)**2)
        target = level-17+23*(d/r)**6
        weight = np.clip((r*1.35-d)/(r*.25),0,1)
        h[:] = h*(1-weight)+np.maximum(target,level-19)*weight
    del xx,yy
    for _, points in rivers:
        distance = np.full(h.shape,np.inf,dtype=np.float32)
        water = np.zeros(h.shape,dtype=np.float32)
        widths = np.ones(h.shape,dtype=np.float32)
        for p,q in zip(points[:-1],points[1:]):
            pad = max(p[3],q[3])*3+55
            lo = np.maximum(0, np.floor((np.minimum(p[:2],q[:2])-pad+4096)/spacing).astype(int))
            hi = np.minimum(len(axis), np.ceil((np.maximum(p[:2],q[:2])+pad+4096)/spacing).astype(int)+1)
            xx,yy = np.meshgrid(axis[lo[0]:hi[0]],axis[lo[1]:hi[1]])
            vec = q[:2]-p[:2]
            t = np.clip(((xx-p[0])*vec[0]+(yy-p[1])*vec[1])/np.dot(vec,vec),0,1)
            d = np.sqrt((xx-p[0]-t*vec[0])**2+(yy-p[1]-t*vec[1])**2)
            level, width = p[2]+t*(q[2]-p[2]), p[3]+t*(q[3]-p[3])
            cut = np.s_[lo[1]:hi[1],lo[0]:hi[0]]
            nearer = d<distance[cut]
            distance[cut] = np.where(nearer,d,distance[cut])
            water[cut] = np.where(nearer,level,water[cut])
            widths[cut] = np.where(nearer,width,widths[cut])
        # Evaluate each sample once using its nearest centreline segment.
        # Row blocks bound temporary memory on the full-resolution grid.
        for row in range(0,len(axis),128):
            cut = np.s_[row:row+128,:]
            d,level,width = np.minimum(distance[cut],1e9),water[cut],widths[cut]
            a = h[cut]
            weight = np.clip((width*3+40-d)/(width*2+40),0,1)
            weight = weight*weight*(3-2*weight)
            a[:] = a*(1-weight)+np.minimum(a,level+12+.15*d+.0009*d*d)*weight
            bed = level-7+7*(d/(width*.5))**2
            a[:] = np.where(d<width*.8,bed,a)
    # River banks must not create emergent causeways inside a flat lake.
    for _,cx,cy,r,level in lakes:
        for row in range(0,len(axis),128):
            d = np.hypot(axis[None,:]-cx,axis[row:row+128,None]-cy)
            a = h[row:row+128]
            a[:] = np.where(d<r*(17/23)**(1/6),np.minimum(a,level-1),a)
    return h


def png8(path, pixels):
    height,width = pixels.shape
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+row.tobytes() for row in pixels),9))+chunk(b'IEND',b''))


def export(h, axis, rivers, lakes, draft, blender_version):
    # Export always uses the runtime's exact 2m grid, including in draft mode.
    if len(axis)!=4097:
        full = np.linspace(-4096,4096,4097)
        intermediate = np.array([np.interp(full,axis,row) for row in h],dtype=np.float32)
        h = np.array([np.interp(full,axis,col) for col in intermediate.T],dtype=np.float32).T
    low,high = float(h.min()),float(h.max())
    encoded = np.rint((h[::-1]-low)/(high-low)*65535).astype('<u2')
    dest = OUT/'terrain/runtime'
    dest.mkdir(parents=True,exist_ok=True)
    for z in range(16):
        for x in range(16):
            encoded[z*256:z*256+257,x*256:x*256+257].tofile(dest/f'{x}_{z}.r16')
    write_json(dest/'manifest.json',dict(version=1,tilesX=16,tilesZ=16,tileSize=512,samples=257,originX=-4096,originZ=-4096,minHeight=low,maxHeight=high))
    write_json(OUT/'terrain/terrain.json',dict(convention=AXES,extent=[-4096,-4096,4096,4096],spacing=2,samples=4097,tileSize=512,tileSamples=257,h_min=low,h_max=high,encoding='uint16 little-endian; rows +Z, columns +X; h = minHeight + v/65535 * (maxHeight-minHeight)',water_levels={n:lev for n,_,_,_,lev in lakes},seed=SEED,blender_version=blender_version,draft=draft))
    ra = np.linspace(-4096,4096,1025)
    rx,rz = np.meshgrid(ra,ra)
    indices = region_indices(rx,-rz)
    (OUT/'regions').mkdir(exist_ok=True)
    png8(OUT/'regions/regions.png',indices)
    records = []
    for i,(id_,name,(cx,cy),desc) in enumerate(REGIONS,1):
        rows,cols = np.where(indices==i)
        records.append(dict(id=id_,name=name,index=i,centre=[cx,-cy],bbox=[float(ra[cols.min()]),float(ra[rows.min()]),float(ra[cols.max()]),float(ra[rows.max()])],description=desc))
    write_json(OUT/'regions/regions.json',dict(convention=AXES,map='regions.png',row_direction='+Z (north to south)',regions=records))
    lake_records = []
    for n,cx,cy,r,level in lakes:
        # Shore polygon is outside the waterline (where terrain > level).
        outline = [[cx+r*math.cos(t),-cy-r*math.sin(t)] for t in np.linspace(0,2*math.pi,97)[:-1]]
        lake_records.append(dict(name=n,water_y=level,outline=outline))
    write_json(OUT/'hydrology.json',dict(convention=AXES,river_point_format=['x','z','water_y','width'],rivers=[dict(name=n,polyline=[[float(x),float(-y),float(z),float(w)] for x,y,z,w in p]) for n,p in rivers],lakes=lake_records,waterfall=dict(river='Weißfall',position=[-1410,-300],description='Weißwall: steiler Abschnitt von 420 m auf 280 m; später Wasserfallgeometrie ergänzen.')))


def build_scene(h, axis, rivers, lakes, draft):
    import bpy
    from mathutils import Vector
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    stride = max(1,(len(axis)-1)//(512 if draft else 1024))
    a,heights = axis[::stride],h[::stride,::stride]
    xx,yy = np.meshgrid(a,a)
    n = len(a)
    vertices = np.column_stack((xx.ravel(),yy.ravel(),heights.ravel()))
    ids = np.arange((n-1)*(n-1))
    k = ids//(n-1)*n+ids%(n-1)
    faces = np.column_stack((k,k+1,k+n+1,k+n))
    mesh = bpy.data.meshes.new('Terrain · 8 km')
    mesh.from_pydata(vertices.tolist(),[],faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new('Violet Reach · terrain',mesh)
    bpy.context.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth=True
    gy,gx = np.gradient(heights,float(a[1]-a[0]))
    slope = np.sqrt(gx*gx+gy*gy)
    variation = noise(xx,yy,210,3)*.5+.5
    forest = np.clip((noise(xx,yy,430,62)+.1)*2,0,1)*(1-np.clip((slope-.4)*2,0,1))
    grass = np.array([.17,.34,.055])[None,None,:]*(.8+.35*variation[...,None])
    color = grass*(1-forest[...,None]*.7)+np.array([.045,.16,.085])*forest[...,None]*.7
    rock = np.clip((slope-.55)/.8,0,1)[...,None]
    color = color*(1-rock)+np.array([.53,.51,.39])*rock
    snow = np.clip((heights-850)/230,0,.7)[...,None]
    color = color*(1-snow)+np.array([.72,.76,.71])*snow
    for _,cx,cy,r,level in lakes:
        shore = (np.abs(np.sqrt((xx-cx)**2+(yy-cy)**2)-r)<32)&(heights<level+14)
        color[shore]=[.62,.56,.33]
    attr = mesh.color_attributes.new(name='biome',type='FLOAT_COLOR',domain='POINT')
    attr.data.foreach_set('color',np.column_stack((color.reshape(-1,3),np.ones(n*n))).ravel())
    mat=bpy.data.materials.new('Meadow • forest • limestone')
    mat.use_nodes=True
    nodes=mat.node_tree.nodes
    bsdf=nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value=.9
    vc=nodes.new('ShaderNodeVertexColor'); vc.layer_name='biome'
    mat.node_tree.links.new(vc.outputs['Color'],bsdf.inputs['Base Color'])
    tex=nodes.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value=.11
    bump=nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.24; bump.inputs['Distance'].default_value=2
    mat.node_tree.links.new(tex.outputs['Fac'],bump.inputs['Height'])
    mat.node_tree.links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    mesh.materials.append(mat)
    water=bpy.data.materials.new('Glacial turquoise water'); water.diffuse_color=(.025,.3,.35,1); water.use_nodes=True
    wb=water.node_tree.nodes.get('Principled BSDF'); wb.inputs['Base Color'].default_value=(.018,.27,.32,1); wb.inputs['Metallic'].default_value=.3; wb.inputs['Roughness'].default_value=.22
    def surface(name,verts,polys):
        me=bpy.data.meshes.new(name); me.from_pydata(verts,[],polys); me.materials.append(water)
        ob=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(ob)
    for name,p in rivers:
        verts=[]
        for i,point in enumerate(p):
            tangent=p[min(i+1,len(p)-1),:2]-p[max(0,i-1),:2]
            normal=np.array([-tangent[1],tangent[0]])/np.linalg.norm(tangent)
            for side in [-1,1]:
                xy=point[:2]+normal*point[3]*.5*side
                verts.append([*xy,point[2]+.5])
        surface(name,verts,[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(p)-1)])
    for name,cx,cy,r,level in lakes:
        radius=r*(17/23)**(1/6)
        verts=[(cx+radius*math.cos(t),cy+radius*math.sin(t),level+.8) for t in np.linspace(0,2*math.pi,128,endpoint=False)]
        surface(name,verts,[tuple(range(128))])
    scene=bpy.context.scene
    scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=24 if draft else 48
    scene.cycles.use_denoising=True
    world=bpy.data.worlds.new('Pale blue atmosphere'); world.use_nodes=True; scene.world=world
    world.node_tree.nodes['Background'].inputs[0].default_value=(.55,.7,.86,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.45
    bpy.ops.object.light_add(type='SUN',location=(-3000,-4000,7000))
    sun=bpy.context.object; sun.rotation_euler=(math.radians(25),math.radians(-30),math.radians(-25)); sun.data.energy=3; sun.data.color=(1,.94,.84); sun.data.angle=.12
    bpy.ops.object.camera_add(location=(0,0,14000))
    camera=bpy.context.object; scene.camera=camera; camera.data.type='ORTHO'; camera.data.ortho_scale=9350; camera.data.clip_end=50000
    camera.rotation_euler=(0,0,0)
    scene.render.resolution_x=2048; scene.render.resolution_y=2048; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='JPEG'; scene.render.image_settings.quality=94
    scene.view_settings.view_transform='AgX'
    scene.view_settings.look='AgX - Medium High Contrast'
    review=OUT/'review'; review.mkdir(exist_ok=True)
    scene.render.filepath=str(review/'overview_plain.jpg'); bpy.ops.render.render(write_still=True)
    # Review annotations live in a dedicated collection, never in the exports.
    annotations=bpy.data.collections.new('Review annotations'); scene.collection.children.link(annotations)
    def line(name,points,material,width):
        curve=bpy.data.curves.new(name,'CURVE'); curve.dimensions='3D'; curve.bevel_depth=width; curve.bevel_resolution=0
        spline=curve.splines.new('POLY'); spline.points.add(len(points)-1)
        for v,co in zip(spline.points,points): v.co=(*co,1)
        ob=bpy.data.objects.new(name,curve); annotations.objects.link(ob); curve.materials.append(material)
    def ink(name,color):
        m=bpy.data.materials.new(name); m.use_nodes=True; ns=m.node_tree.nodes; ns.clear(); em=ns.new('ShaderNodeEmission'); em.inputs[0].default_value=(*color,1); out=ns.new('ShaderNodeOutputMaterial'); m.node_tree.links.new(em.outputs[0],out.inputs[0]); return m
    white=ink('Ivory map lettering',(.96,.93,.78)); dark=ink('Letter shadow',(.018,.038,.035))
    def text(body,x,y,size):
        for dx,dy,z,material in [(4,-5,1700,dark),(0,0,1710,white)]:
            cu=bpy.data.curves.new(body,'FONT'); cu.body=body; cu.size=size; cu.align_x='CENTER'; cu.extrude=0
            ob=bpy.data.objects.new(body,cu); annotations.objects.link(ob); ob.location=(x+dx,y+dy,z); cu.materials.append(material)
    b=np.linspace(-4096,4096,129); bx,by=np.meshgrid(b,b); ri=region_indices(bx,by)
    borders=defaultdict(list)
    for j in range(128):
        for i in range(128):
            if ri[j,i]!=ri[j,i+1]: borders[tuple(sorted((int(ri[j,i]),int(ri[j,i+1]))))].append(((2*i+1,2*j-1),(2*i+1,2*j+1)))
            if ri[j,i]!=ri[j+1,i]: borders[tuple(sorted((int(ri[j,i]),int(ri[j+1,i]))))].append(((2*i-1,2*j+1),(2*i+1,2*j+1)))
    for edges in borders.values():
        graph=defaultdict(set)
        for p,q in edges: graph[p].add(q); graph[q].add(p)
        unused={tuple(sorted(edge)) for edge in edges}
        while unused:
            endpoints=sorted(p for p in graph if len(graph[p])==1 and any(tuple(sorted((p,q))) in unused for q in graph[p]))
            node=endpoints[0] if endpoints else min(unused)[0]
            chain=[node]
            while True:
                options=sorted(q for q in graph[node] if tuple(sorted((node,q))) in unused)
                if not options: break
                nxt=options[0]; unused.remove(tuple(sorted((node,nxt)))); chain.append(nxt); node=nxt
            points=np.array([(-4096+p[0]*32,-4096+p[1]*32,1600) for p in chain],dtype=float)
            for _ in range(3):
                smooth=[points[0]]
                for p,q in zip(points[:-1],points[1:]): smooth.extend((.75*p+.25*q,.25*p+.75*q))
                points=np.array(smooth+[points[-1]])
            line('Region border',points,white,2)
    for _,name,(cx,cy),_ in REGIONS: text(name.upper(),cx,cy+220,119)
    for name,cx,cy,r,level in lakes: text(name,cx,cy,75)
    for name,p in rivers:
        q=p[len(p)//2]; text(name,q[0]+170,q[1],66)
    text('V I O L E T   R E A C H',0,4280,170)
    text('WELTENTWURF  /  8 × 8 km  /  N ↑',0,-4440,88)
    line('Scale bar',[(-3650,-3950,1700),(-2650,-3950,1700)],white,9); text('1 km',-3150,-3830,70)
    scene.render.filepath=str(review/'overview.jpg'); bpy.ops.render.render(write_still=True)
    annotations.hide_render=True
    camera.data.type='PERSP'; camera.data.lens=43; camera.data.clip_end=50000
    camera.location=(8300,-11000,10500); target=Vector((0,500,100)); camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x=2400; scene.render.resolution_y=1800
    # Thin atmospheric volume limited to the landscape.
    bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,1800)); haze=bpy.context.object; haze.name='Atmospheric haze'; haze.scale=(6500,6500,1900)
    hm=bpy.data.materials.new('Distance haze'); hm.use_nodes=True; ns=hm.node_tree.nodes; ns.clear(); volume=ns.new('ShaderNodeVolumeScatter'); volume.inputs['Density'].default_value=.000014; volume.inputs['Color'].default_value=(.65,.76,.86,1); volume.inputs['Anisotropy'].default_value=.25; out=ns.new('ShaderNodeOutputMaterial'); hm.node_tree.links.new(volume.outputs[0],out.inputs['Volume']); haze.data.materials.append(hm)
    scene.render.filepath=str(review/'oblique.jpg'); bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'terrain.blend'))


def main():
    import bpy
    start=time.monotonic()
    parser=argparse.ArgumentParser(); parser.add_argument('--draft',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    axis=np.linspace(-4096,4096,1025 if args.draft else 4097,dtype=np.float32)
    h=np.empty((len(axis),len(axis)),dtype=np.float32)
    for row in range(0,len(axis),128):
        h[row:row+128]=terrain(axis[None,:],axis[row:row+128,None])
    # Two conservative talus transport passes soften unstable faces, preserving towers.
    for _ in range(2):
        for direction in (0,1):
            delta=np.diff(h,axis=direction)
            move=np.sign(delta)*np.maximum(abs(delta)-float(axis[1]-axis[0])*.95,0)*.12
            if direction==0: h[:-1]+=move; h[1:]-=move
            else: h[:,:-1]+=move; h[:,1:]-=move
    rivers,lakes=hydrology(); carve(h,axis,rivers,lakes)
    export(h,axis,rivers,lakes,args.draft,bpy.app.version_string)
    build_scene(h,axis,rivers,lakes,args.draft)
    print(f'WORLD BUILD COMPLETE: {time.monotonic()-start:.1f} seconds; seed {SEED}; draft={args.draft}',flush=True)


if __name__=='__main__': main()

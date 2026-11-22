"""Deterministic metre-scale world. Run with Blender; no third-party packages beyond numpy."""
import argparse
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
    ('spiegelsee', 'Spiegelsee', (650, -1750), 'Buchtenreiches Seebecken, Wiesen und Wald; sanfter zentraler Wanderstart, Uferpavillon.'),
]


def smoothstep(value):
    value = np.clip(value, 0, 1)
    return value*value*(3-2*value)


def canyon_center(y):
    return 1850+450*np.sin(y/600)+140*np.sin(y/265)


def lake_radius(theta, radius):
    def cove(angle, width):
        return np.exp(-(np.sin((theta-angle)/2)/width)**2)
    return radius*(1+.09*np.sin(3*theta+.4)+.06*np.sin(5*theta-1.3)
                   +.035*np.sin(9*theta)+.025*np.sin(13*theta+.8)
                   -.18*cove(2.25,.15)-.12*cove(.4,.12)-.10*cove(4.6,.16)
                   +.12*cove(3.5,.20))


def lake_signed_distance(x, y, cx, cy, radius):
    theta = np.arctan2(y-cy,x-cx)
    r = lake_radius(theta,radius)
    derivative = (lake_radius(theta+.001,radius)-lake_radius(theta-.001,radius))/.002
    return (np.hypot(x-cx,y-cy)-r)/np.sqrt(1+(derivative/r)**2)


def bank_rise(distance):
    d = np.maximum(distance,0)
    return .035*d+.35*(d-12+12*np.exp(-d/12))+.0015*np.maximum(d-100,0)**2


def inlet_coordinates(x, y):
    dx,dz = x-480,-y-1504
    return (dx+dz)/math.sqrt(2),(dx-dz)/math.sqrt(2)


def inlet_distance(x, y):
    along,across = inlet_coordinates(x,y)
    station = np.clip(along,-24,70)
    radius = 7+7*smoothstep((station+25)/55)
    bend = 1.6*np.sin(station/22)
    return np.hypot(across-bend,along-station)-radius


def inlet_terrain(x, y, height, level=180):
    along,across = inlet_coordinates(x,y)
    d = inlet_distance(x,y)
    bed = -.65*smoothstep(-d/2.5)
    bank = .14*smoothstep(d/2.5)+bank_rise(np.maximum(d-20,0))
    target = level+np.where(d<0,bed,bank)
    weight = smoothstep((100-abs(along-10))/50)*smoothstep((75-abs(across))/45)
    return height+(np.minimum(height,target)-height)*weight


def lake_distance(x, y, lake, rivers):
    _,cx,cy,r,level = lake
    base = lake_signed_distance(x,y,cx,cy,r)
    mouths = np.full_like(base,np.inf)
    for _,points in rivers:
        for a,b in zip(points[:-1],points[1:]):
            if abs(a[2]-level)>.001 or abs(b[2]-level)>.001:
                continue
            shore = lake_signed_distance(*((a[:2]+b[:2])*.5),cx,cy,r)
            if shore>180 or shore<-max(a[3],b[3]):
                continue
            delta = b[:2]-a[:2]
            t = np.clip(((x-a[0])*delta[0]+(y-a[1])*delta[1])/np.dot(delta,delta),0,1)
            d = np.hypot(x-a[0]-t*delta[0],y-a[1]-t*delta[1])-(a[3]+t*(b[3]-a[3]))*.5
            mouths = np.minimum(mouths,d)
    blend = np.maximum(1-abs(base-mouths)/60,0)
    combined = np.minimum(base,mouths)-15*blend*blend
    if lake[0]=='Spiegelsee':
        inlet = inlet_distance(x,y)
        blend = np.maximum(1-abs(combined-inlet)/4,0)
        combined = np.minimum(combined,inlet)-blend*blend
    return combined


def lake_outline(lake, rivers, inset=18):
    _,cx,cy,r,_ = lake
    theta = np.linspace(0,2*np.pi,384,endpoint=False)
    if lake[0]=='Spiegelsee':
        bearing = math.atan2(-1504-cy,480-cx)
        theta = np.unique(np.r_[theta,bearing+np.linspace(-.15,.15,181)])
    lo,hi = np.zeros_like(theta),np.full_like(theta,r*1.8+400)
    for _ in range(24):
        radius = (lo+hi)*.5
        inside = lake_distance(cx+radius*np.cos(theta),cy+radius*np.sin(theta),lake,rivers)<inset
        lo,hi = np.where(inside,radius,lo),np.where(inside,hi,radius)
    return np.column_stack((cx+hi*np.cos(theta),cy+hi*np.sin(theta)))


def gorge_distance(x, y):
    sx=(x+2450-150*np.sin((y-2000)/450))/850
    sy=(y-2300)/1260
    angle=np.arctan2(sy,sx)
    return np.hypot(sx,sy)*(1+.10*np.sin(5*angle)+.055*np.sin(9*angle+.6))


def pillar_layout():
    rng = np.random.default_rng(SEED)
    pillars = []
    while len(pillars)<44:
        px,py = rng.uniform(-3400,-1400),rng.uniform(1100,3500)
        if gorge_distance(px,py)>.83:
            continue
        if any(math.hypot(px-x,py-y)<140 for x,y,_,_,_ in pillars):
            continue
        pillars.append((px,py,rng.uniform(36,100),rng.uniform(.7,1.4),rng.uniform(235,440)))
    return pillars


PILLARS = pillar_layout()


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
    for scale, amp in [(1800, 95), (850, 85), (360, 48), (150, 25), (65, 11), (25, 4)]:
        h += amp*noise(wx, wy, scale, int(scale))
    # Elevated northern plateau with a 400–500 m incision.
    plateau = np.exp(-((wx-1800)/2000)**4-((wy-2300)/1500)**4)
    h += 480*plateau
    canyon_d = abs(x-canyon_center(y)+28*noise(x,y,130,19))
    for width, depth, shoulder in [(410,100,60),(295,140,35),(180,200,25)]:
        h -= depth*smoothstep((width-canyon_d)/shoulder)*plateau
    # Broad western tableland and its eastern escarpment.
    wall = smoothstep((y+2350)/650)*smoothstep((2900-y)/600)
    edge = -1540+120*np.sin(y/670)+45*noise(x,y,220,18)
    h += 490*smoothstep((edge-x)/38)*wall
    # Cut a cliff-enclosed amphitheatre into the northern tableland.
    g = gorge_distance(wx,wy)
    gorge = smoothstep((1-g)/.085)
    floor = 185+28*noise(x,y,230,24)+10*noise(x,y,65,25)
    h = h*(1-gorge)+floor*gorge
    crag_x,crag_y = x+9*noise(x,y,45,22),y+9*noise(x,y,45,23)
    for px,py,radius,aspect,height in PILLARS:
        d = np.sqrt(((crag_x-px)/radius)**2+((crag_y-py)/(radius*aspect))**2)
        cap = height+12*noise(x,y,35,26)+5*noise(x,y,13,27)
        h += cap*smoothstep((1-d)/.105)
    # Two continuous, knuckled ridges flank a narrow southern pass.
    path = -2150 + 190*np.sin(y/390)
    band = np.exp(-((y+2400)/1250)**6)
    for offset in (-245, 245):
        crest = 460+100*noise(x,y,110,7)+50*(1-abs(noise(x,y,40,8)))
        h += crest*np.exp(-((wx-path-offset)/155)**4)*band
    # An open crescent: arc ends taper rather than close into a crater.
    dx, dy = wx-2350, wy+1150
    r = np.sqrt(dx*dx+dy*dy)
    angle = np.arctan2(dy, dx)
    arc = np.clip((angle+2.2)/0.5,0,1)*np.clip((2.7-angle)/0.5,0,1)
    h += 400*np.exp(-((r-1000-65*noise(wx,wy,300,5))/190)**2)*arc
    # Pleasant gently rolling centre; no mountains at the walking spawn.
    meadow = np.exp(-((x-50)/380)**4-((y+200)/420)**4)
    h = h*(1-meadow) + (230+15*noise(x,y,180,4)+4*noise(x,y,40,6))*meadow
    # Irregular mountain backdrop, entirely inside the world extent.
    rim = np.clip((np.maximum(abs(wx),abs(wy))-3250)/850,0,1)
    h += rim**1.6*(560+240*(1-abs(noise(wx,wy,430,90)))+90*(1-abs(noise(wx,wy,150,91))))
    rough = np.clip((h-380)/200,0,1)
    h += rough*(14*noise(x,y,95,71)+4*noise(x,y,35,72))
    h -= (1-meadow)*(8*np.exp(-(noise(wx,wy,260,73)/.12)**2)
                            +3*np.exp(-(noise(wx,wy,80,74)/.1)**2))
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
        ('Weißfall', [(-3250,650,650,18),(-2800,420,630,22),(-2300,650,610,27),(-1840,470,595,31),(-1540,440,250,34),(-1150,100,235,38),(-550,160,222,42),(-720,-350,210,46),(-180,-630,202,49),(-350,-1050,195,53),(200,-1320,185,58),(550,-1660,180,65)]),
        ('Aschenlauf', [*[(float(canyon_center(y)),y,z,w) for y,z,w in [(3400,410,18),(2900,380,22),(2400,350,27),(1900,320,32),(1400,295,37),(950,270,42)]],(1850,550,248,46),(1470,0,227,49),(1710,-460,211,53),(1400,-950,194,57),(1550,-1360,184,63),(1260,-1590,180,68)]),
        ('Dornbach', [(-2200,-1540,380,15),(-2050,-2090,320,19),(-2300,-2540,278,24),(-1830,-2900,245,29),(-1250,-2650,225,34),(-1000,-2270,210,38),(-600,-2400,200,42),(-150,-2030,190,47),(100,-1740,184,52),(470,-1870,180,58)]),
        ('Spiegelstrom', [(830,-2310,180,65),(680,-2670,176,72),(1220,-2850,168,78),(1610,-2700,161,84),(2150,-2920,150,91),(2420,-3400,132,98),(3030,-3590,119,108),(3440,-3940,106,116),(3550,-4096,100,124)]),
    ]
    lakes = [('Spiegelsee',900,-1900,520,180),('Hirschweiher',-600,-2400,210,200),('Aschenauge',float(canyon_center(2900)),2900,175,380)]
    paths = [(n,smooth_path(p)) for n,p in rivers]
    for _,p in paths:
        distance = np.r_[0,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
        tangent = np.gradient(p[:,:2],axis=0)
        normal = np.column_stack((-tangent[:,1],tangent[:,0]))
        normal /= np.linalg.norm(normal,axis=1)[:,None]
        curvature = np.linalg.norm(np.gradient(normal,axis=0),axis=1)
        taper = smoothstep(distance/100)*smoothstep((distance[-1]-distance)/100)
        meander = (55*np.sin(distance/90)+28*np.sin(distance/160+.7)
                   +12*noise(distance,np.zeros_like(distance),60,83))*taper/(1+curvature*3)
        p[:,:2] += normal*meander[:,None]
        p[:,3] *= (1+.16*np.sin(distance/160)+.07*np.sin(distance/63)+np.minimum(curvature, .2))
        for _,cx,cy,r,level in lakes:
            shore = lake_signed_distance(p[:,0],p[:,1],cx,cy,r)
            p[:,3] *= 1+1.8*smoothstep((220-shore)/280)
            inside = shore<300
            p[inside,2] = level
        p[:,2] = np.minimum.accumulate(p[:,2])
    return paths, lakes


def carve(h, axis, rivers, lakes):
    spacing = float(axis[1]-axis[0])
    xx,yy = np.meshgrid(axis,axis)
    for lake in lakes:
        _,cx,cy,r,level = lake
        d = lake_distance(xx,yy,lake,rivers)
        bank = np.maximum(d,0)
        target = level+np.where(d<0,-22*smoothstep(-d/180),bank_rise(bank))
        shore = smoothstep((180-abs(d))/100)
        h[:] = np.minimum(h,target)*(1-shore)+target*shore
    del xx,yy
    for _, points in rivers:
        maximum = float(h.max())
        for p,q in zip(points[:-1],points[1:]):
            pad = max(p[3],q[3])*.5+max(100,(maximum-min(p[2],q[2])+6)/.385+12)
            lo = np.maximum(0, np.floor((np.minimum(p[:2],q[:2])-pad-axis[0])/spacing).astype(int))
            hi = np.minimum(len(axis), np.ceil((np.maximum(p[:2],q[:2])+pad-axis[0])/spacing).astype(int)+1)
            vec = q[:2]-p[:2]
            for row in range(lo[1],hi[1],128):
                end = min(row+128,hi[1])
                xx,yy = axis[None,lo[0]:hi[0]],axis[row:end,None]
                t = np.clip(((xx-p[0])*vec[0]+(yy-p[1])*vec[1])/np.dot(vec,vec),0,1)
                d = np.sqrt((xx-p[0]-t*vec[0])**2+(yy-p[1]-t*vec[1])**2)
                level, width = p[2]+t*(q[2]-p[2]), p[3]+t*(q[3]-p[3])
                bank = np.maximum(d-width*.5,0)
                bed = np.where(d<width*.5,level-2.5+2.15*smoothstep(d/(width*.5)),
                               level-.35+bank_rise(bank))
                cut = np.s_[row:end,lo[0]:hi[0]]
                # Compose continuous envelopes, not nearest-segment Voronoi cells.
                h[cut] = np.minimum(h[cut],bed)
    if any(lake[0]=='Spiegelsee' for lake in lakes):
        ix = np.flatnonzero((axis>=330)&(axis<=630))
        iy = np.flatnonzero((axis>=-1654)&(axis<=-1354))
        if len(ix) and len(iy):
            cut = np.ix_(iy,ix)
            h[cut] = inlet_terrain(axis[ix][None,:],axis[iy][:,None],h[cut])
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
    for lake in lakes:
        n,cx,cy,r,level = lake
        # Shore polygon is outside the waterline (where terrain > level).
        outline = [[float(x),float(-y)] for x,y in lake_outline(lake,rivers)]
        lake_records.append(dict(name=n,water_y=level,outline=outline))
    write_json(OUT/'hydrology.json',dict(convention=AXES,river_point_format=['x','z','water_y','width'],rivers=[dict(name=n,polyline=[[float(x),float(-y),float(z),float(w)] for x,y,z,w in p]) for n,p in rivers],lakes=lake_records,waterfall=dict(river='Weißfall',position=[-1540,-440],description='Weißwall: steiler Abschnitt von 595 m auf 250 m; später Wasserfallgeometrie ergänzen.')))


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
    forest = smoothstep((noise(xx,yy,400,62)+.12)*3+noise(xx,yy,65,63)*.65)*(1-np.clip((slope-.45)*2,0,1))
    crown = .65+.35*(noise(xx,yy,17,64)*.5+.5)
    grass = np.array([.21,.36,.075])[None,None,:]*(.78+.4*variation[...,None])
    color = grass*(1-forest[...,None]*.92)+np.array([.018,.075,.035])*crown[...,None]*forest[...,None]*.92
    rock = np.clip((slope-.85)/.95,0,1)[...,None]
    strata = (.86+.10*np.sin(heights/13)+.04*noise(xx,yy,22,65))[...,None]
    color = color*(1-rock)+np.array([.72,.74,.69])*strata*rock
    snow = np.clip((heights-850)/230,0,.7)[...,None]
    color = color*(1-snow)+np.array([.72,.76,.71])*snow
    for lake in lakes:
        _,cx,cy,r,level = lake
        d = lake_distance(xx,yy,lake,rivers)
        shore = (d>0)&(d<22+20*noise(xx,yy,85,66))&(heights>level)&(heights<level+7)&(slope<.3)
        color[shore]=[.61,.57,.37]
        reeds = (d>0)&(d<45)&(heights<level+5)&(noise(xx,yy,120,67)>.1)
        color[reeds]=[.14,.23,.055]
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
    geometry=nodes.new('ShaderNodeNewGeometry')
    mat.node_tree.links.new(geometry.outputs['Position'],tex.inputs['Vector'])
    grain=nodes.new('ShaderNodeMixRGB'); grain.blend_type='MULTIPLY'; grain.inputs[0].default_value=.2
    mat.node_tree.links.new(vc.outputs['Color'],grain.inputs[1]); mat.node_tree.links.new(tex.outputs['Fac'],grain.inputs[2]); mat.node_tree.links.new(grain.outputs[0],bsdf.inputs['Base Color'])
    bump=nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.4; bump.inputs['Distance'].default_value=1
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
    for lake in lakes:
        name,cx,cy,r,level = lake
        outline = lake_outline(lake,rivers,inset=0)
        verts=[(cx,cy,level+.8)]+[(float(x),float(y),level+.8) for x,y in outline]
        surface(name,verts,[(0,i+1,(i+1)%len(outline)+1) for i in range(len(outline))])
    scene=bpy.context.scene
    scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=24 if draft else 48
    scene.cycles.use_denoising=True
    world=bpy.data.worlds.new('Pale blue atmosphere'); world.use_nodes=True; scene.world=world
    sky=world.node_tree.nodes.new('ShaderNodeTexSky'); sky.sky_type='SINGLE_SCATTERING'; sky.sun_elevation=math.radians(30); sky.sun_rotation=math.radians(205); sky.sun_disc=False; sky.air_density=1.1; sky.aerosol_density=.5
    world.node_tree.links.new(sky.outputs[0],world.node_tree.nodes['Background'].inputs[0])
    world.node_tree.nodes['Background'].inputs[1].default_value=.22
    bpy.ops.object.light_add(type='SUN',location=(-3000,-4000,7000))
    sun=bpy.context.object; sun.rotation_euler=Vector((.86,.22,-.5)).to_track_quat('-Z','Y').to_euler(); sun.data.energy=3; sun.data.color=(1,.95,.85); sun.data.angle=.055
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
    b=np.linspace(-4096,4096,513); bx,by=np.meshgrid(b,b); ri=region_indices(bx,by)
    for index in range(1,7):
        mask=(ri==index).astype(float)
        for _ in range(3):
            for axis_ in (0,1):
                padded=np.pad(mask,((2,2),(0,0)) if axis_==0 else ((0,0),(2,2)),mode='edge')
                if axis_==0: mask=sum(w*padded[k:k+513,:] for k,w in enumerate((1,4,6,4,1)))/16
                else: mask=sum(w*padded[:,k:k+513] for k,w in enumerate((1,4,6,4,1)))/16
        curve=bpy.data.curves.new('Smoothed region contour','CURVE'); curve.dimensions='3D'; curve.bevel_depth=2; curve.bevel_resolution=2; curve.materials.append(white)
        # Interpolated marching squares of a Gaussian-smoothed region mask.
        crossing=(np.minimum.reduce((mask[:-1,:-1],mask[1:,:-1],mask[1:,1:],mask[:-1,1:]))<.5)&(np.maximum.reduce((mask[:-1,:-1],mask[1:,:-1],mask[1:,1:],mask[:-1,1:]))>=.5)
        for j,i in np.argwhere(crossing):
            values=[mask[j,i],mask[j,i+1],mask[j+1,i+1],mask[j+1,i]]
            corners=[(b[i],b[j]),(b[i+1],b[j]),(b[i+1],b[j+1]),(b[i],b[j+1])]
            points=[]
            for k in range(4):
                q=(k+1)%4
                if (values[k]<.5)!=(values[q]<.5):
                    t=(.5-values[k])/(values[q]-values[k]); points.append((corners[k][0]*(1-t)+corners[q][0]*t,corners[k][1]*(1-t)+corners[q][1]*t))
            for k in range(0,len(points)-1,2):
                spline=curve.splines.new('POLY'); spline.points.add(1)
                for v,(px,py) in zip(spline.points,points[k:k+2]): v.co=(px,py,1600,1)
        ob=bpy.data.objects.new('Region contour',curve); annotations.objects.link(ob)
    for _,name,(cx,cy),_ in REGIONS:
        if name=='Spiegelsee': cx,cy=50,-2930
        text(name.upper(),cx,cy+220,119)
    for name,cx,cy,r,level in lakes: text(name,cx,cy,75)
    for name,p in rivers:
        q=p[len(p)//2]; text(name,q[0]+170,q[1],66)
    text('V I O L E T   R E A C H',0,4280,170)
    text('WELTENTWURF  /  8 × 8 km  /  N ↑',0,-4440,88)
    line('Scale bar',[(-3650,-3950,1700),(-2650,-3950,1700)],white,9); text('1 km',-3150,-3830,70)
    scene.render.filepath=str(review/'overview.jpg'); bpy.ops.render.render(write_still=True)
    annotations.hide_render=True
    camera.data.type='PERSP'; camera.data.lens=26; camera.data.clip_end=50000
    camera.location=(2450,-3100,1000); target=Vector((-700,1800,360)); camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x=2400; scene.render.resolution_y=1800
    # Thin atmospheric volume limited to the landscape.
    bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,1800)); haze=bpy.context.object; haze.name='Atmospheric haze'; haze.scale=(6500,6500,1900)
    hm=bpy.data.materials.new('Distance haze'); hm.use_nodes=True; ns=hm.node_tree.nodes; ns.clear(); volume=ns.new('ShaderNodeVolumeScatter'); volume.inputs['Density'].default_value=.000035; volume.inputs['Color'].default_value=(.65,.76,.86,1); volume.inputs['Anisotropy'].default_value=.25; out=ns.new('ShaderNodeOutputMaterial'); hm.node_tree.links.new(volume.outputs[0],out.inputs['Volume']); haze.data.materials.append(hm)
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

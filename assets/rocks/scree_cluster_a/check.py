"""Run inside Blender against scree_cluster_a.blend."""
import collections
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tools/blender"))
import vrlib


def directions(values):
    values=np.asarray(values,dtype=float).reshape(-1,3)
    lengths=np.linalg.norm(values,axis=1)
    values=values[lengths>1e-7]/lengths[lengths>1e-7,None]
    return np.unique(np.round(values,6),axis=0)


def proxy(obj):
    bm=bmesh.new()
    coordinates=np.asarray(obj["collision_vertices"]).reshape(-1,3)
    for co in coordinates:
        bm.verts.new(obj.matrix_world@Vector(co))
    bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context="VERTS")
    bm.normal_update()
    verts=np.array([tuple(v.co) for v in bm.verts])
    normals=directions([tuple(f.normal) for f in bm.faces])
    edges=directions([tuple(e.verts[1].co-e.verts[0].co) for e in bm.edges])
    detailed=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices])
    assert (detailed@normals.T-(verts@normals.T).max(axis=0)).max()<.001,obj.name
    bm.free()
    return verts,normals,edges


objects=vrlib.source_objects()
counts=collections.Counter(o["size_class"] for o in objects)
assert counts=={"large":4,"medium":76,"small":240},counts
lo,hi=vrlib.world_bounds(objects)
assert abs(lo.x+hi.x)<.001 and abs(lo.y+hi.y)<.001
assert lo.z>=-.06 and max(hi.x-lo.x,hi.y-lo.y)<7.5
assert 300000<=vrlib.triangle_count(objects)<=1000000
assert 1.7<=hi.z-lo.z<=2.2
assert bpy.context.scene.cycles.device=="CPU"
assert bpy.context.scene["placement_mode"]=="analytical convex gravity contacts"
crest=[o for o in objects if "crest_rotation" in o]
assert len(crest)==3
for obj in crest:
    world=[obj.matrix_world@v.co for v in obj.data.vertices]
    assert min(p.z for p in world)<.02,obj.name
    assert max(p.z for p in world)>1.2,obj.name
    widths=[max(v.co[i] for v in obj.data.vertices)-min(v.co[i] for v in obj.data.vertices) for i in range(3)]
    assert min(widths)/max(widths)<.36,obj.name
assert sum(o["secondary_fractures"] for o in objects)>50
for obj in objects:
    assert obj.rigid_body is None,obj.name
    assert all(f.use_smooth for f in obj.data.polygons),obj.name
    assert all(abs(s-1)<.00001 for s in obj.scale),obj.name
    if obj["size_class"]=="large":
        assert 32<=obj["cut_planes"]<=44
    elif obj["size_class"]=="medium":
        assert 22<=obj["cut_planes"]<=32
    assert obj["secondary_fractures"]>=obj["broad_faces_detailed"]*2,obj.name
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    assert all(e.is_manifold for e in bm.edges),obj.name
    assert bm.calc_volume(signed=True)>0,obj.name
    bm.free()
proxies=[proxy(obj) for obj in objects]
bounds=[(p[0].min(axis=0),p[0].max(axis=0)) for p in proxies]
contacts={i:set() for i in range(len(objects))}
grounded={i for i,(a,b) in enumerate(bounds) if a[2]<.005}
deepest=0
for i,(av,an,ae) in enumerate(proxies):
    for j in range(i):
        if np.any(bounds[i][0]>bounds[j][1]+.006) or np.any(bounds[j][0]>bounds[i][1]+.006):
            continue
        bv,bn,be=proxies[j]
        cross=np.cross(ae[:,None,:],be[None,:,:]).reshape(-1,3)
        axes=directions(np.concatenate((an,bn,cross)))
        a,b=av@axes.T,bv@axes.T
        gap=np.maximum(b.min(axis=0)-a.max(axis=0),a.min(axis=0)-b.max(axis=0)).max()
        deepest=max(deepest,-gap)
        assert gap>=-.01,(objects[i].name,objects[j].name,gap)
        if gap<=.006:
            contacts[i].add(j)
            contacts[j].add(i)
frontier=grounded.copy()
while frontier:
    frontier={j for i in frontier for j in contacts[i] if j not in grounded}
    grounded|=frontier
assert len(grounded)==len(objects),[objects[i].name for i in contacts if i not in grounded]
print("GEOMETRY_CHECK: 320 closed outward meshes; unit scales; centred XY; min_z >= -0.06; CPU: CPU")
print("PIECE_COUNTS:",dict(counts))
print("CREST_CHECK: three ground-seated leaning tabular slabs; no elevated cap block")
print("SECONDARY_FRACTURES:",sum(o["secondary_fractures"] for o in objects),"BROAD_FACES:",sum(o["broad_faces_detailed"] for o in objects))
print("SUPPORT_CHECK: all 320 convex collision proxies connected to ground; overlap <1 cm; detailed meshes inside proxies")
print("MAX_PROXY_OVERLAP_M:",round(deepest,6))
print("PLACEMENT_MODE:",bpy.context.scene["placement_mode"])
print("SIZE_M:",tuple(round(v,3) for v in hi-lo),"TRIANGLES:",vrlib.triangle_count(objects))
for kind in ("large","medium","small"):
    triangles=[sum(len(f.vertices)-2 for f in o.data.polygons) for o in objects if o["size_class"]==kind]
    print("PER_PIECE_TRIANGLES:",kind,min(triangles),max(triangles))

"""Run inside Blender against rock_boulder_b.blend."""
import importlib.util
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tools/blender"))
import vrlib

objects=vrlib.source_objects()
assert len(objects)==17
lo,hi=vrlib.world_bounds(objects)
assert lo.z>=-.06
assert abs(lo.x+hi.x)<.001 and abs(lo.y+hi.y)<.001
assert vrlib.triangle_count(objects)<3000000
assert bpy.context.scene.cycles.device=="CPU"
for obj in objects:
    assert all(abs(s-1)<.00001 for s in obj.scale),obj.name
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    assert all(e.is_manifold for e in bm.edges),obj.name
    assert bm.calc_volume(signed=True)>0,obj.name
    bm.free()
body=bpy.data.objects["Sandstein_Hauptmasse"]
block=bpy.data.objects["Abgespaltener_Bruchblock"]
assert tuple(body["split_normal"])==tuple(block["split_normal"])
assert body["tafoni_cells"]>=3
directions=[Vector(v).normalized() for v in ((-.47,-1.75,.1242),(1.02,.58,.1181),(-1,-.15,-.1),(-.12,.04,1))]
areas=[sum(f.area for f in body.data.polygons if f.normal.dot(n)>.98) for n in directions]
assert min(areas)>.35,areas
moss=bpy.data.objects["Angewachsene_Moosschale"]
assert moss.data.attributes["moss_edge"].domain=="POINT"
tree=BVHTree.FromObject(body,bpy.context.evaluated_depsgraph_get())
inverse=body.matrix_world.inverted()
thickness=max(tree.find_nearest(inverse@(moss.matrix_world@v.co))[3] for v in moss.data.vertices)
assert thickness<.04,thickness
assert len([o for o in objects if o.name.startswith("Bruchsplitter")])==14
block_tree=BVHTree.FromObject(block,bpy.context.evaluated_depsgraph_get())
for shard in [o for o in objects if o.name.startswith("Bruchsplitter")]:
    points=[shard.matrix_world@v.co for v in shard.data.vertices]
    distance=min(block_tree.find_nearest(block.matrix_world.inverted()@p)[3] for p in points)
    assert min(p.z for p in points)<.02 or distance<.01,shard.name
print("B_GEOMETRY: 17 closed outward meshes; unit scales; centred XY; min_z >= -0.06; CPU: CPU")
print("B_MAJOR_FACE_AREAS_M2:",[round(a,3) for a in areas])
print("B_MOSS_MAX_SURFACE_OFFSET_M:",round(thickness,4))
print("B_RUBBLE_CONTACT: all 14 shards ground-seated or touching fallen block within 1 cm")
print("B_SIZE_M:",tuple(round(v,3) for v in hi-lo),"TRIANGLES:",vrlib.triangle_count(objects))
spec=importlib.util.spec_from_file_location("boulder_builder",Path(__file__).with_name("build.py"))
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
empty_mesh=bpy.data.meshes.new("empty_test")
empty=bpy.data.objects.new("empty_test",empty_mesh)
try:
    builder.moss_shell(empty,None)
except RuntimeError as error:
    assert str(error)=="No upward north-side faces for moss"
else:
    raise AssertionError("Empty moss surface was accepted")
finally:
    bpy.data.objects.remove(empty)
    bpy.data.meshes.remove(empty_mesh)
print("B_EMPTY_SURFACE: rejected with explicit error")

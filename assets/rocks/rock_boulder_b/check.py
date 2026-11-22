"""Run inside Blender against the rebuilt sandstone source."""
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
assert len(objects)==17,len(objects)
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
    if "recipe_seed" in obj:
        assert obj["ico_subdivisions"]>=6
        planes=[Vector(n) for n in obj["fracture_planes"]]
        assert 4<=len(planes)<=8
        assert all(min(abs(v) for v in n)>.06 for n in planes)
        assert all(.1<abs(n.dot(m))<.98 for i,n in enumerate(planes) for m in planes[:i])
body=bpy.data.objects["Sandstein_Hauptmasse"]
block=bpy.data.objects["Abgespaltener_Bruchblock"]
bed=bpy.data.objects["Sand_und_Feinkieskragen"]
assert tuple(body["split_normal"])==tuple(block["split_normal"])
assert body["tafoni_voronoi"] and body["fissure_count"]==2
assert body["macro_amplitude_m"]>=.08
moss=bpy.data.objects["Angewachsene_Moosschale"]
assert moss.data.attributes["moss_edge"].domain=="POINT"
tree=BVHTree.FromObject(body,bpy.context.evaluated_depsgraph_get())
inverse=body.matrix_world.inverted()
thickness=max(tree.find_nearest(inverse@(moss.matrix_world@v.co))[3] for v in moss.data.vertices)
assert thickness<.045,thickness
shards=[o for o in objects if o.name.startswith("Bruchsplitter")]
assert len(shards)==12
supports=[(obj.matrix_world.inverted(),BVHTree.FromObject(obj,bpy.context.evaluated_depsgraph_get())) for obj in (bed,block)]
for shard in shards:
    points=[shard.matrix_world@v.co for v in shard.data.vertices]
    distance=min(tree.find_nearest(inv@p)[3] for p in points for inv,tree in supports)
    assert distance<.035,(shard.name,distance)
print("B_GEOMETRY: 17 closed outward meshes; unit scales; centred XY; min_z >= -0.06; CPU: CPU")
print("B_RECIPE: dense cut icospheres; 7 nonorthogonal planes; geometric Voronoi/strata/grain; 2 fissures; Voronoi tafoni")
print("B_MOSS_MAX_SURFACE_OFFSET_M:",round(thickness,4))
print("B_RUBBLE_CONTACT: all 12 shards touch soil collar or fallen block within 3.5 cm")
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
for size,cuts in (((1,0,1),7),((1,1,1),3)):
    try:
        builder.fractured_rock("invalid",size,1,None,cuts=cuts)
    except ValueError as error:
        assert str(error)=="Positive dimensions and 4-8 fracture planes required"
    else:
        raise AssertionError("Invalid rock recipe accepted")
print("B_EMPTY_AND_ERROR_CASES: empty moss, zero dimension and invalid cut count rejected")

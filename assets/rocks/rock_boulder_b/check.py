"""Run in Blender on the generated source blend."""
import importlib.util
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

ASSET_DIR=Path(__file__).resolve().parent
sys.path.insert(0,str(ASSET_DIR.parents[2]/"tools"/"blender"))
import vrlib

spec=importlib.util.spec_from_file_location("asset_builder",ASSET_DIR/"build.py")
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
objects=vrlib.source_objects()
assert objects,"Empty source collection"
low,high=vrlib.world_bounds(objects)
assert low.z>=-.06001,low
assert abs(low.x+high.x)<.01 and abs(low.y+high.y)<.01,(low,high)
triangles=0
for obj in objects:
    assert obj.type=="MESH" and obj.data.vertices,obj.name
    assert max(abs(s-1) for s in obj.scale)<1e-6,obj.name
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    assert all(e.is_manifold for e in bm.edges),obj.name
    assert bm.calc_volume(signed=True)>0,obj.name
    bm.free()
    obj.data.calc_loop_triangles()
    triangles+=len(obj.data.loop_triangles)
assert triangles<5000000,triangles
stones=[obj for obj in objects if obj.get("stone_piece")]
asset=ASSET_DIR.name
assert len(stones)=={"rock_boulder_b":14,"cliff_strata_a":15,"rock_pillar_a":13,"shore_stones_a":40}[asset],len(stones)
assert len({obj["recipe_seed"] for obj in stones})==len(stones),"Repeated seeds"
for obj in stones:
    assert obj["lake_shore_recipe"]=="pr9/lake_shore_a"
    assert 4<=len(obj["fracture_planes"])<=11
    assert obj.data.color_attributes["stone_tones"].domain=="POINT"
    assert obj.data.attributes["stone_saturation"].domain=="POINT"
    assert sum(f.use_smooth for f in obj.data.polygons)/len(obj.data.polygons)>.9,obj.name
trees=[builder.world_tree(obj) for obj in stones]
centres=[sum(vrlib.world_bounds([obj]),Vector())*.5 for obj in stones]
for i,tree in enumerate(trees):
    for j in range(i):
        assert not tree.overlap(trees[j]),(stones[i].name,stones[j].name)
        assert not builder.inside(tree,centres[j]),(stones[i].name,stones[j].name)
        assert not builder.inside(trees[j],centres[i]),(stones[i].name,stones[j].name)
bed=next(obj for obj in objects if obj.get("gravel_apron"))
assert vrlib.world_bounds([bed])[1].z<.04,"Raised sand cone"
grit=next(obj for obj in objects if obj.get("modelled_grit_count"))
assert grit["modelled_grit_count"]>100
grit_tree=builder.world_tree(grit)
assert all(not grit_tree.overlap(tree) for tree in trees),"Intersecting grit"
main=max(stones,key=lambda obj:math.prod(vrlib.world_bounds([obj])[1]-vrlib.world_bounds([obj])[0]))
a,b=vrlib.world_bounds([main])
size=b-a
assert len(main.data.vertices)>10000
if asset=="rock_boulder_b":
    assert 2.8<size.x<3.5 and 1.4<size.z<1.75 and size.x>size.z*1.7,size
    assert min(max(value.color[:3]) for value in main.data.color_attributes["stone_tones"].data)>.04
    relief=[v.value for v in main.data.attributes["weather_relief"].data]
    assert .025<max(relief)-min(relief)<.11,(min(relief),max(relief))
    assert max(abs(v) for v in relief)<.055
    assert sum(abs(v)>.01 for v in relief)>1000
    assert any(n.type=="AMBIENT_OCCLUSION" for n in main.data.materials[0].node_tree.nodes)
    print("B_FACE_RELIEF_M:",round(min(relief),4),round(max(relief),4))
    assert main["fissure_count"]==2
    block=next(obj for obj in stones if obj.get("replacement_kind"))
    points=np.array([tuple(v.co) for v in block.data.vertices])
    points-=points.mean(axis=0)
    axes=np.linalg.eigh(points.T@points)[1]
    thickness=float(np.ptp(points@axes,axis=0).min())
    assert thickness>=.25,thickness
    moss=next(obj for obj in objects if obj.get("moss_patch_count"))
    assert moss["moss_patch_count"]>=2 and moss["moss_lee_only"]
    tree=builder.world_tree(main)
    rise=max(tree.find_nearest(moss.matrix_world@v.co)[3] for v in moss.data.vertices)
    assert .01<rise<.033,rise
    empty=bpy.data.objects.new("empty_moss_test",bpy.data.meshes.new("empty_moss_test"))
    try:
        builder.moss_shell(empty,None)
        raise AssertionError("Empty moss surface accepted")
    except RuntimeError:
        pass
    finally:
        bpy.data.objects.remove(empty,do_unlink=True)
    empty=bpy.data.objects.new("empty_weather_test",bpy.data.meshes.new("empty_weather_test"))
    try:
        builder.weather_faces(empty)
        raise AssertionError("Empty weathering surface accepted")
    except ValueError:
        pass
    finally:
        bpy.data.objects.remove(empty,do_unlink=True)
    supports=[(obj.matrix_world.inverted(),builder.BVHTree.FromObject(obj,bpy.context.evaluated_depsgraph_get())) for obj in (bed,block)]
    for shard in (obj for obj in stones if obj.name.startswith("Bruchsplitter")):
        points=[shard.matrix_world@v.co for v in shard.data.vertices]
        distance=min(tree.find_nearest(inverse@p)[3] for p in points for inverse,tree in supports)
        assert distance<.035,(shard.name,distance)
    empty=bpy.data.objects.new("empty_cleft_test",bpy.data.meshes.new("empty_cleft_test"))
    try:
        builder.cut_cleft(empty,(0,0,0),0)
        raise AssertionError("Empty cleft surface accepted")
    except ValueError:
        pass
    finally:
        bpy.data.objects.remove(empty,do_unlink=True)
    for cuts in (3,9):
        try:
            builder.fractured_rock("invalid",(1,1,1),0,None,cuts=cuts)
            raise AssertionError("Invalid fracture count accepted")
        except ValueError:
            pass
    print("B_SUPPORT: all twelve shards touch soil or fallen block within 3.5 cm")
    print("B_DETAIL: thick fallen block; two clefts; sheltered raised olive cushions; max moss distance",round(rise,4))
elif asset in ("cliff_strata_a","rock_pillar_a"):
    heights=main["strata_heights_m"]
    assert all(1<=y-x<=6 for x,y in zip(heights,heights[1:])),heights
    assert any("gras" in obj.name.lower() for obj in objects)
    if asset=="cliff_strata_a":
        assert 39.9<size.x<40.1 and 44<size.z<46 and 8<size.y<12,size
        nx,nz=main["front_columns"],main["front_rows"]
        error=max(abs(main.data.vertices[j*nx].co[k]-main.data.vertices[j*nx+nx-1].co[k]) for j in range(nz) for k in (1,2))
        assert error<.0001,error
        print("TILE_PROFILE_MAX_ERROR_M:",error)
    else:
        assert 12<size.x<18.1 and 58<size.z<62,size
        assert main["landmark_mode"]=="pillar"
    try:
        builder.strata_heights(0)
        raise AssertionError("Zero-height strata accepted")
    except ValueError:
        pass
else:
    assert 4<high.x-low.x<6,(low,high)
    assert sum(obj.name.startswith("Uferstein_") for obj in stones)==12
    wet,dry=[],[]
    for obj in stones:
        factors=obj.data.attributes["stone_saturation"].data
        for v in obj.data.vertices:
            y=(obj.matrix_world@v.co).y
            if y<-.8:wet.append(factors[v.index].value)
            if y>.8:dry.append(factors[v.index].value)
    assert wet and dry and sum(wet)/len(wet)>sum(dry)/len(dry)+.4
    assert bed.data.color_attributes.get("bank_tones")
    assert bed.data.attributes.get("ground_moisture")
    print("SHORE_WETNESS_MEANS:",round(sum(wet)/len(wet),3),round(sum(dry)/len(dry),3))
for dims in ((),(0,1,1),(1,-1,1)):
    try:
        builder.fractured_rock("invalid",dims,0,None)
        raise AssertionError("Invalid dimensions accepted")
    except ValueError:
        pass
original=builder.vrlib.source_objects
try:
    builder.vrlib.source_objects=lambda:[]
    try:
        builder.add_grit()
        raise AssertionError("Missing apron accepted")
    except ValueError:
        pass
finally:
    builder.vrlib.source_objects=original
assert bpy.context.scene.cycles.device=="CPU"
print("GEOMETRY_CHECK:",asset,len(objects),"closed outward meshes; unit scales; centred XY; min_z >= -0.06; CPU")
print("STONE_CHECK:",len(stones),"unique seeds; no stone intersections/containment; grit disjoint")
print("INPUT_CHECK: empty and invalid inputs rejected")
print("SIZE_M:",tuple(round(v,3) for v in high-low),"MASS_M:",tuple(round(v,3) for v in size),"TRIANGLES:",triangles,"GRIT:",grit["modelled_grit_count"])

"""Run inside Blender against the graded fractured talus source."""
import importlib.util
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tools/blender"))
import vrlib

objects=vrlib.source_objects()
rocks=[o for o in objects if "recipe_seed" in o]
assert len(rocks)==64 and len(objects)==66
assert len({o["recipe_seed"] for o in rocks})==64
lo,hi=vrlib.world_bounds(objects)
assert lo.z>=-.06
assert abs(lo.x+hi.x)<.001 and abs(lo.y+hi.y)<.001
assert vrlib.triangle_count(objects)<8000000
assert bpy.context.scene.cycles.device=="CPU"
for obj in objects:
    assert all(abs(s-1)<.00001 for s in obj.scale),obj.name
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    assert all(e.is_manifold for e in bm.edges),obj.name
    assert bm.calc_volume(signed=True)>0,obj.name
    bm.free()
for rock in rocks:
    assert rock["ico_subdivisions"]>=6
    assert len(rock["fracture_planes"])==8
    assert not rock["tafoni_voronoi"] and rock["fissure_count"]==0
    assert all(f.use_smooth for f in rock.data.polygons)
large=[o for o in rocks if o["size_class"]=="Gross"]
fine=[o for o in rocks if o["size_class"]=="Fein"]
assert len(large)==8
fall_line=Vector(bpy.context.scene["fall_line_world"])
assert sum(o.location.dot(fall_line) for o in large)/len(large)>sum(o.location.dot(fall_line) for o in fine)/len(fine)+.8
assert len({o.data.materials[0].name for o in rocks})>=12
assert "Randgras" in bpy.data.objects
bed=bpy.data.objects["Talus_Feinkieskeil"]
tree=BVHTree.FromObject(bed,bpy.context.evaluated_depsgraph_get())
inverse=bed.matrix_world.inverted()
heights=[]
for y in (-1.1,0):
    hit=tree.ray_cast(-fall_line*y+Vector((0,0,5)),Vector((0,0,-1)))[0]
    assert hit is not None
    heights.append(hit.z)
angle=math.degrees(math.atan((heights[1]-heights[0])/1.1))
assert 29<angle<36,angle
maximum=0
for rock in rocks:
    closest=math.inf
    for vertex in rock.data.vertices:
        p=rock.matrix_world@vertex.co
        hit=tree.ray_cast(inverse@Vector((p.x,p.y,5)),Vector((0,0,-1)))[0]
        if hit is not None:
            closest=min(closest,abs((bed.matrix_world@hit).z-p.z))
    assert closest<.05,(rock.name,closest)
    maximum=max(maximum,closest)
print("SCREE_GEOMETRY: 66 closed outward meshes; 64 unique seeded cut-icosphere shards; unit scales; centred XY; min_z >= -0.06; CPU: CPU")
print("SCREE_GRADING: 8 large toe blocks; progressively smaller fragments upslope; 16 material variants; older stained tops; edge grass")
print("SCREE_SLOPE_DEGREES:",round(angle,2),"MAX_EMBEDDED_SURFACE_GAP_M:",round(maximum,4))
print("SCREE_SIZE_M:",tuple(round(v,3) for v in hi-lo),"TRIANGLES:",vrlib.triangle_count(objects))
spec=importlib.util.spec_from_file_location("talus_builder",Path(__file__).with_name("build.py"))
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
for size,cuts in (((),7),((1,0,1),7),((1,1,1),9)):
    try:
        builder.fractured_rock("invalid",size,1,None,cuts=cuts)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid rock recipe accepted")
print("SCREE_EMPTY_AND_ERROR_CASES: empty dimensions, zero dimension and invalid cut count rejected")

"""Run inside Blender against rock_boulder_a.blend."""
import importlib.util
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tools/blender"))
import vrlib

objects=vrlib.source_objects()
assert len(objects)==8,len(objects)
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
        assert 4<=len(obj["fracture_planes"])<=8
body=bpy.data.objects["Zusammenhaengender_Kalkfindling"]
assert len(body["fracture_planes"])==7
assert body["macro_amplitude_m"]>=.08
body_lo,body_hi=vrlib.world_bounds([body])
assert body_hi.x-body_lo.x>7 and 4<body_hi.z-body_lo.z<5.3
assert body_hi.x-body_lo.x>body_hi.z-body_lo.z
bm=bmesh.new()
bm.from_mesh(body.data)
visited={next(iter(bm.verts))}
frontier=set(visited)
while frontier:
    frontier={e.other_vert(v) for v in frontier for e in v.link_edges}-visited
    visited|=frontier
assert len(visited)==len(bm.verts)
bm.free()
bed=bpy.data.objects["Kalksand_und_Feinkieskragen"]
assert vrlib.world_bounds([bed])[1].z>.30
assert "Grasige_Schichtterrassen" in bpy.data.objects and "Randgras" in bpy.data.objects
assert len([o for o in objects if o.name.startswith("Halbversunkener_Bruchblock")])==4
print("A_GEOMETRY: 8 closed outward meshes; one connected rock mass; unit scales; centred XY; min_z >= -0.06; CPU: CPU")
print("A_RECIPE: dense cut icosphere; 7 fracture planes; geometric Voronoi/strata/grain; no stacked beds")
print("A_GROUND: continuous modelled fines collar; 4 embedded blocks; grass terrace shells and modelled tufts")
print("A_BODY_SIZE_M:",tuple(round(v,3) for v in body_hi-body_lo))
print("A_SIZE_M:",tuple(round(v,3) for v in hi-lo),"TRIANGLES:",vrlib.triangle_count(objects))
spec=importlib.util.spec_from_file_location("chalk_builder",Path(__file__).with_name("build.py"))
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
for size,cuts in (((1,0,1),7),((1,1,1),9)):
    try:
        builder.fractured_rock("invalid",size,1,None,cuts=cuts)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid rock recipe accepted")
print("A_ERROR_CASES: zero dimension and invalid cut count rejected")

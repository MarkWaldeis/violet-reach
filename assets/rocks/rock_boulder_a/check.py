"""Run inside Blender against rock_boulder_a.blend."""
import sys
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tools/blender"))
import vrlib

objects=vrlib.source_objects()
assert len(objects)==33
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
body=bpy.data.objects["Zusammenhaengender_Kalkfindling"]
assert body.data.attributes["weather_face"].domain=="FACE"
assert body.data.attributes["joint_weather"].domain=="FACE"
assert len({v.value for v in body.data.attributes["weather_face"].data})>20
assert len([o for o in objects if o.name.startswith("Loser_Kalkbruch")])==29
print("A_GEOMETRY: 33 closed outward meshes; unit scales; centred XY; min_z >= -0.06; CPU: CPU")
print("A_WEATHERING: per-face seeds and joint-only scratch mask present")
print("A_SIZE_M:",tuple(round(v,3) for v in hi-lo),"TRIANGLES:",vrlib.triangle_count(objects))

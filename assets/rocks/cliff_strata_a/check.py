"""Run in Blender on the generated source blend."""
import ast
import hashlib
import importlib.util
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ASSET_DIR = Path(__file__).resolve().parent
sys.path.insert(0,str(ASSET_DIR.parents[2]/"tools"/"blender"))
import vrlib

spec = importlib.util.spec_from_file_location("asset_builder",ASSET_DIR/"build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
EXPECTED = {"make_rock":"1ac6bc171d7e4a1675f79ab65e3fa5f661cc4d106d532085050e5099d6a069fa","support_material":"e691eef9b0acd6f31f563fdd95e22df4c8f2f04d9093f6fa567c8609b95c1547","fracture":"c7dfcc4da1c8ee838811c8df388169b2f37e71dc0688a387b6dfb96ab85c364b"}
source = (ASSET_DIR/"build.py").read_text()
definitions = {n.name:ast.get_source_segment(source,n).strip() for n in ast.parse(source).body
               if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
for name,digest in EXPECTED.items():
    token = definitions[name]
    assert hashlib.sha256(token.encode()).hexdigest()==digest,("Approved function changed",name)
print("APPROVED_RECIPE:",ASSET_DIR.name,"generator and material source match approved record")


def world_tree(obj):
    obj.data.calc_loop_triangles()
    return BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],
                               [tuple(t.vertices) for t in obj.data.loop_triangles],all_triangles=True)


def inside(tree, point):
    origin = point.copy()
    direction = Vector((.173,.089,1)).normalized()
    count = 0
    for _ in range(128):
        hit = tree.ray_cast(origin,direction)[0]
        if hit is None:
            return count%2==1
        count += 1
        origin = hit+direction*.00001
    raise RuntimeError("Ambiguous containment")


objects = vrlib.source_objects()
assert objects,"Empty source collection"
low,high = vrlib.world_bounds(objects)
assert low.z>=-.06001,low
assert abs(low.x+high.x)<.01 and abs(low.y+high.y)<.01,(low,high)
triangles = 0
for obj in objects:
    assert obj.type=="MESH" and obj.data.vertices,obj.name
    assert max(abs(s-1) for s in obj.scale)<1e-6,obj.name
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    assert all(e.is_manifold for e in bm.edges),obj.name
    assert bm.calc_volume(signed=True)>0,obj.name
    bm.free()
    obj.data.calc_loop_triangles()
    triangles += len(obj.data.loop_triangles)
assert triangles<5000000,triangles

stones = [o for o in objects if o.get("stone_piece")]
assert stones
assert len({(o["recipe_seed"],o.get("slice_index",-1)) for o in stones})==len(stones)
trees = [world_tree(o) for o in stones]
centres = [sum(vrlib.world_bounds([o]),Vector())*.5 for o in stones]
for i,tree in enumerate(trees):
    for j in range(i):
        assert not tree.overlap(trees[j]),(stones[i].name,stones[j].name)
        assert not inside(tree,centres[j]),(stones[i].name,stones[j].name)
        assert not inside(trees[j],centres[i]),(stones[i].name,stones[j].name)
grit = next(o for o in objects if o.get("modelled_grit_count"))
assert grit["modelled_grit_count"]>100,grit["modelled_grit_count"]
grit_tree = world_tree(grit)
assert all(not grit_tree.overlap(tree) for tree in trees),"Intersecting grit"
bed = next(o for o in objects if o.get("gravel_apron"))
assert vrlib.world_bounds([bed])[1].z<.04,"Raised sand cone"

if ASSET_DIR.name=="shore_stones_a":
    assert len([o for o in stones if o.name.startswith("Uferstein_")])==12
    assert len([o for o in stones if o.name.startswith("Zwischenkiesel_")])==28
    assert 4.5<high.x-low.x<5.8
    top_means = []
    for obj in stones:
        assert obj["approved_generator"]=="pr9/lake_shore_a.cobble"
        assert obj["stone_form"] in ("split","worn")
        assert obj.data.color_attributes["stone_tones"].domain=="POINT"
        factors = obj.data.attributes["stone_saturation"].data
        colors = obj.data.color_attributes["stone_tones"].data
        wet,dry = [],[]
        height = obj["wet_gradient_height_m"]
        for v in obj.data.vertices:
            expected = 1-builder.smooth((v.co.z-obj["wet_base_z"])/height)
            assert abs(factors[v.index].value-expected)<1e-5,(obj.name,v.index)
            if expected>.8:
                wet.append(sum(colors[v.index].color[:3])/3)
            if expected<.05:
                dry.append(sum(colors[v.index].color[:3])/3)
        assert wet and dry and sum(dry)/len(dry)>sum(wet)/len(wet)*1.25,obj.name
        top_means.append(sum(dry)/len(dry))
        bsdf = obj.data.materials[0].node_tree.nodes["Principled BSDF"]
        assert bsdf.inputs["Roughness"].is_linked
    assert min(top_means)>.22,top_means
    print("SHORE_BASE_WETNESS: smooth local-Z gradient on every stone; pale dry tops; wet roughness attribute")
    for radius,flat in ((0,.6),(-1,.6),(1,0)):
        try:
            builder.shore_stone("invalid",radius,flat,(0,0),0,None)
            raise AssertionError("Invalid shore parameters accepted")
        except ValueError:
            pass
else:
    main = [o for o in stones if "stratum" in o]
    apron = [o for o in stones if o.get("scree_chunk")]
    assert len(apron)>=8,len(apron)
    a,b = vrlib.world_bounds(main)
    size = b-a
    for obj in stones:
        assert obj["approved_generator"]=="c4c0cd0/crystal_cluster_b.make_rock"
        assert max(abs(v) for v in obj.rotation_euler)<1e-7,obj.name
    if ASSET_DIR.name=="cliff_strata_a":
        assert 39.9<size.x<40.1 and size.y>=16 and 44<size.z<46,size
        assert set(o["joint_column"] for o in main)=={0,1,2,3}
        assert len({round(o["stratum_height_m"],1) for o in main})>=5
        roofs = [max(vrlib.world_bounds([o])[1].z for o in main if o["joint_column"]==c) for c in range(4)]
        assert max(roofs)-min(roofs)>1,roofs
        assert bpy.context.scene["tile_pitch_m"]==40
        assert len(bpy.context.scene["through_band_joints_x_m"])==3
        print("CLIFF_MAIN_M:",tuple(round(v,3) for v in size),"three through-band joints; four columns; irregular crown; 40 m placement pitch")
    else:
        assert len(main)==8
        assert 12<size.x<18.1 and 59<size.z<61,size
        main.sort(key=lambda o:o["stratum"])
        base_width = vrlib.world_bounds([main[0]])[1].x-vrlib.world_bounds([main[0]])[0].x
        cap_width = vrlib.world_bounds([main[-1]])[1].x-vrlib.world_bounds([main[-1]])[0].x
        assert cap_width<base_width,(base_width,cap_width)
        assert all(max(abs(v) for v in o["axis_offset_m"])<.25 for o in main)
        turf = next(o for o in objects if o.get("soil_mat_thickness_m"))
        assert .3<=turf["soil_mat_thickness_m"]<=1
        grass = next(o for o in objects if o.name=="Randgras")
        assert len(grass.data.vertices)>=2600*9*4
        assert max(v.co.z for v in turf.data.vertices)>b.z+.25
        print("PILLAR_STACK: eight straight, slightly tapering approved-block slices; no rotation; same-chunk scree; grass crown")
    for dims in ((),(0,1,1),(1,-1,1)):
        try:
            builder.approved_chunk("invalid",dims,(0,0,0),0,None)
            raise AssertionError("Invalid dimensions accepted")
        except ValueError:
            pass

original = builder.vrlib.source_objects
try:
    builder.vrlib.source_objects = lambda:[]
    try:
        builder.finish()
        raise AssertionError("Empty source accepted")
    except ValueError:
        pass
finally:
    builder.vrlib.source_objects = original
assert bpy.context.scene.cycles.device=="CPU"
print("GEOMETRY_CHECK:",ASSET_DIR.name,len(objects),"closed outward meshes; unit scales; centred XY; min_z >= -0.06; CPU")
print("STONE_CHECK:",len(stones),"unique source/slice IDs; no stone overlap/containment; grit disjoint")
print("INPUT_CHECK: empty and invalid inputs rejected")
print("SIZE_M:",tuple(round(v,3) for v in high-low),"TRIANGLES:",triangles,"GRIT:",grit["modelled_grit_count"])

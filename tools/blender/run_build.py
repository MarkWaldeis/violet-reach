"""blender -b --factory-startup --python tools/blender/run_build.py -- <asset_dir>

Imports <asset_dir>/build.py, calls build(), saves <id>.blend with everything in the SOURCE collection.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import vrlib  # noqa: E402

asset_dir = os.path.abspath(vrlib.script_args()[0])
vrlib.reset_scene()
vrlib.source_collection()

spec = importlib.util.spec_from_file_location("asset_build", os.path.join(asset_dir, "build.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.build()

objs = vrlib.source_objects()
if not objs:
    raise SystemExit("build() left no mesh objects in the SOURCE collection")
lo, hi = vrlib.world_bounds(objs)
print("VR_RESULT", {"triangles": vrlib.triangle_count(objs), "size_m": [round(hi[i] - lo[i], 3) for i in range(3)],
                    "min_z": round(lo.z, 3)}, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=vrlib.blend_path(asset_dir), compress=True)

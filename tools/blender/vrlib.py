"""Shared helpers for Violet Reach asset scripts. Runs inside Blender's Python."""
import json
import math
import os
import sys

import bpy

SOURCE_COLLECTION = "SOURCE"


def script_args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def load_meta(asset_dir):
    with open(os.path.join(asset_dir, "asset.json")) as f:
        return json.load(f)


def blend_path(asset_dir):
    return os.path.join(asset_dir, load_meta(asset_dir)["id"] + ".blend")


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def source_collection():
    col = bpy.data.collections.get(SOURCE_COLLECTION)
    if col is None:
        col = bpy.data.collections.new(SOURCE_COLLECTION)
        bpy.context.scene.collection.children.link(col)
    return col


def link_to_source(obj):
    col = source_collection()
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def source_objects():
    return [o for o in bpy.data.collections[SOURCE_COLLECTION].all_objects if o.type == "MESH"]


def world_bounds(objects):
    """Exact world-space bounds from evaluated vertices (object bound boxes overshoot when rotated)."""
    import numpy as np
    from mathutils import Vector
    deps = bpy.context.evaluated_depsgraph_get()
    lo = np.full(3, math.inf)
    hi = np.full(3, -math.inf)
    for o in objects:
        ev = o.evaluated_get(deps)
        mesh = ev.to_mesh()
        co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        m = np.array(ev.matrix_world)
        world = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
        lo = np.minimum(lo, world.min(axis=0))
        hi = np.maximum(hi, world.max(axis=0))
    return Vector(lo), Vector(hi)


def triangle_count(objects):
    deps = bpy.context.evaluated_depsgraph_get()
    total = 0
    for o in objects:
        mesh = o.evaluated_get(deps).to_mesh()
        total += sum(len(p.vertices) - 2 for p in mesh.polygons)
        o.evaluated_get(deps).to_mesh_clear()
    return total


def use_cycles_cpu(scene, samples):
    # The Devin VM's virtual Metal GPU hangs Cycles, so renders and bakes stay on CPU.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True

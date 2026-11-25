"""Diagnostic dump for monument_split_disc_a; runs inside Blender."""
import json
import os
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, r"C:\Users\Mark Waldeis\Desktop\Violet Reach\tools\blender")
import vrlib  # noqa: E402

out_dir = os.path.dirname(os.path.abspath(__file__))
objs = vrlib.source_objects()
def _jsonsafe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, (list, tuple)) or hasattr(value, "__iter__"):
            try:
                return [_jsonsafe(v) for v in value]
            except TypeError:
                pass
        return repr(value)


report = {"objects": [], "materials": [], "scene_props": {k: _jsonsafe(bpy.context.scene[k]) for k in bpy.context.scene.keys()}}
lo, hi = vrlib.world_bounds(objs)
report["bounds"] = {"lo": list(lo), "hi": list(hi), "size": list(hi - lo)}
report["triangles"] = vrlib.triangle_count(objs)

all_positions = []
all_polys = []
for obj in objs:
    me = obj.data
    pos = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", pos)
    pos = pos.reshape((-1, 3))
    mw = np.array(obj.matrix_world, dtype=np.float64)
    world = pos @ mw[:3, :3].T + mw[:3, 3]
    all_positions.append(world)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    bm = bmesh.new()
    bm.from_mesh(me)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    nonmanifold = sum(1 for e in bm.edges if not e.is_manifold)
    comps = []
    unseen = set(bm.verts)
    while unseen:
        seed = unseen.pop()
        stack = [seed]
        comp = [seed]
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                w = e.other_vert(v)
                if w in unseen:
                    unseen.remove(w)
                    comp.append(w)
                    stack.append(w)
        faces = {f for v in comp for f in v.link_faces}
        comps.append({"verts": len(comp), "faces": len(faces), "tris": sum(len(f.verts) - 2 for f in faces)})
    bm.free()
    report["objects"].append({
        "name": obj.name,
        "verts": len(me.vertices),
        "polys": len(me.polygons),
        "tris": tris,
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "components": sorted(comps, key=lambda c: c["tris"], reverse=True)[:12],
        "materials": [m.name if m else None for m in me.materials],
        "uv_layers": [u.name for u in me.uv_layers],
        "bbox_local": {"lo": pos.min(axis=0).tolist(), "hi": pos.max(axis=0).tolist()},
    })
    # Compact polygon records for offline spatial analysis.
    for poly in me.polygons:
        ids = list(poly.vertices)
        all_polys.append({
            "object": obj.name,
            "verts": ids,
            "center": world[ids].mean(axis=0).tolist(),
            "normal": list(poly.normal),
            "area": float(poly.area),
        })

for mat in bpy.data.materials:
    if not mat.use_nodes or not mat.node_tree:
        continue
    item = {"name": mat.name, "nodes": []}
    for node in mat.node_tree.nodes:
        n = {"type": node.type, "name": node.name}
        if node.type == "TEX_IMAGE" and node.image:
            n["image"] = {"name": node.image.name, "size": list(node.image.size), "packed": bool(node.image.packed_file)}
        if node.type == "NORMAL_MAP":
            n["strength"] = float(node.inputs["Strength"].default_value)
        if node.type == "BSDF_PRINCIPLED":
            n["roughness"] = float(node.inputs["Roughness"].default_value) if not node.inputs["Roughness"].is_linked else "linked"
            n["metallic"] = float(node.inputs["Metallic"].default_value) if not node.inputs["Metallic"].is_linked else "linked"
        item["nodes"].append(n)
    report["materials"].append(item)

pos = np.concatenate(all_positions, axis=0) if all_positions else np.zeros((0, 3))
if len(pos):
    zlo, zhi = pos[:, 2].min(), pos[:, 2].max()
    slices = []
    for i in range(30):
        z0 = zlo + (zhi - zlo) * i / 30
        z1 = zlo + (zhi - zlo) * (i + 1) / 30
        sel = (pos[:, 2] >= z0) & (pos[:, 2] < z1 if i < 29 else pos[:, 2] <= z1)
        pp = pos[sel]
        if len(pp):
            slices.append({"z0": float(z0), "z1": float(z1), "n": int(len(pp)),
                           "x": [float(pp[:, 0].min()), float(pp[:, 0].max())],
                           "y": [float(pp[:, 1].min()), float(pp[:, 1].max())]})
    report["z_slices"] = slices
    np.savez_compressed(os.path.join(out_dir, "mesh_positions.npz"), positions=pos)
    main = max(objs, key=lambda o: len(o.data.vertices), default=None)
    if main is not None:
        me = main.data
        flat = []
        offsets = [0]
        for poly in me.polygons:
            flat.extend(poly.vertices)
            offsets.append(len(flat))
        mco = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", mco)
        mpos = mco.reshape((-1, 3))
        np.savez_compressed(os.path.join(out_dir, "mesh_connectivity.npz"),
                            positions=mpos,
                            poly_indices=np.array(flat, dtype=np.int32),
                            poly_offsets=np.array(offsets, dtype=np.int32))

with open(os.path.join(out_dir, "scene_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
# Polygon centers/normals only; vertex ids are per-object and not needed globally.
polys_small = [{k: p[k] for k in ("object", "center", "normal", "area")} for p in all_polys]
with open(os.path.join(out_dir, "polygon_spatial.json"), "w", encoding="utf-8") as f:
    json.dump(polys_small, f)
print("VR_RESULT", {"objects": len(objs), "triangles": report["triangles"], "size": report["bounds"]["size"]}, flush=True)

"""Kalkstein-Felssäule A (rock_pillar_chalk_a) — 0-Credit Kitbash aus freigegebenen Kreidefelsen.

Kombiniert zwei verjüngte, geschichtete Sektionen aus cliff_chalk_wall_a (Unterbau 0–24,5 m und
eingebettete Turmkrone 13,5–35,0 m) mit einem asymmetrischen boulder_chalk_a-Sockelpfeiler
zu einem monolithischen Kreide-Felsturm (~19 × 13 × 35 m, min_z = -2,5 m).
"""
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
import numpy as np

import vrlib
import vrmeshy
import vrmeshfix
import vrcliffs

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_ROCKS_DIR = os.path.dirname(ASSET_DIR)


def _close_pinholes(objs):
    """Seal small smart-topology boundary loops with a manifold triangle fan and interpolated UVs."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-4)
        uv_layer = bm.loops.layers.uv.active
        vert_uv = {}
        if uv_layer is not None:
            for f in bm.faces:
                for l in f.loops:
                    vert_uv.setdefault(l.vert, l[uv_layer].uv.copy())
        for _ in range(64):
            b_edges = [e for e in bm.edges if e.is_boundary]
            if not b_edges:
                break
            start_e = b_edges[0]
            loop_verts = [start_e.verts[0], start_e.verts[1]]
            used_edges = {start_e}
            cur = loop_verts[-1]
            closed = False
            while True:
                next_e = [e for e in cur.link_edges if e.is_boundary and e not in used_edges]
                if not next_e:
                    break
                e = next_e[0]
                used_edges.add(e)
                nxt = e.other_vert(cur)
                if nxt in loop_verts:
                    cycle = loop_verts[loop_verts.index(nxt):]
                    if len(cycle) >= 3:
                        cv = bm.verts.new(sum((v.co for v in cycle), Vector()) / len(cycle))
                        vert_uv[cv] = sum(
                            (vert_uv.get(v, Vector((0.5, 0.5))) for v in cycle),
                            Vector((0.0, 0.0)),
                        ) / len(cycle)
                        for i in range(len(cycle)):
                            try:
                                nf = bm.faces.new((cycle[i], cycle[(i + 1) % len(cycle)], cv))
                                if uv_layer is not None:
                                    for l in nf.loops:
                                        l[uv_layer].uv = vert_uv[l.vert]
                            except ValueError:
                                pass
                        closed = True
                    break
                loop_verts.append(nxt)
                cur = nxt
            if not closed:
                break
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def _fit_xy_taper(objs, target_x, target_y, z_taper_start, z_taper_end, top_scale):
    """Horizontally scale XY to (target_x, target_y) and linearly taper XY upward."""
    lo, hi = vrlib.world_bounds(objs)
    cx = 0.5 * (lo.x + hi.x)
    cy = 0.5 * (lo.y + hi.y)
    sx = target_x / max(hi.x - lo.x, 1e-6)
    sy = target_y / max(hi.y - lo.y, 1e-6)
    span_z = max(z_taper_end - z_taper_start, 1e-6)
    for obj in [o for o in objs if o and o.type == "MESH"]:
        me = obj.data
        pos = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", pos)
        pos = pos.reshape(-1, 3)
        pos[:, 0] = cx + (pos[:, 0] - cx) * sx
        pos[:, 1] = cy + (pos[:, 1] - cy) * sy
        t = np.clip((pos[:, 2] - z_taper_start) / span_z, 0.0, 1.0)
        taper = 1.0 - (1.0 - top_scale) * t
        pos[:, 0] = cx + (pos[:, 0] - cx) * taper
        pos[:, 1] = cy + (pos[:, 1] - cy) * taper
        me.vertices.foreach_set("co", pos.astype(np.float32).ravel())
        me.update()


def _apply_matrix(objs, mat):
    for o in objs:
        o.matrix_world = mat @ o.matrix_world
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def build():
    wall_a_dir = os.path.join(ASSETS_ROCKS_DIR, "cliff_chalk_wall_a")
    boulder_a_dir = os.path.join(ASSETS_ROCKS_DIR, "boulder_chalk_a")

    # Piece 1 — Lower Monolith (0..24.5 m, buried skirt to -2.5 m)
    lower = vrmeshy.load_raw(wall_a_dir)
    vrmeshy.drop_loose(lower, min_fraction=0.002)
    vrmeshy.normalize(lower, height=24.5, yaw_deg=12.0)
    vrcliffs.shape_cliff(
        lower,
        top_drop=3.8,
        top_teeth_trim=3.2,
        top_taper_xy=0.28,
        back_sign=-1.0,
        back_slope_out=1.4,
        back_shelf_amp=1.1,
        edge_chamfer_amp=0.20,
        seed=4301,
    )
    _fit_xy_taper(lower, target_x=17.5, target_y=12.0, z_taper_start=4.0, z_taper_end=24.0, top_scale=0.78)
    vrmeshy.grade_basecolor(lower, "#BCB296", strength=0.39)
    vrcliffs.clean_chalk_surface(
        lower,
        target_hex="#BCB296",
        dark_floor=0.22,
        dark_lift=0.36,
        deweave_rad=2,
        deweave_keep=0.48,
        normal_strength=0.42,
        bump_strength=0.38,
    )
    vrmeshy.clamp_material(lower, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(lower, depth=2.5)
    vrmeshfix.bury_skirt_below_ground(lower, depth=2.5)

    # Piece 2 — Upper Spire Crown (12.0..33.5 m, embedded 12.5 m deep inside Piece 1)
    upper = vrmeshy.load_raw(wall_a_dir)
    vrmeshy.drop_loose(upper, min_fraction=0.002)
    vrmeshy.normalize(upper, height=21.5, yaw_deg=142.0)
    vrcliffs.shape_cliff(
        upper,
        top_drop=5.8,
        top_teeth_trim=4.0,
        top_taper_xy=0.42,
        back_sign=-1.0,
        back_slope_out=1.2,
        back_shelf_amp=1.2,
        edge_chamfer_amp=0.22,
        seed=4357,
    )
    _fit_xy_taper(upper, target_x=10.0, target_y=7.4, z_taper_start=3.0, z_taper_end=21.0, top_scale=0.56)
    vrmeshy.grade_basecolor(upper, "#BCB296", strength=0.39)
    vrcliffs.clean_chalk_surface(
        upper,
        target_hex="#BCB296",
        dark_floor=0.22,
        dark_lift=0.36,
        deweave_rad=2,
        deweave_keep=0.48,
        normal_strength=0.42,
        bump_strength=0.38,
    )
    vrmeshy.clamp_material(upper, roughness_min=0.68, metallic=0.0)
    _apply_matrix(upper, Matrix.Translation((0.35, -0.25, 12.0)))

    # Piece 3 — Basal Shoulder Buttress (0..11.5 m, buried skirt to -2.5 m)
    buttress = vrmeshy.load_raw(boulder_a_dir)
    vrmeshy.drop_loose(buttress, min_fraction=0.002)
    _close_pinholes(buttress)
    vrmeshy.normalize(buttress, height=11.5, yaw_deg=-38.0)
    _fit_xy_taper(buttress, target_x=10.4, target_y=8.4, z_taper_start=2.5, z_taper_end=11.5, top_scale=0.84)
    vrmeshy.delight_basecolor(buttress, radius_frac=0.25)
    vrmeshy.grade_basecolor(buttress, "#BCB296", strength=0.60)
    vrmeshy.clamp_material(buttress, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(buttress, depth=2.5)
    vrmeshfix.bury_skirt_below_ground(buttress, depth=2.5)
    _apply_matrix(buttress, Matrix.Translation((-4.0, 1.4, 0.0)))

    all_objs = [o for o in lower + upper + buttress if o and o.type == "MESH"]

    # Recenter combined XY footprint to (0, 0) while preserving min_z = -2.5
    lo, hi = vrlib.world_bounds(all_objs)
    _apply_matrix(all_objs, Matrix.Translation((-0.5 * (lo.x + hi.x), -0.5 * (lo.y + hi.y), 0.0)))

    # Ensure matching active UV layer name before join so all material slots retain UVs
    for o in all_objs:
        if o.data.uv_layers:
            o.data.uv_layers[0].name = "UVMap"
            o.data.uv_layers[0].active = True
            o.data.uv_layers[0].active_render = True

    bpy.ops.object.select_all(action="DESELECT")
    for o in all_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]
    if len(all_objs) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = "rock_pillar_chalk_a_source"

    vrmeshy.fix_normals([joined])
    vrmeshy.link_source([joined])

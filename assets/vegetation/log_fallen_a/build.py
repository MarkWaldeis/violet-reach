"""Umgestürzter Baumstamm A (log_fallen_a) — Meshy Klasse B.

Bereitet das Meshy-Rohmodell (log_fallen_a/model/B-v1/model.glb) deterministisch
mit tools/blender/vrmeshy.py auf: Schließt kleine Smart-Topology-Randlöcher wasserdicht,
richtet die Längsachse auf +X aus (yaw -1,6°), skaliert auf 5,0 m Länge mit dezenter
1,15x X-Streckung (H ~1,71 m, flache Auflagefläche auf z = 0 bleibt ohne Eingrabe-Rand
erhalten), gleicht die Rindenfarbe ohne Delight Richtung bark (#41321D, strength 0,25)
an, klemmt Rauheit ≥ 0,75 / Metall 0,0 und richtet alle Normalen aus.
"""
import os

import bpy
import bmesh
from mathutils import Matrix, Vector
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


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
        for _ in range(128):
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
                        vert_uv[cv] = sum((vert_uv.get(v, Vector((0.5, 0.5))) for v in cycle), Vector((0.0, 0.0))) / len(cycle)
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


def _stretch_x(objs, factor):
    """Apply subtle horizontal length stretch along X after yaw alignment, keeping z_min = 0."""
    m = Matrix.Diagonal((factor, 1.0, 1.0, 1.0))
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.matrix_world = m @ o.matrix_world
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    _close_pinholes(objs)
    vrmeshy.normalize(objs, height=1.715, yaw_deg=-1.6)
    _stretch_x(objs, 1.15)
    vrmeshy.grade_basecolor(objs, "#41321D", strength=0.25)
    vrmeshy.clamp_material(objs, roughness_min=0.75, metallic=0.0)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

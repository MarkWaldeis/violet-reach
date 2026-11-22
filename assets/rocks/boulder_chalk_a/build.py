"""Kreidefels-Brocken A (boulder_chalk_a) — Meshy-Pilot Klasse B.

Bereitet das Meshy-Rohmodell (boulder_chalk_a/model/B-v2/model.glb) deterministisch
mit tools/blender/vrmeshy.py auf: Lose Teile entfernen, kleine Smart-Topology-Randlöcher
wasserdicht schließen, auf Zielmaße 2,6 × 2,0 × 1,6 m normalisieren, eingebackenes Licht
herausrechnen, Farbton Richtung canyon_chalk (#BCB296) angleichen, Rauheit ≥ 0,60 /
Metall 0,0 klemmen, 30 cm Eingrabe-Rand extrudieren (Schnittkante bündig auf z = 0)
und Normalen richten.
"""
import os

import bmesh
from mathutils import Vector
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


def _bury_skirt_below_ground(objs, depth):
    """Place the burial_skirt cut seam at z = 0 so the vertical skirt stays underground."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        body = [v for v in bm.verts if v.co.z > -depth + 1e-3]
        if body:
            z0 = min(v.co.z for v in body)
            for v in body:
                v.co.z -= z0
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is not None:
            center = Vector((0.5, 0.5))
            for f in bm.faces:
                if any(v.co.z <= -depth + 1e-3 for v in f.verts) and any(v.co.z > -depth + 1e-3 for v in f.verts):
                    for loop in f.loops:
                        if loop.vert.co.z <= -depth + 1e-3:
                            uv = loop[uv_layer].uv
                            loop[uv_layer].uv = uv + (center - uv) * 0.04
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    _close_pinholes(objs)
    vrmeshy.normalize(objs, size_m=(2.6, 2.0, 1.6), yaw_deg=-0.34)
    vrmeshy.delight_basecolor(objs, radius_frac=0.25)
    vrmeshy.grade_basecolor(objs, "#BCB296", strength=0.60)
    vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.30)
    _bury_skirt_below_ground(objs, depth=0.30)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

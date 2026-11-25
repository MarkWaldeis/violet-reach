"""Umgestürzter Baumstamm A (log_fallen_a) — Meshy Klasse B.

Gate-Reparatur: UV-kohärente Dreiecksfüllung der Smart-Topology-Löcher (keine
schwarzen UV-Leerstellen mehr), zwei versetzte, reliefartige Splintholzkerne in
den hohlen Bruchenden, wärmere/höllere Rindenfärbung und eine reduzierte,
weniger repetitive Normalenstruktur. Geometrie und Texturen bleiben
deterministisch aus dem gepinnten Meshy-Rohmodell ableitbar.
"""
import os

import bpy
import bmesh
from mathutils import Matrix, Vector
import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(ASSET_DIR)))
BARK_SRC = os.path.join(ROOT, "art", "textures", "src", "bark__acg_Bark012.jpg")


def _stretch_x(objs, factor):
    """Apply subtle horizontal length stretch along X after yaw alignment, keeping z_min = 0."""
    m = Matrix.Diagonal((factor, 1.0, 1.0, 1.0))
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.matrix_world = m @ o.matrix_world
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def _seal_plug_center(plug, axis, sign, segments):
    """Close the tiny centre triangle and sector-boundary gaps of a cavity plug.

    make_cavity_plug uses three off-centre knot vertices for relief.  Without
    these few bridge faces the fan leaves narrow triangular gaps that read as
    exactly the black holes the gate criticised.  Kept asset-local so the other
    already reviewed repair sheets remain hash-stable.
    """
    if plug is None:
        return
    bm = bmesh.new()
    bm.from_mesh(plug.data)
    verts = list(bm.verts)
    need = 2 * segments + 3
    if len(verts) >= need:
        ring0 = segments
        centers = [verts[2 * segments + k] for k in range(3)]

        def ring(j):
            return verts[ring0 + (j % segments)]

        def assignment(j):
            return ((j * 3) // segments) % 3

        new_faces = []
        for j in range(segments):
            prev_k = assignment((j - 1) % segments)
            cur_k = assignment(j)
            if cur_k != prev_k:
                try:
                    new_faces.append(bm.faces.new((ring(j), centers[prev_k], centers[cur_k])))
                except ValueError:
                    pass
        try:
            new_faces.append(bm.faces.new(tuple(centers)))
        except ValueError:
            pass
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is not None:
            for f in new_faces:
                for loop in f.loops:
                    loop[uv_layer].uv = Vector((0.48, 0.48))
        desired = Vector((0.0, 0.0, 0.0))
        desired[axis] = float(sign)
        for f in bm.faces:
            if f.normal.dot(desired) < 0.0:
                f.normal_flip()
    bm.to_mesh(plug.data)
    plug.data.update()
    bm.free()


def _retexture_plug_endgrain(plug, axis, segments, uv_center=(0.664, 0.707), uv_radius=0.030):
    """Map the planar plug coherently onto a light fibrous wood patch of the atlas."""
    if plug is None:
        return
    bm = bmesh.new()
    bm.from_mesh(plug.data)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is not None and len(bm.verts) >= 2 * segments:
        verts = list(bm.verts)
        other = [i for i in range(3) if i != axis]
        outer = [v.co for v in verts[:segments]]
        center = sum((Vector((c[other[0]], c[other[1]])) for c in outer), Vector((0.0, 0.0))) / len(outer)
        maxr = max(((Vector((c[other[0]], c[other[1]])) - center).length for c in outer), default=1.0)
        for f in bm.faces:
            for loop in f.loops:
                co = loop.vert.co
                d = (Vector((co[other[0]], co[other[1]])) - center) / max(maxr, 1e-6)
                loop[uv_layer].uv = Vector(uv_center) + d * uv_radius
    bm.to_mesh(plug.data)
    plug.data.update()
    bm.free()


def _roughen_plug(plug, axis, sign, segments, amplitude, seed):
    """Turn the flat sealing disc into a small splintered end-core surface."""
    if plug is None:
        return
    import math
    axis = int(axis)
    for vi, v in enumerate(plug.data.vertices):
        if vi < 2 * segments:
            ring = vi // segments
            j = vi % segments
        else:
            ring = 2
            j = (vi - 2 * segments) * max(1, segments // 3)
        weight = (0.22, 0.68, 1.0)[ring]
        wave = (0.52 * math.sin(j * 1.91 + seed) +
                0.31 * math.sin(j * 4.73 + seed * 1.37) +
                0.17 * math.cos(j * 7.11 - seed))
        v.co[axis] += sign * amplitude * weight * (0.55 + 0.45 * wave)
        # The round sealing core must not inflate the reviewed target bounds
        # or poke through the ground merely because the cavity is irregular.
        v.co.z = min(1.68, max(0.0, v.co.z))
    plug.data.update()


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, height=1.715, yaw_deg=-1.6)
    _stretch_x(objs, 1.15)
    main = objs[0]

    # Close the many small shell pinholes with coherent UVs before adding the
    # larger end plugs.  The old fan caps sampled unrelated UV islands and were
    # the source of several pitch-black triangular facets.
    vrmeshfix.fill_boundary_loops([main])

    # The raw log is a thin shell at both broken ends.  Recessed, uneven plugs
    # sit behind the jagged rims, so the silhouette stays broken while the end
    # no longer reads as a bottomless paper shell.
    plugs = [
        vrmeshfix.make_cavity_plug(main, axis=0, sign=+1, inset=0.00,
                                   radial_scale=1.05, segments=36,
                                   slice_frac=0.13, name="endcore_pos", relief=0.036, circular=True),
        vrmeshfix.make_cavity_plug(main, axis=0, sign=-1, inset=0.00,
                                   radial_scale=1.02, segments=36,
                                   slice_frac=0.13, name="endcore_neg", relief=0.032, circular=True),
    ]
    for plug, sign, amp, seed in ((plugs[0], +1, 0.045, 1.9), (plugs[1], -1, 0.038, 4.2)):
        _seal_plug_center(plug, axis=0, sign=sign, segments=36)
        _retexture_plug_endgrain(plug, axis=0, segments=36)
        _roughen_plug(plug, axis=0, sign=sign, segments=36, amplitude=amp, seed=seed)
    main = vrmeshfix.join_into(main, [p for p in plugs if p is not None])
    objs = [main]

    # Warm the blue-black bark, keep large wood variation, and replace part of
    # the mechanically repetitive Meshy microrelief with the project's bark grain.
    vrmeshfix.soften_basecolor_weave(objs, radius=1, keep=0.58)
    vrmeshfix.harmonize_basecolor(objs, "#6A4426", hue_keep=0.30, sat_mul=1.18, val_shift=0.035)
    vrmeshfix.tint_basecolor(objs, (1.16, 0.96, 0.78))
    vrmeshfix.adjust_basecolor_levels(objs, gain=1.05, gamma=0.90)
    vrmeshfix.overlay_detail_luminance(objs, BARK_SRC, strength=0.14, repeat=1)
    vrmeshfix.set_normal_strength(objs, 0.48)
    vrmeshy.clamp_material(objs, roughness_min=0.75, metallic=0.0)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

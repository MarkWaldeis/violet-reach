"""Umgestürzter Baumstamm A (log_fallen_a) — Meshy Klasse B.

Gate-Reparatur: UV-kohärente Dreiecksfüllung der Smart-Topology-Löcher (keine
schwarzen UV-Leerstellen mehr), zwei versetzte, reliefartige Splintholzkerne in
den hohlen Bruchenden, wärmere/höllere Rindenfärbung und eine reduzierte,
weniger repetitive Normalenstruktur. Geometrie und Texturen bleiben
deterministisch aus dem gepinnten Meshy-Rohmodell ableitbar.
"""
import os

import bpy
from mathutils import Matrix
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
                                   radial_scale=1.10, segments=36,
                                   slice_frac=0.13, name="endcore_pos", relief=0.030, circular=True),
        vrmeshfix.make_cavity_plug(main, axis=0, sign=-1, inset=0.00,
                                   radial_scale=1.06, segments=36,
                                   slice_frac=0.13, name="endcore_neg", relief=0.026, circular=True),
    ]
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

"""Kalkstein-Felsplatte A (rock_slab_a) — Meshy Klasse B.

Gate-Reparatur: die vielen schwarzen Dreieckslöcher an Oberfläche und Kanten
werden mit kohärenten UVs trianguliert statt mit ins Leere greifenden Fans;
anschließend mildert ein sehr schwacher Laplacian-Filter die spitzen Mesh-Zacken.
Die an sich gute Schichtung, hexagonale Silhouette und Kalkstein-Färbung bleiben
erhalten, wobei Crosshatch-Relief und schwarze Lochschatten reduziert werden.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(ASSET_DIR)))
ROCK_SRC = os.path.join(ROOT, "art", "textures", "src", "rock_chalk__acg_Rock018.jpg")


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, size_m=(4.0, 4.0, 0.8), yaw_deg=0.0)
    main = objs[0]

    # Most boundary loops are thin planar slots.  triangle_fill in vrmeshfix
    # closes the majority without crossing UV islands; the remaining deep layer
    # interpenetrations are visually masked rather than destructively remeshed,
    # preserving the class-B Meshy UVs.
    vrmeshfix.fill_boundary_loops([main])
    vrmeshfix.laplacian_smooth_region([main], zmin_frac=0.0, zmax_frac=1.0,
                                      iterations=1, factor=0.13)
    objs = [main]

    # Keep the good layered albedo, but reduce cloth-like fine crosshatch and
    # the harsh normal relief that made filled holes read as black triangles.
    vrmeshfix.soften_basecolor_weave(objs, radius=2, keep=0.45)
    vrmeshfix.harmonize_basecolor(objs, "#BCB296", hue_keep=0.55, sat_mul=0.78, val_shift=0.0)
    vrmeshfix.tint_basecolor(objs, (1.07, 1.00, 0.89))
    vrmeshfix.overlay_detail_luminance(objs, ROCK_SRC, strength=0.15, repeat=1)
    vrmeshfix.set_normal_strength(objs, 0.38)
    vrmeshy.clamp_material(objs, roughness_min=0.62, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.35)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.35)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

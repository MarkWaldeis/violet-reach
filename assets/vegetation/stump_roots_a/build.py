"""Alter Baumstumpf mit Wurzelanlauf A (stump_roots_a) — Meshy Klasse B.

Gate-Reparatur: kohärente UV-Füllung der zahlreichen Schalenschlitze, etwas
breiteres natürliches Footprint-Verhältnis, ein zurückgesetzter unregelmäßiger
Holzkern in der oberen Kavität sowie deutlich reduziertes ornamentales
Meshy-Normalrelief. Die Farbe wird wärmer und mit projekteigenem Barkorn
angereichert, ohne die gepinnten Meshy-UVs zu verlieren.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(ASSET_DIR)))
BARK_SRC = os.path.join(ROOT, "art", "textures", "src", "bark__acg_Bark012.jpg")


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, height=1.20, yaw_deg=-88.4)
    main = objs[0]

    # Gate measurement was ca. 1.64 x 1.41 m instead of the intended
    # 1.8 x 1.7 m.  Non-uniform footprint scaling preserves the trunk height.
    vrmeshfix.scale_xy([main], sx=1.10, sy=1.20)
    vrmeshfix.fill_boundary_loops([main])

    plug = vrmeshfix.make_cavity_plug(main, axis=2, sign=+1, inset=0.16,
                                      radial_scale=0.72, segments=32,
                                      slice_frac=0.18, name="crown_core", relief=0.026)
    if plug is not None:
        main = vrmeshfix.join_into(main, [plug])
    objs = [main]

    # The original relief looked like embossed ornamental cloth.  Flatten the
    # strongest repetitive normal detail, retain large cracks in albedo, then
    # overlay a restrained amount of the project's natural bark grain.
    vrmeshfix.soften_basecolor_weave(objs, radius=4, keep=0.22)
    vrmeshfix.harmonize_basecolor(objs, "#684326", hue_keep=0.34, sat_mul=1.10, val_shift=0.030)
    vrmeshfix.tint_basecolor(objs, (1.15, 0.95, 0.78))
    vrmeshfix.adjust_basecolor_levels(objs, gain=1.05, gamma=0.91)
    vrmeshfix.overlay_detail_luminance(objs, BARK_SRC, strength=0.34, repeat=3)
    vrmeshfix.set_normal_strength(objs, 0.16)
    vrmeshy.clamp_material(objs, roughness_min=0.75, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.30)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.30)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

"""Flaschenbaum Stamm A / Baobab (trunk_baobab_a) — Meshy Klasse B.

Gate-Reparatur: schwarze offene Rohrenden der Primäräste werden mit unregelmäßig
zugespitzten Holzkappen geschlossen, kleine Schalenpinholes UV-kohärent gefüllt,
der glatte lederartige Stamm erhält feine radiale Elephant-skin-Ridges und die
zu dunkle/glatt wirkende Rindentextur wird aufgehellt, entwebt und mit natürlicher
Projekt-Barkstruktur angereichert.
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
    vrmeshy.normalize(objs, height=12.0, yaw_deg=31.3)
    main = objs[0]

    # Most true baobab branch mouths are near the upper crown.  The lower trunk
    # pinholes are only filled, never extended into caps.
    caps, _ = vrmeshfix.make_jagged_tip_caps(
        main, zmin_frac=0.76, min_radius=0.020, max_radius=0.20,
        length_mul=1.55, segments=9, cluster_radius=0.54,
        ratio_min=0.20, name="baobab_tip")
    vrmeshfix.fill_boundary_loops([main])
    if caps:
        main = vrmeshfix.join_into(main, caps)
    objs = [main]

    # A very small radial displacement breaks the smooth clay/leather trunk
    # into fine vertical elephant-skin furrows without altering the silhouette.
    vrmeshfix.bark_ridge_displacement(main, amplitude=0.022, zmin_frac=0.035,
                                      zmax_frac=0.72, frequencies=(17.0, 39.0), seed=2.4)

    # The raw albedo was nearly uniform dark brown.  Retain broad colour
    # variation but suppress cloth-like high frequency, lift the value range
    # and reintroduce non-repetitive bark grain at modest strength.
    vrmeshfix.soften_basecolor_weave(objs, radius=2, keep=0.48)
    vrmeshfix.harmonize_basecolor(objs, "#6A513B", hue_keep=0.38, sat_mul=1.02, val_shift=0.045)
    vrmeshfix.tint_basecolor(objs, (1.14, 0.97, 0.82))
    vrmeshfix.adjust_basecolor_levels(objs, gain=1.08, gamma=0.87)
    vrmeshfix.overlay_detail_luminance(objs, BARK_SRC, strength=0.30, repeat=1)
    vrmeshfix.set_normal_strength(objs, 0.42)
    vrmeshy.clamp_material(objs, roughness_min=0.72, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.50)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.50)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

"""Mehrstämmige Schirmakazie Stamm B (trunk_acacia_b) — Meshy Klasse B.

Gate-Reparatur: offene bzw. schwarze Rohrenden der vielen abgeschnittenen Äste
werden zuerst erkannt, dann die Schalenpinholes UV-kohärent geschlossen und an
den Astspitzen unregelmäßig zugespitzte Bruchkappen ergänzt. Der gemeinsame
Wurzelfuß bekommt einen etwas breiteren organischen Übergang; die ansonsten
überzeugende Schirmakazien-Silhouette und Skalierung bleiben unverändert.
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
    vrmeshy.normalize(objs, height=6.80, yaw_deg=20.8)
    main = objs[0]

    # Detect tube mouths before the pinholes are closed.  Clustering prevents
    # several small defects in one end cap from becoming duplicate cones.
    caps, _ = vrmeshfix.make_jagged_tip_caps(
        main, zmin_frac=0.72, min_radius=0.024, max_radius=0.20,
        length_mul=1.80, segments=9, cluster_radius=0.46,
        ratio_min=0.28, name="acacia_tip")
    vrmeshfix.fill_boundary_loops([main])
    if caps:
        main = vrmeshfix.join_into(main, caps)
    objs = [main]

    # Broaden only the lowest trunk/root transition; the umbrella geometry is
    # otherwise already correct and should not be re-sculpted.
    vrmeshfix.flare_base(main, height=0.72, strength=0.13)

    # Material was close to passing.  Keep the original bark colour structure,
    # only remove the cloth-like sharpness and add a faint natural grain.
    vrmeshfix.soften_basecolor_weave(objs, radius=1, keep=0.62)
    vrmeshfix.harmonize_basecolor(objs, "#5B3E25", hue_keep=0.44, sat_mul=1.05, val_shift=0.025)
    vrmeshfix.tint_basecolor(objs, (1.13, 0.96, 0.81))
    vrmeshfix.overlay_detail_luminance(objs, BARK_SRC, strength=0.11, repeat=1)
    vrmeshfix.set_normal_strength(objs, 0.55)
    vrmeshy.clamp_material(objs, roughness_min=0.70, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.40)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.40)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

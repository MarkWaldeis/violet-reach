"""Kreidefels-Findling C (boulder_chalk_c) — Meshy Klasse B.

Gate-Reparatur: zu geringe Tiefenausdehnung wird nichtlinear in Y korrigiert,
kleine Schalenöffnungen UV-kohärent gefüllt, das regelmäßige Crosshatch-/Beton-
Mikrorelief in Albedo und Normalmap deutlich abgeschwächt und blaue/orange
Flecken Richtung canyon_chalk entsättigt. Schichtfugen bleiben als niederfrequente
Struktur erhalten, wirken aber nicht mehr als schwarze Zierleisten.
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
    vrmeshy.normalize(objs, height=1.0, yaw_deg=-0.7)
    main = objs[0]

    # Gate: depth only ~0.96 m despite a 1.4 m target.  Broaden perpendicular
    # to the long axis while leaving length and height unchanged.
    vrmeshfix.scale_xy([main], sx=1.0, sy=1.35)
    vrmeshfix.fill_boundary_loops([main])
    objs = [main]

    # Remove the uniform plaster/crosshatch impression.  A low keep fraction
    # preserves seams and larger chips but suppresses the repeating weave; the
    # palette compression removes implausible blue and orange staining.
    vrmeshfix.soften_basecolor_weave(objs, radius=2, keep=0.28)
    vrmeshfix.harmonize_basecolor(objs, "#C2B69B", hue_keep=0.38, sat_mul=0.72, val_shift=0.0)
    vrmeshfix.tint_basecolor(objs, (1.08, 1.00, 0.88))
    vrmeshfix.overlay_detail_luminance(objs, ROCK_SRC, strength=0.23, repeat=1)
    vrmeshfix.set_normal_strength(objs, 0.42)
    vrmeshy.clamp_material(objs, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.25)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.25)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

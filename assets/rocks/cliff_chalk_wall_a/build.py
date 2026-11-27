"""Kalkstein-Klippenwand A (cliff_chalk_wall_a) — Meshy-Asset Klasse A + 0-Credit Klippen-Sculpt.

Bricht die starre Quader-Silhouette am Plateau und entfernt das künstliche Zahn-Muster
an der hinteren Oberkante über gestufte Schichtterrassen (vrcliffs.shape_cliff), verfeinert
das Mikrorelief im Objektraum und setzt einen 2,5-m-Eingrabe-Rand unter z = 0.
"""
import os

import vrmeshy
import vrmeshfix
import vrcliffs

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=25.0, yaw_deg=2.7)
    vrcliffs.shape_cliff(
        objs,
        top_drop=4.8,
        top_teeth_trim=3.4,
        top_taper_xy=0.22,
        back_sign=-1.0,
        back_slope_out=2.6,
        back_shelf_amp=1.35,
        edge_chamfer_amp=0.16,
        seed=4111,
    )
    vrmeshy.grade_basecolor(objs, "#BCB296", strength=0.38)
    vrcliffs.clean_chalk_surface(objs, target_hex="#BCB296", dark_floor=0.20, dark_lift=0.30,
                                 deweave_rad=2, deweave_keep=0.55, normal_strength=0.45, bump_strength=0.35)
    vrmeshy.clamp_material(objs, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=2.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=2.5)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

"""Gespaltenes Inselmonument A (monument_split_disc_a) — Meshy Klasse A-multiview, Rework v3.

Das v3-Multiview-Rohmodell ist geschlossen, massiv am Sockel angebunden und
hat eine offene, scharf facettierte Bruchfuge ohne die review-kritisierte
blasige Wabe.  Die frühere geometrische Glättung, Albedo-Harmonisierung,
Farbüberlagerung und Normalenlöschung bleiben entfernt; das unbearbeitete
Normalrelief des v3-Modells ist bereits ausreichend ruhig.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=0.0)

    # Keine geometrische oder Normalen-Glättung mehr: Sockelkontakt und
    # Bruchkante kommen bereits aus dem geschlossenen v3-Rohmodell.
    vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=1.5)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

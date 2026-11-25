"""Gespaltenes Inselmonument A (monument_split_disc_a) — Meshy Klasse A-multiview, Rework v2.

Das v2-Multiview-Rohmodell ist geschlossen, massiv am Sockel angebunden und
frei vom v1-Paneel-/Webmuster.  Die frühere globale und lokale Laplacian-
Glättung, Albedo-Harmonisierung, Farbüberlagerung und die fast vollständige
Normalenlöschung sind entfernt.  Nur die poröse Steinnormalmap wird moderat
abgeschwächt, damit die großen monolithischen Flächen ruhig bleiben.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=-2.0)

    # Keine geometrische Glättung mehr: Sockelkontakt und Bruchkante kommen
    # bereits aus dem geschlossenen v2-Rohmodell.  Die moderate Normalstärke
    # erhält natürliche Poren, ohne sie zum dominanten Relief werden zu lassen.
    vrmeshfix.set_normal_strength(objs, 0.35)
    vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=1.5)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

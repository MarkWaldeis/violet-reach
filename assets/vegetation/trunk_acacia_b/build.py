"""Mehrstämmige Schirmakazie Stamm B (trunk_acacia_b) — Meshy Klasse B, Rework v2.

Die v2-Referenz erzeugt organisch verschmolzene Stämme und verjüngte Astenden;
die v1-Bruchkappen, Basisaufwertung und retuschierte Rindentextur sind daher
entfernt.  `drop_loose` entfernt weiterhin kleine, nachweislich freischwebende
Smart-Topology-Fragmente, bevor die verbleibenden Pinholes geschlossen werden.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, height=6.80, yaw_deg=20.8)
    main = objs[0]

    # Keine prozeduralen Astspitzen-Kappen mehr: die v2-Enden sind im Rohmodell
    # bereits verjüngt.  Es werden nur kleine technische Schalenlöcher gefüllt.
    vrmeshfix.fill_boundary_loops([main])

    vrmeshy.clamp_material(objs, roughness_min=0.70, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.40)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.40)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

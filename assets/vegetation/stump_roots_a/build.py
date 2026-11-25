"""Alter Baumstumpf mit Wurzelanlauf A (stump_roots_a) — Meshy Klasse B, Rework v3.

Das v3-Rohmodell zeigt den natürlichen faserigen Holzbruch und die durchgehenden
Wurzeln bereits ohne die review-kritisierten ornamentalen Kronenplatten.  Die
alten Formkorrekturen bleiben entfernt; es bleiben nur technische Lochfüllung,
Materialregeln und die Boden-Skirt-Vorbereitung.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, height=1.20, yaw_deg=0.0)
    main = objs[0]

    # Keine künstliche Kronenkappe mehr: die v3-Bruchkrone ist bereits massiv
    # und lesbar.  Nur vorhandene Smart-Topology-Pinholes werden geschlossen.
    vrmeshfix.fill_boundary_loops([main])

    vrmeshy.clamp_material(objs, roughness_min=0.75, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.30)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.30)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

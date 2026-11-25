"""Umgestürzter Baumstamm A (log_fallen_a) — Meshy Klasse B, Rework v2.

Das v2-Rohmodell bringt die kritischen volumetrischen, splitterigen Bruchenden
bereits mit.  Die v1-Endkerne, Endgrain-Retexturierung, prozeduralen Plugs und
aggressive Farb-/Reliefkorrektur sind deshalb bewusst entfernt.  Übrig bleiben
nur die asset-neutralen Schritte: kleine Smart-Topology-Pinholes schließen,
Material clampen und Normalen orientieren.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, height=1.715, yaw_deg=-1.6)
    main = objs[0]

    # v2 hat keine offenen Flachkappen mehr; nur die üblichen kleinen
    # Smart-Topology-Pinholes werden UV-kohärent geschlossen.
    vrmeshfix.fill_boundary_loops([main])

    vrmeshy.clamp_material(objs, roughness_min=0.75, metallic=0.0)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

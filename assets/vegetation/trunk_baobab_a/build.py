"""Flaschenbaum Stamm A / Baobab (trunk_baobab_a) — Meshy Klasse B, Rework v3.

Das v3-Rohmodell hat eine breite Krone aus sich verjüngenden, teils gegabelten
Primärästen und unregelmäßige Elephant-skin-Längsfalten bereits in Geometrie
und Textur.  Die alten Formkorrekturen bleiben entfernt; übrig bleiben
technische Pinhole-Füllung, Material-Clamp und Boden-Skirt.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, height=12.0, yaw_deg=0.0)
    main = objs[0]

    # Keine prozeduralen Astkappen oder aufgesetzten Rinden-Ridges mehr.  Nur
    # die kleinen verbleibenden Smart-Topology-Pinholes werden UV-kohärent gefüllt.
    vrmeshfix.fill_boundary_loops([main])

    vrmeshy.clamp_material(objs, roughness_min=0.72, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.50)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.50)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

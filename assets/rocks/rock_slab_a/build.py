"""Kalkstein-Felsplatte A (rock_slab_a) — Meshy Klasse B, Rework v2.

Das v2-Rohmodell ist eine natürlich gebrochene, unregelmäßige Sedimentplatte;
die v1-Glättung der gesamten Platte sowie Crosshatch-/Farbretusche sind
entfernt.  Bewusst bleiben nur die UV-kohärente Pinhole-Füllung, das
Material-Clamp und die Boden-Skirt-Vorbereitung.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.02)
    vrmeshy.normalize(objs, size_m=(4.0, 4.0, 0.8), yaw_deg=0.0)
    main = objs[0]

    # Die v2-Kanten sind bereits natürlich gebrochen; kein globales Laplacian-
    # Glätten mehr.  Nur technische Smart-Topology-Pinholes werden geschlossen.
    vrmeshfix.fill_boundary_loops([main])

    vrmeshy.clamp_material(objs, roughness_min=0.62, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.35)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.35)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

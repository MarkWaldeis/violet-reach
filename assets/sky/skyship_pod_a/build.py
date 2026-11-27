"""Himmelskapsel A (Groß) (skyship_pod_a) — Meshy-Asset Klasse A.

Bereitet das schwebende Himmelskörper-Modell (skyship_pod_a/model/A-v1/model.glb) ohne
Eingrabe-Rand auf: lose Splitter entfernen, auf 60.0 m
Gesamthöhe skalieren, helles Band-Kontrastverhältnis (#8553C6) bewahren und
Rauheit >= 0,55 / Metall 0,0 für matte Außenpaneele setzen.
"""
import os

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=60.0, yaw_deg=0.0)
    vrmeshfix.adjust_basecolor_levels(objs, gain=1.08, gamma=0.96, lift=0.01)
    vrmeshy.clamp_material(objs, roughness_min=0.55, metallic=0.0)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

"""Gespaltenes Inselmonument A (monument_split_disc_a) — Meshy Klasse A-multiview.

Gate-Reparatur: die starke Fernsilhouette bleibt unverändert. Das regelmäßige
Web-/Crosshatch-Muster wird in Albedo und Normalmap deutlich gedämpft und durch
zurückhaltende weiße Steinkörnung ersetzt. Im Übergang Podest/Scheibe glättet
ein enger, radial begrenzter Laplacian-Bandpass die zerknitterte Interpenetration,
ohne die harte zentrale Spaltung oder die großen Steinplatten neu zu formen.
"""
import os

import bmesh
from mathutils import Vector
import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(ASSET_DIR)))
STONE_SRC = os.path.join(ROOT, "art", "textures", "src", "stone_white__acg_Rock042S.jpg")


def _bury_skirt_below_ground(objs, depth):
    """Place the burial_skirt cut seam at z = 0 so the vertical skirt stays underground."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        body = [v for v in bm.verts if v.co.z > -depth + 1e-3]
        if body:
            z0 = min(v.co.z for v in body)
            for v in body:
                v.co.z -= z0
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is not None:
            center = Vector((0.5, 0.5))
            for f in bm.faces:
                if any(v.co.z <= -depth + 1e-3 for v in f.verts) and any(v.co.z > -depth + 1e-3 for v in f.verts):
                    for loop in f.loops:
                        if loop.vert.co.z <= -depth + 1e-3:
                            uv = loop[uv_layer].uv
                            loop[uv_layer].uv = uv + (center - uv) * 0.04
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=-2.0)
    main = objs[0]

    # The crumpled interpenetration is concentrated just above the plinth.
    # Smooth only that band near the central axis; preserve the monumental
    # split, outer silhouette and large panel breaks.
    # One gentle global pass removes the high-frequency geometric fabric
    # embossing baked into the dense multiview sculpt.  A stronger local pass
    # then cleans the crumpled plinth/disc intersection.
    vrmeshfix.laplacian_smooth_region([main], zmin_frac=0.0, zmax_frac=1.0,
                                      iterations=1, factor=0.22)
    vrmeshfix.laplacian_smooth_region([main], zmin_frac=0.045, zmax_frac=0.16,
                                      radius_xy=9.0, iterations=2, factor=0.34)
    objs = [main]

    # Strongly suppress the fabric-like periodic weave while preserving broad
    # stains, masonry breaks and panel value differences.  The fine stone source
    # is project-authored/tileable and only contributes luminance variation.
    vrmeshfix.soften_basecolor_weave(objs, radius=3, keep=0.12)
    vrmeshfix.harmonize_basecolor(objs, "#DCCDB1", hue_keep=0.48, sat_mul=0.74, val_shift=0.015)
    vrmeshfix.tint_basecolor(objs, (1.06, 1.00, 0.90))
    vrmeshfix.overlay_detail_luminance(objs, STONE_SRC, strength=0.22, repeat=1)
    vrmeshfix.set_normal_strength(objs, 0.06)
    vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    _bury_skirt_below_ground(objs, depth=1.5)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

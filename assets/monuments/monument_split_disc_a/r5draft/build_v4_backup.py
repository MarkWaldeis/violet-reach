"""Gespaltenes Inselmonument A (monument_split_disc_a) — Meshy Klasse A-multiview, Rework v3.

Das v3-Multiview-Rohmodell ist geschlossen, massiv am Sockel angebunden und
hat eine offene, scharf facettierte Bruchfuge.  Die v4-Materialreparatur bleibt
kreditfrei und rein textur-/materialseitig: Das wormy micro-crackle wird im
Albedo-Atlas entschärft, die Farbe auf den Wetterkalkstein der Art-Vorgabe
harmonisiert und die sonnenbeschienene Spaltlippe nur in den zugehörigen
UV-Inseln leicht entsättigt/gekühlt.  Geometrie, Silhouette, Bruchfuge und
Plinthe werden nicht verändert.
"""
import os

import numpy as np

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _cleft_uv_mask(objs, res=1024, x_max=2.65, zmin_frac=0.19, zmax_frac=0.97,
                   depth_normal_min=0.35):
    """Rasterize UV space used by the front/back-facing inner cleft lips.

    The selection is deliberately geometric instead of a rectangular UV box:
    several unrelated plinth/outer-face islands share the same atlas region.
    Only triangles close to the open split, in the disc body height range and
    with a substantial front/back normal component are marked.  The result is a
    small feathered weight mask in Blender's bottom-left image-row convention.
    """
    mask = np.zeros((res, res), dtype=np.float32)
    tri_count = 0
    poly_count = 0
    for obj in [o for o in objs if o and o.type == "MESH"]:
        me = obj.data
        uvlay = me.uv_layers.active
        if uvlay is None or not len(me.vertices):
            continue
        mw = np.array(obj.matrix_world, dtype=np.float64)
        rot = mw[:3, :3]
        trans = mw[:3, 3]
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        world = co.reshape((-1, 3)) @ rot.T + trans
        zlo = float(world[:, 2].min())
        zhi = float(world[:, 2].max())
        zspan = max(1e-9, zhi - zlo)
        for poly in me.polygons:
            ids = list(poly.vertices)
            c = world[ids].mean(axis=0)
            zf = (c[2] - zlo) / zspan
            if abs(c[0]) >= x_max or zf < zmin_frac or zf > zmax_frac:
                continue
            # The criticised stripe is the sunlit front/back lip of the split.
            # X-dominant fracture side walls are left completely untouched.
            n = rot @ np.array(poly.normal[:], dtype=np.float64)
            nlen = float(np.linalg.norm(n))
            if nlen <= 1e-9 or abs(n[1] / nlen) < depth_normal_min:
                continue
            poly_count += 1
            uvs = np.array([uvlay.data[li].uv[:] for li in poly.loop_indices], dtype=np.float64)
            # Fan-triangulate the rare n-gons produced by the burial skirt cut.
            for k in range(1, len(uvs) - 1):
                tri = uvs[(0, k, k + 1), :]
                tri_count += 1
                uvmin = tri.min(axis=0)
                uvmax = tri.max(axis=0)
                x0 = max(0, int(np.floor(uvmin[0] * res)) - 1)
                x1 = min(res - 1, int(np.ceil(uvmax[0] * res)) + 1)
                y0 = max(0, int(np.floor(uvmin[1] * res)) - 1)
                y1 = min(res - 1, int(np.ceil(uvmax[1] * res)) + 1)
                if x1 < x0 or y1 < y0:
                    continue
                ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                px = (xs + 0.5) / res
                py = (ys + 0.5) / res
                a, b, cc = tri[0], tri[1], tri[2]
                v0 = cc - a
                v1 = b - a
                v2x = px - a[0]
                v2y = py - a[1]
                den = v0[0] * v1[1] - v1[0] * v0[1]
                if abs(den) < 1e-14:
                    continue
                inv = 1.0 / den
                u = (v2x * v1[1] - v1[0] * v2y) * inv
                v = (v0[0] * v2y - v2x * v0[1]) * inv
                inside = (u >= -0.02) & (v >= -0.02) & ((u + v) <= 1.02)
                if inside.any():
                    mask[y0:y1 + 1, x0:x1 + 1][inside] = 1.0
    # Close rasterisation pinholes, then feather the edge.  One texel at mask
    # resolution is four texels in the 4k atlas, so the final fade is narrow
    # and remains inside Meshy's island padding.
    pad = np.pad(mask, 1, mode="constant")
    dilated = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            dilated = np.maximum(dilated, pad[dy:dy + res, dx:dx + res])
    soft = vrmeshy._box_blur(dilated, 2)
    return soft, {
        "polys": poly_count,
        "tris": tri_count,
        "mask_frac": float((dilated > 0).mean()),
        "mask_max": float(soft.max()),
    }


def _mute_warm_cleft_strip(objs, sat_reduce=0.30, red_cool=0.018, blue_boost=0.009,
                           mask_res=1024):
    """Locally desaturate/cool the warm cleft-lip stripe in base colour.

    This is a chroma correction only.  Luminance, fracture shadows, large mineral
    stains, the silhouette, the open cleft and the plinth geometry are preserved.
    """
    weight_small, info = _cleft_uv_mask(objs, res=mask_res)
    made = {}
    for node in vrmeshfix._basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        w, h = img.size
        px = vrmeshfix._image_pixels(img)
        yy = (np.arange(h) * weight_small.shape[0] // h).astype(int)
        xx = (np.arange(w) * weight_small.shape[1] // w).astype(int)
        weight = weight_small[yy][:, xx]
        rgb = px[..., :3].copy()
        corr = rgb.copy()
        corr[..., 0] = np.clip(corr[..., 0] - float(red_cool), 0.0, 1.0)
        corr[..., 2] = np.clip(corr[..., 2] + float(blue_boost), 0.0, 1.0)
        lum = (corr @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[..., None]
        corr = corr + (lum - corr) * float(sat_reduce)
        corr = np.clip(corr, 0.0, 1.0)
        out = rgb * (1.0 - weight[..., None]) + corr * weight[..., None]
        made[img] = vrmeshfix._replace_image(
            img, np.concatenate([out, px[..., 3:]], axis=-1), "_cleft_muted"
        )
    vrmeshfix._swap_images(objs, made)
    info["images"] = len(made)
    return info


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=0.0)

    # Steinregeln zuerst: kein Metall, hohe Mindestrauheit.  Die eigentliche
    # v4-Reparatur ist anschließend rein textur-/materialseitig.
    vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=1.5)

    # Ablation v4 am gleichen Nahwinkel: Normalstärke 0 allein änderte die
    # sichtbare Mikrostruktur kaum, während soften_basecolor_weave den
    # hochfrequenten Porenkontrast deutlich reduzierte.  Daher bleibt die
    # Normalmap nicht bei 0, sondern nur moderat abgeschwächt.
    vrmeshfix.soften_basecolor_weave(objs, radius=3, keep=0.30)
    stripe_info = _mute_warm_cleft_strip(objs)
    vrmeshfix.harmonize_basecolor(objs, "#DCCDB1", hue_keep=0.50, sat_mul=0.80)
    vrmeshfix.set_normal_strength(objs, 0.35)
    print("VR_CLEFT_STRIPE", stripe_info, flush=True)

    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

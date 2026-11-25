"""Flaschenbaum Stamm A / Baobab (trunk_baobab_a) — Meshy Klasse B, Rework v4.

Das v4-Rohmodell stammt aus einem einzigen budgetierten Multi-Image-to-3D-
Standardtask aus drei konsistenten Ansichten.  Es ist erstmals volumetrisch
radial statt planar.  Die alten Formkorrekturen bleiben entfernt; übrig bleiben
das Entfernen des kleinen freischwebenden Kronenfragments, technische
Pinhole-Füllung, Material-Clamp und Boden-Skirt.

v4-Materialreparatur ohne weitere Meshy-Credits: Meshys gleichmäßige
Mud-Crack-/Reptilien-Mikrostruktur wird nur in den Texturen frequenzselektiv
abgeschwächt.  Die großen, bereits im v4-Material vorhandenen Falten- und
Narbenbänder werden dagegen leicht verstärkt; die Geometrie bleibt unverändert.
"""
import json
import os

import bpy
import numpy as np

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))

# Das Asset-Budget ist 2048 px (asset.json).  Die Meshy-Rohdatei liefert 4k;
# die 2x2-Mittelung auf das Budget entfernt bereits einen Teil des subpixel-
# Crackle-Aliasing, ohne die großen UV-Inseln oder die UVs selbst zu verändern.
TARGET_TEXTURE_SIZE = 2048

# Gemessene mittlere Texeldichte des v4-UVs: ca. 242 px/m bei 4k, also ca.
# 121 px/m bei 2k.  Damit liegen die Filterradien bei etwa 2,5 cm (micro),
# 13 cm (mid) und 53 cm (broad) — genau der Bereich zwischen Reptilien-Crackle
# und elefantenhautartigen Spannfalten.
BASE_MICRO_RADIUS = 3
BASE_MID_RADIUS = 16
BASE_BROAD_RADIUS = 64
BASE_MICRO_KEEP = 0.20
BASE_MID_GAIN = 1.40
BASE_BROAD_GAIN = 1.30
BASE_SCAR_BOOST = 0.30

NORMAL_MICRO_RADIUS = 3
NORMAL_MID_RADIUS = 14
NORMAL_BROAD_RADIUS = 56
NORMAL_MICRO_KEEP = 0.22
NORMAL_MID_GAIN = 1.25
NORMAL_BROAD_GAIN = 1.35
NORMAL_STRENGTH = 0.90

_LUMINANCE = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _box_blur32(channel, radius):
    """Float32-separable box blur with edge clamping (same shape as input)."""
    radius = max(0, int(radius))
    src = channel.astype(np.float32, copy=False)
    if radius == 0:
        return src.copy()
    pad = np.pad(src, ((radius, radius), (0, 0)), mode="edge")
    c = np.concatenate([
        np.zeros((1, pad.shape[1]), dtype=np.float64),
        np.cumsum(pad, axis=0, dtype=np.float64),
    ])
    out = ((c[2 * radius + 1:] - c[:-(2 * radius + 1)]) / (2 * radius + 1)).astype(np.float32)
    pad = np.pad(out, ((0, 0), (radius, radius)), mode="edge")
    c = np.concatenate([
        np.zeros((pad.shape[0], 1), dtype=np.float64),
        np.cumsum(pad, axis=1, dtype=np.float64),
    ], axis=1)
    return ((c[:, 2 * radius + 1:] - c[:, :-(2 * radius + 1)]) / (2 * radius + 1)).astype(np.float32)


def _blur_channels(rgb, radius):
    out = np.empty_like(rgb, dtype=np.float32)
    for ch in range(rgb.shape[-1]):
        out[..., ch] = _box_blur32(rgb[..., ch], radius)
    return out


def _downsample_rgba(px, target=TARGET_TEXTURE_SIZE):
    """Integer area downsample to at most `target` pixels on the long edge."""
    h, w = px.shape[:2]
    factor = max(1, max(h, w) // int(target))
    if factor <= 1:
        return px.astype(np.float32, copy=True)
    h2, w2 = h // factor, w // factor
    cropped = px[:h2 * factor, :w2 * factor].astype(np.float32, copy=False)
    return cropped.reshape(h2, factor, w2, factor, 4).mean(axis=(1, 3), dtype=np.float32)


def _replace_image_resized(img, px, suffix):
    new = bpy.data.images.new(img.name + suffix, px.shape[1], px.shape[0], alpha=True)
    # Assigning colorspace clears the pixel buffer — it must come before the write.
    new.colorspace_settings.name = img.colorspace_settings.name
    new.pixels.foreach_set(px.astype(np.float32, copy=False).ravel())
    new.pack()
    return new


def _swap_and_drop(objs, mapping):
    """Swap generated images in and drop orphaned originals from the .blend."""
    vrmeshfix._swap_images(objs, mapping)
    for old in list(mapping):
        if old.users == 0:
            bpy.data.images.remove(old)


def _luminance_metrics(px, steps=(1, 2, 4, 8, 16, 32, 64)):
    lum = px[..., :3] @ _LUMINANCE
    out = {}
    for step in steps:
        step = int(step)
        if step >= min(lum.shape[:2]):
            continue
        gx = np.abs(lum[:, step:] - lum[:, :-step]).mean()
        gy = np.abs(lum[step:, :] - lum[:-step, :]).mean()
        out[str(step)] = round(float((gx + gy) * 0.5), 6)
    return out


def _frequency_rebalance(rgb, micro_radius, mid_radius, broad_radius,
                         micro_keep, mid_gain, broad_gain, scar_boost=0.0):
    """Suppress only micro contrast while retaining/boosting broad bark bands.

    The decomposition is exact when all gains are one.  Therefore large-scale
    color masses and fold shadows are not globally shifted; only the selected
    frequency bands are reweighted.  `scar_boost` is nonlinear: strong broad
    bands already present in the Meshy texture receive slightly more gain than
    weak blotches, creating larger irregular tension/scar plates instead of
    uniformly raising noise.
    """
    low_micro = _blur_channels(rgb, micro_radius)
    low_mid = _blur_channels(rgb, mid_radius)
    low_broad = _blur_channels(rgb, broad_radius)

    broad_band = low_mid - low_broad
    if scar_boost > 0.0:
        lum_band = (low_mid[..., :3] @ _LUMINANCE) - (low_broad[..., :3] @ _LUMINANCE)
        q95 = float(np.quantile(np.abs(lum_band), 0.95))
        scar_weight = 1.0 + float(scar_boost) * np.clip(np.abs(lum_band) / max(q95, 1e-5), 0.0, 1.0)
        broad_band = broad_band * scar_weight[..., None]

    out = (low_broad + broad_band * float(broad_gain) +
           (low_micro - low_mid) * float(mid_gain) +
           (rgb - low_micro) * float(micro_keep))
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _normal_metrics(px):
    xy = px[..., :2].astype(np.float32) * 2.0 - 1.0
    low_micro = _blur_channels(xy, NORMAL_MICRO_RADIUS)
    low_mid = _blur_channels(xy, NORMAL_MID_RADIUS)
    low_broad = _blur_channels(xy, NORMAL_BROAD_RADIUS)
    micro = xy - low_micro
    mid = low_micro - low_mid
    broad = low_mid - low_broad
    return {
        "rms_xy": round(float(np.sqrt(np.mean(xy * xy))), 6),
        "rms_micro": round(float(np.sqrt(np.mean(micro * micro))), 6),
        "rms_mid": round(float(np.sqrt(np.mean(mid * mid))), 6),
        "rms_broad": round(float(np.sqrt(np.mean(broad * broad))), 6),
    }


def _normal_image_nodes(objs):
    nodes = []
    mats = []
    for obj in objs:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat and mat.node_tree and mat not in mats:
                mats.append(mat)
    for mat in mats:
        for node in mat.node_tree.nodes:
            if node.type != "NORMAL_MAP" or not node.inputs["Color"].links:
                continue
            for link in node.inputs["Color"].links:
                src = link.from_node
                if src.type == "TEX_IMAGE" and src.image and src not in nodes:
                    nodes.append(src)
    return nodes


def _repair_elephant_hide_material(objs):
    """Credit-free texture-only repair of Meshy's reptile/mud-crack surface."""
    info = {"basecolor": {}, "normal": {}, "target_texture_size": TARGET_TEXTURE_SIZE}
    made = {}

    for node in vrmeshfix._basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        small = _downsample_rgba(vrmeshfix._image_pixels(img))
        before = _luminance_metrics(small)
        rgb = _frequency_rebalance(
            small[..., :3], BASE_MICRO_RADIUS, BASE_MID_RADIUS, BASE_BROAD_RADIUS,
            BASE_MICRO_KEEP, BASE_MID_GAIN, BASE_BROAD_GAIN, BASE_SCAR_BOOST,
        )
        out = np.concatenate([rgb, small[..., 3:]], axis=-1).astype(np.float32)
        after = _luminance_metrics(out)
        made[img] = _replace_image_resized(img, out, "_elephanthide")
        info["basecolor"] = {
            "source_size": [int(img.size[0]), int(img.size[1])],
            "output_size": [int(out.shape[1]), int(out.shape[0])],
            "gradient_abs_before": before,
            "gradient_abs_after": after,
            "bands_px_at_2k": [BASE_MICRO_RADIUS, BASE_MID_RADIUS, BASE_BROAD_RADIUS],
            "gains": [BASE_MICRO_KEEP, BASE_MID_GAIN, BASE_BROAD_GAIN, BASE_SCAR_BOOST],
        }

    normal_made = {}
    for node in _normal_image_nodes(objs):
        img = node.image
        if img in normal_made:
            continue
        small = _downsample_rgba(vrmeshfix._image_pixels(img))
        before = _normal_metrics(small)
        xy = small[..., :2] * 2.0 - 1.0
        low_micro = _blur_channels(xy, NORMAL_MICRO_RADIUS)
        low_mid = _blur_channels(xy, NORMAL_MID_RADIUS)
        low_broad = _blur_channels(xy, NORMAL_BROAD_RADIUS)
        xy_out = (low_broad + (low_mid - low_broad) * NORMAL_BROAD_GAIN +
                  (low_micro - low_mid) * NORMAL_MID_GAIN +
                  (xy - low_micro) * NORMAL_MICRO_KEEP)
        xy_out = np.clip(xy_out, -0.35, 0.35).astype(np.float32)
        rr = np.sum(xy_out * xy_out, axis=-1)
        z = np.sqrt(np.clip(1.0 - rr, 0.25, 1.0)).astype(np.float32)
        rgb = np.concatenate([(xy_out + 1.0) * 0.5, z[..., None]], axis=-1)
        out = np.concatenate([rgb, small[..., 3:]], axis=-1).astype(np.float32)
        after = _normal_metrics(out)
        normal_made[img] = _replace_image_resized(img, out, "_elephantnormal")
        info["normal"] = {
            "source_size": [int(img.size[0]), int(img.size[1])],
            "output_size": [int(out.shape[1]), int(out.shape[0])],
            "before": before,
            "after": after,
            "bands_px_at_2k": [NORMAL_MICRO_RADIUS, NORMAL_MID_RADIUS, NORMAL_BROAD_RADIUS],
            "gains": [NORMAL_MICRO_KEEP, NORMAL_MID_GAIN, NORMAL_BROAD_GAIN],
            "strength": NORMAL_STRENGTH,
        }

    # Die beiden Reparaturpfade erzeugen neue Bilder und hängen sie in denselben
    # Materialgraph ein.  Original-Packshots werden verworfen, damit die .blend
    # nicht unnötig doppelt so groß wird.
    made.update(normal_made)
    _swap_and_drop(objs, made)
    normal_nodes = vrmeshfix.set_normal_strength(objs, NORMAL_STRENGTH)
    info["normal"]["nodes"] = int(normal_nodes)
    print("VR_BAOBAB_MATERIAL " + json.dumps(info, sort_keys=True), flush=True)


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    # Das v4-Rohmodell enthält ein einzelnes kleines, vollständig getrenntes
    # Kronenfragment (ca. 2,2 % der Dreiecke).  Es ist ein Rekonstruktionsartefakt,
    # kein sichtbarer Hauptast, und wird deshalb mit der 3-%-Schwelle entfernt.
    vrmeshy.drop_loose(objs, min_fraction=0.03)
    # Die orientierte Rohbox liegt fast exakt auf +Y (gemessener Gierwinkel +89,1°).
    # Zur kanonischen Maßdefinition wird die breiteste Kronenachse auf +X gedreht.
    vrmeshy.normalize(objs, height=12.0, yaw_deg=-89.1)
    main = objs[0]

    # Keine prozeduralen Astkappen oder aufgesetzten Rinden-Ridges.  Das v4-
    # Standardnetz ist bereits wasserdicht; der Loop-Filler bleibt nur als
    # harmlose technische Sicherung und ist hier erwartungsgemäß ein No-op.
    vrmeshfix.fill_boundary_loops([main])

    vrmeshy.clamp_material(objs, roughness_min=0.72, metallic=0.0)
    _repair_elephant_hide_material(objs)
    vrmeshy.burial_skirt(objs, depth=0.50)
    vrmeshfix.bury_skirt_below_ground(objs, depth=0.50)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

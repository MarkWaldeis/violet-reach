"""Deterministic 0-credit Blender repair helpers for chalk cliffs and rock pillars.

Separate from vrmeshfix.py so existing exported Meshy assets keep unchanged source hashes.
Works directly on normalised Blender mesh objects (Z up, ground at z=0, buried skirt below).
"""
import math

import bpy
import bmesh
import numpy as np

import vrmeshy
import vrmeshfix


def _smoothstep(edge0, edge1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - edge0) / max(edge1 - edge0, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash2(ix, iy, seed):
    v = np.asarray(ix, dtype=np.float64) * 127.1 + np.asarray(iy, dtype=np.float64) * 269.5 + float(seed) * 31.7
    x = np.sin(v) * 43758.5453123
    return x - np.floor(x)


def _noise2(x, y, seed):
    xi = np.floor(x).astype(np.int64)
    yi = np.floor(y).astype(np.int64)
    xf, yf = x - xi, y - yi
    u = xf * xf * (3.0 - 2.0 * xf)
    v = yf * yf * (3.0 - 2.0 * yf)
    a = _hash2(xi, yi, seed) * (1.0 - u) + _hash2(xi + 1, yi, seed) * u
    b = _hash2(xi, yi + 1, seed) * (1.0 - u) + _hash2(xi + 1, yi + 1, seed) * u
    return (a * (1.0 - v) + b * v) * 2.0 - 1.0


def _strata_steps(coord, seed, ramp_frac=0.22):
    band = np.floor(coord)
    frac = coord - band
    blend = _smoothstep(0.0, ramp_frac, frac)
    h0 = _hash2(band - 1.0, np.zeros_like(band), seed)
    h1 = _hash2(band, np.zeros_like(band), seed)
    return h0 * (1.0 - blend) + h1 * blend


def _get_coords(me):
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return co.reshape((-1, 3))


def _set_coords(me, pos):
    me.vertices.foreach_set("co", np.asarray(pos, dtype=np.float64).reshape(-1))
    me.update()


def shape_cliff(
    objs,
    *,
    top_drop=0.0,
    top_teeth_trim=0.0,
    top_taper_xy=0.0,
    back_sign=1.0,
    back_slope_out=0.0,
    back_shelf_amp=0.0,
    inner_fracture_amp=0.0,
    concave_box=None,
    edge_chamfer_amp=0.0,
    seed=4109,
):
    """Break rigid box silhouettes, flat sheared walls, smooth corners, and top teeth in-place."""
    for obj in [o for o in objs if o and o.type == "MESH"]:
        me = obj.data
        pos = _get_coords(me)
        if not len(pos):
            continue
        x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
        above = z >= 0.0
        zmax = max(float(z.max()), 1.0)
        xmin, xmax = float(x.min()), float(x.max())
        ymin, ymax = float(y.min()), float(y.max())
        xmid = 0.5 * (xmin + xmax)
        ymid = 0.5 * (ymin + ymax)
        xh = max(0.5 * (xmax - xmin), 1.0)
        yh = max(0.5 * (ymax - ymin), 1.0)

        tz = np.clip(z / zmax, 0.0, 1.0)
        nx_n = (x - xmid) / xh
        ny_n = (y - ymid) / yh

        # 1. Stepped asymmetric limestone terrace across the flat top plateau + wing ends
        if top_drop > 0.0:
            upper_w = _smoothstep(0.62, 0.94, tz)
            wing_drop = np.clip((np.abs(nx_n) - 0.15) / 0.85, 0.0, 1.0) ** 1.35
            back_side = _smoothstep(-0.15, 0.75, ny_n * back_sign)
            terrace = _strata_steps(x * 0.16 + y * 0.11 + 1.5 * _noise2(x * 0.06, y * 0.06, seed), seed + 3)
            slope_drop = top_drop * (0.28 + 0.52 * wing_drop + 0.35 * back_side) * (0.65 + 0.45 * terrace)
            pos[:, 2] -= np.where(above, upper_w * slope_drop, 0.0)

        # 2. Explicitly shave/step the rim where Meshy generated artificial cube teeth along top-back
        if top_teeth_trim > 0.0:
            rim_mask = _smoothstep(0.84, 0.98, tz) * _smoothstep(0.10, 0.78, ny_n * back_sign)
            shelf = _strata_steps(x * 0.22 + 0.4 * _noise2(x * 0.12, y * 0.12, seed + 7), seed + 11)
            pos[:, 2] -= np.where(above, rim_mask * top_teeth_trim * (0.65 + 0.55 * shelf), 0.0)

        # 3. Organic inward taper & stepped benching on rigid vertical box sides/back
        if top_taper_xy > 0.0:
            up = _smoothstep(0.28, 0.96, tz)
            step_n = 0.78 + 0.36 * _strata_steps(z * 0.34 + 0.25 * _noise2(x * 0.15, y * 0.15, seed + 17), seed + 19)
            scale_in = 1.0 - up * top_taper_xy * step_n
            pos[:, 0] = np.where(above, xmid + (pos[:, 0] - xmid) * scale_in, pos[:, 0])
            pos[:, 1] = np.where(above, ymid + (pos[:, 1] - ymid) * scale_in, pos[:, 1])

        if edge_chamfer_amp > 0.0:
            corner_w = _smoothstep(0.45, 0.92, np.abs(nx_n)) * _smoothstep(0.45, 0.92, np.abs(ny_n)) * _smoothstep(0.08, 0.45, tz)
            fract = _noise2(x * 0.28, z * 0.32, seed + 23) * 0.5 + 0.5
            pull = 1.0 - corner_w * edge_chamfer_amp * (0.4 + 0.6 * fract)
            pos[:, 0] = np.where(above, xmid + (pos[:, 0] - xmid) * pull, pos[:, 0])
            pos[:, 1] = np.where(above, ymid + (pos[:, 1] - ymid) * pull, pos[:, 1])

        # 4. Break flat sheared vertical back wall with sloped outward rock buttresses + stepped strata ledges
        if back_slope_out > 0.0 or back_shelf_amp > 0.0:
            bw = _smoothstep(-0.05, 0.65, ny_n * back_sign) * _smoothstep(0.03, 0.22, tz)
            # Slope flares outward toward base so back becomes a natural sloped limestone buttress
            slope_profile = (1.0 - tz) ** 1.15
            terr = _strata_steps(z * 0.42 + 0.08 * x, seed + 29) * 0.55 + 0.45 * _noise2(x * 0.24, z * 0.28, seed + 31)
            rib = 0.5 + 0.5 * np.sin(x * 0.35 + 1.4 * _noise2(x * 0.11, z * 0.09, seed + 37))
            dy = back_sign * bw * (back_slope_out * slope_profile * (0.65 + 0.45 * rib) + back_shelf_amp * (terr - 0.35))
            pos[:, 1] += np.where(above, dy, 0.0)

        # 5. Break smooth unfractured concave inner wall on L-corner cliff
        if inner_fracture_amp > 0.0 and concave_box is not None:
            bx0, bx1, by0, by1 = concave_box
            in_x = _smoothstep(bx0 - 3.0, bx0 + 1.5, pos[:, 0]) * (1.0 - _smoothstep(bx1 - 1.5, bx1 + 3.0, pos[:, 0]))
            in_y = _smoothstep(by0 - 3.0, by0 + 1.5, pos[:, 1]) * (1.0 - _smoothstep(by1 - 1.5, by1 + 3.0, pos[:, 1]))
            cw = in_x * in_y * _smoothstep(0.05, 0.20, tz)
            horiz_ledge = _strata_steps(z * 0.48 + 0.06 * (pos[:, 0] + pos[:, 1]), seed + 41) - 0.45
            vert_crack = -np.maximum(0.0, np.abs(_noise2((pos[:, 0] + pos[:, 1]) * 0.36, z * 0.09, seed + 43)) - 0.15)
            disp = cw * inner_fracture_amp * (0.75 * horiz_ledge + 0.45 * vert_crack)
            # Displace diagonally outward along corner bisector / radial vector from local mass center
            rad_v = np.stack([pos[:, 0] - xmid, pos[:, 1] - ymid], axis=1)
            rn = np.maximum(np.linalg.norm(rad_v, axis=1, keepdims=True), 1.0)
            rad_u = rad_v / rn
            pos[:, 0] += np.where(above, rad_u[:, 0] * disp, 0.0)
            pos[:, 1] += np.where(above, rad_u[:, 1] * disp, 0.0)

        # Keep burial skirt bottom strictly clamped at z_min
        _set_coords(me, pos)


def heal_cavity_patch(objs, xmin, xmax, ymin, ymax, zmin, zmax):
    """Smooth out isolated accidental Meshy holes/cross scars inside a world-space bounding box."""
    for obj in [o for o in objs if o and o.type == "MESH"]:
        me = obj.data
        pos = _get_coords(me)
        mask = (
            (pos[:, 0] >= xmin) & (pos[:, 0] <= xmax) &
            (pos[:, 1] >= ymin) & (pos[:, 1] <= ymax) &
            (pos[:, 2] >= zmin) & (pos[:, 2] <= zmax)
        )
        idxs = set(np.flatnonzero(mask).tolist())
        if not idxs:
            continue
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        patch_verts = [bm.verts[i] for i in idxs if i < len(bm.verts)]
        # Project deep inward concave outlier vertices flush to outer percentile surface before smoothing
        pts = np.array([v.co[:] for v in patch_verts])
        mid_xy = pts[:, :2].mean(axis=0)
        # Push toward outer envelope along dominant box normal (-Y or +Y)
        sign_y = -1.0 if abs(ymin) > abs(ymax) or ymin < 0 and ymax <= 0 else 1.0
        target_y = float(np.quantile(pts[:, 1], 0.18 if sign_y < 0 else 0.82))
        for v in patch_verts:
            if (sign_y < 0 and v.co.y > target_y + 0.18) or (sign_y > 0 and v.co.y < target_y - 0.18):
                v.co.y = v.co.y * 0.25 + target_y * 0.75
        for _ in range(14):
            bmesh.ops.smooth_vert(bm, verts=patch_verts, factor=0.65, use_axis_x=False, use_axis_y=True, use_axis_z=False)
        bm.to_mesh(me)
        me.update()
        bm.free()

        # Paint over ultra-dark pixels mapped inside that small scar region using patch boundary median luminance
        bm2 = bmesh.new()
        bm2.from_mesh(me)
        bm2.verts.ensure_lookup_table()
        uv_layer = bm2.loops.layers.uv.active
        patch_uvs = []
        if uv_layer is not None:
            for f in bm2.faces:
                if any(v.index in idxs for v in f.verts):
                    for l in f.loops:
                        patch_uvs.append((l[uv_layer].uv.x, l[uv_layer].uv.y))
        bm2.free()
        if patch_uvs:
            for node in vrmeshfix._basecolor_nodes([obj]):
                img = node.image
                px = vrmeshfix._image_pixels(img)
                h, w, _ = px.shape
                lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
                us = np.clip((np.array([u for u, _ in patch_uvs]) * (w - 1)).astype(int), 0, w - 1)
                vs = np.clip((np.array([v for _, v in patch_uvs]) * (h - 1)).astype(int), 0, h - 1)
                region = np.zeros((h, w), dtype=bool)
                region[vs, us] = True
                # Expand selection slightly across scar triangles
                for _ in range(6):
                    region = np.pad(region, 1)
                    region = (region[1:-1, 1:-1] | region[:-2, 1:-1] | region[2:, 1:-1] | region[1:-1, :-2] | region[1:-1, 2:])
                bright = px[..., :3][region & (lum > 0.35)]
                fill_rgb = np.median(bright, axis=0) if len(bright) else np.array([0.74, 0.69, 0.58], dtype=np.float32)
                dark_mask = region & (lum < 0.32)
                if np.any(dark_mask):
                    w_dark = np.clip((0.32 - lum) / 0.22, 0.0, 1.0) * dark_mask.astype(np.float32)
                    px[..., :3] = px[..., :3] * (1.0 - w_dark[..., None]) + fill_rgb * w_dark[..., None]
                    new_img = vrmeshfix._replace_image(img, px, "_healed")
                    vrmeshfix._swap_images([obj], {img: new_img})


def facet_pillar(objs, strata_step=2.6, planar_sides=7, seam_smooth_rad=0.45, seed=7719):
    """Turn soft melted pillar bulges into angular faceted limestone strata and erase vertical UV seams."""
    for obj in [o for o in objs if o and o.type == "MESH"]:
        me = obj.data
        pos = _get_coords(me)
        if not len(pos):
            continue
        x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
        above = z >= 0.0
        cx, cy = float(x[above].mean()), float(y[above].mean())
        zmax = max(float(z.max()), 1.0)
        tz = np.clip(z / zmax, 0.0, 1.0)

        dx, dy = x - cx, y - cy
        r = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)

        # Quantize radial silhouette onto angled planar rock cleavage facets
        sec = (2.0 * math.pi) / planar_sides
        # Vary plane angles slightly with sedimentary bed height so column looks geological, not a prism
        bed = np.floor(z / strata_step)
        ang_shift = 0.22 * _hash2(bed, np.zeros_like(bed), seed)
        a_local = ((ang + ang_shift) % sec) - 0.5 * sec
        # Flatten convex bulges in mid-shaft (0.20 < tz < 0.88) toward polygonal chord plane
        plane_ratio = 1.0 / np.maximum(np.cos(a_local), 0.72)
        target_r = r * (0.78 + 0.22 / np.maximum(plane_ratio, 1e-3))
        # Sharp horizontal sedimentary benching steps
        step_r = 1.0 + 0.08 * (_strata_steps(z / strata_step, seed + 5, ramp_frac=0.14) - 0.5)
        mid_w = _smoothstep(0.14, 0.30, tz) * (1.0 - _smoothstep(0.88, 0.99, tz))
        new_r = (r * (1.0 - 0.55 * mid_w) + target_r * (0.55 * mid_w)) * np.where(above, step_r, 1.0)

        scale_r = new_r / np.maximum(r, 1e-6)
        pos[:, 0] = np.where(above, cx + dx * scale_r, pos[:, 0])
        pos[:, 1] = np.where(above, cy + dy * scale_r, pos[:, 1])

        # Gentle vertical step break near straight vertical bisecting seams (around x ≈ cx or y ≈ cy)
        seam_break = _noise2(ang * 3.0, z * 0.25, seed + 13) * 0.22 * _smoothstep(0.15, 0.35, tz)
        pos[:, 0] += np.where(above, np.cos(ang) * seam_break, 0.0)
        pos[:, 1] += np.where(above, np.sin(ang) * seam_break, 0.0)
        _set_coords(me, pos)


def clean_chalk_surface(objs, *, target_hex="#BCB296", dark_floor=0.22, dark_lift=0.45,
                        deweave_rad=3, deweave_keep=0.30, normal_strength=0.32, bump_strength=0.35):
    """Compress dark zebra/maze bands, remove wormy noise, and add crisp object-space limestone microbump."""
    h_hex = target_hex.lstrip("#")
    target = np.array([int(h_hex[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)

    if deweave_keep < 1.0:
        vrmeshfix.soften_basecolor_weave(objs, radius=deweave_rad, keep=deweave_keep)
    vrmeshfix.set_normal_strength(objs, normal_strength)

    if dark_lift > 0.0:
        made = {}
        for node in vrmeshfix._basecolor_nodes(objs):
            img = node.image
            if img in made:
                continue
            px = vrmeshfix._image_pixels(img)
            lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            mask = np.clip((dark_floor - lum) / max(dark_floor, 0.05), 0.0, 1.0) * float(dark_lift)
            out = np.clip(px[..., :3] * (1.0 - mask[..., None]) + target * 0.72 * mask[..., None], 0.0, 1.0)
            made[img] = vrmeshfix._replace_image(img, np.concatenate([out, px[..., 3:]], axis=-1), "_cleanstrata")
        vrmeshfix._swap_images(objs, made)

    # Install multi-scale object-space limestone microbump (zero UV worminess)
    seen = set()
    for obj in [o for o in objs if o and o.type == "MESH"]:
        for mat in obj.data.materials:
            if not mat or not mat.node_tree or mat in seen:
                continue
            seen.add(mat)
            nt = mat.node_tree
            nodes, links = nt.nodes, nt.links
            bsdf = nodes.get("Principled BSDF")
            if bsdf is None:
                continue
            geom = nodes.new("ShaderNodeTexCoord")
            noise_rock = nodes.new("ShaderNodeTexNoise")
            noise_rock.noise_dimensions = "3D"
            noise_rock.inputs["Scale"].default_value = 4.5
            noise_rock.inputs["Detail"].default_value = 5.0
            noise_rock.inputs["Roughness"].default_value = 0.72
            links.new(geom.outputs["Object"], noise_rock.inputs["Vector"])
            bump = nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = float(bump_strength)
            bump.inputs["Distance"].default_value = 0.05
            links.new(noise_rock.outputs["Fac"], bump.inputs["Height"])
            if bsdf.inputs["Normal"].is_linked:
                links.new(bsdf.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

"""Gespaltenes Inselmonument A (monument_split_disc_a) — Meshy Klasse A-multiview, Rework v3/v4+.

Das v3-Multiview-Rohmodell liefert eine starke Silhouette, ist aber material- und
anschlussseitig zu glatt bzw. im Mikrobereich reptilienartig.  Die creditfreie
v4+-Reparatur bleibt bewusst deterministisch und lokal:

* kontinuierliche, in die Plinthe versenkte Kalkstein-Lippen bilden eine
  lesbare Auflager-/Nutzone um die beiden Monolithhälften, ohne die offene
  Keilspalte zu überbrücken oder das Ausgangsmesh zu zerschneiden,
* die großen planaren Bruchwände erhalten eine topologieerhaltende, grob
  geschichtete Reliefstruktur mit gedeckelten Einbuchtungen Richtung Spalt,
* Albedo- und Normaltextur werden entporengt bzw. durch feine, räumlich
  variierende Mineralgranulation ersetzt; warme Projektionsstreifen in der
  Spaltlippe werden nach der Farbharmonisierung chromatisch neutralisiert.

Es werden keine neuen KI-Modelle oder externen Texturen verwendet.  Die groben
Dimensionen, die offene Keilspalte und die Plinthensilhouette bleiben erhalten.
"""
import math
import os

import bpy
import numpy as np

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Kleine numerische Helfer


def _smoothstep(edge0, edge1, x):
    edge1 = float(edge1)
    edge0 = float(edge0)
    t = np.clip((np.asarray(x) - edge0) / max(edge1 - edge0, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _positions(obj):
    me = obj.data
    pos = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", pos)
    return pos.reshape((-1, 3))


def _write_positions(obj, pos):
    obj.data.vertices.foreach_set("co", np.asarray(pos, dtype=np.float64).reshape(-1))
    obj.data.update()


def _mesh_edges(me):
    edges = set()
    for poly in me.polygons:
        ids = list(poly.vertices)
        for i, a in enumerate(ids):
            b = ids[(i + 1) % len(ids)]
            if a != b:
                edges.add((min(a, b), max(a, b)))
    return np.array(sorted(edges), dtype=np.int32)


def _neighbour_mean(values, edges):
    values = np.asarray(values)
    if values.ndim == 1:
        out = np.zeros(len(values), dtype=np.float64)
    else:
        out = np.zeros_like(values, dtype=np.float64)
    count = np.zeros(len(values), dtype=np.float64)
    np.add.at(out, edges[:, 0], values[edges[:, 1]])
    np.add.at(out, edges[:, 1], values[edges[:, 0]])
    np.add.at(count, edges[:, 0], 1.0)
    np.add.at(count, edges[:, 1], 1.0)
    valid = count > 0
    if values.ndim == 1:
        out[valid] /= count[valid]
    else:
        out[valid] /= count[valid, None]
    return out, count


def _surface_data(obj):
    """Polygon centres/normals plus per-vertex incident-normal statistics."""
    me = obj.data
    pos = _positions(obj)
    npoly = len(me.polygons)
    centres = np.zeros((npoly, 3), dtype=np.float64)
    normals = np.zeros((npoly, 3), dtype=np.float64)
    poly_ids = []
    abs_acc = np.zeros((len(pos), 3), dtype=np.float64)
    signed_x = np.zeros(len(pos), dtype=np.float64)
    inc_count = np.zeros(len(pos), dtype=np.float64)
    for pi, poly in enumerate(me.polygons):
        ids = np.array(poly.vertices, dtype=np.int32)
        if len(ids) < 3:
            continue
        c = pos[ids].mean(axis=0)
        n = np.array(poly.normal[:], dtype=np.float64)
        ln = float(np.linalg.norm(n))
        if ln > 1e-12:
            n /= ln
        centres[pi] = c
        normals[pi] = n
        poly_ids.append(ids)
        np.add.at(abs_acc, ids, np.abs(n))
        np.add.at(signed_x, ids, n[0])
        np.add.at(inc_count, ids, 1.0)
    valid = inc_count > 0
    abs_mean = np.zeros_like(abs_acc)
    abs_mean[valid] = abs_acc[valid] / inc_count[valid, None]
    signed_x_mean = np.zeros_like(signed_x)
    signed_x_mean[valid] = signed_x[valid] / inc_count[valid]
    return {
        "pos": pos,
        "centres": centres,
        "normals": normals,
        "poly_ids": poly_ids,
        "vertex_abs_normal": abs_mean,
        "vertex_signed_nx": signed_x_mean,
    }


def _diffuse_scalar(values, edges, passes=1, amount=0.42):
    w = np.asarray(values, dtype=np.float64).copy()
    for _ in range(max(0, int(passes))):
        avg, count = _neighbour_mean(w, edges)
        valid = count > 0
        w[valid] = w[valid] * (1.0 - amount) + avg[valid] * amount
    return w


# ---------------------------------------------------------------------------
# Geometrie: Mikrocrackle beruhigen, Bruch reliefartig gliedern, Scheibe einlassen


def _hash01(values):
    x = np.sin(values * 127.1 + 311.7) * 43758.5453123
    return x - np.floor(x)


def _roughen_split_fracture(obj, amplitude=0.52):
    """Replace billboard-flat cleft walls by coarse layered stone relief.

    The improved selector is primarily spatial: everything close to the open
    wedge belongs to the fracture/lip system, while x-dominant scarps are still
    favoured farther out.  Relief is per-monolith coherent (negative x moves
    left, positive x moves right).  Positive relief recedes outwards and may be
    strong; inward protrusion is capped so the empty wedge cannot close.
    """
    data = _surface_data(obj)
    pos = data["pos"].copy()
    centres = data["centres"]
    normals = data["normals"]
    an = np.abs(normals)
    nxfrac = an[:, 0] / np.maximum(an.sum(axis=1), 1e-9)
    x = centres[:, 0]
    z = centres[:, 2]
    central = 1.0 - _smoothstep(2.85, 3.85, np.abs(x))
    xdominant = _smoothstep(0.24, 0.48, nxfrac)
    inner_core = 1.0 - _smoothstep(1.65, 2.45, np.abs(x))
    orientation = np.maximum(inner_core, xdominant)
    poly_score = (_smoothstep(8.00, 10.0, z) * central * orientation)

    acc = np.zeros(len(pos), dtype=np.float64)
    cnt = np.zeros(len(pos), dtype=np.float64)
    for pi, ids in enumerate(data["poly_ids"]):
        np.add.at(acc, ids, poly_score[pi])
        np.add.at(cnt, ids, 1.0)
    weight = np.zeros(len(pos), dtype=np.float64)
    valid = cnt > 0
    weight[valid] = acc[valid] / cnt[valid]
    edges = _mesh_edges(obj.data)
    weight = _diffuse_scalar(weight, edges, passes=1, amount=0.30)
    weight = np.clip(weight, 0.0, 1.0)

    vx = pos[:, 0]
    vy = pos[:, 1]
    vz = pos[:, 2]
    side = np.where(vx < 0.0, -1.0, 1.0)

    # Piecewise-metre-scale bedding/fracture shelves.  Each shelf receives a
    # deterministic signed offset; a narrow continuous blend at the boundary
    # forms a scarp rather than a disconnected mesh crack.
    bandcoord = vz / 2.15 + 0.16 * np.sin(vy * 0.71 + side * 0.43) + side * 0.117
    band = np.floor(bandcoord)
    frac = bandcoord - band
    hcur = _hash01(band * 17.173 + side * 31.31)
    hprev = _hash01((band - 1.0) * 17.173 + side * 31.31)
    blend_width = 0.065
    blend = np.clip(frac / blend_width, 0.0, 1.0)
    layered01 = np.where(frac < blend_width,
                         hprev * (1.0 - blend) + hcur * blend,
                         hcur)
    layered = layered01 * 2.0 - 1.0

    # Larger undulations break the exact horizontality of the shelves.  The
    # frequencies stay metre-scale; no new worm/centimetre noise is added.
    coarse = (0.58 * np.sin(vz * 0.53 + vy * 0.31 + side * 0.82) +
              0.29 * np.sin(vz * 1.07 - vy * 0.46 + side * 1.61) +
              0.13 * np.sin(vz * 2.03 + vy * 0.92 + 0.29))
    relief = np.clip(0.72 * layered + 0.42 * coarse, -1.0, 1.0)

    # positive relief = outward recession, negative relief = inward protrusion.
    outward_sign = side
    inward_cap = np.where(relief < 0.0, 0.32, 1.0)
    zweight = _smoothstep(8.00, 10.0, vz)
    dx = outward_sign * relief * inward_cap * float(amplitude) * weight * zweight
    pos[:, 0] += dx
    _write_positions(obj, pos)
    return {
        "affected": int(np.count_nonzero(weight * zweight > 0.05)),
        "weight_max": float((weight * zweight).max()) if len(weight) else 0.0,
        "dx_abs_mean": float(np.abs(dx[weight * zweight > 0.05]).mean()) if np.count_nonzero(weight * zweight > 0.05) else 0.0,
        "amplitude": float(amplitude),
        "max_abs_dx": float(np.abs(dx).max()) if len(dx) else 0.0,
    }


# ---------------------------------------------------------------------------
# Auflager/Nut:# ---------------------------------------------------------------------------
# Auflager/Nut: massive segmentierte Kalkstein-Kämme an der Plinthe


def _projected_uvs_for_prism(me, base_uv=(0.080, 0.055), scale=0.006, seed=0):
    uv_layer = me.uv_layers.new(name="UVMap")
    bu, bv = base_uv
    bu += (seed % 3) * 0.030
    bv += ((seed // 3) % 2) * 0.026
    me.update()
    for poly in me.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            # Offset all world coordinates into positive range before scaling;
            # raw negative x/y would otherwise clamp large areas to one texel.
            if abs(n.z) >= max(abs(n.x), abs(n.y)):
                uv = (bu + (co.x + 10.5) * scale,
                      bv + (co.y + 6.5) * scale)
            elif abs(n.y) >= abs(n.x):
                uv = (bu + (co.x + 10.5) * scale,
                      bv + (co.z - 5.85) * scale * 1.6)
            else:
                uv = (bu + (co.y + 6.5) * scale,
                      bv + (co.z - 5.85) * scale * 1.6)
            uv_layer.data[li].uv = (min(0.318, max(0.045, uv[0])),
                                    min(0.238, max(0.035, uv[1])))


def _socket_profile(x, ysign, ycentre, halfwidth, z_bottom, z_top):
    z0 = float(z_bottom)
    h = max(0.05, float(z_top) - z0)
    yi = float(ycentre) - float(ysign) * float(halfwidth)
    yo = float(ycentre) + float(ysign) * float(halfwidth)
    return [
        (x, yi, z0),
        (x, yo, z0),
        (x, yo, z0 + h * 0.36),
        (x, yo - ysign * halfwidth * 0.18, z0 + h * 0.76),
        (x, yi + ysign * halfwidth * 0.22, z_top),
        (x, yi, z_top + 0.035),
    ]


def _orient_closed_mesh_outwards(me):
    verts = np.array([v.co[:] for v in me.vertices], dtype=np.float64)
    centre = verts.mean(axis=0)
    me.update()
    for poly in me.polygons:
        ids = list(poly.vertices)
        fc = verts[ids].mean(axis=0)
        if np.dot(np.array(poly.normal[:], dtype=np.float64), fc - centre) < 0.0:
            poly.flip()
    me.update()


def _make_socket_rim(name, xa, xb, ysign, material, seed, samples=17):
    """Continuous low chamfered socket lip, tapered into the plinth at both ends."""
    xs = np.linspace(float(xa), float(xb), int(samples))
    z_bottom = 6.255
    verts = []
    nprof = 6
    for si, x in enumerate(xs):
        t = si / max(1, len(xs) - 1)
        rise = math.sin(math.pi * t) ** 0.72
        # Lower than the first crenellated draft, but wide and continuous.  A
        # slight long-wave variation reads as hand-set/weathered stone rather
        # than as a machined rail.
        ztop = 6.74 + (1.08 + 0.060 * math.sin(x * 1.17 + seed * 0.73)) * rise
        width_factor = 0.72 + 0.28 * math.sin(math.pi * t)
        halfwidth = 1.50 * width_factor
        ycentre = float(ysign) * (4.35 + 0.035 * math.sin(x * 0.73 + seed))
        verts.extend(_socket_profile(float(x), ysign, ycentre, halfwidth, z_bottom, ztop))

    faces = []
    last = len(xs) - 1
    faces.append(tuple(range(nprof - 1, -1, -1)))
    faces.append(tuple(range(last * nprof, (last + 1) * nprof)))
    for si in range(len(xs) - 1):
        a0 = si * nprof
        b0 = (si + 1) * nprof
        for j in range(nprof):
            nj = (j + 1) % nprof
            faces.append((a0 + j, a0 + nj, b0 + nj, b0 + j))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    _orient_closed_mesh_outwards(me)
    _projected_uvs_for_prism(me, seed=seed)
    me.materials.append(material)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _make_socket_courses(main_obj):
    """Create continuous stone cheek lips forming two open socket channels.

    The lips overlap the monolith sides, sink into the top plinth and taper out
    at their ends.  They read as a carved bearing groove/auflager rather than
    as separate decorative blocks and never bridge the central empty split.
    """
    material = main_obj.data.materials[0] if main_obj.data.materials else None
    made = []
    if material is None:
        return made, {"rims": 0}
    seed = 0
    ranges = ((-8.65, -0.10), (0.10, 8.65))
    for half, (xa, xb) in enumerate(ranges):
        for ysign in (-1, 1):
            rim = _make_socket_rim(
                f"socket_lip_{half}_{'front' if ysign > 0 else 'back'}",
                xa, xb, ysign, material, seed,
            )
            made.append(rim)
            seed += 1
    return made, {"rims": len(made), "triangles_est": len(made) * 192}


# ---------------------------------------------------------------------------
# Texture repair: stone re-graining, pore suppression, normal flattening


def _noise_layer(shape, cell, blur, seed):
    h, w = shape
    rng = np.random.default_rng(seed)
    sh = int(math.ceil(h / float(cell)))
    sw = int(math.ceil(w / float(cell)))
    small = rng.standard_normal((sh, sw), dtype=np.float32)
    rep = np.repeat(np.repeat(small, int(cell), axis=0), int(cell), axis=1)[:h, :w]
    if blur > 0:
        rep = vrmeshy._box_blur(rep, int(blur))
    rep = rep - float(rep.mean())
    rep = rep / max(float(rep.std()), 1e-6)
    return rep.astype(np.float32, copy=False)


def regrain_stone_basecolor(objs, seed=4217):
    """Remove worm/pore high frequency and replace it with mineral grain.

    Unlike plain blur+keep, the residual is split into luminance and chroma:
    dark pitting is inpainted towards its local stone body, chroma speckle is
    reduced more strongly than luminance grain, and a spatially varying low-
    amplitude granular field restores matte limestone tooth.  Large stains,
    fracture shading and UV-island layout remain untouched.
    """
    metrics = {"images": 0, "hf_before": [], "hf_after": [], "pit_pixels": 0}
    made = {}
    for node in vrmeshfix._basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = vrmeshfix._image_pixels(img)
        rgb = px[..., :3].copy()
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        low = np.empty_like(rgb)
        low_lum = np.empty_like(lum)
        for ch in range(3):
            low[..., ch] = vrmeshy._box_blur(rgb[..., ch], 7)
        low_lum = low[..., 0] * 0.2126 + low[..., 1] * 0.7152 + low[..., 2] * 0.0722
        high = rgb - low
        high_lum = lum - low_lum
        hf_before = float(high_lum.std())

        # Dark worm strokes/pores are suppressed harder than positive mineral
        # sparkle.  Chroma noise is reduced even further, preventing the
        # reptilian multicoloured micro-mottling seen in the last review.
        keep_lum = np.where(high_lum < 0.0, 0.035, 0.105).astype(np.float32)
        high_lum_part = high_lum[..., None] * keep_lum[..., None]
        chroma = high - high_lum[..., None]
        filtered = low + high_lum_part + chroma * 0.045

        # Black top-hat correction: small circular holes are dark relative to
        # a slightly wider local support.  Pull exactly those texels back to
        # their surrounding mineral body; broad shading is in the low pass and
        # therefore remains unchanged.
        lum_f = filtered[..., 0] * 0.2126 + filtered[..., 1] * 0.7152 + filtered[..., 2] * 0.0722
        support = vrmeshy._box_blur(lum_f, 7)
        pit = support - lum_f
        pit_w = np.clip((pit - 0.010) / 0.040, 0.0, 1.0) * 0.94
        metrics["pit_pixels"] += int(np.count_nonzero(pit_w > 0.35))
        filtered = filtered * (1.0 - pit_w[..., None]) + low * pit_w[..., None]

        # New low-amplitude stone tooth.  Three blurred noise octaves are
        # granular rather than linear/wormy; a coarse independent field varies
        # the strength so the surface is not uniformly noisy everywhere.
        h, w = lum.shape
        grain = (0.30 * _noise_layer((h, w), 128, 15, seed + 11) +
                 0.40 * _noise_layer((h, w), 18, 3, seed + 23) +
                 0.30 * _noise_layer((h, w), 5, 1, seed + 37))
        spatial = 0.72 + 0.34 * _noise_layer((h, w), 256, 25, seed + 51)
        spatial = np.clip(spatial, 0.42, 1.12)
        grain = grain / max(float(grain.std()), 1e-6)
        signed_grain = np.where(grain < 0.0, grain * 0.52, grain * 0.82)
        mod = 1.0 + signed_grain * spatial * 0.018
        out0 = np.clip(filtered * mod[..., None], 0.0, 1.0)
        # A second black-top-hat pass runs after the replacement grain so the
        # grain itself cannot recreate circular black pore noise.
        lum0 = out0[..., 0] * 0.2126 + out0[..., 1] * 0.7152 + out0[..., 2] * 0.0722
        support0 = vrmeshy._box_blur(lum0, 5)
        pit0 = support0 - lum0
        pit0_w = np.clip((pit0 - 0.012) / 0.045, 0.0, 1.0) * 0.72
        metrics["pit_pixels"] += int(np.count_nonzero(pit0_w > 0.35))
        out = np.clip(out0 * (1.0 - pit0_w[..., None]) + filtered * pit0_w[..., None], 0.0, 1.0)

        out_lum = out[..., 0] * 0.2126 + out[..., 1] * 0.7152 + out[..., 2] * 0.0722
        out_low = np.empty_like(out_lum)
        out_low = vrmeshy._box_blur(out_lum, 3)
        metrics["hf_before"].append(hf_before)
        metrics["hf_after"].append(float((out_lum - out_low).std()))
        made[img] = vrmeshfix._replace_image(
            img, np.concatenate([out, px[..., 3:]], axis=-1), "_stone_regrain"
        )
        metrics["images"] += 1
    vrmeshfix._swap_images(objs, made)
    if metrics["hf_before"]:
        metrics["hf_reduction"] = float(1.0 - np.mean(metrics["hf_after"]) / max(np.mean(metrics["hf_before"]), 1e-9))
    return metrics


def _image_node_feeding(socket, depth=0):
    if depth > 5 or not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.type == "TEX_IMAGE" and node.image:
        return node
    for inp in node.inputs:
        if inp.is_linked:
            found = _image_node_feeding(inp, depth + 1)
            if found is not None:
                return found
    return None


def flatten_normal_microtexture(objs, keep=0.10, xy_compress=0.72):
    """Low-pass tangent-space normal vectors, preserving broad chipped relief."""
    made = {}
    count = 0
    for obj in [o for o in objs if o and o.type == "MESH"]:
        for mat in obj.data.materials:
            if not mat or not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if node.type != "NORMAL_MAP" or "Color" not in node.inputs:
                    continue
                tex = _image_node_feeding(node.inputs["Color"])
                if tex is None or tex.image in made:
                    continue
                img = tex.image
                px = vrmeshfix._image_pixels(img)
                vec = px[..., :3] * 2.0 - 1.0
                low = np.empty_like(vec)
                for ch in range(3):
                    low[..., ch] = vrmeshy._box_blur(vec[..., ch], 3)
                outvec = low + (vec - low) * float(keep)
                outvec[..., 0] *= float(xy_compress)
                outvec[..., 1] *= float(xy_compress)
                length = np.sqrt(np.maximum(np.sum(outvec * outvec, axis=-1), 1e-8))
                outvec /= length[..., None]
                out = np.clip((outvec + 1.0) * 0.5, 0.0, 1.0)
                made[img] = vrmeshfix._replace_image(
                    img, np.concatenate([out, px[..., 3:]], axis=-1), "_normal_calmed"
                )
                count += 1
    vrmeshfix._swap_images(objs, made)
    return {"normal_images": count, "keep": keep, "xy_compress": xy_compress}


# ---------------------------------------------------------------------------
# Spaltstreifen: geometrisch rasterisierte UV-Maske, jetzt normalenunabhängig


def _cleft_uv_mask(objs, res=1024, x_max=3.65, zmin_frac=0.19, zmax_frac=0.985,
                   depth_normal_min=0.0):
    """Rasterize UV space used by inner cleft/fracture-lip triangles.

    v4 only marked front/back-facing lips.  The remaining review stripe sits on
    x-dominant fracture walls, so the improved mask is deliberately normal-
    independent; the tight spatial split selection still prevents unrelated
    outer-face islands from being included.
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
            if depth_normal_min > 0.0:
                n = rot @ np.array(poly.normal[:], dtype=np.float64)
                nlen = float(np.linalg.norm(n))
                if nlen <= 1e-9 or abs(n[1] / nlen) < depth_normal_min:
                    continue
            poly_count += 1
            uvs = np.array([uvlay.data[li].uv[:] for li in poly.loop_indices], dtype=np.float64)
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


def _mute_warm_cleft_strip(objs, sat_reduce=0.68, red_cool=0.018, blue_boost=0.006,
                           mask_res=1024):
    """Locally desaturate/cool the warm cleft-lip stripe in base colour.

    This remains a chroma correction, but runs after the global harmonization
    and covers the x-dominant fracture walls as well as the thin sunlit lips.
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
            img, np.concatenate([out, px[..., 3:]], axis=-1), "_cleft_neutral"
        )
    vrmeshfix._swap_images(objs, made)
    info["images"] = len(made)
    return info


# ---------------------------------------------------------------------------
# Build


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=0.0)

    vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=1.5)

    main = max((o for o in objs if o.type == "MESH"), key=lambda o: len(o.data.vertices), default=None)
    geometry_info = {}
    socket_objs = []
    socket_info = {"blocks": 0}
    if main is not None:
        geometry_info["fracture"] = _roughen_split_fracture(main, amplitude=0.52)
        socket_objs, socket_info = _make_socket_courses(main)
        objs = list(objs) + socket_objs

    # Texture chain: first replace the worm/pore signal, then harmonize the
    # palette, then neutralize the split chroma so the warm target colour cannot
    # reintroduce the stripe.  Normal micro-relief is filtered rather than only
    # turned down, preserving broad chipped form.
    regrain_info = regrain_stone_basecolor(objs)
    vrmeshfix.harmonize_basecolor(objs, "#DCCDB1", hue_keep=0.50, sat_mul=0.80)
    stripe_info = _mute_warm_cleft_strip(objs)
    normal_info = flatten_normal_microtexture(objs, keep=0.10, xy_compress=0.72)
    normal_nodes = vrmeshfix.set_normal_strength(objs, 0.16)

    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

    # Keep the orange QA scale figure visibly separated from the asset in any
    # future formal sheet render.  It remains a renderer marker, never geometry.
    scene = bpy.context.scene
    scene["vr_review_figure"] = (7.0, 12.2, 0.0)
    # Base/socket close-up slightly lower and from the rear-left, matching the
    # previous criticised tangential contact view but showing the new bearing.
    scene["vr_closeup_base"] = (0.0, 0.0, 7.25, 205.0, 18.0, 39.0)

    print("VR_GEOMETRY_REPAIR", geometry_info, flush=True)
    print("VR_SOCKET", socket_info, flush=True)
    print("VR_STONE_REGRAIN", regrain_info, flush=True)
    print("VR_CLEFT_STRIPE", stripe_info, flush=True)
    print("VR_NORMAL_REPAIR", {**normal_info, "nodes": normal_nodes}, flush=True)

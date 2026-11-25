"""One-off patcher for the r5 build iteration; kept for diagnostics."""
from pathlib import Path

p = Path(r"C:/Users/Mark Waldeis/Desktop/Violet Reach/assets/monuments/monument_split_disc_a/build.py")
s = p.read_text(encoding="utf-8")


def replace_between(text, start, end, new):
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + new + text[j:]


new_fracture = '''def _hash01(values):
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
    bandcoord = vz / 1.72 + 0.18 * np.sin(vy * 0.71 + side * 0.43) + side * 0.117
    band = np.floor(bandcoord)
    frac = bandcoord - band
    hcur = _hash01(band * 17.173 + side * 31.31)
    hprev = _hash01((band - 1.0) * 17.173 + side * 31.31)
    blend_width = 0.17
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


'''

s = replace_between(
    s,
    "def _roughen_split_fracture",
    "# ---------------------------------------------------------------------------\n# Auflager/Nut:",
    new_fracture + "# ---------------------------------------------------------------------------\n# Auflager/Nut:",
)

new_socket = '''def _projected_uvs_for_prism(me, base_uv=(0.080, 0.055), scale=0.006, seed=0):
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
        (x, yo, z0 + h * 0.43),
        (x, yo - ysign * halfwidth * 0.16, z_top),
        (x, yi + ysign * halfwidth * 0.19, z_top + 0.035),
        (x, yi, z0 + h * 0.60),
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
        ztop = 6.72 + (0.40 + 0.055 * math.sin(x * 1.17 + seed * 0.73)) * rise
        width_factor = 0.72 + 0.28 * math.sin(math.pi * t)
        halfwidth = 0.79 * width_factor
        ycentre = float(ysign) * (4.30 + 0.035 * math.sin(x * 0.73 + seed))
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
    ranges = ((-8.65, -0.42), (0.42, 8.65))
    for half, (xa, xb) in enumerate(ranges):
        for ysign in (-1, 1):
            rim = _make_socket_rim(
                f"socket_lip_{half}_{'front' if ysign > 0 else 'back'}",
                xa, xb, ysign, material, seed,
            )
            made.append(rim)
            seed += 1
    return made, {"rims": len(made), "triangles_est": len(made) * 192}


'''

s = replace_between(
    s,
    "def _projected_uvs_for_prism",
    "# ---------------------------------------------------------------------------\n# Texture repair:",
    new_socket + "# ---------------------------------------------------------------------------\n# Texture repair:",
)

# Strengthen the regrain algorithm with targeted replacements.
s = s.replace("low[..., ch] = vrmeshy._box_blur(rgb[..., ch], 3)", "low[..., ch] = vrmeshy._box_blur(rgb[..., ch], 7)", 1)
s = s.replace("keep_lum = np.where(high_lum < 0.0, 0.13, 0.25).astype(np.float32)", "keep_lum = np.where(high_lum < 0.0, 0.035, 0.105).astype(np.float32)", 1)
s = s.replace("filtered = low + high_lum_part + chroma * 0.11", "filtered = low + high_lum_part + chroma * 0.045", 1)
s = s.replace("pit_w = np.clip((pit - 0.014) / 0.055, 0.0, 1.0) * 0.88", "pit_w = np.clip((pit - 0.010) / 0.040, 0.0, 1.0) * 0.94", 1)
old_grain = "mod = 1.0 + grain * spatial * 0.020\n        out = np.clip(filtered * mod[..., None], 0.0, 1.0)"
new_grain = """signed_grain = np.where(grain < 0.0, grain * 0.52, grain * 0.82)
        mod = 1.0 + signed_grain * spatial * 0.015
        out0 = np.clip(filtered * mod[..., None], 0.0, 1.0)
        # A second black-top-hat pass runs after the replacement grain so the
        # grain itself cannot recreate circular black pore noise.
        lum0 = out0[..., 0] * 0.2126 + out0[..., 1] * 0.7152 + out0[..., 2] * 0.0722
        support0 = vrmeshy._box_blur(lum0, 5)
        pit0 = support0 - lum0
        pit0_w = np.clip((pit0 - 0.012) / 0.045, 0.0, 1.0) * 0.72
        metrics[\"pit_pixels\"] += int(np.count_nonzero(pit0_w > 0.35))
        out = np.clip(out0 * (1.0 - pit0_w[..., None]) + filtered * pit0_w[..., None], 0.0, 1.0)"""
if old_grain not in s:
    raise SystemExit("grain replacement target missing")
s = s.replace(old_grain, new_grain, 1)

s = s.replace("def _mute_warm_cleft_strip(objs, sat_reduce=0.58, red_cool=0.034, blue_boost=0.016,", "def _mute_warm_cleft_strip(objs, sat_reduce=0.55, red_cool=0.012, blue_boost=0.004,", 1)
s = s.replace("        geometry_info[\"taubin\"] = _taubin_calm_stone_surface(main)\n        geometry_info[\"embed\"] = _embed_disc_lower_edges(main)\n        geometry_info[\"fracture\"] = _roughen_split_fracture(main)", "        geometry_info[\"fracture\"] = _roughen_split_fracture(main, amplitude=0.52)", 1)
s = s.replace("flatten_normal_microtexture(objs, keep=0.18, xy_compress=0.84)", "flatten_normal_microtexture(objs, keep=0.10, xy_compress=0.72)", 1)
s = s.replace("vrmeshfix.set_normal_strength(objs, 0.22)", "vrmeshfix.set_normal_strength(objs, 0.16)", 1)
s = s.replace("scene[\"vr_review_figure\"] = (18.6, 8.8, 0.0)", "scene[\"vr_review_figure\"] = (7.0, 12.2, 0.0)", 1)

p.write_text(s, encoding="utf-8", newline="\n")
print("patched build.py", len(s))

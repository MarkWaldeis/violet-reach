"""Monumental 40 m Split Island Monument built procedurally in Blender (R13 True 3D Ashlar Blocks).

Units are metres, origin at ground centre, Z up.
Matches gate_white_a dressed limestone craftsmanship:
- Continuous 4-tier circular mortar core (-2.0 m burial skirt) wrapped in staggered 3D curved
  dressed limestone ashlar blocks with 0.05 m physical mortar gaps and bevelled coping treads
- Crisp bevelled masonry saddle cradle seated on top plinth tier
- Recessed silty-lime mortar half-disc cores framed by course-aligned rectilinear cleft lips
- Real 3D dressed & chamfered running-bond limestone ashlar blocks proud of the mortar bed
  across front/back disc faces (all 15 courses incl. row 0 & row 14) + 28 radial rim voussoirs
- Jittered, triangulated, smooth-shaded rock strata fracture benches inside the interior cleft
"""
import math
import random

import bmesh
import bpy

import vrlib
import vrmat


COURSE_H = 2.15
Z_START = 7.80
N_COURSES = 15
DISC_ZC = 23.60
DISC_R = 16.45
Z_TOP_CLAMP = DISC_ZC + (DISC_R - 0.55) * math.sin(math.radians(85.4))
MORTAR_GAP = 0.055
Y_CORE = 3.04
Y_ASHLAR = 3.17


def _cleft_x_course(side, row):
    """Discrete course-aligned rectilinear inner cleft offset (never cuts mid-block)."""
    z_mid = Z_START + (row + 0.5) * COURSE_H
    ht = max(0.0, min(1.0, (z_mid - 7.5) / 32.5))
    rng = random.Random(12000 + int(row) * 37 + (7 if side > 0 else 19))
    base = 0.82 + 0.58 * (ht ** 1.05) + rng.uniform(-0.24, 0.28)
    return max(0.60, base)


def _clip_x_outer(z):
    """Outer circular arc X-half-width tucking cleanly behind the radial rim voussoirs."""
    dz = z - DISC_ZC
    r2 = (DISC_R - 0.16) ** 2 - dz * dz
    if r2 <= 0.04:
        return 0.0
    return math.sqrt(r2)


def _block_material_idx(seed_key):
    """Deterministically pick 1 of 12 dressed limestone bed shades."""
    rng = random.Random(seed_key)
    return rng.randrange(12)


def _add_trapezoid_block(bm, x0_bot, x1_bot, x0_top, x1_top, y0, y1, z0, z1, mat_idx, rng):
    """Add a quarry-varied trapezoidal ashlar block that fits cleanly against the curved disc rim."""
    if min(x1_bot - x0_bot, x1_top - x0_top) < 0.12 or z1 - z0 < 0.25:
        return
    py = rng.uniform(-0.022, 0.024)
    p0 = y0 - (py if y0 < 0 else 0.0)
    p1 = y1 + (py if y1 > 0 else 0.0)
    verts = [
        bm.verts.new((x0_bot, p0, z0)),
        bm.verts.new((x1_bot, p0, z0)),
        bm.verts.new((x1_bot, p1, z0)),
        bm.verts.new((x0_bot, p1, z0)),
        bm.verts.new((x0_top, p0, z1)),
        bm.verts.new((x1_top, p0, z1)),
        bm.verts.new((x1_top, p1, z1)),
        bm.verts.new((x0_top, p1, z1)),
    ]
    faces_idx = [
        (3, 2, 1, 0),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    for fi in faces_idx:
        f = bm.faces.new([verts[k] for k in fi])
        f.material_index = mat_idx
        f.smooth = False


def _add_plinth_mortar_core(bm_core):
    """Build solid recessed 4-tier circular mortar core (rx - 0.08, ry - 0.08) down to z = -2.0."""
    segs = 48
    core_profile = [
        (-2.00, 16.50 - 0.08, 12.30 - 0.08),
        (1.96, 15.90 - 0.08, 11.75 - 0.08),
        (1.96, 14.35 - 0.08, 10.65 - 0.08),
        (3.96, 13.88 - 0.08, 10.22 - 0.08),
        (3.96, 12.35 - 0.08, 9.15 - 0.08),
        (5.96, 11.88 - 0.08, 8.72 - 0.08),
        (5.96, 10.35 - 0.08, 7.65 - 0.08),
        (7.76, 9.88 - 0.08, 7.25 - 0.08),
    ]
    rings = []
    for zz, rx, ry in core_profile:
        ring = []
        for s in range(segs):
            a = 2.0 * math.pi * s / segs
            ring.append(bm_core.verts.new((math.cos(a) * rx, math.sin(a) * ry, zz)))
        rings.append(ring)

    for ri in range(len(rings) - 1):
        r0, r1 = rings[ri], rings[ri + 1]
        mat_idx = 13 if core_profile[ri + 1][0] <= 4.0 else 12
        for s in range(segs):
            sn = (s + 1) % segs
            f = bm_core.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
            f.material_index = mat_idx
            f.smooth = False

    f_top = bm_core.faces.new(rings[-1])
    f_top.material_index = 12
    f_top.smooth = False
    f_bot = bm_core.faces.new(list(reversed(rings[0])))
    f_bot.material_index = 13
    f_bot.smooth = False


def _add_plinth_curved_ashlar_and_cradle(bm_stone):
    """Build staggered 3D curved dressed limestone ashlar blocks on all 4 plinth tiers + cradle."""
    # (n_blocks, stagger_frac, z_bot, z_sh, z_top, rx_bot, ry_bot, rx_sh, ry_sh, rx_top, ry_top, rx_in, ry_in)
    tiers = [
        (36, 0.0, -2.00, 1.855, 1.975, 16.50, 12.30, 16.05, 11.90, 15.90, 11.75, 14.05, 10.35),
        (32, 0.5, 2.025, 3.855, 3.975, 14.35, 10.65, 14.02, 10.35, 13.88, 10.22, 12.05, 8.85),
        (28, 0.0, 4.025, 5.855, 5.975, 12.35, 9.15, 12.02, 8.85, 11.88, 8.72, 10.05, 7.35),
        (24, 0.5, 6.025, 7.680, 7.800, 10.35, 7.65, 10.02, 7.38, 9.88, 7.25, 6.20, 4.40),
    ]
    n_arc = 2  # 3 angular slices per curved block -> smooth circular curvature

    for ti, (n_blk, stag, z_bot, z_sh, z_top, rxb, ryb, rxs, rys, rxt, ryt, rxi, ryi) in enumerate(tiers):
        step = 2.0 * math.pi / n_blk
        offset = stag * step
        for bi in range(n_blk):
            a0_raw = offset + bi * step
            a1_raw = offset + (bi + 1) * step
            speed0 = max(1.0, math.hypot(rxs * math.sin(a0_raw), rys * math.cos(a0_raw)))
            speed1 = max(1.0, math.hypot(rxs * math.sin(a1_raw), rys * math.cos(a1_raw)))
            a0 = a0_raw + 0.025 / speed0
            a1 = a1_raw - 0.025 / speed1
            if a1 <= a0 + 0.005:
                continue

            rng = random.Random(90000 + ti * 200 + bi)
            mat_idx = _block_material_idx(91000 + ti * 200 + bi)
            dr = rng.uniform(-0.015, 0.018)

            # 5-point cross section: outer_bot, outer_shoulder, outer_top_coping, inner_top, inner_bot
            prof = [
                (rxb + dr, ryb + dr, z_bot),
                (rxs + dr, rys + dr, z_sh),
                (rxt + dr, ryt + dr, z_top),
                (rxi, ryi, z_top),
                (rxi, ryi, z_bot),
            ]
            slices = []
            for si in range(n_arc + 1):
                aa = a0 + (a1 - a0) * (si / n_arc)
                ca, sa = math.cos(aa), math.sin(aa)
                slices.append([bm_stone.verts.new((ca * rx, sa * ry, zz)) for rx, ry, zz in prof])

            for si in range(n_arc):
                s0, s1 = slices[si], slices[si + 1]
                for pi in range(5):
                    pn = (pi + 1) % 5
                    f = bm_stone.faces.new((s0[pi], s1[pi], s1[pn], s0[pn]))
                    f.material_index = mat_idx
                    # Smooth curved risers/coping across arc chords; flat treads/bottom stay crisp
                    f.smooth = pi in (0, 1, 3)

            f_start = bm_stone.faces.new(list(reversed(slices[0])))
            f_start.material_index = mat_idx
            f_start.smooth = False
            f_end = bm_stone.faces.new(slices[-1])
            f_end.material_index = mat_idx
            f_end.smooth = False

    # Masonry saddle cradle seated cleanly on Tier 3
    for y_sign in (-1.0, 1.0):
        levels = [
            (7.78, 8.5, 3.12, 4.95),
            (8.62, 7.8, 3.16, 4.55),
            (8.64, 7.6, 3.18, 4.25),
            (9.48, 6.7, 3.20, 3.85),
        ]
        c_rings = []
        for zz, xh, yin, yout in levels:
            y0, y1 = y_sign * yin, y_sign * yout
            if y_sign < 0:
                y0, y1 = y1, y0
            c_rings.append([
                bm_stone.verts.new((-xh, y0, zz)),
                bm_stone.verts.new((xh, y0, zz)),
                bm_stone.verts.new((xh, y1, zz)),
                bm_stone.verts.new((-xh, y1, zz)),
            ])
        for ri in range(len(c_rings) - 1):
            r0, r1 = c_rings[ri], c_rings[ri + 1]
            for j in range(4):
                jn = (j + 1) % 4
                f = bm_stone.faces.new((r0[j], r0[jn], r1[jn], r1[j]))
                f.material_index = (ri + j) % 6
                f.smooth = False
        f_ct = bm_stone.faces.new(c_rings[-1])
        f_ct.material_index = 2
        f_ct.smooth = False


def _fracture_wall_x(side, y, z):
    """Course-aligned stepped limestone fracture wall with broad multi-scale rock strata benches."""
    row = max(0, min(N_COURSES - 1, int((z - Z_START) / COURSE_H)))
    z_in_row = (z - (Z_START + row * COURSE_H)) / COURSE_H
    x_c = _cleft_x_course(side, row)
    if row > 0 and z_in_row < 0.08:
        x_prev = _cleft_x_course(side, row - 1)
        t = z_in_row / 0.08
        t = t * t * (3.0 - 2.0 * t)
        lip = x_prev * (1.0 - t) + x_c * t
    else:
        lip = x_c

    y_norm = min(1.0, abs(y) / Y_ASHLAR)
    interior_env = max(0.0, 1.0 - (y_norm ** 2.6))

    # Broad domain-warped geological bedding strata benches (~4.5 m vertical ledges)
    warp = (
        0.42 * math.sin(y * 0.48 + side * 1.1)
        + 0.28 * math.cos(z * 0.14 - y * 0.32 + side * 0.6)
    )
    u = (z - Z_START) * 0.22 + y * 0.07 * side + warp
    u_i = math.floor(u)
    u_f = u - u_i
    if u_f < 0.22:
        bench = u_f / 0.22
    else:
        bench = 1.0 - 0.35 * ((u_f - 0.22) / 0.78)
    stratum_amp = 0.45 + 0.55 * abs(math.sin(u_i * 2.17 + side * 1.73))

    # Broad cleaved macro-planes + sparse domain-warped secondary fracture chips
    p1 = abs(math.sin(z * 0.16 + y * 0.26 + side * 0.9))
    p2 = 0.5 + 0.5 * math.cos(z * 0.09 - y * 0.38 + side * 2.1)
    macro = 0.65 * (p1 ** 1.4) + 0.35 * p2
    spall = abs(math.sin(z * 0.47 - y * 0.53 + warp * 1.6 + side * 0.5)) ** 1.6

    relief = 0.58 * bench * stratum_amp + 0.42 * macro + 0.20 * spall
    return side * (lip + 0.06 + interior_env * relief)


def _add_split_disc_core_and_cleft(bm_core, side):
    """Build recessed silty-mortar half-disc core + jittered, triangulated rock-strata cleft wall."""
    nz = N_COURSES * 6
    th_lo = math.radians(-73.0)
    th_hi = math.radians(85.2)
    ny_cleft = 15
    y_cleft = [-Y_ASHLAR + (2.0 * Y_ASHLAR) * (k / (ny_cleft - 1)) for k in range(ny_cleft)]

    slices = []
    for iz in range(nz + 1):
        z_raw = Z_START + (N_COURSES * COURSE_H) * (iz / nz)
        dz = max(-DISC_R + 0.6, min(DISC_R - 0.2, z_raw - DISC_ZC))
        th = math.asin(dz / DISC_R)
        th = max(th_lo, min(th_hi, th))
        z_arc = DISC_ZC + (DISC_R - 0.14) * math.sin(th)
        dx_arc = (DISC_R - 0.22) * math.cos(th)
        x_rim_outer = side * dx_arc
        # Keep top mortar bevel cleanly inside the top voussoir shoulder
        bevel_inset = min(0.52, max(0.14, dx_arc - 1.15)) if z_arc > 38.5 else 0.52
        x_rim_bevel = side * max(1.12 if z_arc > 38.5 else 0.85, dx_arc - bevel_inset)

        ring = []
        for k, yv in enumerate(y_cleft):
            is_lip = k == 0 or k == ny_cleft - 1
            is_end = iz == 0 or iz == nz
            if is_lip or is_end:
                dy, dz_j = 0.0, 0.0
            else:
                rng_v = random.Random(50000 + (1 if side > 0 else 2) * 10000 + iz * 100 + k)
                z_amp = 0.10 if iz in (1, nz - 1) else 0.14
                dy = rng_v.uniform(-0.14, 0.14)
                dz_j = rng_v.uniform(-z_amp, z_amp)

            yy = -Y_CORE if k == 0 else (Y_CORE if k == ny_cleft - 1 else max(-Y_CORE + 0.15, min(Y_CORE - 0.15, yv + dy)))
            zz = z_arc + dz_j
            xf = _fracture_wall_x(side, yy, zz)
            if side > 0:
                xf = min(xf, x_rim_bevel - 0.22)
                if z_arc > 38.95:
                    xf = max(1.06, min(xf, dx_arc - 0.16))
            else:
                xf = max(xf, x_rim_bevel + 0.22)
                if z_arc > 38.95:
                    xf = min(-1.06, max(xf, -dx_arc + 0.16))
            ring.append(bm_core.verts.new((xf, yy, zz)))

        for px, py, pz in (
            (x_rim_bevel, Y_CORE, z_arc),
            (x_rim_outer, 2.48, z_arc),
            (x_rim_outer, -2.48, z_arc),
            (x_rim_bevel, -Y_CORE, z_arc),
        ):
            ring.append(bm_core.verts.new((px, py, pz)))
        slices.append(ring)

    cleft_faces = []
    nring = len(slices[0])
    for iz in range(nz):
        r0, r1 = slices[iz], slices[iz + 1]
        for j in range(nring):
            jn = (j + 1) % nring
            f = bm_core.faces.new((r0[j], r0[jn], r1[jn], r1[j]) if side > 0 else (r0[jn], r0[j], r1[j], r1[jn]))
            if j < ny_cleft - 1:
                f.material_index = 14  # cleft weathered chalk interior
                f.smooth = True
                cleft_faces.append(f)
            else:
                f.material_index = 12  # silty recessed mortar core
                f.smooth = False

    if cleft_faces:
        res = bmesh.ops.triangulate(bm_core, faces=cleft_faces)
        for tf in res["faces"]:
            tf.material_index = 14
            tf.smooth = True

    def _cap(sl, flip):
        f = bm_core.faces.new(list(reversed(sl)) if flip else list(sl))
        f.material_index = 12
        f.smooth = False
        bmesh.ops.triangulate(bm_core, faces=[f])

    _cap(slices[0], flip=(side > 0))
    _cap(slices[-1], flip=(side < 0))


def _add_3d_ashlar_blocks(bm_stone, side):
    """Build real proud 3D dressed limestone ashlar blocks on front/back faces + 28 rim voussoirs."""
    block_w = 3.45
    gap = MORTAR_GAP

    for row in range(N_COURSES):
        z0 = Z_START + row * COURSE_H + gap * 0.5
        z1 = min(Z_START + (row + 1) * COURSE_H - gap * 0.5, Z_TOP_CLAMP)
        if z1 - z0 < 0.25:
            continue
        x_in = _cleft_x_course(side, row)
        xo0 = _clip_x_outer(z0)
        xo1 = _clip_x_outer(z1)
        xo_min = min(xo0, xo1)
        xo_max = max(xo0, xo1)
        if xo_min <= x_in + 0.14:
            continue

        # Running bond stagger on alternate courses without overlapping/missing perimeter blocks
        stagger = 0.5 * block_w if (row % 2 == 1) else 0.0
        interior_joints = []
        g = x_in + (block_w - stagger if stagger > 0.0 else block_w)
        while g < xo_min - (0.14 + gap):
            interior_joints.append(g)
            g += block_w

        prev_x = interior_joints[-1] if interior_joints else x_in
        if xo_min - prev_x > 2.2 and xo_max - prev_x > 4.5:
            j_extra = xo_min - 0.21
            if j_extra - prev_x >= 0.75:
                interior_joints.append(j_extra)

        edges = [x_in] + interior_joints
        for col, x_left in enumerate(edges):
            bx0 = x_left + gap * 0.5
            if col < len(edges) - 1:
                bx1_b = edges[col + 1] - gap * 0.5
                bx1_t = bx1_b
            else:
                bx1_b = xo0
                bx1_t = xo1

            if min(bx1_b - bx0, bx1_t - bx0) < 0.12:
                continue

            if side > 0:
                w0b, w1b, w0t, w1t = bx0, bx1_b, bx0, bx1_t
            else:
                w0b, w1b, w0t, w1t = -bx1_b, -bx0, -bx1_t, -bx0

            for y_side in (-1, 1):
                rng = random.Random(int(side > 0) * 10000 + (y_side > 0) * 5000 + row * 100 + col)
                mat_idx = _block_material_idx(rng.randint(0, 999999))
                if y_side > 0:
                    _add_trapezoid_block(bm_stone, w0b, w1b, w0t, w1t, Y_CORE - 0.04, Y_ASHLAR, z0, z1, mat_idx, rng)
                else:
                    _add_trapezoid_block(bm_stone, w0b, w1b, w0t, w1t, -Y_ASHLAR, -(Y_CORE - 0.04), z0, z1, mat_idx, rng)

    # 28 radial arch voussoir stone caps framing outer perimeter + both cleft shoulders
    n_voussoirs = 28
    th_lo = math.radians(-73.5)
    th_hi = math.radians(86.2)
    r_in = DISC_R - 1.05
    r_out = DISC_R + 0.06
    yv = Y_ASHLAR - 0.03
    for iv in range(n_voussoirs):
        t0 = th_lo + (th_hi - th_lo) * (iv / n_voussoirs) + (0.0 if iv == 0 else 0.0018)
        t1 = th_lo + (th_hi - th_lo) * ((iv + 1) / n_voussoirs) - (0.0 if iv == n_voussoirs - 1 else 0.0018)
        mat_idx = _block_material_idx(7000 + int(side > 0) * 100 + iv)
        pts = [
            (side * r_in * math.cos(t0), DISC_ZC + r_in * math.sin(t0)),
            (side * r_out * math.cos(t0), DISC_ZC + r_out * math.sin(t0)),
            (side * r_out * math.cos(t1), DISC_ZC + r_out * math.sin(t1)),
            (side * r_in * math.cos(t1), DISC_ZC + r_in * math.sin(t1)),
        ]
        ring0 = [bm_stone.verts.new((px, -yv, pz)) for px, pz in pts]
        ring1 = [bm_stone.verts.new((px, yv, pz)) for px, pz in pts]
        if side < 0:
            ring0.reverse()
            ring1.reverse()
        for k in range(4):
            kn = (k + 1) % 4
            f = bm_stone.faces.new((ring0[k], ring0[kn], ring1[kn], ring1[k]))
            f.material_index = mat_idx
            f.smooth = False
        f_front = bm_stone.faces.new(list(reversed(ring0)))
        f_front.material_index = mat_idx
        f_front.smooth = False
        f_back = bm_stone.faces.new(ring1)
        f_back.material_index = mat_idx
        f_back.smooth = False


def _add_stone_weathering(mat, *, damp_boost=0.0):
    """Apply subtle rain wash streaks, micro limestone pores, and waterline damp moss patina."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    geom = nodes.new("ShaderNodeNewGeometry")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geom.outputs["Position"], xyz.inputs[0])

    def _cur_col():
        return bsdf.inputs["Base Color"].links[0].from_socket

    # 3D isotropic Voronoi pores & high-freq grit
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 3.6
    links.new(geom.outputs["Position"], vor.inputs["Vector"])
    pit = nodes.new("ShaderNodeMapRange")
    pit.inputs["From Min"].default_value = 0.0
    pit.inputs["From Max"].default_value = 0.25
    pit.inputs["To Min"].default_value = 0.72
    pit.inputs["To Max"].default_value = 1.0
    links.new(vor.outputs["Distance"], pit.inputs["Value"])

    p_mix = nodes.new("ShaderNodeMixRGB")
    p_mix.blend_type = "MULTIPLY"
    p_mix.inputs["Fac"].default_value = 0.32
    links.new(_cur_col(), p_mix.inputs["Color1"])
    links.new(pit.outputs["Result"], p_mix.inputs["Color2"])
    links.new(p_mix.outputs["Color"], bsdf.inputs["Base Color"])

    # Vertical rain-wash streaks
    r_vec = nodes.new("ShaderNodeVectorMath")
    r_vec.operation = "MULTIPLY"
    r_vec.inputs[1].default_value = (1.3, 1.3, 0.14)
    links.new(geom.outputs["Position"], r_vec.inputs[0])
    r_noise = nodes.new("ShaderNodeTexNoise")
    r_noise.inputs["Scale"].default_value = 0.45
    r_noise.inputs["Detail"].default_value = 3.0
    links.new(r_vec.outputs["Vector"], r_noise.inputs["Vector"])
    r_ramp = nodes.new("ShaderNodeMapRange")
    r_ramp.inputs["From Min"].default_value = 0.26
    r_ramp.inputs["From Max"].default_value = 0.76
    r_ramp.inputs["To Min"].default_value = 0.74
    r_ramp.inputs["To Max"].default_value = 1.0
    links.new(r_noise.outputs["Fac"], r_ramp.inputs["Value"])

    r_mix = nodes.new("ShaderNodeMixRGB")
    r_mix.blend_type = "MULTIPLY"
    r_mix.inputs["Fac"].default_value = 0.46
    links.new(_cur_col(), r_mix.inputs["Color1"])
    links.new(r_ramp.outputs["Result"], r_mix.inputs["Color2"])
    links.new(r_mix.outputs["Color"], bsdf.inputs["Base Color"])

    # Waterline mossy damp band across plinth tiers 0-1 (z = 0..4.9 m)
    grit = nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 5.8
    grit.inputs["Detail"].default_value = 4.0
    links.new(geom.outputs["Position"], grit.inputs["Vector"])

    w_add = nodes.new("ShaderNodeMath")
    w_add.operation = "ADD"
    links.new(xyz.outputs["Z"], w_add.inputs[0])
    w_n = nodes.new("ShaderNodeMath")
    w_n.operation = "MULTIPLY"
    w_n.inputs[1].default_value = 1.3
    links.new(grit.outputs["Fac"], w_n.inputs[0])
    links.new(w_n.outputs[0], w_add.inputs[1])
    moss = nodes.new("ShaderNodeMapRange")
    moss.inputs["From Min"].default_value = 0.4
    moss.inputs["From Max"].default_value = 4.9 + damp_boost
    moss.inputs["To Min"].default_value = 0.85 + damp_boost * 0.12
    moss.inputs["To Max"].default_value = 0.0
    links.new(w_add.outputs[0], moss.inputs["Value"])

    m_mix = nodes.new("ShaderNodeMixRGB")
    m_mix.blend_type = "MULTIPLY"
    links.new(moss.outputs["Result"], m_mix.inputs["Fac"])
    links.new(_cur_col(), m_mix.inputs["Color1"])
    m_mix.inputs["Color2"].default_value = (0.33, 0.42, 0.27, 1.0)
    links.new(m_mix.outputs["Color"], bsdf.inputs["Base Color"])

    # Crisp limestone grit bump
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.36
    bump.inputs["Distance"].default_value = 0.035
    if bsdf.inputs["Normal"].is_linked:
        links.new(bsdf.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
    links.new(grit.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _make_materials():
    """Create 12 dressed limestone bed shades + mortar + damp foot + isotropic pale cleft stone."""
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]

    mats = []
    for i in range(12):
        mat = vrmat.get("monument_white").copy()
        mat.name = f"SplitDisc_StoneBed_{i + 1:02d}"
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Specular IOR Level"].default_value = 0.23
        old_col = bsdf.inputs["Base Color"].links[0].from_socket
        tone = 0.60 + 0.038 * i
        warm = math.sin(1.93 * i)
        color = tuple(min(1.0, c * tone * s) for c, s in zip(cream, (1.0 + 0.08 * warm, 1.0, 1.0 - 0.14 * warm)))
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs[0].default_value = 0.72
        mix.inputs[2].default_value = (*color, 1.0)
        links.new(old_col, mix.inputs[1])
        links.new(mix.outputs[0], bsdf.inputs["Base Color"])
        _add_stone_weathering(mat)
        mats.append(mat)

    mortar = vrmat.get("monument_weathered").copy()
    mortar.name = "SplitDisc_SiltyMortar"
    ms = mortar.node_tree.nodes["Principled BSDF"]
    msrc = ms.inputs["Base Color"].links[0].from_socket
    mmix = mortar.node_tree.nodes.new("ShaderNodeMixRGB")
    mmix.blend_type = "MULTIPLY"
    mmix.inputs[0].default_value = 1.0
    mmix.inputs[2].default_value = (0.48, 0.46, 0.40, 1.0)
    mortar.node_tree.links.new(msrc, mmix.inputs[1])
    mortar.node_tree.links.new(mmix.outputs[0], ms.inputs["Base Color"])
    _add_stone_weathering(mortar)
    mats.append(mortar)

    foot = vrmat.get("monument_weathered").copy()
    foot.name = "SplitDisc_DampPlinth"
    _add_stone_weathering(foot, damp_boost=1.2)
    mats.append(foot)

    # Isotropic pale weathered limestone cleft (zero horizontal streaks, blends harmonically)
    cleft = vrmat.get("monument_weathered").copy()
    cleft.name = "SplitDisc_IsotropicCleft"
    cn, cl = cleft.node_tree.nodes, cleft.node_tree.links
    cbsdf = cn["Principled BSDF"]
    cbsdf.inputs["Specular IOR Level"].default_value = 0.18
    cgeom = cn.new("ShaderNodeNewGeometry")
    csrc = cbsdf.inputs["Base Color"].links[0].from_socket
    ctint = cn.new("ShaderNodeMixRGB")
    ctint.inputs["Fac"].default_value = 0.48
    cl.new(csrc, ctint.inputs["Color1"])
    ctint.inputs["Color2"].default_value = (0.62, 0.58, 0.52, 1.0)
    cl.new(ctint.outputs["Color"], cbsdf.inputs["Base Color"])

    cvor = cn.new("ShaderNodeTexVoronoi")
    cvor.feature = "DISTANCE_TO_EDGE"
    cvor.inputs["Scale"].default_value = 2.4
    cl.new(cgeom.outputs["Position"], cvor.inputs["Vector"])
    cn_noise = cn.new("ShaderNodeTexNoise")
    cn_noise.inputs["Scale"].default_value = 4.2
    cn_noise.inputs["Detail"].default_value = 5.0
    cl.new(cgeom.outputs["Position"], cn_noise.inputs["Vector"])

    cmult = cn.new("ShaderNodeMath")
    cmult.operation = "MULTIPLY"
    cl.new(cvor.outputs["Distance"], cmult.inputs[0])
    cl.new(cn_noise.outputs["Fac"], cmult.inputs[1])
    cbump = cn.new("ShaderNodeBump")
    cbump.inputs["Strength"].default_value = 0.65
    cbump.inputs["Distance"].default_value = 0.08
    cl.new(cmult.outputs[0], cbump.inputs["Height"])
    cl.new(cbump.outputs["Normal"], cbsdf.inputs["Normal"])
    mats.append(cleft)
    return mats


def build():
    mats = _make_materials()

    # 1. Dressed masonry (plinth curved blocks, cradle, face ashlars, rim voussoirs) + StoneChamfer
    bm_stone = bmesh.new()
    _add_plinth_curved_ashlar_and_cradle(bm_stone)
    _add_3d_ashlar_blocks(bm_stone, -1.0)
    _add_3d_ashlar_blocks(bm_stone, 1.0)
    bmesh.ops.recalc_face_normals(bm_stone, faces=list(bm_stone.faces))

    mesh = bpy.data.meshes.new("monument_split_disc_a_mesh")
    for mat in mats:
        mesh.materials.append(mat)
    bm_stone.to_mesh(mesh)
    bm_stone.free()

    obj = bpy.data.objects.new("monument_split_disc_a", mesh)
    bev = obj.modifiers.new(name="StoneChamfer", type="BEVEL")
    bev.width = 0.055
    bev.segments = 1
    bev.use_clamp_overlap = True
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(24.0)

    vrlib.link_to_source(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bev.name)

    # 2. Recessed mortar cores + triangulated smooth-shaded cleft walls (preserve sharp strata ledges)
    bm_core = bmesh.new()
    _add_plinth_mortar_core(bm_core)
    _add_split_disc_core_and_cleft(bm_core, -1.0)
    _add_split_disc_core_and_cleft(bm_core, 1.0)
    bmesh.ops.recalc_face_normals(bm_core, faces=list(bm_core.faces))

    mesh_core = bpy.data.meshes.new("monument_split_disc_a_core_tmp")
    for mat in mats:
        mesh_core.materials.append(mat)
    bm_core.to_mesh(mesh_core)
    bm_core.free()

    bm_all = bmesh.new()
    bm_all.from_mesh(obj.data)
    bm_all.from_mesh(mesh_core)
    bm_all.to_mesh(obj.data)
    bm_all.free()
    bpy.data.meshes.remove(mesh_core)

    es = obj.modifiers.new(name="SharpArris", type="EDGE_SPLIT")
    es.split_angle = math.radians(30.0)
    es.use_edge_angle = True
    bpy.ops.object.modifier_apply(modifier=es.name)

    scene = bpy.context.scene
    scene["vr_review_figure"] = (9.5, 11.8, 0.0)
    scene["vr_closeup_upper"] = (0.0, 0.25, 24.0, 64.0, 12.0, 27.0)
    scene["vr_closeup_base"] = (0.0, 0.0, 8.2, 208.0, 18.0, 28.0)

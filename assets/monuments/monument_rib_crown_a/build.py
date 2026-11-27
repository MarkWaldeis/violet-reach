"""Monumental >100 m Ribbed Crown Sanctuary built procedurally in Blender.

Units are metres, origin at ground centre, Z up.
Matches art/reference/ref_08_ribbed_crown.jpg:
- Solid stepped horseshoe limestone fortress dais + central altar platform (-5 m buried skirt)
- 8 towering scimitar limestone ribs bowing outward first then sweeping gracefully
  inward into a wide open crown bowl (never colliding at the summit), with crisp
  contrasting dark inner channels (monument_shadow / monument_weathered)
- Tall slender faceted central sanctuary monolith grounded solidly on the central altar
"""
import math

import bmesh
import bpy
from mathutils import Vector

import vrlib
import vrmat


def _add_ring_extrusion(bm, profile_fn, rings_z_mat, smooth=False):
    """Generic watertight prism/frustum builder from vertical rings of (x, y, z) tuples."""
    rings = [ [bm.verts.new(p) for p in profile_fn(z, *extra)] for z, *extra in rings_z_mat ]
    segs = len(rings[0])
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        mat_idx = rings_z_mat[i][-1] if len(rings_z_mat[i]) > 1 else 0
        for s in range(segs):
            sn = (s + 1) % segs
            f = bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
            f.material_index = mat_idx
            f.smooth = smooth
    f_bot = bm.faces.new(list(reversed(rings[0])))
    f_bot.material_index = rings_z_mat[0][-1] if len(rings_z_mat[0]) > 1 else 0
    f_bot.smooth = smooth
    f_top = bm.faces.new(rings[-1])
    f_top.material_index = rings_z_mat[-1][-1] if len(rings_z_mat[-1]) > 1 else 0
    f_top.smooth = smooth


def _add_fortress_plinth_and_dais(bm):
    """Build stepped horseshoe fortress podium + solid inner court terrace & central altar."""
    # 1. Outer stepped bastion terrace (covers full footprint down to -5.0 m burial skirt)
    segs = 48
    outer_tiers = [
        (-5.0, 2.8, 52.0, 46.0, 1),
        (2.6, 5.4, 46.5, 41.0, 1),
        (5.2, 7.6, 41.5, 36.5, 0),
    ]
    for zb, zt, rx, ry, midx in outer_tiers:
        def prof(z, r_x, r_y, _midx):
            return [(math.cos(2 * math.pi * s / segs) * r_x, math.sin(2 * math.pi * s / segs) * r_y, z) for s in range(segs)]
        _add_ring_extrusion(bm, prof, [(zb, rx * 1.03, ry * 1.03, midx), (zt - 0.18, rx, ry, midx), (zt, rx - 0.25, ry - 0.25, midx)])

    # 2. Raised horseshoe colonnade gallery rim (open toward -X/front? Wait: open toward +X / front-left for F3!)
    # Horseshoe spans -142°..+142°, leaving grand ceremonial stairway/portal gap around ±180° (-X or +X).
    # Note: in placements we orient entrance toward camera; keep opening at angle 180° (-X)!
    arc_segs = 32
    a0, a1 = math.radians(-140.0), math.radians(140.0)
    for zb, zt, rxo, ryo, rxi, ryi, midx in (
        (7.4, 10.6, 40.5, 35.5, 29.0, 25.0, 1),
        (10.5, 13.0, 38.8, 34.0, 30.2, 26.2, 0),
    ):
        bo, bi, to, ti = [], [], [], []
        for s in range(arc_segs + 1):
            t = s / arc_segs
            a = a0 + (a1 - a0) * t
            ca, sa = math.cos(a), math.sin(a)
            bo.append(bm.verts.new((ca * rxo * 1.02, sa * ryo * 1.02, zb)))
            bi.append(bm.verts.new((ca * rxi * 0.98, sa * ryi * 0.98, zb)))
            to.append(bm.verts.new((ca * rxo, sa * ryo, zt)))
            ti.append(bm.verts.new((ca * rxi, sa * ryi, zt)))
        for s in range(arc_segs):
            for fv in ((to[s], to[s+1], ti[s+1], ti[s]), (bi[s], bi[s+1], bo[s+1], bo[s]),
                       (bo[s], bo[s+1], to[s+1], to[s]), (ti[s], ti[s+1], bi[s+1], bi[s])):
                f = bm.faces.new(fv)
                f.material_index = midx
                f.smooth = False
        for fv in ((bi[0], bo[0], to[0], ti[0]), (ti[-1], to[-1], bo[-1], bi[-1])):
            f = bm.faces.new(fv)
            f.material_index = midx
            f.smooth = False

    # 3. Solid stepped central altar dais inside the court (z = 7.3..12.6 m) grounding the central spire
    for zb, zt, rx, ry, midx in (
        (7.3, 10.0, 14.5, 12.5, 1),
        (9.9, 12.6, 10.2, 8.8, 0),
    ):
        def altar_prof(z, r_x, r_y, _m):
            return [(math.cos(2 * math.pi * s / 24) * r_x, math.sin(2 * math.pi * s / 24) * r_y, z) for s in range(24)]
        _add_ring_extrusion(bm, altar_prof, [(zb, rx, ry, midx), (zt - 0.16, rx * 0.94, ry * 0.94, midx), (zt, rx * 0.90, ry * 0.90, midx)])


def _rib_cross_section(rad_d, tan_w, is_base=False):
    """Symmetric 10-point chamfered scimitar limestone blade with recessed dark inner spine."""
    hd = rad_d * 0.5
    hw = tan_w * 0.5
    if is_base:
        hd *= 1.18
        hw *= 1.24
    # Outer edge (-hd in radial U -> facing away from centre), Inner spine (+hd -> facing sanctuary)
    return [
        (-hd, -hw * 0.45),        # 0 outer chamfer back
        (-hd * 0.45, -hw),        # 1 side flank back
        (hd * 0.48, -hw * 0.86),  # 2 inner shoulder back
        (hd * 0.88, -hw * 0.40),  # 3 inner channel edge back (recessed dark spine)
        (hd * 0.70, 0.0),         # 4 inner groove center
        (hd * 0.88, hw * 0.40),   # 5 inner channel edge front
        (hd * 0.48, hw * 0.86),   # 6 inner shoulder front
        (-hd * 0.45, hw),         # 7 side flank front
        (-hd, hw * 0.45),         # 8 outer chamfer front
    ]


def _add_scimitar_rib(bm, base_pos, yaw, height, rad_d, tan_w, bow_out_m, lean_in_m, tip_slant):
    """Build one clean sweeping scimitar rib: bows outward first, curves cleanly inward without crossing."""
    rings_n = 24
    ca, sa = math.cos(yaw), math.sin(yaw)
    u_in = Vector((-ca, -sa, 0.0))  # Toward sanctuary center
    v_tan = Vector((-sa, ca, 0.0))

    rings = []
    for i in range(rings_n + 1):
        t = i / rings_n
        z = 6.0 + (height - 6.0) * t
        # Scimitar S-arch: starts smoothly vertical in the plinth (t < 0.12), bellies OUTWARD, then sweeps INWARD
        radial_shift = -bow_out_m * math.sin(min(1.0, t * 1.45) * math.pi) * (1.0 - t) * min(1.0, t * 4.5) + lean_in_m * (t ** 1.85)
        # Buttress foot collar then crisp continuous scimitar taper
        foot_boost = 1.18 if t < 0.08 else (1.08 if t < 0.16 else 1.0)
        # Subtle crisp masonry shadow notch at t=0.45 and t=0.72
        band_notch = 0.94 if (abs(t - 0.45) < 0.02 or abs(t - 0.74) < 0.02) else 1.0
        cur_d = max(1.1, rad_d * foot_boost * band_notch * (1.0 - 0.74 * (t ** 1.15)))
        cur_w = max(0.85, tan_w * foot_boost * band_notch * (1.0 - 0.70 * (t ** 1.05)))
        prof = _rib_cross_section(cur_d, cur_w, is_base=(i == 0))

        # Approximate radial slope to keep cross-section perpendicular to rib arch
        dt = 0.02
        t2 = min(1.0, t + dt)
        r2 = -bow_out_m * math.sin(min(1.0, t2 * 1.45) * math.pi) * (1.0 - t2) * min(1.0, t2 * 4.5) + lean_in_m * (t2 ** 1.85)
        dr = r2 - radial_shift
        dz = (height - 6.0) * dt
        pitch = math.atan2(dr, dz) * 0.45

        center = base_pos + u_in * radial_shift + Vector((0.0, 0.0, z))
        ring = []
        for lx, ly in prof:
            dz_tip = (lx * tip_slant) if t > 0.90 else 0.0
            rx = lx * math.cos(pitch)
            rz = -lx * math.sin(pitch) + dz_tip
            p = center + u_in * rx + v_tan * ly + Vector((0.0, 0.0, rz))
            ring.append(bm.verts.new(p))
        rings.append(ring)

    n_pts = len(rings[0])
    for i in range(rings_n):
        r0, r1 = rings[i], rings[i + 1]
        for j in range(n_pts):
            jn = (j + 1) % n_pts
            f = bm.faces.new((r0[j], r0[jn], r1[jn], r1[j]))
            # Edges j in (3, 4) form the recessed inner spine channel -> dark contrast accent!
            f.material_index = 2 if j in (3, 4) else (1 if j in (2, 5) else 0)
            f.smooth = False
    f_bot = bm.faces.new(list(reversed(rings[0])))
    f_bot.material_index = 0
    f_top = bm.faces.new(rings[-1])
    f_top.material_index = 0


def _add_central_sanctuary_spire(bm):
    """Build tall slender central split sanctuary spire grounded solidly on the z=12.6 altar."""
    for side, x_off, h, tilt in ((-1, -1.7, 94.0, 0.012), (1, 1.8, 106.0, -0.010)):
        rings_n = 16
        rings = []
        for i in range(rings_n + 1):
            t = i / rings_n
            z = 11.2 + (h - 11.2) * t
            sx = 1.9 * (1.0 - 0.72 * (t ** 1.05))
            sy = 4.6 * (1.0 - 0.75 * (t ** 1.05))
            if abs(t - 0.35) < 0.03 or abs(t - 0.68) < 0.03:
                sx *= 0.90
                sy *= 0.90
            cx = x_off + side * (0.6 * t) + tilt * z * 0.25
            pts = [
                (-sx, -sy * 0.55), (0.0, -sy), (sx, -sy * 0.55),
                (sx * 0.92, 0.0), (sx, sy * 0.55), (0.0, sy),
                (-sx, sy * 0.55), (-sx * 0.92, 0.0),
            ]
            ring = []
            for px, py in pts:
                dz = (py * 0.24 * side) if t > 0.88 else 0.0
                ring.append(bm.verts.new((cx + px, py, z + dz)))
            rings.append(ring)
        n_pts = len(rings[0])
        for i in range(rings_n):
            for j in range(n_pts):
                jn = (j + 1) % n_pts
                f = bm.faces.new((rings[i][j], rings[i][jn], rings[i + 1][jn], rings[i + 1][j]))
                f.material_index = 2 if (side < 0 and j in (2, 3)) or (side > 0 and j in (6, 7)) else 0
                f.smooth = False
        bm.faces.new(list(reversed(rings[0]))).material_index = 0
        bm.faces.new(rings[-1]).material_index = 0


def build():
    bm = bmesh.new()
    _add_fortress_plinth_and_dais(bm)

    # 8 wide crescent scimitar ribs: base ring at r = 34.5x29.5 m, bowing outward ~6-8 m then arching inward 14-21 m
    # Peak inward reach stays ~15-20 m clear of center -> open cathedral rib crown matching ref_08_ribbed_crown!
    rib_specs = [
        # (angle_deg, height_m, rad_depth, tan_width, bow_out, lean_in, tip_slant)
        (-130.0, 62.0, 8.2, 4.6, 5.2, 13.5, 0.22),
        (-96.0, 84.0, 10.6, 5.6, 7.0, 17.5, -0.18),
        (-60.0, 102.0, 12.2, 6.4, 8.2, 20.0, 0.25),
        (-24.0, 114.0, 13.0, 6.8, 8.8, 21.5, -0.20),
        (24.0, 110.0, 12.6, 6.6, 8.4, 21.0, 0.22),
        (60.0, 96.0, 11.6, 6.0, 7.6, 19.0, -0.24),
        (96.0, 78.0, 10.0, 5.4, 6.4, 16.5, 0.20),
        (130.0, 58.0, 7.8, 4.4, 4.8, 12.5, -0.18),
    ]
    rx_mid, ry_mid = 34.5, 29.8
    for ang_deg, h, rd, tw, bow, lean, slant in rib_specs:
        ang = math.radians(ang_deg)
        pos = Vector((math.cos(ang) * rx_mid, math.sin(ang) * ry_mid, 0.0))
        _add_scimitar_rib(bm, pos, ang, h, rd, tw, bow, lean, slant)

    _add_central_sanctuary_spire(bm)

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new("monument_rib_crown_a_mesh")
    bm.to_mesh(mesh)
    bm.free()

    mat_white = vrmat.get("monument_white").copy()
    mat_white.name = "RibCrown_WhiteLimestone"
    mat_weath = vrmat.get("monument_weathered").copy()
    mat_weath.name = "RibCrown_WeatheredLimestone"
    mat_shadow = vrmat.get("monument_weathered").copy()
    mat_shadow.name = "RibCrown_DarkRecess"
    # Darken recessed channel cleanly in node tree while preserving vrmat palette linkage
    bsdf = mat_shadow.node_tree.nodes.get("Principled BSDF")
    if bsdf and bsdf.inputs["Base Color"].is_linked:
        src = bsdf.inputs["Base Color"].links[0].from_socket
        mix = mat_shadow.node_tree.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.inputs["Color2"].default_value = (0.58, 0.56, 0.53, 1.0)
        mat_shadow.node_tree.links.new(src, mix.inputs["Color1"])
        mat_shadow.node_tree.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    mesh.materials.append(mat_white)
    mesh.materials.append(mat_weath)
    mesh.materials.append(mat_shadow)

    obj = bpy.data.objects.new("monument_rib_crown_a", mesh)
    bev = obj.modifiers.new(name="StoneChamfer", type="BEVEL")
    bev.width = 0.14
    bev.segments = 1
    bev.use_clamp_overlap = True
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(26.0)
    vrlib.link_to_source(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bev.name)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

"""Targeted repair helpers for Meshy smart-topology assets.

These functions are intentionally separate from vrmeshy.py: they implement the
corrective operations found in the first gate review (coherent UV hole caps,
jagged branch-tip caps, cavity plugs, texture de-weaving and local smoothing).
Everything is deterministic and works in object-local coordinates after
vrmeshy.normalize() has applied transforms.
"""
import math
import os
from collections import defaultdict

import bpy
import bmesh
import numpy as np
from mathutils import Vector

import vrmeshy


# ---------------------------------------------------------------------------
# Mesh/UV utilities


def _mesh_objects(objs):
    return [o for o in objs if o and o.type == "MESH"]


def _vert_uv_map(bm, uv_layer):
    """One representative UV per vertex, preferring UVs on larger faces."""
    out = {}
    if uv_layer is None:
        return out
    faces = sorted(bm.faces, key=lambda f: f.calc_area(), reverse=True)
    for f in faces:
        for lp in f.loops:
            out.setdefault(lp.vert, lp[uv_layer].uv.copy())
    return out


def boundary_loops(bm):
    """Return boundary loops as ordered BMVert lists.

    Smart-topology holes are small, simple loops, but branch intersections can
    make the walking order ambiguous.  At degree>2 vertices choose the edge
    with the straightest continuation; loops are deduplicated afterwards.
    """
    bedges = [e for e in bm.edges if e.is_boundary]
    adj = defaultdict(list)
    for e in bedges:
        adj[e.verts[0]].append(e)
        adj[e.verts[1]].append(e)
    unseen = set(bedges)
    loops = []
    while unseen:
        start = min(unseen, key=lambda e: (e.verts[0].index, e.verts[1].index))
        a, b = start.verts
        loop = [a, b]
        used = {start}
        unseen.discard(start)
        prev, cur = a, b
        closed = False
        for _ in range(20000):
            candidates = [e for e in adj[cur] if e not in used]
            if not candidates:
                break
            if len(candidates) > 1:
                dir_in = (cur.co - prev.co)
                if dir_in.length > 1e-9:
                    dir_in.normalize()

                    def turn_score(edge):
                        other = edge.other_vert(cur)
                        d = other.co - cur.co
                        if d.length <= 1e-9:
                            return 1e9
                        d.normalize()
                        # Prefer continuing straight, but never immediately back.
                        back = -1.0 if other == prev else 0.0
                        return back - d.dot(dir_in)

                    candidates.sort(key=turn_score)
            edge = candidates[0]
            nxt = edge.other_vert(cur)
            used.add(edge)
            unseen.discard(edge)
            if nxt == loop[0]:
                closed = True
                break
            if nxt in loop:
                cycle = loop[loop.index(nxt):]
                if len(cycle) >= 3:
                    loops.append(cycle)
                closed = True
                break
            loop.append(nxt)
            prev, cur = cur, nxt
        if closed and len(loop) >= 3:
            loops.append(loop)
    unique = []
    seen = set()
    for lp in loops:
        key = frozenset(v.index for v in lp)
        if len(lp) >= 3 and key not in seen:
            seen.add(key)
            unique.append(lp)
    return unique


def fill_boundary_loops(objs, uv_step=0.0025):
    """Fill small holes and give the fill coherent, non-black UVs.

    The old per-vertex fan caps often bridged UV seams and sampled the dark
    unused parts of the Meshy atlas, producing exactly the 'black triangular
    holes' criticised in review.  Here every cap face is orientated like its
    neighbouring surface and mapped to a tiny coherent patch around one
    reference UV; small caps therefore read as stone/wood rather than voids.
    Returns the number of cap faces created.
    """
    created_total = 0
    for obj in _mesh_objects(objs):
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.active
        before_faces = set(bm.faces)
        edge_reference_normal = {}
        edge_reference_uv = {}
        for e in [e for e in bm.edges if e.is_boundary]:
            if e.link_faces:
                edge_reference_normal[e] = e.link_faces[0].normal.copy()
                if uv_layer is not None:
                    lp = next((l for l in e.link_faces[0].loops if l.vert in e.verts), None)
                    if lp is not None:
                        edge_reference_uv[e] = lp[uv_layer].uv.copy()
        loops = boundary_loops(bm)
        if not loops:
            bm.free()
            continue
        # Fill loops one at a time with Blender's constrained triangulated
        # hole fill.  holes_fill() silently skips most concave smart-topology
        # slots; triangle_fill() handles them and produces small renderable
        # triangles.  Re-scan once afterwards: a few intersecting layer-edge
        # loops only become fillable after their neighbours are closed.
        new_faces = []
        for _pass in range(2):
            loops_now = boundary_loops(bm)
            made_this_pass = 0
            for loop in loops_now:
                edges = []
                for i, a in enumerate(loop):
                    e = bm.edges.get((a, loop[(i + 1) % len(loop)]))
                    if e is not None and e.is_boundary:
                        edges.append(e)
                if len(edges) < 3:
                    continue
                before = set(bm.faces)
                try:
                    bmesh.ops.triangle_fill(bm, edges=edges)
                except Exception:
                    continue
                made = [f for f in bm.faces if f not in before]
                new_faces.extend(made)
                made_this_pass += len(made)
            if not made_this_pass:
                break
        # A few residual loops are simple tiny slivers rejected by
        # triangle_fill.  Close those directly when no face already exists;
        # they are the pinprick black triangles visible in review close-ups.
        for loop in boundary_loops(bm):
            if len(loop) > 10:
                continue
            before = set(bm.faces)
            try:
                bm.faces.new(loop)
            except ValueError:
                continue
            new_faces.extend([f for f in bm.faces if f not in before])
        if uv_layer is not None:
            vert_uv = _vert_uv_map(bm, uv_layer)
        # Per-hole reference data.  Faces made by holes_fill are not labelled,
        # so use the nearest boundary edge/vertex reference on a face-by-face
        # basis; the holes are small enough that this is stable.
        for f in new_faces:
            ref_n = Vector((0.0, 0.0, 1.0))
            ref_uv = Vector((0.5, 0.5))
            best = None
            best_d = 1e100
            fc = f.calc_center_median()
            for e, uv0 in edge_reference_uv.items():
                ec = (e.verts[0].co + e.verts[1].co) * 0.5
                d = (ec - fc).length_squared
                if d < best_d:
                    best_d = d
                    best = e
                    ref_uv = uv0.copy()
            if best is not None and best in edge_reference_normal:
                ref_n = edge_reference_normal[best]
            if f.normal.dot(ref_n) < 0.0:
                f.normal_flip()
            if uv_layer is not None:
                # Keep caps inside a few UV pixels.  The offsets prevent a
                # completely flat fill but cannot cross an island boundary.
                c = sum((v.co for v in f.verts), Vector()) / len(f.verts)
                for lp in f.loops:
                    d = lp.vert.co - c
                    lp[uv_layer].uv = ref_uv + Vector((d.x, d.y)) * min(uv_step, 0.001 + uv_step / max(1.0, c.length))
        created_total += len(new_faces)
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()
    return created_total


def _object_arrays(obj):
    me = obj.data
    pos = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", pos)
    return pos.reshape((-1, 3))


def join_into(main, extras):
    """Join helper meshes into the main Meshy object, preserving materials/UVs."""
    extras = [o for o in extras if o and o.type == "MESH" and o is not main]
    if not extras:
        return main
    bpy.ops.object.select_all(action="DESELECT")
    main.select_set(True)
    for o in extras:
        o.select_set(True)
    bpy.context.view_layer.objects.active = main
    bpy.ops.object.join()
    return main


# ---------------------------------------------------------------------------
# Procedural local patches


def _basis(axis):
    axis = Vector(axis).normalized()
    guide = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.82 else Vector((1.0, 0.0, 0.0))
    u = axis.cross(guide).normalized()
    v = axis.cross(u).normalized()
    return axis, u, v


def _noise01(seed, n):
    x = np.sin(seed * 12.9898 + np.arange(n, dtype=np.float64) * 78.233) * 43758.5453
    return x - np.floor(x)


def make_jagged_tip_caps(obj, zmin_frac=0.40, min_radius=0.018, max_radius=0.22,
                         length_mul=2.2, segments=9, name="tipcap",
                         ratio_min=0.34, cluster_radius=0.28):
    """Add irregular tapered wooden caps at small upper boundary holes.

    Returns (cap_objects, count).  The caps are deliberately separate patches
    intersecting the tube end by a few millimetres; this hides the flush
    smart-topology 'cut pipe' end without requiring boolean surgery on the
    30k source mesh.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    loops = boundary_loops(bm)
    zlo = min((v.co.z for v in bm.verts), default=0.0)
    zhi = max((v.co.z for v in bm.verts), default=1.0)
    height = max(1e-6, zhi - zlo)
    uv_layer = bm.loops.layers.uv.active
    vert_uv = _vert_uv_map(bm, uv_layer)
    allco = np.array([v.co[:] for v in bm.verts], dtype=np.float64) if bm.verts else np.zeros((0, 3))
    specs = []
    for loop in loops:
        pts = np.array([v.co[:] for v in loop], dtype=np.float64)
        c = pts.mean(axis=0)
        rr = np.linalg.norm(pts - c, axis=1)
        radius = float(rr.mean())
        zrel = (c[2] - zlo) / height
        if zrel < zmin_frac or radius < min_radius or radius > max_radius:
            continue
        # Local PCA estimates the tube direction; orient it outwards using the
        # fact that the shaft centroid lies behind the tip opening.
        dist = np.linalg.norm(allco - c, axis=1) if len(allco) else np.array([])
        sel = dist < max(0.16, radius * 6.0)
        cloud = allco[sel] if np.count_nonzero(sel) >= 8 else pts
        centroid = cloud.mean(axis=0)
        cov = np.cov((cloud - centroid).T) if len(cloud) > 3 else np.eye(3)
        vals, vecs = np.linalg.eigh(cov)
        axis = vecs[:, int(np.argmax(vals))]
        outward = c - centroid
        if np.dot(axis, outward) < 0:
            axis = -axis
        if np.linalg.norm(axis) < 1e-8:
            axis = np.array([0.0, 0.0, 1.0])
        axis = axis / np.linalg.norm(axis)
        # Estimate the real tube radius, not just the pinhole in its end cap.
        rel = cloud - c
        axial = rel @ axis
        radial = rel - np.outer(axial, axis)
        near = np.abs(axial) < max(0.12, radius * 4.0)
        if np.count_nonzero(near) >= 6:
            measured_tube_r = float(np.quantile(np.linalg.norm(radial[near], axis=1), 0.82))
        else:
            measured_tube_r = radius
        # Pinholes in a broad side/end face are tiny compared with the local
        # branch diameter.  Only true open tube mouths span a substantial part
        # of that diameter; this distinction prevents dozens of spike-like
        # false caps on small smart-topology pinholes.
        if radius < measured_tube_r * ratio_min and zrel < 0.82:
            continue
        tube_r = max(radius * 1.05, min(measured_tube_r * 1.03, max_radius * 2.4))
        uv0 = Vector((0.5, 0.5))
        for v in loop:
            if v in vert_uv:
                uv0 = vert_uv[v]
                break
        specs.append((Vector(c), Vector(axis), tube_r, uv0, radius))
    bm.free()

    # Smart-topology end caps often contain several small holes around one
    # tube mouth.  Keep the largest opening per spatial cluster so a branch
    # tip receives one organic cap rather than a tuft of duplicate cones.
    specs.sort(key=lambda s: s[4], reverse=True)
    clustered = []
    for spec in specs:
        if all((spec[0] - old[0]).length >= cluster_radius for old in clustered):
            clustered.append(spec)
    clustered.sort(key=lambda s: (s[0].x, s[0].y, s[0].z))

    caps = []
    mats = list(obj.data.materials)
    for si, (center, axis, radius, uv0, _opening_radius) in enumerate(clustered):
        axis, u, v = _basis(axis)
        length = max(radius * length_mul, radius * 1.4)
        rnd = _noise01(si + 3.17, segments * 3)
        verts = []
        uvs = []
        # Slightly inset base ring: intersections are hidden inside the tube.
        base_c = center - axis * max(0.006, radius * 0.12)
        for ring, (axf, rf) in enumerate(((0.0, 1.0), (0.48, 0.62))):
            for j in range(segments):
                ang = 2.0 * math.pi * j / segments
                jitter = 0.82 + 0.30 * rnd[j + ring * segments]
                p = base_c + axis * (length * axf * (0.88 + 0.20 * rnd[j + segments])) + \
                    (u * math.cos(ang) + v * math.sin(ang)) * radius * rf * jitter
                verts.append(tuple(p))
                uvs.append((uv0.x + math.cos(ang) * 0.0015 * (ring + 1),
                            uv0.y + math.sin(ang) * 0.0015 * (ring + 1)))
        # Three uneven splinter tips instead of a single machined cone point.
        tip_ids = []
        for k in range(3):
            ang = 2.0 * math.pi * (k / 3.0 + 0.11 * si)
            p = base_c + axis * (length * (0.82 + 0.16 * rnd[k])) + \
                (u * math.cos(ang) + v * math.sin(ang)) * radius * (0.10 + 0.09 * rnd[k + 4])
            tip_ids.append(len(verts))
            verts.append(tuple(p))
            uvs.append((uv0.x, uv0.y))
        # Close the back of the cap.  Without this face the patch is an open
        # shell and Blender's consistent-normal pass can turn the whole cap
        # inwards, making it read as a black hollow cup in review close-ups.
        base_center_id = len(verts)
        verts.append(tuple(base_c - axis * max(0.012, radius * 0.16)))
        uvs.append((uv0.x, uv0.y))
        faces = []
        face_uvs = []
        for j in range(segments):
            nj = (j + 1) % segments
            faces.append((j, nj, segments + nj, segments + j))
            face_uvs.append((j, nj, segments + nj, segments + j))
        # Connect each mid-ring edge to alternating uneven tips.
        for j in range(segments):
            nj = (j + 1) % segments
            tip = tip_ids[(j * 3) // max(1, segments) % 3]
            faces.append((segments + j, segments + nj, tip))
            face_uvs.append((segments + j, segments + nj, tip))
        for j in range(segments):
            nj = (j + 1) % segments
            faces.append((nj, j, base_center_id))
            face_uvs.append((nj, j, base_center_id))
        me = bpy.data.meshes.new(f"{name}_{si:02d}")
        me.from_pydata(verts, [], faces)
        me.update()
        # Make the closed cap unambiguously outward-oriented before any global
        # normals_make_consistent pass.  Side normals get a positive radial
        # component; hidden back faces point backwards along the branch axis.
        vco = [Vector(vv) for vv in verts]
        axis_v = Vector(axis)
        for poly in me.polygons:
            ids = list(poly.vertices)
            fc = sum((vco[i] for i in ids), Vector()) / len(ids)
            if base_center_id in ids:
                desired = -axis_v
            else:
                t = (fc - base_c).dot(axis_v)
                radial = fc - (base_c + axis_v * t)
                desired = radial.normalized() if radial.length > 1e-8 else axis_v
            if poly.normal.dot(desired) < 0.0:
                poly.flip()
        me.update()
        uvlay = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                uvlay.data[li].uv = uvs[vi]
        for mat in mats:
            me.materials.append(mat)
        cap = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(cap)
        caps.append(cap)
    return caps, len(caps)


def make_cavity_plug(obj, axis=0, sign=1, inset=0.30, radial_scale=0.88,
                     segments=32, slice_frac=0.14, name="cavity_plug", relief=0.025, circular=False):
    """Create an irregular recessed wooden plug inside a hollow log/stump end.

    The radial profile is measured per angular bin from the source shell.  A
    slightly smaller, uneven disc therefore sits behind the jagged rim instead
    of covering it, replacing the bottomless black cavity with readable wood.
    """
    pos = _object_arrays(obj)
    if not len(pos):
        return None
    axis = int(axis)
    other = [i for i in range(3) if i != axis]
    end = float(pos[:, axis].max() if sign > 0 else pos[:, axis].min())
    span = float(pos[:, axis].max() - pos[:, axis].min())
    thickness = max(1e-4, span * slice_frac)
    if sign > 0:
        sel = pos[:, axis] > end - thickness
    else:
        sel = pos[:, axis] < end + thickness
    shell = pos[sel]
    if len(shell) < 12:
        shell = pos
    plane = shell[:, other]
    center2 = np.median(plane, axis=0)
    rel = plane - center2
    ang = np.arctan2(rel[:, 1], rel[:, 0])
    rad = np.linalg.norm(rel, axis=1)
    radii = np.zeros(segments)
    counts = np.zeros(segments, dtype=int)
    for j in range(segments):
        a0 = -math.pi + 2 * math.pi * j / segments
        a1 = -math.pi + 2 * math.pi * (j + 1) / segments
        am = (a0 + a1) * 0.5
        d = np.abs((ang - am + math.pi) % (2 * math.pi) - math.pi)
        use = d < (math.pi / segments * 1.35)
        if np.count_nonzero(use):
            radii[j] = np.quantile(rad[use], 0.82) * radial_scale
            counts[j] = np.count_nonzero(use)
    # Fill missing bins by circular interpolation/smoothing.
    valid = counts > 0
    if np.count_nonzero(valid) >= 3:
        xs = np.arange(segments)
        for j in range(segments):
            if not valid[j]:
                dists = np.minimum((xs - j) % segments, (j - xs) % segments)
                near = valid & (dists > 0)
                w = 1.0 / np.maximum(dists[near], 1)
                radii[j] = float(np.sum(radii[near] * w) / np.sum(w))
    elif len(rad):
        radii[:] = np.quantile(rad, 0.8) * radial_scale
    # Light circular smoothing removes one-off spikes from branch stubs.
    radii = 0.22 * np.roll(radii, -1) + 0.56 * radii + 0.22 * np.roll(radii, 1)
    if circular and len(rad):
        radii[:] = np.quantile(rad, 0.72) * radial_scale
    axial_c = end - sign * inset
    # Build a shallow relief plug: outer ring, mid ring, three off-centre knots.
    verts = []
    faces = []
    for ring, (rf, axial_off) in enumerate(((1.0, 0.0), (0.58, -sign * inset * 0.18))):
        for j in range(segments):
            a = 2 * math.pi * j / segments
            jitter = 1.0 + 0.045 * math.sin(j * 2.17 + axial_c) + 0.025 * math.sin(j * 5.11)
            co = [0.0, 0.0, 0.0]
            co[axis] = axial_c + axial_off + sign * relief * (0.65 * math.sin(j * 1.73) + 0.35 * math.sin(j * 4.19 + 0.7))
            co[other[0]] = center2[0] + math.cos(a) * radii[j] * rf * jitter
            co[other[1]] = center2[1] + math.sin(a) * radii[j] * rf * jitter
            verts.append(tuple(co))
    center_ids = []
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.31
        co = [0.0, 0.0, 0.0]
        co[axis] = axial_c - sign * (inset * (0.24 + 0.06 * k) + relief * 0.35 * math.sin(k * 2.1 + 0.4))
        co[other[0]] = center2[0] + math.cos(a) * float(np.mean(radii)) * 0.10
        co[other[1]] = center2[1] + math.sin(a) * float(np.mean(radii)) * 0.10
        center_ids.append(len(verts))
        verts.append(tuple(co))
    for j in range(segments):
        nj = (j + 1) % segments
        if sign > 0:
            faces.append((j, nj, segments + nj, segments + j))
        else:
            faces.append((nj, j, segments + j, segments + nj))
    for j in range(segments):
        nj = (j + 1) % segments
        tip = center_ids[(j * 3) // segments]
        if sign > 0:
            faces.append((segments + j, segments + nj, tip))
        else:
            faces.append((segments + nj, segments + j, tip))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    # Coherent small UV patch: growth-ring-like polar offsets around a fixed
    # reference UV.  This avoids the UV-island streaking of naive cap fans.
    uvlay = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            if vi < 2 * segments:
                ring = vi // segments
                j = vi % segments
                a = 2 * math.pi * j / segments
                uvlay.data[li].uv = (0.48 + math.cos(a) * 0.006 * (ring + 1),
                                     0.48 + math.sin(a) * 0.006 * (ring + 1))
            else:
                uvlay.data[li].uv = (0.48, 0.48)
    for mat in obj.data.materials:
        me.materials.append(mat)
    plug = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(plug)
    return plug


# ---------------------------------------------------------------------------
# Geometry smoothing / shaping


def laplacian_smooth_region(objs, zmin_frac=0.0, zmax_frac=1.0, radius_xy=None,
                            iterations=2, factor=0.45):
    """Numpy Laplacian smooth for dense class-A sculpt regions."""
    for obj in _mesh_objects(objs):
        me = obj.data
        if len(me.vertices) < 10:
            continue
        pos = _object_arrays(obj).copy()
        zmin, zmax = pos[:, 2].min(), pos[:, 2].max()
        zspan = max(1e-9, zmax - zmin)
        xy = pos[:, :2] - pos[:, :2].mean(axis=0)
        sel = (pos[:, 2] >= zmin + zspan * zmin_frac) & (pos[:, 2] <= zmin + zspan * zmax_frac)
        if radius_xy is not None:
            sel &= np.linalg.norm(xy, axis=1) <= radius_xy
        if not np.count_nonzero(sel):
            continue
        edges = set()
        for poly in me.polygons:
            vs = list(poly.vertices)
            for i, a in enumerate(vs):
                b = vs[(i + 1) % len(vs)]
                edges.add((min(a, b), max(a, b)))
        ea = np.array(sorted(edges), dtype=np.int32)
        if not len(ea):
            continue
        adj_sum = np.zeros_like(pos)
        adj_count = np.zeros(len(pos), dtype=np.float64)
        for _ in range(iterations):
            adj_sum[:] = 0.0
            adj_count[:] = 0.0
            np.add.at(adj_sum, ea[:, 0], pos[ea[:, 1]])
            np.add.at(adj_sum, ea[:, 1], pos[ea[:, 0]])
            np.add.at(adj_count, ea[:, 0], 1.0)
            np.add.at(adj_count, ea[:, 1], 1.0)
            valid = sel & (adj_count > 0)
            avg = adj_sum[valid] / adj_count[valid, None]
            pos[valid] = pos[valid] * (1.0 - factor) + avg * factor
        flat = pos.reshape(-1)
        me.vertices.foreach_set("co", flat)
        me.update()


def scale_xy(objs, sx=1.0, sy=1.0):
    """Non-uniformly scale XY about the footprint centre, preserving z_min."""
    import vrlib
    lo, hi = vrlib.world_bounds(objs)
    cx, cz = (lo.x + hi.x) * 0.5, lo.z
    cy = (lo.y + hi.y) * 0.5
    for obj in _mesh_objects(objs):
        for v in obj.data.vertices:
            v.co.x = cx + (v.co.x - cx) * sx
            v.co.y = cy + (v.co.y - cy) * sy
        obj.data.update()
    # Re-centre tiny numerical drift; z remains untouched.
    lo2, hi2 = vrlib.world_bounds(objs)
    dx = cx - (lo2.x + hi2.x) * 0.5
    dy = cy - (lo2.y + hi2.y) * 0.5
    for obj in _mesh_objects(objs):
        for v in obj.data.vertices:
            v.co.x += dx
            v.co.y += dy
        obj.data.update()


def bark_ridge_displacement(obj, amplitude=0.018, zmin_frac=0.04, zmax_frac=0.78,
                            frequencies=(19.0, 37.0), seed=0.0):
    """Add fine longitudinal elephant-hide ridges to a vertical trunk mesh.

    The displacement is radial in XY and deliberately small: it breaks the
    clay/leather look in close-ups without changing the silhouette.  Vertices
    are weighted smoothly in and out over the selected height band.
    """
    me = obj.data
    if len(me.vertices) < 20:
        return
    pos = _object_arrays(obj).copy()
    zmin, zmax = pos[:, 2].min(), pos[:, 2].max()
    zspan = max(1e-9, zmax - zmin)
    xy = pos[:, :2] - pos[:, :2].mean(axis=0)
    rr = np.linalg.norm(xy, axis=1)
    theta = np.arctan2(xy[:, 1], xy[:, 0])
    zn = (pos[:, 2] - zmin) / zspan
    mask = (zn >= zmin_frac) & (zn <= zmax_frac) & (rr > 1e-5)
    edge = np.minimum(np.clip((zn - zmin_frac) / 0.08, 0, 1), np.clip((zmax_frac - zn) / 0.10, 0, 1))
    f1, f2 = frequencies
    wave = (np.sin(theta * f1 + zn * 10.5 + seed) * 0.55 +
            np.sin(theta * f2 - zn * 17.0 + seed * 1.71) * 0.30 +
            np.sin(theta * (f1 * 0.47 + 1.0) + zn * 31.0) * 0.15)
    disp = amplitude * wave * edge
    out = pos.copy()
    out[mask, 0] += xy[mask, 0] / rr[mask] * disp[mask]
    out[mask, 1] += xy[mask, 1] / rr[mask] * disp[mask]
    me.vertices.foreach_set("co", out.reshape(-1))
    me.update()


def flare_base(obj, height=0.75, strength=0.16):
    """Broaden the lowest trunk/root transition with a smooth vertical falloff."""
    me = obj.data
    pos = _object_arrays(obj).copy()
    zmin = pos[:, 2].min()
    z = pos[:, 2] - zmin
    center = pos[z < height * 0.5, :2].mean(axis=0) if np.count_nonzero(z < height * 0.5) else pos[:, :2].mean(axis=0)
    w = np.clip(1.0 - z / max(height, 1e-6), 0.0, 1.0) ** 1.7
    xy = pos[:, :2] - center
    pos[:, :2] += xy * (w * strength)[:, None]
    me.vertices.foreach_set("co", pos.reshape(-1))
    me.update()


def bury_skirt_below_ground(objs, depth):
    """Place a vrmeshy.burial_skirt cut seam at z=0 so skirt walls stay hidden.

    This is the same seam correction previously duplicated in the Meshy asset
    build scripts.  It is centralised here because all repaired Meshy assets
    need it after adding the underground skirt.
    """
    for o in _mesh_objects(objs):
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
                if (any(v.co.z <= -depth + 1e-3 for v in f.verts) and
                        any(v.co.z > -depth + 1e-3 for v in f.verts)):
                    for loop in f.loops:
                        if loop.vert.co.z <= -depth + 1e-3:
                            uv = loop[uv_layer].uv
                            loop[uv_layer].uv = uv + (center - uv) * 0.04
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


# ---------------------------------------------------------------------------
# Texture repair


def _image_pixels(img):
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


def _replace_image(img, px, suffix):
    return vrmeshy._replace_image(img, px, suffix)


def _swap_images(objs, mapping):
    vrmeshy._swap_images(objs, mapping)


def _basecolor_nodes(objs):
    return vrmeshy._basecolor_image_nodes(objs)


def soften_basecolor_weave(objs, radius=2, keep=0.38):
    """Suppress regular cloth/crosshatch high frequency in base-colour maps.

    keep is the fraction of high-frequency detail retained after a separable
    box low-pass.  Large cracks, masonry seams and stains survive because the
    low-pass component is preserved unchanged.
    """
    made = {}
    for node in _basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = _image_pixels(img)
        rgb = px[..., :3]
        low = np.empty_like(rgb)
        rad = max(1, int(radius))
        for ch in range(3):
            low[..., ch] = vrmeshy._box_blur(rgb[..., ch], rad)
        out = np.clip(low + (rgb - low) * float(keep), 0.0, 1.0)
        made[img] = _replace_image(img, np.concatenate([out, px[..., 3:]], axis=-1), "_deweave")
    _swap_images(objs, made)
    return made


def harmonize_basecolor(objs, target_hex, hue_keep=0.42, sat_mul=0.72, val_shift=0.0):
    """Compress hue outliers toward a palette colour while keeping value detail."""
    h = target_hex.lstrip("#")
    target = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)
    tgt = vrmeshy._rgb_to_hsv(target.reshape(1, 1, 3))[0, 0]
    made = {}
    for node in _basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = _image_pixels(img)
        hsv = vrmeshy._rgb_to_hsv(px[..., :3])
        dh = ((hsv[..., 0] - tgt[0] + 0.5) % 1.0) - 0.5
        hsv[..., 0] = (tgt[0] + dh * hue_keep) % 1.0
        hsv[..., 1] = np.clip(hsv[..., 1] * sat_mul, 0.0, 1.0)
        hsv[..., 2] = np.clip(hsv[..., 2] + val_shift, 0.0, 1.0)
        out = np.clip(vrmeshy._hsv_to_rgb(hsv), 0.0, 1.0)
        made[img] = _replace_image(img, np.concatenate([out, px[..., 3:]], axis=-1), "_harmonized")
    _swap_images(objs, made)
    return made


def tint_basecolor(objs, rgb_mul=(1.0, 1.0, 1.0)):
    """Direct deterministic colour balance multiplier in texture space."""
    mul = np.array(rgb_mul, dtype=np.float32).reshape(1, 1, 3)
    made = {}
    for node in _basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = _image_pixels(img)
        out = np.clip(px[..., :3] * mul, 0.0, 1.0)
        made[img] = _replace_image(img, np.concatenate([out, px[..., 3:]], axis=-1), "_tinted")
    _swap_images(objs, made)
    return made


def adjust_basecolor_levels(objs, gain=1.0, gamma=1.0, lift=0.0):
    """Simple deterministic level adjustment on the albedo texture."""
    made = {}
    for node in _basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = _image_pixels(img)
        out = np.clip((px[..., :3] ** float(gamma)) * float(gain) + float(lift), 0.0, 1.0)
        made[img] = _replace_image(img, np.concatenate([out, px[..., 3:]], axis=-1), "_levels")
    _swap_images(objs, made)
    return made


def overlay_detail_luminance(objs, src_path, strength=0.18, repeat=1):
    """Modulate albedo by a tileable project detail texture's luminance.

    This replaces Meshy's repetitive ornamental micro-pattern with the natural
    bark/stone grain already used by Violet Reach's material classes, without
    changing the UV layout or palette.  `strength` is deliberately small.
    """
    if not os.path.isfile(src_path) or strength <= 0:
        return {}
    src = bpy.data.images.load(src_path)
    try:
        pxsrc = _image_pixels(src)
    finally:
        bpy.data.images.remove(src)
    lum_src = pxsrc[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    lum_src = lum_src / max(float(np.mean(lum_src)), 1e-5)
    made = {}
    for node in _basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        w, h = img.size
        # Resize tile to 1024 before repeating; this keeps detail frequency in
        # a useful range and avoids a huge memory footprint at 4k.
        tile = 1024
        small = np.array(
            np.array(lum_src[::max(1, lum_src.shape[0] // tile), ::max(1, lum_src.shape[1] // tile)]),
            dtype=np.float32,
        )
        rep = max(1, int(repeat))
        tiled = np.tile(small, (rep, rep))
        # Nearest-neighbour resample to the destination resolution.
        yy = (np.arange(h) * tiled.shape[0] // h).astype(int)
        xx = (np.arange(w) * tiled.shape[1] // w).astype(int)
        lum = tiled[yy][:, xx]
        mod = 1.0 + (lum - 1.0) * float(strength)
        px = _image_pixels(img)
        out = np.clip(px[..., :3] * mod[..., None], 0.0, 1.0)
        made[img] = _replace_image(img, np.concatenate([out, px[..., 3:]], axis=-1), "_detail")
    _swap_images(objs, made)
    return made


def set_normal_strength(objs, strength):
    """Reduce Meshy's cloth-like normal relief without touching shared data."""
    count = 0
    seen = set()
    for obj in _mesh_objects(objs):
        for mat in obj.data.materials:
            if not mat or not mat.node_tree or mat in seen:
                continue
            seen.add(mat)
            for node in mat.node_tree.nodes:
                if node.type == "NORMAL_MAP" and "Strength" in node.inputs:
                    node.inputs["Strength"].default_value = float(strength)
                    count += 1
    return count

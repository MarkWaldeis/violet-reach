"""Gespaltenes Inselmonument A (monument_split_disc_a) — creditfreie R6-Reparatur.

R6 geht die drei R5-Hauptmängel geometrisch statt kosmetisch an:

* die Bruchwand wird lokal bis auf eine kleine Dreieckskante verfeinert und erst
  danach mit mehrskaliger, begrenzt scharfer Bruchrelief-Deformation versehen;
  zusätzliche kleine geschlossene Splinter-/Schuppenkomponenten sind in die
  Bruchwand eingebettet, ohne die offene Luftfuge zuzustellen,
* die Auflager sind keine Einzelklötze oder eingeschnittenen Fremdkörper mehr.
  Die Plinthe wird im Kontaktband adaptiv verfeinert und anschließend selbst zu
  zwei durchgehenden, profilierten Lagerwangen verformt; Stufe, Schulter, Wange
  und Verschmutzungsmulde bleiben dadurch dieselbe zusammenhängende Steinoberfläche,
* die rektiline Poren-/Wurm-Normalstruktur des Rohmodells wird durch ruhige,
  isotrope Mineralgranulation ersetzt.  Die Albedo behält mehr von ihrer
  ursprünglichen Kalksteinstruktur, wird aber nicht mehr schwarz-porig oder
  plastisch geglättet.

Alles ist deterministisch, lokal prozedural und verwendet weder Meshy-Credits
noch externe Nachbearbeitungsdaten.
"""
import math
import os

import bpy
import bmesh
import numpy as np

import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Numerische Basishelfer


def _smoothstep(edge0, edge1, x):
    edge0 = float(edge0)
    edge1 = float(edge1)
    t = np.clip((np.asarray(x) - edge0) / max(edge1 - edge0, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash01(values):
    x = np.sin(np.asarray(values, dtype=np.float64) * 127.1 + 311.7) * 43758.5453123
    return x - np.floor(x)


def _hash2(ix, iy, seed):
    v = (np.asarray(ix, dtype=np.float64) * 127.1 +
         np.asarray(iy, dtype=np.float64) * 269.5 +
         float(seed) * 37.719)
    x = np.sin(v) * 43758.5453123
    return x - np.floor(x)


def _value_noise2(x, y, seed):
    """Deterministic smooth value noise in [-1, 1], vectorized."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    xi = np.floor(x).astype(np.int64)
    yi = np.floor(y).astype(np.int64)
    xf = x - xi
    yf = y - yi
    u = xf * xf * (3.0 - 2.0 * xf)
    v = yf * yf * (3.0 - 2.0 * yf)
    h00 = _hash2(xi, yi, seed)
    h10 = _hash2(xi + 1, yi, seed)
    h01 = _hash2(xi, yi + 1, seed)
    h11 = _hash2(xi + 1, yi + 1, seed)
    a = h00 * (1.0 - u) + h10 * u
    b = h01 * (1.0 - u) + h11 * u
    return (a * (1.0 - v) + b * v) * 2.0 - 1.0


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


def _diffuse_scalar(values, edges, passes=1, amount=0.28):
    w = np.asarray(values, dtype=np.float64).copy()
    for _ in range(max(0, int(passes))):
        avg, count = _neighbour_mean(w, edges)
        valid = count > 0
        w[valid] = w[valid] * (1.0 - amount) + avg[valid] * amount
    return w


def _surface_data(obj):
    """Polygon centres/normals plus per-polygon vertex index arrays."""
    me = obj.data
    pos = _positions(obj)
    npoly = len(me.polygons)
    centres = np.zeros((npoly, 3), dtype=np.float64)
    normals = np.zeros((npoly, 3), dtype=np.float64)
    poly_ids = []
    for pi, poly in enumerate(me.polygons):
        ids = np.array(poly.vertices, dtype=np.int32)
        if len(ids) < 3:
            poly_ids.append(ids)
            continue
        centres[pi] = pos[ids].mean(axis=0)
        n = np.array(poly.normal[:], dtype=np.float64)
        ln = float(np.linalg.norm(n))
        if ln > 1e-12:
            n /= ln
        normals[pi] = n
        poly_ids.append(ids)
    return {"pos": pos, "centres": centres, "normals": normals, "poly_ids": poly_ids}


# ---------------------------------------------------------------------------
# Lokale Bruchverfeinerung und mehrskaliges Bruchrelief


def _fracture_face_score(center, normal):
    c = np.asarray(center, dtype=np.float64)
    n = np.asarray(normal, dtype=np.float64)
    an = np.abs(n)
    denom = max(float(an.sum()), 1e-9)
    nxfrac = abs(float(n[0])) / denom
    nzfrac = abs(float(n[2])) / denom
    central = float(1.0 - _smoothstep(4.10, 5.05, abs(c[0])))
    xdominant = float(_smoothstep(0.18, 0.37, nxfrac))
    # The narrow vertical strip right at the open wedge belongs to the fracture
    # lip even where its normal turns towards the viewer.  Horizontal plinth
    # surfaces are explicitly excluded so the socket heightfield is not moved.
    inner_core = float(1.0 - _smoothstep(1.85, 2.85, abs(c[0])))
    inner_core *= 1.0 - float(_smoothstep(0.54, 0.76, nzfrac))
    zweight = float(_smoothstep(7.65, 9.05, c[2]))
    return zweight * central * max(xdominant, inner_core)


def _refine_fracture_mesh(obj, max_edge=0.28, max_passes=7):
    """Adaptively subdivide only long edges in the split/fracture system.

    The source smart topology contains isolated 3–7 m triangles exactly on the
    planar cleft walls.  Displacing those without refinement necessarily makes
    origami facets.  BMesh subdivision preserves watertightness and interpolates
    the original UVs; unselected dense areas are left untouched.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    passes = []
    for passno in range(int(max_passes)):
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        selected = set()
        for face in bm.faces:
            if _fracture_face_score(face.calc_center_median(), face.normal) > 0.12:
                selected.add(face)
        edges = []
        for edge in bm.edges:
            if edge.calc_length() > float(max_edge) and any(f in selected for f in edge.link_faces):
                edges.append(edge)
        if not edges:
            break
        before = (len(bm.verts), len(bm.faces))
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        passes.append({
            "pass": passno,
            "region_faces": len(selected),
            "split_edges": len(edges),
            "verts_before": before[0],
            "faces_before": before[1],
            "verts_after": len(bm.verts),
            "faces_after": len(bm.faces),
        })
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()

    me = obj.data
    pos = _positions(obj)
    lengths = []
    region_faces = 0
    for poly in me.polygons:
        c = np.array(poly.center[:], dtype=np.float64)
        n = np.array(poly.normal[:], dtype=np.float64)
        if _fracture_face_score(c, n) <= 0.12:
            continue
        region_faces += 1
        ids = list(poly.vertices)
        for i, a in enumerate(ids):
            lengths.append(float(np.linalg.norm(pos[a] - pos[ids[(i + 1) % len(ids)]])))
    return {
        "passes": passes,
        "max_edge_target": float(max_edge),
        "region_faces_after": int(region_faces),
        "region_edge_max": max(lengths) if lengths else 0.0,
        "region_edge_p95": float(np.quantile(lengths, 0.95)) if lengths else 0.0,
    }


# ---------------------------------------------------------------------------
# Integriertes Auflager: die Plinthe selbst wird zu einer durchgehenden Nut
# verfeinert und verformt.  Dadurch gibt es keine separate sichtbare Klemm- oder
# Klotzgeometrie und keine harte Objekt-In-Objekt-Basisnaht mehr.


def _socket_face_score(center, normal):
    """How much a face belongs to the upper-plinth socket shoulder.

    The seat is on a curved shoulder rather than on a perfectly horizontal
    plane, so even a small positive signed z normal is significant.  Vertical
    step risers, downward disc undersides and the steep open-split walls score
    near zero.  The score is deliberately x/y/z bounded: it must never select
    the broad buried plinth or the tall disc faces.
    """
    c = np.asarray(center, dtype=np.float64)
    n = np.asarray(normal, dtype=np.float64)
    ln = float(np.linalg.norm(n))
    if ln <= 1e-12:
        return 0.0
    nz = float(n[2] / ln)
    upward = float(_smoothstep(0.015, 0.24, nz))
    zband = float(_smoothstep(5.05, 5.55, c[2]) * (1.0 - _smoothstep(8.48, 8.96, c[2])))
    xband = float(1.0 - _smoothstep(8.75, 9.48, abs(c[0])))
    yband = float(1.0 - _smoothstep(6.18, 6.88, abs(c[1] - 0.30)))
    return upward * zband * xband * yband


def _refine_socket_mesh(obj, max_edge=0.32, max_passes=7):
    """Adaptively refine only long edges on the smooth socket shoulder.

    R5/R6 iteration showed metre-scale source triangles exactly in the seating
    band.  Sculpting those sparse triangles produces sawteeth no matter how the
    displacement field is shaped.  This pass is separate from fracture
    refinement because the seat needs dense smooth-stone topology while the
    remainder of the plinth remains unchanged.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    passes = []
    for passno in range(int(max_passes)):
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        selected = set()
        for face in bm.faces:
            if _socket_face_score(face.calc_center_median(), face.normal) > 0.10:
                selected.add(face)
        edges = []
        for edge in bm.edges:
            if edge.calc_length() > float(max_edge) and any(f in selected for f in edge.link_faces):
                edges.append(edge)
        if not edges:
            break
        before = (len(bm.verts), len(bm.faces))
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        passes.append({
            "pass": passno,
            "region_faces": len(selected),
            "split_edges": len(edges),
            "verts_before": before[0],
            "faces_before": before[1],
            "verts_after": len(bm.verts),
            "faces_after": len(bm.faces),
        })
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()

    me = obj.data
    pos = _positions(obj)
    lengths = []
    region_faces = 0
    for poly in me.polygons:
        c = np.array(poly.center[:], dtype=np.float64)
        n = np.array(poly.normal[:], dtype=np.float64)
        if _socket_face_score(c, n) <= 0.10:
            continue
        region_faces += 1
        ids = list(poly.vertices)
        for i, a in enumerate(ids):
            lengths.append(float(np.linalg.norm(pos[a] - pos[ids[(i + 1) % len(ids)]])))
    return {
        "passes": passes,
        "max_edge_target": float(max_edge),
        "region_faces_after": int(region_faces),
        "region_edge_max": max(lengths) if lengths else 0.0,
        "region_edge_p95": float(np.quantile(lengths, 0.95)) if lengths else 0.0,
    }


def _integrated_socket_envelope(u):
    """Relative height envelope of the continuous carved crescent, in metres.

    Unlike the abandoned additive heightfield this is a displacement amplitude
    on the plinth itself.  A modest baseline keeps the rail continuous through
    the deepest centre, while the circular component rises towards the sides
    where the lower edge of the disc climbs.  Both ends fade before the plinth
    perimeter so the result is a carved swelling rather than a protruding tusk.
    """
    u = np.asarray(u, dtype=np.float64)
    radius = 15.70
    centre_z = 23.90
    circle_z = centre_z - np.sqrt(np.maximum(radius * radius - u * u, 0.0))
    circular = np.minimum(1.02, np.maximum(0.0, circle_z - 8.16) * 0.58)
    along = _smoothstep(0.28, 1.15, u) * (1.0 - _smoothstep(7.25, 8.65, u))
    crest = np.minimum(1.28, 0.34 + circular)
    return crest * along


def _socket_weights(obj):
    data = _surface_data(obj)
    centres = data["centres"]
    normals = data["normals"]
    pos = data["pos"]
    poly_score = np.zeros(len(centres), dtype=np.float64)

    # Fracture polygons have already been made flat by the fracture pass.  Both
    # that shading tag and the geometric fracture score are used as exclusions;
    # the seating deformation must not erode the open split or its fresh chips.
    for pi, poly in enumerate(obj.data.polygons):
        if pi >= len(poly_score):
            break
        score = _socket_face_score(centres[pi], normals[pi])
        fracture = _fracture_face_score(centres[pi], normals[pi])
        score *= 1.0 - float(_smoothstep(0.06, 0.18, fracture))
        if not poly.use_smooth:
            score = 0.0
        poly_score[pi] = score

    acc = np.zeros(len(pos), dtype=np.float64)
    cnt = np.zeros(len(pos), dtype=np.float64)
    vnorm_acc = np.zeros_like(pos)
    for pi, ids in enumerate(data["poly_ids"]):
        if len(ids) == 0:
            continue
        np.add.at(acc, ids, poly_score[pi])
        np.add.at(cnt, ids, 1.0)
        area = float(obj.data.polygons[pi].area) if pi < len(obj.data.polygons) else 1.0
        np.add.at(vnorm_acc, ids, normals[pi] * max(area, 1e-6))
    weight = np.zeros(len(pos), dtype=np.float64)
    valid = cnt > 0
    weight[valid] = acc[valid] / cnt[valid]
    edges = _mesh_edges(obj.data)
    # Two soft diffusion steps bridge grid-valence discontinuities left by the
    # adaptive subdivision, while the narrow shoulder remains spatially defined.
    weight = np.clip(_diffuse_scalar(weight, edges, passes=2, amount=0.32), 0.0, 1.0)

    vnlen = np.linalg.norm(vnorm_acc, axis=1)
    vnorm = np.zeros_like(vnorm_acc)
    nvalid = vnlen > 1e-9
    vnorm[nvalid] = vnorm_acc[nvalid] / vnlen[nvalid, None]
    # Shared vertices on vertical step risers or split walls lose influence as
    # their averaged normal turns away from the bearing shoulder.
    weight *= _smoothstep(-0.02, 0.16, vnorm[:, 2])
    return data, poly_score, weight, vnorm


def _sculpt_integrated_socket(obj):
    """Raise continuous paired bearing cheeks out of the existing plinth mesh.

    This is the structural replacement for separate wedge/clamp meshes.  No new
    surface is inserted and no visibility seam can appear at a plinth crossing:
    the same vertices and polygons form lower course, shoulder, cheek and wear
    plateau.  Displacement follows the averaged surface normal, so the curved
    shoulder swells outward/upward naturally instead of being extruded as a
    vertical heightfield.  A shallow negative outer groove and low-amplitude
    deterministic wear prevent a machined rail profile.
    """
    data, poly_score, weight, vnorm = _socket_weights(obj)
    pos = data["pos"].copy()
    vx = pos[:, 0]
    vy = pos[:, 1]
    u = np.abs(vx)
    crest = _integrated_socket_envelope(u)

    centreline = 0.34 + 0.11 * np.sin(u * 0.43 + 5.1)
    halfthick = 4.20 - 0.22 * _smoothstep(8.4, 11.0, u)
    v = (vy - centreline) / np.maximum(halfthick, 0.1)
    av = np.abs(v)
    # A defined inner slope, narrow worn bearing crown and longer outer slope.
    # The transitions are deliberately tighter than in the first integrated
    # draft: enough resolution exists after socket refinement, so the arrises
    # can be read as carved stone instead of one soft inflated cushion.
    cheek = _smoothstep(0.72, 0.83, av) * (1.0 - _smoothstep(1.01, 1.12, av))
    edgefade = 1.0 - _smoothstep(1.18, 1.36, av)
    broad = 1.0 - _smoothstep(0.98, 1.30, av)
    weather = ((0.022 * np.sin(u * 2.05 + vy * 1.03 + 3.2) +
                0.014 * np.sin(u * 4.70 - vy * 1.49 + 1.1)) * cheek)
    field = crest * (0.07 * broad * (1.0 - cheek) + 0.92 * cheek) * edgefade
    field += weather * np.minimum(1.0, crest)
    # A shallow continuous compression immediately outside each cheek is the
    # carved equivalent of a shadow line.  It is still only centimetres deep on
    # a 40 m monument, but sufficient to separate crown and shoulder visually.
    groovemask = _smoothstep(1.08, 1.16, av) * (1.0 - _smoothstep(1.25, 1.36, av))
    field -= np.minimum(0.16, crest * 0.16) * groovemask

    # The orientation/location weight is a selection mask, not part of the art
    # shape.  Saturating its high-confidence interior prevents normal variation
    # on the curved shoulder from imprinting unintended lumps into the rail,
    # while the outer mask boundary remains soft and continuous.
    gate = _smoothstep(0.18, 0.55, weight)
    amp = field * gate
    pos += vnorm * amp[:, None]
    _write_positions(obj, pos)

    # The bearing crown and groove are worked stone, not the untouched smooth
    # plinth course.  Flatten only the small refined polygons in that band so
    # the arrises catch light as chiselled mineral facets.  Fracture polygons
    # were already flat before this stage and are not reclassified here.
    flat_socket_polys = 0
    for poly in obj.data.polygons:
        ids = list(poly.vertices)
        if len(ids) < 3 or not poly.use_smooth:
            continue
        centre = pos[ids].mean(axis=0)
        x, y, z = centre
        u = abs(float(x))
        centreline = 0.34 + 0.11 * math.sin(u * 0.43 + 5.1)
        halfthick = 4.20 - 0.22 * float(_smoothstep(8.4, 11.0, u))
        av = abs((float(y) - centreline) / max(halfthick, 0.1))
        n = np.array(poly.normal[:], dtype=np.float64)
        nz = float(n[2] / max(np.linalg.norm(n), 1e-9))
        if (0.28 < u < 8.7 and 0.60 < av < 1.38 and 5.15 < z < 9.4 and nz > 0.0):
            poly.use_smooth = False
            flat_socket_polys += 1
    obj.data.update()

    affected = np.abs(amp) > 0.025
    return {
        "mode": "integrated_plinth_sculpt",
        "affected_vertices": int(np.count_nonzero(affected)),
        "weight_max": float(weight.max()) if len(weight) else 0.0,
        "max_abs_displacement": float(np.abs(amp).max()) if len(amp) else 0.0,
        "mean_abs_displacement": float(np.abs(amp[affected]).mean()) if np.count_nonzero(affected) else 0.0,
        "flat_socket_polys": int(flat_socket_polys),
        "separate_socket_objects": 0,
    }


def _fracture_weights(obj):
    data = _surface_data(obj)
    centres = data["centres"]
    normals = data["normals"]
    an = np.abs(normals)
    denom = np.maximum(an.sum(axis=1), 1e-9)
    nxfrac = an[:, 0] / denom
    nzfrac = an[:, 2] / denom
    x = centres[:, 0]
    z = centres[:, 2]
    central = 1.0 - _smoothstep(4.10, 5.05, np.abs(x))
    xdominant = _smoothstep(0.18, 0.37, nxfrac)
    inner_core = (1.0 - _smoothstep(1.85, 2.85, np.abs(x))) * (1.0 - _smoothstep(0.54, 0.76, nzfrac))
    orientation = np.maximum(xdominant, inner_core)
    poly_score = _smoothstep(7.65, 9.05, z) * central * orientation

    pos = data["pos"]
    acc = np.zeros(len(pos), dtype=np.float64)
    cnt = np.zeros(len(pos), dtype=np.float64)
    for pi, ids in enumerate(data["poly_ids"]):
        if len(ids):
            np.add.at(acc, ids, poly_score[pi])
            np.add.at(cnt, ids, 1.0)
    weight = np.zeros(len(pos), dtype=np.float64)
    valid = cnt > 0
    weight[valid] = acc[valid] / cnt[valid]
    edges = _mesh_edges(obj.data)
    weight = np.clip(_diffuse_scalar(weight, edges, passes=1, amount=0.24), 0.0, 1.0)
    return data, poly_score, weight


def _sculpt_multiscale_fracture(obj, amplitude=0.56):
    """Displace the refined cleft walls with macro/medium/fine breakage.

    Positive relief moves away from the air wedge; negative, wedge-narrowing
    relief is capped.  The field combines irregular value-noise cells with
    narrow-blended shelf steps and a tightly bounded fine notch component, so
    it neither re-creates the old large origami planes nor closes the central
    void.  Connectivity is never changed by this stage.
    """
    data, poly_score, weight = _fracture_weights(obj)
    pos = data["pos"].copy()
    vx = pos[:, 0]
    vy = pos[:, 1]
    vz = pos[:, 2]
    side = np.where(vx < 0.0, -1.0, 1.0)

    # Broad, non-repeating undulation: this changes the silhouette of the crack
    # lips without becoming a simple sinusoidal corrugation.
    macro = (0.64 * _value_noise2(vy / 4.9 + side * 0.173, vz / 4.3, 6101) +
             0.36 * _value_noise2((vy + vz * 0.34) / 3.2, (vz - vy * 0.16) / 3.8, 6107))

    # Oblique irregular shelf bands.  Their height varies both vertically and
    # across the thickness of the disc; short transition ramps produce scarped
    # but connected fractured shelves rather than disconnected floating steps.
    shelf_coord = (vz / 1.28 +
                   0.22 * _value_noise2(vy / 2.7, vz / 2.9, 6113) +
                   0.06 * vy + side * 0.117)
    band = np.floor(shelf_coord)
    frac = shelf_coord - band
    ycell = np.floor(vy / 1.05 + 0.31 * _value_noise2(vy / 3.7, vz / 3.1, 6119) + side * 0.31)
    hcur = _hash2(band, ycell, 6121)
    hprev = _hash2(band - 1.0, ycell, 6121)
    blend_width = 0.075
    blend = np.clip(frac / blend_width, 0.0, 1.0)
    blend = blend * blend * (3.0 - 2.0 * blend)
    shelf01 = np.where(frac < blend_width, hprev * (1.0 - blend) + hcur * blend, hcur)
    shelf = shelf01 * 2.0 - 1.0

    medium = (0.58 * _value_noise2(vy / 1.22 + side * 0.41, vz / 1.08, 6131) +
              0.42 * _value_noise2((vy - vz * 0.23) / 0.72, (vz + vy * 0.18) / 0.78, 6137))
    fine = (0.66 * _value_noise2(vy / 0.245 + side * 0.77, vz / 0.225, 6143) +
            0.34 * _value_noise2((vy + vz) / 0.155, (vz - vy * 0.4) / 0.175, 6149))

    # Sparse small recesses.  They are recessive by sign and tightly bounded,
    # giving dark chipped notches in rendering rather than a noisy worm field.
    notch_seed = _value_noise2(vy / 0.33 + side * 0.29, vz / 0.29, 6157)
    notch = _smoothstep(0.47, 0.82, notch_seed)

    relief = (0.34 * macro + 0.48 * shelf + 0.28 * medium + 0.075 * fine)
    relief = np.clip(relief, -1.0, 1.0)
    inward_cap = np.where(relief < 0.0, 0.31, 1.0)
    zweight = _smoothstep(7.75, 9.05, vz)
    total_weight = weight * zweight
    dx = side * relief * inward_cap * float(amplitude) * total_weight
    # Fine notches recede outwards and therefore can only widen the void.
    dx += side * notch * 0.085 * total_weight

    # Small tangential components keep the relief from reading as an extruded
    # heightfield.  They are deliberately much smaller than the lateral cut.
    pos[:, 0] += dx
    pos[:, 1] += (0.038 * medium + 0.014 * fine) * total_weight
    pos[:, 2] += (0.030 * _value_noise2(vy / 0.91, vz / 1.17 + side * 0.23, 6163) +
                  0.010 * fine) * total_weight
    _write_positions(obj, pos)

    # The old model is globally smooth-shaded, which makes displaced rock look
    # like putty.  Only the high-confidence fracture/lip polygons become flat;
    # outer monolith faces and the plinth keep their calm monumental shading.
    flat_count = 0
    for pi, poly in enumerate(obj.data.polygons):
        make_flat = pi < len(poly_score) and poly_score[pi] > 0.20
        poly.use_smooth = not make_flat
        if make_flat:
            flat_count += 1
    obj.data.update()

    affected = total_weight > 0.05
    return {
        "affected_vertices": int(np.count_nonzero(affected)),
        "weight_max": float(total_weight.max()) if len(total_weight) else 0.0,
        "dx_abs_mean": float(np.abs(dx[affected]).mean()) if np.count_nonzero(affected) else 0.0,
        "max_abs_dx": float(np.abs(dx).max()) if len(dx) else 0.0,
        "amplitude": float(amplitude),
        "flat_fracture_polys": int(flat_count),
    }


# ---------------------------------------------------------------------------
# Eingebettete Splinter, Schuppen und kleine Bruchbrocken


def _orient_closed_mesh_outwards(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    try:
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(me)
    finally:
        bm.free()
    me.update()


def _project_generated_uvs(me, base_uv=(0.72, 0.10), scale=0.010, seed=0,
                           umin=0.68, umax=0.96, vmin=0.035, vmax=0.62):
    uv_layer = me.uv_layers.active or me.uv_layers.new(name="UVMap")
    bu, bv = base_uv
    bu += (seed % 5) * 0.017
    bv += ((seed // 5) % 3) * 0.021
    me.update()
    for poly in me.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if abs(n.z) >= max(abs(n.x), abs(n.y)):
                uv = (bu + (co.x + 13.0) * scale, bv + (co.y + 7.0) * scale)
            elif abs(n.y) >= abs(n.x):
                uv = (bu + (co.x + 13.0) * scale, bv + (co.z - 5.0) * scale * 0.7)
            else:
                uv = (bu + (co.y + 7.0) * scale, bv + (co.z - 5.0) * scale * 0.7)
            uv_layer.data[li].uv = (min(umax, max(umin, uv[0])), min(vmax, max(vmin, uv[1])))


def _valid_cleft_ray(hit, loc, normal, direction):
    if not hit:
        return False
    if abs(float(loc.x)) < 0.10 or float(loc.x) * direction < 0.0:
        return False
    # The first visible wall must face back into the empty wedge.  If the dot
    # product is positive the ray began inside stone and hit an interior/back face.
    return float(np.dot(np.array(normal[:], dtype=np.float64), np.array([direction, 0.0, 0.0]))) < -0.12


def _fragment_basis(normal, angle):
    n = np.array(normal, dtype=np.float64)
    ln = np.linalg.norm(n)
    if ln < 1e-9:
        n = np.array([1.0, 0.0, 0.0])
    else:
        n = n / ln
    up = np.array([0.0, 0.0, 1.0])
    t1 = up - n * float(np.dot(up, n))
    if np.linalg.norm(t1) < 1e-7:
        t1 = np.array([0.0, 1.0, 0.0])
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    t2 /= np.linalg.norm(t2)
    ca = math.cos(angle)
    sa = math.sin(angle)
    t1r = t1 * ca + t2 * sa
    t2r = -t1 * sa + t2 * ca
    return n, t1r, t2r


def _append_tri_prism(verts, faces, centre, n, t1, t2, width, height, protrude, embed, rng):
    """Append one irregular triangular splinter as a closed six-vertex prism."""
    base2 = [(-height * 0.52, -width * 0.52),
             (height * 0.50, -width * (0.30 + 0.16 * rng.random())),
             (-height * (0.08 + 0.18 * rng.random()), width * 0.52)]
    outer_scale = 0.40 + 0.24 * rng.random()
    shift1 = (rng.random() - 0.5) * height * 0.22
    shift2 = (rng.random() - 0.5) * width * 0.24
    ids = []
    for a, b in base2:
        jitter1 = (rng.random() - 0.5) * height * 0.07
        jitter2 = (rng.random() - 0.5) * width * 0.07
        p = centre - n * embed + t1 * (a + jitter1) + t2 * (b + jitter2)
        ids.append(len(verts))
        verts.append(tuple(p))
    for a, b in base2:
        p = (centre + n * protrude +
             t1 * (a * outer_scale + shift1 + (rng.random() - 0.5) * height * 0.08) +
             t2 * (b * outer_scale + shift2 + (rng.random() - 0.5) * width * 0.08))
        ids.append(len(verts))
        verts.append(tuple(p))
    v0, v1, v2, v3, v4, v5 = ids
    faces.extend([
        (v0, v2, v1),
        (v3, v4, v5),
        (v0, v1, v4, v3),
        (v1, v2, v5, v4),
        (v2, v0, v3, v5),
    ])


def _append_frustum_chip(verts, faces, centre, n, t1, t2, width, height, protrude, embed, rng):
    """Append a skewed eight-vertex chipped shelf/frustum."""
    hw = width * 0.5
    hh = height * 0.5
    base2 = [(-hh, -hw), (hh, -hw), (hh, hw), (-hh, hw)]
    outer_scale_x = 0.42 + 0.27 * rng.random()
    outer_scale_y = 0.50 + 0.25 * rng.random()
    shift1 = (rng.random() - 0.5) * height * 0.46
    shift2 = (rng.random() - 0.5) * width * 0.42
    ids = []
    for a, b in base2:
        p = (centre - n * embed +
             t1 * (a + (rng.random() - 0.5) * height * 0.09) +
             t2 * (b + (rng.random() - 0.5) * width * 0.09))
        ids.append(len(verts))
        verts.append(tuple(p))
    for a, b in base2:
        p = (centre + n * protrude +
             t1 * (a * outer_scale_x + shift1 + (rng.random() - 0.5) * height * 0.12) +
             t2 * (b * outer_scale_y + shift2 + (rng.random() - 0.5) * width * 0.12))
        ids.append(len(verts))
        verts.append(tuple(p))
    v = ids
    faces.extend([
        (v[0], v[3], v[2], v[1]),
        (v[4], v[5], v[6], v[7]),
        (v[0], v[1], v[5], v[4]),
        (v[1], v[2], v[6], v[5]),
        (v[2], v[3], v[7], v[6]),
        (v[3], v[0], v[4], v[7]),
    ])


def _make_fracture_fragments(main_obj, material, seed=9301, max_count=82):
    """Embedded multiscale splinters/chips along the open split.

    Every fragment is a closed manifold component.  Its rear face is embedded
    behind the ray-hit wall and only a bounded tip enters the air gap.  The
    measured local gap caps protrusion, so the central void remains continuous.
    """
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    rng = np.random.default_rng(seed)
    verts = []
    faces = []
    placed = 0
    valid_pairs = 0
    rejected = 0
    # Keep embedded chips off the lowest seating/contact band.  At z<10 m the
    # split disappears into the plinth shoulder; chips cast there read as a row
    # of teeth along the socket instead of fracture splintering.
    zrows = np.linspace(10.80, 37.15, 25)
    placements = []
    for zi, zz in enumerate(zrows):
        # One or two thickness positions per height row, with deterministic
        # jitter.  Both walls are considered, but many rows skip one side to
        # avoid a regular bead-like chain.
        for _ in range(2):
            yy = -3.35 + 7.75 * float(rng.random())
            hits = {}
            for direction in (-1.0, 1.0):
                origin = np.array([0.0, yy, zz + (rng.random() - 0.5) * 0.34], dtype=np.float64)
                hit, loc, normal, face_index, obj, matrix = bpy.context.scene.ray_cast(
                    deps, origin, np.array([direction, 0.0, 0.0]), distance=18.0)
                if _valid_cleft_ray(hit, loc, normal, direction):
                    hits[direction] = (np.array(loc[:], dtype=np.float64), np.array(normal[:], dtype=np.float64))
            if len(hits) != 2:
                rejected += 1
                continue
            gap = float(hits[1.0][0][0] - hits[-1.0][0][0])
            if not (0.68 < gap < 10.5):
                rejected += 1
                continue
            valid_pairs += 1
            for direction in (-1.0, 1.0):
                if rng.random() < 0.30:
                    continue
                placements.append((hits[direction][0], hits[direction][1], gap, zi))

    rng.shuffle(placements)
    # Retain broad z coverage by accepting no more than four fragments per row.
    per_row = {}
    chosen = []
    for item in placements:
        row = item[3]
        if per_row.get(row, 0) >= 4:
            continue
        chosen.append(item)
        per_row[row] = per_row.get(row, 0) + 1
        if len(chosen) >= max_count:
            break

    for loc, normal, gap, row in chosen:
        angle = (float(rng.random()) - 0.5) * math.radians(28.0)
        n, t1, t2 = _fragment_basis(normal, angle)
        # Most accreted detail is triangular splintering; only a minority is
        # chunked shelf material because the displaced wall already carries the
        # broader shelf structure.  This avoids a chain of cube-like blocks.
        shelf = rng.random() < 0.28
        if shelf:
            width = 0.46 + 0.60 * float(rng.random())
            height = 0.16 + 0.34 * float(rng.random())
        else:
            width = 0.18 + 0.40 * float(rng.random())
            height = 0.30 + 0.76 * float(rng.random())
        protrude = min(0.095 + 0.135 * float(rng.random()), 0.18 * gap, 0.255)
        embed = 0.085 + 0.075 * float(rng.random())
        centre = loc + n * 0.012
        if shelf:
            _append_frustum_chip(verts, faces, centre, n, t1, t2, width, height, protrude, embed, rng)
        else:
            _append_tri_prism(verts, faces, centre, n, t1, t2, width, height, protrude, embed, rng)
        placed += 1

    if not verts:
        return None, {"components": 0, "valid_pairs": valid_pairs, "rejected": rejected}
    me = bpy.data.meshes.new("split_multiscale_fragments")
    me.from_pydata(verts, [], faces)
    me.update()
    _orient_closed_mesh_outwards(me)
    _project_generated_uvs(me, base_uv=(0.72, 0.09), scale=0.010, seed=seed,
                           umin=0.68, umax=0.965, vmin=0.035, vmax=0.64)
    for poly in me.polygons:
        poly.use_smooth = False
    if material is not None:
        me.materials.append(material)
    obj = bpy.data.objects.new("split_multiscale_fragments", me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, {
        "components": int(placed),
        "valid_pairs": int(valid_pairs),
        "rejected_pairs": int(rejected),
        "verts": len(me.vertices),
        "faces": len(me.polygons),
    }


# ---------------------------------------------------------------------------
# Mineralische Albedo- und shaderseitige Oberfläche


def _noise_layer(shape, cell, blur, seed):
    h, w = shape
    rng = np.random.default_rng(seed)
    cell = max(1, int(cell))
    sh = int(math.ceil(h / float(cell)))
    sw = int(math.ceil(w / float(cell)))
    small = rng.standard_normal((sh, sw), dtype=np.float32)
    if cell > 1:
        rep = np.repeat(np.repeat(small, cell, axis=0), cell, axis=1)[:h, :w]
    else:
        rep = small[:h, :w]
    if int(blur) > 0:
        rep = vrmeshy._box_blur(rep, int(blur))
    rep = rep - float(rep.mean())
    rep = rep / max(float(rep.std()), 1e-6)
    return rep.astype(np.float32, copy=False)


def regrain_mineral_basecolor(objs, seed=4217):
    """Mildly de-worm the Meshy albedo and restore isotropic limestone grain.

    Unlike R5 this is not a near-total pore erase.  Only strong black pinholes
    are inpainted; moderate original luminance detail survives and is combined
    with low-amplitude granular replacement noise.  The intent is matte mineral
    tooth, not featureless putty and not dense reptilian crackle.
    """
    metrics = {"images": 0, "hf_before": [], "hf_after": [], "strong_pit_pixels": 0}
    made = {}
    for node in vrmeshfix._basecolor_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = vrmeshfix._image_pixels(img)
        rgb = px[..., :3]
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        low = np.empty_like(rgb)
        for ch in range(3):
            low[..., ch] = vrmeshy._box_blur(rgb[..., ch], 5)
        low_lum = low[..., 0] * 0.2126 + low[..., 1] * 0.7152 + low[..., 2] * 0.0722
        high = rgb - low
        high_lum = lum - low_lum
        hf_before = float(high_lum.std())

        # Keep enough signed micro-contrast for stone.  Dark linear crackle is
        # reduced more than light mineral sparkle; chroma speckle is reduced
        # because coloured pore noise was a major reptile-like cue.
        keep_lum = np.where(high_lum < 0.0, 0.18, 0.30).astype(np.float32)
        chroma = high - high_lum[..., None]
        filtered = low + high_lum[..., None] * keep_lum[..., None] + chroma * 0.16

        # Only strong narrow black pits are pulled back.  The threshold is far
        # above R5's aggressive pore erase, leaving subtle natural pores intact.
        lum_f = filtered[..., 0] * 0.2126 + filtered[..., 1] * 0.7152 + filtered[..., 2] * 0.0722
        support = vrmeshy._box_blur(lum_f, 5)
        pit = support - lum_f
        pit_w = np.clip((pit - 0.034) / 0.058, 0.0, 1.0) * 0.58
        metrics["strong_pit_pixels"] += int(np.count_nonzero(pit_w > 0.35))
        filtered = filtered * (1.0 - pit_w[..., None]) + low * pit_w[..., None]

        # Isotropic granular replacement: three rounded noise octaves, spatially
        # varying in strength.  No elongated stripe/crack coordinate is used.
        h, w = lum.shape
        grain = (0.42 * _noise_layer((h, w), 3, 1, seed + 11) +
                 0.38 * _noise_layer((h, w), 9, 2, seed + 23) +
                 0.20 * _noise_layer((h, w), 31, 5, seed + 37))
        spatial = 0.76 + 0.28 * _noise_layer((h, w), 181, 19, seed + 51)
        spatial = np.clip(spatial, 0.52, 1.10)
        grain = grain / max(float(grain.std()), 1e-6)
        signed_grain = np.where(grain < 0.0, grain * 0.66, grain * 0.88)
        mod = 1.0 + signed_grain * spatial * 0.022
        out = np.clip(filtered * mod[..., None], 0.0, 1.0)

        out_lum = out[..., 0] * 0.2126 + out[..., 1] * 0.7152 + out[..., 2] * 0.0722
        out_low = vrmeshy._box_blur(out_lum, 3)
        metrics["hf_before"].append(hf_before)
        metrics["hf_after"].append(float((out_lum - out_low).std()))
        alpha = px[..., 3:].copy()
        made[img] = vrmeshfix._replace_image(img, np.concatenate([out, alpha], axis=-1), "_mineral_r6")
        metrics["images"] += 1
        # Release large temporaries promptly on the contention-prone build host.
        del px, low, high, high_lum, chroma, filtered, lum_f, support, pit, pit_w, grain, spatial, mod, out, alpha
    vrmeshfix._swap_images(objs, made)
    if metrics["hf_before"]:
        metrics["hf_reduction"] = float(1.0 - np.mean(metrics["hf_after"]) / max(np.mean(metrics["hf_before"]), 1e-9))
    return metrics


def _set_node_input(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def install_mineral_shader(objs):
    """Replace reptile-normal detail with multi-scale matte limestone shading.

    The Meshy normal map remains unused.  Object-space 3D noise is isotropic,
    has a real metre scale on all UV islands and cannot form UV-space worms.
    AO is only a subtle albedo multiplier: actual cleft shadowing still comes
    from the new geometry and Cycles lighting.
    """
    changed = 0
    seen = set()
    for obj in [o for o in objs if o and o.type == "MESH"]:
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes or not mat.node_tree or mat in seen:
                continue
            seen.add(mat)
            nt = mat.node_tree
            nodes = nt.nodes
            links = nt.links
            bsdf = nodes.get("Principled BSDF")
            if bsdf is None:
                continue
            base_socket = bsdf.inputs["Base Color"]
            base_source = base_socket.links[0].from_socket if base_socket.is_linked else None
            base_default = tuple(base_socket.default_value)
            for socket_name in ("Base Color", "Normal", "Roughness", "Metallic"):
                sock = bsdf.inputs[socket_name]
                for link in list(sock.links):
                    links.remove(link)
            bsdf.inputs["Metallic"].default_value = 0.0
            _set_node_input(bsdf, "Specular IOR Level", 0.27)
            _set_node_input(bsdf, "Coat Weight", 0.0)

            tex = nodes.new("ShaderNodeTexCoord")
            tex.name = "R6 object-space mineral coordinates"
            noise_mid = nodes.new("ShaderNodeTexNoise")
            noise_mid.name = "R6 mineral mid grain"
            noise_mid.noise_dimensions = "3D"
            _set_node_input(noise_mid, "Scale", 8.5)
            _set_node_input(noise_mid, "Detail", 3.0)
            _set_node_input(noise_mid, "Roughness", 0.68)
            _set_node_input(noise_mid, "Distortion", 0.10)
            noise_fine = nodes.new("ShaderNodeTexNoise")
            noise_fine.name = "R6 mineral fine grain"
            noise_fine.noise_dimensions = "3D"
            _set_node_input(noise_fine, "Scale", 47.0)
            _set_node_input(noise_fine, "Detail", 2.1)
            _set_node_input(noise_fine, "Roughness", 0.74)
            links.new(tex.outputs["Object"], noise_mid.inputs["Vector"])
            links.new(tex.outputs["Object"], noise_fine.inputs["Vector"])

            height_mix = nodes.new("ShaderNodeMixRGB")
            height_mix.name = "R6 layered mineral height"
            height_mix.blend_type = "MIX"
            height_mix.inputs["Fac"].default_value = 0.46
            links.new(noise_mid.outputs["Fac"], height_mix.inputs["Color1"])
            links.new(noise_fine.outputs["Fac"], height_mix.inputs["Color2"])

            bump = nodes.new("ShaderNodeBump")
            bump.name = "R6 matte stone microbump"
            bump.inputs["Strength"].default_value = 0.30
            bump.inputs["Distance"].default_value = 0.048
            links.new(height_mix.outputs["Color"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

            # Very low-frequency value variation gives mineral patches without
            # changing the established ivory/grey-beige palette.
            noise_broad = nodes.new("ShaderNodeTexNoise")
            noise_broad.name = "R6 broad mineral patches"
            noise_broad.noise_dimensions = "3D"
            _set_node_input(noise_broad, "Scale", 2.35)
            _set_node_input(noise_broad, "Detail", 2.0)
            _set_node_input(noise_broad, "Roughness", 0.70)
            links.new(tex.outputs["Object"], noise_broad.inputs["Vector"])
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.name = "R6 mineral albedo modulation"
            cr = ramp.color_ramp
            cr.elements[0].position = 0.18
            cr.elements[0].color = (0.955, 0.965, 0.985, 1.0)
            cr.elements[1].position = 0.82
            cr.elements[1].color = (1.035, 1.025, 1.0, 1.0)
            links.new(noise_broad.outputs["Fac"], ramp.inputs["Fac"])

            mineral_mix = nodes.new("ShaderNodeMixRGB")
            mineral_mix.name = "R6 mineral albedo mix"
            mineral_mix.blend_type = "MULTIPLY"
            mineral_mix.inputs["Fac"].default_value = 0.34
            if base_source is not None:
                links.new(base_source, mineral_mix.inputs["Color1"])
            else:
                mineral_mix.inputs["Color1"].default_value = base_default
            links.new(ramp.outputs["Color"], mineral_mix.inputs["Color2"])

            # Recess weathering: bounded AO darkening, strongest in the new
            # fracture shelves, socket overlap and chip undersides.
            ao = nodes.new("ShaderNodeAmbientOcclusion")
            ao.name = "R6 crevice weathering AO"
            _set_node_input(ao, "Distance", 0.72)
            ao_ramp = nodes.new("ShaderNodeValToRGB")
            ao_ramp.name = "R6 crevice weathering curve"
            acr = ao_ramp.color_ramp
            acr.elements[0].position = 0.0
            acr.elements[0].color = (0.74, 0.75, 0.75, 1.0)
            acr.elements[1].position = 0.72
            acr.elements[1].color = (1.0, 1.0, 1.0, 1.0)
            links.new(ao.outputs["AO"], ao_ramp.inputs["Fac"])
            ao_mix = nodes.new("ShaderNodeMixRGB")
            ao_mix.name = "R6 recessed weathering mix"
            ao_mix.blend_type = "MULTIPLY"
            ao_mix.inputs["Fac"].default_value = 0.31
            links.new(mineral_mix.outputs["Color"], ao_mix.inputs["Color1"])
            links.new(ao_ramp.outputs["Color"], ao_mix.inputs["Color2"])
            links.new(ao_mix.outputs["Color"], bsdf.inputs["Base Color"])

            rough_ramp = nodes.new("ShaderNodeValToRGB")
            rough_ramp.name = "R6 mineral roughness variation"
            rr = rough_ramp.color_ramp
            rr.elements[0].color = (0.72, 0.72, 0.72, 1.0)
            rr.elements[1].color = (0.91, 0.91, 0.91, 1.0)
            links.new(height_mix.outputs["Color"], rough_ramp.inputs["Fac"])
            links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])
            changed += 1
    return {"materials": changed, "normal_mode": "object-space granular bump", "ao_weathering": True}


# ---------------------------------------------------------------------------
# Validierungsmessung der offenen Fuge vor dem Einsetzen der Splinter


def _measure_open_split(obj):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    rows = []
    for zz in (9.0, 12.0, 15.0, 18.0, 21.0, 24.0, 27.0, 30.0, 33.0, 36.0):
        for yy in (-2.2, -1.0, 1.0, 2.2):
            origin = np.array([0.0, yy, zz], dtype=np.float64)
            hits = {}
            for direction in (-1.0, 1.0):
                hit, loc, normal, face_index, hit_obj, matrix = bpy.context.scene.ray_cast(
                    deps, origin, np.array([direction, 0.0, 0.0]), distance=18.0)
                if hit:
                    hits[direction] = float(loc.x)
            if len(hits) == 2:
                rows.append({"z": zz, "y": yy, "gap": hits[1.0] - hits[-1.0]})
    if not rows:
        return {"count": 0}
    gaps = [r["gap"] for r in rows]
    return {
        "count": len(rows),
        "min": float(min(gaps)),
        "max": float(max(gaps)),
        "mean": float(sum(gaps) / len(gaps)),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Build


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=0.0)

    vrmeshy.clamp_material(objs, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=1.5)

    main = max((o for o in objs if o.type == "MESH"), key=lambda o: len(o.data.vertices), default=None)
    refine_info = {}
    socket_refine_info = {}
    fracture_info = {}
    fragment_info = {"components": 0}
    socket_info = {"mode": "not_run"}
    split_info = {"count": 0}
    extra_objs = []
    if main is not None:
        refine_info = _refine_fracture_mesh(main, max_edge=0.28)
        socket_refine_info = _refine_socket_mesh(main, max_edge=0.32)
        fracture_info = _sculpt_multiscale_fracture(main, amplitude=0.56)
        socket_info = _sculpt_integrated_socket(main)
        split_info = _measure_open_split(main)
        material = main.data.materials[0] if main.data.materials else None
        fragments, fragment_info = _make_fracture_fragments(main, material)
        if fragments is not None:
            extra_objs.append(fragments)
        objs = list(objs) + extra_objs

    # Mild texture-space mineral restoration plus object-space granular bump.
    # The broad Meshy palette is intentionally retained; no heavy global colour
    # flattening or glossy normal smoothing is reintroduced.
    regrain_info = regrain_mineral_basecolor(objs)
    shader_info = install_mineral_shader(objs)

    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

    scene = bpy.context.scene
    scene["vr_review_figure"] = (7.0, 12.2, 0.0)
    # Upper close-up looks slightly into the open wedge rather than perpendicular
    # to one outer face.  Base close-up frames both saddle cheeks and the contact.
    scene["vr_closeup_upper"] = (0.0, 0.35, 24.0, 64.0, 7.0, 27.0)
    scene["vr_closeup_base"] = (0.0, 0.15, 8.2, 213.0, 18.0, 28.0)

    print("VR_R6_REFINE", refine_info, flush=True)
    print("VR_R6_SOCKET_REFINE", socket_refine_info, flush=True)
    print("VR_R6_FRACTURE", fracture_info, flush=True)
    print("VR_R6_SPLIT_PRE_DETAIL", split_info, flush=True)
    print("VR_R6_FRAGMENTS", fragment_info, flush=True)
    print("VR_R6_SOCKET", socket_info, flush=True)
    print("VR_R6_REGRAIN", regrain_info, flush=True)
    print("VR_R6_SHADER", shader_info, flush=True)

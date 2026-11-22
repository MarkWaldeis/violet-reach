#!/usr/bin/env python3
"""Rundum-Prüfung eines Meshy-Rohmodells (GRAFIK_PLAN.md 7.4).

    python tools/meshy/inspect_raw.py <raw.glb> --out <model_qa_dir> --brief <brief.md>
                                      [--expect-size L,W,H] [--name <label>]
    python tools/meshy/inspect_raw.py compare <out.jpg> <model_qa_dir> [<model_qa_dir> ...]
                                      [--labels "a|b|c"]

Ablauf (ein Aufruf, zwei Stufen):
  1. Diese Datei startet Blender headless (`-b --factory-startup --python inspect_raw.py -- --stage blender …`).
     Die Blender-Stufe importiert das GLB, misst (nichts wird gespeichert oder normiert) und rendert die
     Einzelansichten nach <out>/panels/*.png. Messwerte -> <out>/measure.json.
  2. Die Python-Stufe (Pillow) prüft die Renderings (abgeschnitten? schwarz?), setzt die Flags,
     baut <out>/sheet.jpg (ca. 2400x1500) und schreibt <out>/qa.json.

Das Modell wird NUR für das Blatt auf die Zielhöhe aus --expect-size skaliert (Maßfigur 1,8 m).
Alle geometrischen Messwerte in qa.json sind in Meshy-Einheiten bzw. als Verhältnisse angegeben.

compare: legt die 3-m-Nahansichten (texturiert und Drahtgitter) mehrerer model_qa-Ordner nebeneinander.

Umgebung: VR_BLENDER überschreibt den Blender-Pfad.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

BLENDER_DEFAULT = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"

PANEL = (505, 440)          # Endgröße einer Kachel im Blatt
PANEL_RENDER_SCALE = 2      # texturierte Kacheln doppelt rendern, dann verkleinern
CLOSE = (1600, 1200)        # 3-m-Nahansicht (für compare.jpg)
FIGURE_COLOR = (0.85, 0.32, 0.08)

# Schwellen für die Flags. Werden 1:1 in qa.json ("thresholds") übernommen.
THRESHOLDS = {
    "flat_disc_min_depth_ratio": 0.35,
    "flat_disc_note": "Tiefe/Breite (orientierte Box, Breite = längere waagrechte Achse) < 0.35; erwartet der "
                      "Brief selbst ein dünneres Objekt (Mauer), gilt 0.6 x erwartetes Tiefe/Breite.",
    "aspect_tolerance_factor": 1.30,
    "aspect_note": "Tiefe/Breite und Höhe/Breite gemessen vs. --expect-size; Flag, wenn ein Verhältnis um mehr "
                   "als Faktor 1.30 abweicht.",
    "loose_parts_max": 3,
    "loose_parts_min_tris": 12,
    "largest_part_min_share": 0.995,
    "loose_parts_note": "Teile = verbundene Komponenten nach Verschweißen gleicher Positionen. Flag, wenn mehr als "
                        "3 Teile mit >= 12 Dreiecken existieren oder das größte Teil < 99.5 % der Dreiecke hat.",
    "holes_max_boundary_edges": 0,
    "holes_note": "Randkanten (Kante an genau einem Dreieck) nach Verschweißen; jede offene Kante zählt.",
    "non_manifold_max_edges": 0,
    "baked_light_top_bottom_max": 1.45,
    "baked_light_sides_max": 1.30,
    "baked_light_min_group_area_share": 0.03,
    "baked_light_note": "Mittlere lineare Luminanz der base_color-Texel, flächengewichtet je Normalengruppe "
                        "(oben/unten/+X/-X/+Y/-Y im orientierten Rahmen, Zuordnung zur nächsten Achse, cos >= 0.5). "
                        "Gruppen mit < 3 % der Fläche werden nicht bewertet.",
    "required_maps": ["base_color", "normal", "roughness"],
    "min_texture_size": 2048,
    "tri_target_tolerance": 1.10,
}


# ----------------------------------------------------------------------------------------------
# Blender-Stufe
# ----------------------------------------------------------------------------------------------

def bl_main(argv):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    ap = argparse.ArgumentParser()
    ap.add_argument("--stage")
    ap.add_argument("--glb", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--expect", default="")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(os.path.join(a.work, "panels"), exist_ok=True)
    timing = {}
    t0 = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=a.glb)
    timing["import_s"] = round(time.time() - t0, 2)
    t1 = time.time()
    meshes = [o for o in scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("keine Meshes im GLB")

    # ---------- Geometrie sammeln (Weltkoordinaten; bound_box wird nicht benutzt) ----------
    V, T, TL, TM, UV, E = [], [], [], [], [], []
    mats = []
    voff = loff = 0
    n_polys = n_quads = n_ngons = 0
    has_uv = True
    for ob in meshes:
        me = ob.data
        me.calc_loop_triangles()
        nv, nl, nt = len(me.vertices), len(me.loops), len(me.loop_triangles)
        co = np.empty(nv * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3).astype(np.float64)
        M = np.array(ob.matrix_world)
        V.append(co @ M[:3, :3].T + M[:3, 3])
        tv = np.empty(nt * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", tv)
        tl = np.empty(nt * 3, np.int32)
        me.loop_triangles.foreach_get("loops", tl)
        tm = np.empty(nt, np.int32)
        me.loop_triangles.foreach_get("material_index", tm)
        T.append(tv.reshape(-1, 3) + voff)
        TL.append(tl.reshape(-1, 3) + loff)
        slot_map = []
        for m in me.materials:
            if m not in mats:
                mats.append(m)
            slot_map.append(mats.index(m))
        slot_map = np.array(slot_map or [-1], np.int64)
        TM.append(slot_map[np.clip(tm, 0, len(slot_map) - 1)])
        uvl = me.uv_layers.active
        if uvl is not None:
            uv = np.empty(nl * 2, np.float32)
            uvl.data.foreach_get("uv", uv)
            UV.append(uv.reshape(-1, 2).astype(np.float64))
        else:
            has_uv = False
            UV.append(np.full((nl, 2), np.nan))
        ev = np.empty(len(me.edges) * 2, np.int32)
        me.edges.foreach_get("vertices", ev)
        E.append(ev.reshape(-1, 2) + voff)
        lt = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("loop_total", lt)
        n_polys += len(lt)
        n_quads += int((lt == 4).sum())
        n_ngons += int((lt > 4).sum())
        voff += nv
        loff += nl
    V = np.concatenate(V)
    T = np.concatenate(T)
    TL = np.concatenate(TL)
    TM = np.concatenate(TM)
    UV = np.concatenate(UV)

    vmin, vmax = V.min(0), V.max(0)
    ext = vmax - vmin
    diag = float(np.linalg.norm(ext))
    H = float(ext[2])

    # ---------- Verschweißen gleicher Positionen (glTF trennt Vertices an UV-Nähten) ----------
    q = np.round((V - vmin) / (diag * 1e-6)).astype(np.int64)
    key = (q[:, 0] << 42) | (q[:, 1] << 21) | q[:, 2]
    uniq, first, weld = np.unique(key, return_index=True, return_inverse=True)
    weld = weld.ravel()
    Nw = len(uniq)
    Vw = V[first]
    TW = weld[T]

    p0, p1, p2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0)
    a2 = np.linalg.norm(cr, axis=1)
    area = 0.5 * a2
    nrm = cr / np.maximum(a2, 1e-30)[:, None]
    degen = ((TW[:, 0] == TW[:, 1]) | (TW[:, 1] == TW[:, 2]) | (TW[:, 0] == TW[:, 2])
             | (area < 1e-10 * diag * diag))
    good = ~degen
    tw = TW[good]

    e = np.concatenate([tw[:, [0, 1]], tw[:, [1, 2]], tw[:, [2, 0]]])
    e.sort(axis=1)
    ekey = e[:, 0].astype(np.int64) * Nw + e[:, 1]
    uk, cnt = np.unique(ekey, return_counts=True)
    ea, eb = uk // Nw, uk % Nw
    bmask = cnt == 1
    nmmask = cnt > 2

    def cc_labels(n, ia, ib):
        lab = np.arange(n, dtype=np.int64)
        if len(ia) == 0:
            return lab
        for _ in range(10000):
            la, lb = lab[ia], lab[ib]
            m = np.minimum(la, lb)
            new = lab.copy()
            np.minimum.at(new, la, m)
            np.minimum.at(new, lb, m)
            while True:
                nn = new[new]
                if np.array_equal(nn, new):
                    break
                new = nn
            if np.array_equal(new, lab):
                break
            lab = new
        return lab

    # Löcher: Zahl der zusammenhängenden Randkanten-Züge
    bverts = np.unique(np.concatenate([ea[bmask], eb[bmask]])) if bmask.any() else np.zeros(0, np.int64)
    if len(bverts):
        remap = np.full(Nw, -1, np.int64)
        remap[bverts] = np.arange(len(bverts))
        bl = cc_labels(len(bverts), remap[ea[bmask]], remap[eb[bmask]])
        boundary_loops = int(len(np.unique(bl)))
        # Länge des größten Randzugs relativ zur Diagonale
        blen = np.linalg.norm(Vw[ea[bmask]] - Vw[eb[bmask]], axis=1)
        loop_of_edge = bl[remap[ea[bmask]]]
        lu, linv = np.unique(loop_of_edge, return_inverse=True)
        linv = linv.ravel()
        lens = np.bincount(linv, weights=blen)
        largest_hole_rel = float(lens.max() / diag)
        mid = (Vw[ea[bmask]] + Vw[eb[bmask]]) / 2
        ecount = np.bincount(linv)
        holes = []
        for li in np.argsort(-lens)[:10]:
            ctr = mid[linv == li].mean(0)
            holes.append({"edges": int(ecount[li]), "perimeter_rel_diag": round(float(lens[li] / diag), 4),
                          "center_rel_bbox": [round(float(x), 3) for x in (ctr - vmin) / np.maximum(ext, 1e-12)]})
    else:
        boundary_loops = 0
        largest_hole_rel = 0.0
        holes = []

    # Lose Teile
    lab = cc_labels(Nw, ea, eb)
    comp_tri = lab[tw[:, 0]]
    cu, comp_idx = np.unique(comp_tri, return_inverse=True)
    comp_idx = comp_idx.ravel()
    ncomp = len(cu)
    ctris = np.bincount(comp_idx, minlength=ncomp)
    pz = np.stack([p0[good, 2], p1[good, 2], p2[good, 2]], 1)
    cmin = np.full((ncomp, 3), np.inf)
    cmax = np.full((ncomp, 3), -np.inf)
    for k in range(3):
        coords = np.stack([p0[good, k], p1[good, k], p2[good, k]], 1)
        np.minimum.at(cmin[:, k], comp_idx, coords.min(1))
        np.maximum.at(cmax[:, k], comp_idx, coords.max(1))
    del pz
    order = np.argsort(-ctris)
    total_good = int(good.sum())
    parts = []
    main = order[0]
    for ci in order[:15]:
        inside = bool(np.all(cmin[ci] >= cmin[main] - 1e-9) and np.all(cmax[ci] <= cmax[main] + 1e-9))
        parts.append({
            "tris": int(ctris[ci]),
            "share": round(float(ctris[ci] / total_good), 5),
            "z_min_rel": round(float((cmin[ci, 2] - vmin[2]) / max(H, 1e-12)), 4),
            "size_rel": [round(float(v), 4) for v in (cmax[ci] - cmin[ci]) / diag],
            "inside_main_bbox": inside,
        })
    floating = [p for p in parts[1:] if p["z_min_rel"] > 0.03 and p["tris"] >= THRESHOLDS["loose_parts_min_tris"]]

    # ---------- orientierte waagrechte Box (kleinste Rechteckfläche) ----------
    rng = np.random.default_rng(1)
    xy = Vw[:, :2] if Nw <= 200000 else Vw[rng.choice(Nw, 200000, replace=False), :2]

    def rect(ang):
        c, s = math.cos(ang), math.sin(ang)
        u = xy[:, 0] * c + xy[:, 1] * s
        v = -xy[:, 0] * s + xy[:, 1] * c
        return (u.max() - u.min()) * (v.max() - v.min()), u, v

    angs = np.radians(np.arange(0.0, 90.0, 0.5))
    best = min(angs, key=lambda t: rect(t)[0])
    fine = best + np.radians(np.arange(-0.5, 0.5, 0.02))
    best = float(min(fine, key=lambda t: rect(t)[0]))
    _, u, v = rect(best)
    ru, rv = float(u.max() - u.min()), float(v.max() - v.min())
    uc, vc = float(u.max() + u.min()) / 2, float(v.max() + v.min()) / 2
    c, s = math.cos(best), math.sin(best)
    cx, cy = uc * c - vc * s, uc * s + vc * c
    if ru >= rv:
        yaw, Lm, Dm = best, ru, rv
    else:
        yaw, Lm, Dm = best + math.pi / 2, rv, ru
    yaw = (yaw + math.pi / 2) % math.pi - math.pi / 2   # Längsachse, -90..90°

    # ---------- Normalengruppen im orientierten Rahmen ----------
    cyw, syw = math.cos(yaw), math.sin(yaw)
    nx = nrm[:, 0] * cyw + nrm[:, 1] * syw
    ny = -nrm[:, 0] * syw + nrm[:, 1] * cyw
    nz = nrm[:, 2]
    axes = np.stack([nz, -nz, nx, -nx, ny, -ny], 1)
    gname = ["top", "bottom", "+X", "-X", "+Y", "-Y"]
    gi = axes.argmax(1)
    gok = (axes.max(1) >= 0.5) & good

    # ---------- Material / Texturen ----------
    def trace(sock, depth=0):
        if sock is None or not sock.is_linked or depth > 10:
            return None, None
        link = sock.links[0]
        node, out = link.from_node, link.from_socket.name
        if node.type == "TEX_IMAGE":
            return node, ("A" if out == "Alpha" else "RGB")
        if node.type in ("SEPARATE_COLOR", "SEPRGB", "SEPARATE_RGB"):
            n, _ = trace(node.inputs[0], depth + 1)
            return n, {"Red": "R", "Green": "G", "Blue": "B"}.get(out, out)
        for inp in node.inputs:
            if inp.is_linked:
                n, ch = trace(inp, depth + 1)
                if n is not None:
                    return n, ch
        return None, None

    mat_info = []
    for m in mats:
        info = {"name": m.name if m else None, "maps": {}}
        if m and m.node_tree:
            bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is not None:
                for role, sock in (("base_color", "Base Color"), ("roughness", "Roughness"),
                                   ("metallic", "Metallic"), ("normal", "Normal"), ("alpha", "Alpha"),
                                   ("emission", "Emission Color")):
                    node, ch = trace(bsdf.inputs.get(sock))
                    if node is not None and node.image is not None:
                        info["maps"][role] = {"image": node.image.name, "channel": ch,
                                              "size": list(node.image.size),
                                              "colorspace": node.image.colorspace_settings.name}
                        info.setdefault("_nodes", {})[role] = node
            for n in m.node_tree.nodes:   # glTF-Occlusion steckt in einer Gruppe
                if n.type == "GROUP" and n.node_tree and "glTF" in n.node_tree.name:
                    occ = n.inputs.get("Occlusion")
                    node, ch = trace(occ)
                    if node is not None and node.image is not None:
                        info["maps"]["occlusion"] = {"image": node.image.name, "channel": ch,
                                                     "size": list(node.image.size)}
        mat_info.append(info)

    img_cache = {}

    def img_np(im):
        if im.name not in img_cache:
            w, h = im.size
            px = np.empty(w * h * 4, np.float32)
            im.pixels.foreach_get(px)
            img_cache[im.name] = px.reshape(h, w, 4)
        return img_cache[im.name]

    bary = np.array([[1 / 3, 1 / 3, 1 / 3], [2 / 3, 1 / 6, 1 / 6], [1 / 6, 2 / 3, 1 / 6], [1 / 6, 1 / 6, 2 / 3]])

    def srgb_to_lin(x):
        return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

    ntri = len(T)
    Ytri = np.full(ntri, np.nan)
    RGBtri = np.full((ntri, 3), np.nan)
    HFtri = np.full(ntri, np.nan)
    HF2tri = np.full(ntri, np.nan)
    ROUGHtri = np.full(ntri, np.nan)
    METALtri = np.full(ntri, np.nan)
    uvarea = np.zeros(ntri)
    base_size = None
    tex_ok = has_uv and not np.isnan(UV).any()
    if tex_ok:
        uvt = UV[TL]   # (ntri,3,2)
        uvarea = 0.5 * np.abs((uvt[:, 1, 0] - uvt[:, 0, 0]) * (uvt[:, 2, 1] - uvt[:, 0, 1])
                              - (uvt[:, 2, 0] - uvt[:, 0, 0]) * (uvt[:, 1, 1] - uvt[:, 0, 1]))
        suv = np.einsum("sk,tkc->tsc", bary, uvt)   # (ntri,4,2)

        def lookup(arr, sel):
            h, w = arr.shape[:2]
            uu = np.mod(suv[sel, :, 0], 1.0)
            vv = np.mod(suv[sel, :, 1], 1.0)
            ix = np.clip((uu * w).astype(np.int64), 0, w - 1)
            iy = np.clip((vv * h).astype(np.int64), 0, h - 1)
            return arr[iy, ix]

        for mi, info in enumerate(mat_info):
            sel = TM == mi
            if not sel.any():
                continue
            nodes = info.get("_nodes", {})
            if "base_color" in nodes:
                im = nodes["base_color"].image
                base_size = list(im.size)
                arr = img_np(im)
                smp = lookup(arr, sel)[..., :3].astype(np.float64)    # sRGB-Werte
                lin = srgb_to_lin(smp)
                Y = lin @ np.array([0.2126, 0.7152, 0.0722])
                Ytri[sel] = Y.mean(1)
                RGBtri[sel] = smp.mean(1)
                luma = arr[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
                lap = np.abs(4 * luma - np.roll(luma, 1, 0) - np.roll(luma, -1, 0)
                             - np.roll(luma, 1, 1) - np.roll(luma, -1, 1))
                HFtri[sel] = lookup(lap, sel).mean(1)
                hh, ww = luma.shape
                half = luma[: hh // 2 * 2, : ww // 2 * 2].reshape(hh // 2, 2, ww // 2, 2).mean((1, 3))
                lap2 = np.abs(4 * half - np.roll(half, 1, 0) - np.roll(half, -1, 0)
                              - np.roll(half, 1, 1) - np.roll(half, -1, 1))
                HF2tri[sel] = lookup(lap2, sel).mean(1)
                del lap, lap2, luma, half
            for role, dst in (("roughness", ROUGHtri), ("metallic", METALtri)):
                if role in nodes:
                    arr = img_np(nodes[role].image)
                    ch = {"R": 0, "G": 1, "B": 2, "A": 3}.get(info["maps"][role]["channel"], 0)
                    dst[sel] = lookup(arr, sel)[..., ch].mean(1)
        img_cache.clear()

    def wmean(x, w):
        ok = ~np.isnan(x) & (w > 0)
        return float((x[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() and w[ok].sum() > 0 else None

    total_area = float(area[good].sum())
    groups = {}
    for k, g in enumerate(gname):
        sel = gok & (gi == k)
        planar = sel & (axes[:, k] > 0.97)
        groups[g] = {"area_share": round(float(area[sel].sum() / total_area), 4),
                     "planar_share": round(float(area[planar].sum() / max(area[sel].sum(), 1e-30)), 4),
                     "lum_lin": None if wmean(Ytri[sel], area[sel]) is None else round(wmean(Ytri[sel], area[sel]), 4)}
    zc = (p0[:, 2] + p1[:, 2] + p2[:, 2]) / 3
    lowband = good & (zc < vmin[2] + 0.25 * H)
    highband = good & (zc > vmin[2] + 0.75 * H)
    y_low, y_high = wmean(Ytri[lowband], area[lowband]), wmean(Ytri[highband], area[highband])
    rgb_mean = [wmean(RGBtri[:, k], area) for k in range(3)]

    # Unterseite / Fuß
    bottom_flat = good & (nz < -0.9) & (zc < vmin[2] + 0.03 * H)
    rv_ = Vw[:, 2] < vmin[2] + 0.05 * H
    if rv_.any():
        bx = Vw[rv_, 0] * cyw + Vw[rv_, 1] * syw
        by = -Vw[rv_, 0] * syw + Vw[rv_, 1] * cyw
        base_slice = [float((bx.max() - bx.min()) / Lm), float((by.max() - by.min()) / Dm)]
    else:
        base_slice = [0.0, 0.0]

    signed_vol = float((p0[good] * np.cross(p1[good], p2[good])).sum() / 6.0)

    maps_present = sorted({r for info in mat_info for r in info["maps"]})
    meas = {
        "glb": os.path.abspath(a.glb),
        "glb_bytes": os.path.getsize(a.glb),
        "objects": len(meshes),
        "materials": [{k: v for k, v in i.items() if not k.startswith("_")} for i in mat_info],
        "maps_present": maps_present,
        "vertices_raw": int(len(V)),
        "vertices_welded": int(Nw),
        "polygons": n_polys, "quads": n_quads, "ngons": n_ngons,
        "triangles": int(ntri),
        "bbox_min": vmin.tolist(), "bbox_max": vmax.tolist(),
        "bbox_size": ext.tolist(),
        "oriented": {"length": Lm, "depth": Dm, "height": H, "yaw_deg": math.degrees(yaw),
                     "center_xy": [cx, cy]},
        "degenerate_tris": int(degen.sum()),
        "edges_unique": int(len(uk)),
        "boundary_edges": int(bmask.sum()),
        "boundary_loops": boundary_loops,
        "largest_hole_perimeter_rel_diag": round(largest_hole_rel, 4),
        "holes_top": holes,
        "non_manifold_edges": int(nmmask.sum()),
        "parts": int(ncomp),
        "parts_min_tris": int((ctris >= THRESHOLDS["loose_parts_min_tris"]).sum()),
        "largest_part_share": round(float(ctris.max() / max(total_good, 1)), 5),
        "parts_top": parts,
        "floating_parts": floating,
        "signed_volume": signed_vol,
        "has_uv": bool(has_uv),
        "uv_coverage": round(float(uvarea[good].sum()), 4),
        "base_color_size": base_size,
        "surface_area": total_area,
        "lum_groups": groups,
        "lum_low_quarter": y_low, "lum_high_quarter": y_high,
        "base_color_mean_srgb": rgb_mean,
        "texture_hf_full": wmean(HFtri, area),
        "texture_hf_half": wmean(HF2tri, area),
        "roughness_mean": wmean(ROUGHtri, area),
        "roughness_below_05_share": (float(area[good & (ROUGHtri < 0.5)].sum() / total_area)
                                     if not np.isnan(ROUGHtri).all() else None),
        "metallic_mean": wmean(METALtri, area),
        "bottom_flat_area_rel_footprint": round(float(area[bottom_flat].sum() / (Lm * Dm)), 4),
        "base_slice_extent_rel": [round(x, 3) for x in base_slice],
    }
    timing["measure_s"] = round(time.time() - t1, 2)

    if a.no_render:
        meas["timing"] = timing
        json.dump(meas, open(os.path.join(a.work, "measure.json"), "w"), indent=1)
        return

    # ---------- Rendern ----------
    t2 = time.time()
    exp = [float(x) for x in a.expect.split(",")] if a.expect else None
    s = (exp[2] / H) if exp else 1.0
    meas["sheet_scale"] = s

    root = bpy.data.objects.new("QA_Root", None)
    scene.collection.objects.link(root)
    for ob in list(scene.objects):
        if ob is not root and ob.parent is None:
            ob.parent = root
            ob.matrix_parent_inverse = Matrix.Identity(4)
    root.matrix_world = (Matrix.Scale(s, 4) @ Matrix.Rotation(-yaw, 4, "Z")
                         @ Matrix.Translation((-cx, -cy, -vmin[2])))
    bpy.context.view_layer.update()

    sub = Vw if Nw <= 60000 else Vw[rng.choice(Nw, 60000, replace=False)]
    Rm = np.array(root.matrix_world)
    P = sub @ Rm[:3, :3].T + Rm[:3, 3]
    # Extrempunkte sicher dabei: Rand-Vertices der Achsen
    P = np.concatenate([P, (Vw[np.r_[Vw.argmin(0), Vw.argmax(0)]] @ Rm[:3, :3].T + Rm[:3, 3])])
    Rh = float(np.sqrt((P[:, 0] ** 2 + P[:, 1] ** 2)).max())
    Hs = H * s

    # Maßfigur 1,8 m: Zylinder 0..1,5 m + Kugel r=0,15 bei 1,65 m
    fmat = bpy.data.materials.new("QA_Figure")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (*FIGURE_COLOR, 1)
    fb.inputs["Roughness"].default_value = 0.8
    bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=1.5, location=(0, 0, 0.75), vertices=24)
    body = bpy.context.object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0, 0, 1.65), segments=24, ring_count=12)
    head = bpy.context.object
    head.parent = body
    head.matrix_parent_inverse = body.matrix_world.inverted()
    for o in (body, head):
        o.data.materials.append(fmat)
        o.color = (*FIGURE_COLOR, 1)
    fig_pts = np.array([[x, y, z] for x in (-0.2, 0.2) for y in (-0.2, 0.2) for z in (0.0, 1.8)])

    # Welt + Licht
    world = bpy.data.worlds.new("QA_World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.62, 0.62, 0.62, 1)
    bg.inputs[1].default_value = 1.0
    scene.world = world
    sun_d = bpy.data.lights.new("QA_Sun", "SUN")
    sun_d.energy = 2.2
    sun_d.angle = math.radians(8)
    sun = bpy.data.objects.new("QA_Sun", sun_d)
    scene.collection.objects.link(sun)

    cam_d = bpy.data.cameras.new("QA_Cam")
    cam = bpy.data.objects.new("QA_Cam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_d.sensor_fit = "HORIZONTAL"
    cam_d.clip_start = 0.01
    cam_d.clip_end = 10000

    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = 24
    except AttributeError:
        pass
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.display_settings.display_device = "sRGB"

    def look(fwd, up_hint, loc):
        f = np.asarray(fwd, float)
        f /= np.linalg.norm(f)
        r = np.cross(f, up_hint)
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        return Matrix(((r[0], u[0], -f[0], loc[0]), (r[1], u[1], -f[1], loc[1]),
                       (r[2], u[2], -f[2], loc[2]), (0, 0, 0, 1))), r, u, f

    def place_light(r, u, f):
        ldir = f * 1.0 - u * 0.55 + r * 0.45      # Licht von oben links hinter der Kamera
        hint = (0, 0, 1) if abs(ldir[2] / np.linalg.norm(ldir)) < 0.95 else (0, 1, 0)
        sun.matrix_world = look(ldir, hint, (0, 0, 0))[0]

    def setup_ortho(fwd, up_hint, res, with_figure, margin=0.06, scale=None):
        _, r, u, f = look(fwd, up_hint, (0, 0, 0))
        pts = P
        if with_figure:
            rh = np.array([r[0], r[1], 0.0])
            rh = rh / np.linalg.norm(rh) if np.linalg.norm(rh) > 1e-6 else np.array([1.0, 0, 0])
            floc = rh * (Rh + 0.35 + 0.05 * Rh)
            body.location = Vector(floc + np.array([0.0, 0.0, 0.75]))
            body.hide_render = head.hide_render = False
            pts = np.concatenate([P, fig_pts + floc])
        else:
            body.hide_render = head.hide_render = True
        bpy.context.view_layer.update()
        pr, pu, pf = pts @ r, pts @ u, pts @ f
        wr, hu = pr.max() - pr.min(), pu.max() - pu.min()
        aspect = res[0] / res[1]
        cam_d.type = "ORTHO"
        cam_d.ortho_scale = float(scale or max(wr, hu * aspect) * (1 + 2 * margin))
        ctr = r * (pr.max() + pr.min()) / 2 + u * (pu.max() + pu.min()) / 2
        depth = pf.max() - pf.min()
        loc = ctr + f * (pf.min() - depth - 1.0)
        cam.matrix_world = look(f, up_hint, loc)[0]
        place_light(r, u, f)
        return cam_d.ortho_scale

    def setup_persp(loc, target, lens=35.0):
        f = np.asarray(target, float) - np.asarray(loc, float)
        m, r, u, f = look(f, (0, 0, 1), loc)
        cam_d.type = "PERSP"
        cam_d.lens = lens
        cam_d.sensor_width = 36
        cam.matrix_world = m
        body.hide_render = head.hide_render = True
        place_light(r, u, f)

    def render(path, res, engine="BLENDER_EEVEE"):
        scene.render.engine = engine
        scene.render.resolution_x, scene.render.resolution_y = res
        scene.render.resolution_percentage = 100
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)

    model_objs = meshes

    # Grundfarbe-Ersatzmaterialien (Emission der base_color-Textur)
    albedo_mats = {}
    for info, m in zip(mat_info, mats):
        am = bpy.data.materials.new("QA_Albedo")
        am.use_nodes = True
        nt = am.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(em.outputs[0], out.inputs[0])
        bn = info.get("_nodes", {}).get("base_color")
        if bn is not None:
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = bn.image
            nt.links.new(tex.outputs[0], em.inputs[0])
        else:
            em.inputs[0].default_value = (1, 0, 1, 1)
        albedo_mats[m.name if m else None] = am

    # Drahtgitter-Material (Wireframe-Knoten, Pixelbreite)
    wmat = bpy.data.materials.new("QA_Wire")
    wmat.use_nodes = True
    nt = wmat.node_tree
    wb = nt.nodes["Principled BSDF"]
    wb.inputs["Roughness"].default_value = 0.8
    wire = nt.nodes.new("ShaderNodeWireframe")
    wire.use_pixel_size = True
    wire.inputs[0].default_value = 0.7
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    # Mix-Sockets per Index: 0 Factor(float), 6 A(color), 7 B(color); Ausgang 2 = Result(color)
    nt.links.new(wire.outputs[0], mix.inputs[0])
    mix.inputs[6].default_value = (0.78, 0.78, 0.78, 1)
    mix.inputs[7].default_value = (0.03, 0.03, 0.04, 1)
    nt.links.new(mix.outputs[2], wb.inputs["Base Color"])

    def swap_materials(kind):
        saved = []
        for ob in model_objs:
            for i, slot in enumerate(ob.material_slots):
                saved.append((ob, i, slot.material))
                if kind == "albedo":
                    slot.material = albedo_mats.get(slot.material.name if slot.material else None)
                elif kind == "wire":
                    slot.material = wmat
        return saved

    def restore(saved):
        for ob, i, m in saved:
            ob.material_slots[i].material = m

    pdir = os.path.join(a.work, "panels")
    pres = (PANEL[0] * PANEL_RENDER_SCALE, PANEL[1] * PANEL_RENDER_SCALE)
    el = math.radians(20)
    views = {}
    for az in range(0, 360, 45):
        ar = math.radians(az)
        cdir = np.array([math.sin(ar) * math.cos(el), -math.cos(ar) * math.cos(el), math.sin(el)])
        views["tex_%03d" % az] = (-cdir, (0, 0, 1))
    # gleicher Maßstab für alle Rundum-Ansichten (vergleichbar), eigener für Drauf-/Untersicht
    ring_scale = max(setup_ortho(fwd, up, pres, True) for fwd, up in views.values())
    for name, (fwd, up) in views.items():
        setup_ortho(fwd, up, pres, True, scale=ring_scale)
        render(os.path.join(pdir, name + ".png"), pres)
    tb_scale = max(setup_ortho((0, 0, -1), (0, 1, 0), pres, True), setup_ortho((0, 0, 1), (0, -1, 0), pres, True))
    setup_ortho((0, 0, -1), (0, 1, 0), pres, True, scale=tb_scale)
    render(os.path.join(pdir, "top.png"), pres)
    setup_ortho((0, 0, 1), (0, -1, 0), pres, True, scale=tb_scale)
    render(os.path.join(pdir, "bottom.png"), pres)
    meas["ortho_scale_m"] = {"ring": ring_scale, "top_bottom": tb_scale}

    fwd45 = views["tex_045"][0]
    saved = swap_materials("albedo")
    setup_ortho(fwd45, (0, 0, 1), pres, True, scale=ring_scale)
    render(os.path.join(pdir, "albedo_045.png"), pres)
    restore(saved)

    saved = swap_materials("wire")
    setup_ortho(fwd45, (0, 0, 1), PANEL, True, scale=ring_scale)
    render(os.path.join(pdir, "wire_045.png"), PANEL)
    restore(saved)

    # 3-m-Nahansicht: Kamera 3 m vor der Vorderseite (−Y), Augenhöhe 1,7 m
    Ds = Dm * s
    cam_loc = (0.0, -(Ds / 2 + 3.0), 1.7)
    target = (0.0, 0.0, min(Hs * 0.5, 1.5))
    setup_persp(cam_loc, target, 35.0)
    render(os.path.join(pdir, "close3m.png"), CLOSE)
    saved = swap_materials("wire")
    wire.inputs[0].default_value = 1.0
    render(os.path.join(pdir, "close3m_wire.png"), (CLOSE[0] // 2, CLOSE[1] // 2))
    restore(saved)

    timing["render_s"] = round(time.time() - t2, 2)
    meas["timing"] = timing
    json.dump(meas, open(os.path.join(a.work, "measure.json"), "w"), indent=1)


# ----------------------------------------------------------------------------------------------
# Python-Stufe (Pillow)
# ----------------------------------------------------------------------------------------------

def parse_brief(path):
    out = {"path": path}
    if not path or not os.path.exists(path):
        return out
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"^#\s*(.+)$", txt, re.M)
    out["title"] = m.group(1).strip() if m else None
    m = re.search(r"Klasse\s+([AB])", txt)
    out["class"] = m.group(1) if m else None
    m = re.search(r"LOD0\s*(?:≤|<=)\s*([\d\s.]+)", txt)
    if m:
        out["lod0_max_tris"] = int(re.sub(r"[\s.]", "", m.group(1)))
    m = re.search(r"Rauheit\s*(?:≥|>=)\s*(\d+[.,]\d+)", txt)
    if m:
        out["roughness_min"] = float(m.group(1).replace(",", "."))
    out["palette"] = {n: "#" + h.upper() for n, h in re.findall(r"(\w+)\s+#([0-9A-Fa-f]{6})", txt)}
    m = re.search(r"^- Maße:(.*)$", txt, re.M)
    if m:
        out["size_line"] = m.group(1).strip()
        nums = re.findall(r"(\d+(?:[.,]\d+)?)\s*m\s+(?:lang|tief|dick|hoch|breit)", m.group(1))
        if len(nums) == 3:
            out["size_parsed"] = [float(n.replace(",", ".")) for n in nums]
    return out


def hexcol(rgb):
    return "#%02X%02X%02X" % tuple(int(round(max(0, min(1, c)) * 255)) for c in rgb)


def evaluate(meas, expect, brief):
    th = THRESHOLDS
    o = meas["oriented"]
    L, D, H = o["length"], o["depth"], o["height"]
    r = {"depth_over_width": D / L, "height_over_width": H / L}
    flags, notes = {}, []
    # flache Scheibe
    min_dw = th["flat_disc_min_depth_ratio"]
    exp_r = None
    if expect:
        el, ew = max(expect[0], expect[1]), min(expect[0], expect[1])
        exp_r = {"depth_over_width": ew / el, "height_over_width": expect[2] / el}
        if exp_r["depth_over_width"] < min_dw:
            min_dw = 0.6 * exp_r["depth_over_width"]
    flags["flat_disc"] = r["depth_over_width"] < min_dw
    # Seitenverhältnisse
    dev = {}
    if exp_r:
        for k in exp_r:
            dev[k] = r[k] / exp_r[k]
        flags["aspect_mismatch"] = any(max(v, 1 / v) > th["aspect_tolerance_factor"] for v in dev.values())
    else:
        flags["aspect_mismatch"] = None
        notes.append("keine erwarteten Maße -> aspect_mismatch nicht geprüft")
    flags["many_loose_parts"] = (meas["parts_min_tris"] > th["loose_parts_max"]
                                 or meas["largest_part_share"] < th["largest_part_min_share"])
    flags["holes"] = meas["boundary_edges"] > th["holes_max_boundary_edges"]
    flags["non_manifold"] = meas["non_manifold_edges"] > th["non_manifold_max_edges"]
    g = meas["lum_groups"]
    ok = lambda k: g[k]["lum_lin"] is not None and g[k]["area_share"] >= th["baked_light_min_group_area_share"]
    light = {}
    if ok("top") and ok("bottom"):
        light["top_over_bottom"] = g["top"]["lum_lin"] / max(g["bottom"]["lum_lin"], 1e-6)
        flags["baked_light_top_bottom"] = (max(light["top_over_bottom"], 1 / light["top_over_bottom"])
                                           > th["baked_light_top_bottom_max"])
    else:
        light["top_over_bottom"] = None
        flags["baked_light_top_bottom"] = None
        notes.append("oben/unten-Gruppe zu klein für Lichtvergleich")
    sides = [g[k]["lum_lin"] for k in ("+X", "-X", "+Y", "-Y") if ok(k)]
    if len(sides) >= 2:
        light["sides_max_over_min"] = max(sides) / max(min(sides), 1e-6)
        flags["baked_light_sides"] = light["sides_max_over_min"] > th["baked_light_sides_max"]
    else:
        light["sides_max_over_min"] = None
        flags["baked_light_sides"] = None
    if meas["lum_low_quarter"] and meas["lum_high_quarter"]:
        light["high_quarter_over_low_quarter"] = meas["lum_high_quarter"] / meas["lum_low_quarter"]
    maps = meas["maps_present"]
    missing = [m for m in th["required_maps"] if m not in maps]
    small = [f"{role}:{v['size'][0]}" for mi in meas["materials"] for role, v in mi["maps"].items()
             if role in ("base_color", "normal") and min(v["size"]) < th["min_texture_size"]]
    flags["missing_maps"] = bool(missing) or not meas["has_uv"]
    # Zusatzinfos (keine Pflicht-Flags)
    extra = {}
    if brief.get("lod0_max_tris") and brief.get("class_used") == "B":
        extra["over_tri_target"] = meas["triangles"] > brief["lod0_max_tris"] * th["tri_target_tolerance"]
    if brief.get("roughness_min") is not None and meas.get("roughness_mean") is not None:
        extra["roughness_below_brief"] = meas["roughness_mean"] < brief["roughness_min"]
    if meas.get("metallic_mean") is not None:
        extra["metallic_nonzero"] = meas["metallic_mean"] > 0.05
    extra["floating_parts"] = len(meas["floating_parts"]) > 0
    extra["small_textures"] = bool(small)
    extra["inverted_normals"] = meas["boundary_edges"] == 0 and meas["signed_volume"] < 0
    return {"ratios": r, "expected_ratios": exp_r, "ratio_deviation": dev, "flat_disc_threshold": min_dw,
            "light": light, "flags": flags, "info_flags": extra, "missing_maps": missing,
            "small_textures": small, "notes": notes}


def check_panel(path):
    from PIL import Image
    import numpy as np
    im = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255
    a = im[..., 3]
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    obj = a > 0.5
    cover = float(obj.mean())
    lum = float((im[..., :3][obj] @ np.array([0.2126, 0.7152, 0.0722])).mean()) if obj.any() else 0.0
    return {"border_alpha_px": int((border > 0.5).sum()), "coverage": round(cover, 4),
            "object_luma": round(lum, 4),
            "ok": bool((border > 0.5).sum() == 0 and cover > 0.02 and lum > 0.06)}


BG = (128, 131, 136)


def load_panel(path, size):
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    bg = Image.new("RGBA", size, BG + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def font(size, bold=False, mono=False):
    from PIL import ImageFont
    name = ("consolab.ttf" if bold else "consola.ttf") if mono else ("arialbd.ttf" if bold else "arial.ttf")
    try:
        return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
    except OSError:
        return ImageFont.load_default()


def f2(x, n=2):
    return "–" if x is None else f"{x:.{n}f}"


def compose_sheet(out_dir, qa):
    from PIL import Image, ImageDraw
    W, Hh = 2400, 1500
    col = 380
    sheet = Image.new("RGB", (W, Hh), (34, 35, 38))
    d = ImageDraw.Draw(sheet)
    pdir = os.path.join(out_dir, "panels")
    layout = [("tex_000", "0° (vorn)"), ("tex_045", "45°"), ("tex_090", "90°"), ("tex_135", "135°"),
              ("tex_180", "180° (hinten)"), ("tex_225", "225°"), ("tex_270", "270°"), ("tex_315", "315°"),
              ("wire_045", "Drahtgitter 45°"), ("albedo_045", "nur Grundfarbe (unbeleuchtet) 45°"),
              ("top", "Draufsicht"), ("bottom", "Untersicht")]
    top = 34
    d.text((col + 8, 8), "Rundum, orthografisch, 20° von oben · Maßfigur 1,8 m (orange) · Modell nur fürs Blatt "
           f"auf Zielhöhe skaliert (x{qa['sheet_scale']:.3f})", fill=(220, 220, 220), font=font(17))
    fcap = font(15)
    for i, (key, cap) in enumerate(layout):
        r, c = divmod(i, 4)
        x = col + c * PANEL[0]
        y = top + r * (PANEL[1] + 26)
        p = os.path.join(pdir, key + ".png")
        if os.path.exists(p):
            sheet.paste(load_panel(p, PANEL), (x, y))
        chk = qa["render_checks"].get(key, {})
        colr = (200, 200, 200) if chk.get("ok", True) else (255, 90, 80)
        warn = "" if chk.get("ok", True) else "  ! Rand/dunkel"
        d.text((x + 6, y + PANEL[1] + 4), cap + warn, fill=colr, font=fcap)
        d.rectangle([x, y, x + PANEL[0] - 1, y + PANEL[1] - 1], outline=(60, 62, 66))

    # Textspalte
    m, ev = qa["measure"], qa["eval"]
    fm, fb, ft = font(15, mono=True), font(15, bold=True, mono=True), font(22, bold=True)
    y = 10
    d.text((12, y), qa["name"], fill=(255, 255, 255), font=ft)
    y += 30
    d.text((12, y), (qa["brief"].get("title") or "")[:58], fill=(190, 190, 190), font=font(11))
    y += 22

    def line(txt, colr=(215, 215, 215), bold=False):
        nonlocal y
        d.text((12, y), txt, fill=colr, font=fb if bold else fm)
        y += 19

    def head(txt):
        nonlocal y
        y += 6
        line(txt, (140, 190, 255), True)

    o = m["oriented"]
    exp = qa["expect_size"]
    line(f"Klasse {qa['brief'].get('class_used') or '?'}" + (f" · Ziel LOD0 ≤ {qa['brief']['lod0_max_tris']:,}".replace(",", " ")
         if qa['brief'].get('lod0_max_tris') else ""), (190, 190, 190))
    head("Maße (Meshy-Einheiten)")
    line(f"Box L×T×H {o['length']:.3f}×{o['depth']:.3f}×{o['height']:.3f}")
    line(f"Gier der Längsachse {o['yaw_deg']:+.1f}°")
    if exp:
        line(f"erwartet  {exp[0]}×{exp[1]}×{exp[2]} m")
        line(f"Blatt: ×{qa['sheet_scale']:.3f} -> {o['length']*qa['sheet_scale']:.2f}×"
             f"{o['depth']*qa['sheet_scale']:.2f}×{o['height']*qa['sheet_scale']:.2f} m")
    r, er = ev["ratios"], ev["expected_ratios"] or {}
    line(f"T/B  {r['depth_over_width']:.3f}  (soll {f2(er.get('depth_over_width'), 3)})")
    line(f"H/B  {r['height_over_width']:.3f}  (soll {f2(er.get('height_over_width'), 3)})")
    head("Netz")
    line(f"Dreiecke   {m['triangles']:,}".replace(",", " "))
    line(f"Polygone   {m['polygons']:,} ({m['quads']:,} Quads)".replace(",", " "))
    line(f"Vertices   {m['vertices_welded']:,} verschw.".replace(",", " "))
    line(f"Teile      {m['parts']}  (≥{THRESHOLDS['loose_parts_min_tris']} Dr.: {m['parts_min_tris']})")
    line(f"größtes    {m['largest_part_share']*100:.2f} % der Dr.")
    line(f"schwebend  {len(m['floating_parts'])}")
    line(f"Randkanten {m['boundary_edges']}  in {m['boundary_loops']} Löchern")
    if m["boundary_loops"]:
        line(f" größtes Loch: Umfang {m['largest_hole_perimeter_rel_diag']*100:.1f} % Diag.")
    line(f"nicht-mannigf. Kanten {m['non_manifold_edges']}")
    line(f"degeneriert {m['degenerate_tris']}")
    head("Textur")
    line(f"UV {'ja' if m['has_uv'] else 'NEIN'}, Belegung {m['uv_coverage']*100:.0f} %")
    for mi in m["materials"]:
        for role, v in sorted(mi["maps"].items()):
            line(f" {role:<10} {v['size'][0]}² {v.get('channel','')}")
    if qa.get("texel_density_px_per_m"):
        line(f"Texeldichte {qa['texel_density_px_per_m']:.0f} px/m")
    line(f"Detail 4K/2K {f2(qa.get('texture_detail_ratio'))}  HF {f2(m['texture_hf_full'], 4)}")
    rgb = m["base_color_mean_srgb"]
    if rgb[0] is not None:
        line(f"Grundfarbe Ø {hexcol(rgb)}")
    line(f"Rauheit Ø {f2(m['roughness_mean'])}  Metall Ø {f2(m['metallic_mean'])}")
    head("Licht in Grundfarbe (lin. Lum.)")
    g = m["lum_groups"]
    for k in ("top", "bottom", "+X", "-X", "+Y", "-Y"):
        line(f" {k:<6} {f2(g[k]['lum_lin'], 3)}  Fl {g[k]['area_share']*100:4.1f}%  eben {g[k]['planar_share']*100:3.0f}%")
    lt = ev["light"]
    line(f"oben/unten {f2(lt.get('top_over_bottom'))}  Seiten max/min {f2(lt.get('sides_max_over_min'))}")
    head("Flags")
    for k, v in list(ev["flags"].items()) + [(k + "*", v) for k, v in ev["info_flags"].items()]:
        colr = (120, 220, 120) if v is False else ((255, 90, 80) if v else (170, 170, 170))
        line(f" {k:<24} {'JA' if v else ('nein' if v is False else '–')}", colr)
    y += 4
    d.text((12, y), "* Zusatzinfo, kein Pflicht-Flag", fill=(150, 150, 150), font=font(12))
    # Fußzeile
    t = qa["timing"]
    d.text((col + 8, Hh - 30), f"{qa['glb']}   ·   Laufzeit {t.get('total_s', 0):.0f} s (Import {t.get('import_s')} s, "
           f"Messung {t.get('measure_s')} s, Render {t.get('render_s')} s)   ·   {qa['created']}",
           fill=(160, 160, 160), font=font(14))
    out = os.path.join(out_dir, "sheet.jpg")
    sheet.save(out, quality=90)
    return out


def run_inspect(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb")
    ap.add_argument("--out", required=True)
    ap.add_argument("--brief", default="")
    ap.add_argument("--expect-size", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--class", dest="klass", choices=["A", "B"], default=None,
                    help="Meshy-Klasse; Standard: aus Ordnername (A-…/B-…), sonst aus dem Brief")
    ap.add_argument("--blender", default=os.environ.get("VR_BLENDER", BLENDER_DEFAULT))
    ap.add_argument("--no-render", action="store_true", help="nur messen (kein Blatt)")
    a = ap.parse_args(argv)
    t0 = time.time()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    brief = parse_brief(a.brief)
    folder = os.path.basename(os.path.dirname(os.path.abspath(a.glb)))
    klass = a.klass or (folder[0] if re.match(r"^[AB]-", folder) else brief.get("class"))
    brief["class_used"] = klass
    expect = [float(x) for x in a.expect_size.split(",")] if a.expect_size else brief.get("size_parsed")
    name = a.name or os.path.basename(os.path.dirname(os.path.abspath(a.glb)))
    cmd = [a.blender, "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--",
           "--stage", "blender", "--glb", os.path.abspath(a.glb), "--work", out]
    if expect:
        cmd += ["--expect", ",".join(str(x) for x in expect)]
    if a.no_render:
        cmd += ["--no-render"]
    with open(os.path.join(out, "blender.log"), "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    mpath = os.path.join(out, "measure.json")
    if proc.returncode != 0 or not os.path.exists(mpath):
        raise SystemExit(f"Blender-Stufe fehlgeschlagen (rc={proc.returncode}), siehe {out}\\blender.log")
    meas = json.load(open(mpath))
    ev = evaluate(meas, expect, brief)
    s = meas.get("sheet_scale", 1.0)
    texel = None
    if meas.get("base_color_size") and meas["surface_area"] > 0 and expect:
        w, h = meas["base_color_size"]
        texel = math.sqrt(meas["uv_coverage"] * w * h / (meas["surface_area"] * s * s))
    detail = (meas["texture_hf_full"] / meas["texture_hf_half"]
              if meas.get("texture_hf_full") and meas.get("texture_hf_half") else None)
    checks = {}
    pdir = os.path.join(out, "panels")
    if os.path.isdir(pdir):
        for fn in sorted(os.listdir(pdir)):
            if fn.endswith(".png"):
                checks[fn[:-4]] = check_panel(os.path.join(pdir, fn))
    # Nahansicht darf angeschnitten sein (3 m vor großem Objekt)
    for k in ("close3m", "close3m_wire"):
        if k in checks:
            checks[k]["ok"] = checks[k]["coverage"] > 0.02 and checks[k]["object_luma"] > 0.06
    timing = dict(meas.get("timing", {}))
    timing["total_s"] = round(time.time() - t0, 1)
    qa = {
        "name": name,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "glb": os.path.abspath(a.glb),
        "brief": brief,
        "expect_size": expect,
        "sheet_scale": s,
        "thresholds": THRESHOLDS,
        "flags": ev["flags"],
        "info_flags": ev["info_flags"],
        "eval": ev,
        "texel_density_px_per_m": texel,
        "texture_detail_ratio": detail,
        "base_color_mean_hex": hexcol(meas["base_color_mean_srgb"]) if meas["base_color_mean_srgb"][0] is not None else None,
        "render_checks": checks,
        "render_ok": all(c["ok"] for c in checks.values()) if checks else None,
        "measure": meas,
        "timing": timing,
    }
    if not a.no_render:
        qa["sheet"] = compose_sheet(out, qa)
        qa["timing"]["total_s"] = round(time.time() - t0, 1)
    qa_path = os.path.join(out, "qa.json")
    json.dump(qa, open(qa_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.remove(mpath)
    fl = [k for k, v in {**ev["flags"], **ev["info_flags"]}.items() if v]
    print(f"{name}: {meas['triangles']} Dr., {meas['parts']} Teile, Randkanten {meas['boundary_edges']}, "
          f"T/B {ev['ratios']['depth_over_width']:.2f}, Flags: {', '.join(fl) or '-'}, "
          f"{qa['timing']['total_s']} s -> {qa_path}")
    return qa


def run_compare(argv):
    from PIL import Image, ImageDraw
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--labels", default="")
    a = ap.parse_args(argv)
    labels = [x.strip() for x in a.labels.split("|")] if a.labels else []
    cw, chh = 800, 600
    n = len(a.dirs)
    head, cap = 44, 46
    W, H = cw * n, head + 3 * (chh + cap)
    img = Image.new("RGB", (W, H), (34, 35, 38))
    d = ImageDraw.Draw(img)
    d.text((10, 10), "Nahansicht aus 3 m (Augenhöhe 1,7 m, 35 mm), Modell auf Zielhöhe skaliert · "
           "oben texturiert, Mitte Drahtgitter, unten Ausschnitt 2x (Bildmitte, volle Renderauflösung)", fill=(225, 225, 225), font=font(19))
    for i, dd in enumerate(a.dirs):
        qa = json.load(open(os.path.join(dd, "qa.json"), encoding="utf-8"))
        m = qa["measure"]
        lab = labels[i] if i < len(labels) else qa["name"]
        x = i * cw
        for row, key in enumerate(("close3m", "close3m_wire", "close3m_crop")):
            y = head + row * (chh + cap)
            if key == "close3m_crop":
                full = Image.open(os.path.join(dd, "panels", "close3m.png")).convert("RGBA")
                fw, fh = full.size
                crop = full.crop(((fw - cw) // 2, (fh - chh) // 2, (fw + cw) // 2, (fh + chh) // 2))
                bgc = Image.new("RGBA", (cw, chh), BG + (255,))
                bgc.alpha_composite(crop)
                img.paste(bgc.convert("RGB"), (x, y))
            else:
                img.paste(load_panel(os.path.join(dd, "panels", key + ".png"), (cw, chh)), (x, y))
            d.rectangle([x, y, x + cw - 1, y + chh - 1], outline=(60, 62, 66))
            if row == 0:
                tris = f"{m['triangles']:,}".replace(",", " ")
                txt = (f"{lab}  ·  {tris} Dr.  ·  {m['parts']} Teile  ·  "
                       f"Texel {qa.get('texel_density_px_per_m') or 0:.0f} px/m")
                txt2 = (f"T/B {qa['eval']['ratios']['depth_over_width']:.2f}  H/B "
                        f"{qa['eval']['ratios']['height_over_width']:.2f}  ·  Licht o/u "
                        f"{f2(qa['eval']['light'].get('top_over_bottom'))} Seiten "
                        f"{f2(qa['eval']['light'].get('sides_max_over_min'))}  ·  Detail 4K/2K "
                        f"{f2(qa.get('texture_detail_ratio'))}")
            elif row == 1:
                fl = [k for k, v in {**qa["flags"], **qa["info_flags"]}.items() if v]
                txt, txt2 = f"{lab}  ·  Drahtgitter", "Flags: " + (", ".join(fl) or "keine")
            else:
                txt = f"{lab}  ·  Ausschnitt 2x"
                txt2 = (f"Grundfarbe Ø {qa.get('base_color_mean_hex')}  ·  Rauheit Ø {f2(m.get('roughness_mean'))}"
                        f"  ·  HF {f2(m.get('texture_hf_full'), 3)}")
            d.text((x + 8, y + chh + 4), txt, fill=(235, 235, 235), font=font(17, bold=True))
            d.text((x + 8, y + chh + 25), txt2, fill=(190, 190, 190), font=font(15))
    img.save(a.out, quality=90)
    print("->", a.out)


if __name__ == "__main__":
    if IN_BLENDER:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
        try:
            bl_main(argv)
        except Exception:
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            os._exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "compare":
        run_compare(sys.argv[2:])
    else:
        run_inspect(sys.argv[1:])

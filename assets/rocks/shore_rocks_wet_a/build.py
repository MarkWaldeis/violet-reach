"""Nasse Uferfelsen-Gruppe A (shore_rocks_wet_a) — Meshy Klasse B.

Bereitet das Meshy-Rohmodell (shore_rocks_wet_a/model/B-v1/model.glb) deterministisch
mit tools/blender/vrmeshy.py auf: Smart-Topology-Randlöcher schließen, auf Zielhöhe
1,05 m (yaw -84,5°) normalisieren, sanfte Farbabstimmung Richtung shore_wet (#5D6064,
0,15), 35 cm Eingrabe-Rand unter z = 0 extrudieren, Z-gestufte Rauheit direkt in die
Rauheitstextur einbacken (feuchte untere Flanken z < 0,55 m -> 0,38–0,52; trockenere
Oberkanten ≥ 0,60; Metall 0,0) und Normalen richten.
"""
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector
import vrlib
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _close_pinholes(objs):
    """Seal small smart-topology boundary loops with a manifold triangle fan and interpolated UVs."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-4)
        uv_layer = bm.loops.layers.uv.active
        vert_uv = {}
        if uv_layer is not None:
            for f in bm.faces:
                for l in f.loops:
                    vert_uv.setdefault(l.vert, l[uv_layer].uv.copy())
        for _ in range(128):
            b_edges = [e for e in bm.edges if e.is_boundary]
            if not b_edges:
                break
            start_e = b_edges[0]
            loop_verts = [start_e.verts[0], start_e.verts[1]]
            used_edges = {start_e}
            cur = loop_verts[-1]
            closed = False
            while True:
                next_e = [e for e in cur.link_edges if e.is_boundary and e not in used_edges]
                if not next_e:
                    break
                e = next_e[0]
                used_edges.add(e)
                nxt = e.other_vert(cur)
                if nxt in loop_verts:
                    cycle = loop_verts[loop_verts.index(nxt):]
                    if len(cycle) >= 3:
                        cv = bm.verts.new(sum((v.co for v in cycle), Vector()) / len(cycle))
                        vert_uv[cv] = (
                            sum((vert_uv.get(v, Vector((0.5, 0.5))) for v in cycle), Vector((0.0, 0.0)))
                            / len(cycle)
                        )
                        for i in range(len(cycle)):
                            try:
                                nf = bm.faces.new((cycle[i], cycle[(i + 1) % len(cycle)], cv))
                                if uv_layer is not None:
                                    for l in nf.loops:
                                        l[uv_layer].uv = vert_uv[l.vert]
                            except ValueError:
                                pass
                        closed = True
                    break
                loop_verts.append(nxt)
                cur = nxt
            if not closed:
                break
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def _bury_skirt_below_ground(objs, depth):
    """Place the burial_skirt cut seam at z = 0 so the vertical skirt stays underground."""
    for o in objs:
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
                if any(v.co.z <= -depth + 1e-3 for v in f.verts) and any(v.co.z > -depth + 1e-3 for v in f.verts):
                    for loop in f.loops:
                        if loop.vert.co.z <= -depth + 1e-3:
                            uv = loop[uv_layer].uv
                            loop[uv_layer].uv = uv + (center - uv) * 0.04
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def _bake_z_graded_roughness(objs, z_wet=0.45, z_dry=0.62, wet_min=0.38, wet_max=0.52, dry_min=0.60):
    """Bake world Z onto the existing UV layout and rewrite the roughness image channel in place.

    Lower wet waterline flanks (z < 0.55 m) get smoother wet roughness (0.38..0.52);
    drier upper ridges stay matte (>= 0.60); metallic is forced to 0.0.
    Storing directly in the roughness texture ensures identical shading in Cycles and glTF Class B export.
    """
    scene = bpy.context.scene
    z_max_ref = 1.25

    for o in objs:
        if not o.data.materials:
            continue
        mat = o.data.materials[0]
        if not mat or not mat.node_tree:
            continue
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue

        # Force metallic to 0.0
        ms = bsdf.inputs["Metallic"]
        if ms.is_linked:
            for link in list(ms.links):
                mat.node_tree.links.remove(link)
        ms.default_value = 0.0

        rs = bsdf.inputs["Roughness"]
        if not rs.is_linked:
            continue
        r_node = rs.links[0].from_node
        r_channels = (0, 1, 2)
        if r_node.type in ("SEPARATE_COLOR", "SEPRGB", "SEPARATE_RGB"):
            r_channels = {"Red": (0,), "Green": (1,), "Blue": (2,)}.get(rs.links[0].from_socket.name, (1,))
            src_sock = r_node.inputs[0]
            if not src_sock.is_linked or src_sock.links[0].from_node.type != "TEX_IMAGE":
                continue
            tex_node = src_sock.links[0].from_node
        elif r_node.type == "TEX_IMAGE":
            tex_node = r_node
        else:
            continue
        orig_img = tex_node.image
        if orig_img is None:
            continue

        w, h = orig_img.size
        z_img = bpy.data.images.new("_tmp_shore_z", w, h, alpha=False, float_buffer=True)
        z_img.colorspace_settings.name = "Non-Color"

        z_mat = bpy.data.materials.new("_tmp_shore_z_mat")
        z_mat.use_nodes = True
        nt = z_mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        geom = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.clamp = True
        mr.inputs["From Min"].default_value = 0.0
        mr.inputs["From Max"].default_value = z_max_ref
        mr.inputs["To Min"].default_value = 0.0
        mr.inputs["To Max"].default_value = 1.0
        em = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(geom.outputs["Position"], sep.inputs["Vector"])
        nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        bake_tex = nt.nodes.new("ShaderNodeTexImage")
        bake_tex.image = z_img
        nt.nodes.active = bake_tex

        saved_mats = list(o.data.materials)
        o.data.materials.clear()
        o.data.materials.append(z_mat)

        vrlib.use_cycles_cpu(scene, 1)
        scene.cycles.use_denoising = False
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.bake(type="EMIT", use_selected_to_active=False, margin=16)

        o.data.materials.clear()
        for m in saved_mats:
            o.data.materials.append(m)

        z_buf = np.empty(w * h * 4, dtype=np.float32)
        z_img.pixels.foreach_get(z_buf)
        z_world = z_buf.reshape(h, w, 4)[..., 0] * z_max_ref

        r_buf = np.empty(w * h * 4, dtype=np.float32)
        orig_img.pixels.foreach_get(r_buf)
        px = r_buf.reshape(h, w, 4)

        u = np.clip((z_world - z_wet) / max(z_dry - z_wet, 1e-5), 0.0, 1.0)
        t_dry = u * u * (3.0 - 2.0 * u)

        for ch in r_channels:
            r_orig = px[..., ch]
            med = float(np.median(r_orig))
            r_wet = np.clip(0.44 + (r_orig - med) * 0.65, wet_min, wet_max)
            r_dry = np.maximum(r_orig, dry_min)
            px[..., ch] = r_wet * (1.0 - t_dry) + r_dry * t_dry
        if r_channels == (1,):
            px[..., 2] = 0.0  # Blue channel = metallic -> 0.0

        new_img = bpy.data.images.new(orig_img.name + "_zrough", w, h, alpha=True)
        new_img.colorspace_settings.name = orig_img.colorspace_settings.name
        new_img.pixels.foreach_set(px.astype(np.float32).ravel())
        new_img.pack()
        tex_node.image = new_img

        bpy.data.images.remove(z_img)
        bpy.data.materials.remove(z_mat)


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    _close_pinholes(objs)
    vrmeshy.normalize(objs, height=1.05, yaw_deg=-84.5)
    vrmeshy.grade_basecolor(objs, "#5D6064", strength=0.15)
    vrmeshy.burial_skirt(objs, depth=0.35)
    _bury_skirt_below_ground(objs, depth=0.35)
    _bake_z_graded_roughness(objs, z_wet=0.45, z_dry=0.62, wet_min=0.38, wet_max=0.52, dry_min=0.60)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)

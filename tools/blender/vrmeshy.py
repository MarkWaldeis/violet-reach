"""Load and prepare Meshy raw models inside Blender.

The raw GLB lives outside the repo in the Meshy library (VR_MESHY_DIR, default
~/Desktop/Violet Reach Meshy); meshy.json in the asset folder pins its sha256 so a
build.py can verify and reuse the file without it entering the repository.

All helpers are deterministic, take lists of mesh objects and work on the mesh
data in place. Image helpers create NEW images and re-point the texture nodes —
the original textures are never overwritten.
"""
import hashlib
import json
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vrlib

DEFAULT_MESHY_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Violet Reach Meshy")


def meshy_dir():
    return os.environ.get("VR_MESHY_DIR", DEFAULT_MESHY_DIR)


def load_raw(asset_dir):
    """Import the raw GLB that meshy.json records; aborts clearly on a mismatch."""
    with open(os.path.join(asset_dir, "meshy.json")) as f:
        meta = json.load(f)
    model = meta.get("model") or {}
    rel = model.get("file")
    if not rel:
        raise SystemExit(f"meshy.json in {asset_dir} has no model.file")
    path = os.path.join(meshy_dir(), rel.replace("/", os.sep))
    if not os.path.isfile(path):
        raise SystemExit(f"Meshy raw model missing: {path} (check VR_MESHY_DIR)")
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != model.get("sha256"):
        raise SystemExit(f"{path}: sha256 {digest.hexdigest()} does not match "
                         f"meshy.json ({model.get('sha256')}); the raw model changed")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = set(bpy.data.objects) - before
    meshes = [o for o in new if o.type == "MESH"]
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    if not meshes:
        raise SystemExit(f"{path}: the Meshy export contains no mesh objects")
    return meshes


def _apply(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def normalize(objs, size_m=None, height=None, yaw_deg=0.0):
    """Scale to metres, rotate by yaw, then put the origin at the footprint centre.

    size_m=(L,W,H): the object is scaled uniformly so it fits inside the box —
    dimensions are paired largest-to-largest and the binding axis decides.
    height: scale so the world Z extent is exactly this value.
    Result: xy centred on the bounding footprint, z_min = 0.
    """
    lo, hi = vrlib.world_bounds(objs)
    dims = np.array([hi.x - lo.x, hi.y - lo.y, hi.z - lo.z], dtype=float)
    if size_m is not None:
        ratios = np.sort(np.array(size_m, dtype=float))[::-1] / np.maximum(np.sort(dims)[::-1], 1e-9)
        scale = float(ratios.min())
    elif height is not None:
        scale = float(height) / max(dims[2], 1e-9)
    else:
        raise ValueError("normalize needs size_m or height")
    rs = Matrix.Rotation(math.radians(yaw_deg), 4, "Z") @ Matrix.Scale(scale, 4)
    corners = [rs @ Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    nlo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    nhi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    offset = Vector((-(nlo.x + nhi.x) / 2, -(nlo.y + nhi.y) / 2, -nlo.z))
    m = Matrix.Translation(offset) @ rs
    for o in objs:
        o.matrix_world = m @ o.matrix_world
    _apply(objs)
    return objs


def _each_bmesh(objs, fn):
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        try:
            fn(bm)
        finally:
            bm.to_mesh(o.data)
            o.data.update()
            bm.free()


def _loose_components(bm):
    unseen = set(bm.verts)
    comps = []
    while unseen:
        seed = unseen.pop()
        comp = [seed]
        stack = [seed]
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                w = e.other_vert(v)
                if w in unseen:
                    unseen.remove(w)
                    comp.append(w)
                    stack.append(w)
        faces = {f for v in comp for f in v.link_faces}
        comps.append((comp, sum(len(f.verts) - 2 for f in faces)))
    return comps


def drop_loose(objs, min_fraction=0.002):
    """Delete floating fragments whose triangle share is under min_fraction.

    The largest component is always kept, even below the threshold.
    """
    removed = 0

    def go(bm):
        nonlocal removed
        # glTF imports are often fully vertex-split (each face its own island):
        # weld by position first so components reflect real connectivity.
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-4)
        total = sum(len(f.verts) - 2 for f in bm.faces)
        comps = sorted(_loose_components(bm), key=lambda c: c[1], reverse=True)
        for comp, tris in comps[1:]:
            if tris < min_fraction * total:
                bmesh.ops.delete(bm, geom=comp, context="VERTS")
                removed += tris

    _each_bmesh(objs, go)
    return removed


def _floor_faces(bm, z, eps=1e-4):
    """Faces fully on plane z — the cap that _bisect_floor leaves behind."""
    return [f for f in bm.faces if all(abs(v.co.z - z) < eps for v in f.verts)]


def _bisect_floor(bm, z):
    """Cut at plane z, drop everything below and close the cut facing down."""
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z), plane_no=(0, 0, 1),
                                 clear_inner=True, clear_outer=False)
    cuts = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if cuts:
        bmesh.ops.holes_fill(bm, edges=cuts)
    # holes_fill does not guarantee the cap's winding; the cap must face down.
    for f in _floor_faces(bm, z):
        if f.normal.z > 0:
            f.normal_flip()


def cut_below(objs, z):
    """Slice off everything under plane z and cap the cut."""
    _each_bmesh(objs, lambda bm: _bisect_floor(bm, z))


def fix_normals(objs):
    """Recalculate every face normal to point outwards."""
    for o in objs:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")


def _materials(objs):
    mats = []
    for o in objs:
        for m in o.data.materials:
            if m and m.node_tree and m not in mats:
                mats.append(m)
    return mats


def _bsdf(mat):
    return mat.node_tree.nodes.get("Principled BSDF")


def _basecolor_image_nodes(objs):
    """TEX_IMAGE nodes feeding a Principled Base Color input, deduplicated."""
    nodes = []
    for mat in _materials(objs):
        bsdf = _bsdf(mat)
        if bsdf is None:
            continue
        socket = bsdf.inputs["Base Color"]
        for link in socket.links:
            node = link.from_node
            if node.type == "TEX_IMAGE" and node.image and node not in nodes:
                nodes.append(node)
    return nodes


def _image_pixels(img):
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


def _replace_image(img, px, suffix):
    new = bpy.data.images.new(img.name + suffix, img.size[0], img.size[1], alpha=True)
    # Assigning colorspace clears the pixel buffer — it must come before the write.
    new.colorspace_settings.name = img.colorspace_settings.name
    new.pixels.foreach_set(px.astype(np.float32).ravel())
    new.pack()
    return new


def _swap_images(objs, mapping):
    if not mapping:
        return
    for mat in _materials(objs):
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image in mapping:
                node.image = mapping[node.image]


def _rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cmax = rgb.max(axis=-1)
    cmin = rgb.min(axis=-1)
    delta = cmax - cmin
    safe = np.maximum(delta, 1e-6)
    h = np.where(r == cmax, (cmax - b) / safe - (cmax - g) / safe,
                 np.where(g == cmax, 2.0 + (cmax - r) / safe - (cmax - b) / safe,
                          4.0 + (cmax - g) / safe - (cmax - r) / safe))
    h = np.where(delta > 1e-6, h / 6.0 % 1.0, 0.0)
    s = np.where(cmax > 1e-6, delta / np.maximum(cmax, 1e-6), 0.0)
    return np.stack([h, s, cmax], axis=-1)


def _hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    i = (np.floor(h * 6).astype(int)) % 6
    f = h * 6 - np.floor(h * 6)
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def grade_basecolor(objs, target_hex, strength=1.0):
    """Rotate hue and shift saturation/value of every base colour texture.

    The median HSV of the opaque texels is measured and moved toward the
    target sRGB hex by `strength`; the shift is applied to the whole texture so
    variation survives. Returns {old_image: new_image}.
    """
    h = target_hex.lstrip("#")
    target = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)
    tgt_hsv = _rgb_to_hsv(target.reshape(1, 1, 3))[0, 0]
    made = {}
    for node in _basecolor_image_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = _image_pixels(img)
        mask = px[..., 3] > 0.5
        if not mask.any():
            mask = np.ones(px.shape[:2], dtype=bool)
        hsv = _rgb_to_hsv(px[..., :3])
        sample = hsv[mask]
        mean_hue = math.atan2(np.sin(sample[:, 0] * 2 * math.pi).mean(),
                              np.cos(sample[:, 0] * 2 * math.pi).mean()) / (2 * math.pi) % 1.0
        med_s, med_v = np.median(sample[:, 1]), np.median(sample[:, 2])
        dh = ((tgt_hsv[0] - mean_hue + 0.5) % 1.0) - 0.5
        hsv[..., 0] = (hsv[..., 0] + dh * strength) % 1.0
        hsv[..., 1] = np.clip(hsv[..., 1] + (tgt_hsv[1] - med_s) * strength, 0, 1)
        hsv[..., 2] = np.clip(hsv[..., 2] + (tgt_hsv[2] - med_v) * strength, 0, 1)
        made[img] = _replace_image(img, np.concatenate([_hsv_to_rgb(hsv), px[..., 3:]], -1), "_graded")
    _swap_images(objs, made)
    return made


def _box_blur(channel, radius):
    pad = np.pad(channel, ((radius, radius), (0, 0)), mode="edge")
    c = np.concatenate([np.zeros((1, pad.shape[1])),
                        np.cumsum(pad, axis=0, dtype=np.float64)])
    out = (c[2 * radius + 1:] - c[:-(2 * radius + 1)]) / (2 * radius + 1)
    pad = np.pad(out, ((0, 0), (radius, radius)), mode="edge")
    c = np.concatenate([np.zeros((pad.shape[0], 1)),
                        np.cumsum(pad, axis=1, dtype=np.float64)], axis=1)
    return (c[:, 2 * radius + 1:] - c[:, :-(2 * radius + 1)]) / (2 * radius + 1)


def delight_basecolor(objs, radius_frac=0.25):
    """Divide large-scale baked lighting out of the base colour texture.

    Each texel is divided by the low-pass filtered luminance normalised to its
    median, so fine detail survives while broad shading gradients flatten.
    radius_frac is the filter radius as a fraction of the smaller image edge.
    """
    made = {}
    for node in _basecolor_image_nodes(objs):
        img = node.image
        if img in made:
            continue
        px = _image_pixels(img)
        mask = px[..., 3] > 0.5
        if not mask.any():
            mask = np.ones(px.shape[:2], dtype=bool)
        lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        fill = np.where(mask, lum, np.median(lum[mask]))
        radius = max(1, int(radius_frac * min(px.shape[0], px.shape[1])))
        lp = _box_blur(fill, radius)
        gain = lp / np.median(lp[mask])
        out = np.clip(px[..., :3] / np.maximum(gain, 0.05)[..., None], 0, 1)
        made[img] = _replace_image(img, np.concatenate([out, px[..., 3:]], -1), "_delit")
    _swap_images(objs, made)
    return made


def _clamp_linked_image(socket, floor, made):
    """Clamp the texture channel driving a linked BSDF input to >= floor."""
    node = socket.links[0].from_node
    channels = (0, 1, 2)
    if node.type == "SEPARATE_COLOR":
        channels = {"Red": (0,), "Green": (1,), "Blue": (2,)}.get(socket.links[0].from_socket.name, (0, 1, 2))
        src = node.inputs["Color"]
        if not src.links or src.links[0].from_node.type != "TEX_IMAGE":
            return
        node = src.links[0].from_node
    if node.type != "TEX_IMAGE" or not node.image:
        return
    img = node.image
    if img in made:
        return
    px = _image_pixels(img)
    for ch in channels:
        px[..., ch] = np.maximum(px[..., ch], floor)
    made[img] = _replace_image(img, px, "_clamped")


def clamp_material(objs, roughness_min=0.5, metallic=0.0):
    """Stone rules: metallic forced to `metallic`, roughness >= roughness_min.

    Texture-driven values get a new image with the channel clamped; plain
    factors are clamped in place. A linked metallic is replaced by the constant.
    """
    made = {}
    for mat in _materials(objs):
        bsdf = _bsdf(mat)
        if bsdf is None:
            continue
        ms = bsdf.inputs["Metallic"]
        if ms.is_linked:
            for link in list(ms.links):
                mat.node_tree.links.remove(link)
        ms.default_value = metallic
        rs = bsdf.inputs["Roughness"]
        if rs.is_linked:
            _clamp_linked_image(rs, roughness_min, made)
        else:
            rs.default_value = max(float(rs.default_value), roughness_min)
    _swap_images(objs, made)
    return made


def burial_skirt(objs, depth=0.3):
    """Extend the foot down by `depth` so the object sits in sloped ground.

    Cuts the mesh at a low slice (small enough to keep the shape, high enough to
    give the plug a real footprint), then extrudes the cut floor down. The final
    bottom is exactly `depth` under the previous lowest vertex.
    """
    def go(bm):
        if not bm.verts:
            return
        lo = min(v.co.z for v in bm.verts)
        hi = max(v.co.z for v in bm.verts)
        z0 = lo + min(depth * 0.75, max(0.02, 0.08 * (hi - lo)))
        _bisect_floor(bm, z0)
        floor = [f for f in _floor_faces(bm, z0) if f.normal.z < -0.5]
        if not floor:
            return
        res = bmesh.ops.extrude_face_region(bm, geom=floor)
        new_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=(0, 0, lo - depth - z0), verts=new_verts)
        # The source cap is now sandwiched between body and skirt — interior
        # geometry whose ring edges would be non-manifold and block decimation.
        bmesh.ops.delete(bm, geom=floor, context="FACES")

    _each_bmesh(objs, go)


def link_source(objs):
    """Move the prepared objects into the SOURCE collection."""
    for o in objs:
        vrlib.link_to_source(o)
    return objs

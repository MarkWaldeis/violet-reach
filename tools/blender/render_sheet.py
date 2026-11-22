"""blender -b <asset>.blend --python tools/blender/render_sheet.py -- <asset_dir> [--samples N] [--draft]

Renders the review sheet for the Blender quality gate: 8 turntable views, 2 close-ups,
a wireframe view and a clay view, with a 1.8 m figure for scale. Writes review/sheet.jpg,
review/hero.jpg, review/closeup.jpg and review/sheet.json.

--draft renders only one turntable view and the two close-ups to review/draft.jpg (not committed),
for fast iteration while modelling.
"""
import json
import math
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
import vrlib  # noqa: E402

args = vrlib.script_args()
asset_dir = os.path.abspath(args[0])
draft = "--draft" in args
samples = int(args[args.index("--samples") + 1]) if "--samples" in args else (32 if draft else 64)
TILE = (960, 720)
review_dir = os.path.join(asset_dir, "review")
os.makedirs(review_dir, exist_ok=True)
tiles_dir = tempfile.TemporaryDirectory(prefix=".tiles-", dir=review_dir)
tmp_dir = tiles_dir.name

scene = bpy.context.scene
objs = vrlib.source_objects()
lo, hi = vrlib.world_bounds(objs)
size = hi - lo
centre = (lo + hi) / 2
radius = max(size) / 2 * 1.3
stats = {"triangles": vrlib.triangle_count(objs), "size_m": [round(v, 3) for v in size], "objects": len(objs)}


def studio():
    world = bpy.data.worlds.new("vr_studio")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    # Daylight gradient: warm horizon, blue zenith, so glossy surfaces have something to reflect.
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.42, (0.20, 0.24, 0.16, 1)
    e[1].position, e[1].color = 0.85, (0.10, 0.28, 0.80, 1)
    horizon = e.new(0.51)
    horizon.color = (0.62, 0.78, 0.96, 1)
    remap = nt.nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = -1
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], remap.inputs["Value"])
    nt.links.new(remap.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.9
    scene.world = world

    sun = bpy.data.lights.new("vr_sun", "SUN")
    sun.energy = 4.2
    sun.angle = math.radians(2.0)
    sun.color = (1.0, 0.95, 0.86)
    sun_obj = bpy.data.objects.new("vr_sun", sun)
    sun_obj.rotation_euler = (math.radians(52), 0, math.radians(35))
    scene.collection.objects.link(sun_obj)

    bpy.ops.mesh.primitive_plane_add(size=max(60, radius * 30), location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "vr_ground"
    gmat = bpy.data.materials.new("vr_ground")
    gmat.use_nodes = True
    b = gmat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.20, 0.23, 0.17, 1)
    b.inputs["Roughness"].default_value = 0.9
    ground.data.materials.append(gmat)

    figure_xy = scene.get("vr_review_figure", (centre.x, hi.y + 0.5))
    objects = []
    if "vr_review_figure" in scene:
        x, y = figure_xy
        for dx, dy, z, girth, depth in ((0,0,1.14,.24,.69),(-.12,0,.39,.095,.76),
                                         (.12,0,.39,.095,.76),(-.31,0,1.07,.085,.64),
                                         (.31,0,1.05,.085,.61)):
            bpy.ops.mesh.primitive_cylinder_add(radius=girth, depth=depth, location=(x+dx,y+dy,z))
            objects.append(bpy.context.object)
    else:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.5, location=(*figure_xy, 0.75))
        objects.append(bpy.context.object)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(*figure_xy, 1.65))
    objects.append(bpy.context.object)
    fmat = bpy.data.materials.new("vr_figure")
    fmat.use_nodes = True
    fmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.35, 0.05, 1)
    for o in objects:
        o.data.materials.append(fmat)
    return objects


def override_material(kind):
    mat = bpy.data.materials.new("vr_override_" + kind)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.7
    if kind == "wire":
        wire = nt.nodes.new("ShaderNodeWireframe")
        wire.use_pixel_size = True
        wire.inputs["Size"].default_value = 0.6
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.inputs["Color1"].default_value = (0.75, 0.75, 0.75, 1)
        mix.inputs["Color2"].default_value = (0.02, 0.02, 0.02, 1)
        nt.links.new(wire.outputs["Fac"], mix.inputs["Fac"])
        nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1)
    return mat


figure = studio()
cam_data = bpy.data.cameras.new("vr_cam")
cam_data.lens = 50
cam = bpy.data.objects.new("vr_cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

vrlib.use_cycles_cpu(scene, samples)
scene.render.resolution_x, scene.render.resolution_y = TILE
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"


def aim(azimuth_deg, elevation_deg, target, distance):
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    cam.location = target + Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el))) * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


fov = 2 * math.atan(min(cam_data.sensor_width, cam_data.sensor_width * TILE[1] / TILE[0] * 1.0) / (2 * cam_data.lens))
full_distance = radius / math.sin(fov / 2)
views = [("turn_%03d" % a, a, 14, centre, full_distance) for a in range(20, 380, 45)]
if "vr_review_hero" in scene:
    az, el, scale, z_offset = scene["vr_review_hero"]
    views[0] = ("turn_%03d" % (az % 360), az, el, centre + Vector((0, 0, z_offset)), full_distance * scale)
detail_target = Vector((centre.x, centre.y, lo.z + size.z * 0.62))
views.append(("closeup_upper", 65, 8, detail_target, full_distance * 0.42))
views.append(("closeup_base", 205, 22, Vector((centre.x, centre.y, lo.z + size.z * 0.16)), full_distance * 0.40))
if "vr_review_base" in scene:
    x, y, z, az, el, scale = scene["vr_review_base"]
    views[9] = ("closeup_base", az, el, Vector((x, y, z)), full_distance * scale)

if draft:
    views = [views[0], views[8], views[9]]

started = time.time()
tiles = []
for name, az, el, target, dist in views:
    for o in figure:
        o.hide_render = name.startswith("closeup")
    aim(az, el, target, dist)
    scene.render.filepath = os.path.join(tmp_dir, name + ".png")
    bpy.ops.render.render(write_still=True)
    tiles.append(scene.render.filepath)

for o in figure:
    o.hide_render = False
for kind in (() if draft else ("wire", "clay")):
    bpy.context.view_layer.material_override = override_material(kind)
    aim(20, 14, centre, full_distance)
    scene.render.filepath = os.path.join(tmp_dir, kind + ".png")
    bpy.ops.render.render(write_still=True)
    tiles.append(scene.render.filepath)
bpy.context.view_layer.material_override = None


def load(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[:, :, :3]


def save_jpeg(pixels, path, quality):
    h, w, _ = pixels.shape
    img = bpy.data.images.new("vr_out", w, h, alpha=False)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = pixels
    img.pixels.foreach_set(rgba.ravel())
    out = bpy.data.scenes.new("vr_save")
    out.view_settings.view_transform = "Standard"
    out.render.image_settings.file_format = "JPEG"
    out.render.image_settings.quality = quality
    img.save_render(path, scene=out)
    bpy.data.scenes.remove(out)
    bpy.data.images.remove(img)


cols, rows, gap = (3, 1, 8) if draft else (4, 3, 8)
sheet = np.full((rows * TILE[1] + (rows + 1) * gap, cols * TILE[0] + (cols + 1) * gap, 3), 0.02, dtype=np.float32)
for i, path in enumerate(tiles):
    r, c = divmod(i, cols)
    # Image rows are stored bottom-up, so the first sheet row goes at the top of the array.
    y = sheet.shape[0] - (r + 1) * (TILE[1] + gap)
    x = gap + c * (TILE[0] + gap)
    sheet[y:y + TILE[1], x:x + TILE[0]] = load(path)
save_jpeg(sheet, os.path.join(review_dir, "draft.jpg" if draft else "sheet.jpg"), 88)
if not draft:
    save_jpeg(load(tiles[0]), os.path.join(review_dir, "hero.jpg"), 90)
    save_jpeg(load(tiles[8]), os.path.join(review_dir, "closeup.jpg"), 90)
tiles_dir.cleanup()

stats.update({"samples": samples, "render_seconds": round(time.time() - started, 1), "blender": bpy.app.version_string,
              "tiles": [os.path.basename(p)[:-4] for p in tiles]})
if not draft:
    with open(os.path.join(review_dir, "sheet.json"), "w") as f:
        json.dump(stats, f, indent=2)
        f.write("\n")
print("VR_RESULT", stats, flush=True)

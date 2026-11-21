"""Einheitliche Materialprobe: Kugel Ø 1,5 m, Block 0,95 m, Bodenplatte 3 × 2,4 m.

Aufruf über python3 tools/vr.py swatches. Cycles CPU; keine externen Python-Pakete.
"""
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils import Vector
import vrlib
import vrmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/materials/swatches"


def light(scene, name, kind, location, energy, size):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    if kind == "AREA":
        data.shape = "DISK"
        data.size = size
    else:
        data.angle = size
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector((0, 0, .5)) - obj.location).to_track_quat("-Z", "Y").to_euler()


def scene_setup():
    scene = vrlib.reset_scene()
    vrlib.use_cycles_cpu(scene, 48)
    scene.cycles.seed = 1701
    scene.render.resolution_x, scene.render.resolution_y = 800, 640
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.36, .43, .55, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .45
    scene.world = world
    light(scene, "Weiche Hauptquelle", "AREA", (-3, -4, 6), 650, 4)
    light(scene, "Kantenlicht", "AREA", (3, 2, 4), 450, 3)
    light(scene, "Sonne", "SUN", (-6, -4, 8), 1.6, math.radians(3))
    bpy.ops.object.camera_add(location=(3.4, -6, 3.3))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0, 0, .6)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 4.6
    scene.camera = camera
    bpy.ops.mesh.primitive_plane_add(size=200)
    floor = bpy.context.object
    neutral = bpy.data.materials.new("Studio neutral")
    neutral.use_nodes = True
    neutral.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.085, .10, .12, 1)
    neutral.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .85
    floor.data.materials.append(neutral)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=64, radius=.75, location=(-.67, 0, .81))
    sphere = bpy.context.object
    for poly in sphere.data.polygons:
        poly.use_smooth = True
    bpy.ops.mesh.primitive_cube_add(size=1, location=(.88, .05, .56))
    block = bpy.context.object
    block.scale = (.95, .95, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = block.modifiers.new("Steinkante 35 mm", "BEVEL")
    bevel.width, bevel.segments = .035, 4
    block.modifiers.new("Flächennormalen", "WEIGHTED_NORMAL")
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, .025))
    slab = bpy.context.object
    slab.scale = (3, 2.4, .05)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = slab.modifiers.new("Plattenkante", "BEVEL")
    bevel.width, bevel.segments = .015, 3
    bpy.ops.object.text_add()
    text = bpy.context.object
    text.parent = camera
    text.location = (-2.12, -1.62, -1)
    text.rotation_euler = (0, 0, 0)
    text.data.size = .14
    label = bpy.data.materials.new("Beschriftung")
    label.use_nodes = True
    bsdf = label.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
    bsdf.inputs["Emission Color"].default_value = (.8, .86, .91, 1)
    bsdf.inputs["Emission Strength"].default_value = 1
    text.data.materials.append(label)
    return scene, (sphere, block, slab), text


def contact_sheet(paths):
    cols, width, height, gap = 3, 800, 640, 12
    rows = math.ceil(len(paths) / cols)
    sheet = np.full((rows * (height + gap) + gap, cols * (width + gap) + gap, 4), .035, dtype=np.float32)
    sheet[:, :, 3] = 1
    for i, path in enumerate(paths):
        img = bpy.data.images.load(str(path), check_existing=False)
        pixels = np.empty(width * height * 4, dtype=np.float32)
        img.pixels.foreach_get(pixels)
        x = gap + (i % cols) * (width + gap)
        y = sheet.shape[0] - (i // cols + 1) * (height + gap)
        sheet[y:y + height, x:x + width] = pixels.reshape(height, width, 4)
        bpy.data.images.remove(img)
    img = bpy.data.images.new("Kontaktblatt", sheet.shape[1], sheet.shape[0], alpha=False)
    img.pixels.foreach_set(sheet.ravel())
    scene = bpy.data.scenes.new("Kontaktblatt speichern")
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 87
    img.save_render(str(OUT.parent / "swatches.jpg"), scene=scene)


def main():
    start = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    scene, objects, label = scene_setup()
    try:
        vrmat.get("not_a_material")
    except KeyError:
        pass
    else:
        raise AssertionError("Unbekannter Materialname wurde akzeptiert")
    paths = []
    for name in vrmat.SPECS:
        mat = vrmat.get(name)
        assert mat is vrmat.get(name), "Materialcache inkonsistent"
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        assert bsdf.inputs["Alpha"].default_value == 1
        assert bsdf.inputs["Transmission Weight"].default_value == 0
        for obj in objects:
            obj.data.materials.clear()
            obj.data.materials.append(mat)
        label.data.body = name + "   /   1 m   /   Cycles CPU"
        path = OUT / f"{name}.png"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    contact_sheet(paths)
    print("VR_RESULT", json.dumps({"materials": len(paths), "device": scene.cycles.device,
                                   "samples": scene.cycles.samples, "seconds": round(time.monotonic() - start, 1),
                                   "contact_sheet": "art/materials/swatches.jpg"}), flush=True)


if __name__ == "__main__":
    main()

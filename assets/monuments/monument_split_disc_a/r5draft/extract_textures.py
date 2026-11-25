"""Extract packed textures for offline inspection."""
import os

import bpy

out = os.path.dirname(os.path.abspath(__file__))
for img in bpy.data.images:
    if not img.packed_file or not img.size[0]:
        continue
    img.file_format = "PNG"
    path = os.path.join(out, "tex_" + img.name.replace("/", "_") + ".png")
    img.save_render(path) if False else None
    # save_render applies scene color management; use a copy render target for exactness.
    scene = bpy.context.scene
    old_format = scene.render.image_settings.file_format
    old_mode = scene.render.image_settings.color_mode
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    old_path = img.filepath_raw
    img.filepath_raw = path
    img.save()
    img.filepath_raw = old_path
    scene.render.image_settings.file_format = old_format
    scene.render.image_settings.color_mode = old_mode
    print("VR_TEXTURE", img.name, path, tuple(img.size), flush=True)
print("VR_RESULT", {"images": len(bpy.data.images)}, flush=True)

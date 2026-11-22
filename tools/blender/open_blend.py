"""First --python script for vr.py: opens the .blend named by VR_OPEN_BLEND.

`blender -b <file>` hangs on this machine (Blender 5.2), so the launcher always starts
with `-b --factory-startup` and runs this script first; later --python scripts then
execute inside the loaded file.
"""
import os

import bpy

bpy.ops.wm.open_mainfile(filepath=os.path.abspath(os.environ["VR_OPEN_BLEND"]))

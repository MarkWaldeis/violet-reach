"""Orthographic leaf-cluster albedo/coverage tiles for alpha-tested LOD cards."""
import math

import bpy
import numpy as np


class FoliageAtlas:
    def __init__(self, name, source, size, count, occlusion=None):
        self.size = size
        self.columns = math.ceil(math.sqrt(count))
        self.tile = size // self.columns
        if self.tile < 8:
            raise ValueError("Foliage atlas has fewer than eight pixels per card")
        self.pixels = np.zeros((size, size, 4), dtype=np.float32)
        self.source = np.array(source.pixels[:], dtype=np.float32).reshape(source.size[1], source.size[0], 4)
        self.occlusion = np.array(occlusion.pixels[:], dtype=np.float32).reshape(occlusion.size[1], occlusion.size[0], 4) if occlusion else None
        self.ao = np.ones((size, size, 4), dtype=np.float32)
        self.index = 0
        self.image = bpy.data.images.new(name, size, size, alpha=True)
        self.image.colorspace_settings.name = "sRGB"

    def add(self, group, basis, centre, low, high):
        x0, y0 = (self.index % self.columns) * self.tile, (self.index // self.columns) * self.tile
        self.index += 1
        margin = 2
        extent = self.tile - margin * 2
        tile = self.pixels[y0:y0 + self.tile, x0:x0 + self.tile]
        ao_tile = self.ao[y0:y0 + self.tile, x0:x0 + self.tile]
        span = np.maximum(high - low, 1e-6)
        for leaf in group:
            for positions, texture in leaf[4]:
                points = (((positions - centre) @ basis.T - low) / span) * extent + margin
                a, b, c = points
                ab, ac = b - a, c - a
                determinant = ab[0] * ac[1] - ab[1] * ac[0]
                if abs(determinant) < 1e-9:
                    continue
                minimum = np.maximum(margin, np.floor(points.min(axis=0)).astype(int) - 1)
                maximum = np.minimum(self.tile - margin - 1, np.ceil(points.max(axis=0)).astype(int) + 1)
                x, y = np.meshgrid(np.arange(minimum[0], maximum[0] + 1) + .5, np.arange(minimum[1], maximum[1] + 1) + .5)
                u = ((x - a[0]) * ac[1] - (y - a[1]) * ac[0]) / determinant
                v = (ab[0] * (y - a[1]) - ab[1] * (x - a[0])) / determinant
                inside = (u >= -.02) & (v >= -.02) & (u + v <= 1.02)
                coordinates = texture[0] + u[..., None] * (texture[1] - texture[0]) + v[..., None] * (texture[2] - texture[0])
                tx = np.clip((coordinates[..., 0] * self.source.shape[1]).astype(int), 0, self.source.shape[1] - 1)
                ty = np.clip((coordinates[..., 1] * self.source.shape[0]).astype(int), 0, self.source.shape[0] - 1)
                colour = self.source[ty, tx]
                inside &= colour[..., 3] > .1
                region = tile[minimum[1]:maximum[1] + 1, minimum[0]:maximum[0] + 1]
                replace = inside & ((region[..., 3] == 0) | (colour[..., :3].sum(axis=2) > region[..., :3].sum(axis=2)))
                region[replace, :3] = colour[replace, :3]
                region[replace, 3] = colour[replace, 3]
                if self.occlusion is not None:
                    ao_tile[minimum[1]:maximum[1] + 1, minimum[0]:maximum[0] + 1][replace] = self.occlusion[ty, tx][replace]
        covered = tile[..., 3] > 0
        for _ in range(margin):
            old = covered.copy()
            for dy, dx in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                neighbour = np.roll(old, (dy, dx), (0, 1))
                fill = neighbour & ~covered
                tile[fill, :3] = np.roll(tile[..., :3], (dy, dx), (0, 1))[fill]
                ao_tile[fill] = np.roll(ao_tile, (dy, dx), (0, 1))[fill]
                covered |= neighbour
        return [((x0 + x) / self.size, (y0 + y) / self.size)
                for x, y in [(margin, margin), (margin + extent, margin),
                             (margin + extent, margin + extent), (margin, margin + extent)]]

    def material(self):
        self.image.pixels.foreach_set(self.pixels.ravel())
        self.image.pack()
        material = bpy.data.materials.new(self.image.name)
        material.use_nodes = True
        material.use_backface_culling = False
        nodes, links = material.node_tree.nodes, material.node_tree.links
        shader = nodes["Principled BSDF"]
        shader.inputs["Metallic"].default_value = 0
        shader.inputs["Roughness"].default_value = .76
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = self.image
        links.new(texture.outputs["Color"], shader.inputs["Base Color"])
        clip = nodes.new("ShaderNodeMath")
        clip.operation = "GREATER_THAN"
        clip.inputs[1].default_value = .35
        links.new(texture.outputs["Alpha"], clip.inputs[0])
        links.new(clip.outputs[0], shader.inputs["Alpha"])
        if self.occlusion is not None:
            ao = bpy.data.images.new(self.image.name + "_occlusion", self.size, self.size, alpha=False)
            ao.colorspace_settings.name = "Non-Color"
            ao.pixels.foreach_set(self.ao.ravel())
            ao.pack()
            group = bpy.data.node_groups.get("glTF Material Output")
            if group is None:
                group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
                group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
            output = nodes.new("ShaderNodeGroup")
            output.node_tree = group
            node = nodes.new("ShaderNodeTexImage")
            node.image = ao
            links.new(node.outputs["Color"], output.inputs["Occlusion"])
        return material

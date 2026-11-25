"""Orthographic leaf-cluster albedo/coverage tiles for alpha-tested LOD cards."""
import math

import bpy
import numpy as np


class FoliageAtlas:
    def __init__(self, name, source, size, count, occlusion=None, supersample=4, alpha_cutoff=.35):
        self.size = size
        self.columns = math.ceil(math.sqrt(count))
        self.tile = size // self.columns
        if self.tile < 8:
            raise ValueError("Foliage atlas has fewer than eight pixels per card")
        self.supersample = int(supersample)
        if not 1 <= self.supersample <= 8:
            raise ValueError("Foliage atlas supersampling must be between 1 and 8")
        self.alpha_cutoff = float(alpha_cutoff)
        if not 0 <= self.alpha_cutoff <= 1:
            raise ValueError("Foliage alpha cutoff must be between 0 and 1")
        self.pixels = np.zeros((size, size, 4), dtype=np.float32)
        self.source = np.array(source.pixels[:], dtype=np.float32).reshape(source.size[1], source.size[0], 4)
        self.occlusion = np.array(occlusion.pixels[:], dtype=np.float32).reshape(occlusion.size[1], occlusion.size[0], 4) if occlusion else None
        self.source_constant = self.source[0, 0].copy() if np.all(self.source == self.source[0, 0]) else None
        self.occlusion_constant = (self.occlusion[0, 0].copy() if self.occlusion is not None
                                   and np.all(self.occlusion == self.occlusion[0, 0]) else None)
        self.ao = np.ones((size, size, 4), dtype=np.float32)
        high_size = self.tile * self.supersample
        self._transmittance = np.ones((high_size, high_size), dtype=np.float32)
        self._colour_sum = np.zeros((high_size, high_size, 3), dtype=np.float32)
        self._ao_sum = np.zeros((high_size, high_size, 4), dtype=np.float32) if self.occlusion is not None else None
        self.index = 0
        self.image = bpy.data.images.new(name, size, size, alpha=True)
        self.image.colorspace_settings.name = "sRGB"

    @staticmethod
    def _sample_nearest(image, coordinates):
        """Point-sample source texels at stratified supersample positions."""
        height, width = image.shape[:2]
        x = np.clip(np.floor(coordinates[..., 0] * width).astype(np.int32), 0, width - 1)
        y = np.clip(np.floor(coordinates[..., 1] * height).astype(np.int32), 0, height - 1)
        return image[y, x]

    @staticmethod
    def _dilate_padding(tile, ao_tile, margin):
        """Fill RGB/AO padding from covered neighbours without wrapping at tile borders."""
        covered = tile[..., 3] > 0
        for _ in range(margin):
            if not covered.any():
                break
            known = np.pad(covered, 1, constant_values=False)
            colour = np.pad(tile[..., :3], ((1, 1), (1, 1), (0, 0)), constant_values=0)
            occlusion = np.pad(ao_tile, ((1, 1), (1, 1), (0, 0)), constant_values=0)
            height, width = covered.shape
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not dy and not dx:
                        continue
                    yslice = slice(1 + dy, 1 + dy + height)
                    xslice = slice(1 + dx, 1 + dx + width)
                    fill = known[yslice, xslice] & ~covered
                    if not fill.any():
                        continue
                    tile[..., :3][fill] = colour[yslice, xslice][fill]
                    ao_tile[fill] = occlusion[yslice, xslice][fill]
                    covered |= known[yslice, xslice]

    def add(self, group, basis, centre, low, high):
        x0, y0 = (self.index % self.columns) * self.tile, (self.index // self.columns) * self.tile
        self.index += 1
        margin = 2
        extent = self.tile - margin * 2
        tile = self.pixels[y0:y0 + self.tile, x0:x0 + self.tile]
        ao_tile = self.ao[y0:y0 + self.tile, x0:x0 + self.tile]
        span = np.maximum(high - low, 1e-6)
        factor = self.supersample
        high_size = self.tile * factor
        transmittance = self._transmittance
        transmittance.fill(1)
        colour_sum = self._colour_sum
        colour_sum.fill(0)
        ao_sum = self._ao_sum
        if ao_sum is not None:
            ao_sum.fill(0)
        sample_min = margin * factor
        sample_max = (self.tile - margin) * factor - 1
        normal = np.cross(basis[0], basis[1])
        triangles = []
        for leaf in group:
            for positions, texture in leaf[4]:
                positions = np.asarray(positions, dtype=np.float32)
                texture = np.asarray(texture, dtype=np.float32)
                depth = float(np.dot(positions.mean(axis=0) - centre, normal))
                triangles.append((depth, positions, texture))
        triangles.sort(key=lambda item: item[0], reverse=True)
        for _, positions, texture in triangles:
            points = ((((positions - centre) @ basis.T - low) / span) * extent + margin).astype(np.float32)
            points *= factor
            a, b, c = points
            ab, ac = b - a, c - a
            determinant = ab[0] * ac[1] - ab[1] * ac[0]
            if abs(determinant) < 1e-9:
                continue
            minimum = np.maximum(sample_min, np.floor(points.min(axis=0)).astype(int) - 1)
            maximum = np.minimum(sample_max, np.ceil(points.max(axis=0)).astype(int) + 1)
            if (minimum > maximum).any():
                continue
            xslice = slice(minimum[0], maximum[0] + 1)
            yslice = slice(minimum[1], maximum[1] + 1)
            open_transmittance = transmittance[yslice, xslice] > 1e-6
            if not open_transmittance.any():
                continue
            xs = (np.arange(minimum[0], maximum[0] + 1, dtype=np.float32) + .5)[None, :]
            ys = (np.arange(minimum[1], maximum[1] + 1, dtype=np.float32) + .5)[:, None]
            u_unnormalised = xs * ac[1] - ys * ac[0] + (a[1] * ac[0] - a[0] * ac[1])
            v_unnormalised = ys * ab[0] - xs * ab[1] + (a[0] * ab[1] - a[1] * ab[0])
            # Exact inside tests are intentional here: edge softness comes from the
            # supersamples, not from inflating the triangle by a binary tolerance.  The
            # barycentric division is only needed for the sparse active samples below.
            epsilon = abs(float(determinant)) * 1e-7
            if determinant > 0:
                inside = ((u_unnormalised >= -epsilon) & (v_unnormalised >= -epsilon)
                          & (u_unnormalised + v_unnormalised <= determinant + epsilon))
            else:
                inside = ((u_unnormalised <= epsilon) & (v_unnormalised <= epsilon)
                          & (u_unnormalised + v_unnormalised >= determinant - epsilon))
            if not inside.any():
                continue
            # In dense canopies most later triangles are already hidden behind opaque
            # coverage.  Only evaluate samples that can still contribute; opaque ordering
            # follows the projection direction, so this is visibility culling rather than
            # a change in alpha coverage.
            active = inside & open_transmittance
            local_y, local_x = np.nonzero(active)
            if not len(local_y):
                continue
            u = u_unnormalised[local_y, local_x] / determinant
            v = v_unnormalised[local_y, local_x] / determinant
            coordinates = texture[0] + u[:, None] * (texture[1] - texture[0]) + v[:, None] * (texture[2] - texture[0])
            if self.source_constant is not None:
                colour = np.broadcast_to(self.source_constant, (len(local_y), 4))
            else:
                colour = self._sample_nearest(self.source, coordinates)
            coverage = np.clip(colour[:, 3], 0, 1).astype(np.float32)
            visible = coverage > 0
            if not visible.any():
                continue
            if not visible.all():
                local_y, local_x = local_y[visible], local_x[visible]
                colour = colour[visible]
                coverage = coverage[visible]
                coordinates = coordinates[visible]
            absolute_y = minimum[1] + local_y
            absolute_x = minimum[0] + local_x
            contribution = coverage * transmittance[absolute_y, absolute_x]
            colour_sum[absolute_y, absolute_x] += colour[:, :3] * contribution[:, None]
            transmittance[absolute_y, absolute_x] *= 1 - coverage
            if ao_sum is not None:
                if self.occlusion_constant is not None:
                    ao_sum[absolute_y, absolute_x] += self.occlusion_constant * contribution[:, None]
                else:
                    ao_sum[absolute_y, absolute_x] += self._sample_nearest(self.occlusion, coordinates) * contribution[:, None]

        alpha_high = np.clip(1 - transmittance, 0, 1)
        alpha = alpha_high.reshape(self.tile, factor, self.tile, factor).mean(axis=(1, 3))
        alpha_sum = alpha_high.reshape(self.tile, factor, self.tile, factor).sum(axis=(1, 3))
        colour = np.zeros((self.tile, self.tile, 3), dtype=np.float32)
        colour_numerator = colour_sum.reshape(self.tile, factor, self.tile, factor, 3).sum(axis=(1, 3))
        np.divide(colour_numerator, alpha_sum[..., None], out=colour, where=alpha_sum[..., None] > 1e-7)
        tile[..., :3] = colour
        tile[..., 3] = alpha
        if ao_sum is not None:
            ao_numerator = ao_sum.reshape(self.tile, factor, self.tile, factor, 4).sum(axis=(1, 3))
            ao = np.ones((self.tile, self.tile, 4), dtype=np.float32)
            np.divide(ao_numerator, alpha_sum[..., None], out=ao, where=alpha_sum[..., None] > 1e-7)
            ao_tile[:] = ao
        self._dilate_padding(tile, ao_tile, margin)
        return [((x0 + x) / self.size, (y0 + y) / self.size)
                for x, y in [(margin, margin), (margin + extent, margin),
                             (margin + extent, margin + extent), (margin, margin + extent)]]

    def material(self):
        self.image.pixels.foreach_set(self.pixels.ravel())
        self.image.pack()
        material = bpy.data.materials.new(self.image.name)
        material.use_nodes = True
        material.use_backface_culling = False
        material["vr_alpha_cutoff"] = self.alpha_cutoff
        material["vr_atlas_supersample"] = self.supersample
        nodes, links = material.node_tree.nodes, material.node_tree.links
        shader = nodes["Principled BSDF"]
        shader.inputs["Metallic"].default_value = 0
        shader.inputs["Roughness"].default_value = .76
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = self.image
        links.new(texture.outputs["Color"], shader.inputs["Base Color"])
        clip = nodes.new("ShaderNodeMath")
        clip.operation = "GREATER_THAN"
        clip.inputs[1].default_value = self.alpha_cutoff
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

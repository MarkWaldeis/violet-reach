"""Credit-free shallow-water island shoal for the mirror-lake monument.

A low, irregular chalk and sandstone bank, built as continuous nested strata rather
than as a noisy dome.  The bottom centre is the origin, units are metres and Z is up.
The high-detail SOURCE is intentionally one coherent grounded mass with embedded
boulders, volumetric moss pads and sparse solid grass blades; there are no alpha
cards, helper meshes or floating pieces.
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise

import vrlib
import vrmat

SEED = 730291
TAU = math.tau
SEGMENTS = 168
TARGET_SIZE = (34.0, 27.0, 5.5)
RX, RY = 17.0, 13.5

# Horizontal treads and repeated radii form vertical/slightly overhung risers.
# Level -1 is the buried bottom skirt at z=0.
RING_SPECS = (
    (0.07, 5), (0.15, 5), (0.24, 5), (0.31, 5), (0.38, 5),
    (0.38, 4), (0.43, 4), (0.49, 4),
    (0.49, 3), (0.55, 3), (0.61, 3),
    (0.61, 2), (0.67, 2), (0.73, 2),
    (0.73, 1), (0.80, 1), (0.87, 1),
    (0.87, 0), (0.94, 0), (1.00, 0),
    (1.00, -1),
)
LEVEL_HEIGHT = {5: 5.32, 4: 4.88, 3: 4.31, 2: 3.68, 1: 3.02, 0: 2.21}
LEVEL_AMP = {5: 0.035, 4: 0.145, 3: 0.165, 2: 0.185, 1: 0.195, 0: 0.205}

_fracture_rng = random.Random(SEED + 41)
FRACTURES = tuple(
    (_fracture_rng.uniform(0, TAU), _fracture_rng.uniform(0.034, 0.068), _fracture_rng.uniform(0.65, 1.0))
    for _ in range(17)
)
LEVEL_OFFSETS = {
    5: (-0.16, 0.10),
    4: (0.10, -0.04),
    3: (0.24, -0.15),
    2: (-0.10, -0.24),
    1: (0.16, -0.07),
    0: (0.0, 0.0),
}


def clamp01(v):
    return min(1.0, max(0.0, v))


def smooth(v):
    t = clamp01(v)
    return t * t * (3.0 - 2.0 * t)


def blend(a, b, t):
    t = clamp01(t) if isinstance(t, float) else t
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def scale(a, factor):
    return tuple(x * factor for x in a)


def n3(x, y, z):
    return noise.noise(Vector((x, y, z)), noise_basis="PERLIN_ORIGINAL")


def noise01(x, y, z, gain=1.65):
    """Contrast-expanded Perlin in [0,1]; raw Blender noise is clustered too tightly."""
    return clamp01(0.5 + gain * n3(x, y, z))


def angle_delta(a, b):
    return math.atan2(math.sin(a - b), math.cos(a - b))


def raw_shape(theta):
    c, s = math.cos(theta), math.sin(theta)
    return (
        1.0
        + 0.073 * math.sin(2.0 * theta + 0.46)
        + 0.054 * math.sin(3.0 * theta - 1.16)
        + 0.036 * math.cos(5.0 * theta + 0.74)
        + 0.025 * math.sin(7.0 * theta - 2.03)
        + 0.039 * n3(c * 1.71 + 8.3, s * 1.71 - 2.8, 4.7)
    )


# Normalise the noisy outline so the broad toe, not an accidental noise lobe,
# defines the nominal 34 x 27 m footprint before final exact scaling.
_shape_max = max(raw_shape(TAU * i / 720.0) for i in range(720))


def shape_factor(theta):
    return raw_shape(theta) / _shape_max


def fracture_amount(theta):
    total = 0.0
    for centre, width, strength in FRACTURES:
        total += strength * math.exp(-((angle_delta(theta, centre) / width) ** 2))
    return clamp01(total)


def hash01(index):
    return math.sin(index * 12.9898 + 78.233) * 43758.5453 % 1.0


def sector_step(theta, level, sectors, salt):
    """Piecewise angular offset; gives the strata broken block edges instead of cake rings."""
    index = math.floor((theta / TAU) * sectors + 0.5) % sectors
    return hash01(index + level * 173 + salt * 887) * 2.0 - 1.0


def plan_point(q, theta, level):
    """Nested irregular elliptical plan. Inner rings become more circular for the plateau."""
    circularity = ((1.0 - q) ** 1.15) * 0.75
    sx = RX * (1.0 - 0.045 * circularity)
    sy = RY * 1.05 * (1.0 + 0.18 * circularity)
    band = max(0, level)
    c, s = math.cos(theta), math.sin(theta)
    sectors = 28 + (band * 7) % 13
    block = sector_step(theta, band, sectors, 11) * (0.006 + 0.014 * q)
    warp = q * (0.055 - 0.005 * band) * (
        0.55 * math.sin(2.0 * theta + band * 1.37)
        + 0.32 * math.sin(3.0 * theta - band * 0.73)
        + 0.18 * math.sin(5.0 * theta + band * 0.41)
    )
    small = (
        0.009 * math.sin(11.0 * theta + 4.7 * q + band * 0.83)
        + 0.0055 * math.sin(23.0 * theta - band * 1.37)
        + 0.007 * n3(c * 4.1 + band * 0.13, s * 4.1 - q * 2.3, band * 0.71)
    ) * q
    joint = fracture_amount(theta) * (0.018 + 0.025 * q) * (0.45 + 0.11 * (5 - band))
    radial = q * shape_factor(theta) * (1.0 + small + block + warp - joint)
    ox, oy = LEVEL_OFFSETS.get(band, (0.0, 0.0))
    # Eccentricity grows subtly towards the outer strata; the plateau itself stays central.
    eccentricity = 0.35 + 0.65 * q
    return sx * radial * c + ox * eccentricity, sy * radial * s + oy * eccentricity


def surface_height(level, q, theta):
    x, y = plan_point(q, theta, level)
    phase = level * 1.713 + 0.41
    amp = LEVEL_AMP[level]
    if level == 5:
        # Spatial, not angular, undulation: theta harmonics otherwise read as radial
        # fan ridges on the broad monument pad.
        broad = 0.54 * n3(x * 0.20 + 2.0, y * 0.20 - 3.0, 7.5) + 0.20 * n3(x * 0.52, y * 0.52, 3.2)
    else:
        broad = (
            0.48 * math.sin(2.0 * theta + phase)
            + 0.31 * math.sin(4.0 * theta - phase * 1.31)
            + 0.25 * n3(math.cos(theta) * 2.2 + q, math.sin(theta) * 2.2, level * 3.7)
        )
    z = LEVEL_HEIGHT[level] + amp * broad
    if level == 5:
        # The monument plate reads as a gently weathered, almost level pad rather than a hill.
        z += 0.025 * (1.0 - q / 0.38)
        micro = (
            0.070 * n3(x * 0.72, y * 0.72, 7.6)
            + 0.040 * n3(x * 1.45, y * 1.45, 11.3)
            + 0.015 * n3(x * 5.8, y * 5.8, 4.2)
        )
        # Keep the future monument footprint level while the rest of the cap is weathered.
        micro *= 0.22 + 0.78 * smooth((q - 0.14) / 0.10)
    else:
        micro = (
            0.160 * n3(x * 0.58, y * 0.58, level * 2.7)
            + 0.072 * n3(x * 1.65, y * 1.65, level + 8.0)
            + 0.022 * n3(x * 5.6, y * 5.6, level)
        )
    z += micro
    # Localised edge collapse: fracture corridors nibble the outer lip of each tread,
    # so the risers are eroded rock edges rather than uninterrupted cylinders.
    boundary = {5: 0.38, 4: 0.49, 3: 0.61, 2: 0.73, 1: 0.87, 0: 1.0}[level]
    edge = smooth((q - (boundary - 0.08)) / 0.08)
    chip_amp = {5: 0.22, 4: 0.19, 3: 0.17, 2: 0.15, 1: 0.13, 0: 0.10}[level]
    chip = fracture_amount(theta) * (0.65 + 0.50 * n3(theta * 2.0, q * 5.0, level * 4.0))
    z -= edge * chip * chip_amp
    return z


def level_for_q(q):
    if q <= 0.38:
        return 5
    if q <= 0.49:
        return 4
    if q <= 0.61:
        return 3
    if q <= 0.73:
        return 2
    if q <= 0.87:
        return 1
    return 0


def surface_point(q, theta):
    level = level_for_q(q)
    x, y = plan_point(q, theta, level)
    return Vector((x, y, surface_height(level, q, theta)))


def vegetation_mask(x, y, z, q, theta, level):
    if level != 5 or q > 0.385 or z < 5.05:
        return 0.0
    patch = (
        0.62 * n3(x * 0.19 + 13.1, y * 0.19 - 7.4, 4.2)
        + 0.30 * n3(x * 0.63 - 4.8, y * 0.63 + 8.2, 9.1)
        + 0.035 * math.sin(theta * 3.0 + q * 8.0)
    )
    rim_fade = 1.0 - smooth((q - 0.355) / 0.045)
    return clamp01(smooth((patch - 0.165) / 0.25) * rim_fade)


def water_wetness(z, theta=0.0):
    # The lake is expected to intersect the upper strata.  A broad submerged tone is
    # overlaid by a narrower, darker capillary waterline band around z=4.8 m.  Its
    # centre wanders a little around the perimeter so it reads as a shoreline deposit,
    # not as a perfectly machined painted stripe.
    centre = 4.73 + 0.075 * math.sin(2.0 * theta + 0.4) + 0.045 * n3(math.cos(theta) * 2.3, math.sin(theta) * 2.3, 6.1)
    width = 0.16 + 0.035 * (0.5 + 0.5 * n3(math.cos(theta) * 4.0, math.sin(theta) * 4.0, 3.8))
    line = math.exp(-((z - centre) / width) ** 2)
    patch = clamp01(0.66 + 0.52 * n3(math.cos(theta) * 3.2 + 8.0, math.sin(theta) * 3.2, 9.4))
    below = 1.0 - smooth((z - 4.91) / 0.55)
    return clamp01(0.32 * below + 0.86 * line * patch)


def shoal_tone(p, x, y, z, q, theta, level):
    broad = noise01(x * 0.12 + 3.2, y * 0.12 - 4.1, level * 0.9, 1.45)
    chalk = blend(p["canyon_chalk"], p["stone_weathered"], 0.10 + 0.42 * broad)
    warm = clamp01(0.08 + 0.72 * noise01(x * 0.16 - 2.0, y * 0.16 + 5.3, level, 1.75) + 0.045 * math.sin(theta * 3.0 + level))
    base = blend(chalk, p["sandstone"], warm * 0.68)

    sandy = clamp01(0.12 + 0.72 * noise01(x * 0.31 + 8.0, y * 0.31, 2.7, 1.8) + 0.035 * math.sin(theta * 5.0 - q * 4.0))
    base = blend(base, p["path_sand"], sandy * (0.24 + 0.14 * (level >= 4)))

    depth = clamp01((5.15 - z) / 3.0)
    mineral_patch = noise01(x * 0.43 - 7.0, y * 0.43 + 2.0, level * 1.9, 1.9)
    base = blend(base, p["canyon_strata"], 0.07 + 0.17 * mineral_patch + 0.27 * depth)
    lamina_wave = 0.5 + 0.5 * math.sin(12.5 * z + 2.6 * n3(x * 0.18, y * 0.18, 1.8))
    lamina = smooth((lamina_wave - 0.58) / 0.26)
    base = scale(base, 1.0 - 0.30 * lamina * (0.35 + 0.65 * depth))
    fracture_visibility = clamp01((z - 2.25) / 2.7)
    if level == 5 and q < 0.36:
        fracture_visibility *= 0.16
    base = scale(base, 1.0 - 0.17 * fracture_amount(theta) * fracture_visibility)

    wet = water_wetness(z, theta)
    wet *= clamp01(0.78 + 0.34 * n3(x * 0.38 + 6.0, y * 0.38 - 1.0, 15.2))
    wet *= 0.55 + 0.45 * smooth((q - 0.31) / 0.13)
    wet_grain = 0.40 + 0.12 * n3(x * 1.55, y * 1.55, z * 0.7)
    wet_rgb = scale(blend(p["shore_wet"], p["canyon_strata"], 0.24), wet_grain)
    colour = blend(scale(base, 0.99), wet_rgb, wet)

    veg = vegetation_mask(x, y, z, q, theta, level)
    if veg:
        moss_mix = clamp01(0.52 + 0.30 * n3(x * 0.9, y * 0.9, 12.0))
        veg_rgb = scale(blend(p["moss"], p["grass_green"], moss_mix), 1.18)
        colour = blend(colour, veg_rgb, veg)
    return colour, wet * (1.0 - 0.45 * veg), veg


class MeshBuilder:
    def __init__(self):
        self.verts = []
        self.faces = []
        self.colors = []
        self.factors = []

    def object(self, name, materials, color_name=None, factor_name=None, material_indices=None, smooth_mask=None):
        data = bpy.data.meshes.new(name)
        data.from_pydata(self.verts, [], self.faces)
        data.update()
        for material in materials if isinstance(materials, (tuple, list)) else (materials,):
            data.materials.append(material)
        for index, poly in enumerate(data.polygons):
            poly.use_smooth = bool(smooth_mask[index]) if smooth_mask is not None else False
            if material_indices is not None and index < len(material_indices):
                poly.material_index = material_indices[index]
        if color_name:
            layer = data.color_attributes.new(name=color_name, type="FLOAT_COLOR", domain="POINT")
            layer.data.foreach_set("color", [channel for rgb in self.colors for channel in (*rgb, 1.0)])
        if factor_name:
            layer = data.attributes.new(name=factor_name, type="FLOAT", domain="POINT")
            layer.data.foreach_set("value", self.factors)
        obj = bpy.data.objects.new(name, data)
        return vrlib.link_to_source(obj)


def attribute_material(base, name, color_attr, color_weight, factor_attr=None, roughness=None):
    """Library material copy driven by point colour/moisture, as in lake_shore_a."""
    material = vrmat.get(base).copy()
    material.name = name
    nodes, links = material.node_tree.nodes, material.node_tree.links
    # The shared layered-rock shader uses extremely thin 5 cm laminae.  On metre-high
    # shoal risers they alias into a uniform grey wash, so this copy uses thicker,
    # readable sediment bands while leaving the global library material untouched.
    for node in nodes:
        if node.type == "VECTOR_MATH" and node.operation == "MULTIPLY":
            factors = node.inputs[1].default_value
            if abs(factors[2] - 18.0) < 0.01:
                node.inputs[1].default_value = (1.45, 1.45, 5.2)
    bsdf = nodes["Principled BSDF"]
    tint = nodes.new("ShaderNodeAttribute")
    tint.attribute_name = color_attr
    target = bsdf.inputs["Base Color"]
    mineral = nodes.new("ShaderNodeMixRGB")
    mineral.inputs["Fac"].default_value = color_weight
    links.new(target.links[0].from_socket, mineral.inputs[1])
    links.new(tint.outputs["Color"], mineral.inputs[2])
    links.new(mineral.outputs["Color"], target)
    if factor_attr and roughness:
        wet = nodes.new("ShaderNodeAttribute")
        wet.attribute_name = factor_attr
        ranges = nodes.new("ShaderNodeMapRange")
        ranges.inputs["To Min"].default_value, ranges.inputs["To Max"].default_value = roughness
        links.new(wet.outputs["Fac"], ranges.inputs["Value"])
        rough = bsdf.inputs["Roughness"]
        variation = nodes.new("ShaderNodeMath")
        variation.operation = "MULTIPLY_ADD"
        links.new(rough.links[0].from_socket, variation.inputs[0])
        variation.inputs[1].default_value = 0.15
        links.new(ranges.outputs["Result"], variation.inputs[2])
        links.new(variation.outputs[0], rough)
    return material


def add_mineral_grain(material, strength, scale):
    """Add non-repeating close-range mineral grain to a copied material.

    The mesh is deliberately low-frequency; this shader detail is what survives as
    fine rock texture in the bake instead of requiring extra triangles.
    """
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes["Principled BSDF"]
    target = bsdf.inputs["Base Color"]
    if not target.links:
        return material
    coord = next((node for node in nodes if node.type == "TEX_COORD"), None)
    if coord is None:
        return material
    source = target.links[0].from_socket
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = scale
    grain.inputs["Detail"].default_value = 3.2
    grain.inputs["Roughness"].default_value = 0.78
    links.new(coord.outputs["Object"], grain.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.24
    ramp.color_ramp.elements[0].color = (0.62, 0.59, 0.53, 1.0)
    ramp.color_ramp.elements[1].position = 0.76
    ramp.color_ramp.elements[1].color = (1.03, 0.99, 0.88, 1.0)
    links.new(grain.outputs["Fac"], ramp.inputs["Fac"])
    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs["Fac"].default_value = strength
    links.new(source, multiply.inputs["Color1"])
    links.new(ramp.outputs["Color"], multiply.inputs["Color2"])
    links.new(multiply.outputs["Color"], target)
    return material


def multiply_tint(material, rgb, strength):
    """Darken a copied material without touching the shared vrmat cache."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes["Principled BSDF"]
    target = bsdf.inputs["Base Color"]
    if not target.links:
        return material
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs["Fac"].default_value = strength
    links.new(target.links[0].from_socket, tint.inputs[1])
    tint.inputs[2].default_value = (*rgb, 1.0)
    links.new(tint.outputs[0], target)
    return material


def build_core(p, rock_material, cap_material, strata_material):
    mesh = MeshBuilder()
    vegetation = []

    def append_vertex(x, y, z, q, theta, level):
        colour, wet, veg = shoal_tone(p, x, y, z, q, theta, level)
        mesh.verts.append((x, y, z))
        mesh.colors.append(colour)
        mesh.factors.append(wet)
        vegetation.append(veg)
        return len(mesh.verts) - 1

    centre = append_vertex(0.0, 0.0, surface_height(5, 0.0, 0.0), 0.0, 0.0, 5)
    ring_starts = []
    for q, level in RING_SPECS:
        start = len(mesh.verts)
        for i in range(SEGMENTS):
            theta = TAU * i / SEGMENTS
            if level == -1:
                # The buried skirt follows the toe exactly and closes every possible gap.
                x, y = plan_point(q, theta, 0)
                z = 0.0
                colour, wet, veg = shoal_tone(p, x, y, z, q, theta, 0)
                mesh.verts.append((x, y, z))
                mesh.colors.append(scale(blend(p["shore_wet"], p["soil"], 0.25), 0.42))
                mesh.factors.append(0.65)
                vegetation.append(0.0)
            else:
                x, y = plan_point(q, theta, level)
                z = surface_height(level, q, theta)
                append_vertex(x, y, z, q, theta, level)
        ring_starts.append(start)

    material_indices = []
    smooth_mask = []

    def face_vegetation(indices):
        return sum(vegetation[i] for i in indices) / len(indices)

    def add_face(indices, horizontal, level):
        index = len(mesh.faces)
        mesh.faces.append(indices)
        avg_veg = face_vegetation(indices)
        avg_z = sum(mesh.verts[i][2] for i in indices) / len(indices)
        grassy = horizontal and level == 5 and avg_z > 5.08 and avg_veg > 0.38
        material_indices.append(1 if grassy else (2 if not horizontal else 0))
        smooth_mask.append(horizontal)
        return index

    first = ring_starts[0]
    for i in range(SEGMENTS):
        ni = (i + 1) % SEGMENTS
        add_face((centre, first + i, first + ni), True, 5)

    for ring_index in range(len(ring_starts) - 1):
        inner, outer = ring_starts[ring_index], ring_starts[ring_index + 1]
        level_a, level_b = RING_SPECS[ring_index][1], RING_SPECS[ring_index + 1][1]
        horizontal = level_a == level_b and level_a != -1
        for i in range(SEGMENTS):
            ni = (i + 1) % SEGMENTS
            add_face((inner + i, outer + i, outer + ni, inner + ni), horizontal, level_a)

    bottom_ring = ring_starts[-1]
    bottom_centre = len(mesh.verts)
    mesh.verts.append((0.0, 0.0, 0.0))
    mesh.colors.append(scale(p["soil"], 0.34))
    mesh.factors.append(0.7)
    vegetation.append(0.0)
    for i in range(SEGMENTS):
        ni = (i + 1) % SEGMENTS
        add_face((bottom_centre, bottom_ring + ni, bottom_ring + i), False, -1)

    obj = mesh.object(
        "Continuous stepped chalk-sandstone shoal mass",
        (rock_material, cap_material, strata_material),
        "shoal_tones",
        "shoal_moisture",
        material_indices,
        [True] * len(mesh.faces),
    )
    # Smooth the circumference of each riser, but keep the tread/riser arrises sharp.
    # This removes column-like triangular facets without deleting the stepped silhouette.
    obj.data.set_sharp_from_angle(angle=math.radians(24.0))
    obj["vr_role"] = "continuous_island_mass"
    obj["vr_cap_faces"] = sum(1 for index in material_indices if index == 1)
    return obj


def ico(level):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=level, radius=1.0)
    bm.verts.index_update()
    vertices = [tuple(v.co) for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return vertices, faces


def eased_min(a, b, radius):
    gap = max(0.0, radius - abs(a - b))
    return min(a, b) - gap * gap / (4.0 * radius)


def add_boulder(mesh, p, template, q, theta, radius, flat, rng, seed):
    coords, faces = template
    centre_surface = surface_point(q, theta)
    level = level_for_q(q)
    offset = len(mesh.verts)
    angle = rng.uniform(0.0, TAU)
    ca, sa = math.cos(angle), math.sin(angle)
    elongation = rng.uniform(0.62, 0.88)
    lean = rng.uniform(-0.13, 0.13)
    weather = rng.random()
    floor = centre_surface.z - radius * flat * rng.uniform(0.34, 0.48)
    centre_z = centre_surface.z + radius * flat * rng.uniform(0.16, 0.27)

    cuts = []
    strike = rng.uniform(0.0, TAU)
    count = rng.randint(5, 7)
    for j in range(count):
        azimuth = strike + j * TAU / count + rng.uniform(-0.23, 0.23)
        rise = rng.uniform(-0.28, 0.32)
        axy = math.sqrt(max(0.05, 1.0 - rise * rise))
        cuts.append((math.cos(azimuth) * axy, math.sin(azimuth) * axy, rise, rng.uniform(0.58, 0.77)))
    cuts.extend(((0.20, -0.12, 0.96, rng.uniform(0.45, 0.60)),
                 (-0.55, 0.31, 0.76, rng.uniform(0.55, 0.68)),
                 (0.61, 0.55, 0.30, rng.uniform(0.57, 0.72))))

    body = blend(p["canyon_chalk"], p["canyon_strata"], rng.uniform(0.38, 0.70))
    body = blend(body, p["sandstone"], rng.uniform(0.08, 0.30))
    for u, v, w in coords:
        coarse = n3(2.0 * u + seed, 2.0 * v, 2.0 * w)
        medium = n3(5.3 * u, 5.3 * v + seed, 5.3 * w)
        fine = n3(13.5 * u, 13.5 * v, 13.5 * w + seed)
        radial = 1.0 + 0.060 * coarse
        for nx, ny, nz, upper in cuts:
            dot = nx * u + ny * v + nz * w
            if dot > 0.27:
                radial = eased_min(radial, upper / dot, 0.026)
        lamina = math.sin((18.0 + 5.0 * weather) * (w + 0.20 * u - 0.12 * v) + 0.7 * coarse)
        chip = smooth((medium + 0.18) / 0.72)
        radial *= 1.0 + 0.025 * medium + 0.010 * fine - 0.030 * chip + 0.012 * lamina
        radial = max(0.42, radial)

        x_local = (u * radial + lean * w * 0.30) * radius
        y_local = v * radial * radius * elongation
        z_local = (w * radial + lean * u * 0.22) * radius * flat
        x = centre_surface.x + ca * x_local - sa * y_local
        y = centre_surface.y + sa * x_local + ca * y_local
        z = centre_z + z_local
        z = floor + 0.018 * radius + max(0.0, z - floor)
        mesh.verts.append((x, y, z))

        wet = water_wetness(z, math.atan2(y, x)) * 0.95
        pale = 0.018 * smooth((lamina - 0.55) / 0.35) + 0.012 * (1.0 - chip)
        dry = scale(body, 0.82 + 0.20 * weather + 0.19 * coarse + 0.15 * medium + 0.055 * fine)
        dry = tuple(min(1.0, c + pale) for c in dry)
        wet_rgb = scale(blend(dry, p["shore_wet"], 0.42), 0.48)
        mesh.colors.append(blend(dry, wet_rgb, wet))
        mesh.factors.append(wet)
    mesh.faces.extend(tuple(offset + i for i in face) for face in faces)


def build_boulders(p, material):
    rng = random.Random(SEED + 107)
    mesh = MeshBuilder()
    templates = {3: ico(3), 4: ico(4)}
    placements = (
        (math.radians(-128), 0.405, 1.05, 0.57),
        (math.radians(-24), 0.435, 0.82, 0.61),
        (math.radians(38), 0.535, 1.24, 0.55),
        (math.radians(105), 0.625, 0.88, 0.65),
        (math.radians(164), 0.795, 1.32, 0.52),
        (math.radians(-71), 0.885, 0.72, 0.58),
    )
    for index, (theta, q, radius, flat) in enumerate(placements):
        # Only the two large foreground stones need the denser template; smaller stones
        # stay on the cheaper one so the total source budget remains controlled.
        template = templates[4 if radius >= 1.20 else 3]
        add_boulder(mesh, p, template, q, theta, radius, flat, rng, 900 + index * 37)
    obj = mesh.object(
        "Embedded angular chalk boulders",
        (material,),
        "boulder_tones",
        "boulder_moisture",
        smooth_mask=[True] * len(mesh.faces),
    )
    obj.data.set_sharp_from_angle(angle=math.radians(28.0))
    obj["vr_role"] = "embedded_boulders"
    return obj


def add_moss_pad(mesh, p, q0, theta0, radius, rng):
    sides = 16
    centre = surface_point(q0, theta0)
    bottom_centre = len(mesh.verts)
    mesh.verts.append((centre.x, centre.y, centre.z - 0.018))
    mesh.colors.append(scale(p["moss"], 0.48))
    top_centre = len(mesh.verts)
    mesh.verts.append((centre.x, centre.y, centre.z + rng.uniform(0.042, 0.066)))
    mesh.colors.append(scale(blend(p["moss"], p["grass_green"], rng.uniform(0.62, 0.86)), 1.34))

    bottom_ring, top_ring = [], []
    for j in range(sides):
        az = TAU * j / sides
        local_radius = radius * (0.68 + 0.25 * math.sin(3 * az + rng.uniform(-0.35, 0.35)) + rng.uniform(-0.13, 0.15))
        dq = math.cos(az) * local_radius / 15.0
        dtheta = math.sin(az) * local_radius / max(2.4, q0 * 14.0)
        qi = min(0.345, max(0.055, q0 + dq))
        pos = surface_point(qi, theta0 + dtheta)
        bottom_ring.append(len(mesh.verts))
        mesh.verts.append((pos.x, pos.y, pos.z - 0.018))
        mesh.colors.append(scale(p["moss"], 0.50))
        top_ring.append(len(mesh.verts))
        crown = 0.017 + 0.010 * (0.5 + 0.5 * n3(pos.x * 1.8, pos.y * 1.8, 17.0))
        mesh.verts.append((pos.x, pos.y, pos.z + crown))
        living = scale(blend(p["moss"], p["grass_green"], 0.64 + 0.26 * n3(pos.x, pos.y, 3.0)), 1.24)
        mineral_edge = scale(blend(p["canyon_chalk"], p["path_sand"], 0.32), 0.72)
        mesh.colors.append(blend(living, mineral_edge, 0.28))

    for j in range(sides):
        nj = (j + 1) % sides
        mesh.faces.append((bottom_ring[j], bottom_ring[nj], top_ring[nj], top_ring[j]))
        mesh.faces.append((top_centre, top_ring[j], top_ring[nj]))
        mesh.faces.append((bottom_centre, bottom_ring[nj], bottom_ring[j]))


def build_moss(p, material):
    rng = random.Random(SEED + 211)
    mesh = MeshBuilder()
    placements = (
        (0.13, math.radians(-142), 0.36),
        (0.19, math.radians(-58), 0.43),
        (0.25, math.radians(18), 0.34),
        (0.29, math.radians(78), 0.39),
        (0.22, math.radians(151), 0.32),
    )
    for q, theta, radius in placements:
        add_moss_pad(mesh, p, q, theta, radius, rng)
    obj = mesh.object(
        "Sparse volumetric moss cushions on the dry upper pad",
        (material,),
        "moss_tones",
        smooth_mask=[True] * len(mesh.faces),
    )
    obj["vr_role"] = "volumetric_moss_cap"
    return obj


def grass_blade(mesh, p, base, length, width, direction, bend, tone):
    rings = 5
    indices = []
    ca, sa = math.cos(direction), math.sin(direction)
    twist = direction + 0.7
    for s in range(rings):
        t = s / (rings - 1)
        horizontal = bend * (t ** 1.55)
        centre_x = base.x + ca * horizontal + 0.018 * math.sin(t * 5.0 + direction) * t
        centre_y = base.y + sa * horizontal + 0.014 * math.cos(t * 4.0 + direction) * t
        centre_z = base.z + length * t - 0.035 * length * t * t
        radius = width * ((1.0 - t) ** 0.78) + 0.0008
        ring = []
        for k in range(3):
            az = twist + TAU * k / 3.0
            ring.append(len(mesh.verts))
            mesh.verts.append((centre_x + math.cos(az) * radius,
                               centre_y + math.sin(az) * radius,
                               centre_z + 0.22 * radius * math.sin(az)))
            blade_shade = 0.92 + 0.72 * t
            mesh.colors.append(scale(tone, blade_shade))
        indices.append(ring)
    for s in range(rings - 1):
        for k in range(3):
            nk = (k + 1) % 3
            mesh.faces.append((indices[s][k], indices[s][nk], indices[s + 1][nk], indices[s + 1][k]))
    mesh.faces.append(tuple(reversed(indices[0])))
    mesh.faces.append(tuple(indices[-1]))


def build_grass(p, material):
    rng = random.Random(SEED + 307)
    mesh = MeshBuilder()
    clumps = []
    attempts = 0
    while len(clumps) < 13 and attempts < 500:
        attempts += 1
        q = rng.uniform(0.105, 0.345)
        theta = rng.uniform(0.0, TAU)
        pos = surface_point(q, theta)
        if vegetation_mask(pos.x, pos.y, pos.z, q, theta, 5) > 0.16:
            clumps.append((q, theta))
    # Guarantee a few readable tufts even if the noise threshold is locally harsh.
    while len(clumps) < 10:
        clumps.append((rng.uniform(0.14, 0.31), rng.uniform(0.0, TAU)))

    for q0, theta0 in clumps:
        for _ in range(rng.randint(4, 6)):
            q = min(0.355, max(0.07, q0 + rng.uniform(-0.010, 0.010)))
            theta = theta0 + rng.uniform(-0.022, 0.022)
            base = surface_point(q, theta)
            base.z -= 0.014
            dryness = rng.random() ** 2.2
            tone = blend(p["grass_green"], p["grass_dry"], dryness)
            tone = blend(p["moss"], tone, 0.48)
            grass_blade(
                mesh,
                p,
                base,
                rng.uniform(0.13, 0.26),
                rng.uniform(0.016, 0.029),
                rng.uniform(0.0, TAU),
                rng.uniform(0.05, 0.16),
                tone,
            )
    obj = mesh.object(
        "Sparse solid sedge blades rooted in the upper cap",
        (material,),
        "sedge_tones",
        smooth_mask=[True] * len(mesh.faces),
    )
    obj["vr_role"] = "solid_sparse_grass"
    return obj


def transform_source_exact():
    """Recentre XY, put the underside at z=0 and normalise to the requested metres."""
    objs = vrlib.source_objects()
    lo, hi = vrlib.world_bounds(objs)
    centre_x = (lo.x + hi.x) * 0.5
    centre_y = (lo.y + hi.y) * 0.5
    size = hi - lo
    sx = TARGET_SIZE[0] / size.x
    sy = TARGET_SIZE[1] / size.y
    sz = TARGET_SIZE[2] / size.z
    for obj in objs:
        for vertex in obj.data.vertices:
            vertex.co.x = (vertex.co.x - centre_x) * sx
            vertex.co.y = (vertex.co.y - centre_y) * sy
            vertex.co.z = (vertex.co.z - lo.z) * sz
        obj.data.update()

    def convert(point):
        return Vector(((point.x - centre_x) * sx, (point.y - centre_y) * sy, (point.z - lo.z) * sz))

    return convert


def validate_source():
    objs = vrlib.source_objects()
    zero_faces = 0
    loose_objects = []
    total_triangles = vrlib.triangle_count(objs)
    lo, hi = vrlib.world_bounds(objs)
    for obj in objs:
        zero = sum(1 for poly in obj.data.polygons if poly.area < 1e-9)
        zero_faces += zero
        if min((vertex.co.z for vertex in obj.data.vertices), default=0.0) < -0.002:
            loose_objects.append(obj.name)
    print(
        "VR_SHOAL_CHECK",
        {
            "triangles": total_triangles,
            "objects": len(objs),
            "zero_area_faces": zero_faces,
            "below_origin_objects": loose_objects,
            "size_m": [round(hi.x - lo.x, 3), round(hi.y - lo.y, 3), round(hi.z - lo.z, 3)],
            "min_z": round(lo.z, 4),
        },
        flush=True,
    )


def build():
    p = {key: value["linear_rgb"] for key, value in vrmat.load_palette().items()}

    rock_material = attribute_material(
        "canyon_layered",
        "Island shoal | chalk sandstone with capillary waterline",
        "shoal_tones",
        0.84,
        "shoal_moisture",
        (0.84, 0.30),
    )
    strata_material = attribute_material(
        "canyon_layered",
        "Island shoal | shadowed vertical strata and fracture faces",
        "shoal_tones",
        0.82,
        "shoal_moisture",
        (0.86, 0.34),
    )
    multiply_tint(strata_material, scale(p["canyon_strata"], 0.72), 0.34)
    add_mineral_grain(rock_material, 0.62, 3.8)
    add_mineral_grain(strata_material, 0.50, 4.9)
    cap_material = attribute_material(
        "grass_ground",
        "Island shoal | sparse olive grass and moss surface",
        "shoal_tones",
        0.76,
    )
    boulder_material = attribute_material(
        "river_stones",
        "Island shoal | embedded wet chalk boulders",
        "boulder_tones",
        0.88,
        "boulder_moisture",
        (0.82, 0.38),
    )
    boulder_material.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.24
    add_mineral_grain(cap_material, 0.34, 3.5)
    add_mineral_grain(boulder_material, 0.45, 4.7)
    moss_material = attribute_material(
        "grass_ground",
        "Island shoal | dimensional moss cushions",
        "moss_tones",
        0.88,
    )
    sedge_material = attribute_material(
        "grass_ground",
        "Island shoal | solid sedges",
        "sedge_tones",
        0.90,
    )
    add_mineral_grain(moss_material, 0.18, 8.0)
    add_mineral_grain(sedge_material, 0.12, 10.0)

    core = build_core(p, rock_material, cap_material, strata_material)
    build_boulders(p, boulder_material)
    build_moss(p, moss_material)
    build_grass(p, sedge_material)

    convert = transform_source_exact()
    validate_source()

    scene = bpy.context.scene
    scene["vr_review_turn"] = (0.0, 0.0, 2.55, -32.0, 24.0, 61.0)
    figure = convert(surface_point(0.235, math.radians(-34)))
    figure.z += 0.012
    scene["vr_review_figure"] = tuple(figure)
    upper = convert(surface_point(0.22, math.radians(28)))
    upper.z += 0.15
    scene["vr_closeup_upper"] = (upper.x, upper.y, upper.z, 62.0, 19.0, 15.5)
    base = convert(surface_point(0.45, math.radians(-118)))
    base.z += 0.05
    scene["vr_closeup_base"] = (base.x, base.y, base.z, 205.0, 17.0, 15.0)

    # Deliberate provenance metadata for downstream reviewers; no helper geometry is shipped.
    core["vr_design_notes"] = "stepped continuous strata; central gently domed monument pad; no helper intersections"

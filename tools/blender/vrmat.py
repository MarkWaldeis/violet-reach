"""Undurchsichtige, backbare Materialien. Objektkoordinaten in Metern; Scale anwenden.

Die Palette wird direkt geladen, nicht als zweite Farbliste kopiert.
get(name) liefert pro Blender-Datei dasselbe Material; Kopien vor lokalen Änderungen anlegen.
"""
import json
from pathlib import Path

try:
    import bpy
except ModuleNotFoundError:
    bpy = None

PALETTE_PATH = Path(__file__).resolve().parents[2] / "art/palette.json"
SPECS = {
    "monument_white": ("monument_white", "monument_shadow", .76, .002, "stone"),
    "monument_weathered": ("monument_white", "stone_weathered", .88, .012, "weathered"),
    "canyon_layered": ("canyon_chalk", "canyon_strata", .88, .014, "layered"),
    "sandstone": ("sandstone", "canyon_strata", .87, .008, "layered"),
    "mossy_rock": ("canyon_strata", "moss", .92, .009, "moss"),
    "grass_ground": ("grass_green", "grass_dry", .94, .006, "grass"),
    "forest_soil": ("soil", "bark", .95, .008, "soil"),
    "dirt_path": ("soil", "path_sand", .90, .004, "soil"),
    "river_stones": ("shore_wet", "canyon_strata", .34, .003, "pebble"),
    "tree_bark": ("bark", "soil", .92, .012, "bark"),
    "foliage_leaf": ("leaf_green", "leaf_shadow", .76, .0005, "leaf"),
    "violet_crystal": ("violet_body", "violet_shadow", .23, .0004, "crystal"),
    "violet_energy": ("violet_body", "violet_glow", .38, .0002, "energy"),
    "water_opaque": ("water_deep", "water_shallow", .19, .0007, "water"),
    "ochre_inlay": ("accent_ochre", "sandstone", .69, .001, "stone"),
}


def load_palette():
    colors = json.loads(PALETTE_PATH.read_text())["colors"]
    for name, color in colors.items():
        rgb = [int(color["srgb_hex"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        expected = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        if len(color["linear_rgb"]) != 3 or any(abs(a - b) > 1e-6 for a, b in zip(expected, color["linear_rgb"])):
            raise ValueError(f"Inkonsistente sRGB/Linear-Palette: {name}")
    for a, b, *_ in SPECS.values():
        if a not in colors or b not in colors:
            raise ValueError(f"Fehlende Materialfarbe: {a}, {b}")
    return colors


def get(name):
    if name not in SPECS:
        raise KeyError(f"Unbekanntes VR-Material {name!r}; erlaubt: {', '.join(SPECS)}")
    if bpy is None:
        raise RuntimeError("vrmat.get benötigt Blender-Python")
    colors = load_palette()
    key = "vrmat_" + name
    cached = bpy.data.materials.get(key)
    if cached is not None:
        return cached
    a, b, roughness, depth, family = SPECS[name]
    rgba = lambda key: (*colors[key]["linear_rgb"], 1)
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    mat.diffuse_color = rgba(a)
    mat["vrmat_name"] = name
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Alpha"].default_value = 1
    bsdf.inputs["Metallic"].default_value = 0
    bsdf.inputs["Transmission Weight"].default_value = 0
    coord = nodes.new("ShaderNodeTexCoord")
    vector = coord.outputs["Object"]

    def noise(scale, detail=4, vector=vector):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = .72
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(source, low, high, positions=(.2, .8)):
        node = nodes.new("ShaderNodeValToRGB")
        for el, position, color in zip(node.color_ramp.elements, positions, (low, high)):
            el.position, el.color = position, color
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def multiply(source, gain):
        node = nodes.new("ShaderNodeMath")
        node.operation = "MULTIPLY"
        node.inputs[1].default_value = gain
        links.new(source, node.inputs[0])
        return node.outputs[0]

    coarse, fine = noise(2.3), noise(145)
    mask, height = coarse, fine
    if family in {"layered", "bark", "grass", "leaf", "crystal", "water"}:
        stretch = nodes.new("ShaderNodeVectorMath")
        stretch.operation = "MULTIPLY"
        stretch.inputs[1].default_value = {
            "layered": (1.6, 1.6, 18), "bark": (28, 28, 1.2),
            "grass": (35, 35, 4), "leaf": (45, 3, 4),
            "crystal": (45, 45, 1), "water": (2, 18, 1),
        }[family]
        links.new(vector, stretch.inputs[0])
        grain = noise(1, vector=stretch.outputs["Vector"])
        height = grain
        mask = grain if family in {"layered", "bark"} else coarse
    elif family in {"soil", "pebble"}:
        cells = nodes.new("ShaderNodeTexVoronoi")
        cells.inputs["Scale"].default_value = 65 if family == "soil" else 12
        links.new(vector, cells.inputs["Vector"])
        height = ramp(cells.outputs["Distance"], (0, 0, 0, 1), (1, 1, 1, 1), (.08, .55))
    elif family == "weathered":
        geo = nodes.new("ShaderNodeNewGeometry")
        wear = nodes.new("ShaderNodeMixRGB")
        wear.inputs["Fac"].default_value = .18
        links.new(coarse, wear.inputs["Color1"])
        links.new(geo.outputs["Pointiness"], wear.inputs["Color2"])
        mask = wear.outputs["Color"]
    elif family == "moss":
        mask = ramp(coarse, (0, 0, 0, 1), (1, 1, 1, 1), (.4, .6))
        height = noise(85, 6)

    base = ramp(mask, rgba(b), rgba(a), (.32, .67))
    if family == "stone":
        base = ramp(coarse, tuple(v * .85 for v in rgba(a)[:3]) + (1,), rgba(a))
    if family in {"stone", "weathered", "layered", "moss"}:
        pores = nodes.new("ShaderNodeTexVoronoi")
        pores.distance = "EUCLIDEAN"
        pores.inputs["Scale"].default_value = 180 if family == "stone" else 65
        links.new(vector, pores.inputs["Vector"])
        pits = ramp(pores.outputs["Distance"], (.08, .08, .08, 1), (1, 1, 1, 1), (.09, .24))
        height_mix = nodes.new("ShaderNodeMixRGB")
        height_mix.blend_type = "MULTIPLY"
        height_mix.inputs["Fac"].default_value = .65
        links.new(height, height_mix.inputs["Color1"])
        links.new(pits, height_mix.inputs["Color2"])
        height = height_mix.outputs["Color"]
        patina = nodes.new("ShaderNodeMixRGB")
        patina.blend_type = "MULTIPLY"
        patina.inputs["Fac"].default_value = .12 if family == "stone" else .36
        links.new(base, patina.inputs["Color1"])
        links.new(pits, patina.inputs["Color2"])
        base = patina.outputs["Color"]
    if family == "weathered":
        stains = ramp(noise(8, 6), (1, 1, 1, 1), rgba("monument_shadow"), (.46, .66))
        stain_mix = nodes.new("ShaderNodeMixRGB")
        stain_mix.blend_type = "MULTIPLY"
        stain_mix.inputs["Fac"].default_value = .65
        links.new(base, stain_mix.inputs["Color1"])
        links.new(stains, stain_mix.inputs["Color2"])
        base = stain_mix.outputs["Color"]
    if family == "water":
        base = ramp(coarse, rgba(a), tuple(.82 * v + .18 * w for v, w in zip(rgba(a)[:3], rgba(b)[:3])) + (1,))
    if family in {"crystal", "energy"}:
        cells = nodes.new("ShaderNodeTexVoronoi")
        cells.feature = "DISTANCE_TO_EDGE"
        cells.inputs["Scale"].default_value = 7
        links.new(vector, cells.inputs["Vector"])
        fractures = ramp(cells.outputs["Distance"], (1, 1, 1, 1), (0, 0, 0, 1), (.007, .025))
        base = ramp(coarse, rgba("violet_shadow"), rgba("violet_body"))
    links.new(base, bsdf.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = max(.08, roughness - .13)
    rough.inputs["To Max"].default_value = min(1, roughness + .08)
    links.new(fine, rough.inputs["Value"])
    links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    micro = nodes.new("ShaderNodeBump")
    micro.inputs["Strength"].default_value = .24
    micro.inputs["Distance"].default_value = depth * .22
    links.new(fine, micro.inputs["Height"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .48
    bump.inputs["Distance"].default_value = depth
    links.new(height, bump.inputs["Height"])
    links.new(micro.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if family in {"crystal", "energy"}:
        bsdf.inputs["IOR"].default_value = 1.52
        bsdf.inputs["Emission Color"].default_value = rgba("violet_glow" if family == "crystal" else "violet_body")
        links.new(multiply(fractures, .55 if family == "crystal" else 3), bsdf.inputs["Emission Strength"])
    return mat

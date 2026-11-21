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
    "monument_white": ("monument_white", "monument_shadow", .76, .003, "stone"),
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
    "ochre_inlay": ("accent_ochre", "sandstone", .69, .001, "inlay"),
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

    def mix(factor, first, second, blend="MIX"):
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = blend
        if isinstance(factor, (float, int)):
            node.inputs["Fac"].default_value = factor
        else:
            links.new(factor, node.inputs["Fac"])
        for value, socket in ((first, "Color1"), (second, "Color2")):
            if isinstance(value, tuple):
                node.inputs[socket].default_value = value
            else:
                links.new(value, node.inputs[socket])
        return node.outputs["Color"]

    def toned(key, gain):
        return tuple(v * gain for v in rgba(key)[:3]) + (1,)

    def stretched(factors):
        node = nodes.new("ShaderNodeVectorMath")
        node.operation = "MULTIPLY"
        node.inputs[1].default_value = factors
        links.new(vector, node.inputs[0])
        return node.outputs["Vector"]

    def wave(scale, distortion, vector=vector):
        node = nodes.new("ShaderNodeTexWave")
        node.bands_direction = "DIAGONAL"
        node.inputs["Scale"].default_value = scale
        node.inputs["Distortion"].default_value = distortion
        node.inputs["Detail"].default_value = 5
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

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

    base = ramp(mask, rgba(b), rgba(a), (.32, .67))
    if family == "stone":
        mineral = ramp(noise(1.8, 3), toned(a, .68), rgba(a), (.42, .58))
        base = mix(.3, mineral, ramp(noise(12), toned(a, .67), rgba(a)))
        base = mix(.32, base, ramp(noise(65, 5), (.6, .6, .6, 1), (1, 1, 1, 1)), "MULTIPLY")
        geo = nodes.new("ShaderNodeNewGeometry")
        wear = ramp(geo.outputs["Pointiness"], (0, 0, 0, 1), (1, 1, 1, 1), (.49, .52))
        base = mix(multiply(wear, .2), base, rgba(a))
        height = noise(65, 6)
    if family in {"stone", "weathered", "layered", "moss"}:
        pores = nodes.new("ShaderNodeTexVoronoi")
        pores.distance = "EUCLIDEAN"
        pores.inputs["Scale"].default_value = 65
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
    if family == "moss":
        geo = nodes.new("ShaderNodeNewGeometry")
        normal = nodes.new("ShaderNodeSeparateXYZ")
        links.new(geo.outputs["Normal"], normal.inputs["Vector"])
        up = ramp(normal.outputs["Z"], (0, 0, 0, 1), (1, 1, 1, 1), (.12, .88))
        growth = mix(1, up, ramp(noise(3, 6), (.25, .25, .25, 1), (1, 1, 1, 1)), "MULTIPLY")
        growth = ramp(growth, (0, 0, 0, 1), (1, 1, 1, 1), (.12, .7))
        warp = mix(.35, vector, noise(2), "ADD")
        cells = nodes.new("ShaderNodeTexVoronoi")
        cells.feature = "DISTANCE_TO_EDGE"
        cells.inputs["Scale"].default_value = 3.8
        links.new(warp, cells.inputs["Vector"])
        fading = nodes.new("ShaderNodeMath")
        fading.operation = "ADD"
        links.new(cells.outputs["Distance"], fading.inputs[0])
        links.new(multiply(noise(5), .055), fading.inputs[1])
        cracks = ramp(fading.outputs[0], (.12, .12, .12, 1), (1, 1, 1, 1), (.012, .055))
        rock = ramp(coarse, toned("canyon_strata", .3), rgba("canyon_strata"))
        rock = mix(.75, rock, cracks, "MULTIPLY")
        fibers = noise(1, 5, stretched((90, 90, 16)))
        moss_color = ramp(fibers, toned("moss", .55), rgba("moss"), (.25, .78))
        base = mix(growth, rock, moss_color)
        height = mix(growth, mix(.55, noise(90, 6), cracks, "MULTIPLY"), fibers)
    if family == "inlay":
        bands = wave(2.8, .08)
        design = ramp(bands, (0, 0, 0, 1), (1, 1, 1, 1), (.72, .79))
        ochre = ramp(coarse, rgba("sandstone"), rgba("accent_ochre"))
        base = mix(design, ochre, toned("sandstone", .42))
        height = mix(.8, fine, design)
    if family == "crystal":
        cells = nodes.new("ShaderNodeTexVoronoi")
        cells.inputs["Scale"].default_value = 3.5
        links.new(stretched((1, 1, .48)), cells.inputs["Vector"])
        cell_tone = nodes.new("ShaderNodeSeparateXYZ")
        links.new(cells.outputs["Color"], cell_tone.inputs["Vector"])
        body = ramp(cell_tone.outputs["X"], toned("violet_shadow", .18), rgba("violet_body"), (.15, .9))
        bands = noise(1, 6, stretched((8, 8, .7)))
        inclusions = ramp(bands, (.38, .38, .38, 1), (1, 1, 1, 1), (.25, .8))
        base = mix(.55, body, inclusions, "MULTIPLY")
        facet = nodes.new("ShaderNodeVectorMath")
        facet.operation = "SUBTRACT"
        facet.inputs[1].default_value = (.5, .5, .5)
        links.new(cells.outputs["Color"], facet.inputs[0])
        tilt = nodes.new("ShaderNodeVectorMath")
        tilt.operation = "SCALE"
        tilt.inputs[3].default_value = .65
        links.new(facet.outputs["Vector"], tilt.inputs[0])
        geo = nodes.new("ShaderNodeNewGeometry")
        facet_normal = nodes.new("ShaderNodeVectorMath")
        facet_normal.operation = "ADD"
        links.new(geo.outputs["Normal"], facet_normal.inputs[0])
        links.new(tilt.outputs["Vector"], facet_normal.inputs[1])
        cracks = ramp(noise(9, 5, stretched((1, 1, .16))), (0, 0, 0, 1), (1, 1, 1, 1), (.73, .85))
        bsdf.inputs["Emission Color"].default_value = rgba("violet_glow")
        links.new(multiply(cracks, .16), bsdf.inputs["Emission Strength"])
    if family == "energy":
        flow = noise(1, 6, stretched((5, 5, .65)))
        core = ramp(flow, (0, 0, 0, 1), (1, 1, 1, 1), (.38, .7))
        base = ramp(flow, toned("violet_body", .6), toned("violet_glow", .8), (.3, .72))
        links.new(base, bsdf.inputs["Emission Color"])
        gain = nodes.new("ShaderNodeMapRange")
        gain.inputs["To Min"].default_value = .7
        gain.inputs["To Max"].default_value = 2.5
        links.new(core, gain.inputs["Value"])
        links.new(gain.outputs["Result"], bsdf.inputs["Emission Strength"])
        bsdf.inputs["Specular IOR Level"].default_value = .12
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
    if family == "crystal":
        links.new(facet_normal.outputs["Vector"], micro.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if family in {"crystal", "energy"}:
        bsdf.inputs["IOR"].default_value = 1.52
    return mat

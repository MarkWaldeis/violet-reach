"""Faceted mineral growth. Dimensions are in metres, Z up."""
import math
import random

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.noise import noise_vector

import vrlib
import vrmat


def make_mesh(name, vertices, faces, materials):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    for material in materials:
        mesh.materials.append(vrmat.get(material) if isinstance(material, str) else material)
    vrlib.link_to_source(obj)
    return obj


def hull(points):
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in points]
    result = bmesh.ops.convex_hull(bm, input=verts)
    discarded = set(result["geom_interior"] + result["geom_unused"])
    bmesh.ops.delete(bm, geom=[v for v in verts if v in discarded], context="VERTS")
    return bm


def trim(bm, point, normal, material):
    result = bmesh.ops.bisect_plane(
        bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
        plane_co=point, plane_no=normal, dist=0.000001, clear_outer=True,
    )
    edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
    if edges:
        for face in bmesh.ops.holes_fill(bm, edges=edges, sides=0)["faces"]:
            face.material_index = material


def from_bmesh(name, bm, materials):
    bm = clean_edges(bm)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    obj = make_mesh(name, [], [], materials)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def apply(obj, mod):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def clean_edges(bm):
    for tolerance in (.00008, .00001):
        cleaned = bm.copy()
        bmesh.ops.dissolve_degenerate(cleaned, dist=tolerance, edges=list(cleaned.edges))
        if all(edge.is_manifold for edge in cleaned.edges):
            bm.free()
            return cleaned
        cleaned.free()
    return bm


def arrises(obj, width):
    mod = obj.modifiers.new("Worn edges", "BEVEL")
    mod.width, mod.segments = width, 3
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(24)
    mod.harden_normals = True
    apply(obj, mod)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm = clean_edges(bm)
    bm.to_mesh(obj.data)
    bm.free()


def optical_finish(height, radius, tint):
    """Opaque for baking; a subsurface lobe and spatial phantom zones give optical depth."""
    palette = vrmat.load_palette()
    mat = vrmat.get("violet_crystal").copy()
    mat.name = "Violet | phantom growth"
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    coord = next(n for n in nodes if n.type == "TEX_COORD").outputs["Object"]

    def scalar(op, a, b):
        node = nodes.new("ShaderNodeMath")
        node.operation = op
        for value, socket in zip((a, b), node.inputs):
            if isinstance(value, (int, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs[0]

    def color(key, gain, warmth=1):
        r, g, b = palette[key]["linear_rgb"]
        return (r * gain * warmth, g * gain * .76, b * gain / warmth, 1)

    def ramp(fac, stops):
        node = nodes.new("ShaderNodeValToRGB")
        elements = node.color_ramp.elements
        for i, (position, rgb) in enumerate(stops):
            e = elements[i] if i < 2 else elements.new(position)
            e.position, e.color = position, rgb
        links.new(fac, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(fac, a, b):
        node = nodes.new("ShaderNodeMixRGB")
        for value, socket in zip((fac, a, b), node.inputs):
            if isinstance(value, (tuple, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs[0]

    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord, xyz.inputs[0])
    x, y, z = xyz.outputs
    # These nested chevrons share one growth origin, rather than repeating surface stripes.
    axial = scalar("DIVIDE", z, height)
    wedge = scalar("ADD", scalar("MULTIPLY", x, 1.7), scalar("MULTIPLY", y, .95))
    plane = scalar("ADD", axial, scalar("MULTIPLY", scalar("ABSOLUTE", wedge, 0), .105 / radius))
    dark = color("violet_shadow", .29 * tint, 1.38)
    purple = color("violet_body", .73 * tint, 1.44)
    light = color("violet_body", 1.25 * tint, 1.40)
    middle = color("violet_body", .45 * tint, 1.46)
    phantom = ramp(plane, [(0, dark), (.27, dark), (.38, middle), (.44, dark),
                           (.58, dark), (.672, purple), (.709, light), (.755, middle),
                           (.87, purple), (1, light)])
    plane_variation = nodes.new("ShaderNodeAttribute")
    plane_variation.attribute_name = "cleavage"
    phantom = mix(plane_variation.outputs["Fac"], phantom, light)
    base = bsdf.inputs["Base Color"]
    original = base.links[0].from_socket
    links.new(mix(.105, phantom, original), base)
    bsdf.inputs["Subsurface Weight"].default_value = .34
    bsdf.inputs["Subsurface Scale"].default_value = radius * .36
    bsdf.inputs["Subsurface Radius"].default_value = (1, .19, .75)
    bsdf.inputs["Coat Weight"].default_value = .08
    bsdf.inputs["Coat Roughness"].default_value = .23
    bsdf.inputs["Specular IOR Level"].default_value = .29
    # Keep the library's emissive colour anchor but reserve strong light for energy assets.
    links.new(scalar("MULTIPLY", bsdf.inputs["Emission Strength"].links[0].from_socket, .27),
              bsdf.inputs["Emission Strength"])
    return mat


def score_face(obj, outline, side, height, radius, z, rng, fork=False):
    """Excavate a tapered, meandering cleavage groove directly into a long face."""
    a, b = outline[side], outline[(side + 1) % len(outline)]
    span = (b - a).length
    normal = Vector((b.y - a.y, a.x - b.x, 0)).normalized()
    if fork:
        profile = [(0, .158, .70), (.18, .195, .65), (.48, .27, .48),
                   (.73, .351, .32), (1, .373, .04)]
    else:
        profile = [(0, .19, .19), (.19, .145, 1.), (.37, .205, .85),
                   (.51, .175, .78), (.68, .255, .60), (.83, .225, .42), (1, .30, .07)]
    verts = []
    for along, across, width in profile:
        h = z + along * height * (.145 if fork else .27)
        t = across + rng.uniform(-.015, .015)
        p = a.lerp(b, t) * (1 - .16 * h / height) + Vector((0, 0, h))
        half = min(radius * .042, span * .032) * width
        tangent = (b - a).normalized()
        verts.extend((p - tangent * half + normal * (.021 * radius),
                      p + tangent * half + normal * (.021 * radius),
                      p - normal * (.085 * radius * width)))
    faces = [(0, 2, 1)]
    for i in range(0, len(verts) - 3, 3):
        for j in range(3):
            k = (j + 1) % 3
            faces.extend(((i+j, i+k, i+3+k), (i+j, i+3+k, i+3+j)))
    faces.append(tuple(range(len(verts) - 3, len(verts))))
    cutter = make_mesh("Cleavage cutter", verts, faces, [])
    bm = bmesh.new()
    bm.from_mesh(cutter.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(cutter.data)
    bm.free()
    cut = obj.modifiers.new("Open cleavage", "BOOLEAN")
    cut.operation, cut.solver, cut.object = "DIFFERENCE", "EXACT", cutter
    apply(obj, cut)
    mesh = cutter.data
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(mesh)


def prism(name, foot, direction, length, radius, sides, roll, rng, damage=0, grooves=0):
    angles = [roll + math.tau * (i + rng.uniform(-.16, .16)) / sides for i in range(sides)]
    outline = [radius * rng.uniform(.87, 1.11) * Vector((math.cos(a), math.sin(a), 0)) for a in angles]
    # One tapered prism. The cap and spalls are new planes cut into the same solid.
    bm = hull(outline + [v * .84 + Vector((0, 0, length)) for v in outline])
    cap_angle = roll + rng.uniform(-.5, .5)
    cap_height = length * (.99 if damage != 2 else .88)
    for i, tilt in enumerate((1.02, .69, .84)):
        angle = cap_angle + i * math.tau / 3 + rng.uniform(-.16, .16)
        trim(bm, (0, 0, cap_height - rng.uniform(0, .14) * radius),
             (math.cos(angle), math.sin(angle), tilt), 0)
    if damage:
        for i, v in enumerate(outline):
            if i % 2 != damage % 2:
                continue
            n = v.normalized()
            h = rng.uniform(.54, .81) * cap_height
            trim(bm, v * rng.uniform(.84, .92) + Vector((0, 0, h)), n + Vector((0, 0, .09)), 0)
        if damage == 2:
            trim(bm, (radius * .06, 0, cap_height - .26 * radius), (-.23, .4, 1), 0)
    obj = from_bmesh(name, bm, [optical_finish(length, radius, rng.uniform(.77, 1.21))])
    for i in range(grooves):
        side = (i * 2 + int(sides * .3)) % sides
        z = length * (.24 + i * .115)
        score_face(obj, outline, side, length, radius, z, rng)
        if grooves >= 2:
            score_face(obj, outline, side, length, radius, z + .0513 * length, rng, fork=True)
    arrises(obj, min(.014, radius * .025))
    attribute = obj.data.attributes.new("cleavage", "FLOAT", "FACE")
    for face in obj.data.polygons:
        n = face.normal
        phase = math.atan2(n.y, n.x)
        attribute.data[face.index].value = min(.83, .139 * (math.sin(1.7 + 2.7 * phase) + 1)
                                                + .48 * max(0, n.z))
    rotation = Vector(direction).to_track_quat("Z", "Y")
    lowest = min((rotation @ v.co).z for v in obj.data.vertices)
    obj.location = (foot[0], foot[1], max(foot[2], -.040-lowest))
    obj.rotation_euler = rotation.to_euler()
    return obj


def strata(name, centre, outline, top, thickness, rng, material):
    """An individual, displaced sedimentary bed with a split, shelved margin."""
    z0 = max(-.033, top - thickness)
    cx, cy = centre
    skew = rng.uniform(-.19, .19), rng.uniform(-.11, .11)
    phases = [rng.uniform(-.19, .19) for _ in outline]
    points = []
    for fraction, inset in ((0, .89), (.27, 1), (.70, .96), (1, .76)):
        for (x, y), phase in zip(outline, phases):
            points.append((cx + x * inset + skew[0] * fraction,
                           cy + y * inset + skew[1] * fraction,
                           max(-.033, z0 + thickness * (fraction + phase * min(fraction * 3, 1)))))
    bm = hull(points)
    for i in rng.sample(range(len(outline)), min(3, len(outline))):
        x, y = outline[i]
        trim(bm, (cx + .91*x, cy + .91*y, z0+.45*thickness), (x, y, .21), 0)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=3, use_grid_fill=True)
    for v in bm.verts:
        size = min(.044, thickness * .125)
        n = noise_vector(v.co * 11.7)
        v.co.x += size * n.x
        v.co.y += size * n.y
        v.co.z = max(-.039, v.co.z + size * n.z)
    obj = from_bmesh(name, bm, [material])
    for face in obj.data.polygons:
        face.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(31))
    return obj


def scree(rng, i, x, y, z, size, height, material):
    sides = rng.choice((5, 6, 7, 9))
    yaw = rng.random() * math.tau
    outline = []
    for k in range(sides):
        a = yaw + math.tau * (k + rng.uniform(-.18, .18)) / sides
        outline.append((size * rng.uniform(.69, 1.18) * math.cos(a),
                        size * rng.uniform(.42, 1.0) * math.sin(a)))
    strata(f"Loose split {i:02d}", (x, y), outline, z + height, height + .029, rng, material)


def rubble_bed():
    surfaces = [BVHTree.FromPolygons([v.co for v in obj.data.vertices],
                                    [face.vertices[:] for face in obj.data.polygons])
                for obj in vrlib.source_objects()]

    def ground_at(x, y):
        return max(0, max((hit.z for surface in surfaces
                          if (hit := surface.ray_cast((x, y, 3), (0, 0, -1))[0]) is not None), default=0))

    return ground_at


def rim(rng):
    west = [(-1.06,-1.41),(.08,-1.34),(.48,-.60),(.26,-.18),(.42,.41),
            (.19,.94),(.02,1.42),(-1.01,1.66),(-1.66,1.04),(-1.82,.12),(-1.58,-.68)]
    east = [(-.47,-1.45),(.25,-1.49),(1.24,-1.13),(1.66,-.71),(1.58,.22),(1.18,1.10),
            (.89,1.56),(.12,1.46),(-.21,.89),(-.13,.31),(-.37,-.29),(-.30,-.81)]
    stacks = [
        ("West exposed bed", (-.56,.02), west, .47, .50, "canyon_layered"),
        ("Uplifted chalk escarpment", (-.61,.13), [(x*.94,y*.92) for x,y in west],
         1.19, .79, "canyon_layered"),
        ("Slipped crest", (-.66,.29), [(-1.23,-.59),(-.98,-1.13),(-.17,-1.05),
                                          (.31,-.38),(.16,.16),(.29,.69),(-.22,1.14),(-1.10,.95)],
         1.57, .43, "monument_white"),
        ("East exposed bed", (.64,-.14), east, .49, .51, "canyon_layered"),
        ("Lowered fault scarp", (.69,-.06), [(x*.86,y*.91) for x,y in east],
         1.12, .66, "canyon_layered"),
        ("East tongue", (.63,-.59), [(-.32,-.65),(.71,-.39),(.92,.19),(.35,.56),(-.40,.24)],
         1.29, .24, "monument_white"),
        ("Eroded apron", (-1.70,-.57), [(-.72,-.87),(.12,-1.1),(.81,-.52),(.69,.27),(-.18,.97),(-.75,.66)],
         .49, .51, "canyon_layered"),
        ("Fault continuation", (.03,1.58), [(-.91,-.41),(.15,-.50),(.84,-.24),(.76,.49),(.21,.77),
                                           (-.47,.53)], .45, .47, "monument_weathered"),
        ("Runout", (.72,1.71), [(-.47,-.43),(.28,-.48),(.72,.07),(.55,.31),(-.23,.55),(-.51,.21)],
         .24, .26, "canyon_layered"),
        ("Overturned fragment", (-1.11,-1.36), [(-.85,-.35),(-.46,-.79),(.25,-.57),(.92,-.12),
                                              (.72,.37),(-.07,.61),(-.68,.42)],
         .36, .38, "monument_weathered"),
    ]
    for name, centre, outline, top, thickness, material in stacks:
        strata(name, centre, outline, top, thickness, rng, material)
    strata("Earth in the fault", (.02,-.02), [(-.42,-1.59),(.33,-1.34),(.46,.72),(.2,1.91),
           (-.3,1.76),(-.53,.21)], .241, .245, rng, "forest_soil")


def build():
    rng = random.Random(247611)
    rim(rng)
    ground_at = rubble_bed()
    growth = [
        ("Leaning fracture spire", (.04,.02,.16), (.175,-.077,1), 7.32,.85,7,.91,1,3),
        ("Paired blade", (.11,.33,.31), (.41,.37,.92), 4.86,.58,6,.3,2,2),
        ("Split back face", (-.15,.65,.24), (-.21,.49,.92), 4.34,.47,5,1.11,1,2),
        ("Slip twin", (-.27,-.28,.23), (-.57,-.12,.92), 3.93,.40,6,.59,0,2),
        ("Headward shard", (.09,-.57,.19), (.18,-.72,.87), 3.36,.36,5,1.4,2,1),
        ("Spall above upper bank", (-.61,-.11,1.21), (-.91,-.21,.66), 2.18,.278,6,.81,1,1),
        ("Right-side strain", (.37,.11,.51), (.86,-.21,.68), 2.21,.29,7,1.2,2,1),
        ("Pinkish lamella", (.20,.75,.57), (.10,.74,.90), 2.11,.26,5,.37,0,1),
        ("Backbank daughter", (-.42,.85,.72), (-.33,.74,.72), 1.59,.22,6,.8,1,0),
        ("Fault seam spike", (.14,-1.04,.31), (.35,-.42,.81), 1.52,.215,5,.8,2,0),
        ("Buried splinter", (-.15,1.21,.23), (.17,.82,.62), 1.33,.20,7,.31,2,0),
        ("Vein offshoot", (-.24,-.67,.45), (-.23,-.41,.86), .94,.13,5,1.81,1,0),
    ]
    for name, foot, direction, length, radius, sides, roll, damage, grooves in growth:
        prism(name, foot, direction, length, radius, sides, roll, rng, damage, grooves)
    for i in range(59):
        a = rng.choice((-.7, 1.29, 2.7, 4.15)) + rng.uniform(-.40,.42)
        r = rng.uniform(1.35,2.40)
        x,y = r*math.cos(a),.84*r*math.sin(a)
        size = .048 + .33 * rng.random()**2.2
        scree(rng, i, x,y,ground_at(x,y)-size*.12,size,size*rng.uniform(.25,.75),
              rng.choice(("canyon_layered", "monument_weathered", "monument_white")))
    for i in range(14):
        y = rng.choice((-1,1))*rng.uniform(.85,1.7)
        x = .27 * math.sin(y*3) + rng.uniform(-.22,.22)
        prism(f"Fault mineral {i+1:02d}", (x,y,ground_at(x,y)-.024), (rng.uniform(-.4,.4),y*.5,1),
              rng.uniform(.21,.63),rng.uniform(.042,.12),rng.choice((5,6,7)),rng.random(),rng,2)

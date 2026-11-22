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


def open_soil():
    # Uneven tapered skirt with no vertical edge where it meets the surrounding ground.
    n = 101
    verts = [(0, 0, .115)]
    for k in range(1, 14):
        t = k / 13
        for i in range(n):
            a = math.tau * i / n
            r = t * (1 + .12*math.sin(3*a+.8) + .075*math.sin(5*a)
                       + .024*math.cos(9*a) + .019*math.sin(15*a))
            x, y = 2.24 * r * math.cos(a), 1.76 * r * math.sin(a)
            noise = noise_vector(Vector((x * 4 + 3, y * 4, 1))).z
            z = .004 + (1-t*t) * (.104 + .042 * noise + .021*math.sin(a*7 + t*8))
            verts.append((x, y, z))
    faces = [(0, 1+i, 1+(i+1)%n) for i in range(n)]
    for k in range(12):
        for i in range(n):
            a, b = 1+k*n+i, 1+k*n+(i+1)%n
            faces.append((a, a+n, b+n, b))
    bottom = len(verts)
    verts.append((0, 0, -.018))
    for i in range(n):
        a, b = 1+12*n+i, 1+12*n+(i+1)%n
        faces.append((b, a, bottom))
    obj = make_mesh("Open mineral earth", verts, faces, ["forest_soil"])
    for face in obj.data.polygons:
        face.use_smooth = True


def build():
    rng = random.Random(315713)
    open_soil()
    beds = [
        ("Footwall toe", (-.74, .23), [(-.99,-.17),(-.57,-.57),(.11,-.7),(.8,-.25),(.69,.36),
                                      (.0,.72),(-.72,.51)], .355, .29, "canyon_layered"),
        ("Split shelf", (-.48, .33), [(-.94,-.09),(-.56,-.43),(.16,-.48),(.60,-.12),
                                     (.37,.45),(-.21,.53),(-.82,.28)], .54, .205, "monument_white"),
        ("Slid cap", (-.60, .22), [(-.75,-.18),(-.21,-.44),(.37,-.3),(.55,.02),
                                   (.26,.40),(-.47,.32),(-.67,.16)], .68, .15, "canyon_layered"),
        ("Broken hanging wall", (.62, -.06), [(-.33,-.59),(.27,-.63),(1.02,-.14),(.81,.47),
                                              (.11,.52),(-.38,.28)], .48, .40, "canyon_layered"),
        ("Raised jaw", (.68, .11), [(-.38,-.31),(.21,-.41),(.84,-.08),(.66,.35),
                                   (.19,.59),(-.43,.19)], .76, .30, "monument_white"),
        ("Ledge fragment", (.99, -.41), [(-.11,-.45),(.42,-.32),(.71,.10),(.39,.28),(-.38,.13)],
                                       .27, .21, "monument_weathered"),
        ("Fault apron", (-.57, -.72), [(-.71,-.22),(-.24,-.42),(.32,-.32),(.63,.11),(.38,.32),(-.40,.38)],
                                     .24, .17, "monument_weathered"),
    ]
    for name, centre, outline, top, thickness, material in beds:
        strata(name, centre, outline, top, thickness, rng, material)
    ground_at = rubble_bed()
    shoots = [
        ("Dominant violet", (-.28,.16,.30), (.29,-.08,1), 2.92,.60,7,.9,1,3),
        ("Right counterweight", (.03,.16,.30), (.85,.44,.99), 1.92,.385,5,.4,2,2),
        ("Low splitting tooth", (-.31,.22,.36), (-.86,.28,.71), 1.82,.34,6,.7,1,1),
        ("Forked rear blade", (-.16,.34,.47), (-.12,.76,.89), 1.71,.30,6,1.16,0,1),
        ("Near broken shoulder", (-.04,-.12,.34), (.35,-.85,.73), 1.51,.28,5,.17,2,1),
        ("Above the back shelf", (.36,.32,.59), (.32,.63,.78), 1.10,.23,7,.56,1,1),
        ("Groundward twin", (-.39,.05,.27), (-.49,-.66,.56), .94,.206,5,.1,1,0),
        ("Sliver in the cap", (-.67,.29,.56), (-.63,.20,.83), .72,.14,6,.8,0,0),
        ("Cleaved foot satellite", (.82,-.29,.32), (.61,-.36,.78), .77,.19,7,.58,2,0),
        ("New shoot", (.61,.33,.63), (.68,.33,.81), .59,.113,5,.97,0,0),
        ("Embedded shard", (-.25,-.72,.17), (.17,-.62,.40), .69,.158,6,1.6,2,0),
    ]
    for name, foot, direction, length, radius, sides, roll, damage, grooves in shoots:
        prism(name, foot, direction, length, radius, sides, roll, rng, damage, grooves)
    for i in range(47):
        # Three local debris fans, leaving open earth between them.
        a = rng.choice((.32, 2.81, 4.96)) + rng.uniform(-.52, .48)
        r = rng.uniform(.77, 1.84)
        x, y = r*math.cos(a), .88*r*math.sin(a)
        size = .047 + rng.random()**2.4 * .24
        scree(rng, i, x, y, ground_at(x,y)-size*.12, size, size*rng.uniform(.24,.68),
              rng.choice(("monument_weathered", "canyon_layered", "monument_white")))
    for i in range(13):
        a = rng.uniform(0, math.tau)
        x, y = rng.uniform(.68, 1.42)*math.cos(a), rng.uniform(.48, .94)*math.sin(a)
        prism(f"Fissure chip {i+1:02d}", (x,y,ground_at(x,y)-.024), (math.cos(a),math.sin(a),rng.uniform(.4,1.2)),
              rng.uniform(.15,.37),rng.uniform(.04,.085),rng.choice((5,6,7)),a,rng,2)

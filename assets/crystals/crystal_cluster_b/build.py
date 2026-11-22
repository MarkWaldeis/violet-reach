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


def clean_edges(bm):
    for tolerance in (.00008, .00001):
        cleaned = bm.copy()
        bmesh.ops.dissolve_degenerate(cleaned, dist=tolerance, edges=list(cleaned.edges))
        if all(edge.is_manifold for edge in cleaned.edges):
            bm.free()
            return cleaned
        cleaned.free()
    return bm


def optical_finish():
    palette = vrmat.load_palette()
    mat = vrmat.get("violet_crystal").copy()
    mat.name = "Violet | indigo heart and growth zones"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for key in ("Normal", "Roughness", "Emission Color", "Emission Strength"):
        for link in list(bsdf.inputs[key].links):
            links.remove(link)
    bsdf.inputs["Roughness"].default_value = .43
    bsdf.inputs["Specular IOR Level"].default_value = .07

    def attr(name):
        result = nodes.new("ShaderNodeAttribute")
        result.attribute_name = name
        return result.outputs

    def math_node(op, a, b):
        result = nodes.new("ShaderNodeMath")
        result.operation = op
        for value, socket in zip((a,b), result.inputs):
            if isinstance(value, (int,float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return result.outputs[0]

    def ramp(source, stops, interpolation="EASE"):
        result = nodes.new("ShaderNodeValToRGB")
        result.color_ramp.interpolation = interpolation
        for i, (position, color) in enumerate(stops):
            elements = result.color_ramp.elements
            element = elements[i] if i < 2 else elements.new(position)
            element.position, element.color = position, color
        links.new(source, result.inputs["Fac"])
        return result.outputs["Color"]

    def mix(factor, a, b):
        result = nodes.new("ShaderNodeMixRGB")
        for value, socket in zip((factor,a,b), result.inputs):
            links.new(value, socket)
        return result.outputs[0]

    def color(key, gains):
        return (*(c*g for c,g in zip(palette[key]["linear_rgb"], gains)), 1)

    axis = attr("crystal axis metres")
    height = attr("crystal axial height")["Fac"]
    distance = nodes.new("ShaderNodeVectorMath")
    distance.operation = "LENGTH"
    links.new(axis["Vector"], distance.inputs[0])
    radial = math_node("ADD", math_node("MULTIPLY", distance.outputs["Value"], .93),
                       math_node("MULTIPLY", attr("crystal radial distance")["Fac"], .07))
    indigo = color("violet_shadow", (.38,.22,.33))
    violet = color("violet_body", (.80,.55,.79))
    lavender = color("violet_glow", (.75,.67,.98))
    shell = ramp(radial, [(.79,indigo), (1.04,lavender), (.89,violet), (.96, violet)])
    black, white = (0,0,0,1), (1,1,1,1)
    random = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    xy = nodes.new("ShaderNodeSeparateXYZ")
    links.new(axis["Vector"], xy.inputs[0])
    strata = math_node("ADD", height, math_node("ADD", math_node("MULTIPLY", xy.outputs["X"], .041),
                                                math_node("MULTIPLY", random, .074)))
    band = ramp(strata, [(0,black), (1,black), (.39,(.21,.21,.21,1)), (.411,black),
                         (.66,(.34,.34,.34,1)), (.692,black)], "CONSTANT")
    inner = ramp(radial, [(.78,(.83,.83,.83,1)), (1,black), (.89,white)])
    tip = ramp(height, [(.79,black), (.99,(.76,.76,.76,1)), (.915,(.56,.56,.56,1))])
    shell = mix(math_node("MAXIMUM", tip, math_node("MULTIPLY", band, inner)),
                shell, ramp(height, [(0,lavender), (1,lavender)]))

    tint = nodes.new("ShaderNodeHueSaturation")
    links.new(math_node("ADD", .484, math_node("MULTIPLY", random, .036)), tint.inputs["Hue"])
    links.new(math_node("ADD", .88, math_node("MULTIPLY", random, .19)), tint.inputs["Value"])
    links.new(shell, tint.inputs["Color"])
    links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])

    rim = nodes.new("ShaderNodeLayerWeight")
    rim.inputs["Blend"].default_value = .38
    links.new(math_node("MULTIPLY", rim.outputs["Facing"], .17), bsdf.inputs["Emission Strength"])
    bsdf.inputs["Emission Color"].default_value = lavender
    return mat


def fracture_finish():
    name = "Violet | sunken cleavage"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    palette = vrmat.load_palette()
    mat = vrmat.get("violet_crystal").copy()
    mat.name = name
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    for key in ("Base Color", "Normal", "Emission Color", "Emission Strength"):
        for link in list(bsdf.inputs[key].links):
            mat.node_tree.links.remove(link)
    bsdf.inputs["Base Color"].default_value = (*(v*.36 for v in palette["violet_shadow"]["linear_rgb"]), 1)
    bsdf.inputs["Emission Color"].default_value = (*palette["violet_body"]["linear_rgb"], 1)
    bsdf.inputs["Emission Strength"].default_value = .72
    return mat


def inset_fracture(obj, outline, radius, length, rotation, material):
    front = rotation.inverted() @ Vector((1,.42,.03))
    corner = max(range(len(outline)), key=lambda i: outline[i].normalized().dot(front))
    left, tip, right = (outline[(corner+i)%len(outline)] for i in (-1,0,1))
    points = []
    for edge, z, span in ((left.lerp(tip,.22), .57, .15), (left.lerp(tip,.48), .60, .72),
                          (left.lerp(tip,.72), .587, 1), (tip,.63,.86),
                          (tip.lerp(right,.34), .67,.74), (tip.lerp(right,.72), .65,.12)):
        p = edge*(1-.18*z)+Vector((0,0,z*length))
        normal = edge.normalized()
        up = Vector((0,0,.057*radius*span))
        points.extend((p+normal*radius*.11-up, p+normal*radius*.11+up,
                       p-normal*radius*.13*span))
    faces = [(2,1,0)]
    for i in range(0,len(points)-3,3):
        for j in range(3):
            k = (j+1)%3
            faces.append((i+j,i+k,i+3+k,i+3+j))
    faces.append(tuple(range(len(points)-3,len(points))))
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in points]
    for face in faces:
        bm.faces.new([verts[i] for i in face])
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    cutter = from_bmesh("Cleavage cutter", bm, [material])
    cut = obj.modifiers.new("Recessed cleavage", "BOOLEAN")
    cut.operation, cut.solver, cut.object = "DIFFERENCE", "EXACT", cutter
    cut.material_mode = "TRANSFER"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=cut.name)
    data = cutter.data
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(data)


def prism(name, foot, direction, length, radius, sides, roll, rng, damage=0, fracture=False):
    angles = [roll + math.tau*(i+rng.uniform(-.13,.13))/sides for i in range(sides)]
    outline = [radius*rng.uniform(.95,1.05)*Vector((math.cos(a),math.sin(a),0)) for a in angles]
    bm = hull(outline + [v*.82 + Vector((0,0,length)) for v in outline])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bmesh.ops.dissolve_limit(bm, angle_limit=.0001, verts=list(bm.verts), edges=list(bm.edges))
    cap_angle = roll + rng.uniform(-.5,.5)
    cap_height = length*(.995 if damage != 2 else .93)
    for i, tilt in enumerate((1.08,.82,.96)):
        angle = cap_angle + i*math.tau/3 + rng.uniform(-.16,.16)
        trim(bm, (0,0,cap_height-rng.uniform(.01,.10)*radius),
             (math.cos(angle), math.sin(angle), tilt), 0)
    rotation = Vector(direction).to_track_quat("Z","Y")
    front = rotation.inverted() @ Vector((1,.42,.05))
    corners = sorted(outline, key=lambda p: p.normalized().dot(front), reverse=True)
    for i in range(1+damage):
        corner = corners[(i*2)%sides]
        outward = corner.normalized()
        height = cap_height-radius*(.46 if i==0 else .83+.42*i)
        trim(bm, corner*(.54+.055*i)+Vector((0,0,height)),
             outward+Vector((0,0,.64-.09*i)), 0)

    material = bpy.data.materials.get("Violet | indigo heart and growth zones") or optical_finish()
    obj = from_bmesh(name, bm, [material])
    if fracture:
        inset_fracture(obj, outline, radius, length, rotation, fracture_finish())
    axial = obj.data.attributes.new("crystal axial height", "FLOAT", "POINT")
    axis = obj.data.attributes.new("crystal axis metres", "FLOAT_VECTOR", "POINT")
    radial = obj.data.attributes.new("crystal radial distance", "FLOAT", "POINT")
    for i, vert in enumerate(obj.data.vertices):
        height = vert.co.z/length
        xy = Vector((vert.co.x,vert.co.y,0))/(radius*(1-.18*height))
        axial.data[i].value = height
        axis.data[i].vector = xy
        radial.data[i].value = xy.length
    for face in obj.data.polygons:
        face.use_smooth = False
    lowest = min((rotation @ vert.co).z for vert in obj.data.vertices)
    obj.location = (foot[0], foot[1], max(foot[2], -.040-lowest))
    obj.rotation_euler = rotation.to_euler()


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
        ("Dominant violet", (-.28,.16,.30), (.29,-.08,1), 2.92,.60,6,.9,1,True),
        ("Right counterweight", (.03,.16,.30), (.85,.44,.99), 1.92,.385,5,.4,2,False),
        ("Low splitting tooth", (-.31,.22,.36), (-.86,.28,.71), 1.82,.34,6,.7,1,False),
        ("Forked rear blade", (-.16,.34,.47), (-.12,.76,.89), 1.71,.30,6,1.16,0,False),
        ("Near broken shoulder", (-.04,-.12,.34), (.35,-.85,.73), 1.51,.28,5,.17,2,False),
        ("Above the back shelf", (.36,.32,.59), (.32,.63,.78), 1.10,.23,7,.56,1,False),
        ("Groundward twin", (-.39,.05,.27), (-.49,-.66,.56), .94,.206,5,.1,1,False),
        ("Sliver in the cap", (-.67,.29,.56), (-.63,.20,.83), .72,.14,6,.8,0,False),
        ("Cleaved foot satellite", (.82,-.29,.32), (.61,-.36,.78), .77,.19,7,.58,2,False),
        ("New shoot", (.61,.33,.63), (.68,.33,.81), .59,.113,5,.97,0,False),
        ("Embedded shard", (-.25,-.72,.17), (.17,-.62,.40), .69,.158,6,1.6,2,False),
    ]
    for name, foot, direction, length, radius, sides, roll, damage, fracture in shoots:
        prism(name, foot, direction, length, radius, sides, roll, rng, damage, fracture)
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

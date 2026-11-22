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
        ("Leaning fracture spire", (.04,.02,.16), (.175,-.077,1), 7.32,.85,6,.91,1,True),
        ("Paired blade", (.11,.33,.31), (.41,.37,.92), 4.86,.58,6,.3,2,False),
        ("Split back face", (-.15,.65,.24), (-.21,.49,.92), 4.34,.47,5,1.11,1,False),
        ("Slip twin", (-.27,-.28,.23), (-.57,-.12,.92), 3.93,.40,6,.59,0,False),
        ("Headward shard", (.09,-.57,.19), (.18,-.72,.87), 3.36,.36,5,1.4,2,False),
        ("Spall above upper bank", (-.61,-.11,1.21), (-.91,-.21,.66), 2.18,.278,6,.81,1,False),
        ("Right-side strain", (.37,.11,.51), (.86,-.21,.68), 2.21,.29,7,1.2,2,False),
        ("Pinkish lamella", (.20,.75,.57), (.10,.74,.90), 2.11,.26,5,.37,0,False),
        ("Backbank daughter", (-.42,.85,.72), (-.33,.74,.72), 1.59,.22,6,.8,1,False),
        ("Fault seam spike", (.14,-1.04,.31), (.35,-.42,.81), 1.52,.215,5,.8,2,False),
        ("Buried splinter", (-.15,1.21,.23), (.17,.82,.62), 1.33,.20,7,.31,2,False),
        ("Vein offshoot", (-.24,-.67,.45), (-.23,-.41,.86), .94,.13,5,1.81,1,False),
    ]
    for name, foot, direction, length, radius, sides, roll, damage, fracture in growth:
        prism(name, foot, direction, length, radius, sides, roll, rng, damage, fracture)
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

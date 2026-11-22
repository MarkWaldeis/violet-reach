"""Asymmetrischer Kalkfindling: geneigte Bänke, Scherflächen und versetzte Klüfte."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree

import vrlib
import vrmat

SEED = 27183
BEDDING = Matrix.Rotation(math.radians(4), 4, "Y")


def cut(bm, point, normal):
    result = bmesh.ops.bisect_plane(
        bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
        plane_co=point, plane_no=normal, clear_inner=True, dist=.00001)
    edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))


def prism(poly, bottom, height):
    bm = bmesh.new()
    rings = [[bm.verts.new((x, y, z)) for x, y in poly] for z in (bottom, bottom + height)]
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[1])
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        bm.faces.new((rings[0][i], rings[0][j], rings[1][j], rings[1][i]))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


def finish(bm, name, rng, stone, joint, detail=3, bed=True, slump=False):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    for face in bm.faces:
        if face.normal.z < -.7:
            face.material_index = 1
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(stone)
    obj.data.materials.append(joint)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if name == "Zusammenhaengender_Kalkfindling":
        carve_clefts(obj)
    bevel = obj.modifiers.new("Scharfe Abplatzungen", "BEVEL")
    bevel.width, bevel.segments = .035, 2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    tri = obj.modifiers.new("Bruchfacetten", "TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier=tri.name)
    sub = obj.modifiers.new("Feine Kalksplitter", "SUBSURF")
    sub.subdivision_type, sub.levels = "SIMPLE", detail
    bpy.ops.object.modifier_apply(modifier=sub.name)
    normals = [v.normal.copy() for v in obj.data.vertices]
    offset = Vector((rng.uniform(10, 80), rng.uniform(10, 80), rng.uniform(10, 80)))
    pivot = sum((v.co for v in obj.data.vertices), Vector()) / len(obj.data.vertices)
    slant = Matrix.Rotation(math.radians(5), 4, "X")
    for v, normal in zip(obj.data.vertices, normals):
        p = v.co + offset
        coarse = round(noise.noise(p * 2.8) * 3) / 3
        fine = round(noise.noise(p * 9) * 4) / 4
        depth = .055 * coarse + .008 * fine
        if bed:
            wave = .015*math.sin(v.co.x*2.7 + v.co.y*1.8) + .008*noise.noise(p*3)
            phase = (v.co.z + wave) / .17 + .15*math.sin(v.co.z*5)
            groove = max(0, 1 - abs(phase-round(phase))/.16)
            broken = max(0, min(1, (noise.noise(Vector((v.co.x*2, v.co.y*2, round(phase)*2)))+.3)*2))
            depth -= .026 * groove * broken * (1-abs(normal.z))
        v.co += normal * depth
        if slump:
            v.co = pivot + slant @ (v.co - pivot) + Vector((.08, .12, -.06))
        if bed:
            v.co = BEDDING @ v.co
        v.co.z = max(v.co.z, -.045)
    obj.data.update()
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(25))
    obj.select_set(False)
    return obj


def carve_clefts(obj):
    bpy.ops.mesh.primitive_cube_add(location=(2.35, 1.15, 2.05))
    notch = bpy.context.object
    notch.name = "Eckausbruch_Schneider"
    notch.scale = (.85, .65, .65)
    notch.rotation_euler = (math.radians(12), math.radians(-15), math.radians(35))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    notch.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    boolean = obj.modifiers.new("Grosser_Eckausbruch", "BOOLEAN")
    boolean.operation, boolean.solver, boolean.object = "DIFFERENCE", "EXACT", notch
    bpy.ops.object.modifier_apply(modifier=boolean.name)
    bpy.data.objects.remove(notch, do_unlink=True)
    for index, (axis, pos, bottom, top, reach) in enumerate(
            [("X", -.65, .5, 3.4, .15), ("X", 1.1, 1.6, 4.8, -.6),
             ("Y", -1.7, 2.5, 5.2, .1)]):
        verts, faces = [], []
        levels = 12
        for j in range(levels):
            t = j/(levels-1)
            z = bottom + t*(top-bottom)
            centre = pos + .075*math.sin(j*2.1+index) + .045*math.sin(j*.8)
            width = .035 + .095*t
            for along, across in ((reach,centre-width),(5,centre-width),(5,centre+width),(reach,centre+width)):
                verts.append((along,across,z) if axis == "X" else (across,along,z))
        faces.append((3,2,1,0))
        for j in range(levels-1):
            for k in range(4):
                n = (k+1)%4
                faces.append((j*4+k,j*4+n,(j+1)*4+n,(j+1)*4+k))
        faces.append(tuple((levels-1)*4+k for k in range(4)))
        mesh = bpy.data.meshes.new("Kluftschneider")
        mesh.from_pydata(verts, [], faces)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        cutter = bpy.data.objects.new("Kluftschneider", mesh)
        bpy.context.scene.collection.objects.link(cutter)
        boolean = obj.modifiers.new("Unregelmaessige Sackkluft", "BOOLEAN")
        boolean.operation, boolean.solver, boolean.object = "DIFFERENCE", "EXACT", cutter
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=boolean.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def materials():
    stone = vrmat.get("canyon_layered").copy()
    stone.name = "rock_boulder_a_grobporiger_Kalk"
    # Local variant: reduce anisotropy from 1.6/1.6/18 to 3/3/5, halve bump depth.
    for node in stone.node_tree.nodes:
        if node.type == "VECT_MATH" and node.operation == "MULTIPLY":
            if tuple(round(v, 1) for v in node.inputs[1].default_value) == (1.6, 1.6, 18):
                node.inputs[1].default_value = (3, 3, 5)
        if node.type == "BUMP":
            node.inputs["Distance"].default_value *= .5
    # Local variant: bed tones, rain streaks and sparse palette-based weathering.
    nt = stone.node_tree
    colour = nt.nodes.get("Principled BSDF").inputs["Base Color"]
    original = colour.links[0].from_socket
    palette = vrmat.load_palette()
    chalk = palette["canyon_chalk"]["linear_rgb"]
    lift = nt.nodes.new("ShaderNodeMixRGB")
    lift.inputs[0].default_value = .5
    lift.inputs[2].default_value = tuple(v + (1-v)*.1 for v in chalk) + (1,)
    nt.links.new(original, lift.inputs[1])
    coord = nt.nodes.new("ShaderNodeTexCoord")
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], split.inputs[0])
    height = nt.nodes.new("ShaderNodeMath")
    height.operation = "DIVIDE"
    height.inputs[1].default_value = 5
    nt.links.new(split.outputs["Z"], height.inputs[0])
    tones = nt.nodes.new("ShaderNodeValToRGB")
    tones.color_ramp.interpolation = "CONSTANT"
    entries = [(0,(1.04,1.01,.95,1)),(.17,(.86,.80,.69,1)),
               (.29,(1.1,1.06,.99,1)),(.54,(.88,.83,.74,1)),
               (.76,(1.06,1.02,.95,1))]
    for element, (position,tone) in zip(tones.color_ramp.elements, entries[:2]):
        element.position, element.color = position,tone
    for position,tone in entries[2:]:
        tones.color_ramp.elements.new(position).color = tone
    nt.links.new(height.outputs[0], tones.inputs[0])
    beds = nt.nodes.new("ShaderNodeMixRGB")
    beds.blend_type = "MULTIPLY"
    beds.inputs[0].default_value = 1
    nt.links.new(lift.outputs[0], beds.inputs[1])
    nt.links.new(tones.outputs[0], beds.inputs[2])
    stretch = nt.nodes.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (9,9,.4)
    nt.links.new(coord.outputs["Object"], stretch.inputs[0])
    rain = nt.nodes.new("ShaderNodeTexNoise")
    rain.inputs["Scale"].default_value = 1
    rain.inputs["Detail"].default_value = 2
    nt.links.new(stretch.outputs[0], rain.inputs["Vector"])
    mask = nt.nodes.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = .58
    mask.inputs["From Max"].default_value = .78
    mask.inputs["To Max"].default_value = .22
    nt.links.new(rain.outputs["Fac"], mask.inputs["Value"])
    stains = nt.nodes.new("ShaderNodeMixRGB")
    stains.blend_type = "MULTIPLY"
    stains.inputs[2].default_value = (.49,.46,.40,1)
    nt.links.new(mask.outputs[0], stains.inputs[0])
    nt.links.new(beds.outputs[0], stains.inputs[1])
    patches = nt.nodes.new("ShaderNodeTexNoise")
    patches.inputs["Scale"].default_value = 3.5
    patches.inputs["Detail"].default_value = 3
    nt.links.new(coord.outputs["Object"], patches.inputs["Vector"])
    patch_mask = nt.nodes.new("ShaderNodeMapRange")
    patch_mask.inputs["From Min"].default_value = .7
    patch_mask.inputs["From Max"].default_value = .84
    patch_mask.inputs["To Max"].default_value = .3
    nt.links.new(patches.outputs["Fac"], patch_mask.inputs["Value"])
    weather = nt.nodes.new("ShaderNodeMixRGB")
    weather.inputs[2].default_value = tuple(palette["canyon_strata"]["linear_rgb"]) + (1,)
    nt.links.new(patch_mask.outputs[0], weather.inputs[0])
    nt.links.new(stains.outputs[0], weather.inputs[1])
    nt.links.new(weather.outputs[0], colour)
    joint = stone.copy()
    joint.name = "rock_boulder_a_dunkle_Lagerfugen"
    nt = joint.node_tree
    colour = nt.nodes.get("Principled BSDF").inputs["Base Color"]
    source = colour.links[0].from_socket
    shade = nt.nodes.new("ShaderNodeMixRGB")
    shade.blend_type = "MULTIPLY"
    shade.inputs[0].default_value = 1
    shade.inputs[2].default_value = (.65, .61, .54, 1)
    nt.links.new(source, shade.inputs[1])
    nt.links.new(shade.outputs[0], colour)
    return stone, joint


def build():
    rng = random.Random(SEED)
    noise.seed_set(SEED)
    stone, joint = materials()
    outline = [(-3.65,-1.35),(-2.95,-2.15),(-.8,-2.2),(-.35,-1.95),
               (2.7,-1.95),(3.65,-.7),(3.35,.2),(3.45,1.25),
               (1.6,2.12),(-.7,2),(-1.3,2.3),(-3.55,1.1)]
    # z, positive-X retreat, Y contraction, recessed joint depth.
    profiles = [(-.04,0,1,0),(.7,.05,1,0),(.79,.08,.99,.12),
                (.88,.55,.86,0),(1.28,.6,.86,0),(1.36,.65,.86,.1),
                (1.45,1.15,.72,0),(2.38,1.2,.72,0),(2.48,1.35,.72,.18),
                (2.62,1.3,.72,.13),(2.7,1.65,.59,0),(3.6,1.7,.59,0),
                (3.69,1.8,.59,.12),(3.8,2.0,.55,0),(4.2,2.45,.53,0),
                (4.55,2.8,.5,0)]
    perimeter = []
    corner_rng = random.Random(SEED + 51)
    corners = [[(corner_rng.uniform(-.42,.42), corner_rng.uniform(-.3,.3))
                for _ in outline] for _ in range(5)]

    def corner_shift(edge, t, z):
        bed = sum(z > boundary for boundary in (.84,1.4,2.66,3.75))
        a, b = corners[bed][edge], corners[bed][(edge+1)%len(outline)]
        return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)

    for edge, (a, b) in enumerate(zip(outline, outline[1:]+outline[:1])):
        steps = max(1, math.ceil(math.dist(a,b)/.28))
        perimeter.extend(((a[0]+(b[0]-a[0])*j/steps,
                           a[1]+(b[1]-a[1])*j/steps, edge, j/steps) for j in range(steps)))
    bm = bmesh.new()
    rings = []
    for lower, upper in zip(profiles, profiles[1:]):
        count = max(1, math.ceil((upper[0]-lower[0])/.12))
        for j in range(count):
            t = j/count
            z, retreat, sy, recess = [a+(b-a)*t for a,b in zip(lower,upper)]
            ring = []
            for x,y,edge,along in perimeter:
                dx, dy = corner_shift(edge, along, z)
                x, y = x+dx, y+dy
                fraction = max(0,min(1,(x+3.65)/7.3))
                xx = x - retreat*fraction**1.2
                yy = y*sy
                radial = Vector((xx+.7, yy, 0)).normalized()
                xx -= radial.x*recess
                yy -= radial.y*recess
                zz = z - max(0,xx+.7)*max(0,z-3.75)*.32
                ring.append(bm.verts.new((xx,yy,zz)))
            rings.append(ring)
    last = profiles[-1]
    top = []
    for x,y,edge,along in perimeter:
        dx,dy = corner_shift(edge,along,last[0])
        x,y = x+dx,y+dy
        top.append(bm.verts.new((x-last[1]*max(0,min(1,(x+3.65)/7.3))**1.2,
                                y*last[2],last[0]-max(0,x+.7)*.26)))
    rings.append(top)
    for low, high in zip(rings, rings[1:]):
        for k in range(len(perimeter)):
            n = (k+1)%len(perimeter)
            face = bm.faces.new((low[k],low[n],high[n],high[k]))
            if any(abs(low[k].co.z-z)<.065 for z in (.79,1.36,2.53,3.69)):
                face.material_index = 1
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    body = finish(bm, "Zusammenhaengender_Kalkfindling", rng, stone, joint, detail=2)
    bpy.context.view_layer.update()
    surface = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    for i in range(25):
        angle = rng.uniform(0, math.tau)
        x, y = math.cos(angle)*rng.uniform(2.8,3.6), math.sin(angle)*rng.uniform(2,2.35)
        radius = rng.uniform(.06,.39)
        base = .005
        if i < 3:
            x, y, radius, base = 2.25+i*.13, -.64+i*.05, .11+i*.015, 2.1+i*.09
        elif i < 9:
            x, y, radius, base = rng.uniform(-.5,1.1), rng.uniform(1.56,1.7), rng.uniform(.06,.16), 1.35
        poly = [(x+radius*math.cos(a), y+radius*.7*math.sin(a)) for a in (0,.8,2.7,3.5,5)]
        height = radius*rng.uniform(.65,1.5)
        bm = prism(poly, base, height)
        cut(bm, (x,y,base+height*.7), (.4,-.35,-1))
        chip = finish(bm, f"Kluftstein_{i:02d}" if i<3 else f"Loser_Kalkbruch_{i:02d}",
                      rng, stone, joint, detail=2, bed=i<3)
        if 3 <= i < 9:
            hit, _, _, _ = surface.ray_cast(Vector((x,y,7)), Vector((0,0,-1)))
            support = hit.z if hit is not None else 0
            chip.location.z += support - min(v.co.z for v in chip.data.vertices) + .002
    bpy.context.view_layer.update()
    lo, hi = vrlib.world_bounds(vrlib.source_objects())
    shift = Vector(((lo.x+hi.x)/2, (lo.y+hi.y)/2, 0))
    for obj in vrlib.source_objects():
        obj.location -= shift
    vrlib.use_cycles_cpu(bpy.context.scene, 32)

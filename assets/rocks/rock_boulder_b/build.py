"""Geschnittener Sandsteinhull mit Kreuzschichtung und angewachsenen Moosschalen."""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise
from mathutils.bvhtree import BVHTree

import vrlib
import vrmat

SEED = 81329


def link_mesh(name, verts, faces, material):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    vrlib.link_to_source(obj)
    return obj


def materials():
    palette = vrmat.load_palette()
    result = []
    for key, name in (("sandstone", "Warmer_Kreuzsandstein"),
                      ("mossy_rock", "Dunkle_Olivmoosspitzen")):
        mat = vrmat.get(key).copy()
        mat.name = "rock_boulder_b_" + name
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        coord = nt.nodes.new("ShaderNodeTexCoord")
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 55 if key == "sandstone" else 95
        tex.inputs["Detail"].default_value = 3
        nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        # Local copies: palette ochre/sandstone bands, and pure olive fibre tips without a pale edge mix.
        colors = (("accent_ochre", .38), ("sandstone", .46)) if key == "sandstone" else (("moss", .55), ("moss", 1.15))
        for el, (color, gain) in zip(ramp.color_ramp.elements, colors):
            el.color = tuple(v * gain for v in palette[color]["linear_rgb"]) + (1,)
        if key == "sandstone":
            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.inputs["Rotation"].default_value = (.08, -.17, 0)
            nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
            wave = nt.nodes.new("ShaderNodeTexWave")
            wave.bands_direction = "Z"
            wave.inputs["Scale"].default_value = .38
            wave.inputs["Distortion"].default_value = .4
            wave.inputs["Detail Scale"].default_value = 1.5
            nt.links.new(mapping.outputs[0], wave.inputs["Vector"])
            nt.links.new(wave.outputs["Fac"], ramp.inputs[0])
        else:
            nt.links.new(tex.outputs["Fac"], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = .003 if key == "sandstone" else .004
        bump.inputs["Strength"].default_value = .35
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs[0], bsdf.inputs["Normal"])
        bsdf.inputs["Roughness"].default_value = .94
        result.append(mat)
    return result


def cut_plane(bm, point, normal):
    bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                          plane_co=point, plane_no=normal, clear_outer=True, dist=.00001)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))


def hull(name, size, rng, material, count=56):
    bm = bmesh.new()
    for _ in range(count):
        z = rng.uniform(-1, 1)
        a = rng.uniform(0, math.tau)
        radius = rng.uniform(.84, 1.12)
        bm.verts.new((math.sqrt(1-z*z)*math.cos(a)*radius,
                      math.sqrt(1-z*z)*math.sin(a)*radius, z*radius))
    bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    for axis, width in enumerate(size):
        lo = min(v.co[axis] for v in bm.verts)
        hi = max(v.co[axis] for v in bm.verts)
        for v in bm.verts:
            v.co[axis] = (v.co[axis]-lo)/(hi-lo)*width-width/2
    cut_plane(bm, (0, -size[1]*.37, 0), (.06, -1, .05))
    for _ in range(3):
        a = rng.uniform(0, math.tau)
        normal = Vector((math.cos(a), math.sin(a), rng.uniform(-.2, .4)))
        point = Vector((normal.x*size[0]*.44, normal.y*size[1]*.44, 0))
        cut_plane(bm, point, normal)
    cut_plane(bm, (0, 0, -size[2]*.46), (0, 0, -1))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    vrlib.link_to_source(obj)
    return obj


def subtract(obj, cutter):
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new("Rauhe_Waben", "BOOLEAN")
    mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000002)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=.0000001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def weather(obj, voxel, amplitude):
    bpy.context.view_layer.objects.active = obj
    remesh = obj.modifiers.new("Gleichmaessige_Dichte", "REMESH")
    remesh.mode, remesh.voxel_size = "VOXEL", voxel
    bpy.ops.object.modifier_apply(modifier=remesh.name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    upper = [v for v in bm.verts if v.co.z > .35*amplitude and v.normal.z > .35]
    bmesh.ops.smooth_vert(bm, verts=upper, factor=.55, use_axis_x=True,
                          use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for v in bm.verts:
        p, n = v.co.copy(), v.normal.copy()
        broad = .07*noise.noise(p*(.85/amplitude))
        cell = noise.noise(p*(4.5/amplitude))*3
        fraction = cell-math.floor(cell)
        transition = max(0, min(1, (fraction-.3)/.4))
        transition = transition*transition*(3-2*transition)
        chip = .035*(math.floor(cell)+transition)/3
        shear = max(0, -n.y)
        v.co += n*(broad*amplitude*(1-.55*shear) + chip*amplitude*(.6+.4*shear))
    bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=.22, use_axis_x=True,
                          use_axis_y=True, use_axis_z=True)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    remesh = obj.modifiers.new("Geschlossene_Bruchkanten", "REMESH")
    remesh.mode, remesh.voxel_size = "VOXEL", voxel*.65
    bpy.ops.object.modifier_apply(modifier=remesh.name)
    for face in obj.data.polygons:
        face.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(85))
    obj.data.update()
    bpy.context.view_layer.update()


def tafoni(body, rng, stone):
    tree = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    for i in range(7):
        y = -.1 + (i % 4)*.21 + rng.uniform(-.04, .04)
        z = .02 + (i // 4)*.2 + rng.uniform(-.04, .04)
        hit, _, _, _ = tree.ray_cast(Vector((4, y, z)), Vector((-1, 0, 0)))
        if hit is None:
            continue
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1)
        cutter = bpy.context.object
        for v in cutter.data.vertices:
            p = v.co.copy()
            v.co *= 1 + .32*noise.noise(p*4 + Vector((i*3, 1, 4)))
            v.co.x *= .18 + .015*(i % 3)
            v.co.y *= .19 + .035*(i % 3)
            v.co.z *= .12 + .025*(i % 2)
            v.co.y += .04*math.sin(p.z*7+i)
        cutter.location = (hit.x+.06, y, z)
        subtract(body, cutter)


def fracture_planes(body, rng):
    planes = []
    bm = bmesh.new()
    bm.from_mesh(body.data)
    for i in range(8):
        a = math.tau*i/8 + rng.uniform(-.09, .09)
        normal = Vector((math.cos(a), math.sin(a), rng.uniform(-.28, .32))).normalized()
        support = math.sqrt((1.6*normal.x)**2 + (1.3*normal.y)**2)
        distance = support*rng.uniform(.76, .83)
        point = normal*distance
        cut_plane(bm, point, normal)
        planes.append((normal, distance))
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return planes


def tapered_wedge(name, centre, along, across, outward, start, end, depth, width,
                  phase, stone, bedding=False, lean=0):
    verts, faces = [], []
    sections = 18
    for j in range(sections+1):
        r = j/sections
        t = start+(end-start)*r
        p = centre+along*t
        wander = .018*math.sin(t*13+phase)+.011*noise.noise(p*27+Vector((phase,0,0)))
        p += across*(wander+lean*t)
        taper = math.sin(math.pi*r)**.65
        if j in (0, sections):
            verts.append(p+outward*.08)
            continue
        variation = .8+.28*math.sin(t*13+phase)+.12*noise.noise(p*37)
        d = .08-(.08+depth*variation)*taper
        w = width*taper*variation
        upper, lower = (w*.3,-w) if bedding else (w,-w*.8)
        root = -.006*taper if bedding else .004*math.sin(t*17+phase)
        verts.extend((p+outward*.08+across*upper,
                      p+outward*d+across*root,
                      p+outward*.08+across*lower))
    last = len(verts)-1
    for k in range(3):
        q = (k+1)%3
        faces.append((0,1+q,1+k))
        a = 1+(sections-2)*3
        faces.append((last,a+k,a+q))
    for j in range(sections-2):
        a = 1+j*3
        for k in range(3):
            q = (k+1)%3
            faces.extend(((a+k,a+q,a+3+q),(a+k,a+3+q,a+3+k)))
    return link_mesh(name, verts, faces, stone)


def bedding_ledges(body, planes, stone):
    bed_normal = Vector((-.17, -.07, 1)).normalized()
    for bed, level in enumerate((-.57, -.18, .25, .6)):
        for index, (normal, distance) in enumerate(planes):
            tangent = normal.cross(bed_normal).normalized()
            centre = normal*distance
            centre += bed_normal*((level-bed_normal.dot(centre))/(1-bed_normal.dot(normal)**2))
            centre -= normal*(normal.dot(centre)-distance)
            outward = (normal-bed_normal*normal.dot(bed_normal)).normalized()
            edge_points = [tangent.dot(v.co-centre) for v in body.data.vertices
                           if abs(normal.dot(v.co)-distance)<.0001]
            if not edge_points:
                continue
            start, end = min(edge_points)+.015, max(edge_points)-.015
            if index % 3 == bed % 3:
                end = start+(end-start)*.78
            if end-start < .14:
                continue
            recess = .035+.025*(.5+.5*math.sin(index*2.3+bed*1.7))
            cutter = tapered_wedge(f"Schichtlippe_{bed}_{index}",centre,tangent,bed_normal,
                                   outward,start,end,recess,.085,index+bed*9,stone,bedding=True)
            subtract(body, cutter)


def split_cracks(body, planes, stone):
    for i, (plane, offset, lean, height) in enumerate(((0,.42,.28,1.15),
                                                     (1,-.2,-.22,.9),
                                                     (5,.15,.25,1.05))):
        normal, distance = planes[plane]
        tangent = normal.cross(Vector((0,0,1))).normalized()
        vertical = tangent.cross(normal).normalized()
        centre = normal*distance+tangent*offset
        cutter = tapered_wedge(f"Kluft_{i}",centre,vertical,tangent,normal,-height/2,
                               height/2,.13,.055,i*7+2,stone,lean=lean)
        subtract(body, cutter)


def facet_chips(body, planes, stone):
    rng = random.Random(SEED+901)
    bpy.context.view_layer.update()
    tree = BVHTree.FromObject(body,bpy.context.evaluated_depsgraph_get())
    for i, (a, da) in enumerate(planes):
        b, db = planes[(i+1)%len(planes)]
        z = rng.uniform(-.52,.47)
        determinant = a.x*b.y-a.y*b.x
        if abs(determinant)<.05:
            continue
        x = ((da-a.z*z)*b.y-a.y*(db-b.z*z))/determinant
        y = (a.x*(db-b.z*z)-(da-a.z*z)*b.x)/determinant
        p = Vector((x,y,z))
        hit, _, _, distance = tree.find_nearest(p)
        if hit is None or distance>.035:
            continue
        size = rng.uniform(.045,.09)
        cutter = hull(f"Kantenabplatzer_{i}",(size,size*.85,size*.7),rng,stone,18)
        cutter.location = p+(a+b).normalized()*size*.12
        cutter.rotation_euler = (rng.random(),rng.random(),rng.random())
        subtract(body,cutter)


def moss_shell(body, material):
    mesh = body.data
    normals = [v.normal.copy() for v in mesh.vertices]
    adjacent = [set() for v in mesh.vertices]
    for edge in mesh.edges:
        a, b = edge.vertices
        adjacent[a].add(b)
        adjacent[b].add(a)
    for _ in range(4):
        normals = [(normals[i]+sum((normals[j] for j in neighbors), Vector())).normalized()
                   for i, neighbors in enumerate(adjacent)]
    candidates = [f for f in mesh.polygons if f.normal.z > .6 and f.center.z > .25
                  and sum(normals[i].z for i in f.vertices)/len(f.vertices) > .65]
    def field(p):
        tuft = .4 if .025 < abs(p.x+.3) < .065 and p.y > .5 else 0
        return noise.noise(p*2.7 + Vector((3, 8, 1))) + .1*noise.noise(p*9) + tuft
    ranked = sorted(candidates, key=lambda f: field(f.center), reverse=True)
    target = sum(f.area for f in candidates)*.30
    chosen, area = [], 0
    for face in ranked:
        chosen.append(face)
        area += face.area
        if area >= target:
            break
    incident = {}
    for fi, face in enumerate(chosen):
        for i in face.vertices:
            incident.setdefault(i, set()).add(fi)
    used, mapping = [], {}
    for i, pending in incident.items():
        while pending:
            component = {pending.pop()}
            frontier = component.copy()
            while frontier:
                linked = {j for a in frontier for j in pending
                          if len(set(chosen[a].vertices) & set(chosen[j].vertices)) > 1}
                pending -= linked
                component |= linked
                frontier = linked
            index = len(used)
            used.append(i)
            for fi in component:
                mapping[fi, i] = index
    top_faces = [tuple(mapping[fi, i] for i in f.vertices) for fi, f in enumerate(chosen)]
    edges = {}
    neighbors = {i: set() for i in range(len(used))}
    for face in top_faces:
        ids = list(face)
        for a, b in zip(ids, ids[1:]+ids[:1]):
            edge = tuple(sorted((a, b)))
            edges[edge] = edges.get(edge, 0)+1
            neighbors[a].add(b)
            neighbors[b].add(a)
    boundary = {i for edge, count in edges.items() if count == 1 for i in edge}
    distance = {i: 0 for i in boundary}
    frontier = boundary
    for step in range(1, 5):
        frontier = {j for i in frontier for j in neighbors[i] if j not in distance}
        distance.update({i: step for i in frontier})
    verts = []
    for j, i in enumerate(used):
        v = mesh.vertices[i]
        p = v.co.copy()
        taper = min(1, distance.get(j, 5)/3)
        clump = .015*noise.noise(p*30)+.003*noise.noise(p*155)
        verts.append(p+normals[i]*(.0008+taper*(.043+clump)))
    verts.extend(mesh.vertices[i].co-normals[i]*.006 for i in used)
    n = len(used)
    faces = top_faces + [tuple(n+i for i in reversed(f)) for f in top_faces]
    for (a, b), count in edges.items():
        if count == 1:
            faces.append((a, b, b+n, a+n))
    obj = link_mesh("Angewachsene_Moosschale", verts, faces, material)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    print("MOSS_SURFACE_COVERAGE", round(area/sum(f.area for f in candidates)*100, 1))


def build():
    rng = random.Random(SEED)
    noise.seed_set(SEED)
    stone, moss = materials()
    body = hull("Sandstein_Hauptmasse", (3.2, 2.6, 2.0), rng, stone)
    bpy.context.view_layer.update()
    cleft = hull("Spaltriss_Schneider", (.085, 1.3, 1.1), rng, stone, 30)
    cleft.location = (-.3, .85, .65)
    subtract(body, cleft)
    weather(body, .02, 1)
    planes = fracture_planes(body, rng)
    bpy.context.view_layer.update()
    tafoni(body, rng, stone)
    bedding_ledges(body, planes, stone)
    split_cracks(body, planes, stone)
    facet_chips(body, planes, stone)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.00001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(body.data)
    bm.free()
    for face in body.data.polygons:
        face.use_smooth = face.area < .018
    body.data.set_sharp_from_angle(angle=math.radians(18))
    bpy.context.view_layer.update()
    moss_shell(body, moss)
    body.location.z = .96
    bpy.data.objects["Angewachsene_Moosschale"].location.z = .96
    block = hull("Abgespaltener_Bruchblock", (.78, .66, .8), rng, stone)
    block.rotation_euler = (.18, -.24, -.18)
    block.location = (.65, -1.0, .4)
    bpy.context.view_layer.objects.active = block
    block.select_set(True)
    body.select_set(False)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    block.select_set(False)
    for i in range(11):
        size = (.3,.25,.18,.12,.28,.08,.22,.15,.3,.1,.2)[i]
        obj = hull(f"Bruchsplitter_{i:02d}", (size, size*rng.uniform(.6,.95), size*rng.uniform(.45,.8)), rng, stone, 18)
        angle = math.tau*i/11+rng.uniform(-.2,.2)
        obj.location = (math.cos(angle)*rng.uniform(1.25,1.5), math.sin(angle)*rng.uniform(1.08,1.3), size*.25)
    bpy.context.view_layer.update()
    lo, hi = vrlib.world_bounds(vrlib.source_objects())
    shift = Vector(((lo.x+hi.x)/2, (lo.y+hi.y)/2, lo.z+.025))
    for obj in vrlib.source_objects():
        obj.location -= shift
    vrlib.use_cycles_cpu(bpy.context.scene, 32)

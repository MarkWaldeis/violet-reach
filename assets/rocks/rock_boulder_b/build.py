"""Heller gebrochener Referenzkalk mit Klüften und angewachsenen Olivpolstern."""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Quaternion, Vector, noise
from mathutils.bvhtree import BVHTree

import vrlib
import vrmat

ASSET = "rock_boulder_b"
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
    stone=stone_material("rock_boulder_b_Paler_Referenzkalk")
    nt=stone.node_tree
    bsdf=nt.nodes["Principled BSDF"]
    original=bsdf.inputs["Base Color"].links[0].from_socket
    ao=nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value=.16
    dirt=nt.nodes.new("ShaderNodeMixRGB")
    dirt.blend_type="MULTIPLY"
    dirt.inputs[0].default_value=.32
    nt.links.new(original,dirt.inputs[1])
    nt.links.new(ao.outputs["Color"],dirt.inputs[2])
    grain=nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value=72
    speckle=nt.nodes.new("ShaderNodeMath")
    speckle.operation="GREATER_THAN"
    speckle.inputs[1].default_value=.72
    nt.links.new(grain.outputs["Fac"],speckle.inputs[0])
    lichen=nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(speckle.outputs[0],lichen.inputs[0])
    nt.links.new(dirt.outputs[0],lichen.inputs[1])
    palette=vrmat.load_palette()
    lichen.inputs[2].default_value=tuple(.72*a+.28*b for a,b in zip(palette["canyon_chalk"]["linear_rgb"],palette["moss"]["linear_rgb"]))+(1,)
    nt.links.new(lichen.outputs[0],bsdf.inputs["Base Color"])
    moss=stone.copy()
    moss.name="rock_boulder_b_Olivpolster"
    nt=moss.node_tree
    bsdf=nt.nodes["Principled BSDF"]
    original=bsdf.inputs["Base Color"].links[0].from_socket
    edge=nt.nodes.new("ShaderNodeAttribute")
    edge.attribute_name="moss_edge"
    factor=nt.nodes.new("ShaderNodeMath")
    factor.operation="SUBTRACT"
    factor.inputs[0].default_value=1
    nt.links.new(edge.outputs["Fac"],factor.inputs[1])
    coord=nt.nodes.new("ShaderNodeTexCoord")
    tex=nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value=32
    nt.links.new(coord.outputs["Object"],tex.inputs["Vector"])
    ramp=nt.nodes.new("ShaderNodeValToRGB")
    palette=vrmat.load_palette()
    for element,weight in zip(ramp.color_ramp.elements,(.18,.38)):
        element.color=tuple((a*(1-weight)+b*weight)*.95 for a,b in
                            zip(palette["grass_green"]["linear_rgb"],palette["path_sand"]["linear_rgb"]))+(1,)
    nt.links.new(tex.outputs["Fac"],ramp.inputs[0])
    mix=nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(factor.outputs[0],mix.inputs[0])
    nt.links.new(original,mix.inputs[1])
    nt.links.new(ramp.outputs[0],mix.inputs[2])
    nt.links.new(mix.outputs[0],bsdf.inputs["Base Color"])
    return stone,moss

def cut_plane(bm, point, normal):
    bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                          plane_co=point, plane_no=normal, clear_outer=True, dist=.00001)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))










def moss_shell(body, material, name="Angewachsene_Moosschale", coverage=.24, thickness=.022, min_height=.85, normal_z=.60):
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
    candidates = [f for f in mesh.polygons if f.center.z > min_height
                  and sum(normals[i].z for i in f.vertices)/len(f.vertices) > normal_z]
    if not candidates:
        raise RuntimeError("No upward north-side faces for moss")
    tree=world_tree(body)
    def field(p):
        heights=[]
        for dx,dy in ((.12,0),(-.12,0),(0,.12),(0,-.12)):
            hit=tree.ray_cast(p+Vector((dx,dy,.5)),Vector((0,0,-1)))[0]
            if hit is not None:
                heights.append(hit.z)
        hollow=max(0,sum(heights)/len(heights)-p.z) if heights else 0
        return (.65*n3(p.x*5,p.y*8,p.z*3)+.22*n3(p.x*17,p.y*13,p.z*10)
                +.55*smooth((p.y-.05)/.7)+min(.45,hollow*10))
    ranked = sorted(candidates, key=lambda f: field(f.center), reverse=True)
    target = sum(f.area for f in candidates)*coverage
    chosen, area = [], 0
    for face in ranked:
        chosen.append(face)
        area += face.area
        if area >= target:
            break
    edge_faces={}
    for index,face in enumerate(chosen):
        ids=list(face.vertices)
        for a,b in zip(ids,ids[1:]+ids[:1]):
            edge_faces.setdefault(tuple(sorted((a,b))),[]).append(index)
    adjacent_faces=[set() for face in chosen]
    for linked in edge_faces.values():
        for index in linked:
            adjacent_faces[index].update(linked)
    pending=set(range(len(chosen)))
    kept=[]
    patch_count=0
    while pending:
        component={pending.pop()}
        frontier=set(component)
        while frontier:
            frontier={j for i in frontier for j in adjacent_faces[i]}&pending
            pending-=frontier
            component|=frontier
        if sum(chosen[i].area for i in component)>.012:
            kept.extend(chosen[i] for i in sorted(component))
            patch_count+=1
    chosen=kept
    if not chosen:
        raise RuntimeError("No broad moss patches")
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
    for step in range(1, 9):
        frontier = {j for i in frontier for j in neighbors[i] if j not in distance}
        distance.update({i: step for i in frontier})
    verts = []
    for j, i in enumerate(used):
        v = mesh.vertices[i]
        p = v.co.copy()
        taper = smooth(min(1, distance.get(j, 9)/6))
        clump = -.009+.009*smooth(noise.noise(p*16)+.5)+.001*noise.noise(p*90)
        verts.append(p+normals[i]*(.0004+taper*(thickness+clump)))
    verts.extend(mesh.vertices[i].co-normals[i]*.004 for i in used)
    n = len(used)
    faces = top_faces + [tuple(n+i for i in reversed(f)) for f in top_faces]
    for (a, b), count in edges.items():
        if count == 1:
            faces.append((a, b, b+n, a+n))
    obj = link_mesh(name, verts, faces, material)
    transfer_stone_attributes(body,obj)
    edge_attribute=obj.data.attributes.new("moss_edge","FLOAT","POINT")
    for j in range(len(verts)):
        edge_attribute.data[j].value=1-smooth(min(1,distance.get(j%n,9)/6))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    print("MOSS_SURFACE_COVERAGE", round(area/sum(f.area for f in candidates)*100, 1))
    obj["moss_patch_count"]=patch_count
    obj["moss_lee_only"]=True
    obj["moss_growth"]="surface hollows and lee-edge noise field"
    return obj

def smooth(v):
    t = min(1, max(0, v))
    return t*t*(3 - 2*t)


def n3(x, y, z):
    return noise.noise(Vector((x, y, z)), noise_basis="PERLIN_ORIGINAL")


def blend(a, b, t):
    return tuple(x + (y-x)*t for x, y in zip(a, b))


def scale(a, factor):
    return tuple(x*factor for x in a)


class Mesh:
    def __init__(self):
        self.verts, self.faces, self.colors, self.factors = [], [], [], []

    def object(self, name, materials, color_name=None, factor_name=None, *, source=True):
        data = bpy.data.meshes.new(name)
        data.from_pydata(self.verts, [], self.faces)
        data.update()
        for mat in materials:
            data.materials.append(mat)
        data.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        if color_name:
            layer = data.color_attributes.new(name=color_name, type="FLOAT_COLOR", domain="POINT")
            layer.data.foreach_set("color", [channel for rgb in self.colors for channel in (*rgb, 1)])
        if factor_name:
            layer = data.attributes.new(name=factor_name, type="FLOAT", domain="POINT")
            layer.data.foreach_set("value", self.factors)
        obj = bpy.data.objects.new(name, data)
        if source:
            return vrlib.link_to_source(obj)
        bpy.context.scene.collection.objects.link(obj)
        obj["vr_review_context"] = True
        obj.hide_render = True
        return obj


def socket_material(base, name, colors, color_weight, factor=None, roughness=None):
    # Library grain still drives the finish; point colours carry the large wet/dry transition.
    m = vrmat.get(base).copy()
    m.name = name
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bsdf = nodes["Principled BSDF"]
    tint = nodes.new("ShaderNodeAttribute")
    tint.attribute_name = colors
    target = bsdf.inputs["Base Color"]
    mineral = nodes.new("ShaderNodeMixRGB")
    mineral.inputs["Fac"].default_value = color_weight
    links.new(target.links[0].from_socket, mineral.inputs[1])
    links.new(tint.outputs["Color"], mineral.inputs[2])
    links.new(mineral.outputs["Color"], target)
    if factor:
        wet = nodes.new("ShaderNodeAttribute")
        wet.attribute_name = factor
        ranges = nodes.new("ShaderNodeMapRange")
        ranges.inputs["To Min"].default_value, ranges.inputs["To Max"].default_value = roughness
        links.new(wet.outputs["Fac"], ranges.inputs["Value"])
        rough = bsdf.inputs["Roughness"]
        variation = nodes.new("ShaderNodeMath")
        variation.operation = "MULTIPLY_ADD"
        links.new(rough.links[0].from_socket, variation.inputs[0])
        variation.inputs[1].default_value = .16
        links.new(ranges.outputs["Result"], variation.inputs[2])
        links.new(variation.outputs[0], rough)
    return m


def ico(level):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=level, radius=1)
    bm.verts.index_update()
    verts = [tuple(v.co) for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return verts, faces


def eased_min(a, b, radius):
    radius=max(.000001,radius*_EDGE_FACTOR*(.30 if radius<.09 else 1))
    gap = max(0, radius - abs(a-b))
    return min(a, b) - gap*gap/(4*radius)


def cobble(m, p, template, x, d, r, flat, rng, form=None, fracture_count=None):
    coords, faces = template
    offset = len(m.verts)
    a = rng.uniform(0, math.tau)
    ca, sa = math.cos(a), math.sin(a)
    seed = rng.uniform(25, 825)
    form = rng.choice(("split", "slab", "worn")) if form is None else form
    elongation = rng.uniform(.50, .85) if form != "worn" else rng.uniform(.76, 1.02)
    weather = rng.random()
    ground = bank(x, d)
    z0 = ground + r*flat*rng.uniform(.06, .36)
    y = waterline(x)+d
    cuts = []
    strike = rng.uniform(0, math.tau)
    count = rng.randint(4, 6) if fracture_count is None else fracture_count
    for j in range(count):
        theta = strike + j*math.tau/count + rng.uniform(-.26,.26)
        rise = rng.uniform(-.27, .29)
        axy = math.sqrt(1-rise*rise)
        setback = rng.uniform(.55, .73) if form != "worn" else rng.uniform(.91, .99)
        cuts.append((math.cos(theta)*axy, math.sin(theta)*axy, rise, setback))
    if form == "slab":
        flat *= .75
        cuts.extend(((.14, -.12, .98, rng.uniform(.36,.49)), (-.52,.36,.77,.56),
                     (.63, .69, .33, rng.uniform(.51,.68))))
    elif form == "split":
        cuts.extend(((.32, .34, .88, rng.uniform(.55,.68)), (-.54,-.37,.75,.61),
                     (-.05, .66, .75, rng.uniform(.52,.72))))
    lean = rng.uniform(-.20, .20)
    kind = rng.random()
    if kind < .29:
        body = blend(scale(p["shore_wet"], .57), p["canyon_strata"], .18)
    elif kind < .53:
        body = blend(p["soil"], p["sandstone"], rng.uniform(.48, .86))
    elif kind < .75:
        body = blend(p["shore_wet"], p["canyon_strata"], rng.uniform(.61, .83))
    else:
        body = blend(p["canyon_strata"], p["canyon_chalk"], rng.uniform(.15, .56))
    if form == "slab":
        body = blend(body, p["canyon_strata"], .28)
    halo = .033 + .096*smooth((.74-d)/.96)
    floor = max(BOTTOM+.0005, ground-.25*r*flat)
    lichen_prop = rng.uniform(.14, .40) if d > .48 else .045
    for u, v, w in coords:
        seam = noise.voronoi(Vector((u*(1.6+weather)+seed, v*2.7, w*(2.1+.8*weather))))[0]
        chip = 1 - smooth((seam[1]-seam[0])/.29)
        coarse = n3(2.1*u, 2.1*v+seed, 2.1*w)
        medium = n3(5.75*u, 5.75*v, 5.75*w+seed)
        if ASSET=="rock_boulder_b":
            phase=(medium+1)*4
            medium=(math.floor(phase)+smooth((phase%1-.25)/.5))/4-1
        fine = n3(15*u+seed, 15*v, 15*w)
        radial = 1 + (.13 if form == "worn" else .022)*coarse
        for nx, ny, nz, upper in cuts:
            dot = nx*u+ny*v+nz*w
            if dot > .28:
                radial = eased_min(radial, upper/dot, .008 if form != "worn" else .095)
        lamina = math.sin((19+7*weather)*(w+.22*u-.14*v) + .76*coarse)
        breakout = smooth(.44 + 1.25*medium - .43*weather)
        radial *= (1 + (.003+.003*weather)*medium + .0015*fine
                   - .014*chip*breakout + (.004 if form == "slab" else .002)*lamina)
        u1, v1 = (u*radial + lean*w*.48)*r, v*radial*r*elongation
        px, py = x+ca*u1-sa*v1, y+sa*u1+ca*v1
        z = z0 + r*flat*(w*radial + lean*u*.41)
        # Turn the bottom into a small bedding contact, not another ellipsoid pole.
        z = floor + .013*r*flat + max(0, z-floor)
        m.verts.append((px, py, z))
        water_z = halo + .049*n3(5*u+seed, 4*v, 2*w)*min(1, r*2)
        wet = max(.0, (1-smooth((z-water_z)/max(.022, r*.14))) * smooth((1.18-d)/.83))
        m.factors.append(wet)
        # Pale mineral on fresh edges, warmer lichen only where elevation and aspect allow.
        marl = .021*n3(u*3.7, v*3.7, w*12+seed) + (1-chip)*.009
        marl += (.057 if form == "slab" else .028)*smooth((lamina-.81)/.19)*smooth(.60+medium)
        mid = scale(body, .83 + .24*weather + .23*coarse + .17*medium)
        stained = blend(mid, p["grass_dry"], smooth((w+.3)/1.2)*smooth(.52+1.6*medium)*lichen_prop)
        dry = tuple(max(.009, rgb+marl) for rgb in stained)
        wet_rgb = scale(blend(dry, p["shore_wet"], .33), .37+.14*coarse)
        m.colors.append(blend(dry, wet_rgb, wet))
    m.faces.extend(tuple(offset+i for i in face) for face in faces)
    return cuts


BOTTOM = -.058
_EDGE_FACTOR = 1.0


def bank(x, d):
    return 0


def waterline(x):
    return 0


def stone_material(name, wet=False):
    mat=socket_material("river_stones",name,"stone_tones",.96,
                        "stone_saturation",(.50,.15) if wet else (.69,.23))
    nt=mat.node_tree
    bsdf=nt.nodes["Principled BSDF"]
    original=bsdf.inputs["Base Color"].links[0].from_socket
    variation=nt.nodes.new("ShaderNodeMixRGB")
    variation.blend_type="MULTIPLY"
    variation.inputs[0].default_value=1
    rng=random.Random(name)
    gain=rng.uniform(.92,1.07)
    variation.inputs[2].default_value=(gain*rng.uniform(.98,1.03),gain,gain*rng.uniform(.94,1.02),1)
    nt.links.new(original,variation.inputs[1])
    nt.links.new(variation.outputs[0],bsdf.inputs["Base Color"])
    return mat

def fractured_rock(name, size, seed, material, cuts=7, split=False,
                    weathering=1.0, strata=.48, tafoni=False, fissures=False):
    if len(size) != 3 or min(size) <= 0 or not 4 <= cuts <= 8 or split:
        raise ValueError("Positive dimensions, 4-8 fractures and separate thick chunks required")
    global _EDGE_FACTOR
    level = 8 if max(size) > 2 else 7 if max(size) > 1.5 else 6 if max(size) > .4 else 4
    form = "worn" if ASSET == "shore_stones_a" else ("slab" if size[2] < min(size[:2])*.45 else "split")
    palette = {k: v["linear_rgb"] for k, v in vrmat.load_palette().items()}
    mesh = Mesh()
    _EDGE_FACTOR = min(1, 3/max(size))
    try:
        planes = cobble(mesh, palette, ico(level), 0, 3, 1, 1, random.Random(seed), form, cuts)
    finally:
        _EDGE_FACTOR = 1
    lo = Vector(tuple(min(p[i] for p in mesh.verts) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in mesh.verts) for i in range(3)))
    centre = (lo+hi)*.5
    mesh.verts = [tuple((p[i]-centre[i])*size[i]/(hi[i]-lo[i]) for i in range(3)) for p in mesh.verts]
    base = min(p[2] for p in mesh.verts)
    mesh.verts = [(x, y, z-base-.035) for x, y, z in mesh.verts]
    pale = .38 if ASSET == "shore_stones_a" else .74
    mesh.colors = [blend(color, palette["canyon_chalk"], pale) for color in mesh.colors]
    obj = mesh.object(name, (material,), "stone_tones", "stone_saturation")
    obj.data.update()
    tones = obj.data.color_attributes["stone_tones"]
    normals=[vertex.normal.copy() for vertex in obj.data.vertices]
    for vertex,normal in zip(obj.data.vertices,normals):
        gain = .93+.10*max(0, normal.z)-.18*max(0, -normal.z)
        color = tones.data[vertex.index].color
        tones.data[vertex.index].color = tuple(c*gain for c in color[:3])+(1,)
    obj.data.set_sharp_from_angle(angle=math.radians(24))
    obj["stone_piece"] = True
    obj["lake_shore_recipe"] = "pr9/lake_shore_a"
    obj["recipe_seed"] = seed
    obj["ico_subdivisions"] = level
    obj["fracture_planes"] = [tuple(row[:3]) for row in planes]
    obj["split_normal"] = tuple(planes[-1][:3])
    return obj


def transfer_stone_attributes(source, target):
    tree = BVHTree.FromObject(source, bpy.context.evaluated_depsgraph_get())
    inverse = source.matrix_world.inverted()
    colors = source.data.color_attributes["stone_tones"]
    tone = target.data.color_attributes.get("stone_tones") or target.data.color_attributes.new(name="stone_tones", type="FLOAT_COLOR", domain="POINT")
    if target.data.attributes.get("stone_saturation") is None:
        target.data.attributes.new("stone_saturation", "FLOAT", "POINT")
    for vertex in target.data.vertices:
        hit = tree.find_nearest(inverse@(target.matrix_world@vertex.co))
        ids = source.data.polygons[hit[2]].vertices
        tone.data[vertex.index].color = tuple(sum(colors.data[i].color[j] for i in ids)/len(ids) for j in range(4))


def world_tree(obj):
    obj.data.calc_loop_triangles()
    return BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],
                               [tuple(t.vertices) for t in obj.data.loop_triangles], all_triangles=True)


def inside(tree, point):
    count = 0
    origin = point.copy()
    direction = Vector((.173, .089, 1)).normalized()
    for _ in range(32):
        hit = tree.ray_cast(origin, direction)
        if hit[0] is None:
            return count % 2 == 1
        count += 1
        origin = hit[0]+direction*.00001
    raise RuntimeError("Ambiguous stone containment")


def separate_stones():
    stones = [o for o in vrlib.source_objects() if o.get("stone_piece")]
    stones.sort(key=lambda o: math.prod(vrlib.world_bounds([o])[1]-vrlib.world_bounds([o])[0]), reverse=True)
    fixed = []
    for obj in stones:
        bpy.context.view_layer.update()
        lo, hi = vrlib.world_bounds([obj])
        centre = (lo+hi)*.5
        direction = Vector((centre.x, centre.y, 0))
        if direction.length < .01:
            direction = Vector((1, 0, 0))
        direction.normalize()
        for attempt in range(160):
            bpy.context.view_layer.update()
            lo, hi = vrlib.world_bounds([obj])
            centre = (lo+hi)*.5
            tree = world_tree(obj)
            collision = False
            for other, other_tree, low, high in fixed:
                if any(hi[i] < low[i] or high[i] < lo[i] for i in range(3)):
                    continue
                if tree.overlap(other_tree) or inside(other_tree, centre):
                    collision = True
                    break
            if not collision:
                fixed.append((obj, tree, lo, hi))
                break
            obj.location += direction*.035
        else:
            raise RuntimeError("Could not separate "+obj.name)


def add_grit():
    rng = random.Random(SEED+890)
    stones = [o for o in vrlib.source_objects() if o.get("stone_piece")]
    trees = [world_tree(o) for o in stones]
    bed = next((o for o in vrlib.source_objects() if o.get("gravel_apron")),None)
    if bed is None:
        raise ValueError("A gravel apron is required")
    low, high = vrlib.world_bounds([bed])
    support = world_tree(bed)
    palette = {k: v["linear_rgb"] for k, v in vrmat.load_palette().items()}
    mesh, template = Mesh(), ico(2)
    count = {"rock_boulder_b": 600, "cliff_strata_a": 3800, "rock_pillar_a": 2200, "shore_stones_a": 650}[ASSET]
    accepted = []
    cells={}
    for attempt in range(count*40):
        if len(accepted) >= count:
            break
        x, y = rng.uniform(low.x, high.x), rng.uniform(low.y, high.y)
        hit = support.ray_cast(Vector((x, y, 100)), Vector((0, 0, -1)))[0]
        if hit is None:
            continue
        r = rng.uniform(.018, .065) if ASSET != "shore_stones_a" else rng.uniform(.009, .035)
        bound = r*1.35+.002
        cell=(math.floor(x/.20),math.floor(y/.20))
        nearby=[p for dx in (-1,0,1) for dy in (-1,0,1) for p in cells.get((cell[0]+dx,cell[1]+dy),())]
        if any((x-a)**2+(y-b)**2 < (bound+c)**2 for a, b, c in nearby):
            continue
        offsets = ((0, 0), (bound, 0), (-bound, 0), (0, bound), (0, -bound))
        if any(tree.ray_cast(Vector((x+dx, y+dy, 100)), Vector((0, 0, -1)))[0] is not None
               for tree in trees for dx, dy in offsets):
            continue
        start = len(mesh.verts)
        first_face=len(mesh.faces)
        cobble(mesh, palette, template, 0, 3, r, rng.uniform(.35, .7), rng, "split")
        local = mesh.verts[start:]
        zmin = min(p[2] for p in local)
        for i, (px, py, pz) in enumerate(local, start):
            mesh.verts[i] = (px+x, py-3+y, pz-zmin+hit.z-.006)
            mesh.colors[i] = blend(mesh.colors[i], palette["canyon_chalk"], .70)
        candidate=BVHTree.FromPolygons(mesh.verts[start:],[tuple(i-start for i in face) for face in mesh.faces[first_face:]],all_triangles=True)
        if any(candidate.overlap(tree) for tree in trees):
            del mesh.verts[start:]
            del mesh.colors[start:]
            del mesh.factors[start:]
            del mesh.faces[first_face:]
            continue
        accepted.append((x, y, bound))
        cells.setdefault(cell,[]).append((x,y,bound))
    if not accepted:
        raise RuntimeError("No exposed gravel apron")
    obj = mesh.object("Modellierter_Kalkgrus", (stone_material(ASSET+"_Kalkgrus", ASSET == "shore_stones_a"),),
                      "stone_tones", "stone_saturation")
    obj["modelled_grit_count"] = len(accepted)
    obj["grit_discs_m"]=[value for disc in accepted for value in disc]


def shore_wetness():
    if ASSET != "shore_stones_a":
        return
    palette = vrmat.load_palette()
    for obj in vrlib.source_objects():
        if obj.get("gravel_apron"):
            tones=obj.data.color_attributes.new(name="bank_tones",type="FLOAT_COLOR",domain="POINT")
            wet=obj.data.attributes.new("ground_moisture","FLOAT","POINT")
            for vertex in obj.data.vertices:
                p=obj.matrix_world@vertex.co
                factor=1-smooth((p.y+1.65)/3.3)
                dry=palette["path_sand"]["linear_rgb"]
                soaked=scale(blend(palette["soil"]["linear_rgb"],dry,.45),.60)
                tones.data[vertex.index].color=blend(dry,soaked,factor)+(1,)
                wet.data[vertex.index].value=factor
        tones = obj.data.color_attributes.get("stone_tones")
        wet = obj.data.attributes.get("stone_saturation")
        if tones is None or wet is None:
            continue
        for vertex in obj.data.vertices:
            p = obj.matrix_world@vertex.co
            factor = 1-smooth((p.y+1.65)/3.3)
            color = tones.data[vertex.index].color
            tones.data[vertex.index].color = blend(color[:3], scale(palette["shore_wet"]["linear_rgb"], .46), factor*.76)+(1,)
            wet.data[vertex.index].value = factor


def finalize_reference_asset():
    separate_stones()
    add_grit()
    shore_wetness()
    bpy.context.view_layer.update()
    low, high = vrlib.world_bounds(vrlib.source_objects())
    shift = Vector(((low.x+high.x)/2, (low.y+high.y)/2, 0))
    for obj in vrlib.source_objects():
        obj.location -= shift
    vrlib.use_cycles_cpu(bpy.context.scene, 32)


def fines_bed(name, radius, material, height=.16, slope=False):
    height=min(height,.018)
    verts=[(0,0,min(1.8,1.6*math.tan(math.radians(32)))-.005 if slope else height)]
    count,rings=96,28
    for row in range(1,rings+1):
        r=row/rings
        for j in range(count):
            angle=math.tau*j/count
            irregular=1+.035*math.sin(angle*7)+.025*math.sin(angle*11+1)
            x,y=radius[0]*r*math.cos(angle)*irregular,radius[1]*r*math.sin(angle)*irregular
            z=height*(1-r**3)
            if slope:
                z=max(0,(y+1.6)*math.tan(math.radians(32)))*max(0,1-(abs(x)/radius[0])**4)
                z=min(1.8,z)*(1-r**12)
            z+=.012*noise.noise(Vector((x*31,y*31,3)))*(1-r*r)
            verts.append((x,y,z-.005))
    faces=[(0,1+j,1+(j+1)%count) for j in range(count)]
    for row in range(rings-1):
        a,b=1+row*count,1+(row+1)*count
        faces.extend((a+j,b+j,b+(j+1)%count,a+(j+1)%count) for j in range(count))
    last=1+(rings-1)*count
    bottom=len(verts)
    verts.extend((verts[last+j][0],verts[last+j][1],-.045) for j in range(count))
    faces.extend((last+j,bottom+j,bottom+(j+1)%count,last+(j+1)%count) for j in range(count))
    faces.append(tuple(reversed(range(bottom,bottom+count))))
    obj=link_mesh(name,verts,faces,material)
    obj["gravel_apron"]=True
    return obj


def grass_tufts(points, material, seed):
    rng=random.Random(seed)
    verts,faces=[],[]
    for point in points:
        for _ in range(9):
            angle=rng.uniform(0,math.tau)
            p=Vector(point)+Vector((rng.uniform(-.07,.07),rng.uniform(-.07,.07),-.01))
            width=rng.uniform(.008,.018)
            side=Vector((math.cos(angle)*width,math.sin(angle)*width,0))
            n=len(verts)
            verts.extend((p-side,p+side,p+Vector((.002,-.002,.001)),p+Vector((rng.uniform(-.07,.07),rng.uniform(-.07,.07),rng.uniform(.10,.22)))))
            faces.extend(((n,n+2,n+1),(n,n+1,n+3),(n+1,n+2,n+3),(n+2,n,n+3)))
    return link_mesh("Randgras",verts,faces,material)


def cut_cleft(body, outward, phase):
    if not body.data.polygons or len(outward)!=3 or math.hypot(outward[0],outward[1])<.000001 or abs(outward[2])>.000001:
        raise ValueError("Cleft needs a rock surface and a horizontal direction")
    tree=BVHTree.FromObject(body,bpy.context.evaluated_depsgraph_get())
    outward=Vector(outward).normalized()
    tangent=Vector((-outward.y,outward.x,0))
    lo,hi=vrlib.world_bounds([body])
    verts=[]
    sections=140
    for i in range(sections):
        t=i/(sections-1)
        z=lo.z+(hi.z-lo.z)*(.18+.58*t)
        wander=.12*math.sin(z*3+phase)+.02*math.sin(z*9+phase)
        origin=outward*5+tangent*wander+Vector((0,0,z))
        hit=tree.ray_cast(origin,-outward)[0]
        if hit is None:
            raise RuntimeError("Cleft missed the main rock")
        taper=math.sin(math.pi*t)**.65
        width=.003+.14*taper*(.85+.15*math.sin(z*7))
        depth=.002+.085*taper
        verts.extend((hit+outward*.18-tangent*width,
                      hit+outward*.18+tangent*width,hit-outward*depth))
    faces=[(2,1,0)]
    for i in range(sections-1):
        a,b=i*3,(i+1)*3
        faces.extend((a+j,a+(j+1)%3,b+(j+1)%3,b+j) for j in range(3))
    faces.append(tuple(range((sections-1)*3,sections*3)))
    cutter=link_mesh("Auskeilende_Kluft",verts,faces,body.data.materials[0])
    tones=cutter.data.color_attributes.new(name="stone_tones",type="FLOAT_COLOR",domain="POINT")
    palette=vrmat.load_palette()
    recess=tuple((a*.88+b*.12)*.78 for a,b in zip(palette["canyon_chalk"]["linear_rgb"],palette["soil"]["linear_rgb"]))
    for value in tones.data:
        value.color=recess+(1,)
    cutter.data.attributes.new("stone_saturation","FLOAT","POINT")
    bpy.context.view_layer.objects.active=body
    modifier=body.modifiers.new("Tiefe_saubere_Sackkluft","BOOLEAN")
    modifier.operation="DIFFERENCE"
    modifier.solver="EXACT"
    modifier.object=cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
    bm=bmesh.new()
    bm.from_mesh(body.data)
    bmesh.ops.dissolve_degenerate(bm,dist=.000001,edges=list(bm.edges))
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    tones=body.data.color_attributes["stone_tones"]
    for value in tones.data:
        if max(value.color[:3])<.04:
            value.color=recess+(1,)


def feather(value):
    t=max(0,min(1,value))
    return t*t*(3-2*t)


def weather_faces(body):
    mesh=body.data
    if not mesh.vertices:
        raise ValueError("No rock surface to weather")
    bm=bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    for _ in range(8):
        long_edges=[edge for edge in bm.edges if edge.calc_length()>.038]
        if not long_edges:
            break
        bmesh.ops.subdivide_edges(bm,edges=long_edges,cuts=1,use_grid_fill=True)
    pending=set(bm.faces)
    components=[]
    while pending:
        component={pending.pop()}
        frontier=component.copy()
        while frontier:
            frontier={neighbor for face in frontier for edge in face.edges if edge.is_manifold
                      for neighbor in edge.link_faces}&pending
            pending-=frontier
            component|=frontier
        components.append(component)
    surface=max(components,key=lambda group:sum(face.calc_area() for face in group))
    bmesh.ops.delete(bm,geom=[face for face in bm.faces if face not in surface],context="FACES")
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mesh.set_sharp_from_angle(angle=math.radians(16))
    sharp=mesh.attributes.get("sharp_edge")
    adjacent=[set() for vertex in mesh.vertices]
    boundary=set()
    for edge in mesh.edges:
        a,b=edge.vertices
        adjacent[a].add(b)
        adjacent[b].add(a)
        if sharp is not None and sharp.data[edge.index].value:
            boundary.update((a,b))
    distances={i:0 for i in boundary}
    frontier=boundary
    for step in range(1,5):
        frontier={j for i in frontier for j in adjacent[i] if j not in distances}
        distances.update({i:step for i in frontier})
    attribute=mesh.attributes.new("weather_relief","FLOAT","POINT")
    offsets=[]
    normals=[vertex.normal.copy() for vertex in mesh.vertices]
    for vertex,normal in zip(mesh.vertices,normals):
        p=vertex.co.copy()
        dip=p.z+.16*p.x-.075*p.y
        cell_distances,sites=noise.voronoi(p*4.2+Vector((3,7,11)))
        weights=[math.exp(-(d-cell_distances[0])/.10) for d in cell_distances[:3]]
        stepped=sum(weight*noise.cell(sites[k]) for k,weight in enumerate(weights))/sum(weights)
        bed=.010*max(0,math.sin(dip*math.tau/.34+.25*noise.noise(p*2)))**3
        bed*=feather((noise.noise(p*2+Vector((4,8,2)))-.18)*4)
        distance=distances.get(vertex.index,4)
        ripple=.012*math.sin(p.dot(Vector((4,7,3)))*math.tau+1.5*noise.noise(p*4))
        ripple*=feather((noise.noise(p*1.7)-.28)*5)
        chip=.020*feather((noise.noise(p*23)-.10)*3)*(1-feather(distance/4))
        amount=(.035*stepped+bed+ripple+.004*noise.noise(p*17))*feather(distance/2)-chip
        amount*=feather((p.z+.035)/.15)
        vertex.co+=normal*amount
        attribute.data[vertex.index].value=amount
        offsets.append(amount)
    mesh.update()
    tones=mesh.color_attributes["stone_tones"]
    for vertex,normal in zip(mesh.vertices,normals):
        gain=.93+.10*normal.x-.07*normal.y+.05*noise.noise(vertex.co*1.2)
        color=tones.data[vertex.index].color
        tones.data[vertex.index].color=tuple(c*gain for c in color[:3])+(1,)
    body["medium_relief_range_m"]=(min(offsets),max(offsets))


def irregular_hollows(body):
    outward=Vector((1,-.25,.04)).normalized()
    tangent=Vector((.25,1,0)).normalized()
    cavities=((- .43,.61,.29,.18,.12,.25),
              (.02,.87,.25,.21,.25,-.35),
              (.43,.62,.35,.17,.18,.12))
    attribute=body.data.attributes.new("hollow_depth","FLOAT","POINT")
    for vertex in body.data.vertices:
        p=vertex.co.copy()
        depth=0
        for i,(u,z,rx,rz,amount,angle) in enumerate(cavities):
            a,b=p.dot(tangent)-u,p.z-z
            x=a*math.cos(angle)-b*math.sin(angle)
            y=a*math.sin(angle)+b*math.cos(angle)
            radius=(abs(x/rx)**2.6+abs(y/rz)**1.6)**.5
            radius+=.12*noise.noise(p*12+Vector((i*7,4,9)))
            pocket=feather((1-radius)/.42)
            depth=max(depth,amount*pocket*(.85+.15*noise.noise(p*17)))
        depth*=feather((vertex.normal.dot(outward)-.5)/.35)
        vertex.co-=outward*depth
        attribute.data[vertex.index].value=depth
    body.data.update()
    body["tafoni_hollow_count"]=3
    body["tafoni_method"]="three warped irregular hollows with unequal depths"


def compact_fallen_block(material):
    block=fractured_rock("Kompakter_Fallblock",(.98,.80,.68),SEED+23,material,
                         cuts=7,weathering=.3,strata=.34)
    points=np.array([tuple(v.co) for v in block.data.vertices])
    centre=points.mean(axis=0)
    values,axes=np.linalg.eigh(np.cov(points.T))
    local=(points-centre)@axes
    spans=np.ptp(local,axis=0)
    local*=np.maximum(1,.38/spans)
    points=local@axes.T+centre
    for vertex,point in zip(block.data.vertices,points):
        vertex.co=point
    block.data.update()
    block["replacement_kind"]="compact fallen chunk"
    return block


def build_asset():
    rng=random.Random(SEED)
    noise.seed_set(SEED)
    stone,moss=materials()
    soil=vrmat.get("dirt_path").copy()
    soil.name="rock_boulder_b_Sandiger_Feinkies"
    body=fractured_rock("Sandstein_Hauptmasse",(3.2,2.6,1.6),SEED,stone,
                              cuts=5,split=False,tafoni=False,fissures=False)
    block=compact_fallen_block(stone)
    block.name="Abgespaltener_Bruchblock"
    bm=bmesh.new()
    bm.from_mesh(body.data)
    cut_plane(bm,(1.05,.1,1.17),Vector((.67,.19,.72)).normalized())
    cut_plane(bm,(-1.13,-.22,.96),Vector((-.74,-.31,.60)).normalized())
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    body.data.set_sharp_from_angle(angle=math.radians(16))
    cut_cleft(body,(.85,.5,0),.2)
    cut_cleft(body,(-.6,.8,0),2.3)
    body["fissure_count"]=2
    body["cleft_method"]="tapered Boolean V-grooves"
    weather_faces(body)
    moss_shell(body,moss)
    normal=Vector(body["split_normal"])
    outward=Vector((normal.x,normal.y,0)).normalized()
    pivot=sum((v.co for v in block.data.vertices),Vector())/len(block.data.vertices)
    for v in block.data.vertices:
        v.co-=pivot
    block.location=outward*1.85
    block.rotation_euler=(.12,.28,math.atan2(outward.y,outward.x)+.4)
    bpy.context.view_layer.update()
    block.location.z+=-.04-min((block.matrix_world@v.co).z for v in block.data.vertices)
    bpy.context.view_layer.objects.active=block
    block.select_set(True)
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    block.select_set(False)
    bed=fines_bed("Sand_und_Feinkieskragen",(1.85,1.6),soil,.30)
    bpy.context.view_layer.update()
    support=BVHTree.FromObject(bed,bpy.context.evaluated_depsgraph_get())
    block_support=BVHTree.FromObject(block,bpy.context.evaluated_depsgraph_get())
    block_inverse=block.matrix_world.inverted()
    for i,size in enumerate((.40,.29,.18,.12,.32,.09,.22,.15,.35,.10,.26,.07)):
        shard=fractured_rock(f"Bruchsplitter_{i:02d}",(size,size*rng.uniform(.55,.85),size*rng.uniform(.3,.65)),SEED+100+i,stone,cuts=8,weathering=.25,strata=.13)
        angle=math.atan2(outward.y,outward.x)+rng.uniform(-.9,.9)
        radius=rng.uniform(.78,.94)
        shard.location=(math.cos(angle)*1.75*radius,math.sin(angle)*1.48*radius,0)
        shard.rotation_euler=(rng.uniform(-.3,.3),rng.uniform(-.3,.3),rng.uniform(-math.pi,math.pi))
        bpy.context.view_layer.update()
        offset=-math.inf
        for v in shard.data.vertices:
            p=shard.matrix_world@v.co
            hit=support.ray_cast(Vector((p.x,p.y,4)),Vector((0,0,-1)))[0]
            block_hit=block_support.ray_cast(block_inverse@Vector((p.x,p.y,4)),Vector((0,0,-1)))[0]
            floor=max(hit.z if hit is not None else 0,(block.matrix_world@block_hit).z if block_hit is not None else 0)
            offset=max(offset,floor-p.z)
        shard.location.z+=offset-.02
    bpy.context.view_layer.update()
    grass=[]
    for angle in (.2,1.9,3.2,4.6):
        x,y=1.65*math.cos(angle),1.4*math.sin(angle)
        hit=support.ray_cast(Vector((x,y,3)),Vector((0,0,-1)))[0]
        if hit is not None:
            grass.append(hit)
    grass_tufts(grass,vrmat.get("grass_ground"),SEED)
    bpy.context.view_layer.update()
    lo,hi=vrlib.world_bounds(vrlib.source_objects())
    shift=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,0))
    for obj in vrlib.source_objects():
        obj.location-=shift
    vrlib.use_cycles_cpu(bpy.context.scene,32)


def build():
    build_asset()
    finalize_reference_asset()

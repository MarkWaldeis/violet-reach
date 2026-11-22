"""Deterministischer Canyonstein; asset-lokales dichtes Bruchrezept."""
import math
import random

import bmesh
import bpy
from mathutils import Quaternion, Vector, noise
from mathutils.bvhtree import BVHTree

import vrlib
import vrmat

ASSET="cliff_strata_a"
SEED=91307


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


def cut_plane(bm, point, normal):
    bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                          plane_co=point, plane_no=normal, clear_outer=True, dist=.00001)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))


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
        radial = 1 + (.13 if form == "worn" else .09)*coarse
        for nx, ny, nz, upper in cuts:
            dot = nx*u+ny*v+nz*w
            if dot > .28:
                radial = eased_min(radial, upper/dot, .035 if form != "worn" else .095)
        lamina = math.sin((19+7*weather)*(w+.22*u-.14*v) + .76*coarse)
        breakout = smooth(.44 + 1.25*medium - .43*weather)
        radial *= (1 + (.026+.016*weather)*medium + .013*fine
                   - .043*chip*breakout + (.019 if form == "slab" else .010)*lamina)
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
    level = 8 if max(size) > 10 else 7 if max(size) > 1.5 else 6 if max(size) > .4 else 4
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
            width=rng.uniform(.018,.038)
            side=Vector((math.cos(angle)*width,math.sin(angle)*width,0))
            n=len(verts)
            verts.extend((p-side,p+side,p+Vector((.002,-.002,.001)),p+Vector((rng.uniform(-.07,.07),rng.uniform(-.07,.07),rng.uniform(.55,1.15) if ASSET=="rock_pillar_a" else rng.uniform(.38,.78)))))
            faces.extend(((n,n+2,n+1),(n,n+1,n+3),(n+1,n+2,n+3),(n+2,n,n+3)))
    return link_mesh("Randgras",verts,faces,material)


def chalk_material(seed, old=False):
    return stone_material(ASSET+"_Referenzkalk_"+str(seed))

def seat_on_bed(obj, bed, burial):
    bpy.context.view_layer.update()
    tree=BVHTree.FromObject(bed,bpy.context.evaluated_depsgraph_get())
    inverse=bed.matrix_world.inverted()
    offset=-math.inf
    for vertex in obj.data.vertices:
        p=obj.matrix_world@vertex.co
        hit=tree.ray_cast(inverse@Vector((p.x,p.y,6)),Vector((0,0,-1)))[0]
        floor=(bed.matrix_world@hit).z if hit is not None else 0
        offset=max(offset,floor-p.z)
    obj.location.z+=offset-burial
    bpy.context.view_layer.update()
    lo=min((obj.matrix_world@v.co).z for v in obj.data.vertices)
    obj.location.z+=max(0,-.05-lo)
    bpy.context.view_layer.objects.active=obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    obj.select_set(False)


def turf_shell(body, material, name="Angewachsene_Moosschale", coverage=.35, thickness=.06, min_height=.9, normal_z=.55):
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
    def field(p):
        return noise.noise(p*.16 + Vector((3, 8, 1))) + .12*noise.noise(p*.43)
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
    while pending:
        component={pending.pop()}
        frontier=set(component)
        while frontier:
            frontier={j for i in frontier for j in adjacent_faces[i]}&pending
            pending-=frontier
            component|=frontier
        if sum(chosen[i].area for i in component)>.012:
            kept.extend(chosen[i] for i in sorted(component))
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
        taper = min(1, distance.get(j, 9)/3)
        clump = .0035*noise.noise(p*30)+.0008*noise.noise(p*155)
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
        edge_attribute.data[j].value=1-min(1,distance.get(j%n,9)/3)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    print("MOSS_SURFACE_COVERAGE", round(area/sum(f.area for f in candidates)*100, 1))
    return obj


def smooth(value):
    t=max(0,min(1,value))
    return t*t*(3-2*t)


def strata_heights(height):
    if height<=0:
        raise ValueError("Strata height must be positive")
    rng=random.Random(SEED+17)
    count=max(2,round(height/3.5))
    for attempt in range(1000):
        widths=[rng.uniform(1.2,5.8) for i in range(count)]
        widths=[w*height/sum(widths) for w in widths]
        if min(widths)>=1.2 and max(widths)<=5:
            values=[0]
            for width in widths:
                values.append(values[-1]+width)
            return values
    raise RuntimeError("Could not partition strata")


def bench_offset(z, axis, heights):
    i=next((i for i,b in enumerate(heights[1:]) if z<b),len(heights)-2)
    a,b=heights[i:i+2]
    t=(z-a)/(b-a)
    pinch=smooth((.5+.5*math.sin(axis+i*2.37))*.95)
    rise,fall=.30/(b-a),.24/(b-a)
    lip=smooth((t-(.75-rise))/rise)*(1-smooth((t-(1-fall))/fall))
    undercut=math.exp(-((t-.58)/.11)**2)
    return (.10+1.10*pinch)*(lip-.32*undercut)


def grass_material():
    mat=vrmat.get("grass_ground").copy()
    mat.name=ASSET+"_Terrassengras"
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    original=bsdf.inputs["Base Color"].links[0].from_socket
    edge=nt.nodes.new("ShaderNodeAttribute")
    edge.attribute_name="moss_edge"
    blend=nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(edge.outputs["Fac"],blend.inputs[0])
    nt.links.new(original,blend.inputs[1])
    root=nt.nodes.new("ShaderNodeAttribute")
    root.attribute_name="stone_tones"
    nt.links.new(root.outputs["Color"],blend.inputs[2])
    nt.links.new(blend.outputs[0],bsdf.inputs["Base Color"])
    return mat


def landmark(body, width, depth, height, mode):
    lo,hi=vrlib.world_bounds([body])
    for v in body.data.vertices:
        v.co.x=(v.co.x-(lo.x+hi.x)/2)*width/(hi.x-lo.x)
        v.co.y=(v.co.y-(lo.y+hi.y)/2)*depth/(hi.y-lo.y)
        v.co.z=(v.co.z-lo.z)*height/(hi.z-lo.z)-.035
    if mode=="wall":
        bm=bmesh.new()
        bm.from_mesh(body.data)
        cut_plane(bm,(20,0,0),Vector((1,0,0)))
        cut_plane(bm,(-20,0,0),Vector((-1,0,0)))
        bm.to_mesh(body.data)
        bm.free()
    heights=strata_heights(height)
    for v in body.data.vertices:
        p=v.co.copy()
        if mode=="wall":
            blend=smooth((abs(p.x)-15)/5)
            angle=math.atan2((p.z-height*.5)/(height*.5),p.y/(depth*.5))
            c,s=math.cos(angle),math.sin(angle)
            r=(c**8+s**8)**(-1/8)
            p.y=p.y*(1-blend)+depth*.5*c*r*blend
            p.z=p.z*(1-blend)+height*.5*(1+s*r)*blend
            axis=math.tau*(p.x+20)/40
            front=smooth((p.y-.4)/1.5)
            p.y+=front*bench_offset(p.z,axis,heights)
            envelope=math.sin(math.pi*(p.x+20)/40)**2
            for i,centre in enumerate((-12,-3.5,7,14)):
                path=centre+.4*math.sin(p.z*.19+i)+.14*math.sin(p.z*.63+i)
                taper=smooth((p.z-1.5)/4)*(1-smooth((p.z-height*.88)/4))
                trench=max(0,1-abs(p.x-path)/(.16+.12*math.sin(p.z*.11+i)**2))
                p.y-=front*envelope*taper*trench*1.1
        else:
            h=max(0,min(1,p.z/height))
            taper=1.14-.35*h-.10*math.exp(-((h-.5)/.15)**2)
            radial=Vector((p.x,p.y,0)).normalized()
            p.x*=taper
            p.y*=taper
            axis=math.atan2(p.y,p.x)
            lip=bench_offset(p.z,axis,heights)*.65
            p+=radial*lip
            for i,angle in enumerate((.3,2.6,4.9)):
                path=angle+.09*math.sin(p.z*.16+i)
                delta=math.atan2(math.sin(axis-path),math.cos(axis-path))
                cut=max(0,1-abs(delta)/.045)
                window=smooth((h-.07)/.12)*(1-smooth((h-.90)/.08))
                p-=radial*(.85*cut*window)
        v.co=p
    body.data.update()
    mats=[chalk_material(SEED+200+i) for i in range(6)]
    body.data.materials.clear()
    for mat in mats:
        body.data.materials.append(mat)
    for face in body.data.polygons:
        index=next((i for i,b in enumerate(heights[1:]) if face.center.z<b),len(heights)-2)
        face.material_index=index%len(mats)
    bm=bmesh.new()
    bm.from_mesh(body.data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(body.data)
    bm.free()
    body["strata_heights_m"]=heights
    body["landmark_mode"]=mode
    if mode=="wall":
        body["tile_pitch_m"]=40.0


def plant_terraces(body, mode):
    bpy.context.view_layer.update()
    material=grass_material()
    threshold=body.dimensions.z-2.0 if mode=="pillar" else 1.2
    turf=turf_shell(body,material,"Grasige_Terrassen",coverage=.98,
                    thickness=.16 if mode=="pillar" else .12,min_height=threshold,
                    normal_z=-.12 if mode=="pillar" else .48)
    bpy.context.view_layer.update()
    faces=[f for f in turf.data.polygons if f.normal.z>.30 and f.center.z>threshold]
    rng=random.Random(SEED+71)
    points=[turf.matrix_world@f.center for f in rng.sample(faces,min(900,len(faces)))]
    grass_tufts(points,material,SEED+71)


def finish():
    bpy.context.view_layer.update()
    lo,hi=vrlib.world_bounds(vrlib.source_objects())
    shift=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,0))
    for obj in vrlib.source_objects():
        obj.location-=shift
    vrlib.use_cycles_cpu(bpy.context.scene,32)



def wall_surface(donor):
    heights=strata_heights(45)
    rng=random.Random(SEED+412)
    setbacks=[rng.uniform(.55,.62) for _ in heights[1:-1]]
    setbacks[len(setbacks)//2]=2.0
    joints=[]
    for band,(a,b) in enumerate(zip(heights,heights[1:])):
        for k in range(rng.randint(2,5)):
            joints.append((rng.uniform(-18,18),a+rng.uniform(.03,.42)*(b-a),
                           min(44.4,b+rng.uniform(-.20,.55)*(b-a)),
                           rng.uniform(.30,.65),rng.uniform(.35,.85),rng.uniform(0,6)))
    nx,ny,nz=480,96,640
    perimeter=([(i,0) for i in range(nx+1)]+[(nx,k) for k in range(1,ny+1)]
               +[(i,ny) for i in range(nx-1,-1,-1)]+[(0,k) for k in range(ny-1,0,-1)])
    count=len(perimeter)
    def surface(i,k,h):
        u,t=i/nx,k/ny
        phase=math.tau*u
        z=-.035+h*(44.55+.42*math.sin(phase)+.21*math.sin(3*phase+.7))
        side_distances,side_sites=noise.voronoi(Vector((t*3.1,z*.15,SEED*.013)))
        weights=[math.exp(-(d-side_distances[0])/.10) for d in side_distances[:3]]
        side_cell=sum(w*(noise.cell(side_sites[i])*2-1) for i,w in enumerate(weights))/sum(weights)
        side=.54*side_cell+.08*n3(t*15,z*.8,SEED*.013)
        x=-20+40*u+math.sin(math.pi*t)**.8*side
        q=Vector((math.sin(phase)*3,math.cos(phase)*3,z*.24))
        coarse=n3(q.x+SEED*.013,q.y,q.z)
        chip=noise.voronoi(q*2.7)[0]
        distances,sites=noise.voronoi(q*2.3+Vector((SEED*.013,2,7)))
        weights=[math.exp(-(d-distances[0])/.055) for d in distances[:3]]
        facets=sum(w*noise.cell(sites[j]) for j,w in enumerate(weights))/sum(weights)
        relief=.15*facets+.085*n3(q.x*8,q.y*8,q.z*8+SEED*.013)
        relief-=.08*(1-smooth((chip[1]-chip[0])/.16))*smooth(n3(q.x*13,q.y*13,q.z*13)+.5)
        warp=z+.55*math.sin(phase*2+z*.12)+.23*math.sin(phase*5-z*.20)
        band=next((j for j,b in enumerate(heights[1:]) if warp<b),len(heights)-2)
        a,b=heights[band:band+2]
        f=(warp-a)/(b-a)
        retreat=sum((step+.05*math.sin(phase*2+j*1.71))*smooth((warp-edge+.09)/.18)
                    for j,(edge,step) in enumerate(zip(heights[1:-1],setbacks)))
        under=-.24*math.exp(-((f-.90)/.06)**2)
        lip=.12*math.exp(-((f-.98)/.025)**2)
        broken_edge=-.15*smooth((n3(q.x*17,q.y*17,band+SEED*.01)+.2)*2)*math.exp(-((f-.98)/.06)**2)
        front=5.2-retreat+.25*coarse+relief+under+lip+broken_edge+.18*f*math.sin(band*2.7)
        for centre,start,end,width,depth,seed in joints:
            path=centre+.58*math.sin(z*.23+seed)+.19*math.sin(z*.71-seed)
            window=smooth((z-start)/.65)*(1-smooth((z-end)/.65))
            width*=.65+.35*math.sin(z*.53+seed)**2
            front-=depth*window*max(0,1-abs(x-path)/width)*math.sin(math.pi*u)**2
        back=-5.65-.40*n3(q.x+31,q.y-17,q.z*.7)-1.3*relief
        y=front*(1-t)+back*t
        z+=h*(1-h)*.10*n3(q.x*.7,q.y*.7+t*4,z*.5)
        return (x,y,z)
    verts=[surface(i,k,j/nz) for j in range(nz+1) for i,k in perimeter]
    faces=[]
    for j in range(nz):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.append((a,b,b+count,a+count))
    lookup={p:i for i,p in enumerate(perimeter)}
    for h,offset in ((0,0),(1,nz*count)):
        grid={}
        for k in range(ny+1):
            for i in range(nx+1):
                if (i,k) in lookup:
                    grid[i,k]=offset+lookup[i,k]
                else:
                    grid[i,k]=len(verts)
                    verts.append(surface(i,k,h))
        for k in range(ny):
            for i in range(nx):
                face=(grid[i,k],grid[i+1,k],grid[i+1,k+1],grid[i,k+1])
                faces.append(face if h else tuple(reversed(face)))
    obj=link_mesh("Canyonwand",verts,faces,donor.data.materials[0])
    transfer_stone_attributes(donor,obj)
    for key in donor.keys():
        obj[key]=donor[key]
    bpy.data.objects.remove(donor,do_unlink=True)
    mats=[chalk_material(SEED+200+i) for i in range(6)]
    obj.data.materials.clear()
    for material in mats:
        obj.data.materials.append(material)
    for face in obj.data.polygons:
        band=next((i for i,b in enumerate(heights[1:]) if face.center.z<b),len(heights)-2)
        face.material_index=band%6
        face.use_smooth=True
    obj.data.set_sharp_from_angle(angle=math.radians(34))
    obj["strata_heights_m"]=heights
    obj["tile_pitch_m"]=40.0
    obj["perimeter_columns"]=count
    obj["wall_rows"]=nz+1
    obj["side_steps"]=ny
    obj["front_steps"]=nx
    obj["joint_count"]=len(joints)
    obj["closed_rock_back"]=True
    obj["stratum_setbacks_m"]=setbacks
    obj["bench_construction"]="integrated setbacks"
    obj["back_shelves"]=False
    obj["landmark_mode"]="wall"
    return obj

def build_asset():
    noise.seed_set(SEED)
    rng=random.Random(SEED)
    body=fractured_rock("Canyonwand",(7.4,1.7,6.3),SEED,chalk_material(SEED),cuts=7,weathering=.65,strata=1.6)
    body=wall_surface(body)
    soil=vrmat.get("dirt_path").copy()
    soil.name=ASSET+"_Kalksandfuss"
    bed=fines_bed("Bodenkontakt",(20.2,7.2),soil,.45)
    for i in range(14):
        size=rng.uniform(.65,1.9)
        rock=fractured_rock(f"Fussschutt_{i:02d}",(size,size*.7,size*.48),SEED+20+i,chalk_material(SEED+20+i),cuts=8,weathering=.2,strata=.45)
        rock.location=(rng.uniform(-18.5,18.5),rng.uniform(5.0,6.9),0)
        rock.rotation_euler=(rng.uniform(-.35,.35),rng.uniform(-.4,.4),rng.uniform(-math.pi,math.pi))
        seat_on_bed(rock,bed,.08)
    plant_terraces(body,"wall")
    finish()


def build():
    build_asset()
    finalize_reference_asset()

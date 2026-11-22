"""Approved fractured limestone chunks composed in metres."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

import vrlib
import vrmat

ASSET = "cliff_strata_a"
SEED = 66317


def make_rock(name, rng, radius, squash, subdivisions, mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    # Chisel the sphere with random planes to get hard, faceted rock breaks.
    planes = []
    for _ in range(26):
        n = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 1))).normalized()
        planes.append((n, radius * rng.uniform(0.62, 0.96)))
    offset = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    for v in bm.verts:
        p = v.co.copy()
        for n, d in planes:
            over = p.dot(n) - d
            if over > 0:
                p -= n * over
        direction = v.co.normalized()
        coarse = noise.fractal(p * (1.1 / radius) + offset, 1.0, 2.0, 5)
        ridged = noise.ridged_multi_fractal(p * (3.2 / radius) + offset, 1.0, 2.1, 5, 1.0, 2.0)
        fine = noise.fractal(p * (16.0 / radius) + offset, 1.0, 2.0, 4)
        p += direction * radius * (0.10 * coarse + 0.035 * (ridged - 1.0) + 0.008 * fine)
        v.co = p
    for v in bm.verts:
        v.co.z *= squash
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    return vrlib.link_to_source(obj)


def support_material(name, ao_distance, earth=False):
    mat = vrmat.get("forest_soil" if earth else "monument_weathered").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    coords = next(node for node in nodes if node.type == "TEX_COORD").outputs["Object"]

    def grain(scale, detail):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(coords, node.inputs["Vector"])
        return node.outputs["Fac"]

    def tones(source, low, high):
        node = nodes.new("ShaderNodeValToRGB")
        node.color_ramp.elements[0].color = (*low, 1)
        node.color_ramp.elements[1].color = (*high, 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, first, second):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, (float, int)):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, value in zip(node.inputs[1:3], (first, second)):
            if isinstance(value, tuple):
                socket.default_value = (*value, 1)
            else:
                links.new(value, socket)
        return node.outputs["Color"]

    if earth:
        base = bsdf.inputs["Base Color"].links[0].from_socket
        coverage = nodes.new("ShaderNodeAttribute")
        coverage.attribute_name = "moss_coverage"
        mask = coverage.outputs["Fac"]
    else:
        neutral = tuple(0.55 * a + 0.45 * b for a, b in zip(
            palette["stone_weathered"]["linear_rgb"], palette["monument_shadow"]["linear_rgb"]))
        base = tones(grain(0.87, 3), tuple(v * 0.55 for v in neutral),
                     tuple(v * 0.68 for v in neutral))
        geometry = nodes.new("ShaderNodeNewGeometry")
        up = nodes.new("ShaderNodeSeparateXYZ")
        links.new(geometry.outputs["Normal"], up.inputs[0])
        patch = nodes.new("ShaderNodeMapRange")
        patch.clamp = True
        patch.interpolation_type = "SMOOTHSTEP"
        patch.inputs["From Min"].default_value = 0.46
        patch.inputs["From Max"].default_value = 0.68
        links.new(grain(1.8, 5), patch.inputs["Value"])
        coverage = nodes.new("ShaderNodeMath")
        coverage.operation = "MULTIPLY"
        coverage.use_clamp = True
        links.new(up.outputs["Z"], coverage.inputs[0])
        links.new(patch.outputs[0], coverage.inputs[1])
        mask = coverage.outputs[0]
    moss = tones(grain(18, 5), tuple(v * 0.8 for v in palette["grass_green"]["linear_rgb"]),
                 tuple(0.7 * a + 0.3 * b for a, b in zip(
                     palette["grass_green"]["linear_rgb"], palette["grass_dry"]["linear_rgb"])))
    base = mix(mask, base, moss)
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 8
    ao.inputs["Distance"].default_value = ao_distance
    grime = tuple(v * 0.65 for v in palette["soil"]["linear_rgb"])
    links.new(mix(ao.outputs["AO"], grime, base), bsdf.inputs["Base Color"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.18
    mat["asset_tweaks"] = "copied library pores; narrow palette limestone tones, irregular moss coverage, recessed AO soil; no painted fracture lines"
    return mat


def fracture(obj, point, normal):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    cut = bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
        plane_co=point, plane_no=Vector(normal).normalized(), clear_outer=True)
    edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
    filled = bmesh.ops.holes_fill(bm, edges=edges)
    for face in filled["faces"]:
        face.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


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
            tip=Vector((rng.uniform(-.13,.13),rng.uniform(-.13,.13),rng.uniform(.65,1.25)))
            if p.x*p.x/64+p.y*p.y/49>.40 and rng.random()<.38:
                tip=Vector((p.x,p.y,0)).normalized()*rng.uniform(.45,.95)+Vector((0,0,rng.uniform(-.30,.35)))
            verts.extend((p-side,p+side,p+Vector((.002,-.002,.001)),p+tip))
            faces.extend(((n,n+2,n+1),(n,n+1,n+3),(n+1,n+2,n+3),(n+2,n,n+3)))
    return link_mesh("Randgras",verts,faces,material)


def grass_material():
    mat=vrmat.get("grass_ground").copy()
    mat.name=ASSET+"_Terrassengras"
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    original=bsdf.inputs["Base Color"].links[0].from_socket
    fresh=nt.nodes.new("ShaderNodeMixRGB")
    fresh.inputs[0].default_value=.48
    fresh.inputs[2].default_value=tuple(v*1.25 for v in vrmat.load_palette()["grass_green"]["linear_rgb"])+(1,)
    nt.links.new(original,fresh.inputs[1])
    original=fresh.outputs[0]
    edge=nt.nodes.new("ShaderNodeAttribute")
    edge.attribute_name="moss_edge"
    blend=nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(edge.outputs["Fac"],blend.inputs[0])
    nt.links.new(original,blend.inputs[1])
    blend.inputs[2].default_value=tuple(v*1.10 for v in vrmat.load_palette()["grass_green"]["linear_rgb"])+(1,)
    nt.links.new(blend.outputs[0],bsdf.inputs["Base Color"])
    return mat


def finish():
    bpy.context.view_layer.update()
    objects = vrlib.source_objects()
    if not objects:
        raise ValueError("Empty source collection")
    lo, hi = vrlib.world_bounds(objects)
    shift = Vector(((lo.x+hi.x)*.5, (lo.y+hi.y)*.5, 0))
    for obj in vrlib.source_objects():
        obj.location -= shift
    vrlib.use_cycles_cpu(bpy.context.scene, 32)


def approved_chunk(name, size, centre, seed, material, subdivisions=6):
    if len(size) != 3 or min(size) <= 0:
        raise ValueError("Three positive dimensions required")
    obj = make_rock(name, random.Random(seed), 1, 1, subdivisions, material)
    points = [v.co for v in obj.data.vertices]
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    mid = (lo+hi)*.5
    obj.data.transform(Matrix.Translation(Vector(centre)) @
                       Matrix.Diagonal(tuple(size[i]/(hi[i]-lo[i]) for i in range(3))).to_4x4() @
                       Matrix.Translation(-mid))
    obj["approved_generator"] = "c4c0cd0/crystal_cluster_b.make_rock"
    obj["recipe_seed"] = seed
    obj["stone_piece"] = True
    obj.data.update()
    return obj


def ground_debris(radius, bases, material, count, seed):
    rng = random.Random(seed)
    occupied = []
    for obj in bases:
        lo, hi = vrlib.world_bounds([obj])
        if lo.z < .1:
            occupied.append((lo.x, hi.x, lo.y, hi.y))
    gravel = []
    for i in range(count):
        size = rng.uniform(.7, 2.4) if i < 24 else rng.uniform(.10, .50)
        for attempt in range(160):
            x, y = rng.uniform(-radius[0], radius[0]), rng.uniform(-radius[1], radius[1])
            r = size*.71
            if (x/(radius[0]-r))**2+(y/(radius[1]-r))**2 > 1:
                continue
            if any(a-r < x < b+r and c-r < y < d+r for a,b,c,d in occupied):
                continue
            break
        else:
            continue
        obj = approved_chunk("Kalkbruch" if i < 24 else "Kalkgrus",
                             (size,size*rng.uniform(.65,.95),size*rng.uniform(.45,.75)),
                             (x,y,size*.15),seed+i+1,material,5 if i < 24 else 2)
        fracture(obj, (0,0,-.04), (0,0,-1))
        obj["scree_chunk"] = True
        occupied.append((x-size*.5,x+size*.5,y-size*.5,y+size*.5))
        if i >= 24:
            gravel.append(obj)
    if gravel:
        gravel_seeds = [obj["recipe_seed"] for obj in gravel]
        bpy.ops.object.select_all(action="DESELECT")
        for obj in gravel:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = gravel[0]
        bpy.ops.object.join()
        gravel[0].name = "Modellierter_Kalkgrus"
        gravel[0]["modelled_grit_count"] = len(gravel)
        gravel[0]["recipe_seeds"] = gravel_seeds
        del gravel[0]["stone_piece"]


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
        taper = .45+.55*min(1, distance.get(j, 9)/3)
        clump = .0035*noise.noise(p*30)+.0008*noise.noise(p*155)
        verts.append(p+normals[i]*(.0004+taper*(thickness+clump)))
    verts.extend(mesh.vertices[i].co-normals[i]*.004 for i in used)
    n = len(used)
    faces = top_faces + [tuple(n+i for i in reversed(f)) for f in top_faces]
    for (a, b), count in edges.items():
        if count == 1:
            faces.append((a, b, b+n, a+n))
    obj = link_mesh(name, verts, faces, material)
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


def plant_terraces(body, mode):
    bpy.context.view_layer.update()
    material=grass_material()
    threshold=max(v.co.z for v in body.data.vertices)-.40 if mode=="pillar" else max(f.center.z for f in body.data.polygons if f.normal.z>.5)-.3
    turf=turf_shell(body,material,"Grasige_Terrassen",coverage=1.0,
                    thickness=.68 if mode=="pillar" else .12,min_height=threshold,
                    normal_z=-.12 if mode=="pillar" else .05)
    soil=vrmat.get("dirt_path").copy()
    soil.name=ASSET+"_Durchwurzelte_Kappenerde"
    soil_bsdf=soil.node_tree.nodes["Principled BSDF"]
    for link in list(soil_bsdf.inputs["Base Color"].links):
        soil.node_tree.links.remove(link)
    palette=vrmat.load_palette()
    soil_bsdf.inputs["Base Color"].default_value=tuple(.72*a+.28*b for a,b in zip(palette["soil"]["linear_rgb"],palette["path_sand"]["linear_rgb"]))+(1,)
    turf.data.materials.append(soil)
    for face in turf.data.polygons:
        if face.normal.z<.25:
            face.material_index=1
    turf["soil_mat_thickness_m"]=.68 if mode=="pillar" else .12
    bpy.context.view_layer.update()
    faces=[f for f in turf.data.polygons if f.normal.z>.30 and f.center.z>threshold]
    rng=random.Random(SEED+71)
    turf.data.calc_loop_triangles()
    triangles=[t for t in turf.data.loop_triangles if t.normal.z>.3
               and sum(turf.data.vertices[i].co.z for i in t.vertices)/3>threshold]
    points=[]
    for triangle in rng.choices(triangles,weights=[t.area for t in triangles],k=2600 if mode=="pillar" else 180):
        a,b,c=(turf.data.vertices[i].co for i in triangle.vertices)
        u,v=rng.random(),rng.random()
        if u+v>1:
            u,v=1-u,1-v
        points.append(turf.matrix_world@(a+(b-a)*u+(c-a)*v))
    grass_tufts(points,material,SEED+71)




def build():
    noise.seed_set(SEED)
    stone = support_material("Approved fault limestone", .5)
    fines_bed("Kalkgrus_Saum", (23,15), vrmat.get("dirt_path"), .018)
    rng = random.Random(SEED)
    columns = ((-20,-10.5,43),(-10.5,.5,45),(.5,9,41.5),(9,20,44))
    bases = []
    for column,(left,right,top) in enumerate(columns):
        bottom = -.04
        band = 0
        while bottom < top-.01:
            remaining = top-bottom
            height = min(rng.uniform(1.8,5.8),remaining)
            if 0 < remaining-height < 1.8:
                height = remaining if remaining <= 5.8 else remaining*.5
            retreat = .12*math.sin(band*2.1)
            group = min(2,int((bottom+height*.5)/top*3))
            block = approved_chunk("Wandkluft_%d_Bank_%02d"%(column,band),
                                    ((right-left)*1.50,21,top*.80),
                                    ((left+right)*.5,retreat,(group+.5)*top/3),
                                    SEED+column*100+group*13,stone,7)
            if column>0:
                fracture(block,(left+.012,0,0),(-1,0,0))
            if column<3:
                fracture(block,(right-.012,0,0),(1,0,0))
            fracture(block,(0,0,bottom),(0,0,-1))
            if bottom+height < top-.01:
                fracture(block,(0,0,bottom+height-.018),(0,0,1))
            else:
                fracture(block,((left+right)*.5,0,top),(.16,-.08,1))
            block["stratum"] = band
            block["slice_index"] = band
            block["joint_column"] = column
            block["stratum_height_m"] = height
            block["tile_pitch_m"] = 40.0
            block["landmark_mode"] = "wall"
            bases.append(block)
            bottom += height
            band += 1
    bpy.context.view_layer.update()
    lo,hi=vrlib.world_bounds(bases)
    factor=45/hi.z
    xfactor=40/(hi.x-lo.x)
    for block in bases:
        block.data.transform(Matrix.Diagonal((xfactor,1,factor,1)))
        block["stratum_height_m"] *= factor
    for column in range(4):
        roof=max((o for o in bases if o["joint_column"]==column),
                 key=lambda o:max(v.co.z for v in o.data.vertices))
        plant_terraces(roof,"wall")
    bpy.context.view_layer.update()
    ground_debris((22.8,14.8),bases,stone,900,SEED+900)
    bpy.context.scene["tile_pitch_m"] = 40.0
    bpy.context.scene["through_band_joints_x_m"] = [-10.5,.5,9]
    finish()
    bpy.context.scene["through_band_joints_x_m"] = [x*xfactor+bases[0].location.x
                                                  for x in (-10.5,.5,9)]

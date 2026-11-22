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
        colors = (("accent_ochre", .50), ("sandstone", .70)) if key == "sandstone" else (("moss", .65), ("moss", 1.05))
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
        if key=="mossy_rock":
            edge=nt.nodes.new("ShaderNodeAttribute")
            edge.attribute_name="moss_edge"
            tips=nt.nodes.new("ShaderNodeMixRGB")
            tips.inputs[2].default_value=tuple(v*1.15 for v in palette["moss"]["linear_rgb"])+(1,)
            nt.links.new(edge.outputs["Fac"],tips.inputs[0])
            nt.links.new(ramp.outputs[0],tips.inputs[1])
            nt.links.new(tips.outputs[0],bsdf.inputs["Base Color"])
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
    bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=.25, use_axis_x=True,
                          use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for v in bm.verts:
        p, n = v.co.copy(), v.normal.copy()
        grain=.0018*noise.noise(p*83)+.0006*noise.noise(p*173)
        phase=(p.z+.1*p.x+.04*p.y+.004*noise.noise(p*5))*12
        lamination=max(0,1-abs(phase-round(phase))/.18)
        lamination*=max(0,noise.noise(p*5+Vector((4,2,8)))+.2)
        sheltered=max(0,n.x,n.y)
        relief=0
        if sheltered>.4:
            for x,y,z in ((1.4,-.1,.52),(1.4,.55,.85),(.5,1.0,.65),(-.8,.9,1.05)):
                q=Vector(((p.x-x)/.33,(p.y-y)/.28,(p.z-z)/.24))
                relief=max(relief,.045*max(0,1-q.length_squared)**.65)
        cell=noise.noise(p*3.2)*3
        fraction=cell-math.floor(cell)
        transition=max(0,min(1,(fraction-.25)/.5))
        transition=transition*transition*(3-2*transition)
        meso=.012*(math.floor(cell)+transition)/3
        v.co+=n*((grain+meso-.002*lamination)*min(1,amplitude/.4)-relief)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(22))
    obj.data.update()
    bpy.context.view_layer.update()


def tafoni(body, rng, stone):
    tree = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    outward=Vector((1.02,.58,.1181)).normalized()
    tangent=Vector((-outward.y,outward.x,0)).normalized()
    cells=[]
    for i,(y,z) in enumerate(((-.1,.6),(.12,.65),(.25,.52),(.48,.65),(.28,.84),(.03,.9))):
        y+=rng.uniform(-.025,.025)
        z+=rng.uniform(-.025,.025)
        hit,normal,_,_=tree.ray_cast(Vector((4,y,z)),Vector((-1,0,0)))
        if hit is None or normal.dot(outward)<.8:
            continue
        cells.append((hit,rng.uniform(.17,.25),rng.uniform(.11,.18),rng.uniform(.11,.15),i))
    normals=[v.normal.copy() for v in body.data.vertices]
    for vertex,normal in zip(body.data.vertices,normals):
        p=vertex.co.copy()
        facing=max(0,min(1,(normal.dot(outward)-.7)/.2))
        if not facing:
            continue
        depth=0
        for centre,width,height,amplitude,index in cells:
            q=p-centre
            warp=.32*noise.noise(p*14+Vector((index*3,1,4)))
            radius=abs(q.dot(tangent)/width)**1.4+abs(q.z/height)**1.65
            bowl=max(0,1-radius+warp)
            depth=max(depth,amplitude*bowl**.7)
        vertex.co-=outward*depth*facing
    body.data.update()
    body["tafoni_cells"]=len(cells)


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
    candidates = [f for f in mesh.polygons if f.normal.z > .7 and f.center.z > .9 and f.center.y>-.35
                  and sum(normals[i].z for i in f.vertices)/len(f.vertices) > .7]
    if not candidates:
        raise RuntimeError("No upward north-side faces for moss")
    def field(p):
        return noise.noise(p*2.0 + Vector((3, 8, 1))) + .18*noise.noise(p*5)
    ranked = sorted(candidates, key=lambda f: field(f.center), reverse=True)
    target = sum(f.area for f in candidates)*.40
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
    for step in range(1, 9):
        frontier = {j for i in frontier for j in neighbors[i] if j not in distance}
        distance.update({i: step for i in frontier})
    verts = []
    for j, i in enumerate(used):
        v = mesh.vertices[i]
        p = v.co.copy()
        taper = min(1, distance.get(j, 9)/6)
        clump = .008*noise.noise(p*30)+.0015*noise.noise(p*155)
        verts.append(p+normals[i]*(.0004+taper*(.03+clump)))
    verts.extend(mesh.vertices[i].co-normals[i]*.004 for i in used)
    n = len(used)
    faces = top_faces + [tuple(n+i for i in reversed(f)) for f in top_faces]
    for (a, b), count in edges.items():
        if count == 1:
            faces.append((a, b, b+n, a+n))
    obj = link_mesh("Angewachsene_Moosschale", verts, faces, material)
    edge_attribute=obj.data.attributes.new("moss_edge","FLOAT","POINT")
    for j in range(len(verts)):
        edge_attribute.data[j].value=1-min(1,distance.get(j%n,9)/6)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    print("MOSS_SURFACE_COVERAGE", round(area/sum(f.area for f in candidates)*100, 1))


def prism(name, outline, bottom, top, material):
    n=len(outline)
    verts=[(x,y,z) for z in (bottom,top) for x,y in outline]
    faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return link_mesh(name,verts,faces,material)


def split_fragment(body, point, normal):
    fragment=body.copy()
    fragment.data=body.data.copy()
    fragment.name="Abgespaltener_Bruchblock"
    vrlib.link_to_source(fragment)
    for obj,direction in ((body,normal),(fragment,-normal)):
        bm=bmesh.new()
        bm.from_mesh(obj.data)
        cut_plane(bm,point,direction)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        obj["split_normal"]=tuple(normal)
    return fragment


def natural_fissures(body,stone):
    front=Vector((-.47,-1.75,.1242)).normalized()
    right=Vector((1.02,.58,.1181)).normalized()
    df=front.dot(Vector((-1.3,-.48,-.025)))
    dr=right.dot(Vector((1.45,-.12,-.025)))
    for i,(normal,distance,level) in enumerate(((front,df,.66),(right,dr,1.08))):
        tangent=Vector((-normal.y,normal.x,0))
        across=Vector((-.12,-.04,1)).normalized()
        horizontal=Vector((normal.x,normal.y,0))
        centre=horizontal*((distance-normal.z*level)/horizontal.length_squared)+Vector((0,0,level))
        cutter=tapered_wedge(f"Gebrochene_Schichtlippe_{i}",centre,tangent,across,normal,
                             -.85,.65,.05,.045,3+i*9,stone,bedding=True)
        subtract(body,cutter)
    for i,(normal,distance,offset) in enumerate(((front,df,.45),(right,dr,-.1))):
        tangent=Vector((-normal.y,normal.x,0))
        horizontal=Vector((normal.x,normal.y,0))
        centre=horizontal*((distance-normal.z)/horizontal.length_squared)+tangent*offset+Vector((0,0,1.0))
        along=(Vector((0,0,1))+tangent*(.17 if i==0 else -.22)).normalized()
        cutter=tapered_wedge(f"Auskeilende_Bruchkluft_{i}",centre,along,tangent,normal,
                             -.65,.6,.13,.035,17+i*13,stone)
        subtract(body,cutter)


def build():
    rng=random.Random(SEED)
    noise.seed_set(SEED)
    stone,moss=materials()
    outline=[(-1.3,-.48),(.45,-.95),(1.45,-.12),(.87,.9),(-.55,.8),(-1.38,.25)]
    body=prism("Sandstein_Hauptmasse",outline,-.025,2.05,stone)
    for vertex in body.data.vertices:
        if vertex.co.z>2:
            vertex.co.x=vertex.co.x*.88-.12
            vertex.co.y=vertex.co.y*.88+.08
    bm=bmesh.new()
    bm.from_mesh(body.data)
    cut_plane(bm,(0,0,1.86),Vector((-.12,.04,1)).normalized())
    cut_plane(bm,(-.5,0,1.75),Vector((-.5,-.15,1)).normalized())
    cut_plane(bm,(-.7,.6,1.65),Vector((-.3,.7,1)).normalized())
    for normal in (Vector((-.15,-1,.12)),Vector((-1,-.15,-.1)),Vector((-.6,.7,.3))):
        normal.normalize()
        support=max(normal.dot(v.co) for v in bm.verts)
        cut_plane(bm,normal*(support-.10),normal)
    bm.to_mesh(body.data)
    bm.free()
    notch=prism("Gebrochene_Dachstufe",[(-.1,-1.8),(2,-1.8),(2,1.8),(.25,1.8),(.05,.75),(.25,.35),(-.12,-.15),(.12,-.5)],1.35,3,stone)
    for vertex in notch.data.vertices:
        vertex.co.z+=.12*vertex.co.x+.04*vertex.co.y
    subtract(body,notch)
    block=split_fragment(body,Vector((.85,-.45,.35)),Vector((1,-1,-1.8)).normalized())
    bm=bmesh.new()
    bm.from_mesh(body.data)
    sites=[e.verts[0].co.lerp(e.verts[1].co,rng.uniform(.15,.85)) for e in bm.edges
           if e.calc_face_angle()>.45 and e.calc_length()>.4 and min(v.co.z for v in e.verts)>.8]
    bm.free()
    weather(body,.018,1)
    weather(block,.018,1)
    for site in rng.sample(sites,min(10,len(sites))):
        bm=bmesh.new()
        radius=rng.uniform(.06,.12)
        for _ in range(18):
            bm.verts.new(site+Vector(tuple(rng.uniform(-radius,radius) for _ in range(3))))
        bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
        bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context="VERTS")
        cutter=link_mesh("Kantenabplatzer",[],[],stone)
        bm.to_mesh(cutter.data)
        bm.free()
        subtract(body,cutter)
    bpy.context.view_layer.update()
    natural_fissures(body,stone)
    tafoni(body,rng,stone)
    for face in body.data.polygons:
        face.use_smooth=True
    body.data.set_sharp_from_angle(angle=math.radians(22))
    bpy.context.view_layer.update()
    moss_shell(body,moss)
    pivot=sum((v.co for v in block.data.vertices),Vector())/len(block.data.vertices)
    for v in block.data.vertices:
        v.co-=pivot
    block.location=pivot+Vector((.18,-.38,0))
    block.rotation_euler=(.25,-.45,-.18)
    bpy.context.view_layer.update()
    block.location.z+=-.04-min((block.matrix_world@v.co).z for v in block.data.vertices)
    block.select_set(True)
    bpy.context.view_layer.objects.active=block
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    block.select_set(False)
    bpy.context.view_layer.update()
    support=BVHTree.FromObject(block,bpy.context.evaluated_depsgraph_get())
    for i,size in enumerate((.42,.31,.12,.07,.24,.16,.36,.09,.19,.27,.11,.06,.22,.14)):
        points=[]
        for j in range(6):
            angle=math.tau*j/6+rng.uniform(-.23,.23)
            radius=size*rng.uniform(.35,.58)
            points.append((radius*math.cos(angle),radius*math.sin(angle)*rng.uniform(.4,.8)))
        shard=prism(f"Bruchsplitter_{i:02d}",points,-size*.14,size*rng.uniform(.22,.55),stone)
        bm=bmesh.new()
        bm.from_mesh(shard.data)
        cut_plane(bm,(0,0,size*.2),Vector((.4,-.2,1)).normalized())
        bm.to_mesh(shard.data)
        bm.free()
        weather(shard,max(.004,size*.035),size)
        shard.location=(rng.uniform(.05,1.45),rng.uniform(-1.5,-1.1),0)
        shard.rotation_euler=(rng.uniform(-.15,.15),rng.uniform(-.2,.2),rng.uniform(-math.pi,math.pi))
        bpy.context.view_layer.update()
        inverse=block.matrix_world.inverted()
        offset=-math.inf
        for vertex in shard.data.vertices:
            p=shard.matrix_world@vertex.co
            ray=inverse@Vector((p.x,p.y,3))
            hit=support.ray_cast(ray,Vector((0,0,-1)))[0]
            floor=(block.matrix_world@hit).z if hit is not None else -.025
            offset=max(offset,floor-p.z)
        shard.location.z+=offset-.003
    bpy.context.view_layer.update()
    lo,hi=vrlib.world_bounds(vrlib.source_objects())
    shift=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z+.025))
    for obj in vrlib.source_objects():
        obj.location-=shift
    vrlib.use_cycles_cpu(bpy.context.scene,32)

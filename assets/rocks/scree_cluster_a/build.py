"""Größengestufter Kalktalus auf geschlossenem Feinkieskeil."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector, noise
from mathutils.bvhtree import BVHTree

import vrlib
import vrmat

SEED=91553


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


def moss_shell(body, material, name="Angewachsene_Moosschale", coverage=.35, thickness=.03):
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
    target = sum(f.area for f in candidates)*coverage
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
        edge_attribute.data[j].value=1-min(1,distance.get(j%n,9)/6)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    print("MOSS_SURFACE_COVERAGE", round(area/sum(f.area for f in candidates)*100, 1))
    return obj


def fractured_rock(name, size, seed, material, cuts=7, split=False,
                    weathering=1.0, strata=.48, tafoni=False, fissures=False):
    if len(size)!=3 or min(size)<=0 or not 4<=cuts<=8:
        raise ValueError("Positive dimensions and 4-8 fracture planes required")
    rng=random.Random(seed)
    def smooth(value):
        t=max(0,min(1,value))
        return t*t*(3-2*t)
    def remesh(obj, spacing):
        bpy.context.view_layer.objects.active=obj
        mod=obj.modifiers.new("Dichte_Bruchoberflaeche","REMESH")
        mod.mode,mod.voxel_size="VOXEL",spacing
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=7 if max(size)>2 else 6,radius=1)
    body=bpy.context.object
    body.name=name
    vrlib.link_to_source(body)
    body.data.materials.append(material)
    for v in body.data.vertices:
        v.co=Vector(tuple(v.co[i]*size[i]*.5 for i in range(3)))
    bm=bmesh.new()
    bm.from_mesh(body.data)
    planes=[]
    fragment=None
    phase=rng.uniform(-math.pi,math.pi)
    for index in range(cuts):
        for _ in range(1000):
            angle=phase+index*math.tau/cuts+rng.uniform(-.4,.4)
            z=rng.uniform(-.65,.65)
            if index==cuts-2:
                z=rng.uniform(.85,1.3)
            if index==cuts-1:
                z=rng.uniform(-1.1,-.7) if not split else rng.uniform(.12,.4)
                if split:
                    angle=rng.uniform(-2.4,-.7)
            normal=Vector((math.cos(angle),math.sin(angle),z)).normalized()
            if min(abs(c) for c in normal)>.06 and all(.1<abs(normal.dot(n))<.98 for n,d in planes):
                break
        else:
            raise RuntimeError("Could not choose nonorthogonal fracture planes")
        support=max(normal.dot(v.co) for v in bm.verts)
        distance=support*rng.uniform(.58,.78)
        if split and index==cuts-1:
            cap=bm.copy()
            cut_plane(cap,normal*distance,-normal)
            fragment=link_mesh("Abgespaltener_Bruchblock",[],[],material)
            cap.to_mesh(fragment.data)
            cap.free()
        cut_plane(bm,normal*distance,normal)
        planes.append((normal,distance))
    bm.to_mesh(body.data)
    bm.free()
    low=Vector(tuple(min(v.co[i] for v in body.data.vertices) for i in range(3)))
    high=Vector(tuple(max(v.co[i] for v in body.data.vertices) for i in range(3)))
    fit=Vector(tuple(size[i]/(high[i]-low[i]) for i in range(3)))
    for obj in ([body,fragment] if split else [body]):
        for vertex in obj.data.vertices:
            vertex.co=Vector(tuple(vertex.co[i]*fit[i] for i in range(3)))
    spacing=max(.003,min(.022,max(size)/150))
    amplitude=min(.11,min(size)*.10)*weathering
    offset=Vector((seed*.013,seed*.007,seed*.019))
    for obj in ([body,fragment] if split else [body]):
        obj.data.update()
        remesh(obj,spacing)
        bm=bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        bmesh.ops.smooth_vert(bm,verts=list(bm.verts),factor=.16,
                              use_axis_x=True,use_axis_y=True,use_axis_z=True)
        for _ in range(3):
            bm.normal_update()
            upper=[v for v in bm.verts if v.co.z>size[2]*.20 and v.normal.z>.25]
            bmesh.ops.smooth_vert(bm,verts=upper,factor=.3,
                                  use_axis_x=True,use_axis_y=True,use_axis_z=True)
        bm.normal_update()
        for v in bm.verts:
            p,n=v.co.copy(),v.normal.copy()
            q=p/max(.08,min(.7,max(size)*.24))+offset
            distances,sites=noise.voronoi(q)
            weights=[math.exp(-(d-distances[0])/.035) for d in distances[:3]]
            cell=sum(w*(noise.cell(sites[i])*2-1) for i,w in enumerate(weights))/sum(weights)
            macro=amplitude*cell
            dip=p.z+.16*p.x-.075*p.y
            mid=.018*min(1,min(size)/.5)*noise.noise(Vector((p.x*10,p.y*10,dip*5))+offset)
            bed=(dip+.045*noise.noise(p*.8+offset))/strata
            fraction=bed-math.floor(bed)
            pinch=smooth((noise.noise(Vector((p.x*.7,p.y*.7,math.floor(bed))))+.35)*1.4)
            lip=(smooth(fraction/.07)-smooth((fraction-.20)/.12))
            band=min(.19,min(size)*.025)*lip*pinch*(1-abs(n.z))
            v.co+=n*(macro+mid+band)
        bm.to_mesh(obj.data)
        bm.free()
        remesh(obj,spacing*.8)
        bm=bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        lo=min(v.co.z for v in bm.verts)
        hi=max(v.co.z for v in bm.verts)
        shadow=Vector((1,-.25,.04)).normalized()
        tangent=Vector((.25,1,0)).normalized()
        for v in bm.verts:
            p,n=v.co.copy(),v.normal.copy()
            depth=.005*min(1,min(size)/.5)*noise.noise(p*65+offset)
            if tafoni and obj==body:
                h=(p.z-lo)/(hi-lo)
                mask=smooth((h-.18)/.10)*(1-smooth((h-.43)/.12))*smooth((n.dot(shadow)-.45)/.35)
                q=Vector((p.dot(tangent)/.23,(p.z+.025*noise.noise(p*9))/.18,1.7))+Vector((2.7,8.2,0))
                distances,sites=noise.voronoi(q)
                margin=min(((q-s).length_squared-(q-sites[0]).length_squared)/(2*(s-sites[0]).length)
                           for s in sites[1:])
                pocket=max(0,min(1,(margin-.045)/.28))
                depth-=.13*pocket*mask*(.65+.35*noise.cell(sites[0]))
            if fissures and obj==body:
                for index,outward in enumerate((Vector((.2,-1,.08)).normalized(),Vector((-.9,.35,.1)).normalized())):
                    t=Vector((-outward.y,outward.x,0)).normalized()
                    h=(p.z-lo)/(hi-lo)
                    window=smooth((h-.2)/.12)*(1-smooth((h-.82)/.12))
                    path=(-.26 if index==0 else .38)+.13*math.sin(p.z*4+index*2)+.035*noise.noise(p*9+offset)
                    width=.009+.012*math.sin(max(0,min(1,h))*math.pi)
                    trench=max(0,1-abs(p.dot(t)-path)/width)
                    depth-=.055*trench*window*smooth((n.dot(outward)-.65)/.25)
            v.co+=n*depth
        bm.normal_update()
        if obj==body:
            floor=min(v.co.z for v in bm.verts)+min(size[2]*.1,.25)
            cut_plane(bm,(0,0,floor),Vector((.025,-.035,-1)).normalized())
        pending=set(bm.verts)
        components=[]
        while pending:
            component=[pending.pop()]
            index=0
            while index<len(component):
                for edge in component[index].link_edges:
                    vertex=edge.other_vert(component[index])
                    if vertex in pending:
                        pending.remove(vertex)
                        component.append(vertex)
                index+=1
            components.append(component)
        largest=max(components,key=len)
        fragments=[v for component in components if component is not largest for v in component]
        obj["discarded_island_vertices"]=len(fragments)
        if fragments:
            bmesh.ops.delete(bm,geom=fragments,context="VERTS")
        base=min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z-=base+.035
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()
        for face in obj.data.polygons:
            face.use_smooth=True
        obj.data.set_sharp_from_angle(angle=math.radians(28))
        obj.data.update()
        obj["recipe_seed"]=seed
        obj["ico_subdivisions"]=7 if max(size)>2 else 6
        obj["fracture_planes"]=[tuple(n) for n,d in planes]
        obj["macro_amplitude_m"]=amplitude
        obj["strata_spacing_m"]=strata
        obj["tafoni_voronoi"]=tafoni and obj==body
        obj["fissure_count"]=2 if fissures and obj==body else 0
        if split:
            obj["split_normal"]=tuple(planes[-1][0])
    bpy.context.view_layer.update()
    return (body,fragment) if split else body


def fines_bed(name, radius, material, height=.16, slope=False):
    verts=[(0,0,1.5-.15*math.tan(math.radians(32))-.005 if slope else height)]
    count,rings=96,28
    for row in range(1,rings+1):
        r=row/rings
        for j in range(count):
            angle=math.tau*j/count
            irregular=1+.035*math.sin(angle*7)+.025*math.sin(angle*11+1)
            x,y=radius[0]*r*math.cos(angle)*irregular,radius[1]*r*math.sin(angle)*irregular
            z=height*(1-r**3)
            if slope:
                z=max(0,1.5-math.hypot(x,y-.15)*math.tan(math.radians(32)))
                z*=min(1,(1-r)/.06)
                z+=.035*noise.noise(Vector((x*2,y*2,4)))*(1-r*r)
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
    for face in obj.data.polygons:
        face.use_smooth=True
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


def chalk_material(seed, old=False):
    rng=random.Random(seed)
    palette=vrmat.load_palette()
    mat=vrmat.get("canyon_layered").copy()
    mat.name=f"Kalkbruch_{seed}"
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    tex=nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value=2.5
    tex.inputs["Detail"].default_value=3
    nt.links.new(coord.outputs["Object"],tex.inputs["Vector"])
    ramp=nt.nodes.new("ShaderNodeValToRGB")
    gain=rng.uniform(.50,.70)
    for el,key in zip(ramp.color_ramp.elements,("canyon_strata","canyon_chalk")):
        el.color=tuple(v*gain for v in palette[key]["linear_rgb"])+(1,)
    nt.links.new(tex.outputs["Fac"],ramp.inputs[0])
    color=ramp.outputs[0]
    if old:
        geo=nt.nodes.new("ShaderNodeNewGeometry")
        normal=nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"],normal.inputs[0])
        mix=nt.nodes.new("ShaderNodeMixRGB")
        nt.links.new(normal.outputs["Z"],mix.inputs[0])
        nt.links.new(color,mix.inputs[1])
        mix.inputs[2].default_value=tuple(v*.35 for v in palette["moss"]["linear_rgb"])+(1,)
        color=mix.outputs[0]
    ao=nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value=.15
    value=nt.nodes.new("ShaderNodeMath")
    value.operation="MULTIPLY_ADD"
    nt.links.new(ao.outputs["AO"],value.inputs[0])
    value.inputs[1].default_value=.3
    value.inputs[2].default_value=.7
    grime=nt.nodes.new("ShaderNodeMixRGB")
    grime.blend_type="MULTIPLY"
    grime.inputs[0].default_value=1
    nt.links.new(color,grime.inputs[1])
    nt.links.new(value.outputs[0],grime.inputs[2])
    nt.links.new(grime.outputs[0],bsdf.inputs["Base Color"])
    fine=nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value=85
    nt.links.new(coord.outputs["Object"],fine.inputs["Vector"])
    bump=nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value=.003
    bump.inputs["Strength"].default_value=.3
    nt.links.new(fine.outputs["Fac"],bump.inputs["Height"])
    nt.links.new(bump.outputs[0],bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value=.96
    return mat


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



def build():
    rng=random.Random(SEED)
    noise.seed_set(SEED)
    soil=vrmat.get("dirt_path").copy()
    soil.name="scree_cluster_a_Kalkiger_Feinkies"
    bed=fines_bed("Talus_Feinkieskeil",(3.0,2.45),soil,height=1.0,slope=True)
    materials=[chalk_material(SEED+i,old=i%7==0) for i in range(16)]
    occupied=[]
    for i in range(64):
        if i<8:
            row,column=divmod(i,4)
            y=-1.65+row*.75+rng.uniform(-.12,.12)
            x=(column-1.5)*1.23+rng.uniform(-.12,.12)
            size=rng.uniform(1.0,1.4)
            group="Gross"
        else:
            rank=(i-8)/55
            y=-.65+rank*1.4+rng.uniform(-.18,.18)
            width=2.45*(1-rank)+.6*rank
            x=rng.uniform(-width,width)
            size=(.72-.52*rank)*rng.uniform(.75,1.15)
            group="Fein" if rank>.6 else "Mittel"
        rock=fractured_rock(f"{group}_{i:02d}",(size,size*rng.uniform(.48,.8),size*rng.uniform(.25,.5)),SEED+100+i,materials[i%16],cuts=8,weathering=.6 if i%11==0 else .20,strata=max(.08,size*.2))
        rock["size_class"]=group
        rock["talus_rank"]=i
        radius=size*.36
        for attempt in range(30):
            if all((Vector((x,y))-centre).length>(radius+other)*.85 for centre,other in occupied):
                break
            x+=rng.uniform(-.2,.2)
            y+=rng.uniform(-.12,.12)
            x=max(-2.55,min(2.55,x))
            y=max(-1.9,min(1.55,y))
        rock.location=(x,y,0)
        distance=max(.1,math.hypot(x,y-.15))
        normal=Vector((math.tan(math.radians(32))*x/distance,
                       math.tan(math.radians(32))*(y-.15)/distance,1)).normalized()
        align=Vector((0,0,1)).rotation_difference(normal)
        rock.rotation_euler=(align@Quaternion((0,0,1),rng.uniform(-math.pi,math.pi))
                             @Quaternion((1,0,0),rng.uniform(-.15,.15))).to_euler()
        seat_on_bed(rock,bed,min(.09,size*.12))
        occupied.append((Vector((x,y)),radius))
    bpy.context.view_layer.update()
    tree=BVHTree.FromObject(bed,bpy.context.evaluated_depsgraph_get())
    points=[]
    for angle in (.1,.6,1.2,1.9,2.6,3.3,4.1,4.8,5.5):
        hit=tree.ray_cast(Vector((2.8*math.cos(angle),2.25*math.sin(angle),4)),Vector((0,0,-1)))[0]
        if hit is not None:
            points.append(hit)
    grass_tufts(points,vrmat.get("grass_ground"),SEED)
    bpy.context.scene["talus_angle_degrees"]=32
    bpy.context.scene["placement_mode"]="size-graded fragments seated in modelled fines"
    rotation=Matrix.Rotation(math.radians(110),4,"Z")
    bpy.context.scene["fall_line_world"]=tuple(rotation.to_3x3()@Vector((0,-1,0)))
    for obj in vrlib.source_objects():
        obj.matrix_world=rotation@obj.matrix_world
        bpy.context.view_layer.objects.active=obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
        obj.select_set(False)
    bpy.context.view_layer.update()
    lo,hi=vrlib.world_bounds(vrlib.source_objects())
    shift=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,0))
    for obj in vrlib.source_objects():
        obj.location-=shift
    vrlib.use_cycles_cpu(bpy.context.scene,32)

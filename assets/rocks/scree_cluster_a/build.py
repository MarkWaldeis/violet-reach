"""Kantiger Kalkschuttfächer aus physikalisch gesetzten Bruchstücken."""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat

SEED = 62951


def materials():
    palette = vrmat.load_palette()
    result = []
    for i, gain in enumerate((.68, .84, .95, .78, 1.0, .72, .88)):
        mat = vrmat.get("canyon_layered").copy()
        mat.name = f"scree_cluster_a_Kalkton_{i}"
        # Local variants: warm chalk/strata/ochre beds, reduced anisotropy and fine pores.
        for node in mat.node_tree.nodes:
            if node.type == "VECT_MATH" and node.operation == "MULTIPLY":
                if tuple(round(v, 1) for v in node.inputs[1].default_value) == (1.6, 1.6, 18):
                    node.inputs[1].default_value = (3, 3, 5)
            if node.type == "BUMP":
                node.inputs["Distance"].default_value = .004
        nt = mat.node_tree
        colour = nt.nodes["Principled BSDF"].inputs["Base Color"]
        source = colour.links[0].from_socket
        lift = nt.nodes.new("ShaderNodeMixRGB")
        lift.inputs[0].default_value = .72
        chalk = palette["canyon_chalk"]["linear_rgb"]
        strata = palette["canyon_strata"]["linear_rgb"]
        ochre = palette["accent_ochre"]["linear_rgb"]
        warm = (.1,.25,.12,.42,.04,.58,.30)[i]
        lift.inputs[2].default_value = tuple(
            (v*(1-warm)+strata[j]*warm*.8+ochre[j]*warm*.2)*gain for j,v in enumerate(chalk))+(1,)
        nt.links.new(source,lift.inputs[1])
        coord=nt.nodes.new("ShaderNodeTexCoord")
        wave=nt.nodes.new("ShaderNodeTexWave")
        wave.bands_direction="Z"
        wave.inputs["Scale"].default_value=2.2
        wave.inputs["Distortion"].default_value=.7
        nt.links.new(coord.outputs["Object"],wave.inputs["Vector"])
        bands=nt.nodes.new("ShaderNodeValToRGB")
        bands.color_ramp.elements[0].color=(.74,.66,.52,1)
        bands.color_ramp.elements[1].color=(1.04,1.01,.95,1)
        nt.links.new(wave.outputs["Fac"],bands.inputs[0])
        tint=nt.nodes.new("ShaderNodeMixRGB")
        tint.blend_type="MULTIPLY"
        tint.inputs[0].default_value=.65 if i%3==0 else .22
        nt.links.new(lift.outputs[0],tint.inputs[1])
        nt.links.new(bands.outputs[0],tint.inputs[2])
        geometry=nt.nodes.new("ShaderNodeNewGeometry")
        normal=nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geometry.outputs["Normal"],normal.inputs[0])
        shade=nt.nodes.new("ShaderNodeMapRange")
        shade.inputs["From Min"].default_value=-.7
        shade.inputs["From Max"].default_value=.25
        shade.inputs["To Min"].default_value=.55
        shade.inputs["To Max"].default_value=1
        nt.links.new(normal.outputs["Z"],shade.inputs["Value"])
        underside=nt.nodes.new("ShaderNodeMixRGB")
        underside.blend_type="MULTIPLY"
        underside.inputs[0].default_value=1
        nt.links.new(tint.outputs[0],underside.inputs[1])
        nt.links.new(shade.outputs["Result"],underside.inputs[2])
        position=nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geometry.outputs["Position"],position.inputs[0])
        soil_height=nt.nodes.new("ShaderNodeMapRange")
        soil_height.inputs["From Min"].default_value=.04
        soil_height.inputs["From Max"].default_value=.45
        soil_height.inputs["To Min"].default_value=.32
        soil_height.inputs["To Max"].default_value=0
        nt.links.new(position.outputs["Z"],soil_height.inputs["Value"])
        soil_facing=nt.nodes.new("ShaderNodeMapRange")
        soil_facing.inputs["From Min"].default_value=-.7
        soil_facing.inputs["From Max"].default_value=.7
        soil_facing.inputs["To Min"].default_value=1
        soil_facing.inputs["To Max"].default_value=.08
        nt.links.new(normal.outputs["Z"],soil_facing.inputs["Value"])
        soil_mask=nt.nodes.new("ShaderNodeMath")
        soil_mask.operation="MULTIPLY"
        nt.links.new(soil_height.outputs["Result"],soil_mask.inputs[0])
        nt.links.new(soil_facing.outputs["Result"],soil_mask.inputs[1])
        soil=nt.nodes.new("ShaderNodeMixRGB")
        soil.inputs[2].default_value=(.11,.07,.035,1)
        nt.links.new(soil_mask.outputs[0],soil.inputs[0])
        nt.links.new(underside.outputs[0],soil.inputs[1])
        nt.links.new(soil.outputs[0],colour)
        result.append(mat)
    return result


def cut(bm, point, normal):
    result = bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                                  plane_co=point,plane_no=normal,clear_outer=True,dist=.000001)
    edges = [e for e in result["geom_cut"] if isinstance(e,bmesh.types.BMEdge) and e.is_boundary]
    if edges:
        bmesh.ops.holes_fill(bm,edges=edges)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))


def piece(name, size, rng, tones, bedded=False):
    bm = bmesh.new()
    for _ in range(30):
        z = rng.uniform(-1,1)
        a = rng.uniform(0,math.tau)
        r = rng.uniform(.8,1.15)
        bm.verts.new((math.sqrt(1-z*z)*math.cos(a)*r,
                      math.sqrt(1-z*z)*math.sin(a)*r,z*r))
    bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context="VERTS")
    for axis, width in enumerate(size):
        lo,hi = min(v.co[axis] for v in bm.verts),max(v.co[axis] for v in bm.verts)
        for v in bm.verts:
            v.co[axis] = ((v.co[axis]-lo)/(hi-lo)-.5)*width
    for normal in (Vector((.12,-1,.08)),Vector((1,.17,.09)),Vector((-.14,.08,1))):
        support = max(normal.dot(v.co) for v in bm.verts)
        cut(bm,normal*(support*.77/normal.length_squared),normal)
    plane_count=rng.randint(32,44) if bedded else rng.randint(22,32) if name.startswith("Mittel") else rng.randint(5,8)
    for _ in range(plane_count-3):
        vertex = rng.choice(list(bm.verts))
        normal = (vertex.co+Vector((rng.uniform(-.08,.08)*size[0],
                                  rng.uniform(-.08,.08)*size[1],0))).normalized()
        support = max(normal.dot(v.co) for v in bm.verts)
        cut(bm,normal*(support-min(size)*rng.uniform(.025,.085)),normal)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    for axis, width in enumerate(size):
        lo,hi = min(v.co[axis] for v in bm.verts),max(v.co[axis] for v in bm.verts)
        for v in bm.verts:
            v.co[axis] = ((v.co[axis]-lo)/(hi-lo)-.5)*width
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name,mesh)
    vrlib.link_to_source(obj)
    tone = rng.randrange(len(tones))
    mesh.materials.append(tones[tone])
    obj["size_class"] = "large" if bedded else "medium" if name.startswith("Mittel") else "small"
    obj["nominal_size_m"] = max(size)
    obj["cut_planes"]=plane_count
    return obj


def fracture_detail(obj, neighbors):
    s=obj["nominal_size_m"]
    target=s*(.027 if obj["size_class"]!="small" else .095)
    coarse=obj.data
    vertices=[v.co.copy() for v in coarse.vertices]
    offsets=[Vector() for _ in vertices]
    phase=sum((i+1)*ord(c) for i,c in enumerate(obj.name))*.017
    seed=Vector((math.sin(phase)*3,math.cos(phase)*5,phase%7))
    edge_normals={}
    for face in coarse.polygons:
        ids=list(face.vertices)
        for a,b in zip(ids,ids[1:]+ids[:1]):
            edge_normals.setdefault(tuple(sorted((a,b))),[]).append(face.normal.copy())
    normals={key:sum(values,Vector()).normalized() for key,values in edge_normals.items()}

    def edge_chip(p,t,normal):
        envelope=max(0,math.sin(math.pi*t))**.65
        flake=max(0,noise.noise(p/s*29+seed)+.24)
        return -normal*(s*.022*flake*envelope)

    edges={}
    for edge in coarse.edges:
        a,b=sorted(edge.vertices)
        start,end=vertices[a],vertices[b]
        count=max(1,math.ceil((end-start).length/target))
        ids=[a]
        for j in range(1,count):
            t=j/count
            p=start.lerp(end,t)
            ids.append(len(vertices))
            vertices.append(p)
            offsets.append(edge_chip(p,t,normals[a,b]))
        ids.append(b)
        edges[a,b]=ids
    faces=[]
    broad_faces=0
    secondary_fractures=0
    for face in coarse.polygons:
        original=list(face.vertices)
        origin=vertices[original[0]]
        u=(vertices[original[1]]-origin).normalized()
        v=face.normal.cross(u).normalized()
        polygon=[Vector(((vertices[i]-origin).dot(u),(vertices[i]-origin).dot(v))) for i in original]
        boundary=[]
        for a,b in zip(original,original[1:]+original[:1]):
            ids=edges[tuple(sorted((a,b)))]
            boundary.extend((ids if a<b else list(reversed(ids)))[:-1])
        points=[Vector(((vertices[i]-origin).dot(u),(vertices[i]-origin).dot(v))) for i in boundary]
        mapping=boundary.copy()
        boundary_count=len(points)
        segments=list(zip(polygon,polygon[1:]+polygon[:1]))
        scoops=[]
        if face.area>.15:
            broad_faces+=1
            rng=random.Random(SEED+int(phase*1000)+face.index*7919)
            for _ in range(max(2,math.ceil(face.area/.065))):
                for _ in range(80):
                    q=Vector((rng.uniform(min(p.x for p in polygon),max(p.x for p in polygon)),
                              rng.uniform(min(p.y for p in polygon),max(p.y for p in polygon))))
                    if all((b-a).cross(q-a)>0 for a,b in segments):
                        scoops.append((q,rng.uniform(.10,.22),rng.uniform(.08,.17),rng.uniform(-math.pi,math.pi)))
                        break
            secondary_fractures+=len(scoops)

        def interior_offset(p):
            best=None
            for a,b in zip(original,original[1:]+original[:1]):
                start,end=vertices[a],vertices[b]
                direction=end-start
                t=max(0,min(1,(p-start).dot(direction)/direction.length_squared))
                q=start+direction*t
                distance=(p-q).length
                if best is None or distance<best[0]:
                    best=distance,q,t,normals[tuple(sorted((a,b)))]
            distance,q,t,normal=best
            edge_offset=edge_chip(q,t,normal)*max(0,1-distance/(target*1.5))
            pscale=p/s
            site=noise.voronoi(pscale*6+seed)[1][0]
            broad=max(0,noise.cell(site)+.4)
            steps=(math.floor((noise.noise(pscale*19+seed)+1)*5))/5
            centre=Vector((math.sin(phase)*.4,math.cos(phase*1.3)*.3,math.sin(phase*.7)*.2))
            ripple=max(0,math.sin((pscale-centre).length*45+noise.noise(pscale*4)*2))**3
            ripple*=max(0,noise.noise(pscale*7+seed)+.15)
            fine=max(0,noise.noise(pscale*97+seed))
            depth=s*(.006*broad+.005*steps+.003*ripple+.001*fine)
            local=Vector(((p-origin).dot(u),(p-origin).dot(v)))
            fracture=0
            for centre,rx,ry,angle in scoops:
                delta=local-centre
                x=(delta.x*math.cos(angle)+delta.y*math.sin(angle))/rx
                y=(-delta.x*math.sin(angle)+delta.y*math.cos(angle))/ry
                radius=math.sqrt(x*x+y*y)
                bowl=max(0,1-radius*radius)
                lip=math.floor(bowl*5)/5
                fracture=max(fracture,min(.045,s*.035)*(.72*bowl**.65+.28*lip))
            return edge_offset-face.normal*((depth+fracture)*min(1,distance/(target*2)))

        y=min(p.y for p in polygon)+target*.4
        row=0
        while y<max(p.y for p in polygon):
            x=min(p.x for p in polygon)+target*(.35+.5*(row%2))
            while x<max(p.x for p in polygon):
                q=Vector((x,y))
                if all((b-a).cross(q-a)/(b-a).length>target*.32 for a,b in segments):
                    p=origin+u*x+v*y
                    points.append(q)
                    mapping.append(len(vertices))
                    vertices.append(p)
                    offsets.append(interior_offset(p))
                x+=target
            y+=target*math.sqrt(3)/2
            row+=1
        result=delaunay_2d_cdt(points,[],[list(range(boundary_count))],1,s*1e-8,True)
        remap=[]
        for q,ids in zip(result[0],result[3]):
            if ids:
                remap.append(mapping[ids[0]])
            else:
                p=origin+u*q.x+v*q.y
                remap.append(len(vertices))
                vertices.append(p)
                offsets.append(interior_offset(p))
        faces.extend(tuple(remap[i] for i in f) for f in result[2])
    inverse=obj.matrix_world.inverted()
    verts,neighbor_faces=[],[]
    for other in neighbors:
        offset=len(verts)
        verts.extend(inverse@(other.matrix_world@v.co) for v in other.data.vertices)
        neighbor_faces.extend(tuple(offset+i for i in f.vertices) for f in other.data.polygons)
    tree=BVHTree.FromPolygons(verts,neighbor_faces) if neighbor_faces else None
    for i,p in enumerate(vertices):
        world=obj.matrix_world@p
        if world.z<.02:
            continue
        if tree:
            _,_,_,distance=tree.find_nearest(p)
            if distance is not None and distance<max(.016,target*1.5):
                continue
        offset=offsets[i]
        limit=1.0
        for face in coarse.polygons:
            movement=face.normal.dot(offset)
            if movement>1e-9:
                clearance=face.normal.dot(coarse.vertices[face.vertices[0]].co-p)
                limit=min(limit,max(0,clearance)/movement)
        vertices[i]=p+offset*min(1,limit)
    mesh=bpy.data.meshes.new(obj.name+"_Bruchrelief")
    mesh.from_pydata(vertices,[],faces)
    for material in coarse.materials:
        mesh.materials.append(material)
    obj.data=mesh
    bpy.data.meshes.remove(coarse)
    bm=bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    for f in bm.faces:
        f.smooth=True
        f.material_index=0
    for e in bm.edges:
        e.smooth=e.is_manifold and e.calc_face_angle()<math.radians(30)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    obj["broad_faces_detailed"]=broad_faces
    obj["secondary_fractures"]=secondary_fractures


def detail_pile(objects):
    bounds=[]
    for obj in objects:
        world=[obj.matrix_world@v.co for v in obj.data.vertices]
        bounds.append((Vector(tuple(min(p[i] for p in world) for i in range(3))),
                       Vector(tuple(max(p[i] for p in world) for i in range(3)))))
    copies=[]
    for obj in objects:
        obj["collision_vertices"]=[coordinate for v in obj.data.vertices for coordinate in v.co]
        copy=obj.copy()
        copy.data=obj.data.copy()
        copies.append(copy)
    for i,obj in enumerate(objects):
        neighbors=[copies[j] for j in range(len(objects)) if j!=i and all(
            bounds[i][0][k]<bounds[j][1][k]+.04 and bounds[j][0][k]<bounds[i][1][k]+.04
            for k in range(3))]
        fracture_detail(obj,neighbors)
    for copy in copies:
        mesh=copy.data
        bpy.data.objects.remove(copy)
        bpy.data.meshes.remove(mesh)


def power_size(rng, low, high, exponent=2.2):
    p=1-exponent
    return (low**p+rng.random()*(high**p-low**p))**(1/p)


def settle(objects):
    placed=[]
    up,down=Vector((0,0,1)),Vector((0,0,-1))

    def geometry(obj):
        points=[obj.matrix_world@v.co for v in obj.data.vertices]
        values=np.array([tuple(p) for p in points])
        edges=np.array([e.vertices[:] for e in obj.data.edges])
        return points,values,edges,BVHTree.FromPolygons(points,[f.vertices[:] for f in obj.data.polygons])

    def cross(a,b):
        return a[...,0]*b[...,1]-a[...,1]*b[...,0]

    order=objects[:4]+objects[80:160]+objects[4:80]+objects[160:]
    for index,obj in enumerate(order):
        if index<3:
            obj.rotation_euler=obj["crest_rotation"]
        else:
            base=max((f for f in obj.data.polygons if f.normal.z<-.4),key=lambda f:f.area)
            rotation=base.normal.rotation_difference(down).to_matrix().to_4x4()
            obj.rotation_euler=(Matrix.Rotation(obj.rotation_euler.z,4,"Z")@rotation).to_euler()
        obj.location.z=0
        bpy.context.view_layer.update()
        points,local,edges,tree=geometry(obj)
        origin=obj.location.copy()
        local-=np.array(tuple(origin))
        shape_height=np.ptp(local[:,2])
        for attempt in range(512):
            radius=.20*math.sqrt(attempt)
            x=origin.x+radius*math.cos(attempt*2.39996)
            y=origin.y+radius*math.sin(attempt*2.39996)-radius*.3
            if index<3:
                x,y=origin.x,origin.y
                if placed:
                    x+=max(0,max(p[1][:,0].max() for p in placed)+.04-(local[:,0].min()+x))
            current=local+np.array((x,y,0))
            lo,hi=current.min(axis=0),current.max(axis=0)
            if index>=3 and (lo[0]<-3.2 or hi[0]>3.2 or lo[1]<-3.2 or hi[1]>1.8):
                continue
            height=.001-lo[2]
            for other,values,other_edges,other_tree in placed:
                olo,ohi=values.min(axis=0),values.max(axis=0)
                if np.any(lo[:2]>ohi[:2]) or np.any(olo[:2]>hi[:2]):
                    continue
                for p in current:
                    hit=other_tree.ray_cast(Vector((p[0],p[1],ohi[2]+1)),down)[0]
                    if hit is not None:
                        height=max(height,hit.z-p[2]+.002)
                shift=Vector((origin.x-x,origin.y-y,0))
                for p in other:
                    hit=tree.ray_cast(Vector((p.x,p.y,lo[2]-1))+shift,up)[0]
                    if hit is not None:
                        height=max(height,p.z-hit.z+.002)
                a=values[other_edges[:,0]][:,None,:]
                r=(values[other_edges[:,1]]-values[other_edges[:,0]])[:,None,:]
                b=current[edges[:,0]][None,:,:]
                s=(current[edges[:,1]]-current[edges[:,0]])[None,:,:]
                denominator=cross(r,s)
                valid=abs(denominator)>1e-10
                safe=np.where(valid,denominator,1)
                t,u=cross(b-a,s)/safe,cross(b-a,r)/safe
                valid&=(t>=0)&(t<=1)&(u>=0)&(u<=1)
                if valid.any():
                    z=a[...,2]+t*r[...,2]-b[...,2]-u*s[...,2]
                    height=max(height,float(z[valid].max())+.002)
            ceiling=max(shape_height+.025,1.48-.25*max(0,.4-y)-.1*abs(x+.2))
            if index<3 or height+hi[2]<=ceiling:
                obj.location=(x,y,height)
                break
        else:
            raise RuntimeError(f"No supported position for {obj.name}")
        bpy.context.view_layer.update()
        placed.append(geometry(obj))
    bpy.context.scene["placement_mode"]="analytical convex gravity contacts"
    bpy.context.view_layer.update()


def build():
    rng=random.Random(SEED)
    noise.seed_set(SEED)
    tones=materials()
    objects=[]
    slabs=(((1.95,1.15,.52),(-1.1,.85,1.8)),
           ((1.75,1.0,.44),(.2,.95,3.3)),
           ((1.5,.9,.4),(1.35,.75,4.5)),
           ((1.4,1.0,.55),(-1.3,-.3,2.1)))
    for i,(size,location) in enumerate(slabs):
        obj=piece(f"Grossblock_{i:02d}",size,rng,tones,True)
        obj.location=location
        obj.rotation_euler=(rng.uniform(-.4,.4),rng.uniform(-.35,.35),rng.uniform(-math.pi,math.pi))
        if i<3:
            obj["crest_rotation"]=(.08*(i-1),math.radians((68,-64,-58)[i]),math.radians((-12,9,-8)[i]))
        objects.append(obj)
    for i in range(76):
        s=power_size(rng,.35,1)
        obj=piece(f"Mittelbruch_{i:02d}",(s,s*rng.uniform(.58,.95),s*rng.uniform(.4,.78)),rng,tones)
        a=rng.uniform(-math.pi,.1)
        r=rng.uniform(.35,1.55)
        obj.location=(math.cos(a)*r,.45+math.sin(a)*r,2.5+i*.13)
        if i<30:
            obj.location.x=-1.15+(i%10)*.27
            obj.location.y=.15+(i//10)*.28
        obj.rotation_euler=tuple(rng.uniform(-math.pi,math.pi) for _ in range(3))
        objects.append(obj)
    for i in range(240):
        s=power_size(rng,.12,.3)
        obj=piece(f"Kleinbruch_{i:03d}",(s,s*rng.uniform(.5,.95),s*rng.uniform(.35,.8)),rng,tones)
        a=rng.uniform(-math.pi+.08,-.08)
        r=(1.9*rng.random()**.85) if i<185 else rng.uniform(1.8,3.0)
        obj.location=(math.cos(a)*r,.45+math.sin(a)*r,2+i*.055)
        if i<60:
            obj.location.x=-1.15+(i%15)*.19
            obj.location.y=.45+(i//15)*.18
        obj.rotation_euler=tuple(rng.uniform(-math.pi,math.pi) for _ in range(3))
        objects.append(obj)
    settle(objects)
    detail_pile(objects)
    lo,hi=vrlib.world_bounds(objects)
    assert lo.z>-.08 and hi.z<3 and max(hi.x-lo.x,hi.y-lo.y)<9, (lo,hi)
    shift=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z+.012))
    for obj in objects:
        obj.location-=shift
    bpy.context.view_layer.update()
    vrlib.use_cycles_cpu(bpy.context.scene,32)

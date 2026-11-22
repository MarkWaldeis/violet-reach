"""Driftward: two fault-separated limestone tables and their detached shelves."""
import math
import random

import bpy
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat


def mesh(name, verts, faces, materials, indices=None, smooth_from=None):
    data=bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces)
    data.update()
    for mat in materials:
        data.materials.append(vrmat.get(mat) if isinstance(mat,str) else mat)
    for face in data.polygons:
        if indices:
            face.material_index=indices[face.index]
        face.use_smooth=smooth_from is not None and face.index>=smooth_from
    return vrlib.link_to_source(bpy.data.objects.new(name,data))


def terrain_finish():
    mat=vrmat.get("grass_ground").copy()
    mat.name="Driftward / turf, dry grass, exposed earth"
    nt=mat.node_tree
    nodes,links=nt.nodes,nt.links
    bsdf=nodes["Principled BSDF"]
    for attr,color in (("dryness",(.28,.239,.087,1)),("bare",(.145,.091,.045,1))):
        a=nodes.new("ShaderNodeAttribute")
        a.attribute_name=attr
        mix=nodes.new("ShaderNodeMixRGB")
        mix.inputs[2].default_value=color
        links.new(a.outputs["Fac"],mix.inputs[0])
        links.new(bsdf.inputs["Base Color"].links[0].from_socket,mix.inputs[1])
        links.new(mix.outputs[0],bsdf.inputs["Base Color"])
    return mat


def bedding_finish():
    mat=vrmat.get("canyon_layered").copy()
    mat.name="Driftward / subdued limestone bedding"
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    socket=nodes["Principled BSDF"].inputs["Base Color"]
    mix=nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value=.66
    coords=nodes.new("ShaderNodeTexCoord")
    noise=nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value=.35
    noise.inputs["Detail"].default_value=6
    links.new(coords.outputs["Object"],noise.inputs["Vector"])
    ramp=nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position=.23
    ramp.color_ramp.elements[0].color=(.23,.208,.172,1)
    ramp.color_ramp.elements[1].position=.8
    ramp.color_ramp.elements[1].color=(*vrmat.load_palette()["canyon_chalk"]["linear_rgb"],1)
    links.new(noise.outputs["Fac"],ramp.inputs[0])
    links.new(ramp.outputs["Color"],mix.inputs[2])
    links.new(socket.links[0].from_socket,mix.inputs[1])
    cavity=nodes.new("ShaderNodeAmbientOcclusion")
    cavity.inputs["Distance"].default_value=2.2
    cavity.samples=8
    shade=nodes.new("ShaderNodeMixRGB")
    shade.blend_type="MULTIPLY"
    shade.inputs[0].default_value=.42
    links.new(mix.outputs[0],shade.inputs[1])
    links.new(cavity.outputs["AO"],shade.inputs[2])
    links.new(shade.outputs[0],socket)
    normal=nodes["Principled BSDF"].inputs["Normal"]
    relief=nodes.new("ShaderNodeBump")
    relief.inputs["Strength"].default_value=.64
    relief.inputs["Distance"].default_value=.46
    links.new(noise.outputs["Fac"],relief.inputs["Height"])
    links.new(normal.links[0].from_socket,relief.inputs["Normal"])
    links.new(relief.outputs["Normal"],normal)
    return mat


def perimeter(polygon,spacing,rng):
    result=[]
    for i,p in enumerate(polygon):
        a,b=Vector(p),Vector(polygon[(i+1)%len(polygon)])
        d=b-a
        normal=Vector((d.y,-d.x)).normalized()
        count=max(2,math.ceil(d.length/spacing))
        crack=rng.randrange(1,count) if count>3 else -1
        for k in range(count):
            f=k/count
            notch=(-rng.uniform(2.2,5.8) if k==crack else rng.uniform(-.8,1.05)) if k else 0
            result.append(a.lerp(b,f)+normal*notch*min(1,spacing*.44))
    return result


def summit(x,y,h):
    return h+4.2*math.sin(.037*x-.027*y)+2.8*math.cos(.088*y+.029*x)+1.2*math.sin(.12*x+.076*y)


def add_turf(verts,faces,indices,dry,bare,n,center,bottom,top,rng):
    start=len(verts)-n
    boundary=[Vector((x,y)) for x,y,_ in verts[start:]]
    samples=list(boundary)
    x_min=math.floor(min(p.x for p in boundary))
    x_max=math.ceil(max(p.x for p in boundary))
    y_min=math.floor(min(p.y for p in boundary))
    y_max=math.ceil(max(p.y for p in boundary))
    for x in range(x_min+2,x_max,3):
        for y in range(y_min+2,y_max,3):
            samples.append(Vector((x+rng.uniform(-.77,.77),y+rng.uniform(-.77,.77))))
    coords,_,tris,original,_,_=delaunay_2d_cdt(samples,[],[list(range(n))],1,1e-5)
    index=[]
    for p,inputs in zip(coords,original):
        boundary_point=next((i for i in inputs if i<n),None)
        if boundary_point is not None:
            index.append(start+boundary_point)
            continue
        index.append(len(verts))
        x,y=p+center
        verts.append((p.x,p.y,summit(x,y,top)-bottom))
        distance=min((p-q).length for q in boundary)
        dri=.56+.30*math.sin(x*.051+y*.093)+.41*math.sin(x*.12+y*.031)*math.cos(y*.14)
        dry.append(min(1,max(0,(dri-.31)*2.05)))
        ash=.56+.24*math.sin(x*.27+y*.04)+.21*math.sin(y*.31+x*.084)
        bare.append(.91*max(0,1-distance/(2.1+max(.1,ash)*5.2)))
    for tri in tris:
        a,b,c=(coords[i] for i in tri)
        face=tuple(index[i] for i in tri)
        if (b-a).cross(c-a)<0:
            face=tuple(reversed(face))
        faces.append(face)
        indices.append(2)


def table(name,polygon,bottom,top,ledge,drift,materials,rng,cap=True,spacing=2.5,tilt=None):
    center=sum((Vector(p) for p in polygon),Vector((0,0)))/len(polygon)
    boundary=perimeter(polygon,spacing,rng)
    n=len(boundary)
    if cap:
        levels=((0,ledge),( .026,ledge*1.12),(.081,ledge*1.13),(.123,ledge*1.32),
                (.151,ledge*1.28),(.183,ledge*1.43),(.249,ledge*1.56),(.268,ledge*1.63),
                (.294,ledge*1.54),(.322,ledge*1.74),(.416,ledge*1.86),(.447,ledge*1.80),
                (.474,ledge*1.93),(.519,.87),(.548,.90),(.573,.875),(.631,.946),
                (.655,.962),(.693,.925),(.711,.97),(.789,.99),(.818,.956),(.843,.993),
                (.891,1.028),(.927,.998),(.965,1.005),(1,1))
    else:
        levels=((0,.56),(.10,.70),(.21,.76),(.27,.71),(.32,.85),(.47,.94),(.54,.85),
                (.60,1),(.68,1.025),(.73,.99),(.79,.98),(.87,.93),(.95,.83),(1,.73))
    if cap:
        levels=tuple(level for i,(a,b) in enumerate(zip(levels,levels[1:]))
                     for level in (a,((a[0]+b[0])*.5,(a[1]+b[1])*.5+(.004 if i%3==0 else -.003))))+levels[-1:]
    depth=top-bottom
    verts,faces,indices=[],[],[]
    dry,bare=[],[]
    for j,(t,s) in enumerate(levels):
        for i,p in enumerate(boundary):
            d=p-center
            bias=(.14*math.tanh(d.x/24)+.058*math.tanh(d.y/21))*math.sin(math.pi*t)
            fractures=(.005*math.sin(i*1.71+j*.68)+.014*math.sin(i*.47)+
                       .030*math.sin(i*.15+t*6))*math.sin(math.pi*t)
            overhang=.13*math.exp(-((t-.64)/.17)**2)*max(0,math.cos(i*math.tau/n+1.43)) if cap else 0
            xy=center+d*(s+bias+fractures+overhang)+Vector(drift)*(1-t)**1.5
            x,y=xy
            floor=.026*depth*math.sin(i*.23)+.011*depth*math.sin(i*1.34)
            bedding=.022*(x-center.x)-.045*(y-center.y)+depth*.019*math.sin(i*.14+t*3)
            z=bottom+t*depth+(1-t)*floor+math.sin(math.pi*t)*(
                bedding+.46*math.sin(i*.76+j*.37)+.31*math.sin(i*1.82-j*.62))
            z+=t**3*(summit(x,y,top)-top) if cap else 0
            verts.append((x-center.x,y-center.y,z-bottom))
            dry.append(0)
            bare.append(.82+.17*math.sin(i*.31) if j==len(levels)-1 else 1)
            if j:
                k=(j-1)*n
                faces.append((k+i,k+(i+1)%n,k+n+(i+1)%n,k+n+i))
                indices.append(3 if cap and j==len(levels)-1 else
                               (1 if j in ((8,16,22,30,36,42) if cap else (4,8,11))
                                and math.sin(i*.092+j)>.18 else 0))
    faces.append(tuple(reversed(range(n))))
    indices.append(1)
    if cap:
        smooth_from=len(faces)
        add_turf(verts,faces,indices,dry,bare,n,center,bottom,top,rng)
    else:
        smooth_from=None
        faces.append(tuple(range(len(verts)-n,len(verts))))
        indices.append(0)
    ob=mesh(name,verts,faces,materials,indices,smooth_from)
    if cap or tilt:
        for face in ob.data.polygons[:n*(len(levels)-1)]:
            face.use_smooth=True
        ob.data.set_sharp_from_angle(angle=math.radians(27))
    ob.location=(*center,bottom)
    if tilt:
        ob.rotation_euler=tilt
    for values,name in ((dry,"dryness"),(bare,"bare")):
        attr=ob.data.attributes.new(name,"FLOAT","POINT")
        attr.data.foreach_set("value",values)
    return boundary


def tube(vertices,faces,points,radii,n=6):
    start=len(vertices)
    for i,(p,r) in enumerate(zip(points,radii)):
        tangent=(points[min(i+1,len(points)-1)]-points[max(i-1,0)]).normalized()
        u=tangent.cross(Vector((0,.87,.49))).normalized()
        v=tangent.cross(u)
        vertices.extend(p+r*(u*math.cos(math.tau*j/n)+v*math.sin(math.tau*j/n)) for j in range(n))
        if i:
            a=start+(i-1)*n
            faces.extend((a+j,a+(j+1)%n,a+n+(j+1)%n,a+n+j) for j in range(n))
    faces.append(tuple(reversed(range(start,start+n))))
    faces.append(tuple(range(len(vertices)-n,len(vertices))))


def cap_roots(boundary,h,rng):
    verts,faces=[],[]
    center=sum(boundary,Vector((0,0)))/len(boundary)
    for i,p in enumerate(boundary):
        f=math.sin(i*.23)+.70*math.sin(i*.094)
        if f<.36 or rng.random()<.24:
            continue
        outward=(p-center).normalized()
        k=rng.uniform(1.1,5.4)
        p=Vector((*p,summit(*p,h)))
        q=Vector((*outward,0))
        root=[p-q*.32-Vector((0,0,.10)),p+q*.40-Vector((0,0,k*.29)),
              p+q*.86+Vector((.23,-.14,-k*.58)),p+q*.61+Vector((.62,.21,-k))]
        tube(verts,faces,root,(.24,.18,.105,.035),5)
        stub=[root[1],root[1].lerp(root[2],.65)+Vector((.38,.20,0)),
              root[2]+Vector((.85,.48,-.44))]
        tube(verts,faces,stub,(.13,.077,.018),5)
    mesh("Root strands in broken turf lip",verts,faces,("tree_bark",))


def trees(positions,rng):
    bark,bark_faces,canopy,canopy_faces,tones=[],[],[],[],[]
    for x,y,z,h in positions:
        root=Vector((x,y,z-.16))
        knee=root+Vector((.17,-.2,h*.43))
        trunk=knee+Vector((-.52,.30,h*.24))
        tube(bark,bark_faces,[root,knee,trunk],(.65,.43,.28),8)
        for i in range(6):
            a=i*math.tau/6+rng.uniform(-.26,.25)
            d=Vector((math.cos(a),math.sin(a),0))
            r=h*rng.uniform(.26,.51)
            crown=trunk+r*d+Vector((0,0,h*rng.uniform(.14,.33)))
            tube(bark,bark_faces,[knee.lerp(trunk,.59),trunk+.51*r*d,crown],
                 (.25,.16,.040),6)
            for j in range(11):
                angle=rng.uniform(0,math.tau)
                s=rng.uniform(.48,1.49)
                p=crown+Vector((r*.57*math.cos(angle),r*.37*math.sin(angle),rng.uniform(-.66,.47)))*rng.random()
                start=len(canopy)
                n=8
                for k,(v,g) in enumerate(((-.42,.64),(-.19,.91),(.09,1),(.37,.81),(.61,.44))):
                    for l in range(n):
                        th=math.tau*l/n
                        m=1+.15*math.sin(l*1.9+k*.91)
                        canopy.append(p+Vector((s*g*m*math.cos(th),s*g*m*math.sin(th),s*(v+.07*math.sin(l*2.7)))))
                    if k:
                        b=start+(k-1)*n
                        canopy_faces.extend((b+l,b+(l+1)%n,b+n+(l+1)%n,b+n+l) for l in range(n))
                        tones.extend([int((i+j)%7==0)]*n)
                canopy_faces.extend((tuple(reversed(range(start,start+n))),tuple(range(len(canopy)-n,len(canopy)))))
                tones.extend((0,1))
    mesh("Wind-shaped acacia silhouettes / trunks and forks",bark,bark_faces,("tree_bark",),smooth_from=0)
    mesh("Wind-shaped acacia silhouettes / clustered leaf crowns",canopy,canopy_faces,
         ("foliage_leaf","grass_ground"),tones,0)


def outcrops(groups,material,rng):
    for j,(x,y,h,density) in enumerate(groups):
        for i in range(density):
            px,py=x+rng.uniform(-12,12),y+rng.uniform(-7,7)
            s=rng.uniform(1.15,2.4)*(2.4 if i%7==0 else 1)
            polygon=[(px+s*rng.uniform(.74,1.13)*math.cos(k*math.tau/7),
                      py+s*rng.uniform(.51,.91)*math.sin(k*math.tau/7)) for k in range(7)]
            z=summit(px,py,h)-.61
            table(f"Limestone tor field {j+1}.{i+1}",polygon,z,z+s*.54,.55,(.27,-.54),
                  material,rng,False,1.8)


def build():
    rng=random.Random(970146)
    material=(bedding_finish(),"canyon_layered",terrain_finish(),"forest_soil")
    west=[(-151,-15),(-144,-49),(-125,-69),(-87,-76),(-52,-71),(-39,-57),
          (-6,-67),(8,-51),(2,-19),(15,-4),(11,21),(22,37),(16,62),
          (-18,68),(-43,78),(-84,74),(-105,63),(-132,44),(-146,21)]
    east=[(31,-50),(58,-63),(86,-61),(97,-44),(120,-29),(123,-4),
          (105,21),(118,37),(111,58),(81,67),(53,59),(38,46),
          (47,29),(30,14),(37,-9),(23,-21)]
    left=table("High west table / overhanging beds and fault wall",west,8,143,.40,(-11,-6),
               material,rng)
    right=table("Downthrown east table / displaced bedding",east,31,121,.36,(5,9),material,rng)
    cap_roots(left,143,rng)
    cap_roots(right,121,rng)
    for i,(cx,cy,z,h,rx,ry,a) in enumerate(((145,14,54,66,22,38,.37),(157,-31,37,53,12,16,-.21),
                                             (-122,-88,33,48,15,10,.18),(-106,-88,18,29,8,7,.23),
                                             (72,-45,9,42,22,10,-.30),(-46,51,2.1,37,18,11,-.11),
                                             (37,0,17,24,12,8,-.22),(64,73,17,34,13,10,.04))):
        poly=[(cx+rx*f*math.cos(k*math.tau/8+a),cy+ry*f*math.sin(k*math.tau/8+a))
              for k,f in enumerate((1,.78,1.07,.89,.98,.89,1.05,.82))]
        table(f"Detached tilted bedding block {i+1}",poly,z,z+h,.45,(3,-4),material,rng,False,
              2.9,(.14*math.sin(i*1.7),.19*math.cos(i*1.4),0))
    outcrops(((-73,28,143,22),(-106,-23,143,11),(-23,-26,143,19),
              (69,-20,121,16),(83,30,121,18)),material,rng)
    positions=[(x,y,summit(x,y,h),size) for x,y,h,size in
               ((-26,-45,143,11.2),(-38,-45,143,8.5),(-34,-34,143,9.7),
                (-84,43,143,9.3),(-71,41,143,7.4),(-94,-4,143,10.1),
                (64,-16,121,10.4),(67,-27,121,7.5),(92,45,121,11.5),
                (87,33,121,7.6),(80,38,121,8.7))]
    trees(positions,rng)
    objects=vrlib.source_objects()
    lo,_=vrlib.world_bounds(objects)
    lift=.005-lo.z
    for ob in objects:
        ob.location.z+=lift
    scene=bpy.context.scene
    x,y=-45,-48
    bpy.context.view_layer.update()
    hit,point,*_=scene.ray_cast(bpy.context.evaluated_depsgraph_get(),Vector((x,y,170)),Vector((0,0,-1)))
    scene["vr_review_figure"]=(x,y,point.z if hit else summit(x,y,143)+lift)
    scene["vr_review_floating"]=True
    scene["vr_closeup_upper"]=(-39,-40,141+lift,247,20,92)
    scene["vr_closeup_base"]=(-3,-19,73+lift,281,5,313)

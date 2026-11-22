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
    for attr,color in (("dryness",(.29,.242,.106,1)),("bare",(.247,.159,.084,1)),
                       ("hollows",(.057,.081,.030,1))):
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
        for k in range(count):
            f=k/count
            result.append(a.lerp(b,f)+normal*rng.uniform(-.068,.055)*spacing if k else a)
    return result


def summit(x,y,h):
    return h+4.2*math.sin(.037*x-.027*y)+2.8*math.cos(.088*y+.029*x)+1.2*math.sin(.12*x+.076*y)


def add_turf(verts,faces,indices,dry,bare,hollows,n,center,bottom,top,rng):
    start=len(verts)-n
    boundary=[Vector((x,y)) for x,y,_ in verts[start:]]
    samples=list(boundary)
    x_min=math.floor(min(p.x for p in boundary))
    x_max=math.ceil(max(p.x for p in boundary))
    y_min=math.floor(min(p.y for p in boundary))
    y_max=math.ceil(max(p.y for p in boundary))
    for x in range(x_min+2,x_max,2):
        for y in range(y_min+2,y_max,2):
            samples.append(Vector((x+rng.uniform(-.58,.58),y+rng.uniform(-.58,.58))))
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
        dri=.36+.33*math.sin(x*.053+y*.096)+.37*math.sin(x*.12+y*.031)*math.cos(y*.12)
        dry.append(min(1,max(0,(dri-.26)*1.96)))
        ash=.56+.24*math.sin(x*.27+y*.04)+.21*math.sin(y*.31+x*.084)
        path = abs(y-(-2+16*math.sin(.049*x)+6*math.sin(.10*x)))
        track = .92*max(0,min(1,(3.6-path)/2.5))*min(1,distance/6)
        blowout = .83*max(0,(math.sin(x*.128-y*.13)+math.sin(x*.052+y*.17)-1.26))
        bare.append(max(track,blowout,.87*max(0,1-distance/(2.1+max(.1,ash)*5.2))))
        hollows.append(.79*max(0,math.sin(x*.076+y*.065)*math.cos(y*.086-x*.021)-.23))
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
    levels = (((0,ledge),(.13,ledge*1.55),(.31,.61),(.47,.84),(.51,.77),(.60,.83),
               (.63,.98),(.75,.955),(.772,.915),(.798,.98),(.918,.98),(.943,1.025),
               (.978,.998),(1,1)) if cap else
              ((0,.38),(.16,.63),(.19,.58),(.32,.75),(.37,.71),(.53,.88),
               (.57,.83),(.65,1),(.82,.97),(.86,.94),(1,.84)))
    depth=top-bottom
    verts,faces,indices=[],[],[]
    dry,bare,hollows=[],[],[]
    joints=[(i,rng.uniform(.027,.077),rng.choice((.40,.57,.75,.91)))
            for i in range(2,n,rng.randint(6,11))] if cap else []
    bevels=[rng.uniform(-.008,.007) for _ in range(n)]
    course=[rng.uniform(-.026,.025) for _ in levels]
    for j,(t,s) in enumerate(levels):
        for i,p in enumerate(boundary):
            d=p-center
            theta=math.atan2(d.y,d.x)
            dip = .025*math.cos(theta*2+.65)+.018*math.sin(theta*3-.22)
            panel = (.052*math.sin(theta*4-j*.83)+.024*math.sin(theta*9+j*.46)) if cap else bevels[i]
            fracture=0
            for m,width,reach in joints:
                delta=abs((i-m-.95*t+.5*n)%n-.5*n)
                fracture=max(fracture,width*max(0,1-delta/1.7)*max(0,1-abs(t-reach)*2.32))
            face = min(1,(1-t)*12)*max(0,min(1,t*5))
            xy=center+d*(s+face*(dip+panel+course[j]+bevels[i])-fracture*min(1,(1-t)*26))
            xy+=Vector(drift)*(1-t)**1.23
            x,y=xy
            keels = .14 + .09*math.sin(2*theta+.30)+.070*math.cos(3*theta-1.10)
            floor=depth*keels if cap else .095*depth*math.sin(theta+1.2)
            bedding=(.039*(x-center.x)-.027*(y-center.y)+depth*.022*math.sin(theta*3)
                     +depth*.006*math.cos(theta*9+j*.69))
            z=bottom+t*depth+(1-t)**2.3*floor+math.sin(math.pi*t)*bedding
            z+=t**3*(summit(x,y,top)-top) if cap else 0
            verts.append((x-center.x,y-center.y,z-bottom))
            dry.append(0)
            hollows.append(0)
            bare.append(.82+.17*math.sin(i*.31) if j==len(levels)-1 else 1)
            if j:
                k=(j-1)*n
                faces.append((k+i,k+(i+1)%n,k+n+(i+1)%n,k+n+i))
                indices.append(3 if cap and j==len(levels)-1 else
                               int(j in ((4,8,11) if cap else (2,4,6)) and
                                   math.sin(theta*2.8+j*.77)>.33))
    faces.append(tuple(reversed(range(n))))
    indices.append(1)
    if cap:
        smooth_from=len(faces)
        add_turf(verts,faces,indices,dry,bare,hollows,n,center,bottom,top,rng)
    else:
        smooth_from=None
        faces.append(tuple(range(len(verts)-n,len(verts))))
        indices.append(0)
    ob=mesh(name,verts,faces,materials,indices,smooth_from)
    ob.location=(*center,bottom)
    if tilt:
        ob.rotation_euler=tilt
    for values,name in ((dry,"dryness"),(bare,"bare"),(hollows,"hollows")):
        attr=ob.data.attributes.new(name,"FLOAT","POINT")
        attr.data.foreach_set("value",values)
    if cap:
        fault_aprons(name,verts,n,center,bottom,materials,rng)
    return boundary


def fault_aprons(name,wall,n,center,bottom,materials,rng):
    # Displaced rock panels break across the bedding rather than following the skin of the cliff.
    def point(row,i,t):
        k=int(i)
        j=k%n
        m=(k+1)%n
        a=Vector(wall[row*n+j]).lerp(Vector(wall[row*n+m]),i-k)
        b=Vector(wall[(row+1)*n+j]).lerp(Vector(wall[(row+1)*n+m]),i-k)
        return a.lerp(b,t)

    verts,faces,tones=[],[],[]
    for row in (2,4,6,8,9,10,11):
        i=rng.uniform(0,7)
        while i<n-3:
            span=rng.uniform(1.7,6.4)
            if i+span>n:
                break
            if rng.random()<(.57 if row in (8,9,10,11) else .38):
                left,right=i+rng.uniform(-.30,.50),i+span
                lift=rng.uniform(.065,.38)
                head=rng.uniform(.60,1.08)
                rim=[point(row,left+.33,lift+.035),point(row,right-.38,lift),
                     point(row,right+.04,lift+.16),point(row,right-.43,head),
                     point(row,left+.21,head+rng.uniform(-.16,.15)),point(row,left-.08,head-.32)]
                normal=(rim[1]-rim[0]).cross(rim[-1]-rim[0]).normalized()
                protrusion=rng.uniform(.75,4.6)*(1.47 if row in (6,9) else 1)
                k=len(verts)
                mid=sum(rim,Vector((0,0,0)))/len(rim)
                verts.extend(p-normal*(.87+protrusion*.79) for p in rim)
                verts.extend(mid+(p-mid)*rng.uniform(.88,.99)+normal*protrusion*rng.uniform(.78,1.20) for p in rim)
                verts.append(mid+normal*protrusion*rng.uniform(.99,1.43)+Vector((0,0,rng.uniform(-.78,.78))))
                faces.append(tuple(k+j for j in reversed(range(6))))
                tones.append(1)
                for j in range(6):
                    q=(j+1)%6
                    faces.extend(((k+j,k+q,k+q+6,k+j+6),(k+j+6,k+q+6,k+12)))
                    tones.extend((int(j in (0,1) and rng.random()<.7),0))
            i+=span+rng.uniform(.26,2.61)
    ob=mesh(name.split(" /")[0]+" / displaced sandstone fracture plates",verts,faces,materials,tones)
    ob.location=(*center,bottom)


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


def scrub(fields,rng):
    verts,faces,indices=[],[],[]
    for cx,cy,h,count in fields:
        for i in range(count):
            a=rng.uniform(0,math.tau)
            offset=rng.uniform(.4,12.8)
            x,y=cx+offset*math.cos(a),cy+offset*.49*math.sin(a)
            z=summit(x,y,h)
            s=rng.uniform(.52,1.56)
            for j in range(rng.randint(3,7)):
                a=rng.uniform(0,math.tau)
                p=Vector((x+s*.6*math.cos(a),y+s*.52*math.sin(a),z+s*rng.uniform(.19,.65)))
                k=len(verts)
                leaf=rng.uniform(.26,.76)*s
                verts.extend(p+Vector((leaf*math.cos(a+q*math.tau/7),leaf*.74*math.sin(a+q*math.tau/7),0))
                             for q in range(7))
                verts.extend((p+Vector((.18*leaf,0,.44*leaf)),p-Vector((0,0,.37*leaf))))
                for q in range(7):
                    nxt=(q+1)%7
                    faces.extend(((k+q,k+nxt,k+7),(k+nxt,k+q,k+8)))
                    indices.extend((int((q+j)%4!=0),0))
    mesh("Low windswept scrub in linked pockets",verts,faces,("foliage_leaf","grass_ground"),indices)


def build():
    rng=random.Random(970146)
    material=(bedding_finish(),"canyon_layered",terrain_finish(),"forest_soil")
    west=[(-151,-15),(-144,-49),(-125,-69),(-87,-76),(-52,-71),(-39,-57),
          (-6,-67),(8,-51),(2,-19),(15,-4),(11,21),(22,37),(16,62),
          (-18,68),(-43,78),(-84,74),(-105,63),(-132,44),(-146,21)]
    east=[(31,-50),(58,-63),(86,-61),(97,-44),(120,-29),(123,-4),
          (105,21),(118,37),(111,58),(81,67),(53,59),(38,46),
          (47,29),(30,14),(37,-9),(23,-21)]
    left=table("High west table / overhanging beds and fault wall",west,8,143,.18,(-23,-13),
               material,rng)
    right=table("Downthrown east table / displaced bedding",east,31,121,.22,(16,16),material,rng)
    cap_roots(left,143,rng)
    cap_roots(right,121,rng)
    for i,(cx,cy,z,h,rx,ry,a) in enumerate(((147,17,54,63,26,39,.37),(150,-31,35,39,12,17,-.21),
                                             (-121,-80,43,59,22,10,.18),(-105,-91,33,29,8,7,.23),
                                             (73,-38,8,64,23,13,-.30),(-53,34,-5,65,38,26,-.11),
                                             (24,5,30,34,12,10,-.22),(57,76,50,34,16,10,.04))):
        profile=((1,.03),(.47,.91),(-.69,.71),(-1,-.14),(-.54,-.91),(.68,-.61))
        poly=[(cx+rx*u*math.cos(a)-ry*v*math.sin(a),cy+rx*u*math.sin(a)+ry*v*math.cos(a))
              for u,v in profile]
        table(f"{'Embedded broken keel' if i in (4,5) else 'Detached tilted bedding block'} {i+1}",
              poly,z,z+h,.45,(rx*.28,-ry*.17),material,rng,False,4.1,
              (.14*math.sin(i*1.7),.22*math.cos(i*1.4),0))
    outcrops(((-73,28,143,22),(-106,-23,143,11),(-23,-26,143,19),
              (69,-20,121,16),(83,30,121,18)),material,rng)
    groves=((-32,-40,143,5),(-88,40,143,5),(-94,-9,143,5),(-110,-41,143,4),
            (-23,38,143,4),(-60,-40,143,3),(65,-23,121,6),(88,37,121,6),(76,14,121,4))
    positions=[]
    for x,y,h,n in groves:
        a=rng.uniform(0,math.tau)
        for i in range(n):
            a+=2.40
            r=3.9*math.sqrt(i+1)
            px,py=x+r*math.cos(a),y+r*.86*math.sin(a)
            positions.append((px,py,summit(px,py,h),rng.uniform(5.7,12.3)))
    trees(positions,rng)
    scrub(tuple((x,y,h,n*9) for x,y,h,n in groves),rng)
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
    scene["vr_closeup_base"]=(-34,-54,106+lift,252,9,132)

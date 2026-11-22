"""The Threefold Reliquary: corbelled limestone around a levitating energy seed."""
import math
import random

import bmesh
import bpy
from mathutils import Vector

import vrlib
import vrmat


def loft(name, rings, material, bevel=0):
    n = len(rings[0])
    faces = [tuple(reversed(range(n)))]
    for j in range(len(rings)-1):
        a, b = j*n, (j+1)*n
        for i in range(n):
            k = (i+1) % n
            faces.append((a+i,a+k,b+k,b+i))
    faces.append(tuple(range((len(rings)-1)*n,len(rings)*n)))
    me = bpy.data.meshes.new(name)
    me.from_pydata([v for ring in rings for v in ring], [], faces)
    me.update()
    me.materials.append(vrmat.get(material) if isinstance(material, str) else material)
    ob = vrlib.link_to_source(bpy.data.objects.new(name, me))
    if bevel:
        mod = ob.modifiers.new("Dressed edges", "BEVEL")
        mod.width, mod.segments = bevel, 3
        mod.limit_method = "ANGLE"
    return ob


def sector(name, a, b, inner, outer, bottom, top, material, bevel):
    arc = [a + (b-a)*j/6 for j in range(7)]
    perimeter = [(outer,t) for t in arc] + [(inner,t) for t in reversed(arc)]
    loft(name, [[(r*math.cos(t),r*math.sin(t),z) for r,t in perimeter] for z in (bottom,top)],
         material, bevel)


def section(angle, z, radius, w, depth, shear):
    u = Vector((math.cos(angle), math.sin(angle),0))
    v = Vector((-u.y,u.x,0))
    cross = [(-.52,-.67),(0,-1),(.57,-.68),(.96,-.29),(.97,.46),
             (.51,.94),(-.50,1),(-.96,.48),(-1,-.29)]
    origin = u*radius + v*shear + Vector((0,0,z))
    return [origin + u*(r*depth) + v*(t*w) for r,t in cross]


def spline(rows, t):
    i = min(len(rows)-2, int(t))
    p, a, b, q = [Vector(rows[j]) for j in (max(0,i-1),i,i+1,min(len(rows)-1,i+2))]
    f = t-i
    return .5*((2*a)+(b-p)*f + (2*p-5*a+4*b-q)*f*f + (3*a-p-3*b+q)*f*f*f)


def rib(name, angle, rows, joints, material):
    for i,(a,b) in enumerate(zip(joints,joints[1:])):
        a += .004 if i else 0
        b -= .006 if i+2 < len(joints) else 0
        steps = max(3, math.ceil((b-a)*8))
        rings = [section(angle, *spline(rows,a+(b-a)*k/steps)) for k in range(steps+1)]
        if i in (2,5,7):
            j = (i*7+int(angle*7))%len(rings[0])
            for k in range(1,len(rings)):
                t = k/(len(rings)-1)
                p = rings[k][j]
                cap = rings[k][j-1].lerp(rings[k][(j+1)%len(rings[k])],.48)
                rings[k][j] = p.lerp(cap,(.91 if i in (2,5) else .53)*t*t)
                if i in (2,5):
                    rings[k][j].z -= .23*t*t
                    n = (j+1)%len(rings[k])
                    rings[k][n] = rings[k][n].lerp(cap,.43*t*t)
        loft(f"{name} / bed {i+1}", rings,
             "monument_weathered" if i==0 else material, .044 if i+2 < len(joints) else .022)


def pale_limestone():
    mat = vrmat.get("monument_white").copy()
    mat.name = "Reliquary / warm honed limestone"
    nodes,links = mat.node_tree.nodes,mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    color = bsdf.inputs["Base Color"]
    blend = nodes.new("ShaderNodeMixRGB")
    blend.inputs[0].default_value = .77
    blend.inputs[2].default_value = (*vrmat.load_palette()["monument_white"]["linear_rgb"],1)
    links.new(color.links[0].from_socket,blend.inputs[1])
    links.new(blend.outputs[0],color)
    return mat


def energy_surface(name,gain,flow_color,tone=1,seed=False):
    mat = vrmat.get("violet_energy").copy()
    mat.name = name
    nodes,links = mat.node_tree.nodes,mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for node in list(nodes):
        if node.type not in {"BSDF_PRINCIPLED","OUTPUT_MATERIAL"}:
            nodes.remove(node)
    coord=nodes.new("ShaderNodeTexCoord")
    noise=nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value=7.5
    links.new(coord.outputs["Object"],noise.inputs["Vector"])
    if seed:
        attr=nodes.new("ShaderNodeAttribute")
        attr.attribute_name="seed_inclusions"
        mix=nodes.new("ShaderNodeMath")
        mix.operation="MULTIPLY_ADD"
        mix.inputs[1].default_value=.14
        links.new(noise.outputs["Fac"],mix.inputs[0])
        links.new(attr.outputs["Fac"],mix.inputs[2])
        field=mix.outputs[0]
        emission=nodes.new("ShaderNodeMath")
        emission.operation="MULTIPLY_ADD"
        links.new(attr.outputs["Fac"],emission.inputs[0])
        emission.inputs[1].default_value=.30
        emission.inputs[2].default_value=gain
        links.new(emission.outputs[0],bsdf.inputs["Emission Strength"])
    else:
        field=noise.outputs["Fac"]
    band=nodes.new("ShaderNodeValToRGB")
    palette=vrmat.load_palette()
    r,g,b=palette["violet_body"]["linear_rgb"]
    for i,element in enumerate(band.color_ramp.elements):
        f=(.58*tone,.54+.55*tone)[i]
        element.color=(r*f*1.35,g*f*.79,b*f*.75,1)
        element.position=(.12,.95)[i]
    links.new(field,band.inputs["Fac"])
    links.new(band.outputs["Color"],bsdf.inputs["Base Color"])
    bsdf.inputs["Emission Color"].default_value=(*flow_color,1)
    bsdf.inputs["Emission Strength"].default_value=gain
    bsdf.inputs["Roughness"].default_value=.36
    return mat


def filament(name, points, width, material, highlight=None):
    rings = []
    for i,pt in enumerate(points):
        tangent = (points[min(len(points)-1,i+1)]-points[max(0,i-1)]).normalized()
        ref = Vector((pt.x,pt.y,.19))
        if abs(ref.normalized().dot(tangent))>.96:
            ref = Vector((0,0,1))
        v = tangent.cross(ref).normalized()
        u = v.cross(tangent)
        size = width * (.20+.80*math.sin(math.pi*i/(len(points)-1))**.7)
        rings.append([pt + size*(u*math.cos(a*math.tau/14)+v*math.sin(a*math.tau/14)) for a in range(14)])
    obj = loft(name, rings, material)
    if highlight:
        obj.data.materials.append(highlight)
    for poly in obj.data.polygons[1:-1]:
        poly.use_smooth = True
        if highlight and (poly.index-1)%14 in (0,6,7,13):
            poly.material_index=1


def seed_body():
    materials=[energy_surface(f"Seed / cleaved facet {i}",.019,(.47,.065,.58),tone,True)
               for i,tone in enumerate((.26,.53,.73,.40,.61,.32))]
    n=16
    rings=[]
    for k,(z,r,skew) in enumerate(((7.18,.095,-.12),(7.68,.46,-.14),(8.41,.81,-.19),
             (9.54,1.44,-.23),(10.38,1.88,-.21),(12.02,2.15,-.11),
             (13.00,2.35,.01),(14.62,2.23,.24),(15.14,2.06,.29),
             (16.31,1.62,.33),(17.19,1.14,.34),(18.34,.47,.26),(19.18,.044,.14))):
        ring=[]
        for i in range(n):
            a=i*math.tau/n+.022*k+.085*math.sin(i*2.3)
            rh=r*(1+.092*math.cos(i*math.tau/4+.45)+.071*math.cos(i*2.1+k*.18))
            ring.append((skew+rh*math.cos(a),.90*rh*math.sin(a),
                         z+min(r,.96)*(.31*math.sin(i*1.95+k*.34)+.097*math.cos(i*3.1))))
        rings.append(ring)
    ob=loft("Levitating seed / scalenohedral cleavage",rings,materials[0],.012)
    for material in materials[1:]:
        ob.data.materials.append(material)
    for face in ob.data.polygons[1:-1]:
        row,col=divmod(face.index-1,n)
        face.material_index = (col*5+(row%3 if row<3 or row>8 else 0))%6

    bm=bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=12,use_grid_fill=True)
    layer=bm.verts.layers.float.new("seed_inclusions")
    for v in bm.verts:
        x,y,z=v.co
        field=.34*math.exp(-((z-12.8)/3.1)**2)*max(.0,1-abs(x*.38+y*.26))
        for center,width,amp in ((9.7,.24,.46),(11.8,.51,.53),(13.8,.45,.69),(15.7,.23,.52),(16.8,.16,.36)):
            local=z-center-x*.44+y*.53-.32*math.cos(y*1.2+x*.4)
            lobe=max(0,1-((x*.30+y*.22)+.13*math.sin(z*.57))**2)
            field=max(field,amp*lobe*max(0,1-abs(local)/width))
        v[layer]=field
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    vein=energy_surface("Seed / narrow violet seams",.69,(.54,.12,.77),1.24)
    for col, begin, end in ((1,2,9),(5,4,10),(9,1,7)):
        verts,faces=[],[]
        nxt=(col+1)%n
        for k in range(begin,end):
            a,b,c,d=[Vector(p) for p in (rings[k][col],rings[k][nxt],rings[k+1][nxt],rings[k+1][col])]
            normal=(b-a).cross(d-a).normalized()
            q=k-begin
            for j in range(7):
                f=j/6
                center=.29+.13*math.sin((q+f)*1.71+col)+.042*math.sin((q+f)*8.3)
                width=.005+.014*math.sin(math.pi*(q+f)/(end-begin))**.87
                mid=a.lerp(d,f).lerp(b.lerp(c,f),center)+normal*.018
                delta=(b-a).lerp(c-d,f)*width
                verts.extend((mid-delta,mid+delta))
                if j or q:
                    s=len(verts)-4
                    faces.append((s,s+1,s+3,s+2))
        me=bpy.data.meshes.new("Narrow crystallized vein")
        me.from_pydata(verts,[],faces)
        me.update()
        me.materials.append(vein)
        vrlib.link_to_source(bpy.data.objects.new(me.name,me))


def field_arcs():
    field=energy_surface("Flux / saturated purple sheath",.46,(.44,.031,.72),.78)
    core=energy_surface("Flux / slender lilac center",1.24,(.68,.17,.79),1.40)
    for i,(angle,low,high,bend,width) in enumerate(((2.60,8.16,17.38,2.80,.077),
                     (-1.21,9.13,18.61,1.97,.061),(-2.46,10.83,16.42,1.77,.050))):
        path=[]
        for j in range(121):
            t=j/120
            peak=(2.6,2.8,2.6)[i]
            r=1.02+(peak-1.02)*math.sin(math.pi*t)**.69+.36*math.sin(math.pi*t*2)**2
            a=angle+bend*t+.07*math.sin(math.tau*t)
            z=low+(high-low)*t
            path.append(Vector((r*math.cos(a),r*math.sin(a),z)))
        filament(f"Core-borne orbital strand {i+1}",path,width,field,core)

    for i in range(3):
        a=i*math.tau/3+.50
        pts=[]
        for j in range(51):
            t=j/50
            r=.36*(1-t)+.085+.08*math.sin(math.pi*t)
            ang=a+1.3*t
            pts.append(Vector((r*math.cos(ang),r*math.sin(ang),2.25+4.99*t)))
        filament(f"Phase tether from the altar {i+1}",pts,.041,field,core)
    for i in range(13):
        z=2.17+i*.38
        t=i/12
        r=.50-.40*t
        a=i*2.4
        pts=[Vector((r*math.cos(a),r*math.sin(a),z+s*.016)) for s in range(6)]
        filament(f"Suspended censer spark {i+1}",pts,.021,core)


def emitter(pale):
    crystal=energy_surface("Emitter / glowing violet throat",.38,(.53,.094,.70),.9)
    for i in range(12):
        a=i*math.tau/12
        end=a+math.tau/12
        sector(f"Keyed altar socket foot {i+1}",a+.004,end-.004,.44,1.19,1.51,1.78,
               "monument_weathered",.019)
        sector(f"Bevelled altar socket jaw {i+1}",a+.012,end-.012,.47,.90,1.78,
               1.99+(.17 if i%4==0 else 0),pale,.042)
    for i in range(3):
        a=.50+i*math.tau/3
        x,y=.45*math.cos(a),.45*math.sin(a)
        loft(f"Socket crystal electrode {i+1}",
             [[(x+s*math.cos(a+j*math.tau/6),y+s*math.sin(a+j*math.tau/6),z)
               for j in range(6)] for z,s in ((1.63,.13),(1.83,.20),(2.07,.16),(2.30,.035))],
             crystal,.013)
    loft("Recessed central emitter crystal",
         [[(s*math.cos(j*math.tau/8),s*math.sin(j*math.tau/8),z) for j in range(8)]
          for z,s in ((1.51,.25),(1.76,.37),(2.03,.34),(2.16,.16))],crystal,.013)


def build():
    rng = random.Random(8704)
    pale = pale_limestone()
    for j,(inner,outer,low,high,n) in enumerate(((.03,8.0,-.045,.25,30),(.03,7.67,.25,.57,30),
                  (.03,7.34,.57,.86,30),(4.78,7.01,.86,1.17,27),(3.14,4.77,.86,1.08,21),
                  (1.48,3.12,.86,1.25,18),(1.38,2.45,1.25,1.52,18),(.85,1.90,1.52,1.71,15))):
        for i in range(n):
            angle = (i + .36*(j%2))*math.tau/n
            sector(f"Radial masonry {j+1}.{i+1}", angle+.0015, angle+math.tau/n-.0015,
                   inner,outer, low,high+rng.uniform(-.018,.018),
                   "monument_weathered" if j in (0,4) else pale, .035)
    for i,(angle,tip,weight,sweep,joints) in enumerate((
           (10,21.38,1.31,.93,(0,.31,.89,1.63,1.92,2.76,3.15,3.93,4.18,4.98,5.52,6)),
           (135,17.44,.82,1.30,(0,.56,1.30,1.63,2.49,2.76,3.67,4.10,4.89,5.55,6)),
           (254,19.66,1.07,1.02,(0,.40,1.25,1.69,2.57,3.00,3.81,4.11,4.91,5.27,6)))):
        az = math.radians(angle-36)
        for j,(r,w,z,d) in enumerate(((5.53,1.53,1.02,.92),(5.44,1.41,1.27,.87),(5.32,1.24,1.60,.82))):
            loft(f"Pier plinth {i+1}.{j+1}",[section(az,z,r,w*weight,d,0),
                 section(az,z+.27,r,w*weight*.97,d,0)],"monument_weathered" if j==0 else pale,.055)
        rows = [(1.77,5.36,1.18*weight,.95,0),(tip*.20,5.72,1.04*weight,.82,-.10),
                (tip*.35,6.12+.17*i,.87*weight,.74,-.24),(tip*.51,6.48+.22*i,.76*weight,.65,-.33),
                (tip*.68,6.43,.56*weight,.52,-.25),(tip-2.10,4.86*sweep,.37*weight,.39,.16),
                (tip,3.75*sweep,.095*weight,.13,.58)]
        rib(f"Great catching rib {i+1}",az,rows,joints,pale)
        for side,height in ((-1,10.38-i*.79),(1,5.79+i*.75)):
            rows = [(1.11,5.40,.42,.57,side*1.54),(2.34,5.94,.37,.43,side*1.61),
                    (height*.58,6.43,.31,.36,side*1.32),(height*.82,6.51,.22,.27,side*.95),
                    (height,6.26,.072,.13,side*.59)]
            rib(f"Companion web {i+1}/{side}",az,rows,(0,.64,1.48,2.16+i*.10,3.26,4),pale)

    emitter(pale)
    seed_body()
    field_arcs()
    bpy.context.scene["vr_closeup_upper"]=(0,0,13.2,68,11,20.5)
    bpy.context.scene["vr_closeup_base"]=(0,0,3.6,315,16,13.6)

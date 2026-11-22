"""The Threefold Reliquary: corbelled limestone around a levitating energy seed."""
import math
import random

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
                rings[k][j] = p.lerp(cap,.36*t*t)
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


def energy_surface(name,gain,flow_color,tone=1):
    mat = vrmat.get("violet_energy").copy()
    mat.name = name
    nodes,links = mat.node_tree.nodes,mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for key in ("Normal","Base Color","Emission Strength","Emission Color"):
        for link in list(bsdf.inputs[key].links):
            links.remove(link)
    coord=nodes.new("ShaderNodeTexCoord")
    stretch=nodes.new("ShaderNodeVectorMath")
    stretch.operation="MULTIPLY"
    stretch.inputs[1].default_value=(2.4,2.4,.088)
    links.new(coord.outputs["Object"],stretch.inputs[0])
    noise=nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value=1.2
    noise.inputs["Detail"].default_value=2.3
    links.new(stretch.outputs[0],noise.inputs["Vector"])
    band=nodes.new("ShaderNodeValToRGB")
    palette=vrmat.load_palette()
    for i,key in enumerate(("violet_shadow","violet_body")):
        r,g,b=palette[key]["linear_rgb"]
        band.color_ramp.elements[i].color = (r*tone*1.43,g*tone*.76,b*tone*.90,1)
        band.color_ramp.elements[i].position = (.16,.86)[i]
    links.new(noise.outputs["Fac"],band.inputs["Fac"])
    links.new(band.outputs["Color"],bsdf.inputs["Base Color"])
    bsdf.inputs["Emission Color"].default_value=(*flow_color,1)
    bsdf.inputs["Emission Strength"].default_value=gain
    bsdf.inputs["Roughness"].default_value=.36
    return mat


def filament(name, points, width, material):
    rings = []
    for i,pt in enumerate(points):
        tangent = (points[min(len(points)-1,i+1)]-points[max(0,i-1)]).normalized()
        v = tangent.cross(Vector((0,1,0))).normalized()
        u = v.cross(tangent)
        size = width * (.20+.80*math.sin(math.pi*i/(len(points)-1))**.7)
        rings.append([pt + size*(u*math.cos(a*math.tau/8)+v*math.sin(a*math.tau/8)) for a in range(8)])
    obj = loft(name, rings, material)
    for poly in obj.data.polygons[1:-1]:
        poly.use_smooth = True


def seed_body():
    body=energy_surface("Seed / amethyst body",.16,(.37,.03,.53),1.04)
    shadow=energy_surface("Seed / deeper cleaved mineral",.11,(.32,.02,.48),.73)
    crown=energy_surface("Seed / translucent inner cleavage",.27,(.47,.056,.66),1.40)
    n=12
    rings=[]
    for k,(z,r,skew) in enumerate(((7.18,.095,-.12),(7.68,.46,-.14),(8.41,.81,-.19),
             (9.54,1.44,-.23),(10.38,1.88,-.21),(12.02,2.15,-.11),
             (13.00,2.35,.01),(14.62,2.23,.24),(15.14,2.06,.29),
             (16.31,1.62,.33),(17.19,1.14,.34),(18.34,.47,.26),(19.18,.044,.14))):
        ring=[]
        for i in range(n):
            a=i*math.tau/n+.06*k
            rh=r*(1+.11*math.cos(i*math.tau/4+.45)+.047*math.cos(i*2.1))
            ring.append((skew+rh*math.cos(a),.90*rh*math.sin(a),
                         z+min(r,.96)*(.31*math.sin(i*1.95+k*.34)+.097*math.cos(i*3.1))))
        rings.append(ring)
    ob=loft("Levitating seed / scalenohedral cleavage",rings,body,.020)
    ob.data.materials.append(shadow)
    ob.data.materials.append(crown)
    for face in ob.data.polygons[1:-1]:
        row,col=divmod(face.index-1,n)
        face.material_index = 2 if col in (0,6) and row in (2,3,4,6,9,10) else int(col%3==2)

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
    field=energy_surface("Flux / saturated purple sheath",.45,(.44,.031,.72),1.35)
    core=energy_surface("Flux / slender lilac center",.83,(.68,.17,.79),1.40)
    for i,(angle,low,high,bend,width) in enumerate(((.58,8.09,15.9,.91,.19),(2.72,10.20,18.12,-.87,.16),
                                                  (4.74,8.82,15.53,1.02,.17))):
        sheath,rail=[],[]
        for j in range(73):
            t=j/72
            r=2.62+.80*math.sin(math.pi*t)**1.25
            a=angle+bend*t+.15*math.sin(math.tau*t)
            z=low+(high-low)*t
            outward=Vector((math.cos(a),math.sin(a),0))
            point=outward*r+Vector((0,0,z))
            sheath.append(point)
            rail.append(point+outward*width*.93)
        filament(f"Detached flux arc {i+1}",sheath,width,field)
        filament(f"Lilac highlight in flux arc {i+1}",rail,width*.235,core)

    for i in range(3):
        a=i*math.tau/3+.50
        pts=[]
        for j in range(51):
            t=j/50
            r=.53*(1-t)+.10+.08*math.sin(math.pi*t)
            ang=a+1.3*t
            pts.append(Vector((r*math.cos(ang),r*math.sin(ang),1.79+5.49*t)))
        filament(f"Phase tether from the altar {i+1}",pts,.039,field if i else core)
    for i in range(13):
        z=2.17+i*.38
        t=i/12
        r=.50-.40*t
        a=i*2.4
        pts=[Vector((r*math.cos(a),r*math.sin(a),z+s*.016)) for s in range(6)]
        filament(f"Suspended censer spark {i+1}",pts,.021,core)


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
           (10,21.38,1.31,.93,(0,.42,.88,1.20,1.78,2.37,2.93,3.65,4.24,4.86,5.42,6)),
           (135,17.44,.82,1.30,(0,.51,1.19,1.69,2.31,2.92,3.57,4.32,5.01,5.47,6)),
           (254,19.66,1.07,1.02,(0,.66,1.20,1.87,2.40,3.13,3.60,4.08,4.76,5.30,6)))):
        az = math.radians(angle)
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

    inlay=energy_surface("Altar aperture / violet ceramic",.36,(.43,.046,.73),1.14)
    for i in range(18):
        a=i*math.tau/18
        sector(f"Altar lens rim {i+1}",a+.008,a+math.tau/18-.008,.63,1.21,1.54,1.92,pale,.036)
        sector(f"Violet collector inlay {i+1}",a+.024,a+math.tau/18-.024,.14,.67,1.49,1.76,inlay,.014)
    seed_body()
    field_arcs()
    bpy.context.scene["vr_closeup_upper"]=(0,0,13.2,68,11,20.5)
    bpy.context.scene["vr_closeup_base"]=(0,0,4.2,315,13,19)

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
        loft(f"{name} / bed {i+1}", rings,
             "monument_weathered" if i in (0,3) else material, .045 if i+2 < len(joints) else .022)


def body_point(t, a):
    radius = .07 + 2.56*math.sin(math.pi*t)**.73 * (.74+.38*t)
    lobes = 1 + .115*math.cos(3*a - t*1.5) + .035*math.sin(7*a+3*t)
    angle = a + .92*t
    return Vector((.70*(t-.4)+radius*lobes*math.cos(angle),
                   .38*math.sin(t*3) + .86*radius*lobes*math.sin(angle),
                   8.0+10.55*t + .22*math.sin(math.pi*t)*math.sin(3*a)))


def energy_surface(name, gain_min, gain_max, frequency, core_width, halo_width):
    """Local violet_energy variant: widen the flow scale and narrow the lit area at monument size."""
    mat = vrmat.get("violet_energy").copy()
    mat.name = name
    bsdf = mat.node_tree.nodes["Principled BSDF"]

    def upstream(node, socket):
        return node.inputs[socket].links[0].from_node

    gain = upstream(bsdf, "Emission Strength")
    halo = upstream(gain, "Value")
    core = upstream(upstream(bsdf, "Emission Color"), "Fac")
    flow = upstream(upstream(upstream(halo,"Fac"),0),0)
    gain.inputs["To Min"].default_value = gain_min
    gain.inputs["To Max"].default_value = gain_max
    upstream(flow,"Vector").inputs[1].default_value = frequency
    flow.inputs["Detail"].default_value = 1.6
    for ramp, width in ((core,core_width),(halo,halo_width)):
        ramp.color_ramp.elements[0].position = width*.38
        ramp.color_ramp.elements[1].position = width
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


def build():
    rng = random.Random(8704)
    for j,(inner,outer,low,high,n) in enumerate(((.03,8.0,-.045,.25,30),(.03,7.67,.25,.57,30),
                  (.03,7.34,.57,.86,30),(4.78,7.01,.86,1.17,27),(3.14,4.77,.86,1.08,21),
                  (1.48,3.12,.86,1.25,18),(1.38,2.45,1.25,1.52,18),(.85,1.90,1.52,1.71,15))):
        for i in range(n):
            angle = (i + .36*(j%2))*math.tau/n
            sector(f"Radial masonry {j+1}.{i+1}", angle+.0015, angle+math.tau/n-.0015,
                   inner,outer, low,high+rng.uniform(-.018,.018),
                   "monument_weathered" if j in (0,4) or rng.random()<.14 else "monument_white", .035)
    for i in range(3):
        az = math.radians(8+120*i)
        for j,(r,w,z,d) in enumerate(((5.53,1.53,1.02,.92),(5.44,1.41,1.27,.87),(5.32,1.24,1.60,.82))):
            loft(f"Pier plinth {i+1}.{j+1}", [section(az,z,r,w,d,0),section(az,z+.27,r,w*.97,d,0)],
                 "monument_weathered" if j==0 else "monument_white", .055)
        tip = (21.18,18.9,20.02)[i]
        rows = [(1.77,5.36,1.18,.93,0),(4.16,5.42,1.03,.80,-.10),
                (7.24,6.04,.84,.73,-.19),(10.65,6.32,.72,.66,-.28),
                (14.17,5.98,.59,.54,-.22),(tip-2.25,4.98,.40,.40,.10),(tip,3.69,.14,.19,.48)]
        rib(f"Great catching rib {i+1}",az,rows,(0,.58,1.12,1.69,2.21,2.78,3.34,3.99,4.62,5.25,6),
            "monument_white")
        for side, height in ((-1,9.15),(1,6.42)):
            rows = [(1.10,5.33,.41,.58,side*1.45),(2.34,5.80,.36,.43,side*1.50),
                    (height*.58,6.06,.29,.36,side*1.29),(height*.81,6.30,.24,.30,side*.92),
                    (height,6.28,.10,.17,side*.57)]
            rib(f"Companion web {i+1}/{side}",az,rows,(0,.68,1.44,2.25,3.2,4),"monument_white")

    body = energy_surface("Violet energy / broad longitudinal flow",.18,5.4,(1.25,1.25,.14),.010,.043)
    thread = energy_surface("Violet energy / dense suspended filaments",1.9,7.0,(.95,.95,.21),.018,.051)
    seed = loft("Levitating three-lobed energy body",
                [[body_point(k/52,j*math.tau/36) for j in range(36)] for k in range(53)],body)
    for poly in seed.data.polygons[1:-1]:
        poly.use_smooth = True
    for j,(a,begin,end,w) in enumerate(((.7,.12,.86,.051),(2.8,.17,.94,.046),(4.8,.11,.84,.049),
                                       (2.71,.24,.61,.028),(.67,.47,.83,.035),(4.76,.28,.64,.032))):
        pts = []
        for k in range(61):
            f = k/60
            t = begin+(end-begin)*f
            pt = body_point(t,a + .44*math.sin(f*5.9+j*.42))
            distance = (.06 + (.21 if j<3 else .46)*math.sin(math.pi*f)**1.4)
            outward = Vector((pt.x-.70*(t-.4),pt.y-.38*math.sin(t*3),0)).normalized()
            pts.append(pt + outward*distance)
        filament(f"Detached flux filament {j+1}",pts,w,thread)

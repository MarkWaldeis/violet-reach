"""White limestone barrel-vault bridge with a 25 m opening and dressed slab deck."""
import math
import random

import bpy

import vrlib
import vrmat


def prism(name, rings, material, rounding):
    n = len(rings[0])
    faces = [tuple(reversed(range(n)))]
    for j in range(len(rings)-1):
        a, b = n*j, n*(j+1)
        faces.extend((a+i,a+(i+1)%n,b+(i+1)%n,b+i) for i in range(n))
    faces.append(tuple(range(n*(len(rings)-1),n*len(rings))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([v for ring in rings for v in ring], [], faces)
    mesh.update()
    mesh.materials.append(vrmat.get(material) if isinstance(material, str) else material)
    obj = vrlib.link_to_source(bpy.data.objects.new(name, mesh))
    if rounding:
        bevel = obj.modifiers.new("Dressed and worn edges", "BEVEL")
        bevel.width, bevel.segments = rounding, 3
        bevel.limit_method = "ANGLE"
    return obj


def deck_z(x):
    a = abs(x)
    if a >= 18:
        return .034
    return .034+5.52*math.cos(math.pi*a/36)**1.02


def tread_intervals():
    stations = [18.0]
    for n in range(1,31):
        stations.append(36/math.pi*math.acos((n*.176/5.52)**(1/1.02)))
    half = [(a,b,.034+i*.176) for i,(b,a) in enumerate(zip(stations,stations[1:]))]
    return [(-b,-a,z) for a,b,z in half]+[(-stations[-1],stations[-1],.034+30*.176)]+half[::-1]


def dressed_stone():
    """A local low-contrast honed finish, retaining the library's limestone pores."""
    mat = vrmat.get("monument_white").copy()
    mat.name = "Pale Ford / honed limestone"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    diffuse = bsdf.inputs["Base Color"]
    mix = nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = .83
    mix.inputs[2].default_value = (*vrmat.load_palette()["monument_white"]["linear_rgb"], 1)
    links.new(diffuse.links[0].from_socket, mix.inputs[1])
    links.new(mix.outputs[0], diffuse)
    return mat


def arch_point(a, r):
    return (12.50 + r*.85)*math.cos(a), .21+(4.18+r)*math.sin(a)


def extrados(x):
    radius, rise = 12.50+.62*.85, 4.18+.62
    return .21+rise*math.sqrt(max(0,1-(x/radius)**2)) if abs(x)<radius else 0


def arch_block(name, a, b, r0, r1, y0, y1, material, bevel):
    t = [b+(a-b)*i/4 for i in range(5)]
    profile = [arch_point(t0,r1) for t0 in t]+[arch_point(t0,r0) for t0 in reversed(t)]
    prism(name, [[(x,y,z) for x,z in profile] for y in (y0,y1)], material, bevel)


def run(name, x0, x1, y0, y1, depth0, depth1, material, bevel, follows=deck_z):
    ts = [x0+(x1-x0)*j/3 for j in range(4)]
    section = [(x,y0) for x in ts]+[(x,y1) for x in reversed(ts)]
    prism(name, [[(x,y,max(-.052,follows(x)+d)) for x,y in section] for d in (depth0,depth1)], material,bevel)


def pier(name,x,y,height,material):
    rings = []
    for f,s in ((0,1),(.21,1),(.28,.83),(.63,.60),(.89,.59),(1,.68)):
        outline = [(-.72,-.9),(.65,-.9),(1,-.52),(1,.57),(.66,.91),(-.70,.91),(-1,.54),(-1,-.54)]
        rings.append([(x+.34*s*u,y+.26*s*v,deck_z(x+.34*s*u)+height*f) for u,v in outline])
    prism(name,rings,material,.036)


def wingwalls(side, pale):
    for bank in (-1,1):
        for j in range(10):
            z = -.048+j*.235
            if j>0:
                z += .007
            reach = 17.95 - j*.49
            start = 12.17 + .09*j
            mid = (reach+start)/2
            bulge = 3.12-.060*j
            # Mirrored returns spread out beyond the walkable stair width.
            outline = [(start,1.87),(mid,1.9),(reach,2.04),(reach-.09,bulge),
                       (mid+.22,bulge+.12),(start-.16,bulge-.27)]
            if side*bank<0:
                outline.reverse()
            prism(f"Splayed wing {side:+}/{bank:+}/{j+1}", [
                [(side*x,bank*y,z0) for x,y in outline] for z0 in (z,z+.23)],
                "monument_weathered" if j in (0,2) else pale,.030)
    for j,(a,b) in enumerate(((17.98,18.83),(18.84,19.51),(19.51,20.18))):
        x0,x1 = sorted((side*a,side*b))
        run(f"Bank landing {side:+}/{j+1}",x0,x1,-2.17,2.17,-.05,.034,
            pale,.021,lambda x:0)


def stairs(pale, rng, treads):
    for i,(x0,x1,z) in enumerate(treads):
        split = [-1.865,-.95,.02,.94,1.865]
        for j in (1,2,3):
            split[j] += rng.uniform(-.14,.14)
        for j,(u,v) in enumerate(zip(split,split[1:])):
            run(f"Stair tread {i+1}.{j+1}",
                x0+.004,x1-.004,u+.005,v-.005,-.238,.0,
                pale,.012,lambda x,z=z:z)
    for side in (-1,1):
        for x in (-16.57,-13.48,-8.8,-4.18,0,4.18,8.8,13.48,16.57):
            # Modelled cover blocks anchor the coping at strongly loaded pier lines.
            run(f"Projecting drip block {side:+}/{x:+.2f}",x-.14,x+.14,
                *sorted((side*2.13,side*2.33)),-.24,-.08,pale,.026)


def build():
    rng = random.Random(135719)
    pale = dressed_stone()
    treads = tread_intervals()
    n = 39
    for i in range(n):
        a,b = ((i+v)*math.pi/n for v in (.015,.985))
        arch_block(f"Barrel voussoir {i+1:02}",a,b,0,.62,-1.88,1.88,
                   "monument_weathered" if i in (0,1,37,38) else pale,.022)
        for side in (-1,1):
            y0,y1 = sorted((side*1.87,side*(2.38 if i==n//2 else 2.24)))
            arch_block(f"Face voussoir {side:+d}/{i+1:02}",a,b,-.15 if i==n//2 else -.04,
                       .85 if i==n//2 else .68,y0,y1,
                       "monument_weathered" if i in (0,1,37,38) else pale,.041)

    for side in (-1,1):
        wingwalls(side,pale)
        for i,(xa,xb,z,w) in enumerate(((11.98,15.09,-.04,2.87),(12.05,14.82,.23,2.67),
                                         (12.46,14.63,.48,2.56),(13.38,14.47,.73,2.49))):
            x0,x1 = sorted((side*xa,side*xb))
            run(f"Abutment footing {side:+}/{i+1}",x0,x1,-w,w,z,z+.255,
                "monument_weathered" if i<2 else pale,.042,lambda x:0)
        for i in range(10):
            z = .02+.27*i
            xa = max(12.4,13.2055*math.sqrt(max(0,1-((z-.21)/5.01)**2)))
            xa = xa if z>.23 else 13.20
            for j,q in enumerate((0,.47)):
                k = .47 if j==0 else 1
                xb = 17.98
                x0,x1 = sorted((side*(xa+(xb-xa)*q), side*(xa+(xb-xa)*k-.013)))
                heights = [top for a,b,top in treads if a<x1 and x0<b]
                top = min(z+.255,min(heights)-.045) if heights else z
                if top<=z+.01:
                    continue
                run(f"Retaining masonry {side:+}/{i+1}.{j+1}",x0,x1,-2.03,2.03,
                    z,top,pale,.026,lambda x:0)

    stairs(pale,rng,treads)
    for i in range(53):
        x0,x1 = -17.99+i*35.98/53,-17.99+(i+1)*35.98/53
        for side in (-1,1):
            width = .29 if i in (0,52) else .20
            lo,hi = sorted((side*1.87,side*(2.21+width*.15)))
            run(f"Recessed drip course {side:+}/{i+1:02}",x0+.009,x1-.009,lo,hi,-.25,-.19 if i not in (0,52) else -.06,
                "monument_weathered",.014)
            run(f"Drip cornice {side:+}/{i+1:02}",x0+.009,x1-.009,lo,hi,-.19 if i not in (0,52) else -.058,
                -.04 if i not in (0,52) else .016,pale,.027)
    for i,(x0,x1,z) in enumerate(treads):
        a,b = x0+.012,x1-.012
        top = z-.045
        xs = [a+(b-a)*k/4 for k in range(5)]
        if top>max(extrados(x) for x in xs)+.008:
            section = [(x,-2.025) for x in xs]+[(x,2.025) for x in reversed(xs)]
            prism(f"Spandrel ashlar {i+1:02}",[[(x,y,extrados(x)-.01) for x,y in section],
                 [(x,y,top) for x,y in section]],pale,.017)

    for side in (-1,1):
        breaks = (-18,-16.57,-14.6,-13.48,-11.25,-8.8,-7.1,-5.9,-4.18,-2.65,
                  -1.18,1.18,2.65,4.18,5.9,7.1,8.8,11.25,13.48,14.6,16.57,18)
        for x in (-18,-16.57,-13.48,-8.8,-4.18,-1.18,1.18,4.18,8.8,13.48,16.57,18):
            pier(f"Parapet pier {side:+}/{x:+.2f}",x,side*2.005,1.11 if abs(x)>2 else 1.29,pale)
        for i,(x,xx) in enumerate(zip(breaks,breaks[1:])):
            yo,yi=sorted((side*2.21,side*1.86))
            a,b=x+.013,xx-.013
            mid = (a+b)/2
            crest = abs(mid)<1.0
            crown = 1.08 if crest else .97
            run(f"Parapet base {side:+}/{i+1:02}",a,b,yo,yi,-.084,.26,"monument_weathered",.025)
            if crest or abs(mid)>13 or i in (4,6,14,16):
                run(f"Solid parapet field {side:+}/{i+1:02}",a,b,yo+.046,yi-.046,.18,crown-.11,pale,.026)
                if crest:
                    run(f"Crown relief {side:+}",a+.29,b-.29,*sorted((side*2.18,side*2.24)),.35,.79,pale,.039)
            else:
                count = 2 if b-a<1.65 else 3
                pitch = (b-a)/count
                for j in range(count):
                    pier(f"Open parapet baluster {side:+}/{i+1:02}.{j+1}",a+(j+.5)*pitch,
                         side*2.025,.87,pale)
            run(f"Parapet coping {side:+}/{i+1:02}",a,b,yo-.037,yi+.037,crown-.19,crown,pale,.038)
    for ob in vrlib.source_objects():
        ob.location.z += .008

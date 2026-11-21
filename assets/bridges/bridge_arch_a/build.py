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
    mesh.materials.append(vrmat.get(material))
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


def arch_point(a, r):
    return (12.50 + r*.85)*math.cos(a), .21+(4.18+r)*math.sin(a)


def extrados(x):
    radius, rise = 12.50+.65*.85, 4.18+.65
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


def build():
    rng = random.Random(135719)
    n = 39
    for i in range(n):
        a,b = ((i+v)*math.pi/n for v in (.015,.985))
        arch_block(f"Barrel voussoir {i+1:02}",a,b,0,.89,-1.88,1.88,
                   "monument_weathered" if i%7==0 else "monument_white",.022)
        for side in (-1,1):
            y0,y1 = sorted((side*1.82,side*(2.38 if i==n//2 else 2.24)))
            arch_block(f"Face voussoir {side:+d}/{i+1:02}",a,b,-.15 if i==n//2 else -.04,
                       .85 if i==n//2 else .68,y0,y1,
                       "monument_weathered" if rng.random()<.11 else "monument_white",.041)

    for side in (-1,1):
        for i,(xa,xb,z,w) in enumerate(((11.98,15.09,-.04,2.87),(12.05,14.82,.23,2.67),
                                         (12.46,14.63,.48,2.56),(13.38,14.47,.73,2.49))):
            x0,x1 = sorted((side*xa,side*xb))
            run(f"Abutment footing {side:+}/{i+1}",x0,x1,-w,w,z,z+.255,
                "monument_weathered" if i%2==0 else "monument_white",.042,lambda x:0)
        for i in range(10):
            z = .02+.27*i
            xa = max(12.4,13.2055*math.sqrt(max(0,1-((z-.21)/5.01)**2)))
            xa = xa if z>.23 else 13.20
            for j,q in enumerate((0,.47)):
                k = .47 if j==0 else 1
                xb = 17.98
                x0,x1 = sorted((side*(xa+(xb-xa)*q), side*(xa+(xb-xa)*k-.013)))
                ts = [x0+(x1-x0)*j/8 for j in range(9)]
                ts = [x for x in ts if deck_z(x)-.17>z+.01]
                if len(ts)<2:
                    continue
                section = [(x,-2.03) for x in ts]+[(x,2.03) for x in reversed(ts)]
                prism(f"Retaining masonry {side:+}/{i+1}.{j+1}",
                      [[(x,y,z) for x,y in section],
                       [(x,y,min(z+.255,deck_z(x)-.149)) for x,y in section]],
                      "monument_weathered",.026)

    for i in range(53):
        x0,x1 = -17.99+i*35.98/53,-17.99+(i+1)*35.98/53
        for side in (-1,1):
            width = .29 if i in (0,52) else .20
            lo,hi = sorted((side*1.87,side*(2.21+width*.15)))
            run(f"Drip cornice {side:+}/{i+1:02}",x0+.009,x1-.009,lo,hi,-.29 if i not in (0,52) else -.074,
                -.104 if i not in (0,52) else .012,
                "monument_white",.033)
        for j in range(4):
            y0 = -1.85+j*.925+.037*math.sin(i*1.7+j) if j else -1.85
            y1 = -1.85+(j+1)*.925+.037*math.sin(i*1.7+j+1) if j<3 else 1.85
            run(f"Paving {i+1:02}.{j+1}",x0+.007,x1-.007,y0+.007,y1-.007,
                -.126 if max(abs(x0),abs(x1))<17 else -.07,0,
                "monument_weathered" if rng.random()<.21 else "monument_white",.017)
    for i in range(67):
        a,b = ((i+v)*36/67-18 for v in (.015,.985))
        if abs((a+b)/2)>17.65:
            continue
        xs = [a+(b-a)*k/4 for k in range(5)]
        if all(deck_z(x)-.10>extrados(x)+.04 for x in xs):
            section = [(x,-2.025) for x in xs]+[(x,2.025) for x in reversed(xs)]
            prism(f"Spandrel ashlar {i+1:02}",[[(x,y,extrados(x)-.01) for x,y in section],
                 [(x,y,deck_z(x)-.095) for x,y in section]],"monument_white",.017)

    for side in (-1,1):
        for i in range(25):
            x = -16.8+i*1.4
            if i in (0,6,12,18,24):
                pier(f"Parapet pilaster {side:+}/{i+1:02}",x,side*2.005,1.13,"monument_white")
            if i>=24:
                continue
            yo,yi=sorted((side*2.21,side*1.86))
            a,b=x+.018,x+1.4-.018
            run(f"Parapet base {side:+}/{i+1:02}",a,b,yo,yi,-.084,.26,"monument_weathered",.025)
            if i%6 in (0,1,4,5):
                run(f"Solid parapet field {side:+}/{i+1:02}",a,b,yo+.046,yi-.046,.18,.81,
                    "monument_white",.026)
            else:
                for j in range(2):
                    pier(f"Open parapet baluster {side:+}/{i+1:02}.{j+1}",a+.3+j*.67,
                         side*2.025,.87,"monument_white")
            run(f"Parapet coping {side:+}/{i+1:02}",a,b,yo-.037,yi+.037,.78,.98,
                "monument_white",.038)

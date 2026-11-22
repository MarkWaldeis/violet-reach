"""White limestone barrel-vault bridge with a 25 m opening and dressed slab deck."""
import math
import random

import bpy

import vrlib
import vrmat


def prism(name, rings, material, rounding, patina=None):
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
    if patina is not None:
        mask = mesh.attributes.new("patina", "FLOAT", "POINT")
        mask.data.foreach_set("value", [patina(x,y,z) for ring in rings for x,y,z in ring])
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
    coords = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 8.0
    links.new(coords.outputs["Object"], noise.inputs["Vector"])
    breakup = nodes.new("ShaderNodeMapRange")
    breakup.inputs["From Min"].default_value = .25
    breakup.inputs["From Max"].default_value = .75
    breakup.inputs["To Min"].default_value = .45
    breakup.inputs["To Max"].default_value = 1.0
    links.new(noise.outputs["Fac"], breakup.inputs["Value"])
    mask = nodes.new("ShaderNodeAttribute")
    mask.attribute_name = "patina"
    intensity = nodes.new("ShaderNodeMath")
    intensity.operation = "MULTIPLY"
    links.new(mask.outputs["Fac"], intensity.inputs[0])
    links.new(breakup.outputs["Result"], intensity.inputs[1])
    weather = nodes.new("ShaderNodeMixRGB")
    weather.inputs[2].default_value = (.096,.058,.030,1)
    links.new(intensity.outputs[0], weather.inputs[0])
    links.new(mix.outputs[0], weather.inputs[1])
    links.new(weather.outputs[0], diffuse)
    return mat


def damp_stone():
    mat = vrmat.get("monument_weathered").copy()
    mat.name = "Pale Ford / concentrated ochre and mineral damp"
    nt = mat.node_tree
    socket = nt.nodes["Principled BSDF"].inputs["Base Color"]
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = .67
    mix.inputs[2].default_value = (.48,.37,.25,1)
    nt.links.new(socket.links[0].from_socket,mix.inputs[1])
    nt.links.new(mix.outputs[0],socket)
    return mat


def footing_patina(x,y,z):
    return min(1.0,max(0.0,(.86+.24*math.sin(2.6*x)+.12*math.sin(5.8*x+2*y)-z)/.70))


def arch_point(a, r):
    return (12.50 + r*.85)*math.cos(a), .21+(4.18+r)*math.sin(a)


def extrados(x):
    radius, rise = 12.50+.62*.85, 4.18+.62
    return .21+rise*math.sqrt(max(0,1-(x/radius)**2)) if abs(x)<radius else 0


def arch_block(name, a, b, r0, r1, y0, y1, material, bevel, patina=None):
    t = [b+(a-b)*i/4 for i in range(5)]
    profile = [arch_point(t0,r1) for t0 in t]+[arch_point(t0,r0) for t0 in reversed(t)]
    prism(name, [[(x,y,z) for x,z in profile] for y in (y0,y1)], material, bevel, patina)


def run(name, x0, x1, y0, y1, depth0, depth1, material, bevel, follows=deck_z, patina=None):
    ts = [x0+(x1-x0)*j/3 for j in range(4)]
    section = [(x,y0) for x in ts]+[(x,y1) for x in reversed(ts)]
    prism(name, [[(x,y,max(-.052,follows(x)+d)) for x,y in section] for d in (depth0,depth1)],
          material,bevel,patina)


def column(name,x,y,height,rx,ry,profile,material,chip=None):
    outline = [(-.69,-1),(.74,-1),(1,-.62),(1,.64),(.68,1),(-.76,1),(-1,.59),(-1,-.56)]
    if chip:
        corner, low, high, depth = chip
        u,v = outline[corner]
        prev_u,prev_v = outline[corner-1]
        next_u,next_v = outline[(corner+1)%len(outline)]
        outline[corner:corner+1] = [(.53*u+.47*prev_u,.53*v+.47*prev_v), (u,v),
                                     (.51*u+.49*next_u,.51*v+.49*next_v)]
        profile = sorted((*profile, *((f,None) for f in (low,(low+high)*.5,high))))
    rings = []
    chip_patina = {}
    for k,(f,s) in enumerate(profile):
        if s is None:
            a,sa = next((a,v) for a,v in reversed(profile[:k]) if v is not None)
            b,sb = next((b,v) for b,v in profile[k+1:] if v is not None)
            s = sa+(sb-sa)*(f-a)/(b-a)
        ring = []
        for j,(u,v) in enumerate(outline):
            mask = 0
            if chip and corner <= j <= corner+2 and low < f < high:
                cut = depth*(1-abs(2*(f-low)/(high-low)-1))
                if j == corner+1:
                    u,v = u*(1-cut),v*(1-cut)
                    mask = .67*cut
                else:
                    u,v = u*(1-.38*cut),v*(1-.38*cut)
                    mask = .30*cut
            q = x+rx*s*u
            point = (q,y+ry*s*v,deck_z(q)+height*f)
            ring.append(point)
            if mask:
                chip_patina[point] = mask
        rings.append(ring)
    prism(name,rings,material,.007 if chip else .016 if rx<.24 else .034,
          (lambda x,y,z: chip_patina.get((x,y,z),0)) if chip else None)


def crown_panel(side,a,b,pale,damp):
    yi,yo = sorted((side*1.89,side*2.19))
    run(f"Crown ashlar panel {side:+}",a,b,yi,yo,.25,.94,pale,.041)
    for face in (-1,1):
        y = side*2.04+face*.155
        for z,w in ((.38,.77),(.81,.77),(.51,.59),(.67,.59)):
            run(f"Crown tablet moulding {side:+}/{face:+}/{z}",-w,w,*sorted((y,y+face*.061)),
                z,z+.043,damp if z==.38 else pale,.012)
        for x in (-.69,.69):
            run(f"Raised crown tablet jamb {side:+}/{face:+}/{x}",x-.065,x+.065,
                *sorted((y,y+face*.072)),.40,.83,pale,.020)
        for i,offset in enumerate((-.28,0,.28)):
            points = [(offset-.12,.605),(offset,.419),(offset+.12,.605),(offset,.79)]
            if face>0:
                points.reverse()
            prism(f"Carved lozenge boss {side:+}/{face:+}/{i}",
                  [[(x,q,deck_z(x)+z) for x,z in points] for q in (y,y+face*(.098 if i==1 else .066))],
                  pale,.016)


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
                pale,.030,footing_patina)
    rings = []
    for x,w,edge,deck in ((17.72,2.67,.47,.021),(18.0,2.67,.47,.034),
                          (18.65,2.79,.46,.034),(19.43,2.72,.38,.034),
                          (20.16,2.61,.29,.026),(20.47,2.53,.21,.012)):
        section = [(-w,-.057),(w,-.057),(w,edge),(2.13,edge),
                   (1.87,deck),(-1.87,deck),(-2.13,edge),(-w,edge)]
        if side < 0:
            section.reverse()
        rings.append([(side*x,y,z) for y,z in section])
    prism(f"Bonded landing and wing-wall plinth {side:+}", rings,pale,.018,
          lambda x,y,z: footing_patina(x,y,z)*min(.83,max(0,(abs(y)-1.45)*.85)))


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
    damp = damp_stone()
    treads = tread_intervals()
    n = 39
    for i in range(n):
        a,b = ((i+v)*math.pi/n for v in (.015,.985))
        def vault_patina(x,y,z):
            radial = max(0,1-(x/12.5)**2)
            underside = max(0,1-abs(z-(.21+4.18*math.sqrt(radial)))*2.6)
            seep = .23+.76*max(0,math.sin(i*.89+.57))**1.3
            return max(footing_patina(x,y,z),underside*seep)

        arch_block(f"Barrel voussoir {i+1:02}",a,b,0,.62,-1.88,1.88,pale,.022,vault_patina)
        if i:
            joint = i*math.pi/n
            seam = .082*math.pi/n
            arch_block(f"Recessed vault mortar joint {i:02}",joint-seam,joint+seam,.023,.13,
                       -1.881,1.881,damp,0)
        for side in (-1,1):
            y0,y1 = sorted((side*1.87,side*(2.38 if i==n//2 else 2.24)))
            arch_block(f"Face voussoir {side:+d}/{i+1:02}",a,b,-.15 if i==n//2 else -.04,
                       .85 if i==n//2 else .68,y0,y1,pale,.041,footing_patina)
            if i:
                arch_block(f"Recessed arch face mortar joint {side:+}/{i:02}",joint-seam,joint+seam,
                           .01,.56,*sorted((side*1.88,side*2.216)),damp,0)

    for side in (-1,1):
        wingwalls(side,pale)
        for i,(xa,xb,z,w) in enumerate(((11.98,15.09,-.04,2.87),(12.05,14.82,.23,2.67),
                                         (12.46,14.63,.48,2.56),(13.38,14.47,.73,2.49))):
            x0,x1 = sorted((side*xa,side*xb))
            run(f"Abutment footing {side:+}/{i+1}",x0,x1,-w,w,z,z+.255,
                pale,.042,lambda x:0,footing_patina)
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
                    z,top,pale,.026,lambda x:0,footing_patina)

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
            h = 1.25 if abs(x)>2 else 1.62
            column(f"Heavy parapet pier shaft {side:+}/{x:+.2f}",x,side*2.17,h,.35,.29,
                   ((.03,1.06),(.17,1.06),(.23,.87),(.79,.82),(.85,.98),(.95,.98)),pale)
            run(f"Pier oversailing cap {side:+}/{x:+.2f}",x-.43,x+.43,
                *sorted((side*1.84,side*2.57)),h-.108,h+.025,pale,.055)
        for i,(x,xx) in enumerate(zip(breaks,breaks[1:])):
            yo,yi=sorted((side*2.21,side*1.86))
            a,b=x+.013,xx-.013
            mid = (a+b)/2
            crest = abs(mid)<1.0
            crown = 1.08 if crest else .97
            run(f"Parapet base {side:+}/{i+1:02}",a,b,yo,yi,-.084,.26,"monument_weathered",.025)
            if crest:
                crown_panel(side,a,b,pale,damp)
            elif abs(mid)>13 or i in (4,6,14,16):
                run(f"Solid parapet field {side:+}/{i+1:02}",a,b,yo+.046,yi-.046,.18,crown-.11,pale,.026,
                    patina=lambda x,y,z: (.32+.59*abs(2*(x-a)/(b-a)-1)**2) if z-deck_z(x)>.65 else .035)
            else:
                count = 2 if b-a<1.65 else 3
                pitch = (b-a)/count
                for j in range(count):
                    chip = None
                    if (i*7+j+side)%7 in (0,3):
                        corner = (0,1)[j%2] if side<0 else (4,5)[j%2]
                        low,high = rng.uniform(.28,.32),rng.uniform(.64,.73)
                        chip = (corner,low,high,rng.uniform(.94,1.18))
                    profile = ((.23,1),(.30,.93),(.39,.66),(.55,.78),(.65,.71),(.76,.95),(.83,.95))
                    if i%3==0:
                        profile = ((.23,1),(.33,1),(.40,.72),(.54,.61),(.66,.76),(.75,1),(.83,1))
                    column(f"{'Spalled' if chip else 'Dressed'} baluster {side:+}/{i+1:02}.{j+1}",
                           a+(j+.5)*pitch,side*2.037,1,.155+.026*(i%2),.145,profile,pale,chip)
            run(f"Recessed damp under coping {side:+}/{i+1:02}",a,b,yo-.012,yi+.012,
                crown-.185,crown-.131,damp,.011)
            run(f"Parapet coping {side:+}/{i+1:02}",a,b,yo-.037,yi+.037,crown-.137,crown,pale,.033,
                patina=lambda x,y,z: .69+.30*abs(2*(x-a)/(b-a)-1) if z-deck_z(x)<crown-.08 else .035)
    for ob in vrlib.source_objects():
        ob.location.z += .008
    bpy.context.scene["vr_hero"] = (1.4,0,2.25,292,20,65)
    bpy.context.scene["vr_closeup_upper"] = (3.9,-1.95,4.85,255,-12,10.8)
    bpy.context.scene["vr_closeup_base"] = (-15.65,-.16,1.08,235,15,21)

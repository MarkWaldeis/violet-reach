"""A violet seam broken through a low fan of limestone and bare earth."""
import math
import random

import bpy
from mathutils import Matrix, Vector

import vrlib
import vrmat


def loft(name, rings, material, bevel=0):
    n = len(rings[0])
    pointed = len(rings[-1]) == 1
    sections = len(rings)-int(pointed)
    faces = [tuple(reversed(range(n)))]
    for row in range(sections - 1):
        a, b = row * n, (row + 1) * n
        faces.extend((a + i, a + (i + 1) % n, b + (i + 1) % n, b + i) for i in range(n))
    if pointed:
        a=(sections-1)*n
        faces.extend((a+i,a+(i+1)%n,a+n) for i in range(n))
    else:
        faces.append(tuple(range((sections-1)*n,sections*n)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([v for ring in rings for v in ring], [], faces)
    mesh.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, mesh))
    mesh.materials.append(vrmat.get(material) if isinstance(material,str) else material)
    if bevel:
        mod = obj.modifiers.new("Cleaved edges", "BEVEL")
        mod.width, mod.segments = bevel, 3
        mod.limit_method = "ANGLE"
    return obj


def mineral_finish(variant):
    key = "Violet / axial inclusions " + str(variant)
    existing = bpy.data.materials.get(key)
    if existing:
        return existing
    mat = vrmat.get("violet_crystal").copy()
    mat.name = key
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for name in ("Base Color","Normal","Emission Strength"):
        socket = bsdf.inputs[name]
        for link in list(socket.links):
            links.remove(link)
    bsdf.inputs["Roughness"].default_value = .31+.02*variant
    bsdf.inputs["Coat Weight"].default_value = .18
    bsdf.inputs["IOR"].default_value = 1.49
    bsdf.inputs["Emission Strength"].default_value = .065
    coord = nodes.new("ShaderNodeTexCoord").outputs["Generated"]

    def scale(vector, factors):
        op = nodes.new("ShaderNodeVectorMath")
        op.operation = "MULTIPLY"
        links.new(vector,op.inputs[0])
        op.inputs[1].default_value = factors
        return op.outputs[0]

    def remap(source, a, b, colors):
        r = nodes.new("ShaderNodeValToRGB")
        for k,(position,color) in enumerate(zip((a,b),colors)):
            r.color_ramp.elements[k].position = position
            r.color_ramp.elements[k].color = color
        links.new(source,r.inputs[0])
        return r.outputs[0]

    cells = nodes.new("ShaderNodeTexVoronoi")
    cells.inputs["Scale"].default_value = 1.8
    links.new(scale(coord,(4.3,4.3,1.2)),cells.inputs["Vector"])
    veins = nodes.new("ShaderNodeTexNoise")
    veins.inputs["Scale"].default_value = 1
    links.new(scale(coord,(28,28,1.7)),veins.inputs["Vector"])
    bands = nodes.new("ShaderNodeTexWave")
    bands.bands_direction = "Z"
    bands.wave_profile = "TRI"
    bands.inputs["Scale"].default_value = 1.48
    bands.inputs["Distortion"].default_value = .25
    links.new(coord,bands.inputs["Vector"])
    pal = vrmat.load_palette()
    warm = (.91,1.0,1.08)[variant]
    def violet(name, exposure):
        r,g,b = pal[name]["linear_rgb"]
        return (r*1.48*warm*exposure,g*.91*exposure,b*.89*exposure,1)

    body = remap(cells.outputs["Distance"],.18,.76,
                 (violet("violet_body",1.02),violet("violet_shadow",1.06)))
    for field, weight, low in ((veins.outputs["Fac"],.32,.59),(bands.outputs["Fac"],.39,.67)):
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = weight
        links.new(body,mix.inputs[1])
        links.new(remap(field,.15,.73,((low,low*.97,low,1),(1,1,1,1))),mix.inputs[2])
        body = mix.outputs[0]
    links.new(body,bsdf.inputs["Base Color"])
    links.new(body,bsdf.inputs["Emission Color"])
    return mat


def cleft_material():
    key = "Violet / buried fissure glow"
    if bpy.data.materials.get(key):
        return bpy.data.materials[key]
    mat = mineral_finish(1).copy()
    mat.name = key
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    for name in ("Base Color","Emission Color"):
        socket = bsdf.inputs[name]
        nt.links.remove(socket.links[0])
    bsdf.inputs["Base Color"].default_value = (.31,.077,.50,1)
    bsdf.inputs["Emission Color"].default_value = (.63,.15,.79,1)
    bsdf.inputs["Emission Strength"].default_value = .57
    return mat


def prismatic_growth(name, base, height, radius, lean, phase, rng, outline_kind=0):
    axis = Vector((*lean,1)).normalized()
    u = Vector((0,1,0)).cross(axis).normalized()
    v = axis.cross(u)
    rotation = Matrix((u,v,axis)).transposed().to_4x4()
    rotation.translation = Vector(base)
    corners = 4 if outline_kind==2 else 6
    profile = [Vector((radius*math.cos(phase+i*math.tau/corners),
                       radius*math.sin(phase+i*math.tau/corners)*(.59 if outline_kind else .85),0))
               for i in range(corners)]
    widths=(1.0,1.12,.74)
    irregularity=rng.uniform(.89,1.17)
    levels = ((0,.76,0,0),(.08,1,0,0),(.235,1,0,0),(.243,1.034,0,0),
              (.263,1.034,0,0),(.277,.955,.022,0),(.43,.955,.022,0),
              (.432,.997,.005,0),(.453,.997,.005,0),(.466,.887,.058,0),
              (.575,.887,.058,0),(.582,.925,.049,0),(.601,.925,.049,0),
              (.621,.855,.064,0),(.743,.855,.064,0),
              (.815,.855,.064,.85),(.907,.41,.18,.33))
    rings = []
    pinch = rng.randrange(corners)
    for k,(f,s,drift,termination) in enumerate(levels):
        ring = []
        for i,p in enumerate(profile):
            spread=1+(s-1)*widths[outline_kind]
            variation=math.sin(i*1.8+phase)*.014*math.sin(math.pi*f) if 1<k<15 else 0
            axial=f+(irregularity-1)*f*(1-f)*.73+variation
            q=p*spread+Vector((radius*drift,0,height*(axial+termination*.069*math.sin(i*1.53+phase))))
            if i==pinch and k in (10,11,12):
                q.x-=p.x*.115
                q.y-=p.y*.115
            ring.append(q)
        rings.append(ring)
    rings.append([Vector((radius*.23,-radius*.035,height))])
    ob = loft(name,rings,mineral_finish(1),min(.004,radius*.014))
    ob.matrix_world = rotation
    for tone in (0,2):
        ob.data.materials.append(mineral_finish(tone))
    for f in ob.data.polygons:
        if 0<f.index<len(ob.data.polygons)-1:
            col,row=(f.index-1)%corners,(f.index-1)//corners
            f.material_index = (2,0,1,0,1,2)[col] if row not in (2,4,6,8,10,12) else 2

    if radius<.20:
        return
    for side,k in ((0,1),(corners-2,6),(corners-1,10)):
        def face_point(t,w):
            row = min(len(rings)-2,int(t))
            local = t-row
            right=(side+1)%corners
            p=rings[row][side].lerp(rings[row][right],w)
            q=rings[row+1][side].lerp(rings[row+1][right],w)
            normal=(rings[row][right]-rings[row][side]).cross(rings[row+1][side]-rings[row][side]).normalized()
            return p.lerp(q,local)+normal*radius*.004
        verts, faces = [], []
        for j in range(15):
            q = j/14
            t = k+q*3.85
            w=.37+.13*math.sin(3.6*q+side)+.049*math.sin(27*q+side)
            taper=.003+.019*math.sin(math.pi*q)
            verts.extend((face_point(t,w-taper),face_point(t,w+taper)))
            if j:
                a=j*2
                faces.append((a-2,a-1,a+1,a))
        data=bpy.data.meshes.new(name+" cleft")
        data.from_pydata(verts,[],faces)
        data.update()
        data.materials.append(cleft_material())
        fissure=vrlib.link_to_source(bpy.data.objects.new(name+" / faint mineral fissure",data))
        fissure.matrix_world=rotation


def crystal(name, base, height, radius, lean, phase, rng):
    prismatic_growth(name,base,height,radius,lean,phase,rng,2 if "Raking" in name else int(radius<.37))


def slab(name, x, y, rx, ry, h, yaw, rng, material, lift=0):
    n = rng.randint(6,10)
    angles = [yaw + i * math.tau / n + rng.uniform(-.16, .16) for i in range(n)]
    fac = [rng.uniform(.63, 1.18) for _ in angles]
    relief = [rng.uniform(-.18, .15) for _ in angles]
    bite = rng.randrange(n)
    rings = []
    for z, s, dx in ((-.045, .85, 0), (.14*h,1,0), (.34*h,.99,.01),
                     (.39*h,.88,.023),(.43*h,.93,.026),(.63*h,.92,.04),
                     (.69*h,.75,.076),(.73*h,.82,.099),(.91*h,.79,.099),(h,.61,.114)):
        ratios = [s*(.72 if i==bite and z>.60*h else 1) for i in range(n)]
        rings.append([(x + rx * (fac[i] * ratios[i] * math.cos(a) + dx), y + ry * fac[i] * ratios[i] * math.sin(a),
                       max(-.046,z + lift + max(z, 0) * relief[i])) for i, a in enumerate(angles)])
    obj = loft(name, rings, material, min(.021, .056 * h))
    if h > .25:
        obj.data.materials.append(vrmat.get("monument_weathered"))
        for poly in obj.data.polygons[1:-1]:
            row,col = divmod(poly.index-1,n)
            if row in (2,5) or (row==6 and col in (bite,(bite-1)%n)):
                poly.material_index = 1


def build():
    rng = random.Random(695720)
    n = 80
    angles = [i * math.tau / n for i in range(n)]
    rings = []
    for r, z in ((1, -.046), (1, .002), (.94, .028), (.76, .087), (.52, .15),
                 (.35, .17), (.16, .11), (.02, .117)):
        rings.append([(2.72 * r * math.cos(a) * (1 + .09 * math.sin(3*a) + .08 * math.cos(5*a)),
                       1.85 * r * math.sin(a) * (1 + .11 * math.cos(4*a)+.045*math.sin(9*a)),
                       z + min(.7, 1-r) * (.045 * math.sin(5*a + r*8) + rng.uniform(-.028, .028)))
                      for a in angles])
    shelf = loft("Bare earth, heaved out of the seam", rings, "forest_soil")
    for poly in shelf.data.polygons:
        poly.use_smooth = len(poly.vertices) == 4

    for i, args in enumerate((
            (-.71, .15, 1.12, .85, .61, .34), (.39, .29, 1.28, .73, .48, .08),
            (-1.57, -.19, .73, .56, .36, .52), (.85, -.22, .91, .67, .33, .42),
            (.03, .91, .92, .53, .41, -.27), (-.81, -.57, .67, .36, .24, .19),
            (1.54, .07, .62, .43, .30, .22), (-1.18, .74, .53, .37, .39, 1.10),
            (-1.18,-.88,.47,.30,.155,.51), (.11,-.82,.32,.21,.14,-.26),
            (.72,.73,.34,.28,.29,.63))):
        slab(f"Ruptured limestone shelf {i+1:02}", *args, rng, "canyon_layered")

    for name, base, h, r, lean, phase in (
            ("Main crown", (-.51, .04, .40), 2.68, .52, (-.31, -.09), .48),
            ("Split shoulder", (-.20, .32, .40), 1.76, .34, (.12, .23), .90),
            ("Raking crystal", (.43, -.12, .32), 1.72, .37, (.73, -.18), .25),
            ("Low fork", (.27, -.34, .29), .96, .22, (.43, -.62), 1.2),
            ("Far blade", (-1.05, .55, .31), 1.16, .24, (-.70, .29), .72),
            ("Fissure crystal", (-.39, -.48, .15), .86, .21, (-.22, -.37), .34),
            ("Small counterpoint", (.75, .50, .28), .87, .19, (.48, .32), .88),
            ("Rear needle", (.10, .65, .38), 1.07, .16, (.09, .56), 1.25),
    ):
        crystal(name, base, h, r, lean, phase, rng)

    for i in range(138):
        a, r = rng.uniform(0, math.tau), rng.uniform(.60, .91)
        if i%3:
            a = rng.choice((.58,2.66,4.32,5.72))+rng.gauss(0,.26)
        x, y = r * 2.58 * math.cos(a), r * 1.75 * math.sin(a)
        s = .019+.18*rng.random()**3
        slab(f"Limestone spall {i+1:02}", x, y, s, s * rng.uniform(.39, .99),
             s * rng.uniform(.27, .86), a, rng, "mossy_rock" if i % 7 == 0 else "canyon_layered",
             .025+.14*(1-r))
        if i < 17 and i % 2 == 0:
            crystal(f"Seam splinter {i+1:02}", (x * .69, y * .69, .13), rng.uniform(.11, .23),
                    rng.uniform(.025, .055), (.27 * math.cos(a), .42 * math.sin(a)), a, rng)

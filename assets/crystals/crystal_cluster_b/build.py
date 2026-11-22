"""A violet seam broken through a low fan of limestone and bare earth."""
import math
import random

import bmesh
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
    key = f"Violet / opaque chalcedony facet {variant}"
    if bpy.data.materials.get(key):
        return bpy.data.materials[key]
    mat = vrmat.get("violet_crystal").copy()
    mat.name = key
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    for node in list(nodes):
        if node.type not in {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}:
            nodes.remove(node)
    bsdf.inputs["Roughness"].default_value = (.34,.29,.26,.32,.27,.31)[variant]
    bsdf.inputs["Coat Weight"].default_value = .055
    bsdf.inputs["Specular IOR Level"].default_value = .31
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "inclusions"

    def scalar(operation, a, b):
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        for socket,value in zip(node.inputs,(a,b)):
            if isinstance(value,(float,int)):
                socket.default_value = value
            else:
                links.new(value,socket)
        return node.outputs[0]

    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 14
    links.new(coord,grain.inputs["Vector"])
    field = scalar("ADD",attr.outputs["Fac"],scalar("MULTIPLY",grain.outputs["Fac"],.11))
    palette = vrmat.load_palette()
    r,g,b = palette["violet_body"]["linear_rgb"]
    gain = (.20,.49,.76,.31,.60,.39)[variant]
    dark = (r*gain*1.26,g*gain*.80,b*gain*.76,1)
    band = (r*(gain*.72+.34)*1.48,g*(gain*.70+.38),b*(gain*.63+.26)*.85,1)
    color = nodes.new("ShaderNodeValToRGB")
    color.color_ramp.elements[0].position = .09
    color.color_ramp.elements[0].color = dark
    color.color_ramp.elements[1].position = .94
    color.color_ramp.elements[1].color = band
    links.new(field,color.inputs[0])
    links.new(color.outputs["Color"],bsdf.inputs["Base Color"])
    links.new(color.outputs["Color"],bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = .025
    return mat


def cleft_material(edge):
    key = "Violet / healed fracture" if edge else "Violet / mineral seam"
    if bpy.data.materials.get(key):
        return bpy.data.materials[key]
    mat = mineral_finish(0).copy()
    mat.name = key
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    for name in ("Base Color","Emission Color"):
        socket = bsdf.inputs[name]
        nt.links.remove(socket.links[0])
    bsdf.inputs["Base Color"].default_value = (.039,.009,.066,1) if edge else (.28,.067,.38,1)
    bsdf.inputs["Emission Color"].default_value = (.63,.16,.73,1)
    bsdf.inputs["Emission Strength"].default_value = .0 if edge else .51
    return mat


def fissures(name, rotation, rings, radius, sections, sides, phase):
    corners = len(rings[0])
    verts, faces, tones = [], [], []
    for i,side in enumerate(sides):
        right = (side+1)%corners
        a,b = rings[sections[i]][side],rings[sections[i]][right]
        c,d = rings[sections[i]+1][side],rings[sections[i]+1][right]
        normal = (b-a).cross(c-a).normalized()
        start = len(verts)
        for j in range(23):
            t = j/22
            s = .13+.77*t
            w = .22+.52*t+.19*math.sin(math.pi*t)+.035*math.sin(t*23+phase)
            width = (.011+.055*math.sin(math.pi*t))*(.82+.18*math.cos(t*31))
            for shift in (-1,-.38,.38,1):
                u = w+width*shift
                verts.append(a.lerp(b,u).lerp(c.lerp(d,u),s)+normal*radius*.003)
            if j:
                k = start+j*4
                for m in range(3):
                    faces.append((k-4+m,k-3+m,k+1+m,k+m))
                    tones.append(int(m!=1))
    data = bpy.data.meshes.new(name+" fracture mineralization")
    data.from_pydata(verts,[],faces)
    data.update()
    data.materials.append(cleft_material(False))
    data.materials.append(cleft_material(True))
    for poly,tone in zip(data.polygons,tones):
        poly.material_index = tone
    fissure = vrlib.link_to_source(bpy.data.objects.new(data.name,data))
    fissure.matrix_world = rotation


def prismatic_growth(name, base, height, radius, lean, phase, rng, outline_kind=0, broken=False):
    axis = Vector((*lean,1)).normalized()
    u = Vector((0,1,0)).cross(axis).normalized()
    v = axis.cross(u)
    rotation = Matrix((u,v,axis)).transposed().to_4x4()
    rotation.translation = Vector(base)
    corners = 4 if outline_kind==2 else 6
    profile = [Vector((radius*math.cos(phase+i*math.tau/corners),
                       radius*math.sin(phase+i*math.tau/corners)*(.63 if outline_kind else .88),0))
               for i in range(corners)]
    first = rng.uniform(.22,.40)
    second = rng.uniform(.49,.66)
    shift = rng.choice((-1,1))
    levels = (
        (0,.80,0,0),(.085,1,0,0),
        (first,1,0,.013),(first+.032,.90,.048*shift,.013),
        (second,.90,.048*shift,.019),(second+.048,.76,-.027*shift,.019),
        (.78,.76,-.027*shift,.037),(.89,.51,.08,.026))
    rings = []
    for k,(f,s,drift,rake) in enumerate(levels):
        ring = [p*s+Vector((radius*drift,0,height*(f+rake*math.sin(i*math.tau/corners+phase))))
                for i,p in enumerate(profile)]
        rings.append(ring)
    if broken:
        rings.append([p*.33+Vector((radius*.18,-radius*.08,
                      height*(.97+.035*math.cos(i*math.tau/corners+phase))))
                      for i,p in enumerate(profile)])
    else:
        rings.append([Vector((radius*.27,-radius*.035,height))])
    ob = loft(name,rings,mineral_finish(0),min(.005,radius*.016))
    ob.matrix_world = rotation
    for tone in range(1,6):
        ob.data.materials.append(mineral_finish(tone))
    for poly in ob.data.polygons[1:]:
        row,col = divmod(poly.index-1,corners)
        poly.material_index = ((col*5+int(phase*2))%6 if row<6 else
                               (col*3+row+int(phase*3))%6)
        if broken and row == len(rings)-1:
            poly.material_index = 4

    # An opaque section of the growth volume: oblique shells narrow into the stone at each end.
    # A mesh attribute keeps their buried, curved silhouettes independent of the outer growth steps.
    if height>=.34:
        mesh_data = ob.data
        bm = bmesh.new()
        bm.from_mesh(mesh_data)
        bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=11 if radius>=.2 else 4,
                                  use_grid_fill=True)
        layer = bm.verts.layers.float.new("inclusions")
        pools = [(rng.uniform(.24,.35),.011,.42), (rng.uniform(.44,.55),.028,.86),
                 (rng.uniform(.65,.76),.020,.66),(.91,.014,.32)]
        for vertex in bm.verts:
            x,y,z = vertex.co
            ax = z/height
            across = (x*.81+y*.55)/radius
            depth = (x*-.55+y*.81)/radius
            envelope = max(.0,1.05-across*across*.92)
            field = 0
            for center,width,gain in pools:
                dist = abs(ax-center-depth*.064-across*across*.058)
                field = max(field,gain*envelope*max(0,1-dist/(width*(.35+.65*envelope))))
            vertex[layer] = field
        bm.to_mesh(mesh_data)
        bm.free()
        mesh_data.update()

    if radius>=.20:
        target = math.radians(20)
        camera = Vector((math.cos(target),math.sin(target),.23))
        face_order = sorted(range(corners),key=lambda i:camera.dot(rotation.to_3x3() @
                            (profile[i]+profile[(i+1)%corners]).normalized()),reverse=True)
        fissures(name,rotation,rings,radius,(1,3,5),(face_order[0],face_order[1],face_order[0]),phase)


def crystal(name, base, height, radius, lean, phase, rng, broken=False):
    prismatic_growth(name,base,height,radius,lean,phase,rng,2 if "Raking" in name else int(radius<.37),broken)


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
        crystal(name, base, h, r, lean, phase, rng, name in {"Main crown","Raking crystal","Far blade"})

    for i,(x,y,z,lean) in enumerate(((-.86,-.42,.44,(-.38,-.52)),(-.69,-.52,.36,(-.19,-.70)),
                                    (-.50,-.59,.31,(.22,-.76)),(.67,.21,.36,(.48,-.08)),
                                    (.77,.29,.35,(.79,.14)),(.92,.25,.30,(.67,-.25)))):
        crystal(f"Exposed seam pricket {i+1}",(x,y,z),rng.uniform(.24,.46),
                rng.uniform(.060,.103),lean,rng.uniform(0,math.tau),rng,i%3==0)

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

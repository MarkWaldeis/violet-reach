"""Two flights of stepped limestone rise to an open-ended spillway terrace."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    if name in ("mossy_rock", "dirt_path", "grass_ground"):
        return vrmat.get(name)
    local_name = f"stair_terrace_a.{name}"
    mat = bpy.data.materials.get(local_name)
    if mat is not None:
        return mat
    mat = vrmat.get(name).copy()
    mat.name = local_name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]
    cool = tuple(c*k for c,k in zip(cream, (.88, .94, 1.065)))
    pale = tuple(c*k for c,k in zip(cream, (1.035, 1.001, .945)))
    seam = palette["stone_weathered"]["linear_rgb"]
    coords = next(node for node in nodes if node.type == "TEX_COORD").outputs["Object"]

    def noise(scale, detail, vector=coords):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(source, low, high, colors):
        node = nodes.new("ShaderNodeValToRGB")
        for stop, pos, color in zip(node.color_ramp.elements, (low, high), colors):
            stop.position, stop.color = pos, (*color, 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, a, b):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, float):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, value in zip(node.inputs[1:3], (a,b)):
            if isinstance(value, tuple):
                socket.default_value = (*value,1)
            else:
                links.new(value, socket)
        return node.outputs["Color"]

    variation = noise(.87, 3)
    tone = ramp(variation, .23, .79, (cool, pale))
    random_tone = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(.18, tone, ramp(random_tone, 0, 1, (cool, pale)))
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    old = name == "monument_weathered"
    ao.inputs["Distance"].default_value = .19 if old else .065
    joint = tuple(.74*a+.26*b for a,b in zip(seam, cream))
    tone = mix(ao.outputs["AO"], joint, tone)
    if old:
        patina = palette["monument_shadow"]["linear_rgb"]
        weathered = tuple(.38*a+.62*b for a,b in zip(seam,patina))
        tone = mix(.48, tone, ramp(noise(2.3, 3), .28, .68, (weathered, pale)))
    stretch = nodes.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (5.2, 5.2, .62)
    links.new(coords, stretch.inputs[0])
    runoff = nodes.new("ShaderNodeAttribute")
    runoff.attribute_name = "coping_runoff"
    stain = tuple(.40*a+.60*b for a,b in zip(seam, palette["monument_shadow"]["linear_rgb"]))
    streaked = mix(ramp(noise(1, 3, stretch.outputs["Vector"]), .44, .74, ((0,0,0),(.91,.91,.91))), tone, stain)
    tone = mix(runoff.outputs["Fac"], tone, streaked)
    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), .16, .86, ((.72,.72,.72),(.93,.93,.93))), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .023
    bump.inputs["Strength"].default_value = .42
    links.new(noise(10, 2), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return mat


def tread_mesh(bounds, chip, damaged_edge, sink):
    x0, x1, y0, y1, bottom, top = bounds
    depth = y1-y0
    min_surface_z = bottom+.035
    site = .18+.63*abs(math.sin(17*y0+5*x0))
    samples = sorted({*(j/64 for j in range(65)),
                      *(v for v in (site-.105,site,site+.105) if abs(64*v-round(64*v))>.14)})
    vertices = []
    for v in samples:
        x = x0+(x1-x0)*v
        lane = math.exp(-((x-.14-.17*math.sin(y0))/1.48)**2)
        edge_loss = chip * max(0, 1-abs(v-site)/.105)
        radius = .045+.032*lane
        nose = radius/depth
        surface=[]
        for j in range(25):
            t=1-(1-nose)*j/24
            dip=.10*lane*math.sin(math.pi*(1-t)/1.49)**2
            noise=lane*(.005*math.sin(12*x+7*t+y0)+.0016*math.sin(31*x+21*t))
            surface.append((t,top-dip+noise-edge_loss*max(0,1-t/.42)*.49))
        for j in range(1,11):
            angle=math.pi*j/20
            t=nose*(1-math.sin(angle))
            surface.append((t,surface[24][1]-radius*(1-math.cos(angle))-.28*edge_loss*math.sin(angle)))
        section = ((0, bottom), (1, bottom)) + tuple((t, max(z, min_surface_z)) for t, z in surface)
        for t, z in section:
            edge_weight = max(0, 1-4*(v if damaged_edge == -1 else 1-v)) if damaged_edge else 0
            front_spall = max(0, 1 - t/.41)*edge_loss
            crack = edge_weight*.029*(2*(t+front_spall/depth)-1)
            vertices.append((x+crack, y0+t*depth+front_spall, z-sink))
    n = len(section)
    faces = [tuple(reversed(range(n)))]
    for row in range(len(samples)-1):
        for i in range(n):
            a, b = row*n+i, row*n+(i+1)%n
            faces.append((a,b,b+n,a+n))
    faces.append(tuple(range(len(vertices)-n,len(vertices))))
    return vertices, faces, n


def ashlar(name, bounds, rng, stone, wear=.022, chip=0, coping_z=None):
    x0, x1, y0, y1, z0, z1 = bounds
    chip = max(chip, min(.026 + .012*abs(math.sin(4*x0 + 7*y0 + 13*z0)), (z1-z0)*.19))
    chamfer = min(wear * 1.9, (z1 - z0) * .22)
    footprint = [(x0 + chamfer, y0), (x1 - chamfer, y0), (x1, y0 + chamfer),
                 (x1, y1 - chamfer), (x1 - chamfer, y1), (x0 + chamfer, y1),
                 (x0, y1 - chamfer), (x0, y0 + chamfer)]
    corners = [(x + rng.uniform(-wear, wear) * .5, y + rng.uniform(-wear, wear) * .5)
               for x, y in footprint]
    n = len(corners)
    vertices = [(x, y, z0) for x, y in corners]
    notch = int(abs(x0*17+y0*23+z0*31)) % n
    vertices += [(x + rng.uniform(-wear, wear)*.31 + (.07*(x0+x1-2*x) if i == notch else 0),
                  y + rng.uniform(-wear, wear)*.37 + (.07*(y0+y1-2*y) if i == notch else 0),
                  z1 - (chip if i == notch else 0)) for i,(x, y) in enumerate(corners)]
    faces = [tuple(reversed(range(n)))]
    for i in range(n):
        a, b = i, (i+1)%n
        faces.append((a,b,b+n,a+n))
    faces.append(tuple(range(n,len(vertices))))
    obj = masonry(name, vertices, faces, stone, coping_z)
    bevel = obj.modifiers.new("Soft quarry edges", "BEVEL")
    bevel.width, bevel.segments = wear*.51, 2
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(20)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


def masonry(name, vertices, faces, stone, coping_z=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone) if stone == "mossy_rock" else limestone(stone))
    if coping_z is not None:
        runoff = mesh.attributes.new("coping_runoff", "FLOAT", "POINT")
        runoff.data.foreach_set("value", [max(0, min(1, 1-(coping_z-z)/1.68)) for _,_,z in vertices])
    return obj


def build():
    rng = random.Random(251553)
    white, old = "monument_white", "monument_weathered"
    rise = 6 / 34
    tread = .42
    start = -10.22
    lower_end = start + 17 * tread
    upper_start = lower_end + 2.04
    upper_end = upper_start + 17 * tread
    back = 10.22

    def course(label, cuts, y0, y1, bottom, top, worn=False, step=None):
        bed_top = top-.201 if step is not None else top-.075
        if bed_top-bottom > .023:
            ashlar(f"{label} recessed bearing", (cuts[0]+.038,cuts[-1]-.038,
                                                y0+.025,y1-.026,bottom,bed_top),
                   rng,white,.013)
        for k, (x0, x1) in enumerate(zip(cuts, cuts[1:])):
            name = f"{label} slab {k}"
            if step is None:
                ashlar(name, (x0+.008,x1-.008,y0,y1,top-.115,top), rng, white, .021 if worn else .013)
                continue
            broken = (step, k) in ((2,0),(8,1),(14,2),(21,1),(29,0))
            sunken = (step, k) in ((5,0),(12,2),(25,0),(30,2))
            crack = x0+(x1-x0)*.64
            pieces = ((x0+.008, crack-.021, 1), (crack+.021, x1-.008, -1)) if broken else (
                (x0+.008,x1-.008,0),)
            for i, (left, right, edge) in enumerate(pieces):
                drift = .057 if sunken or (broken and i == 1) else 0
                sink = .021 if sunken or (broken and i == 1) else 0
                chip = .138 if broken else .040+.077*abs(math.sin(step*2.8+k*1.7))
                bounds = (left, right, y0+drift, y1, top-.191, top)
                vertices, faces, n = tread_mesh(bounds, chip, edge, sink)
                obj = masonry(f"{name} piece {i}" if broken else name, vertices, faces, white)
                for face in obj.data.polygons[1:-1]:
                    face.use_smooth = 2 <= (face.index-1)%n < n-1
                obj.data.set_sharp_from_angle(angle=math.radians(36))

    ashlar("Buried stair foundation", (-3.54,3.54,start+.008,upper_end+.02,-.19,-.008), rng, old,.018)
    ashlar("Buried summit foundation", (-5.61,5.61,upper_end-.03,back,-.19,.24), rng, old,.021)
    for j in range(34):
        y = (start if j < 17 else upper_start) + (j % 17) * tread
        cuts = (-3.48, -1.12 + rng.uniform(-.28, .27), 1.10 + rng.uniform(-.26, .25), 3.48)
        course(f"Riser {j + 1:02}", cuts, y, y + tread, -.028, (j + 1) * rise, j % 6 == 0, step=j)
    for j in range(4):
        y = lower_end + j * .51
        course(f"Rest landing bay {j}", (-3.48, -1.76, -.42 + .23 * (j % 2), 1.47, 3.48),
               y, y + .51, 0, 3, j % 2 == 0)
    for j in range(5):
        y0 = upper_end + (back - upper_end) * j / 5
        y1 = upper_end + (back - upper_end) * (j + 1) / 5
        shift = .23 if j % 2 else -.21
        course(f"Summit terrace bay {j}", (-5.26, -3.50, -1.72 + shift, .15 - shift, 2.05 + shift, 3.5, 5.26),
               y0, y1, 0, 6, j in (0, 4))
    ashlar("Pale summit joint bedding",(-5.26,5.26,upper_end,back,5.783,5.90),
           rng,white,.01)

    # The broad retaining cheeks step back in plan, leaving the treads and upper terrace open.
    cheek = [
        (start + .29, start + 2.71, 1.30, 4.53),
        (start + 2.71, start + 5.19, 2.38, 4.95),
        (start + 5.19, lower_end + .62, 3.44, 5.29),
        (lower_end + .62, upper_start + 1.50, 4.13, 5.29),
        (upper_start + 1.50, upper_start + 3.91, 5.12, 5.48),
        (upper_start + 3.91, upper_end, 6.33, 5.64),
        (upper_end, back, 6.33, 5.62),
    ]
    for sign, side in ((-1, "west"), (1, "east")):
        for j, (y0, y1, ceiling, outer) in enumerate(cheek):
            layers = math.ceil(ceiling / .79)
            ribs = (0,*sorted(row/layers + rng.uniform(-.053,.053) for row in range(1,layers)),1)
            for row in range(layers):
                bottom, top = ceiling*ribs[row], ceiling*ribs[row+1]
                split = y0 + (y1 - y0) * (.42 if (row + j) % 2 else .59)
                x1 = outer - .057 * row - (.08 if row > 0 and row != layers - 1 else 0)
                a,b=sorted((sign*3.45,sign*(x1-.095)))
                ashlar(f"{side} solid pale joint backing {j} course {row}",
                       (a,b,y0-.021,y1+.022,-.14 if row==0 else bottom-.018,top+.02),
                       rng,white,.007)
                for i, (a, b) in enumerate(((y0, split), (split, y1))):
                    lo, hi = sorted((sign * 3.45, sign * x1))
                    ashlar(f"{side} cheek {j} course {row} block {i}",
                           (lo, hi, a+.011, b-.011, -.028 if row==0 else bottom+.011, top),
                           rng, old if row == 0 else white, .033,
                           chip=.11 if (j+row+i)%7==4 else 0, coping_z=ceiling)
            foot_lo, foot_hi = sorted((sign*3.43,sign*(outer+.16)))
            ashlar(f"{side} projecting foot course {j}",
                   (foot_lo,foot_hi,y0-.022,y1-.015,-.044,.30),rng,old,.031)
            shoulder = outer - .057 * (layers - 1)
            for part, low, high, projection in (
                    ("recessed fascia", -.38, -.19, .11), ("drip lip", -.19, -.075, .23),
                    ("coping", -.075, .12, .34)):
                lo, hi = sorted((sign*3.40, sign*(shoulder+projection)))
                seam = y0 + (y1-y0)*(.41 if j%2 else .56)
                for i, (a, b) in enumerate(((y0, seam), (seam, y1))):
                    ashlar(f"{side} {part} {j} block {i}", (lo, hi, a+.012, b-.012, ceiling+low, ceiling+high),
                           rng, white, .031, chip=.116 if part == "coping" and (j+i)%3==1 else 0,
                           coping_z=ceiling+.16 if part == "recessed fascia" else None)
            if j in (1,2,3,5,6):
                at = y0+(y1-y0)*.32
                for k,(lo_z,hi_z,span) in enumerate((
                    (-.04,.38,.86),(.37,ceiling*.34,.64),(ceiling*.33,ceiling*.63,.49),
                    (ceiling*.62,ceiling*.79,.36),(ceiling*.785,ceiling*.86,.45))):
                    a,b=sorted((sign*(outer-.67),sign*(outer+span)))
                    ashlar(f"{side} raked spur {j} bed {k}",(a,b,at-.36+.027*k,at+.39-.035*k,lo_z,hi_z),
                           rng,old if k==0 else white,.023)
    ashlar("Rear solid pale backing",(-5.56,5.56,back-.43,back-.027,-.17,6.0),rng,white,.007)
    for i,(x0,x1) in enumerate(((-5.57,-3.21),(-3.21,-1.01),(-1.01,1.73),(1.73,3.67),(3.67,5.57))):
        for j,(z0,z1) in enumerate(((-.043,.29),(.279,1.03),(1.05,2.27),(2.29,3.03),(3.05,4.12),
                                    (4.14,5.39),(5.41,5.94))):
            f=.11 if j==0 else .005
            ashlar(f"Back bearing face bay {i} course {j}",(x0+.012-f,x1-.012+f,back-.32,back+f,z0,z1),
                   rng,old if j==0 else white,.021,chip=.061 if (i+j)%7==4 else 0, coping_z=6.04)
    for j,x in enumerate((-4.73,-2.41,.03,2.60,4.77)):
        ashlar(f"Rear pilaster buried plinth {j}",(x-.56,x+.56,back-.16,back+.77,-.19,.37),rng,old,.041)
        levels=(.34,1.48,2.87,3.98,5.17,5.78)
        for k,(lo,hi) in enumerate(zip(levels,levels[1:])):
            w=.48-.034*k
            ashlar(f"Rear pilaster {j} course {k}",(x-w,x+w,back-.14,back+.65-.063*k,lo,hi),
                   rng,white,.039,chip=.14 if (j+k)%5==0 else 0,coping_z=5.98)
        ashlar(f"Rear pilaster {j} head",(x-.57,x+.57,back-.24,back+.68,5.76,6.15),
               rng,white,.036,chip=.116 if j%2 else 0)
    for seed,(x,y) in enumerate(((4.58,start+1.08),(5.10,start+4),(-5.39,lower_end-.14),
                                  (-5.73,upper_end-.22),(-4.8,back+.71),(.73,back+.09),(2.63,back+.65))):
        for i in range(12):
            u,v = x+rng.uniform(-.15,.15), y+rng.uniform(-.22,.22)
            ashlar(f"Foot joint moss cluster {seed} fragment {i}",
                   (u,u+.12,v,v+.17,-.11,rng.uniform(.034,.12)),rng,
                   "mossy_rock" if i%3 else "dirt_path",.009)
    for i,(step,x) in enumerate(((2,-3.34),(7,3.35),(13,-3.35),(20,3.35),(26,3.34),(32,-3.36))):
        y=(start if step < 17 else upper_start)+(step%17)*tread+.028
        z=(step+1)*rise-.065
        for j in range(9):
            angle=rng.uniform(0,math.tau)
            height=rng.uniform(.15,.29)
            dx,dy=math.cos(angle),math.sin(angle)
            vertices=[]
            for h,lean,w in ((-.065,0,.013),(height*.65,height*.25,.022),(height,height*.58,.002)):
                a,b=x+lean*dx,y+lean*dy
                vertices.extend(((a+w*dx,b+w*dy,z+h),(a-w*dy,b+w*dx,z+h),
                                 (a-.62*w*dx+.74*w*dy,b-.62*w*dy-.74*w*dx,z+h)))
            faces=[(2,1,0)]+[(k*3+a,k*3+(a+1)%3,(k+1)*3+(a+1)%3,(k+1)*3+a)
                             for k in range(2) for a in range(3)]+[(6,7,8)]
            masonry(f"Joint grass {i} blade {j}",vertices,faces,"grass_ground")

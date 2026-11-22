"""Two flights of stepped limestone rise to an open-ended spillway terrace."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    local_name = f"stair_terrace_a.{name}"
    mat = bpy.data.materials.get(local_name)
    if mat is not None:
        return mat
    mat = vrmat.get(name).copy()
    mat.name = local_name
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    surface = nodes["Principled BSDF"]
    weathered = name == "monument_weathered"
    palette = vrmat.load_palette()
    white = palette["monument_white"]["linear_rgb"]
    patina = palette["stone_weathered"]["linear_rgb"]
    coords = next(n for n in nodes if n.type == "TEX_COORD").outputs["Object"]
    grain_scale = 1

    def noise(scale, detail, vector=coords):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(source, lo, hi, low, high):
        node = nodes.new("ShaderNodeValToRGB")
        for stop, position, color in zip(node.color_ramp.elements, (lo, hi), (low, high)):
            stop.position = position
            stop.color = (*(color if isinstance(color, tuple) else (color,) * 3), 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, first, second, blend="MIX"):
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = blend
        if isinstance(factor, (int, float)):
            node.inputs["Fac"].default_value = factor
        else:
            links.new(factor, node.inputs["Fac"])
        for value, socket in zip((first, second), ("Color1", "Color2")):
            if isinstance(value, tuple):
                node.inputs[socket].default_value = (*value, 1)
            else:
                links.new(value, node.inputs[socket])
        return node.outputs["Color"]

    cool = tuple(c * k for c, k in zip(white, (.94, .974, 1.020)))
    cream = tuple(c * k for c, k in zip(white, (1.005, .965, .895)))
    temperature = noise(.34 * grain_scale, 2)
    tone = ramp(temperature, .15, .86, cool, cream)
    random_tint = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(.24, tone, ramp(random_tint, 0, 1, cream, cool))

    pores = next(n for n in nodes if n.type == "TEX_VORONOI")
    pores.inputs["Scale"].default_value = 27 * grain_scale
    grain = noise(13 * grain_scale, 2)
    clusters = ramp(noise(3.4 * grain_scale, 3), .29, .66, .10, .96)
    coarse_pits = ramp(pores.outputs["Distance"], .10, .30, .43, 1)
    fine_cells = nodes.new("ShaderNodeTexVoronoi")
    fine_cells.inputs["Scale"].default_value = 84 * grain_scale
    links.new(coords, fine_cells.inputs["Vector"])
    fine_pits = ramp(fine_cells.outputs["Distance"], .08, .24, .60, 1)
    pits = mix(clusters, fine_pits, coarse_pits)
    deposits = ramp(grain, .23, .79, .80, 1)
    tone = mix(.72, tone, mix(.54, deposits, pits, "MULTIPLY"), "MULTIPLY")

    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 6
    ao.inputs["Distance"].default_value = (.36 if weathered else .19) / grain_scale
    strength = .68 if weathered else .36
    grime = tuple(a * (1-strength) + b * strength for a, b in zip(white, patina))
    tone = mix(ao.outputs["AO"], grime, tone)
    stretch = nodes.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (9.5, 9.5, .69)
    links.new(coords, stretch.inputs[0])
    runoff = noise(1, 3, stretch.outputs["Vector"])
    envelope = nodes.new("ShaderNodeAttribute")
    envelope.attribute_name = "coping_runoff"
    streaks = mix(envelope.outputs["Fac"], (0, 0, 0), ramp(runoff, .43, .63, 0, .94))
    mineral_stain = tuple(a*.30+b*.70 for a, b in zip(patina, palette["monument_shadow"]["linear_rgb"]))
    links.new(mix(streaks, tone, mineral_stain), surface.inputs["Base Color"])
    links.new(ramp(grain, .22, .79, .65, .96), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .29

    def bump(height, depth, strength):
        node = nodes.new("ShaderNodeBump")
        node.inputs["Distance"].default_value = depth / grain_scale
        node.inputs["Strength"].default_value = strength
        links.new(height, node.inputs["Height"])
        return node

    sand = bump(noise(69 * grain_scale, 2), .006, .58)
    etch = bump(mix(.78, grain, pits, "MULTIPLY"), .035, .8)
    links.new(sand.outputs["Normal"], etch.inputs["Normal"])
    links.new(etch.outputs["Normal"], surface.inputs["Normal"])
    return mat


def tread_mesh(bounds, chip, damaged_edge, sink):
    x0, x1, y0, y1, bottom, top = bounds
    depth = y1-y0
    min_surface_z = bottom+.035
    site = .18+.63*abs(math.sin(17*y0+5*x0))
    samples = sorted(set((0, .025, .08, .20, .34, .46, .57, .69, .82, .94, .98, 1,
                          site-.075, site, site+.085)))
    vertices = []
    for v in samples:
        x = x0+(x1-x0)*v
        lane = math.exp(-((x-.14)/1.55)**2)
        scuff = lane*(.79+.21*math.cos(11*y0+.89*x))
        edge_loss = chip * max(0, 1-abs(v-site)/.085)
        eased = .011+.021*lane
        surface = (
            (1, top-.003), (.79, top-.012*scuff),
            (.61, top-.017*scuff), (.44, top-.037*scuff), (.26, top-.059*scuff),
            (.12, top-.051*scuff-.27*edge_loss),
            (.055, top-.046*scuff-eased-.55*edge_loss),
            (.016, top-.037-eased-.71*edge_loss),
            (0, top-.070-.23*edge_loss),
        )
        section = ((0, bottom), (1, bottom)) + tuple((t, max(z, min_surface_z)) for t, z in surface)
        for t, z in section:
            edge_weight = max(0, 1-4*(v if damaged_edge == -1 else 1-v)) if damaged_edge else 0
            crack = edge_weight*(.027*math.sin(6.2*t)+.020*t)
            front_spall = max(0, 1 - t/.41)*edge_loss
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
        ashlar(f"{label} recessed bearing", (cuts[0] + .038, cuts[-1] - .038,
                                            y0 + .025, y1 - .026, bottom, top - .075),
               rng, old, .013)
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
                sink = .040 if sunken or (broken and i == 1) else 0
                chip = .113 if broken else .033+.042*abs(math.sin(step*2.8+k*1.7))
                bounds = (left, right, y0+drift, y1, top-.133, top)
                vertices, faces, n = tread_mesh(bounds, chip, edge, sink)
                obj = masonry(f"{name} piece {i}" if broken else name, vertices, faces, white)
                for face in obj.data.polygons[1:-1]:
                    face.use_smooth = 2 <= (face.index-1)%n <= 9
                obj.data.set_sharp_from_angle(angle=math.radians(36))

    ashlar("Buried stair foundation", (-3.54,3.54,start+.008,upper_end+.02,-.045,.073), rng, old,.018)
    ashlar("Buried summit foundation", (-5.61,5.61,upper_end-.03,back,-.045,.24), rng, old,.021)
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
                for i, (a, b) in enumerate(((y0, split), (split, y1))):
                    x1 = outer - .057 * row - (.08 if row > 0 and row != layers - 1 else 0)
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
                    ashlar(f"{side} {part} {j} block {i}", (lo, hi, a+.018, b-.018, ceiling+low, ceiling+high),
                           rng, white, .031, chip=.085 if part == "coping" and (j+i)%3==1 else 0,
                           coping_z=ceiling+.16 if part == "recessed fascia" else None)
            if j in (1,2,3,5,6):
                at = y0+(y1-y0)*.32
                for k,(lo_z,hi_z,span) in enumerate((
                    (-.04,.38,.86),(.37,ceiling*.34,.64),(ceiling*.33,ceiling*.63,.49),
                    (ceiling*.62,ceiling*.79,.36),(ceiling*.785,ceiling*.86,.45))):
                    a,b=sorted((sign*(outer-.67),sign*(outer+span)))
                    ashlar(f"{side} raked spur {j} bed {k}",(a,b,at-.36+.027*k,at+.39-.035*k,lo_z,hi_z),
                           rng,old if k==0 else white,.023)
    for i,(x0,x1) in enumerate(((-5.57,-3.21),(-3.21,-1.01),(-1.01,1.73),(1.73,3.67),(3.67,5.57))):
        for j,(z0,z1) in enumerate(((-.043,.29),(.279,1.03),(1.05,2.27),(2.29,3.03),(3.05,4.12),
                                    (4.14,5.39),(5.41,5.94))):
            f=.11 if j==0 else .005
            ashlar(f"Back bearing face bay {i} course {j}",(x0+.012-f,x1-.012+f,back-.32,back+f,z0,z1),
                   rng,old if j==0 else white,.021,chip=.061 if (i+j)%7==4 else 0, coping_z=6.04)
    for seed,(x,y) in enumerate(((4.7,start+1.08),(5.47,lower_end-.14),(-5.64,upper_end-.22))):
        for i in range(7):
            u,v = x+rng.uniform(-.030,.030), y+rng.uniform(-.18,.18)
            ashlar(f"Foot joint moss cluster {seed} fragment {i}",
                   (u,u+.052,v,v+.078,-.009,rng.uniform(.016,.051)),rng,"mossy_rock",.003)

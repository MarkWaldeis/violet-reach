"""Two flights of stepped limestone rise to an open-ended spillway terrace."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    mat = vrmat.get(name)
    if mat.get("quarried_finish"):
        return mat
    mat["quarried_finish"] = True
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    surface = nodes["Principled BSDF"]
    weathered = name == "monument_weathered"
    palette = vrmat.load_palette()
    white = palette["monument_white"]["linear_rgb"]
    patina = palette["stone_weathered"]["linear_rgb"]
    pores = next(n for n in nodes if n.type == "TEX_VORONOI")
    pores.inputs["Scale"].default_value = 32
    grain = nodes.new("ShaderNodeValToRGB")
    grain.color_ramp.elements[0].position = .11
    grain.color_ramp.elements[0].color = (*(v * .74 for v in white), 1)
    grain.color_ramp.elements[1].position = .34
    grain.color_ramp.elements[1].color = (*white, 1)
    links.new(pores.outputs["Distance"], grain.inputs["Fac"])
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = .31 if weathered else .14
    tone = nodes.new("ShaderNodeMixRGB")
    strength = .68 if weathered else .34
    tone.inputs["Color1"].default_value = (*(a * (1-strength) + b * strength for a, b in zip(white, patina)), 1)
    links.new(ao.outputs["AO"], tone.inputs["Fac"])
    links.new(grain.outputs["Color"], tone.inputs["Color2"])
    links.new(tone.outputs["Color"], surface.inputs["Base Color"])
    bump = surface.inputs["Normal"].links[0].from_node
    bump.inputs["Strength"].default_value = .67
    bump.inputs["Distance"].default_value = .021
    roughness = surface.inputs["Roughness"].links[0].from_node
    roughness.inputs["To Min"].default_value = .77
    roughness.inputs["To Max"].default_value = .94
    return mat


def ashlar(name, bounds, rng, stone, wear=.022, nosing=0, chip=0):
    x0, x1, y0, y1, z0, z1 = bounds
    chamfer = min(wear * 1.9, (z1 - z0) * .22)
    footprint = [(x0 + chamfer, y0), (x1 - chamfer, y0), (x1, y0 + chamfer),
                 (x1, y1 - chamfer), (x1 - chamfer, y1), (x0 + chamfer, y1),
                 (x0, y1 - chamfer), (x0, y0 + chamfer)]
    corners = [(x + rng.uniform(-wear, wear) * .5, y + rng.uniform(-wear, wear) * .5)
               for x, y in footprint]
    if nosing:
        corners = [corners[0]] + [(x0 + (x1 - x0) * t, y0) for t in (.14,.24,.36,.49,.62,.73,.84)] + corners[1:]
    n = len(corners)
    vertices = [(x, y, z0) for x, y in corners]
    if nosing:
        for height, setback in ((z1-.072,0),(z1-.040,.21),(z1-.018,.55),(z1,1)):
            for i,(x,y) in enumerate(corners):
                front = i < n-6
                lane = math.exp(-(x/1.8)**2)
                loss = (chip * math.exp(-((x-(x0+.19))/(x1-x0)*8)**2)) if front else 0
                vertices.append((x, y + setback * (.008 + .052*lane + loss) if front else y,
                                 height-setback*(.015*lane + .42*loss) if front else height))
    else:
        vertices += [(x + rng.uniform(-wear, wear) * .31, y + rng.uniform(-wear, wear) * .37,
                      z1 - (chip if i == 0 else 0)) for i,(x, y) in enumerate(corners)]
    faces = [tuple(reversed(range(n)))]
    for ring in range(len(vertices)//n-1):
        for i in range(n):
            a, b = ring*n+i, ring*n+(i+1)%n
            faces.append((a,b,b+n,a+n))
    top = len(vertices)-n
    if nosing:
        for i in range(n-6):
            faces.append((top+i,top+i+1,top+n-3))
        faces.extend(((top+n-6,top+n-5,top+n-4,top+n-3),
                      (top,top+n-3,top+n-2,top+n-1)))
    else:
        faces.append(tuple(range(top,len(vertices))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone) if stone == "mossy_rock" else limestone(stone))
    bevel = obj.modifiers.new("Soft quarry edges", "BEVEL")
    bevel.width, bevel.segments = wear * (.30 if nosing else .51), 2
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(20)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


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
            broken = .068 if (step, k) in ((2,0),(8,1),(14,2),(21,1),(29,0)) else 0
            drift = .013 if (step,k) in ((8,1),(21,1)) else 0
            ashlar(f"{label} slab {k}", (x0+.008,x1-.008,y0+drift,y1,top-.115,top),
                   rng, white, .021 if worn else .013, nosing=step is not None, chip=broken)

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
                           chip=.085 if (j+row+i)%9==4 else 0)
            foot_lo, foot_hi = sorted((sign*3.43,sign*(outer+.16)))
            ashlar(f"{side} projecting foot course {j}",
                   (foot_lo,foot_hi,y0-.022,y1-.015,-.044,.30),rng,old,.031)
            lo, hi = sorted((sign * 3.40, sign * (outer - .057 * (layers - 1) + .18)))
            ashlar(f"{side} copestone {j}", (lo, hi, y0 + .018, y1 - .018, ceiling - .048, ceiling + .095),
                   rng, white, .034, chip=.115 if j in (1,4) else 0)
            if j in (1,3,5,6):
                at = y0+(y1-y0)*.32
                for k,(lo_z,hi_z,span) in enumerate((
                    (-.04,.38,.71),(.37,ceiling*.34,.53),(ceiling*.33,ceiling*.63,.39),
                    (ceiling*.62,ceiling*.79,.28),(ceiling*.785,ceiling*.83,.35))):
                    a,b=sorted((sign*(outer-.67),sign*(outer+span)))
                    ashlar(f"{side} raked spur {j} bed {k}",(a,b,at-.36+.027*k,at+.39-.035*k,lo_z,hi_z),
                           rng,old if k==0 else white,.023)
    for i,(x0,x1) in enumerate(((-5.57,-3.21),(-3.21,-1.01),(-1.01,1.73),(1.73,3.67),(3.67,5.57))):
        for j,(z0,z1) in enumerate(((-.043,.29),(.279,1.03),(1.05,2.27),(2.29,3.03),(3.05,4.12),
                                    (4.14,5.39),(5.41,5.94))):
            f=.11 if j==0 else .005
            ashlar(f"Back bearing face bay {i} course {j}",(x0+.012-f,x1-.012+f,back-.32,back+f,z0,z1),
                   rng,old if j==0 else white,.021,chip=.061 if (i+j)%7==4 else 0)
    for seed,(x,y) in enumerate(((4.7,start+1.08),(5.47,lower_end-.14),(-5.64,upper_end-.22))):
        for i in range(7):
            u,v = x+rng.uniform(-.030,.030), y+rng.uniform(-.18,.18)
            ashlar(f"Foot joint moss cluster {seed} fragment {i}",
                   (u,u+.052,v,v+.078,-.009,rng.uniform(.016,.051)),rng,"mossy_rock",.003)

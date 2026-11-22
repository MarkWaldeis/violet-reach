"""Shinglewake: a 21 m shelf of sand, sorted cobbles and undercut turf.

The lake is a Blender review backdrop only. SOURCE meets runtime water at Z = 0.
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise

import vrlib
import vrmat

SEED = 40871
HALF = 10.6
BOTTOM = -.058
BANK_LENGTH = 6.1


def smooth(v):
    t = min(1, max(0, v))
    return t*t*(3 - 2*t)


def n3(x, y, z):
    return noise.noise(Vector((x, y, z)), noise_basis="PERLIN_ORIGINAL")


def blend(a, b, t):
    return tuple(x + (y-x)*t for x, y in zip(a, b))


def scale(a, factor):
    return tuple(x*factor for x in a)


def waterline(x):
    return .86*(x/HALF)**2 + .36*math.sin(.39*x+.78) - .25*math.sin(.82*x-.45) + .081*math.sin(1.4*x)


def turf_line(x):
    return 3.52 + .29*math.sin(.55*x+1.1) + .23*math.sin(1.08*x) + .16*n3(x*.8, 5, 10)


def bank(x, d):
    q = d - turf_line(x)
    shoal = (BOTTOM+.004)*smooth(-d/.58) if d < 0 else .29*(1-math.exp(-d*.63))
    scarp = (.14 + .08*smooth(.5+n3(x*.5, 4.1, 12))) * smooth((q+.085)/.42)
    swales = .083*n3(x*.44, d*.90, 5) + .038*n3(x*1.7, d*2, 7)
    ripple = .012*math.sin(d*11 + .7*x + 3*n3(x*.55, d*1.1, 21))
    relief = (swales+ripple)*smooth(d/.85) + scarp
    blend_in = smooth((HALF-abs(x))/.88) * smooth((BANK_LENGTH-d)/.97)
    baseline = shoal + relief
    return max(BOTTOM+.001, -.006 + (baseline+.006)*blend_in) if d > .007 else shoal


class Mesh:
    def __init__(self):
        self.verts, self.faces, self.colors, self.factors = [], [], [], []

    def object(self, name, materials, color_name=None, factor_name=None, *, source=True):
        data = bpy.data.meshes.new(name)
        data.from_pydata(self.verts, [], self.faces)
        data.update()
        for mat in materials:
            data.materials.append(mat)
        data.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        if color_name:
            layer = data.color_attributes.new(name=color_name, type="FLOAT_COLOR", domain="POINT")
            layer.data.foreach_set("color", [channel for rgb in self.colors for channel in (*rgb, 1)])
        if factor_name:
            layer = data.attributes.new(name=factor_name, type="FLOAT", domain="POINT")
            layer.data.foreach_set("value", self.factors)
        obj = bpy.data.objects.new(name, data)
        if source:
            return vrlib.link_to_source(obj)
        bpy.context.scene.collection.objects.link(obj)
        obj["vr_review_context"] = True
        obj.hide_render = True
        return obj


def socket_material(base, name, colors, color_weight, factor=None, roughness=None):
    # Library grain still drives the finish; point colours carry the large wet/dry transition.
    m = vrmat.get(base).copy()
    m.name = name
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bsdf = nodes["Principled BSDF"]
    tint = nodes.new("ShaderNodeAttribute")
    tint.attribute_name = colors
    target = bsdf.inputs["Base Color"]
    mineral = nodes.new("ShaderNodeMixRGB")
    mineral.inputs["Fac"].default_value = color_weight
    links.new(target.links[0].from_socket, mineral.inputs[1])
    links.new(tint.outputs["Color"], mineral.inputs[2])
    links.new(mineral.outputs["Color"], target)
    if factor:
        wet = nodes.new("ShaderNodeAttribute")
        wet.attribute_name = factor
        ranges = nodes.new("ShaderNodeMapRange")
        ranges.inputs["To Min"].default_value, ranges.inputs["To Max"].default_value = roughness
        links.new(wet.outputs["Fac"], ranges.inputs["Value"])
        rough = bsdf.inputs["Roughness"]
        variation = nodes.new("ShaderNodeMath")
        variation.operation = "MULTIPLY_ADD"
        links.new(rough.links[0].from_socket, variation.inputs[0])
        variation.inputs[1].default_value = .16
        links.new(ranges.outputs["Result"], variation.inputs[2])
        links.new(variation.outputs[0], rough)
    return m


def sand_color(p, x, d):
    q = d - turf_line(x)
    silt = n3(x*1.03, d*.74, 18)
    warp = .18*n3(x*.48, d*1.8, 20) + .09*n3(x*1.7, d*3, 14)
    wet = 1 - smooth((d-.46+warp)/(.75+.21*math.sin(.76*x)+.24*silt))
    fine = .10*n3(x*3.4, d*4.1, 6)
    dry = scale(blend(p["soil"], p["path_sand"], smooth(.76 + .34*silt + fine)), .96)
    soaked = scale(blend(p["soil"], p["path_sand"], .14+.19*silt), .65)
    color = blend(dry, soaked, wet)
    scarp = smooth((q+.27+warp)/.32)
    turf = smooth((q-.33+.42*silt+warp)/.54)
    moss = n3(x*2.6, d*3.3, 27)
    top = scale(blend(p["moss"], p["grass_green"], smooth(.59+.64*silt+.66*moss)), 1.30 + .38*moss)
    earth = scale(p["soil"], .74+.37*silt)
    bands = .95 + .10*math.sin(23*q + 2.2*n3(x*.85, d*1.2, 6))
    return blend(blend(color, scale(earth, bands), scarp), top, turf), wet


def shore_ground(p):
    m = Mesh()
    nx, nd = 282, 160
    for i in range(nx+1):
        u = 2*i/nx - 1
        for j in range(nd+1):
            t = j/nd
            d = -.61 + (BANK_LENGTH+.61)*t
            d -= .46*abs(u)**4*smooth((d-3.5)/2.6) + .078*math.sin(14*u)*smooth((d-5.4)/.7)
            x = u*(HALF - .34*smooth((d-4.7)/1.4) - .21*smooth(-d/.61))
            m.verts.append((x, waterline(x)+d, bank(x, d)))
            color, wet = sand_color(p, x, d)
            m.colors.append(color)
            m.factors.append(wet)
            if i and j:
                k = i*(nd+1) + j
                m.faces.append((k-nd-2, k-1, k, k-nd-1))

    # Tapered shallow skirt below the bank avoids a visible open cut when viewed from the back.
    perimeter = (list(range(0, (nx+1)*(nd+1), nd+1))
                 + [nx*(nd+1)+j for j in range(1, nd+1)]
                 + [i*(nd+1)+nd for i in range(nx-1, -1, -1)]
                 + list(range(nd-1, 0, -1)))
    offset = len(m.verts)
    for j, i in enumerate(perimeter):
        x, y, _ = m.verts[i]
        m.verts.append((x, y, BOTTOM))
        m.colors.append(scale(p["soil"], .6))
        m.factors.append(0)
        k = (j+1) % len(perimeter)
        m.faces.append((i, offset+j, offset+k, perimeter[k]))
    # The perimeter is concave alongshore; tessellate the underside n-gon in Blender.
    m.faces.append(tuple(reversed(range(offset, len(m.verts)))))
    ground = socket_material("dirt_path", "Shinglewake | sand and capillary fringe",
                             "bank_tones", .94, "ground_moisture", (.84, .31))
    nodes, links = ground.node_tree.nodes, ground.node_tree.links
    coords = next(n for n in nodes if n.type == "TEX_COORD")
    grains = nodes.new("ShaderNodeTexNoise")
    grains.inputs["Scale"].default_value = 27
    grains.inputs["Detail"].default_value = 2.6
    links.new(coords.outputs["Object"], grains.inputs["Vector"])
    shade = nodes.new("ShaderNodeMapRange")
    shade.inputs["To Min"].default_value = .67
    shade.inputs["To Max"].default_value = 1.21
    links.new(grains.outputs["Fac"], shade.inputs["Value"])
    bsdf = nodes["Principled BSDF"]
    color = bsdf.inputs["Base Color"]
    mineral = nodes.new("ShaderNodeMixRGB")
    mineral.blend_type = "MULTIPLY"
    mineral.inputs[0].default_value = 1
    links.new(color.links[0].from_socket, mineral.inputs[1])
    links.new(shade.outputs["Result"], mineral.inputs[2])
    links.new(mineral.outputs[0], color)
    turf = socket_material("grass_ground", "Shinglewake | living ground cover", "bank_tones", .83)
    shore = m.object("Continuous sandy shelf and undercut bank", (ground, turf), "bank_tones", "ground_moisture")
    for poly in shore.data.polygons[:nx*nd]:
        x, y, _ = poly.center
        if y - waterline(x) > turf_line(x) + .64 + .16*n3(x*1.7, 7, 24):
            poly.material_index = 1


def ico(level):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=level, radius=1)
    bm.verts.index_update()
    verts = [tuple(v.co) for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return verts, faces


def eased_min(a, b, radius):
    gap = max(0, radius - abs(a-b))
    return min(a, b) - gap*gap/(4*radius)


def cobble(m, p, template, x, d, r, flat, rng, form=None):
    coords, faces = template
    offset = len(m.verts)
    a = rng.uniform(0, math.tau)
    ca, sa = math.cos(a), math.sin(a)
    seed = rng.uniform(25, 825)
    form = rng.choice(("split", "slab", "worn")) if form is None else form
    elongation = rng.uniform(.50, .85) if form != "worn" else rng.uniform(.76, 1.02)
    weather = rng.random()
    ground = bank(x, d)
    z0 = ground + r*flat*rng.uniform(.06, .36)
    y = waterline(x)+d
    cuts = []
    strike = rng.uniform(0, math.tau)
    count = rng.randint(4, 6)
    for j in range(count):
        theta = strike + j*math.tau/count + rng.uniform(-.26,.26)
        rise = rng.uniform(-.27, .29)
        axy = math.sqrt(1-rise*rise)
        setback = rng.uniform(.55, .73) if form != "worn" else rng.uniform(.91, .99)
        cuts.append((math.cos(theta)*axy, math.sin(theta)*axy, rise, setback))
    if form == "slab":
        flat *= .75
        cuts.extend(((.14, -.12, .98, rng.uniform(.36,.49)), (-.52,.36,.77,.56),
                     (.63, .69, .33, rng.uniform(.51,.68))))
    elif form == "split":
        cuts.extend(((.32, .34, .88, rng.uniform(.55,.68)), (-.54,-.37,.75,.61),
                     (-.05, .66, .75, rng.uniform(.52,.72))))
    lean = rng.uniform(-.20, .20)
    kind = rng.random()
    if kind < .29:
        body = blend(scale(p["shore_wet"], .57), p["canyon_strata"], .18)
    elif kind < .53:
        body = blend(p["soil"], p["sandstone"], rng.uniform(.48, .86))
    elif kind < .75:
        body = blend(p["shore_wet"], p["canyon_strata"], rng.uniform(.61, .83))
    else:
        body = blend(p["canyon_strata"], p["canyon_chalk"], rng.uniform(.15, .56))
    if form == "slab":
        body = blend(body, p["canyon_strata"], .28)
    halo = .033 + .096*smooth((.74-d)/.96)
    floor = max(BOTTOM+.0005, ground-.25*r*flat)
    lichen_prop = rng.uniform(.14, .40) if d > .48 else .045
    for u, v, w in coords:
        seam = noise.voronoi(Vector((u*(1.6+weather)+seed, v*2.7, w*(2.1+.8*weather))))[0]
        chip = 1 - smooth((seam[1]-seam[0])/.29)
        coarse = n3(2.1*u, 2.1*v+seed, 2.1*w)
        medium = n3(5.75*u, 5.75*v, 5.75*w+seed)
        fine = n3(15*u+seed, 15*v, 15*w)
        radial = 1 + (.13 if form == "worn" else .09)*coarse
        for nx, ny, nz, upper in cuts:
            dot = nx*u+ny*v+nz*w
            if dot > .28:
                radial = eased_min(radial, upper/dot, .035 if form != "worn" else .095)
        lamina = math.sin((19+7*weather)*(w+.22*u-.14*v) + .76*coarse)
        breakout = smooth(.44 + 1.25*medium - .43*weather)
        radial *= (1 + (.026+.016*weather)*medium + .013*fine
                   - .043*chip*breakout + (.019 if form == "slab" else .010)*lamina)
        u1, v1 = (u*radial + lean*w*.48)*r, v*radial*r*elongation
        px, py = x+ca*u1-sa*v1, y+sa*u1+ca*v1
        z = z0 + r*flat*(w*radial + lean*u*.41)
        # Turn the bottom into a small bedding contact, not another ellipsoid pole.
        z = floor + .013*r*flat + max(0, z-floor)
        m.verts.append((px, py, z))
        water_z = halo + .049*n3(5*u+seed, 4*v, 2*w)*min(1, r*2)
        wet = max(.0, (1-smooth((z-water_z)/max(.022, r*.14))) * smooth((1.18-d)/.83))
        m.factors.append(wet)
        # Pale mineral on fresh edges, warmer lichen only where elevation and aspect allow.
        marl = .021*n3(u*3.7, v*3.7, w*12+seed) + (1-chip)*.009
        marl += (.057 if form == "slab" else .028)*smooth((lamina-.81)/.19)*smooth(.60+medium)
        mid = scale(body, .83 + .24*weather + .23*coarse + .17*medium)
        stained = blend(mid, p["grass_dry"], smooth((w+.3)/1.2)*smooth(.52+1.6*medium)*lichen_prop)
        dry = tuple(max(.009, rgb+marl) for rgb in stained)
        wet_rgb = scale(blend(dry, p["shore_wet"], .33), .37+.14*coarse)
        m.colors.append(blend(dry, wet_rgb, wet))
    m.faces.extend(tuple(offset+i for i in face) for face in faces)


def stones(p, rng):
    m = Mesh()
    high, middle, small = ico(6), ico(4), ico(2)
    anchors = (
        (-8.44, .52, .83, .51), (-7.31, .11, .47, .70), (-8.72, 1.32, .48, .43),
        (-4.13, 2.92, .79, .51), (-3.05, 3.20, .46, .57),
        (-2.30, -.16, .93, .68), (-1.26, .22, .48, .51), (-2.54, .71, .39, .50),
        (1.20, 2.46, .32, .47), (2.14, 3.36, .62, .62), (2.87, 3.12, .43, .47),
        (4.38, .24, .74, .50), (5.12, -.13, .61, .71), (5.38, .72, .48, .47),
        (7.62, .92, .61, .68), (8.38, .41, .72, .38), (8.74, 1.29, .41, .63),
        (8.24, 4.15, .46, .51), (-7.87, 4.66, .36, .56),
    )
    forms = ("split", "worn", "slab", "split", "slab", "slab", "split", "worn", "slab",
             "split", "worn", "split", "worn", "slab", "worn", "slab", "split", "worn", "slab")
    for (x, d, r, flat), form in zip(anchors, forms, strict=True):
        cobble(m, p, high, x, d, r, flat, rng, form)
    clusters = (
        (-8.17, .39, .66, .25, 155), (-5.14, .04, .59, .17, 69),
        (-1.94, .22, .68, .29, 160), (.42, .31, .48, .20, 66),
        (4.77, .27, .68, .32, 165), (8.37, .48, .63, .28, 161),
        (-3.91, 3.04, .48, .26, 71), (2.54, 3.19, .44, .29, 83),
        (8.08, 4.15, .29, .19, 48), (-7.86, 4.57, .23, .23, 36),
    )
    accepted = []
    for cx, cd, sx, sd, count in clusters:
        rotation = rng.uniform(-.31, .31)
        ca, sa = math.cos(rotation), math.sin(rotation)
        for _ in range(count):
            gx, gy = rng.gauss(0, sx), rng.gauss(0, sd)
            if (gx/sx)**2 + (gy/sd)**2 > 3.5:
                continue
            x, d = cx+ca*gx-sa*gy, cd+sa*gx+ca*gy
            if abs(x) > HALF-.55 or not -.43 < d < 5.5:
                continue
            r = .037 + .21*rng.random()**3.1
            if any(math.hypot(x-bx, d-bd) < .50*br for bx, bd, br, _ in anchors):
                continue
            if any((x-px)**2+(d-pd)**2 < (.65*(r+pr))**2 for px, pd, pr in accepted):
                continue
            accepted.append((x, d, r))
            cobble(m, p, middle if r > .095 else small, x, d, r, rng.uniform(.31, .77), rng)
    mat = socket_material("river_stones", "Shinglewake | weathered cobbles with soaked bases",
                          "stone_tones", .96, "stone_saturation", (.69, .23))
    m.object("Distinct glacial cobbles and sorted shingle", (mat,), "stone_tones", "stone_saturation")


def grass_blade(m, x, y, z, h, width, direction, spread, bend, tone):
    ca, sa = math.cos(direction), math.sin(direction)
    wx, wy = -sa*width, ca*width
    j = len(m.verts)
    for u, width_at in ((0, .77), (.30, 1), (.66, .55), (.87, .25)):
        dx = ca*spread*u**1.7 + h*bend*u*u
        dy = sa*spread*u**1.7 - h*.18*u*u
        for side, keel in ((-1, 0), (0, .30), (1, 0)):
            m.verts.append((x+dx+side*wx*width_at, y+dy+side*wy*width_at,
                            z+h*u+width*keel*width_at))
            m.colors.append(scale(tone, .64+.42*u))
    m.verts.append((x+ca*spread+h*bend, y+sa*spread-h*.18, z+h))
    m.colors.append(tone)
    for k in range(3):
        i = j+3*k
        m.faces.extend(((i, i+1, i+4, i+3), (i+1, i+2, i+5, i+4)))
    m.faces.extend(((j+9, j+10, j+12), (j+10, j+11, j+12)))


def root(m, path, radii):
    origin = len(m.verts)
    n = 7
    for i, pt in enumerate(path):
        v = (path[min(i+1,len(path)-1)] - path[max(0,i-1)]).normalized()
        a = v.cross(Vector((1, .2, .3))).normalized()
        b = v.cross(a)
        for j in range(n):
            ang = math.tau*j/n
            m.verts.append(pt + (math.cos(ang)*a + math.sin(ang)*b)*radii[i])
        if i:
            k = origin + (i-1)*n
            for j in range(n):
                q = (j+1)%n
                m.faces.append((k+j, k+q, k+q+n, k+j+n))
    end = len(m.verts)
    m.faces.extend((tuple(reversed(range(origin, origin+n))), tuple(range(end-n, end))))


def vegetation(p, rng):
    grass, fibres = Mesh(), Mesh()
    for cx, q, wx, wd, count in (
        (-8.6,.7,.66,.38,87), (-7.2,1.43,.73,.47,72), (-4.8,.64,.86,.45,102),
        (-2.5,1.32,.66,.42,78), (-.76,.55,.68,.35,64), (.8,1.36,.79,.42,66),
        (2.1,.63,.71,.34,77), (4.3,1.19,.71,.43,91), (5.8,.80,.76,.40,78),
        (8.07,.87,.88,.49,113), (9.23,1.39,.44,.29,60),
      ):
        for _ in range(count*3):
            x = cx + rng.gauss(0, wx)
            d = turf_line(x) + q + rng.gauss(0, wd)
            if abs(x) > HALF-.75 or not .26 < d-turf_line(x) or d > BANK_LENGTH-.89:
                continue
            if n3(x*.83, d*1.3, 4.8) < -.46:
                continue
            y = waterline(x)+d
            dry_clump = n3(x*.85, d*1.4, 24) < -.17
            length = rng.uniform(.068,.28) * (.61+.57*smooth((d-turf_line(x))/.91))
            tone = blend(p["grass_green"], p["grass_dry"], rng.random()**2.5)
            if dry_clump:
                length *= 1.45
                tone = blend(p["grass_dry"], p["path_sand"], rng.uniform(.18, .46))
            for _ in range(rng.randint(6, 10)):
                gx, gy = x+rng.uniform(-.059,.059), y+rng.uniform(-.059,.059)
                z = bank(gx, gy-waterline(gx))-.011
                h = length*rng.uniform(.44,1.34)
                grass_blade(grass, gx, gy, z, h, rng.uniform(.003,.010) if dry_clump else rng.uniform(.006,.018),
                            rng.uniform(0, math.tau), h*rng.uniform(.39,1.02), rng.uniform(.12,.44), tone)
    for cx in (-5.43, -.44, 2.12, 6.21, 8.90):
        for _ in range(rng.randint(7, 14)):
            x = cx+rng.uniform(-.46,.46)
            d = turf_line(x)+rng.uniform(.31,.48)
            y = waterline(x)+d
            length = rng.uniform(.23,.55)
            side = rng.uniform(-.23,.23)
            z = bank(x, d)-rng.uniform(.014,.034)
            path = []
            for i in range(9):
                t = i/8
                px, py = x+side*t+.037*math.sin(6*t), y-length*t
                surface = bank(px, py-waterline(px))
                zz = z - .14*t*t
                path.append(Vector((px, py, max(surface-.024*t, min(zz, surface+.046*t)))))
            radius = rng.uniform(.007,.023)
            root(fibres, path, [radius*(1-.94*i/8)**.83 for i in range(9)])
            if rng.random() < .57:
                branch = [path[4], path[5]+Vector((.041,.008,-.008)), path[8]+Vector((.11,.015,-.016))]
                root(fibres, branch, [radius*.52, radius*.30, radius*.06])
    grass_mat = socket_material("grass_ground", "Shinglewake | lakeside sedge blades", "grass_tone", .84)
    grass.object("Folded grass and dry sedge in dense patches", (grass_mat,), "grass_tone")
    fibres.object("Root fibres emerging from beneath the turf lip", (vrmat.get("tree_bark"),))


def review_lake(p):
    m = Mesh()
    nx, nd = 272, 116
    for i in range(nx+1):
        x = 2*HALF*(i/nx-.5)
        for j in range(nd+1):
            d = -6.8 + 6.81*j/nd
            y = waterline(x) + d
            m.verts.append((x, y, 0))
            suspended = smooth((d+2.3 + .22*n3(x*.61, d*1.9, 14))/2.54)
            shallows = blend(p["water_shallow"], p["path_sand"], .21*smooth((d+.48)/.55))
            shallow_tint = scale(shallows, .79+.19*n3(x*.83, d*1.2, 18))
            deep = tuple(v*f for v, f in zip(p["water_deep"], (.86, 1.18, .77)))
            color = blend(deep, shallow_tint, suspended)
            # Thin broken capillary line and one fainter wash just lakeward of it.
            ridge = d+.045 - .023*n3(x*3.7, d*1.4, 20) - .01*math.sin(3.4*x)
            foam = math.exp(-(ridge/.045)**2) * smooth(.73 + n3(x*1.01, d*.85, 23)*1.18)
            wake = math.exp(-((d+.31-.038*math.sin(x*1.28))/.042)**2) * smooth(.19 + .92*n3(x*.72, 7, 15))
            pale = blend(p["haze"], p["cloud_cream"], .56)
            m.colors.append(blend(color, pale, min(.78, .76*foam+.19*wake)))
            m.factors.append(smooth((d+.59)/.35)*(.84-.72*foam))
            if i and j:
                k = i*(nd+1)+j
                m.faces.append((k-nd-2, k-1, k, k-nd-1))
    mat = socket_material("water_opaque", "Review only | lake, shallows and broken wash", "lake_tone", .94)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Specular IOR Level"].default_value = .23
    tex = nodes.new("ShaderNodeTexCoord")
    spread = nodes.new("ShaderNodeVectorMath")
    spread.operation = "MULTIPLY"
    spread.inputs[1].default_value = (1.18, 8.1, 1)
    links.new(tex.outputs["Object"], spread.inputs[0])
    rolls = nodes.new("ShaderNodeTexNoise")
    rolls.inputs["Scale"].default_value = 1
    rolls.inputs["Detail"].default_value = 2
    links.new(spread.outputs["Vector"], rolls.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .009
    bump.inputs["Strength"].default_value = .47
    normal = bsdf.inputs["Normal"]
    links.new(normal.links[0].from_socket, bump.inputs["Normal"])
    links.new(rolls.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], normal)
    opacity = nodes.new("ShaderNodeAttribute")
    opacity.attribute_name = "shoal_visibility"
    invert = nodes.new("ShaderNodeMath")
    invert.operation = "SUBTRACT"
    invert.inputs[0].default_value = 1
    links.new(opacity.outputs["Fac"], invert.inputs[1])
    links.new(invert.outputs[0], bsdf.inputs["Alpha"])
    m.object("Review only | calm blue-green lake at Z=0", (mat,), "lake_tone", "shoal_visibility", source=False)


def build():
    p = {k: v["linear_rgb"] for k, v in vrmat.load_palette().items()}
    rng = random.Random(SEED)
    shore_ground(p)
    stones(p, rng)
    vegetation(p, rng)
    review_lake(p)
    scene = bpy.context.scene
    scene["vr_review_turn"] = (0, -.30, .02, -103, 36, 38)
    x, d = -6.8, 3.22
    scene["vr_review_figure"] = (x, waterline(x)+d, bank(x, d)-.017)
    scene["vr_closeup_upper"] = (-1.75, waterline(-1.75)+.39, .13, -106, 27, 9.4)
    scene["vr_closeup_base"] = (4.85, waterline(4.85)+2.88, .24, -55, 32, 11.3)

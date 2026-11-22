"""A levitating violet seed held between four eroded limestone sails."""
import math
import random

import bmesh
import bpy
from mathutils import Quaternion, Vector
from mathutils.noise import noise_vector

import vrlib
import vrmat


CORE_ORIGIN = Vector((.05, .17, 9.45))
CORE_TILT = Quaternion(Vector((-.20, .98, 0)), .405)


def mesh_object(name, points, faces, materials, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(points, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    for material in materials:
        data.materials.append(vrmat.get(material) if isinstance(material, str) else material)
    for face in data.polygons:
        face.use_smooth = smooth
    return vrlib.link_to_source(obj)


def commit_mesh(name, bm, materials, smooth=False):
    bmesh.ops.dissolve_degenerate(bm, dist=.00001, edges=list(bm.edges))
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    obj = mesh_object(name, [], [], materials)
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = smooth
    return obj


def spall(bm, point, normal):
    chipped = bm.copy()
    geom = list(chipped.verts) + list(chipped.edges) + list(chipped.faces)
    bmesh.ops.bisect_plane(chipped, geom=geom, plane_co=point, plane_no=normal,
                          dist=.00001, clear_outer=True)
    edges = [e for e in chipped.edges if e.is_boundary]
    new = bmesh.ops.holes_fill(chipped, edges=edges, sides=0)["faces"]
    if not new or any(not e.is_manifold for e in chipped.edges):
        chipped.free()
        return bm
    for face in new:
        face.material_index = 1
    bm.free()
    return chipped


def shaped_stone(name, outline, bottom, top, rng, material, weathered=False):
    bm = bmesh.new()
    footprint = [Vector(p) for p in outline]
    centre = sum(footprint, Vector((0, 0))) / len(footprint)
    for portion, scale in ((0, .94), (.18, 1), (.68, .98), (1, .85)):
        for p in footprint:
            q = centre.lerp(p, scale)
            local_z = (top-bottom) * rng.uniform(-.10, .10) * portion
            bm.verts.new((q.x, q.y, bottom + (top-bottom)*portion + local_z))
    result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
    discarded = set(result["geom_interior"] + result["geom_unused"])
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v in discarded], context="VERTS")
    for p in rng.sample(footprint, min(len(footprint), 3)):
        q = centre.lerp(p, rng.uniform(.80, .91))
        n = (p - centre).normalized()
        bm = spall(bm, (q.x, q.y, top-.19*(top-bottom)), (n.x, n.y, .6))
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=3, use_grid_fill=True)
    for v in bm.verts:
        n = noise_vector(v.co * 2.7)
        amplitude = min(.095, (top-bottom) * .16)
        v.co.x += n.x * amplitude
        v.co.y += n.y * amplitude
        v.co.z = max(-.042, v.co.z + n.z * amplitude)
    obj = commit_mesh(name, bm, [material, "monument_white"], smooth=True)
    obj.data.set_sharp_from_angle(angle=math.radians(32))
    if weathered:
        obj.data.materials[1] = vrmat.get("monument_weathered")
    return obj


def loft(rows):
    n = len(rows[0])
    faces = [tuple(reversed(range(n)))]
    for j in range(len(rows)-1):
        for i in range(n):
            a, b = j*n+i, j*n+(i+1)%n
            faces.append((a, b, b+n, a+n))
    faces.append(tuple(range(n*(len(rows)-1), n*len(rows))))
    return [tuple(p) for row in rows for p in row], faces


def profile_at(profile, t):
    count = len(profile)-1
    i = min(int(t*count), count-1)
    f = t*count-i
    p0, p1, p2, p3 = [profile[max(0, min(count, j))]
                      for j in (i-1, i, i+1, i+2)]
    return tuple(.5*(2*b + f*((c-a) + f*((2*a-5*b+4*c-d) + f*(3*b-3*c+d-a))))
                 for a,b,c,d in zip(p0,p1,p2,p3))


def radial(angle):
    return Vector((math.cos(angle), math.sin(angle), 0))


def blade_section(angle, profile, section, t):
    distance, z, depth, width, drift = profile_at(profile, t)
    radial_dir, side_dir = radial(angle), radial(angle+math.pi/2)
    centre = radial_dir*distance + side_dir*drift + Vector((0, 0, z))
    return [centre + radial_dir*(r*depth) + side_dir*(s*width) for r,s in section]


def rib(name, angle, profile, breaks, section, rng):
    # Individual voussoirs share a continuous curved profile but have separate cut beds.
    for index, (a,b) in enumerate(zip(breaks, breaks[1:])):
        rows = []
        steps = max(7, round((b-a)*100))
        for k in range(steps+1):
            f = k/steps
            t = (a + (.0009 if index else 0)) + (b-a-.0019)*f
            row = blade_section(angle, profile, section, t)
            for j, v in enumerate(row):
                noise = noise_vector(v * 3.6 + Vector((1.7, 3.1, 2)))
                v += noise * (.024 + .030 * abs(2*f-1)**4)
                v.z = max(-.035, v.z)
            rows.append(row)
        points, faces = loft(rows)
        bm = bmesh.new()
        verts = [bm.verts.new(p) for p in points]
        for face in faces:
            bm.faces.new([verts[i] for i in face])
        for row, k, sign in ((rows[-1], (index*5+1)%len(section), 1),
                             (rows[0], (index*7+4)%len(section), -1)):
            if index == 0 and sign < 0:
                continue
            point = row[k].lerp(row[(k+1)%len(row)], rng.uniform(.16,.46))
            q = sum(row, Vector()) / len(row)
            n = (point-q).normalized() + Vector((0, 0, sign*rng.uniform(.50,.81)))
            bm = spall(bm, point.lerp(q, rng.uniform(.035,.20)), n)
        obj = commit_mesh(f"{name} | ashlar {index+1}", bm,
                          ["monument_white", "monument_white"], smooth=True)
        obj.data.set_sharp_from_angle(angle=math.radians(37))


def energy_finish(name, filament=False, gain=1):
    """Local violet_energy variant: geometry supplies the flow, the shader supplies depth."""
    mat = vrmat.get("violet_energy").copy()
    mat.name = name
    palette = vrmat.load_palette()
    r,g,b = palette["violet_body"]["linear_rgb"]
    light = (r*1.48, g*.31, b*.83, 1)
    hot = (r*2.49, g*.37, b*1.27, 1)
    dark = (r*.13, g*.04, b*.17, 1)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "plasma"
    ramp = nodes.new("ShaderNodeValToRGB")
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = .06, dark
    e[1].position, e[1].color = .95, hot
    e.new(.38).color = (r*.48, g*.17, b*.52, 1)
    e.new(.68).color = light
    links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    links.new(ramp.outputs[0], bsdf.inputs["Emission Color"])
    strength = bsdf.inputs["Emission Strength"]
    links.remove(strength.links[0])
    strength.default_value = (1.45 if filament else 1.22)*gain
    return mat


def seed_point(t, theta, clearance=0):
    span = math.sin(t*math.pi)**.90
    swelling = (1 + .18 * math.sin(2*math.pi*(t-.14)) + .07*math.sin(5.4*t+.2))
    wave = (.12*math.cos(2*theta-10*t) + .10*math.sin(3*theta+6*t) + .035*math.cos(6*theta-7*t))
    radius = (2.47*swelling*(1+span*wave))*span
    x = (radius+clearance) * math.cos(theta) + .29*math.sin(5.5*t)
    y = (radius*.77+clearance) * math.sin(theta) + .27*math.sin(math.pi*t)
    z = -5.45 + 10.9*t + .20*span*math.cos(theta + 7*t)
    return CORE_ORIGIN + CORE_TILT @ Vector((x, y, z))


def body():
    n, steps = 88, 100
    points = [seed_point(0, 0)]
    intensity = [.08]
    for k in range(1, steps):
        t = k/steps
        for j in range(n):
            theta = math.tau*j/n
            p = seed_point(t, theta)
            curved = .5 + .5*math.sin(2*theta + 13*t + .47*math.sin(9*t))
            secondary = .5 + .5*math.sin(4*theta - 16*t + .43*math.sin(theta*3))
            whorl = max(0, .91 - abs(t-(.48 + .07*math.sin(theta+8*t)))*2.8)
            noise = noise_vector(p*.67).x
            streak = (.5 + .5*math.sin(11*t+theta*2+.60*math.sin(4*theta-17*t)))**12
            value = whorl*(.37+.52*curved**2.2) + whorl*(.16*secondary**3 + .13*streak) + .104*noise + .055
            points.append(p)
            intensity.append(max(0,min(1,value)))
    points.append(seed_point(1, 0))
    intensity.append(.08)
    faces = [(0, 1+(j+1)%n, 1+j) for j in range(n)]
    for k in range(steps-2):
        for j in range(n):
            a,b = 1+k*n+j,1+k*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
    last = len(points)-1
    for j in range(n):
        faces.append((last-n+j,last-n+(j+1)%n,last))
    obj = mesh_object("Levitating seed | rolling plasma surface", points, faces,
                      [energy_finish("Violet | plasma interior")], smooth=True)
    field = obj.data.attributes.new("plasma", "FLOAT", "POINT")
    field.data.foreach_set("value", intensity)


def anchor(angle, profile, section, t, across):
    intersections = [r + (s-r)*(across-a)/(b-a)
                     for (r,a),(s,b) in zip(section, section[1:] + section[:1])
                     if min(a,b) <= across < max(a,b)]
    return blade_section(angle, profile, [(min(intersections)+.11, across)], t)[0]


def branch(name, start, end, turns, width, gain, phase):
    n = 108
    points = []
    local_start, local_end = CORE_TILT.inverted() @ (start-CORE_ORIGIN), CORE_TILT.inverted() @ (end-CORE_ORIGIN)
    t0, t1 = ((v.z + 5.45)/10.9 for v in (local_start, local_end))
    t0, t1 = min(.96, max(.04, t0)), min(.96, max(.04,t1))
    head, tail = (math.atan2(v.y/.77, v.x) for v in (local_start, local_end))
    travel = (tail-head+math.pi) % math.tau - math.pi + turns*math.tau
    for k in range(n+1):
        u = k/n
        distance = .28 + .18*(.5+.5*math.sin(math.tau*u+phase)) + 1.1*width
        theta = head+travel*(u*u*(3-2*u)) + .16*math.sin(math.tau*u)*math.sin(math.pi*u)
        p = seed_point(t0+(t1-t0)*u, theta, distance)
        if u < .195:
            f = u/.195
            p = p.lerp(start, (1-f)**2)
        if u > .795:
            f = (u-.795)/.205
            p = p.lerp(end, f*f)
        points.append(p)
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth, curve.bevel_resolution = width, 4
    curve.use_fill_caps = True
    spline = curve.splines.new("POLY")
    spline.points.add(n)
    for k,(p, loc) in enumerate(zip(spline.points, points)):
        f = k/n
        p.co = (*loc, 1)
        p.radius = .30 + .66 * math.sin(math.pi*f)**.65 + .18*math.sin(13*f+phase)**2
    obj = bpy.data.objects.new(name, curve)
    vrlib.link_to_source(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    obj.data.materials.append(energy_finish(name+" | emission", True, gain))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.00001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    field = obj.data.attributes.new("plasma", "FLOAT", "POINT")
    for point, vert in zip(field.data, obj.data.vertices):
        point.value = .71 + .13 * math.sin(vert.co.z*1.29 + phase) + .10 * math.cos(vert.co.x*2.1)
    for face in obj.data.polygons:
        face.use_smooth = True


def build():
    rng = random.Random(763197)
    # Four masonry paths with unequal silhouettes and cross sections.
    sails = [
        ("West sail", 3.53,
         [(7.72,.03,1.88,2.76,-.21),(7.78,2.76,1.58,2.46,-.47),
          (7.55,6.13,1.42,2.02,-.5),(7.16,10.02,1.17,1.55,-.37),
          (6.56,13.12,.89,1.08,-.21),(5.34,15.76,.72,.85,-.14),(4.23,17.18,.42,.47,-.05)],
         [0,.123,.225,.363,.553,.711,.859,1],
         [(-1,-.31),(-.91,-.78),(-.56,-.96),(.26,-1),(.82,-.73),(1,-.33),
          (1,.46),(.67,.79),(.09,1),(-.68,.93),(-.92,.57),(-1,.25)]),
        ("East high vane", .72,
         [(7.78,.05,2.02,2.7,.60),(8.1,2.86,1.62,2.41,.62),(7.97,6.46,1.41,2.0,.39),
          (7.62,10.37,1.26,1.54,.26),(6.97,14.22,1.12,1.25,.03),
          (5.83,17.23,.75,.86,-.21),(4.52,19.23,.37,.52,-.47)],
         [0,.10,.231,.332,.474,.643,.776,.917,1],
         [(-1,-.27),(-.81,-.82),(-.51,-1),(.37,-.88),(.85,-.96),(1,-.61),
          (1,.34),(.82,.71),(.28,.99),(-.53,.91),(-.92,.65),(-1,.12)]),
        ("Far usher", 1.88,
         [(6.84,.04,1.56,2.28,.31),(7.06,2.19,1.34,1.95,.26),(6.96,4.99,1.11,1.51,.18),
          (6.75,7.51,.90,1.06,.15),(6.13,9.92,.78,.77,-.04),(5.09,11.53,.33,.38,-.26)],
         [0,.17,.30,.514,.697,.913,1],
         [(-1,-.30),(-.82,-.87),(-.23,-1),(.56,-.87),(.94,-.49),
          (1,.21),(.80,.78),(.19,1),(-.63,.83),(-.95,.48)]),
        ("Near remnant", 5.08,
         [(6.80,.04,1.63,2.35,-.33),(7.10,1.61,1.42,1.84,-.18),(7.09,3.45,1.20,1.54,-.21),
          (6.76,5.58,1.02,1.25,-.19),(6.21,7.30,.80,.73,-.31),(5.67,8.04,.48,.56,-.43)],
         [0,.188,.37,.547,.779,1],
         [(-.99,-.46),(-.72,-.93),(.09,-1),(.72,-.62),(1,-.26),
          (.94,.41),(.67,.88),(-.16,1),(-.86,.64)]),
    ]
    sails = [(name, angle, profile, breaks,
              [p for p in section if (p[1] <= -.49 and p[0] >= .70) or (p[0] < .70 and p[1] < 0)] + [
                  (.95, -.39), (1.08, -.29), (1.08, -.19), (.95, -.10),
                  (.94, .06), (1.055, .14), (1.06, .24), (.96, .33),
              ] + [p for p in section if p[1] > .33 or (p[0] < -.90 and p[1] >= 0)])
             for name, angle, profile, breaks, section in sails]
    for name, angle, profile, breaks, section in sails:
        rib(name, angle, profile, breaks, section, rng)
    feet = [
        ("West out-thrust", [(-10.7,-2.8),(-8.3,-6.4),(-5.87,-5.42),(-4.89,-4.18),
                              (-5.47,-1.85),(-7.86,.17),(-10.0,-.59)], .68),
        ("East fractured apron", [(3.8,2.3),(5.97,1),(8.03,2.32),(9.4,4.48),
                                   (8.25,7.41),(6.84,8.30),(5.2,6.61)], .57),
        ("North landing", [(-5.54,4.9),(-3.29,3.89),(-.59,4.59),(.78,6.62),
                            (-.61,8.73),(-3.31,9.32),(-5.31,7.52)], .55),
        ("South landing", [(-1.47,-7.03),(.57,-9.22),(3.29,-9.13),(5.19,-7.24),
                            (4.48,-5.53),(2.68,-4.41),(-.13,-5.10)], .46),
        ("Lower entry step", [(3.47,-5.8),(4.51,-6.59),(5.73,-6.11),(6.37,-4.82),
                              (5.92,-3.69),(4.82,-3.17),(4.05,-4.29)], .25),
        ("Cleaved outer footing", [(-8.88,-5.72),(-8.45,-6.87),(-7.2,-6.86),
                                     (-6.56,-5.61),(-7.35,-5.09)], .29),
    ]
    for name, outline, top in feet:
        shaped_stone(name, outline, -.027, top, rng, "monument_weathered", True)
    paving = [
        ([(.13,-6.53),(1.12,-6.16),(2.17,-5.09),(1.51,-4.37),(.35,-4.76),(-.42,-5.66)], .14),
        ([(-.40,-5.04),(.33,-4.49),(.79,-3.43),(.17,-2.9),(-.86,-3.31),(-1.24,-4.24)], .195),
        ([(.51,-4.37),(1.60,-4.20),(1.75,-3.48),(.91,-3.22)], .17),
        ([(-.79,-3.16),(.05,-2.77),(.37,-1.91),(-.32,-1.34),(-1.21,-1.76),(-1.39,-2.60)], .14),
        ([(.47,-2.79),(1.12,-2.97),(1.38,-2.37),(.89,-1.92),(.48,-2.04)], .11),
    ]
    for i, (outline, top) in enumerate(paving):
        shaped_stone(f"Broken processional flags {i+1}", outline, -.017, top, rng, "monument_weathered")
    for i in range(42):
        _, a, profile, _, _ = rng.choice(sails)
        centre = profile[0][0]
        rr = centre + rng.uniform(.94,2.51)
        x,y = rr*math.cos(a) - rng.uniform(-2,2)*math.sin(a), rr*math.sin(a) + rng.uniform(-2,2)*math.cos(a)
        extent = .10+.57*rng.random()**2.8
        count = rng.choice((5,6,7))
        outline = []
        for k in range(count):
            angle = math.tau*(k+rng.uniform(-.32,.32))/count
            outline.append((x+extent*rng.uniform(.72,1.24)*math.cos(angle),
                            y+extent*rng.uniform(.68,1.15)*math.sin(angle)))
        shaped_stone(f"Apron spall {i+1}", outline, -.018,
                     extent*rng.uniform(.43,.91), rng, "monument_weathered", True)
    body()
    west,east,north,south = sails

    def seat(sail, t, across):
        return anchor(sail[1], sail[2], sail[4], t, across)

    paths = [
        ("Primary current", seat(west,.29,-.19), seat(east,.70,.19), 1,.052,1,1.3),
        ("Return current", seat(north,.48,.21), seat(west,.73,-.13), -1,.032,.95,3.2),
        ("Lower winding", seat(south,.61,-.15), seat(east,.42,-.24), 0,.039,.98,1.8),
        ("Upper winding", seat(east,.62,.12), seat(north,.94,.06), 0,.026,.93,4.0),
    ]
    for path in paths:
        branch(*path)
    rotation = Quaternion(Vector((0,0,1)), .86).to_matrix().to_4x4()
    for obj in vrlib.source_objects():
        obj.data.transform(rotation)

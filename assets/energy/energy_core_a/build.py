"""A levitating violet seed held between four eroded limestone sails."""
import math
import random

import bmesh
import bpy
from mathutils import Quaternion, Vector
from mathutils.kdtree import KDTree
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


def blade_section(angle, profile, section, t, sockets=()):
    distance, z, depth, width, drift = profile_at(profile, t)
    radial_dir, side_dir = radial(angle), radial(angle+math.pi/2)
    centre = radial_dir*distance + side_dir*drift + Vector((0, 0, z))
    row = []
    for r, s in section:
        inset = 0
        if r < -.85:
            for level, across, size in sockets:
                dz = z - profile_at(profile, level)[1]
                lateral = (s-across)*width
                rr = math.hypot((lateral-.15*dz)/size, dz/(size*1.73))
                flute = .085 * rr * math.sin(5*math.atan2(dz, lateral)+.9)
                inset += .55 * max(0, 1-(rr+flute)**4)**1.50
        row.append(centre + radial_dir*(r*depth+inset) + side_dir*(s*width))
    return row


def rib(name, angle, profile, breaks, section, sockets, rng, limestone):
    section = [tuple(x+(y-x)*k/steps for x,y in zip(p,q))
               for p, q in zip(section, section[1:] + section[:1])
               for steps in [14 if max(p[0], q[0]) < -.85 else 1]
               for k in range(steps)]
    for index, (a,b) in enumerate(zip(breaks, breaks[1:])):
        rows = []
        steps = max(10, round((b-a)*142))
        for k in range(steps+1):
            f = k/steps
            start = a + (.0027 if index else 0)
            stop = b - (.0033 if index < len(breaks)-2 else 0)
            t = start+(stop-start)*f
            row = blade_section(angle, profile, section, t, sockets)
            centre = sum(row, Vector()) / len(row)
            bed = .045 * abs(2*f-1)**14
            for j, v in enumerate(row):
                noise = noise_vector(v * 3.6 + Vector((1.7, 3.1, 2)))
                v -= (v-centre)*bed
                v += noise * (.024 + .030 * abs(2*f-1)**4)
                v.z = max(-.035, v.z)
            rows.append(row)
        points, faces = loft(rows)
        bm = bmesh.new()
        verts = [bm.verts.new(p) for p in points]
        for face in faces:
            bm.faces.new([verts[i] for i in face])
        corners = [j for j, (r, s) in enumerate(section) if r > -.85 or abs(s) > .53]
        for row, k, sign in ((rows[-1], rng.choice(corners), 1),
                             (rows[0], rng.choice(corners), -1)):
            if index == 0 and sign < 0:
                continue
            point = row[k].lerp(row[(k+1)%len(row)], rng.uniform(.16,.46))
            q = sum(row, Vector()) / len(row)
            n = (point-q).normalized() + Vector((0, 0, sign*rng.uniform(.45,.76)))
            bm = spall(bm, point.lerp(q, rng.uniform(.19,.36)), n)
        obj = commit_mesh(f"{name} | ashlar {index+1}", bm,
                          [limestone, "monument_white"], smooth=True)
        obj.data.set_sharp_from_angle(angle=math.radians(37))
        patina = obj.data.attributes.new("socket lining", "FLOAT", "POINT")
        forward, across_dir = radial(angle), radial(angle+math.pi/2)
        for (level, across, size) in sockets:
            if not a-.12 <= level <= b+.12:
                continue
            socket = blade_section(angle, profile, [(-.94, across)], level)[0]
            for field, vert in zip(patina.data, obj.data.vertices):
                v = vert.co-socket
                if v.dot(forward) > .85:
                    continue
                rr = math.hypot((v.dot(across_dir)-.15*v.z)/size, v.z/(1.73*size))
                field.value = max(field.value, .79*max(0, 1-(rr/.83)**4))
        if index:
            bed_rows = []
            for t in (a-.006, a, a+.006):
                row = blade_section(angle, profile, section, t, sockets)
                centre = sum(row, Vector()) / len(row)
                bed_rows.append([v.lerp(centre, .105) for v in row])
            mesh_object(f"{name} | recessed joint {index}", *loft(bed_rows), ["dirt_path"])


def limestone_finish():
    mat = vrmat.get("monument_white").copy()
    mat.name = "Sails | laminated limestone"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    base = nodes["Principled BSDF"].inputs["Base Color"]
    coord = next(node for node in nodes if node.type == "TEX_COORD")
    grain = nodes.new("ShaderNodeVectorMath")
    grain.operation = "MULTIPLY"
    grain.inputs[1].default_value = (.68, .73, 3.1)
    links.new(coord.outputs["Object"], grain.inputs[0])
    seams = nodes.new("ShaderNodeTexNoise")
    seams.inputs["Detail"].default_value = 2
    links.new(grain.outputs["Vector"], seams.inputs["Vector"])
    tone = nodes.new("ShaderNodeValToRGB")
    tone.color_ramp.elements[0].position = .24
    tone.color_ramp.elements[0].color = (.67,.60,.54,1)
    tone.color_ramp.elements[1].position = .64
    links.new(seams.outputs["Fac"], tone.inputs[0])
    shade = nodes.new("ShaderNodeMixRGB")
    shade.blend_type = "MULTIPLY"
    shade.inputs[0].default_value = .64
    links.new(base.links[0].from_socket, shade.inputs[1])
    links.new(tone.outputs["Color"], shade.inputs[2])
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "socket lining"
    lining = nodes.new("ShaderNodeMixRGB")
    lining.blend_type = "MULTIPLY"
    lining.inputs[2].default_value = (.34,.29,.48,1)
    links.new(attr.outputs["Fac"], lining.inputs[0])
    links.new(shade.outputs[0], lining.inputs[1])
    links.new(lining.outputs[0], base)
    return mat


def energy_finish(name, strength, current=False):
    mat = vrmat.get("violet_energy").copy()
    mat.name = name
    palette = vrmat.load_palette()
    r,g,b = palette["violet_body"]["linear_rgb"]
    light = (r*.77, g*.19, b*.51, 1)
    hot = (r*1.72, g*.19, b*.92, 1)
    dark = (r*.078, g*.04, b*.115, 1)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "plasma"
    ramp = nodes.new("ShaderNodeValToRGB")
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = .06, dark
    e[1].position, e[1].color = .95, hot
    e.new(.43).color = (r*.38, g*.13, b*.48, 1)
    e.new(.72).color = light
    ramp.color_ramp.interpolation = "EASE"
    links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    links.new(ramp.outputs[0], bsdf.inputs["Emission Color"])
    emission = bsdf.inputs["Emission Strength"]
    links.remove(emission.links[0])
    emission.default_value = strength
    if current:
        links.remove(bsdf.inputs["Base Color"].links[0])
        bsdf.inputs["Base Color"].default_value = dark
    return mat


def seed_axis(t):
    return Vector((.64*math.sin(6.4*t-.45)+.25*math.sin(12*t),
                   .51*math.sin(6*t+.35), -5.25+10.5*t))


def seed_point(t, theta):
    span = max(0, math.sin(t*math.pi))**.67
    centre = seed_axis(t)
    swelling = 1 + .15*math.sin(2*math.pi*t+.22) + .093*math.sin(4*math.pi*t-.64)
    helix = 3*theta - 11.8*t + .65*math.sin(6.6*t)
    lobes = .245*math.cos(helix) + .094*math.sin(2*theta+8*t) + .046*math.cos(2*helix+.32)
    radius = 2.60*swelling*span*(1+span*lobes)
    x = centre.x + radius*math.cos(theta)
    y = centre.y + radius*.79*math.sin(theta)
    z = centre.z + .24*span*math.cos(theta+7*t)
    return CORE_ORIGIN + CORE_TILT @ Vector((x, y, z))


def body():
    n, steps = 104, 116
    points = [seed_point(0, 0)]
    intensity = [.065]
    for k in range(1, steps):
        t = k/steps
        for j in range(n):
            theta = math.tau*j/n
            p = seed_point(t, theta)
            helix = 3*theta-11.8*t+.65*math.sin(6.6*t)
            twist = helix + .44*math.sin(14*t-2*theta)
            lane = .5 + .5*math.cos(twist)
            fold = (.5 + .5*math.cos(twist+1.52))**4
            thread = (.5 + .5*math.cos(2*twist-.8+.49*math.sin(theta+9*t)))**8
            waist = .49 + .10*math.sin(2*theta+4.8*t)
            envelope = math.sin(math.pi*t)**1.13 * math.exp(-((t-waist)/.39)**2)
            noise = noise_vector(p*.82).x
            value = .065 + envelope*(.25 + .49*lane**1.9 + .21*fold + .12*thread + .09*noise)
            points.append(p)
            intensity.append(max(0,min(1,value)))
    points.append(seed_point(1, 0))
    intensity.append(intensity[0])
    faces = [(0, 1+(j+1)%n, 1+j) for j in range(n)]
    for k in range(steps-2):
        for j in range(n):
            a,b = 1+k*n+j,1+k*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
    last = len(points)-1
    for j in range(n):
        faces.append((last-n+j,last-n+(j+1)%n,last))
    obj = mesh_object("Levitating seed | plasma folds", points, faces,
                      [energy_finish("Violet | plasma folds", 2.3)], smooth=True)
    field = obj.data.attributes.new("plasma", "FLOAT", "POINT")
    field.data.foreach_set("value", intensity)


def anchor(angle, profile, section, t, across):
    intersections = [r + (s-r)*(across-a)/(b-a)
                     for (r,a),(s,b) in zip(section, section[1:] + section[:1])
                     if min(a,b) <= across < max(a,b)]
    return blade_section(angle, profile, [(min(intersections), across)], t)[0] + radial(angle)*.64


def branch(name, start, end, turns, width, gain, phase, overpass):
    n = 140
    points = []
    local_start, local_end = CORE_TILT.inverted() @ (start-CORE_ORIGIN), CORE_TILT.inverted() @ (end-CORE_ORIGIN)
    t0, t1 = (min(.92, max(.08, (v.z+5.25)/10.5)) for v in (local_start, local_end))
    directions = (v-seed_axis(t) for v,t in ((local_start,t0),(local_end,t1)))
    head, tail = (math.atan2(v.y/.79, v.x) for v in directions)
    travel = (tail-head+math.pi) % math.tau - math.pi + turns*math.tau
    radii = []
    normals = []
    for k in range(n+1):
        u = k/n
        radius = .36 + .53*math.sin(math.pi*u)**.78 + .21*math.sin(11*u+phase)**2
        radii.append(radius)
        theta = head+travel*(u*u*(3-2*u)) + .105*math.sin(math.tau*u)*math.sin(math.pi*u)
        t = t0+(t1-t0)*u
        tangent = seed_point(t, theta+.002) - seed_point(t, theta-.002)
        rise = seed_point(t+.002, theta) - seed_point(t-.002, theta)
        normal = tangent.cross(rise).normalized()
        normals.append(normal)
        lift = sum(height * math.exp(-((u-level)/span)**2)
                   for level, span, height in overpass)
        p = seed_point(t, theta) + normal*(width*radius+.09+lift)
        if u < .172:
            f = 1-u/.172
            p = p.lerp(start, f*f*(3-2*f))
        if u > .828:
            f = (u-.828)/.172
            p = p.lerp(end, f*f*(3-2*f))
        points.append(p)
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth, curve.bevel_resolution = width, 4
    curve.use_fill_caps = True
    spline = curve.splines.new("POLY")
    spline.points.add(n)
    for p, loc, radius in zip(spline.points, points, radii):
        p.co = (*loc, 1)
        p.radius = radius
    obj = bpy.data.objects.new(name, curve)
    vrlib.link_to_source(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    obj.data.materials.append(energy_finish(name+" | emission", 1.9*gain, current=True))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.00001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    track = KDTree(len(points))
    for i, point in enumerate(points):
        track.insert(point, i)
    track.balance()
    field = obj.data.attributes.new("plasma", "FLOAT", "POINT")
    for point, vert in zip(field.data, obj.data.vertices):
        spine, i, _ = track.find(vert.co)
        u = i/n
        ridge = max(0, (vert.co-spine).normalized().dot(normals[i]))**2.6
        pulse = math.sin(15*u+phase+.45*math.sin(19*u))**2
        point.value = .57 + .25*ridge + .12*pulse + .065*noise_vector(vert.co*3.5).x
    for face in obj.data.polygons:
        face.use_smooth = True


def earth_bed(name, angle, base, rng):
    distance, _, depth, width, drift = base
    forward, across = radial(angle), radial(angle+math.pi/2)
    centre = forward*(distance-.19) + across*drift
    n = 48
    rows = []
    phase = rng.uniform(0, math.tau)
    for span, height in ((.96,-.055), (1,-.009), (.81,.078), (.65,.22), (.38,.32), (.13,.28)):
        row = []
        for j in range(n):
            theta = j*math.tau/n
            erosion = 1 + .08*math.sin(3*theta+phase) + .055*math.cos(7*theta-phase)
            p = centre + span*erosion*((depth+.62)*math.cos(theta)*forward
                                       + (width+.79)*math.sin(theta)*across)
            p.z = max(-.055, height + min(.16, height+.09)*noise_vector(p*2.15).z)
            row.append(p)
        rows.append(row)
    return mesh_object(name+" | settled mineral earth", *loft(rows), ["dirt_path"], smooth=True)


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
    paths = [
        ("Primary current", (0,.29,-.15,.61), (1,.70,.16,.53), 1,.246,1,1.3, ((.887,.08,.38),)),
        ("Return current", (2,.45,.16,.55), (0,.78,-.10,.50), -1,.158,.94,3.2, ((.544,.11,.59),)),
        ("Lower winding", (3,.64,-.15,.54), (1,.42,-.20,.51), 0,.194,.97,1.8, ((.48,.14,.75),)),
        ("Upper winding", (1,.60,.15,.49), (2,.96,.06,.39), 0,.132,.92,4.0, ()),
    ]
    limestone = limestone_finish()
    for index, (name, angle, profile, breaks, section) in enumerate(sails):
        sockets = [seat[1:] for _,start,end,*_ in paths for seat in (start,end) if seat[0] == index]
        rib(name, angle, profile, breaks, section, sockets, rng, limestone)
        earth_bed(name, angle, profile[0], rng)
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
    for name, angle, profile, _, section in sails:
        bed = blade_section(angle, profile, section, .005)
        centre = sum(bed, Vector())/len(bed)
        outline = [(centre.x+1.18*(v.x-centre.x), centre.y+1.13*(v.y-centre.y)) for v in bed]
        shaped_stone(name+" | buried foundation course", outline, -.042,
                     rng.uniform(.32,.46), rng, "monument_weathered", True)
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
                     extent*rng.uniform(.32,.76), rng, "monument_weathered", True)
    body()

    def seat(spec):
        index, t, across, _ = spec
        _, angle, profile, _, section = sails[index]
        return anchor(angle, profile, section, t, across)

    for name, start, end, *spec in paths:
        branch(name, seat(start), seat(end), *spec)
    rotation = Quaternion(Vector((0,0,1)), .86).to_matrix().to_4x4()
    for obj in vrlib.source_objects():
        obj.data.transform(rotation)

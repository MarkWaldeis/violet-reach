"""Pale lake-shore limestone; donor geometry at 20% relief and unchanged shader."""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import vrlib
import vrmat

ASSET = "shore_stones_a"
SEED = 91411
HALF = 10.6
BOTTOM = -.058
BANK_LENGTH = 6.1
_TEMPLATES = {}


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
        radial = 1 + (.026 if form == "worn" else .018)*coarse
        for nx, ny, nz, upper in cuts:
            dot = nx*u+ny*v+nz*w
            if dot > .28:
                radial = eased_min(radial, upper/dot, .035 if form != "worn" else .095)
        lamina = math.sin((19+7*weather)*(w+.22*u-.14*v) + .76*coarse)
        breakout = smooth(.44 + 1.25*medium - .43*weather)
        radial *= (1 + (.0052+.0032*weather)*medium + .0026*fine
                   - .0086*chip*breakout + (.0038 if form == "slab" else .002)*lamina)
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


def link_mesh(name, verts, faces, material):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    vrlib.link_to_source(obj)
    return obj


def fines_bed(name, radius, material, height=.16, slope=False):
    height=min(height,.018)
    verts=[(0,0,min(1.8,1.6*math.tan(math.radians(32)))-.005 if slope else height)]
    count,rings=96,28
    for row in range(1,rings+1):
        r=row/rings
        for j in range(count):
            angle=math.tau*j/count
            irregular=1+.13*math.sin(angle*3+.4)+.075*math.sin(angle*5+1)+.035*math.sin(angle*9)
            x,y=radius[0]*r*math.cos(angle)*irregular,radius[1]*r*math.sin(angle)*irregular
            z=height*(1-r**3)
            if slope:
                z=max(0,(y+1.6)*math.tan(math.radians(32)))*max(0,1-(abs(x)/radius[0])**4)
                z=min(1.8,z)*(1-r**12)
            z+=.012*noise.noise(Vector((x*31,y*31,3)))*(1-r*r)
            z-=.025*smooth((r-.55)/.45)
            verts.append((x,y,z-.005))
    faces=[(0,1+j,1+(j+1)%count) for j in range(count)]
    for row in range(rings-1):
        a,b=1+row*count,1+(row+1)*count
        faces.extend((a+j,b+j,b+(j+1)%count,a+(j+1)%count) for j in range(count))
    last=1+(rings-1)*count
    bottom=len(verts)
    verts.extend((verts[last+j][0],verts[last+j][1],-.045) for j in range(count))
    faces.extend((last+j,bottom+j,bottom+(j+1)%count,last+(j+1)%count) for j in range(count))
    faces.append(tuple(reversed(range(bottom,bottom+count))))
    obj=link_mesh(name,verts,faces,material)
    coverage=obj.data.attributes.new(name="bed_coverage",type="FLOAT",domain="POINT")
    coverage.data[0].value=1
    for row in range(1,rings+1):
        for j in range(count):
            coverage.data[1+(row-1)*count+j].value=1-smooth((row/rings-.38)/.28)
    obj["gravel_apron"]=True
    return obj


def finish():
    bpy.context.view_layer.update()
    objects = vrlib.source_objects()
    if not objects:
        raise ValueError("Empty source collection")
    lo, hi = vrlib.world_bounds(objects)
    shift = Vector(((lo.x+hi.x)*.5, (lo.y+hi.y)*.5, 0))
    for obj in vrlib.source_objects():
        obj.location -= shift
    vrlib.use_cycles_cpu(bpy.context.scene, 32)


def plane_cut(obj, point, normal):
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    result=bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                                 dist=.000001,plane_co=point,plane_no=normal,clear_outer=True)
    boundary=[e for e in result["geom_cut"] if isinstance(e,bmesh.types.BMEdge) and e.is_boundary]
    if boundary:
        caps=bmesh.ops.holes_fill(bm,edges=boundary,sides=0)["faces"]
        for face in caps:face.smooth=False
    bmesh.ops.triangulate(bm,faces=list(bm.faces),quad_method="BEAUTY",ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()


def fracture_detail(obj, radius, form, seed):
    rng=random.Random(seed+4301)
    points=[v.co.copy() for v in obj.data.vertices]
    lo=Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
    middle=(lo+hi)*.5
    for j in range(2):
        theta=rng.uniform(0,math.tau) if j==0 else theta+2.1
        normal=Vector((math.cos(theta),math.sin(theta),1.6 if form=="worn" else .22)).normalized()
        support=max(v.co.dot(normal) for v in obj.data.vertices)
        plane_cut(obj,normal*(support-radius*(.10 if form=="worn" else .065)),normal)
    if form=="worn":
        plane_cut(obj,Vector((0,0,lo.z+(hi.z-lo.z)*.035)),Vector((0,0,-1)))
        obj["fracture_steps"]=0
        obj["edge_chips"]=0
        obj["worn_facets"]=2
        return
    offsets=[]
    for j,fraction in enumerate((.36,.71)):
        bm=bmesh.new()
        bm.from_mesh(obj.data)
        normal=Vector((rng.uniform(-.12,.12),rng.uniform(-.12,.12),1)).normalized()
        point=Vector((middle.x,middle.y,lo.z+(hi.z-lo.z)*(fraction+rng.uniform(-.04,.04))))
        width=max(.006,radius*.018)
        theta=rng.uniform(0,math.tau)
        side=Vector((math.cos(theta),math.sin(theta),0))
        side_start=middle+side*radius*.12
        side_width=radius*.30
        for location in (point,point+normal*width):
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                                  plane_co=location,plane_no=normal,dist=.0000001)
        for location in (side_start,side_start+side*side_width):
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                                  plane_co=location,plane_no=side,dist=.0000001)
        distance=radius*rng.uniform(.045,.065)
        direction=-side*distance
        for face in bm.faces:
            heights=[(v.co-point).dot(normal) for v in face.verts]
            if min(heights)>-.000001 and max(heights)<width+.000001 and (face.calc_center_median()-side_start).dot(side)>0:face.smooth=False
        for v in bm.verts:
            amount=min(1,max(0,(v.co-point).dot(normal)/width))
            lateral=min(1,max(0,(v.co-side_start).dot(side)/side_width))
            v.co+=direction*amount*lateral
        bmesh.ops.triangulate(bm,faces=list(bm.faces),quad_method="BEAUTY",ngon_method="BEAUTY")
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()
        offsets.append(distance)
    for j in range(3):
        theta=rng.uniform(0,math.tau)
        normal=Vector((math.cos(theta),math.sin(theta),rng.uniform(.25,.95))).normalized()
        support=max(v.co.dot(normal) for v in obj.data.vertices)
        plane_cut(obj,normal*(support-radius*rng.uniform(.045,.08)),normal)
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm,faces=list(bm.faces),quad_method="BEAUTY",ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj["fracture_steps"]=2
    obj["edge_chips"]=3
    obj["fracture_step_offsets_m"]=offsets


def shore_stone(name, radius, flat, centre, seed, material, level=6, form="split", shape=0):
    if radius <= 0 or flat <= 0 or level < 1:
        raise ValueError("Positive radius, flattening and subdivision level required")
    palette = {key:value["linear_rgb"] for key,value in vrmat.load_palette().items()}
    sample = _TEMPLATES.setdefault(2,ico(2))
    target = blend(palette["canyon_strata"],palette["canyon_chalk"],.5)
    target = tuple(c/sum(target) for c in target)
    for attempt in range(512):
        selected = seed+attempt*7919
        probe = Mesh()
        cobble(probe,palette,sample,0,3,radius,flat,random.Random(selected),form)
        rgb = tuple(sum(c[i] for c in probe.colors)/len(probe.colors) for i in range(3))
        luminance = sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))
        chroma = tuple(c/sum(rgb) for c in rgb)
        if .33<=luminance<=.39 and max(abs(a-b) for a,b in zip(chroma,target))<.018:
            break
    else:
        raise RuntimeError("No pale limestone seed found")
    if level not in _TEMPLATES:
        _TEMPLATES[level] = ico(level)
    mesh = Mesh()
    cobble(mesh,palette,_TEMPLATES[level],0,3,radius,flat,random.Random(selected),form)
    lo = Vector(tuple(min(p[i] for p in mesh.verts) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in mesh.verts) for i in range(3)))
    height_scale = flat*max(hi.x-lo.x,hi.y-lo.y)/(hi.z-lo.z)
    mesh.verts = [(p[0],p[1],lo.z+(p[2]-lo.z)*height_scale) for p in mesh.verts]
    if form=="worn":
        mx,my=(lo.x+hi.x)*.5,(lo.y+hi.y)*.5
        mesh.verts=[(mx+(p[0]-mx)*1.17+.16*(p[2]-lo.z),my+(p[1]-my)*.76,p[2]) for p in mesh.verts]
    elif shape==1:
        mx,my=(lo.x+hi.x)*.5,(lo.y+hi.y)*.5
        mesh.verts=[(mx+(p[0]-mx)*1.45,my+(p[1]-my)*.65,p[2]) for p in mesh.verts]
    hi.z = lo.z+(hi.z-lo.z)*height_scale
    middle = (lo+hi)*.5
    datum = centre[2] if len(centre)>2 else -.027
    offset = Vector((centre[0]-middle.x,centre[1]-middle.y,datum-lo.z))
    mesh.verts=[Vector(p)+offset for p in mesh.verts]
    dry_colors=mesh.colors[:]
    nearest=KDTree(len(mesh.verts))
    for i,p in enumerate(mesh.verts):nearest.insert(p,i)
    nearest.balance()
    obj=mesh.object(name,(material,),"stone_tones","stone_saturation")
    if level>=6:
        fracture_detail(obj,radius,form,selected)
        bottom=min(v.co.z for v in obj.data.vertices)
        for v in obj.data.vertices:v.co.z+=datum-bottom
    dry_layer=obj.data.color_attributes.new(name="stone_dry_tones",type="FLOAT_COLOR",domain="POINT")
    base_layer=obj.data.attributes.new(name="stone_base_z",type="FLOAT",domain="POINT")
    wet_height = min(.14,max(.002,(max(v.co.z for v in obj.data.vertices)-min(v.co.z for v in obj.data.vertices))*.75))
    height_layer=obj.data.attributes.new(name="stone_wet_height",type="FLOAT",domain="POINT")
    tint=random.Random(seed+99).uniform(.80,1.08) if level<6 else 1
    for v in obj.data.vertices:
        dry=scale(dry_colors[nearest.find(v.co)[1]],tint)
        if level<6:dry=blend(dry,palette["canyon_chalk" if seed%2 else "canyon_strata"],.12)
        wet=1-smooth((v.co.z-datum-wet_height*.40)/(wet_height*.60))
        soaked=scale(blend(dry,palette["shore_wet"],.33),.36)
        obj.data.color_attributes["stone_tones"].data[v.index].color=(*blend(dry,soaked,wet),1)
        dry_layer.data[v.index].color=(*dry,1)
        obj.data.attributes["stone_saturation"].data[v.index].value=wet
        base_layer.data[v.index].value=datum
        height_layer.data[v.index].value=wet_height
    obj["approved_generator"] = "pr9/lake_shore_a.cobble"
    obj["recipe_seed"] = selected
    obj["requested_seed"] = seed
    obj["stone_piece"] = True
    obj["wet_gradient_height_m"] = wet_height
    obj["wet_base_z"] = datum
    obj["stone_form"] = form
    obj["height_width_ratio"] = flat
    obj["donor_displacement_multiplier"] = .2
    obj["pebble_shape"]=shape
    obj["pebble_tint"]=tint
    return obj


def xy_bounds(obj):
    points = [v.co for v in obj.data.vertices]
    return (min(p.x for p in points),max(p.x for p in points),
            min(p.y for p in points),max(p.y for p in points))


def overlaps(bounds, occupied, margin=.025):
    a,b,c,d = bounds
    return any(a < y+margin and b > x-margin and c < v+margin and d > u-margin
               for x,y,u,v in occupied)


def stone_tree(obj):
    return BVHTree.FromPolygons([v.co for v in obj.data.vertices],
                               [tuple(f.vertices) for f in obj.data.polygons])


def inside(tree, point):
    origin = Vector(point)
    direction = Vector((.173,.089,1)).normalized()
    count = 0
    for _ in range(64):
        hit = tree.ray_cast(origin,direction)[0]
        if hit is None:
            return count%2==1
        count += 1
        origin = hit+direction*.00001
    raise RuntimeError("Ambiguous containment")


def wet_finish(material):
    nodes,links=material.node_tree.nodes,material.node_tree.links
    bsdf=nodes["Principled BSDF"]
    coord=nodes.new("ShaderNodeTexCoord")
    separate=nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["Object"],separate.inputs["Vector"])
    base=nodes.new("ShaderNodeAttribute")
    base.attribute_name="stone_base_z"
    height=nodes.new("ShaderNodeAttribute")
    height.attribute_name="stone_wet_height"
    subtract=nodes.new("ShaderNodeMath")
    subtract.operation="SUBTRACT"
    links.new(separate.outputs["Z"],subtract.inputs[0])
    links.new(base.outputs["Fac"],subtract.inputs[1])
    divide=nodes.new("ShaderNodeMath")
    divide.operation="DIVIDE"
    links.new(subtract.outputs[0],divide.inputs[0])
    links.new(height.outputs["Fac"],divide.inputs[1])
    rough_range=next(n for n in nodes if n.type=="MAP_RANGE" and n.inputs["Value"].is_linked
                     and n.inputs["Value"].links[0].from_node.type=="ATTRIBUTE"
                     and n.inputs["Value"].links[0].from_node.attribute_name=="stone_saturation")
    mask=nodes.new("ShaderNodeMapRange")
    mask.name="Physical_wet_band"
    mask.interpolation_type="SMOOTHSTEP"
    mask.inputs["From Min"].default_value=.40
    mask.inputs["From Max"].default_value=1
    mask.inputs["To Min"].default_value=1
    mask.inputs["To Max"].default_value=0
    links.new(divide.outputs[0],mask.inputs["Value"])
    links.new(mask.outputs["Result"],rough_range.inputs["Value"])
    color=nodes.new("ShaderNodeMixRGB")
    color.blend_type="MULTIPLY"
    color.inputs[2].default_value=(.20,.24,.27,1)
    links.new(bsdf.inputs["Base Color"].links[0].from_socket,color.inputs[1])
    links.new(mask.outputs["Result"],color.inputs[0])
    links.new(color.outputs[0],bsdf.inputs["Base Color"])


def feather_finish(material):
    nodes,links=material.node_tree.nodes,material.node_tree.links
    bsdf=nodes["Principled BSDF"]
    cover=nodes.new("ShaderNodeAttribute")
    cover.attribute_name="bed_coverage"
    palette={key:value["linear_rgb"] for key,value in vrmat.load_palette().items()}
    ground=blend(blend(palette["canyon_strata"],palette["water_shallow"],.5),palette["grass_green"],.2)
    color=nodes.new("ShaderNodeMixRGB")
    color.name="Opaque_ground_blend"
    color.inputs[1].default_value=(*ground,1)
    links.new(bsdf.inputs["Base Color"].links[0].from_socket,color.inputs[2])
    links.new(cover.outputs["Fac"],color.inputs[0])
    links.new(color.outputs[0],bsdf.inputs["Base Color"])
    rough=nodes.new("ShaderNodeMixRGB")
    rough.inputs[1].default_value=(.9,.9,.9,1)
    links.new(bsdf.inputs["Roughness"].links[0].from_socket,rough.inputs[2])
    links.new(cover.outputs["Fac"],rough.inputs[0])
    links.new(rough.outputs[0],bsdf.inputs["Roughness"])
    for node in list(nodes):
        if node.type=="BUMP":
            strength=nodes.new("ShaderNodeMath")
            strength.operation="MULTIPLY"
            strength.inputs[1].default_value=node.inputs["Strength"].default_value
            links.new(cover.outputs["Fac"],strength.inputs[0])
            links.new(strength.outputs[0],node.inputs["Strength"])
    bsdf.inputs["Alpha"].default_value=1


def contact_stone(obj, other, direction, obstacles):
    bounds=xy_bounds(obj)
    origin=Vector(((bounds[0]+bounds[1])*.5,(bounds[2]+bounds[3])*.5,0))
    target_bounds=xy_bounds(other)
    target=Vector(((target_bounds[0]+target_bounds[1])*.5,(target_bounds[2]+target_bounds[3])*.5,0))
    reach=math.hypot(bounds[1]-bounds[0],bounds[3]-bounds[2])+math.hypot(target_bounds[1]-target_bounds[0],target_bounds[3]-target_bounds[2])
    original=[v.co.copy() for v in obj.data.vertices]
    tree=stone_tree(other)
    def place(distance,angle):
        delta=target+Vector((math.cos(angle),math.sin(angle),0))*distance-origin
        for v,p in zip(obj.data.vertices,original):v.co=p+delta
        candidate=stone_tree(obj)
        middle=sum((v.co for v in obj.data.vertices),Vector())/len(obj.data.vertices)
        return candidate,middle
    theta=math.atan2(direction[1],direction[0])
    for attempt in range(13):
        angle=theta+((attempt+1)//2)*(.19 if attempt%2 else -.19)
        low,high=0,reach
        for _ in range(15):
            distance=(low+high)*.5
            candidate,middle=place(distance,angle)
            if candidate.overlap(tree) or inside(tree,middle):low=distance
            else:high=distance
        candidate,middle=place(high+.0015,angle)
        if not any(candidate.overlap(t) or inside(t,middle) for t in obstacles):
            obj["contact_partner"]=other.name
            obj["contact_gap_limit_m"]=.004
            return
    raise RuntimeError("Cannot place non-intersecting contact stone")


def build():
    noise.seed_set(SEED)
    rng = random.Random(SEED)
    stone = socket_material("river_stones","Shinglewake | weathered cobbles with soaked bases",
                            "stone_dry_tones",.96,"stone_saturation",(.72,.12))
    wet_finish(stone)
    bedmat = socket_material("dirt_path","Wet limestone fines","bank_tones",.94,
                             "ground_moisture",(.84,.31))
    feather_finish(bedmat)
    bed = fines_bed("Feuchtes_Kiesbett",(2.45,2.0),bedmat,.018)
    tones = bed.data.color_attributes.new(name="bank_tones",type="FLOAT_COLOR",domain="POINT")
    wet = bed.data.attributes.new(name="ground_moisture",type="FLOAT",domain="POINT")
    palette = vrmat.load_palette()
    for v in bed.data.vertices:
        tones.data[v.index].color = tuple(palette["path_sand"]["linear_rgb"])+(1,)
        wet.data[v.index].value = .8
    bed_tree = BVHTree.FromPolygons([v.co for v in bed.data.vertices],
                                   [tuple(f.vertices) for f in bed.data.polygons])
    def seated(x,y,radius):
        hit = bed_tree.ray_cast(Vector((x,y,1)),Vector((0,0,-1)),2)[0]
        if hit is None:
            raise ValueError("Stone is outside gravel bed at %s"%((x,y),))
        return (x,y,-.018 if radius>.15 else hit.z-min(.018,radius*.20))
    anchors = ((-1.1,-.4,.82,"slab",.42,0,-1),(-1.8,.25,.48,"split",.53,0,0),
               (.7,.7,.68,"split",.50,1,-1),(1.7,.7,.49,"worn",.32,1,2),
               (.8,-.85,.46,"worn",.32,2,-1),(1.4,-1.4,.26,"slab",.40,2,4),
               (-1.05,1.25,.27,"split",.48,3,-1),(-.4,-1.5,.18,"slab",.34,4,-1))
    occupied = []
    large_trees = []
    large_centres = []
    primary=[]
    for i,(x,y,radius,form,flat,group,partner) in enumerate(anchors):
        obj=shore_stone("Uferstein_%02d"%i,radius,flat,(x,y,-.018),SEED+100+i,stone,6,form)
        obj["cluster_group"]=group
        if partner>=0:
            contact_stone(obj,primary[partner],(x-anchors[partner][0],y-anchors[partner][1]),large_trees)
        tree=stone_tree(obj)
        midpoint=sum((v.co for v in obj.data.vertices),Vector())/len(obj.data.vertices)
        if any(tree.overlap(t) or inside(t,midpoint) or inside(tree,p) for t,p in zip(large_trees,large_centres)):
            raise RuntimeError("Intersecting primary placement %d"%i)
        large_trees.append(tree)
        large_centres.append(midpoint)
        primary.append(obj)
    feet=[[v.co.copy() for v in o.data.vertices if v.co.z<o["wet_base_z"]+.055] for o in primary]
    centres=[Vector(((xy_bounds(o)[0]+xy_bounds(o)[1])*.5,(xy_bounds(o)[2]+xy_bounds(o)[3])*.5,0)) for o in primary]
    foot_support=[]
    for points,centre in zip(feet,centres):
        foot_support.append([max(points,key=lambda p:(p-centre).dot(Vector((math.cos(math.tau*j/64),math.sin(math.tau*j/64),0)))) for j in range(64)])
    gravel = []
    foot_count=0
    for i in range(780):
        radius = rng.uniform(.055,.15) if i < 28 else rng.uniform(.009,.055)
        against_foot=i%10!=0
        for attempt in range(120):
            if against_foot:
                anchor=rng.randrange(len(primary))
                angle=(anchor*.9+rng.choice((0,2.7))+rng.gauss(0,.5))%math.tau
                direction=Vector((math.cos(angle),math.sin(angle),0))
                p=foot_support[anchor][int(angle/math.tau*64)]
                p=p+direction*(radius*1.4+rng.uniform(0,.24))
                x,y=p.x,p.y
            else:
                x,y=rng.uniform(-2.5,2.5),rng.uniform(-1.9,1.9)
            radial=math.hypot(x/2.5,y/1.9)
            if rng.random()>1-smooth((radial-.60)/.50):
                continue
            if bed_tree.ray_cast(Vector((x,y,1)),Vector((0,0,-1)),2)[0] is None:
                continue
            bounds = (x-radius*1.5,x+radius*1.5,y-radius*1.5,y+radius*1.5)
            if not overlaps(bounds,occupied,.005):
                obj = shore_stone("Zwischenkiesel_%03d"%i,radius,rng.uniform(.20,.62),seated(x,y,radius),
                                  SEED+1000+i,stone,4 if i < 28 else 2,
                                  ("split","slab","worn")[i%3],i%3)
                tree=stone_tree(obj)
                midpoint=sum((v.co for v in obj.data.vertices),Vector())/len(obj.data.vertices)
                if any(tree.overlap(t) or inside(t,midpoint) for t in large_trees):
                    bpy.data.objects.remove(obj,do_unlink=True)
                    continue
                break
        else:
            continue
        occupied.append(xy_bounds(obj))
        foot_count+=against_foot
        if i >= 28:
            gravel.append(obj)
    if gravel:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in gravel:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = gravel[0]
        bpy.ops.object.join()
        gravel[0].name = "Modellierter_Kalkgrus"
        gravel[0]["modelled_grit_count"] = len(gravel)
        gravel[0]["foot_biased_fraction"]=foot_count/(len(gravel)+28)
        del gravel[0]["stone_piece"]
    finish()

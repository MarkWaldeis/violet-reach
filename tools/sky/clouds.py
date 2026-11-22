"""Haufenwolken als Six-Way-Lightmap-Atlas.

Zwei Stufen, ein Skript:

1) Blender (Volumen bauen + rendern, Cycles CPU):
   blender -b --factory-startup --python tools/sky/clouds.py -- [--only NAME] [--res 1024] [--samples 96]
   -> je Wolke 7 Durchlaeufe als .npy (float32, linear, vormultipliziert) im Build-Ordner.

2) System-Python (Atlas packen + Pruefbilder):
   python tools/sky/clouds.py
   -> web/explore/public/sky/clouds_lightA.webp, clouds_lightB.webp, clouds.json
   -> Pruefbilder in devin-screenshots/violet-reach/sky/

Durchlaeufe (Bildraum der Frontkamera: +X rechts, +Y oben, +Z zur Kamera):
  px  Sonne von rechts        nx  von links
  py  von oben                ny  von unten
  pz  von vorn (Kameraseite)  nz  von hinten (Durchlicht)
  amb gleichmaessiger weisser Himmel, keine Sonne (Umgebungslicht)
Blender-Achsen: Kamera bei -Y blickt nach +Y, Z oben -> Bild +X = Blender +X,
Bild +Y = Blender +Z, Bild +Z (zur Kamera) = Blender -Y.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.environ.get("VR_SKY_BUILD", os.path.join(os.environ.get("TEMP", "/tmp"), "vrsky_build", "clouds"))
SHOTS = os.path.join(os.path.expanduser("~"), "devin-screenshots", "violet-reach", "sky")
OUT = os.path.join(ROOT, "web", "explore", "public", "sky")
PASSES = ["px", "nx", "py", "ny", "pz", "nz", "amb"]
# Lichtrichtung (woher das Licht kommt) in Blender-Koordinaten
LIGHT_FROM = {"px": (1, 0, 0), "nx": (-1, 0, 0), "py": (0, 0, 1), "ny": (0, 0, -1),
              "pz": (0, -1, 0), "nz": (0, 1, 0)}
SUN_STRENGTH = 3.0
CELL = 1024

sys.path.insert(0, HERE)


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    o = {"only": None, "res": 384, "samples": 20, "passes": PASSES}
    i = 0
    while i < len(a):
        if a[i] == "--only":
            o["only"] = a[i + 1].split(","); i += 1
        elif a[i] == "--res":
            o["res"] = int(a[i + 1]); i += 1
        elif a[i] == "--samples":
            o["samples"] = int(a[i + 1]); i += 1
        elif a[i] == "--passes":
            o["passes"] = a[i + 1].split(","); i += 1
        i += 1
    return o


# ==========================================================================
# Stufe 1: Blender
# ==========================================================================
def blender_main():
    import bpy
    import numpy as np
    import openvdb
    from mathutils import Vector
    import cloudfield as cf

    opt = args()
    os.makedirs(BUILD, exist_ok=True)
    meta_all = {}
    meta_path = os.path.join(BUILD, "meta.json")
    if os.path.exists(meta_path):
        meta_all = json.load(open(meta_path))

    for name, spec, seed in cf.catalog():
        if opt["only"] and name not in opt["only"]:
            continue
        def _has_pass(p):
            np_path = os.path.join(BUILD, "%s_%s.npy" % (name, p))
            if not os.path.exists(np_path):
                return False
            try:
                arr = np.load(np_path, mmap_mode="r")
                return arr.shape[0] >= opt["res"] and arr.shape[1] >= opt["res"]
            except Exception:
                return False

        if name in meta_all and all(_has_pass(p) for p in opt["passes"]):
            print("[clouds] %s komplett vorhanden (%dx%d), ueberspringe" % (name, opt["res"], opt["res"]), flush=True)
            continue

        t0 = time.time()
        # Voxelgroesse aus der groessten Ausdehnung
        body = np.array(spec["body"])
        ext = max((body[:, 0] + body[:, 3]).max() - (body[:, 0] - body[:, 3]).min(),
                  spec["height"] * 1.3)
        voxel = ext / (430 if name.startswith("bank") else 300) * float(os.environ.get("VR_SKY_COARSE", "1"))
        dens, lo, v = cf.density_field(spec, seed, voxel)
        nz_idx = np.argwhere(dens > 1e-3)
        dlo = nz_idx.min(0) * v + lo
        dhi = (nz_idx.max(0) + 1) * v + lo
        t_field = time.time() - t0

        vdb_path = os.path.join(BUILD, name + ".vdb").replace("\\", "/")
        g = openvdb.FloatGrid()
        g.copyFromArray(dens, tolerance=1e-3)
        g.name = "density"
        g.transform = openvdb.createLinearTransform(voxelSize=v)
        openvdb.write(vdb_path, grids=[g])
        del dens

        # ---- Szene
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        sc.render.engine = "CYCLES"
        cy = sc.cycles
        cy.device = "CPU"
        cy.samples = opt["samples"]
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = 0.02
        cy.use_denoising = True
        cy.denoiser = "OPENIMAGEDENOISE"
        cy.max_bounces = 16
        cy.volume_bounces = 16
        cy.transparent_max_bounces = 8
        cy.diffuse_bounces = 0
        cy.glossy_bounces = 0
        for attr, val in (("volume_step_rate", 1.5), ("volume_preview_step_rate", 1.5),
                          ("volume_max_steps", 1024)):
            if hasattr(cy, attr):
                setattr(cy, attr, val)
        cy.seed = seed
        sc.render.film_transparent = True
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = 0.0
        sc.render.resolution_x = sc.render.resolution_y = opt["res"]
        sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = "OPEN_EXR"
        sc.render.image_settings.color_depth = "32"
        sc.render.image_settings.color_mode = "RGBA"
        sc.render.threads_mode = "AUTO"

        vol = bpy.data.volumes.new(name)
        vol.filepath = vdb_path
        ob = bpy.data.objects.new(name, vol)
        ob.location = Vector(lo)
        sc.collection.objects.link(ob)
        mat = bpy.data.materials.new(name + "_mat")
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        pv = nt.nodes.new("ShaderNodeVolumePrincipled")
        pv.inputs["Color"].default_value = (1, 1, 1, 1)
        pv.inputs["Density"].default_value = 1.0
        pv.inputs["Anisotropy"].default_value = 0.35
        pv.inputs["Absorption Color"].default_value = (0, 0, 0, 1)
        mo = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(pv.outputs[0], mo.inputs["Volume"])
        vol.materials.append(mat)

        # Kamera: orthografisch von vorn, quadratisch, Wolke zentriert
        w = dhi[0] - dlo[0]
        h = dhi[2] - dlo[2]
        size = max(w, h) * 1.04
        cx = 0.5 * (dlo[0] + dhi[0])
        cz = 0.5 * (dlo[2] + dhi[2])
        camd = bpy.data.cameras.new("cam")
        camd.type = "ORTHO"
        camd.ortho_scale = size
        camd.clip_start = 0.01
        camd.clip_end = 1000
        cam = bpy.data.objects.new("cam", camd)
        cam.location = (cx, dlo[1] - 5.0, cz)
        cam.rotation_euler = (math.pi / 2, 0, 0)
        sc.collection.objects.link(cam)
        sc.camera = cam

        world = bpy.data.worlds.new("w")
        sc.world = world
        bg = world.node_tree.nodes.get("Background")
        bg.inputs["Color"].default_value = (1, 1, 1, 1)

        sund = bpy.data.lights.new("sun", "SUN")
        sund.angle = math.radians(0.6)
        sund.energy = SUN_STRENGTH
        sun = bpy.data.objects.new("sun", sund)
        sc.collection.objects.link(sun)

        times = dict(meta_all.get(name, {}).get("render_s", {}))
        for p in opt["passes"]:
            npy_path = os.path.join(BUILD, "%s_%s.npy" % (name, p))
            if _has_pass(p):
                print("[clouds] %s %s vorhanden (%dx%d), ueberspringe" % (name, p, opt["res"], opt["res"]), flush=True)
                continue
            t1 = time.time()
            if p == "amb":
                sun.hide_render = True
                bg.inputs["Strength"].default_value = 1.0
            else:
                sun.hide_render = False
                bg.inputs["Strength"].default_value = 0.0
                d = Vector(LIGHT_FROM[p])
                # Sonne strahlt entlang lokal -Z: -Z soll nach -d zeigen
                sun.rotation_euler = (d).to_track_quat("Z", "Y").to_euler()
            exr = os.path.join(BUILD, "%s_%s.exr" % (name, p)).replace("\\", "/")
            sc.render.filepath = exr
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(exr)
            px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
            img.pixels.foreach_get(px)
            px = px.reshape(img.size[1], img.size[0], 4)[::-1]  # oben zuerst
            np.save(npy_path, px)
            bpy.data.images.remove(img)
            times[p] = round(time.time() - t1, 1)
            print("[clouds] %s %s %.1fs" % (name, p, times[p]), flush=True)

        # Bodenlinie (z = base) in Zellkoordinaten (0 oben .. 1 unten)
        base = spec.get("base", 0.0)
        top_z = cz + size / 2
        meta_all[name] = dict(
            seed=seed, voxel=v, grid=list(map(int, nz_idx.max(0) + 1)),
            extent_units=[float(w), float(dhi[1] - dlo[1]), float(h)],
            ortho_size=float(size), base_v=float((top_z - base) / size),
            content_uv=[float((dlo[0] - (cx - size / 2)) / size), float((top_z - dhi[2]) / size),
                        float((dhi[0] - (cx - size / 2)) / size), float((top_z - dlo[2]) / size)],
            field_s=round(t_field, 1), render_s=times, res=opt["res"], samples=opt["samples"])
        json.dump(meta_all, open(meta_path, "w"), indent=1)
        print("[clouds] %s fertig, Feld %.1fs, gesamt %.1fs" % (name, t_field, time.time() - t0), flush=True)


# ==========================================================================
# Stufe 2: Atlas (System-Python mit Pillow)
# ==========================================================================
def srgb_encode(x):
    import numpy as np
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_decode(x):
    import numpy as np
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def compose_main():
    import numpy as np
    from PIL import Image
    sys.path.insert(0, HERE)
    import cloudfield as cf

    meta = json.load(open(os.path.join(BUILD, "meta.json")))
    names = [c[0] for c in cf.catalog()]
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SHOTS, exist_ok=True)
    W, H = 4 * CELL, 2 * CELL
    data = {p: np.zeros((H, W), np.float32) for p in PASSES}
    alpha = np.zeros((H, W), np.float32)

    def load(n, p):
        a = np.load(os.path.join(BUILD, "%s_%s.npy" % (n, p)))
        if a.shape[0] != CELL:
            chans = [
                np.asarray(Image.fromarray(a[..., c].astype(np.float32), mode="F").resize((CELL, CELL), Image.BICUBIC))
                for c in range(a.shape[-1])
            ]
            a = np.stack(chans, axis=-1)
        return a

    # gemeinsame Normierung: hellster Lichtkanal (99.9-Perzentil) -> 1.0
    peaks = []
    for n in names:
        for p in PASSES[:6]:
            a = load(n, p)
            peaks.append(np.percentile(a[..., 0][a[..., 3] > 0.5], 99.9) if (a[..., 3] > 0.5).any() else 0)
    light_scale = 1.0 / max(peaks)
    amb_peaks = []
    for n in names:
        a = load(n, "amb")
        amb_peaks.append(np.percentile(a[..., 0][a[..., 3] > 0.5], 99.9))
    amb_scale = 1.0 / max(amb_peaks)

    cells = []
    for i, n in enumerate(names):
        cxi, cyi = i % 4, i // 4
        x0, y0 = cxi * CELL, cyi * CELL
        al = None
        for p in PASSES:
            a = load(n, p)
            # Luminanz der (weissen) Durchlaeufe, vormultipliziert
            lum = np.maximum(0.0, a[..., :3].mean(-1))
            data[p][y0:y0 + CELL, x0:x0 + CELL] = lum * (amb_scale if p == "amb" else light_scale)
            a_alpha = np.clip(a[..., 3], 0.0, 1.0)
            if al is None:
                al = a_alpha
            else:
                al = np.maximum(al, a_alpha)
        alpha[y0:y0 + CELL, x0:x0 + CELL] = al
        m = meta[n]
        u0, v0, u1, v1 = m["content_uv"]
        cells.append(dict(
            name=n, index=i,
            cell_px=[x0, y0, CELL, CELL],
            cell_uv=[x0 / W, y0 / H, (x0 + CELL) / W, (y0 + CELL) / H],
            content_px=[round(x0 + u0 * CELL), round(y0 + v0 * CELL), round(x0 + u1 * CELL), round(y0 + v1 * CELL)],
            aspect=round(m["extent_units"][0] / m["extent_units"][2], 4),
            baseline_v=round(m["base_v"], 4),
            baseline_px=round(y0 + m["base_v"] * CELL, 1),
            extent_units=[round(e, 3) for e in m["extent_units"]],
            cell_size_units=round(m["ortho_size"], 3),
            suggested_width_m=round(m["extent_units"][0] * 100.0),
        ))

    # Kanaele packen (RGB sRGB-kodiert, Alpha linear)
    def to8(x):
        return np.clip(np.round(x * 255), 0, 255).astype(np.uint8)
    A = np.stack([to8(srgb_encode(data["px"])), to8(srgb_encode(data["py"])),
                  to8(srgb_encode(data["pz"])), to8(alpha)], -1)
    B = np.stack([to8(srgb_encode(data["nx"])), to8(srgb_encode(data["ny"])),
                  to8(srgb_encode(data["nz"])), to8(data["amb"])], -1)
    pa = os.path.join(OUT, "clouds_lightA.webp")
    pb = os.path.join(OUT, "clouds_lightB.webp")
    Image.fromarray(A, "RGBA").save(pa, "WEBP", quality=90, alpha_quality=100, method=6, exact=False)
    Image.fromarray(B, "RGBA").save(pb, "WEBP", quality=90, alpha_quality=100, method=6, exact=False)

    info = dict(
        version=1,
        generator="tools/sky/clouds.py (Blender 5.2 Cycles CPU, Principled Volume, anisotropy 0.35)",
        atlas_size=[W, H], grid=[4, 2], cell_size=CELL,
        files=dict(lightA="clouds_lightA.webp", lightB="clouds_lightB.webp"),
        channels=dict(
            lightA=dict(R="+X Licht von rechts", G="+Y Licht von oben", B="+Z Licht von vorn (Kameraseite)",
                        A="Deckung (1 - Transmission), linear"),
            lightB=dict(R="-X Licht von links", G="-Y Licht von unten", B="-Z Licht von hinten (Durchlicht)",
                        A="Umgebungslicht (gleichmaessiger weisser Himmel), linear, vormultipliziert"),
        ),
        color_space=dict(RGB="sRGB-kodiert (Textur als SRGBColorSpace laden -> linear)", A="linear (nicht dekodieren)"),
        premultiplied=True,
        light_scale_note="Lichtkanaele: gemessene Strahldichte * light_scale (Sonne 1.0 -> 99.9-Perzentil des hellsten Kanals = 1.0). "
                         "Ambient: Strahldichte * amb_scale.",
        light_scale=float(light_scale), amb_scale=float(amb_scale), sun_strength_render=SUN_STRENGTH,
        baseline_note="baseline_v: Zeile der flachen Wolkenunterseite in Zellkoordinaten (0 = Zelloberkante, 1 = Zellunterkante).",
        units_note="extent_units: Breite (x), Tiefe, Hoehe in Wolkeneinheiten; suggested_width_m nimmt 1 Einheit = 100 m an.",
        clouds=cells,
    )
    json.dump(info, open(os.path.join(OUT, "clouds.json"), "w"), indent=1, ensure_ascii=False)
    print("Atlas:", pa, os.path.getsize(pa), pb, os.path.getsize(pb))

    # ---------------- Pruefbilder (aus den gespeicherten WebP gelesen)
    A2 = np.asarray(Image.open(pa)).astype(np.float32) / 255
    B2 = np.asarray(Image.open(pb)).astype(np.float32) / 255
    chans = {"px": srgb_decode(A2[..., 0]), "py": srgb_decode(A2[..., 1]), "pz": srgb_decode(A2[..., 2]),
             "nx": srgb_decode(B2[..., 0]), "ny": srgb_decode(B2[..., 1]), "nz": srgb_decode(B2[..., 2]),
             "amb": B2[..., 3]}
    al = A2[..., 3]
    sky = srgb_decode(np.array([0x70, 0x8C, 0xAB], np.float32) / 255)
    cream = srgb_decode(np.array([0xE6, 0xE1, 0xCE], np.float32) / 255)
    shade = srgb_decode(np.array([0x8F, 0x9F, 0xB8], np.float32) / 255)   # blaugraue Himmelsfuellung

    def lit(L, sun_gain, amb_gain):
        L = np.array(L, np.float32); L /= np.linalg.norm(L)
        w = L * L   # Six-Way: Gewichte = quadrierte Komponenten
        sx = chans["px"] if L[0] > 0 else chans["nx"]
        sy = chans["py"] if L[1] > 0 else chans["ny"]
        sz = chans["pz"] if L[2] > 0 else chans["nz"]
        s = w[0] * sx + w[1] * sy + w[2] * sz
        col = s[..., None] * cream[None, None] * sun_gain + chans["amb"][..., None] * shade[None, None] * amb_gain
        bgc = np.broadcast_to(sky, col.shape)
        out = col + bgc * (1 - al[..., None])        # vormultipliziert
        out = out / (1 + out * 0.15)                  # sanftes Tonemapping
        return (srgb_encode(out) * 255).astype(np.uint8)

    for tag, L, sg, ag in (("front_top", (0.45, 0.6, 0.66), 1.25, 0.55), ("backlight", (0.25, 0.35, -0.9), 2.2, 0.55)):
        img = lit(L, sg, ag)
        Image.fromarray(img).resize((W // 2, H // 2), Image.LANCZOS).save(os.path.join(SHOTS, "clouds_check_%s.jpg" % tag), quality=92)
    # Kanal-Uebersicht einer Zelle
    row = [chans[p][:CELL, :CELL] for p in PASSES]
    sheet = np.concatenate(row, 1)
    Image.fromarray((srgb_encode(sheet) * 255).astype(np.uint8)).resize((7 * 384, 384), Image.LANCZOS).save(
        os.path.join(SHOTS, "clouds_channels_cell0.jpg"), quality=90)
    print("Pruefbilder in", SHOTS)


if __name__ == "__main__":
    try:
        import bpy  # noqa
        blender_main()
    except ImportError:
        compose_main()

"""Kachelnde Wasser-Normalen und Schaumkarte aus dem Ocean-Modifier.

1) Blender:  blender -b --factory-startup --python tools/sky/water.py
   backt zwei Ozeane (klein: Kraeuselwellen, gross: Wellen) per ocean_bake als EXR
   (Verschiebung + Schaum) und legt sie als .npy im Build-Ordner ab.
2) Python:   python tools/sky/water.py
   rechnet daraus periodische Tangentenraum-Normalen (zentrale Differenzen mit
   Wrap-around -> exakt kachelnd) und die Schaumkarte, schreibt
   web/explore/public/water/water_normal_a.webp, water_normal_b.webp, water_foam.webp
   und 3x3-Pruefbilder.

Normalen-Konvention: Tangentenraum, R = +X (u, nach rechts), G = +Y (v, Bild nach OBEN,
OpenGL/three.js-Konvention), B = +Z (aus der Flaeche); kodiert n*0.5+0.5, linear.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(os.environ.get("TEMP", "/tmp"), "vrsky_build", "water")
SHOTS = os.path.join(os.path.expanduser("~"), "devin-screenshots", "violet-reach", "sky")
OUT = os.path.join(ROOT, "web", "explore", "public", "water")
RES = 1024

# Ozean-Parameter (feste Seeds). spatial_size = Kachelkante in Metern.
OCEANS = {
    "a": dict(spatial_size=4, wind_velocity=3.2, wave_scale=1.0, choppiness=0.9, seed=4021,
              spectrum="PHILLIPS", wave_alignment=0.35, wave_direction=0.6, damping=0.6,
              wave_scale_min=0.02, foam_coverage=0.0),
    "b": dict(spatial_size=48, wind_velocity=9.0, wave_scale=1.0, choppiness=1.2, seed=7310,
              spectrum="PIERSON_MOSKOWITZ", wave_alignment=0.5, wave_direction=0.6, damping=0.5,
              wave_scale_min=0.05, foam_coverage=0.25),
}


def blender_main():
    import time
    import bpy
    import numpy as np
    os.makedirs(BUILD, exist_ok=True)
    meta = {}
    for key, p in OCEANS.items():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        bpy.ops.mesh.primitive_plane_add(size=2)
        ob = bpy.context.active_object
        m = ob.modifiers.new("Ocean", "OCEAN")
        m.geometry_mode = "GENERATE"
        m.resolution = int(round(RES ** 0.5))  # Blender Ocean-Gitter = resolution^2 (32 -> 1024x1024)
        m.viewport_resolution = 4
        m.spatial_size = p["spatial_size"]
        m.wind_velocity = p["wind_velocity"]
        m.wave_scale = p["wave_scale"]
        m.wave_scale_min = p["wave_scale_min"]
        m.choppiness = p["choppiness"]
        m.random_seed = p["seed"]
        m.spectrum = p["spectrum"]
        m.wave_alignment = p["wave_alignment"]
        m.wave_direction = p["wave_direction"]
        m.damping = p["damping"]
        m.use_normals = True
        m.use_foam = True
        m.foam_coverage = p["foam_coverage"]
        m.frame_start = 1
        m.frame_end = 1
        bdir = os.path.join(BUILD, "bake_" + key).replace("\\", "/") + "/"
        os.makedirs(bdir, exist_ok=True)
        for old in os.listdir(bdir):
            if old.lower().endswith(".exr"):
                os.remove(os.path.join(bdir, old))
        m.filepath = bdir
        sc.frame_set(1)
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.ocean_bake(modifier="Ocean")
        expected = {"disp_0001.exr", "foam_0001.exr", "normal_0001.exr"}
        prev_sizes = None
        for _ in range(300):
            time.sleep(0.1)
            cur = set(os.listdir(bdir))
            if expected.issubset(cur):
                sizes = tuple(os.path.getsize(os.path.join(bdir, fn)) for fn in sorted(expected))
                if min(sizes) > 0 and sizes == prev_sizes:
                    break
                prev_sizes = sizes
        files = sorted(os.listdir(bdir))
        print("[water]", key, files, flush=True)
        for f in files:
            if not f.lower().endswith(".exr"):
                continue
            img = bpy.data.images.load(bdir + f)
            w, h = img.size
            px = np.empty(w * h * img.channels, np.float32)
            img.pixels.foreach_get(px)
            px = px.reshape(h, w, img.channels)
            np.save(os.path.join(BUILD, "%s_%s.npy" % (key, f.split("_")[0])), px)
            print("[water]", key, f, w, h, img.channels, px.min(axis=(0, 1)), px.max(axis=(0, 1)), flush=True)
            bpy.data.images.remove(img)
        meta[key] = dict(p, grid=[w, h])
    json.dump(meta, open(os.path.join(BUILD, "meta.json"), "w"), indent=1)


def compose_main():
    import numpy as np
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SHOTS, exist_ok=True)
    meta = json.load(open(os.path.join(BUILD, "meta.json")))
    report = {}

    def resize_periodic(a, n):
        """periodisch auf n x n bringen (Fourier-Resampling, bleibt nahtlos)."""
        h, w = a.shape
        if h == n and w == n:
            return a
        F = np.fft.fftshift(np.fft.fft2(a))
        out = np.zeros((n, n), complex)
        ch, cw = min(h, n) // 2, min(w, n) // 2
        out[n // 2 - ch:n // 2 + ch, n // 2 - cw:n // 2 + cw] = F[h // 2 - ch:h // 2 + ch, w // 2 - cw:w // 2 + cw]
        return np.real(np.fft.ifft2(np.fft.ifftshift(out))) * (n * n) / (h * w)

    for key in ("a", "b"):
        m = meta[key]
        L = m["spatial_size"]
        disp = np.load(os.path.join(BUILD, "%s_disp.npy" % key))
        # Bake-Bilder: Zeile 0 = unten (Blender). Auf "oben zuerst" drehen.
        disp = disp[::-1]
        # Blender-Ozean: R = dx, G = dz? Vorzeichen/Belegung aus den Daten bestimmt:
        # Kanal mit groesster Varianz = Hoehe.
        var = [float(disp[..., c].var()) for c in range(3)]
        hc = int(np.argmax(var))
        hgt = resize_periodic(disp[..., hc].astype(np.float64), RES)
        # Steigungen periodisch (spektral -> exakt nahtlos und glatt)
        k = np.fft.fftfreq(RES, d=L / RES) * 2 * np.pi
        KX, KY = np.meshgrid(k, k, indexing="xy")
        H = np.fft.fft2(hgt)
        dhdx = np.real(np.fft.ifft2(1j * KX * H))
        dhdy_img = np.real(np.fft.ifft2(1j * KY * H))   # nach unten (Zeilenrichtung)
        dhdy = -dhdy_img                                  # +Y = Bild nach oben
        # Normale der Hoehenflaeche (Tangentenraum, z aus der Flaeche)
        strength = 1.0
        n = np.stack([-dhdx * strength, -dhdy * strength, np.ones_like(hgt)], -1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        enc = np.clip(np.round((n * 0.5 + 0.5) * 255), 0, 255).astype(np.uint8)
        path = os.path.join(OUT, "water_normal_%s.webp" % key)
        Image.fromarray(enc, "RGB").save(path, "WEBP", lossless=True, quality=100, method=6)
        slope = np.sqrt(dhdx ** 2 + dhdy ** 2)
        report[key] = dict(file=os.path.basename(path), bytes=os.path.getsize(path), tile_m=L,
                           height_channel=hc, slope_rms=float(np.sqrt((slope ** 2).mean())),
                           nz_min=float(n[..., 2].min()))
        print("[water] normal", key, report[key])

        if key == "b":
            foam_raw = None
            fp = os.path.join(BUILD, "%s_foam.npy" % key)
            if os.path.exists(fp):
                f = np.load(fp)[::-1]
                foam_raw = f[..., 0].astype(np.float64)
            # Schaum: Ozean-Schaum (Jacobian) plus Kammhoehe, periodisch weichgezeichnet
            crest = (hgt - hgt.mean()) / (hgt.std() + 1e-9)
            fm = np.clip(crest - 0.6, 0, None)
            if foam_raw is not None and foam_raw.max() > 1e-6:
                fr = resize_periodic(foam_raw, RES)
                fm = 0.6 * np.clip(fr / (np.percentile(fr, 99.5) + 1e-9), 0, 1) + 0.4 * np.clip(fm / 2.0, 0, 1)
            # periodische Weichzeichnung (Gauss im Frequenzraum)
            KK = KX ** 2 + KY ** 2
            blur = lambda a, s: np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-0.5 * KK * s * s)))
            fm = 0.65 * blur(fm, L / RES * 1.2) + 0.35 * blur(fm, L / RES * 6)
            # Struktur: feine Blasen aus periodischem Rauschen (Fourier-Rauschen, nahtlos)
            rng = np.random.default_rng(991)
            wn = rng.normal(size=(RES, RES))
            bub = blur(wn, L / RES * 1.5)
            bub = (bub - bub.mean()) / bub.std()
            fm = fm * (0.75 + 0.25 * np.tanh(bub))
            fm = np.clip(fm / (np.percentile(fm, 99.7) + 1e-9), 0, 1) ** 0.85
            foam8 = np.clip(np.round(fm * 255), 0, 255).astype(np.uint8)
            fpath = os.path.join(OUT, "water_foam.webp")
            Image.fromarray(foam8, "L").save(fpath, "WEBP", quality=92, method=6)
            report["foam"] = dict(file="water_foam.webp", bytes=os.path.getsize(fpath), tile_m=L,
                                  mean=float(fm.mean()), source="ocean_bake foam + Kammhoehe")

    # 3x3-Pruefbilder (aus den gespeicherten Dateien)
    for fn in ("water_normal_a.webp", "water_normal_b.webp", "water_foam.webp"):
        im = Image.open(os.path.join(OUT, fn))
        a = np.asarray(im)
        tile = np.tile(a, (3, 3, 1) if a.ndim == 3 else (3, 3))
        img = Image.fromarray(tile).resize((1536, 1536), Image.LANCZOS)
        img.save(os.path.join(SHOTS, "tile3x3_" + fn.replace(".webp", ".jpg")), quality=90)
        # schattierte Variante der Normalen (Licht schraeg) - Naehte sind hier am deutlichsten
        if "normal" in fn:
            nn = tile.astype(np.float32) / 255 * 2 - 1
            Ld = np.array([0.5, 0.45, 0.74]); Ld /= np.linalg.norm(Ld)
            sh = np.clip((nn * Ld).sum(-1), 0, 1) ** 4
            Image.fromarray((sh * 255).astype(np.uint8)).resize((1536, 1536), Image.LANCZOS).save(
                os.path.join(SHOTS, "tile3x3_shaded_" + fn.replace(".webp", ".jpg")), quality=90)
    json.dump(report, open(os.path.join(OUT, "water.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    try:
        import bpy  # noqa
        blender_main()
    except ImportError:
        compose_main()

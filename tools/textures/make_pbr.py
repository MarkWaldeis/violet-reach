"""Farbkarte (Draufsicht-Foto) -> kachelnder PBR-Satz fuer Violet Reach.

Schritte
  1. Laden, optional zuschneiden (--crop), quadratisch machen, auf Arbeitsgroesse.
  2. (a) Grossflaechige Helligkeits-/Farbunterschiede herausrechnen: Hochpass auf
     log-Luminanz mit grossem Gauss-Radius (--flatten-radius, Anteil der Kantenlaenge),
     Farbmittel bleibt erhalten; Chroma-Tieffrequenz anteilig (--flatten-chroma).
  3. (b) Kachelbarkeit pruefen (Randsprung vs. Innengradient). Ist die Quelle nicht
     kachelbar (oder --tile force): Versatz um halbe Kantenlaenge, danach die
     Mittelkreuz-Naht mit Patches aus dem Bild selbst ueberdecken, deren Raender per
     Minimalschnitt (dynamische Programmierung, Efros-Freeman) gelegt werden.
  4. Mittlere Farbe sanft an die Palettenfarbe angleichen (--match, 0..1).
  5. (c) Hoehe aus Luminanz mit Frequenzgewichtung (Differenz-von-Gauss-Pyramide,
     --freq), Normalen im Tangentenraum (OpenGL: +Y = Bild oben, --strength),
     Rauheit (--roughness Grundwert + --rough-var Variation), Verdeckung aus Hoehe.
  6. (d) Ausgabe:
       ground: <out>/<1k|2k>/<name>_albedo.webp  sRGB
               <out>/<1k|2k>/<name>_normal.webp  linear, RGB = XYZ*0.5+0.5
               <out>/<1k|2k>/<name>_orh.webp     linear, R=Verdeckung G=Rauheit B=Hoehe
       detail: <out>/<name>_normal.webp, <out>/<name>_rough.webp (Graustufe), 1024
     plus art/textures/meta/<kind>_<name>.json mit Messwerten (Kachelbarkeit, mittlere Farbe, Palette).

Nur numpy + Pillow (kein scipy): Unschaerfe per FFT (periodisch) bzw. FFT auf
gespiegelt aufgefuelltem Bild (nicht periodische Quellen).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PALETTE = json.loads((ROOT / "art" / "palette.json").read_text(encoding="utf-8"))["colors"]


# --------------------------------------------------------------- Farbe
def srgb_to_lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055).astype(np.float32)


def luminance(lin):
    return (lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722).astype(np.float32)


def lab(lin_rgb):
    """CIELAB (D65) aus linearem sRGB, fuer Delta-E-Angaben."""
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = m @ np.asarray(lin_rgb, float) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def hex_to_lin(h):
    h = h.lstrip("#")
    return srgb_to_lin(np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0)


def lin_to_hex(c):
    s = np.round(lin_to_srgb(np.asarray(c, np.float32)) * 255).astype(int)
    return "#%02X%02X%02X" % tuple(s)


def palette_target(spec):
    """'grass_green' | '#RRGGBB' | 'a:0.5+b:0.5' (lineare Mischung) | 'name*0.7' (Helligkeit)."""
    total = np.zeros(3, np.float32)
    for part in spec.split("+"):
        w = 1.0
        if ":" in part:
            part, w = part.split(":")
            w = float(w)
        mul = 1.0
        if "*" in part:
            part, mul = part.split("*")
            mul = float(mul)
        c = hex_to_lin(part) if part.startswith("#") else np.array(PALETTE[part]["linear_rgb"], np.float32)
        total += w * mul * c
    return total


# --------------------------------------------------------------- Filter
def _gauss_kernel_fft(shape, sigma):
    h, w = shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    return np.exp(-2 * (math.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2)).astype(np.float32)


def blur(img, sigma, wrap=True):
    """Gauss-Unschaerfe. wrap=True: periodisch; sonst gespiegelt aufgefuellt."""
    if sigma <= 0.3:
        return img.copy()
    if not wrap:
        pad = int(min(3 * sigma, img.shape[0] - 1, img.shape[1] - 1))
        pw = ((pad, pad), (pad, pad)) + (((0, 0),) if img.ndim == 3 else ())
        out = blur(np.pad(img, pw, mode="reflect"), sigma, True)
        return out[pad:pad + img.shape[0], pad:pad + img.shape[1]]
    k = _gauss_kernel_fft(img.shape[:2], sigma)
    if img.ndim == 3:
        return np.stack([blur(img[..., c], sigma, True) for c in range(img.shape[2])], -1)
    return np.fft.irfft2(np.fft.rfft2(img) * k, s=img.shape).astype(np.float32)


def resize(arr, n):
    """Float-Array (H,W[,C]) auf n x n (Lanczos je Kanal; Pillow-Modus 'F')."""
    if arr.shape[0] == n and arr.shape[1] == n:
        return arr.copy()
    if arr.ndim == 2:
        return np.asarray(Image.fromarray(arr.astype(np.float32), "F").resize((n, n), Image.LANCZOS), np.float32)
    return np.stack([resize(arr[..., c], n) for c in range(arr.shape[2])], -1)


def resize_wrap(arr, n):
    """Wie resize, aber periodisch (Rand mit Gegenseite aufgefuellt) - fuer Kacheln."""
    h = arr.shape[0]
    pad = max(4, h // 32)
    pw = ((pad, pad), (pad, pad)) + (((0, 0),) if arr.ndim == 3 else ())
    big = np.pad(arr, pw, mode="wrap")
    m = int(round(big.shape[0] * n / h))
    r = resize(big, m)
    p2 = int(round(pad * n / h))
    return r[p2:p2 + n, p2:p2 + n]


# --------------------------------------------------------------- Kachelbarkeit
def seam_ratio(img):
    """Randsprung / mittlerer Nachbargradient, je Achse. ~1 = kachelbar."""
    g = luminance(img) if img.ndim == 3 else img
    g = np.sqrt(np.maximum(g, 0))
    ix = np.abs(np.diff(g, axis=1)).mean()
    iy = np.abs(np.diff(g, axis=0)).mean()
    ex = np.abs(g[:, 0] - g[:, -1]).mean()
    ey = np.abs(g[0, :] - g[-1, :]).mean()
    return float(ex / max(ix, 1e-6)), float(ey / max(iy, 1e-6))


def _min_cut_vertical(err):
    """Pfad minimaler Kosten von oben nach unten durch err (H x w). Liefert Spalte je Zeile."""
    h, w = err.shape
    cost = err.copy()
    back = np.zeros((h, w), np.int8)
    for y in range(1, h):
        prev = cost[y - 1]
        left = np.r_[np.inf, prev[:-1]]
        right = np.r_[prev[1:], np.inf]
        stack = np.stack([left, prev, right])
        idx = np.argmin(stack, 0)
        cost[y] += stack[idx, np.arange(w)]
        back[y] = idx - 1
    path = np.zeros(h, int)
    path[-1] = int(np.argmin(cost[-1]))
    for y in range(h - 1, 0, -1):
        path[y - 1] = np.clip(path[y] + back[y, path[y]], 0, w - 1)
    return path


def _paste_vertical_band(dst, patch, x0, ov, feather):
    """patch (H x pw) in dst ab Spalte x0 (periodisch) setzen; linke/rechte Ueberlappung
    der Breite ov per Minimalschnitt. Gibt neues Bild zurueck."""
    H, W = dst.shape[:2]
    pw = patch.shape[1]
    cols = (np.arange(pw) + x0) % W
    region = dst[:, cols]
    err = ((region - patch) ** 2).sum(-1) if dst.ndim == 3 else (region - patch) ** 2
    mask = np.zeros((H, pw), np.float32)  # 1 = patch
    lp = _min_cut_vertical(err[:, :ov])
    rp = _min_cut_vertical(err[:, pw - ov:]) + pw - ov
    xx = np.arange(pw)[None, :]
    mask[(xx >= lp[:, None]) & (xx <= rp[:, None])] = 1.0
    if feather > 0:
        mask = blur(mask, feather, wrap=False)
        mask[:, :1] = 0
        mask[:, -1:] = 0
    m = mask[..., None] if dst.ndim == 3 else mask
    out = dst.copy()
    out[:, cols] = region * (1 - m) + patch * m
    return out


def make_tileable(img, band=0.10, overlap=0.06, feather=1.5, rng=None, directional=False):
    """Offset + Patch-Mischung mit Minimalschnitt-Raendern. img (H,W,3) float, quadratisch."""
    rng = rng or np.random.default_rng(1)
    H, W = img.shape[:2]
    hb = int(W * band / 2)
    ov = max(8, int(W * overlap))
    half = hb + ov
    B = np.roll(img, (H // 2, W // 2), (0, 1))
    # Senkrechte Naht bei x = W/2: Spaltenband aus dem Original, vertikal um H/2 versetzt
    # (seine eigene Randnaht faellt so auf die waagrechte Naht, die Schritt 2 ueberdeckt).
    dst0 = W // 2 - half
    best = None
    for xs in np.linspace(W * 0.3, W * 0.7, 13).astype(int):
        P = np.roll(img[:, xs - half:xs + half], H // 2, 0)
        cols = (np.arange(2 * half) + dst0) % W
        r = B[:, cols]
        e = (((r[:, :ov] - P[:, :ov]) ** 2).mean() + ((r[:, -ov:] - P[:, -ov:]) ** 2).mean())
        if best is None or e < best[0]:
            best = (e, xs, P)
    B1 = _paste_vertical_band(B, best[2], dst0, ov, feather)
    # Waagrechte Naht bei y = H/2: Zeilenband aus B1 (horizontal schon periodisch, daher
    # beliebig verschiebbar). Bei Schichtgestein (directional) nur kleiner Versatz.
    T = np.transpose(B1, (1, 0, 2))
    dst1 = H // 2 - half
    best2 = None
    ys_c = np.r_[np.linspace(H * 0.08, H * 0.30, 6), np.linspace(H * 0.70, H * 0.92, 6)].astype(int)
    dxs = [0] if directional else list(rng.integers(0, W, 6)) + [0]
    for ys in ys_c:
        for dx in dxs:
            rows = (np.arange(2 * half) + ys - half) % H
            P = np.roll(T[:, rows], int(dx), 0)
            cols = (np.arange(2 * half) + dst1) % H
            r = T[:, cols]
            e = (((r[:, :ov] - P[:, :ov]) ** 2).mean() + ((r[:, -ov:] - P[:, -ov:]) ** 2).mean())
            if best2 is None or e < best2[0]:
                best2 = (e, ys, dx, P)
    T2 = _paste_vertical_band(T, best2[3], dst1, ov, feather)
    out = np.transpose(T2, (1, 0, 2))
    info = {"band_px": 2 * hb, "overlap_px": ov, "src_col": int(best[1]),
            "src_row": int(best2[1]), "row_shift": int(best2[2])}
    return out.astype(np.float32), info


# --------------------------------------------------------------- Ableitungen
def flatten(lin, radius, amount, chroma_amount, wrap):
    sigma = radius * lin.shape[1]
    L = luminance(lin)
    logL = np.log(L + 1e-4)
    low = blur(logL, sigma, wrap)
    ratio = np.exp((low.mean() - low) * amount)[..., None]
    out = lin * ratio
    if chroma_amount > 0:
        Lo = luminance(out)[..., None] + 1e-4
        ch = out / Lo
        lowc = blur(ch, sigma, wrap)
        mean_c = ch.reshape(-1, 3).mean(0)
        fac = (mean_c / np.maximum(lowc, 1e-4)) ** chroma_amount
        out = ch * fac * Lo
    return np.clip(out, 0, 1).astype(np.float32)


def color_match(lin, target, amount, max_gain=3.0):
    mean = lin.reshape(-1, 3).mean(0)
    gain = np.clip((target / np.maximum(mean, 1e-5)) ** amount, 1 / max_gain, max_gain)
    return np.clip(lin * gain, 0, 1).astype(np.float32)


def height_from(lin, weights, invert=False, gamma=1.0, base_sigma=1.0):
    g = np.sqrt(np.clip(luminance(lin), 0, 1))  # wahrnehmungsnaeher als linear
    if invert:
        g = 1 - g
    h = np.zeros_like(g)
    prev = blur(g, 0.5 * base_sigma)
    for k, w in enumerate(weights):
        cur = blur(g, base_sigma * (2 ** k))
        band = prev - cur
        h += w * band / (band.std() + 1e-6)
        prev = cur
    lo, hi = np.percentile(h, [0.5, 99.5])
    h = np.clip((h - lo) / max(hi - lo, 1e-6), 0, 1)
    if gamma != 1.0:
        h = h ** gamma
    return h.astype(np.float32)


def normals_from(h, strength):
    """Tangentenraum-Normalen, OpenGL (+X rechts, +Y = Bild oben, +Z aus der Flaeche).
    strength bezieht sich auf 1024 Texel je Kachel und ist damit aufloesungsunabhaengig."""
    n = h.shape[0]
    s = strength * n / 1024.0
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    gy_down = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    nx = -s * gx
    ny = s * gy_down  # dH/dv = -dH/drow  ->  ny = -s * dH/dv
    nz = np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l, ny / l, nz / l], -1).astype(np.float32)


def ao_from(h, strength, scales):
    cav = np.zeros_like(h)
    for s in scales:
        cav += np.maximum(blur(h, s) - h, 0)
    p = np.percentile(cav, 99.0) + 1e-6
    return np.clip(1 - strength * np.clip(cav / p, 0, 1), 0, 1).astype(np.float32)


def roughness_from(lin, h, base, var, invert, height_mix, sigma):
    L = np.sqrt(np.clip(luminance(lin), 0, 1))
    hp = L - blur(L, sigma)
    v = np.clip(-hp / (2.5 * hp.std() + 1e-6), -1, 1)
    if invert:
        v = -v
    v = (1 - height_mix) * v + height_mix * np.clip((0.5 - h) * 2, -1, 1)
    return np.clip(base + var * v, 0.03, 1.0).astype(np.float32)


# --------------------------------------------------------------- IO
def save_webp(arr, path, quality, mode="RGB"):
    a = np.clip(np.round(arr * 255), 0, 255).astype(np.uint8)
    im = Image.fromarray(a, "L" if a.ndim == 2 else "RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=quality, method=6)
    return path.stat().st_size


def load(path, crop, work):
    im = Image.open(path).convert("RGB")
    if crop:
        x0, y0, x1, y1 = crop
        W, H = im.size
        im = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
    W, H = im.size
    return im, (W, H)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--name", required=True)
    ap.add_argument("--kind", choices=["ground", "detail"], default="ground")
    ap.add_argument("--out", default=None, help="Zielordner (Standard: web/explore/public/<kind>)")
    ap.add_argument("--crop", type=lambda s: [float(v) for v in s.split(",")], default=None,
                    help="x0,y0,x1,y1 als Anteile 0..1")
    ap.add_argument("--repeat-x", type=int, default=1, help="Quelle n-mal nebeneinander (Seitenverhaeltnis 2:1 -> 2)")
    ap.add_argument("--rotate", type=float, default=0.0,
                    help="Grad gegen den Uhrzeigersinn; nicht-rechte Winkel schneiden das Innenquadrat aus (danach --tile force)")
    ap.add_argument("--work", type=int, default=2048)
    ap.add_argument("--flatten-radius", type=float, default=0.10)
    ap.add_argument("--flatten", type=float, default=1.0)
    ap.add_argument("--flatten-chroma", type=float, default=0.6)
    ap.add_argument("--tile", choices=["auto", "force", "none"], default="auto")
    ap.add_argument("--tile-threshold", type=float, default=1.35)
    ap.add_argument("--tile-band", type=float, default=0.10)
    ap.add_argument("--directional", action="store_true", help="Schichtung erhalten (kein Querversatz)")
    ap.add_argument("--palette", default=None, help="Palettenname/Mischung fuer Farbangleich")
    ap.add_argument("--match", type=float, default=0.5, help="0 = kein Angleich, 1 = Mittel exakt")
    ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--freq", default="0.15,0.3,0.55,0.8,1,1,0.85,0.6",
                    help="Gewichte der DoG-Baender fein->grob (Sigma 1,2,4,... px bei 2048)")
    ap.add_argument("--height-invert", action="store_true")
    ap.add_argument("--height-gamma", type=float, default=1.0)
    ap.add_argument("--strength", type=float, default=4.0, help="Normalenstaerke (bei 1024 px)")
    ap.add_argument("--roughness", type=float, default=0.85)
    ap.add_argument("--rough-var", type=float, default=0.10)
    ap.add_argument("--rough-invert", action="store_true")
    ap.add_argument("--rough-height", type=float, default=0.0, help="Anteil Hoehe an der Rauheitsvariation")
    ap.add_argument("--ao", type=float, default=0.55)
    ap.add_argument("--sizes", default=None, help="z. B. 1024,2048 (ground) bzw. 1024 (detail)")
    ap.add_argument("--q-albedo", type=int, default=85)
    ap.add_argument("--q-normal", type=int, default=92)
    ap.add_argument("--q-orh", type=int, default=90)
    ap.add_argument("--q2k-normal", type=int, default=88, help="Normalen-Qualitaet ab 2048 (Groessenbudget)")
    ap.add_argument("--q2k-orh", type=int, default=84)
    a = ap.parse_args(argv)

    out = Path(a.out) if a.out else ROOT / "web" / "explore" / "public" / a.kind
    sizes = [int(s) for s in (a.sizes or ("1024,2048" if a.kind == "ground" else "1024")).split(",")]
    im, src_size = load(a.src, a.crop, a.work)
    if a.rotate % 90:
        W0 = min(im.size)
        im = im.crop(((im.size[0] - W0) // 2, (im.size[1] - W0) // 2, (im.size[0] + W0) // 2, (im.size[1] + W0) // 2))
        im = im.rotate(a.rotate, resample=Image.BICUBIC, expand=False)
        t = math.radians(a.rotate)
        side = int(W0 / (abs(math.cos(t)) + abs(math.sin(t)))) - 4
        o = (W0 - side) // 2
        im = im.crop((o, o, o + side, o + side))
    elif a.rotate:
        im = im.rotate(a.rotate, expand=True)
    if a.repeat_x > 1:
        W, H = im.size
        big = Image.new("RGB", (W * a.repeat_x, H))
        for i in range(a.repeat_x):
            big.paste(im, (i * W, 0))
        im = big
    W, H = im.size
    if W != H:
        s = min(W, H)
        im = im.crop(((W - s) // 2, (H - s) // 2, (W - s) // 2 + s, (H - s) // 2 + s))
    srgb = np.asarray(im, np.float32) / 255.0
    lin = srgb_to_lin(srgb)
    lin = resize(lin, a.work) if lin.shape[0] != a.work else lin
    lin = np.clip(lin, 0, 1)
    rep = {"name": a.name, "kind": a.kind, "src": str(Path(a.src).as_posix()), "src_size": list(src_size)}
    rep["seam_before"] = [round(v, 3) for v in seam_ratio(lin)]
    tileable = max(rep["seam_before"]) < a.tile_threshold
    # (a) Grossflaechige Unterschiede (vor dem Kacheln gespiegelt, sonst periodisch)
    lin = flatten(lin, a.flatten_radius, a.flatten, a.flatten_chroma, wrap=tileable)
    # (b) Kacheln
    if a.tile == "force" or (a.tile == "auto" and not tileable):
        lin, rep["tiling"] = make_tileable(lin, band=a.tile_band, directional=a.directional)
        lin = flatten(lin, a.flatten_radius, a.flatten * 0.5, a.flatten_chroma * 0.5, wrap=True)
    else:
        rep["tiling"] = "source already tileable" if a.tile == "auto" else "skipped"
    rep["seam_after"] = [round(v, 3) for v in seam_ratio(lin)]
    if a.saturation != 1.0:
        L = luminance(lin)[..., None]
        lin = np.clip(L + (lin - L) * a.saturation, 0, 1)
    rep["mean_before_match"] = lin_to_hex(lin.reshape(-1, 3).mean(0))
    if a.palette:
        tgt = palette_target(a.palette)
        lin = color_match(lin, tgt, a.match)
        m = lin.reshape(-1, 3).mean(0)
        rep.update(palette=a.palette, palette_hex=lin_to_hex(tgt), match=a.match,
                   delta_e=round(float(np.linalg.norm(lab(m) - lab(tgt))), 2))
    rep["mean"] = lin_to_hex(lin.reshape(-1, 3).mean(0))
    # (c) Ableitungen auf Arbeitsgroesse
    weights = [float(w) for w in a.freq.split(",")]
    bs = a.work / 2048.0
    h = height_from(lin, weights, a.height_invert, a.height_gamma, base_sigma=bs)
    rough = roughness_from(lin, h, a.roughness, a.rough_var, a.rough_invert, a.rough_height, sigma=6 * bs)
    ao = ao_from(h, a.ao, [2 * bs, 6 * bs, 18 * bs])
    rep["roughness_mean"] = round(float(rough.mean()), 3)
    rep["files"] = {}
    # (d) Ausgabe
    for n in sizes:
        hn = resize_wrap(h, n)
        nrm = normals_from(hn, a.strength) * 0.5 + 0.5
        rn = np.clip(resize_wrap(rough, n), 0, 1)
        if a.kind == "ground":
            d = out / ("%dk" % (n // 1024))
            alb = lin_to_srgb(np.clip(resize_wrap(lin, n), 0, 1))
            orh = np.stack([np.clip(resize_wrap(ao, n), 0, 1), rn, np.clip(hn, 0, 1)], -1)
            big = n >= 2048
            for suf, arr, q in (("albedo", alb, a.q_albedo), ("normal", nrm, a.q2k_normal if big else a.q_normal),
                                ("orh", orh, a.q2k_orh if big else a.q_orh)):
                p = d / f"{a.name}_{suf}.webp"
                rep["files"][p.relative_to(out).as_posix()] = save_webp(arr, p, q)
        else:
            for suf, arr, q in (("normal", nrm, a.q_normal), ("rough", rn, a.q_orh)):
                p = out / f"{a.name}_{suf}.webp"
                rep["files"][p.relative_to(out).as_posix()] = save_webp(arr, p, q)
    rep["args"] = {k: v for k, v in vars(a).items() if k not in ("src",)}
    meta = ROOT / "art" / "textures" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / f"{a.kind}_{a.name}.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("name", "seam_before", "seam_after", "mean_before_match", "mean")
                      if k in rep} | ({"palette": rep.get("palette_hex"), "dE": rep.get("delta_e")}), ensure_ascii=False))


if __name__ == "__main__":
    main()

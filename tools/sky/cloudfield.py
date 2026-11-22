"""Dichtefelder fuer Haufenwolken (reines numpy, laeuft in Blender und System-Python).

Aufbau einer Wolke:
  * Ebene 0: wenige grosse Kugeln bilden die Grundmasse (Kuppeln/Tuerme).
  * Ebene 1/2: kleinere Kugeln sitzen auf der Aussenhaut der vorigen Ebene,
    vor allem oben und seitlich -> blumenkohlartige Oberseite.
  * Vereinigung per polynomialem smooth-min, danach Billow-fBm als Verschiebung.
  * Flache Unterseite: Schnitt mit einer (leicht welligen) Halbebene z >= base.

Achsen: Feld[ix, iy, iz] = Blender x (rechts), y (Tiefe, weg von Kamera), z (oben).
Alle Laengen in Wolkeneinheiten (1 Einheit ~ 100 m, frei skalierbar).
"""
import math
import numpy as np

# --------------------------------------------------------------------------
# Rauschen
# --------------------------------------------------------------------------
_GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
                  [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                  [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
                  [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]], np.float32)


class Perlin3:
    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        p = rng.permutation(256).astype(np.int32)
        self.perm = np.concatenate([p, p])

    def __call__(self, x, y, z):
        perm = self.perm
        xi = np.floor(x).astype(np.int32)
        yi = np.floor(y).astype(np.int32)
        zi = np.floor(z).astype(np.int32)
        xf = (x - xi).astype(np.float32)
        yf = (y - yi).astype(np.float32)
        zf = (z - zi).astype(np.float32)
        xi &= 255
        yi &= 255
        zi &= 255

        def fade(t):
            return t * t * t * (t * (t * 6 - 15) + 10)
        u, v, w = fade(xf), fade(yf), fade(zf)

        def g(ix, iy, iz, dx, dy, dz):
            h = perm[perm[perm[ix] + iy] + iz] & 15
            gr = _GRAD[h]
            return gr[..., 0] * dx + gr[..., 1] * dy + gr[..., 2] * dz

        x1, y1, z1 = (xi + 1) & 255, (yi + 1) & 255, (zi + 1) & 255
        n000 = g(xi, yi, zi, xf, yf, zf)
        n100 = g(x1, yi, zi, xf - 1, yf, zf)
        n010 = g(xi, y1, zi, xf, yf - 1, zf)
        n110 = g(x1, y1, zi, xf - 1, yf - 1, zf)
        n001 = g(xi, yi, z1, xf, yf, zf - 1)
        n101 = g(x1, yi, z1, xf - 1, yf, zf - 1)
        n011 = g(xi, y1, z1, xf, yf - 1, zf - 1)
        n111 = g(x1, y1, z1, xf - 1, yf - 1, zf - 1)
        nx00 = n000 + u * (n100 - n000)
        nx10 = n010 + u * (n110 - n010)
        nx01 = n001 + u * (n101 - n001)
        nx11 = n011 + u * (n111 - n011)
        nxy0 = nx00 + v * (nx10 - nx00)
        nxy1 = nx01 + v * (nx11 - nx01)
        return nxy0 + w * (nxy1 - nxy0)


def fbm(noise, x, y, z, octaves=4, lac=2.03, gain=0.5, billow=False):
    amp, tot, norm = 1.0, 0.0, 0.0
    for o in range(octaves):
        n = noise(x, y, z)
        if billow:
            n = np.abs(n) * 2.0 - 0.5
        tot = tot + amp * n
        norm += amp
        amp *= gain
        x, y, z = x * lac + 17.1, y * lac - 3.7, z * lac + 9.3
    return tot / norm


# --------------------------------------------------------------------------
# Kugelhierarchie
# --------------------------------------------------------------------------
def _sphere_sdf_min(p, spheres):
    """min SDF ueber Kugelliste an Punkten p (N,3)."""
    c = spheres[:, :3][None]
    r = spheres[:, 3][None]
    d = np.linalg.norm(p[:, None, :] - c, axis=2) - r
    return d.min(axis=1)


def build_spheres(spec, rng):
    """spec: dict mit 'body' = Liste (cx, cy, cz, r) der Grundkugeln (Ebene 0)
    und Detailparametern. Gibt Liste von Arrays je Ebene zurueck."""
    levels = [np.array(spec["body"], np.float64)]
    per = spec.get("children", (16, 8, 4))
    scale = spec.get("child_scale", (0.42, 0.42, 0.45))
    up_bias = spec.get("up_bias", 0.25)
    base = spec.get("base", 0.0)
    for li, (n_per, s) in enumerate(zip(per, scale)):
        parents = levels[-1]
        allsph = np.concatenate(levels, 0)
        kids = []
        for (cx, cy, cz, r) in parents:
            k = 0
            tries = 0
            while k < n_per and tries < n_per * 12:
                tries += 1
                d = rng.normal(size=3)
                d[2] += up_bias * 2.0
                d /= np.linalg.norm(d)
                pt = np.array([cx, cy, cz]) + d * r
                if pt[2] < base + 0.05 * r:
                    continue
                # nur echte Aussenhaut: Punkt darf nicht tief in anderen Kugeln stecken
                if _sphere_sdf_min(pt[None], allsph)[0] < -0.08 * r:
                    continue
                rr = r * s * rng.uniform(0.7, 1.25)
                c = pt - d * rr * rng.uniform(0.25, 0.55)
                kids.append((c[0], c[1], c[2], rr))
                k += 1
        levels.append(np.array(kids, np.float64).reshape(-1, 4))
    return levels


def _smin_into(D, Dloc_slices, d_new, k):
    a = D[Dloc_slices]
    inv_k = np.float32(0.5 / k)
    kf = np.float32(k)
    h = np.clip(np.float32(0.5) + inv_k * (d_new - a), np.float32(0.0), np.float32(1.0))
    omh = np.float32(1.0) - h
    D[Dloc_slices] = (d_new * omh + a * h) - kf * h * omh


def density_field(spec, seed, voxel, pad=0.6):
    """Gibt (dichte float32 [nx,ny,nz], origin(3), voxel) zurueck."""
    rng = np.random.default_rng(seed)
    levels = build_spheres(spec, rng)
    allsph = np.concatenate(levels, 0)
    base = spec.get("base", 0.0)
    lo = (allsph[:, :3] - allsph[:, 3:4]).min(0) - pad
    hi = (allsph[:, :3] + allsph[:, 3:4]).max(0) + pad
    lo[2] = base - pad * 0.5
    n = np.ceil((hi - lo) / voxel).astype(int)
    D = np.full(n, 1e3, np.float32)
    xs = (lo[0] + (np.arange(n[0]) + 0.5) * voxel).astype(np.float32)
    ys = (lo[1] + (np.arange(n[1]) + 0.5) * voxel).astype(np.float32)
    zs = (lo[2] + (np.arange(n[2]) + 0.5) * voxel).astype(np.float32)
    ks = spec.get("smooth", (0.35, 0.18, 0.1, 0.08))
    # SDF muss bis hinter die Rausch-Verschiebung gueltig sein, sonst Kanten an Kugel-Boxen
    margin = 1.65 * spec.get("noise_amp", 0.06) * spec["height"] + 2.0 * spec.get("edge", 3.0) * voxel
    for li, sph in enumerate(levels):
        for (cx, cy, cz, r) in sph:
            k = ks[min(li, len(ks) - 1)] * r
            ext = r + k + margin
            i0 = max(0, int((cx - ext - lo[0]) / voxel)); i1 = min(n[0], int((cx + ext - lo[0]) / voxel) + 2)
            j0 = max(0, int((cy - ext - lo[1]) / voxel)); j1 = min(n[1], int((cy + ext - lo[1]) / voxel) + 2)
            l0 = max(0, int((cz - ext - lo[2]) / voxel)); l1 = min(n[2], int((cz + ext - lo[2]) / voxel) + 2)
            if i0 >= i1 or j0 >= j1 or l0 >= l1:
                continue
            X = xs[i0:i1, None, None] - np.float32(cx)
            Y = ys[None, j0:j1, None] - np.float32(cy)
            Z = zs[None, None, l0:l1] - np.float32(cz)
            d = np.sqrt(X * X + Y * Y + Z * Z) - np.float32(r)
            _smin_into(D, (slice(i0, i1), slice(j0, j1), slice(l0, l1)), d, k)

    H = spec["height"]
    noise = Perlin3(seed + 101)
    noise2 = Perlin3(seed + 202)
    fs = spec.get("noise_freq", 3.2) / H          # Grundfrequenz der Billows
    amp = spec.get("noise_amp", 0.06) * H
    wisp = spec.get("wisp", 0.35)
    dens = np.zeros(n, np.float32)
    X2, Y2 = np.meshgrid(xs, ys, indexing="ij")
    X2 = X2.astype(np.float32); Y2 = Y2.astype(np.float32)
    # leicht wellige, aber flache Unterseite
    basew = base + 0.025 * H * fbm(noise2, X2 * fs * 0.5, Y2 * fs * 0.5, np.zeros_like(X2), 3)
    edge = spec.get("edge", 3.0) * voxel
    sigma = spec.get("sigma", 12.0)
    for iz in range(n[2]):
        z = np.float32(zs[iz])
        sd0 = D[:, :, iz]
        if sd0.min() > amp * 1.6 + edge:
            continue
        m1 = sd0 <= amp * 1.6 + edge
        hz = np.clip((z - base) / H, 0, 1)
        xm1 = X2[m1]; ym1 = Y2[m1]; zm1 = np.full_like(xm1, z)
        b = fbm(noise, xm1 * fs, ym1 * fs, zm1 * fs, 5, billow=True)
        sd = sd0[m1] - amp * b * (0.55 + 0.45 * hz)
        # Unterseite: flacher Schnitt, unten fasriger (wisp)
        sb = basew[m1] - z
        sd = np.maximum(sd, sb)
        # Dichte: harte Hautkante oben, weichere unten
        e = edge * (1.0 + wisp * 3.0 * (1 - hz))
        core = np.clip(-sd / e, 0, 1)
        m2 = core > 0
        if not m2.any():
            continue
        xm2 = xm1[m2]; ym2 = ym1[m2]; zm2 = zm1[m2]; c2 = core[m2]
        # feine Erosion der Haut (fasrige Raender statt Seifenblasen)
        ero = fbm(noise2, xm2 * fs * 6.0, ym2 * fs * 6.0, zm2 * fs * 6.0, 3)
        c2 = np.clip(c2 - np.clip(0.55 - c2, 0, 1) * (0.45 + 0.9 * ero), 0, 1)
        # innere Dichtevariation + unten duenner
        inner = 0.75 + 0.25 * fbm(noise2, xm2 * fs * 2.3, ym2 * fs * 2.3, zm2 * fs * 2.3, 3)
        lowfade = np.clip((z - base) / (0.12 * H) + 0.35, 0.35, 1.0)
        out = np.zeros_like(core)
        out[m2] = (c2 ** 1.3) * inner * lowfade * sigma
        dens[:, :, iz][m1] = out
    return dens, lo, voxel


# --------------------------------------------------------------------------
# Wolkenkatalog: 8 Formen (feste Seeds)
# --------------------------------------------------------------------------
def _ring(rng, n, cx, cy, rx, ry, z, r0, r1):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)
        out.append((cx + rx * math.cos(a) * rng.uniform(0.6, 1.0),
                    cy + ry * math.sin(a) * rng.uniform(0.6, 1.0),
                    z, rng.uniform(r0, r1)))
    return out


def catalog():
    """Gibt Liste von (name, spec, seed) zurueck."""
    C = []
    r = np.random.default_rng(7)

    # 1 klassischer Haufen, mittel
    body = [(0, 0, 1.0, 1.6), (-1.5, 0.2, 0.7, 1.15), (1.5, -0.2, 0.75, 1.2),
            (0.3, 0.3, 2.0, 1.15), (-0.6, -0.6, 1.5, 1.0), (0.9, 0.7, 1.4, 1.0)]
    C.append(("cumulus_a", dict(body=body, height=3.4, base=0.0, children=(16, 8, 4)), 11))

    # 2 hoher Turm (congestus)
    body = [(0, 0, 1.0, 1.8), (0.2, 0.1, 2.5, 1.5), (-0.1, -0.2, 3.8, 1.2),
            (0.4, 0.2, 4.8, 0.95), (-1.7, 0.2, 0.8, 1.2), (1.8, -0.3, 0.8, 1.25),
            (-0.9, 0.5, 2.2, 1.0), (1.0, -0.4, 3.0, 0.9)]
    C.append(("congestus", dict(body=body, height=5.8, base=0.0, children=(16, 8, 4)), 22))

    # 3 kleiner Schoenwetter-Haufen (humilis)
    body = [(0, 0, 0.55, 1.0), (-0.9, 0.1, 0.45, 0.75), (0.95, 0.0, 0.5, 0.8), (0.2, 0.2, 0.95, 0.7)]
    C.append(("humilis", dict(body=body, height=1.7, base=0.0, children=(14, 8, 4), noise_amp=0.09), 33))

    # 4 breiter Haufen mit zwei Kuppeln
    body = [(-1.6, 0, 1.0, 1.5), (1.4, 0.2, 1.2, 1.7), (0, -0.3, 0.8, 1.3),
            (-2.9, 0.1, 0.6, 1.0), (2.9, -0.2, 0.7, 1.05), (1.2, 0.0, 2.4, 1.15),
            (-1.4, 0.3, 2.0, 1.0)]
    C.append(("cumulus_twin", dict(body=body, height=3.6, base=0.0, children=(16, 8, 4)), 44))

    # 5 schiefer, windverwehter Haufen
    body = [(0, 0, 0.9, 1.4), (0.9, 0.1, 1.9, 1.15), (1.7, -0.1, 2.6, 0.85),
            (-1.4, 0.2, 0.6, 1.0), (1.4, 0.3, 0.8, 1.1), (2.4, 0.0, 1.4, 0.8)]
    C.append(("cumulus_lean", dict(body=body, height=3.4, base=0.0, children=(16, 8, 4), up_bias=0.15), 55))

    # 6 mittlerer, rundlicher Haufen mit Seitenlappen
    body = [(0, 0, 1.2, 1.7), (-1.7, -0.3, 0.8, 1.1), (1.8, 0.4, 0.9, 1.0),
            (0.0, 0.8, 2.1, 1.1), (-0.8, -0.8, 2.2, 0.9), (2.6, 0.0, 0.5, 0.7),
            (-2.6, 0.2, 0.45, 0.65)]
    C.append(("cumulus_round", dict(body=body, height=3.6, base=0.0, children=(16, 8, 4)), 66))

    # 7 flache breite Bank (stratocumulus)
    body = []
    for i in range(13):
        x = -7.0 + i * 14.0 / 12 + r.uniform(-0.3, 0.3)
        body.append((x, r.uniform(-1.2, 1.2), 0.45 + r.uniform(0, 0.25), r.uniform(0.75, 1.15)))
        body.append((x + 0.5, r.uniform(-1.6, 1.6), 0.35, r.uniform(0.6, 0.9)))
    C.append(("bank_wide", dict(body=body, height=1.6, base=0.0, children=(10, 6, 3),
                                child_scale=(0.45, 0.4, 0.45), up_bias=0.45, noise_amp=0.11,
                                smooth=(0.5, 0.2, 0.1, 0.08), wisp=0.6), 77))

    # 8 flache Bank mit einzelnen Kuppeln
    body = []
    for i in range(11):
        x = -6.0 + i * 12.0 / 10 + r.uniform(-0.3, 0.3)
        body.append((x, r.uniform(-1.0, 1.0), 0.4, r.uniform(0.7, 1.0)))
    body += [(-2.5, 0.0, 1.1, 1.0), (1.8, 0.3, 1.3, 1.1), (4.3, -0.2, 0.9, 0.8)]
    C.append(("bank_domes", dict(body=body, height=2.3, base=0.0, children=(10, 6, 3),
                                 child_scale=(0.45, 0.4, 0.45), up_bias=0.4, noise_amp=0.1,
                                 smooth=(0.5, 0.2, 0.1, 0.08), wisp=0.5), 88))
    return C

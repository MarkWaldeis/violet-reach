"""Pruefbilder fuer die Bodentexturen und Detailtexturen.

python tools/textures/preview.py [namen...]   (Standard: alle aus textures.json)

Je Textur: <shots>/<name>_check.jpg mit
  [3x3-Kachel der Farbe (bzw. der Normalen bei Detailtexturen)] [3x3 Ebene, schraeg
  beleuchtet mit Normalen + Verdeckung + Glanz aus Rauheit] [Kugel mit Tangentenraum-Normalen]
und <shots>/contact_sheet.jpg (eine Zeile je Textur).
Pruefbilder liegen ausserhalb des Repos (devin-screenshots).
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from make_pbr import lin_to_srgb, srgb_to_lin  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHOTS = Path(os.environ.get("VR_TEX_SHOTS", Path.home() / "devin-screenshots" / "violet-reach" / "textures"))
PUB = ROOT / "web" / "explore" / "public"
LIGHT = np.array([-0.55, 0.55, 0.62])
LIGHT /= np.linalg.norm(LIGHT)
VIEW = np.array([0.0, 0.0, 1.0])


def rd(p, mode="RGB"):
    return np.asarray(Image.open(p).convert(mode), np.float32) / 255.0


def load_set(name, kind):
    if kind == "ground":
        d = PUB / "ground" / "2k"
        alb = srgb_to_lin(rd(d / f"{name}_albedo.webp"))
        nrm = rd(d / f"{name}_normal.webp") * 2 - 1
        orh = rd(d / f"{name}_orh.webp")
        return alb, nrm, orh[..., 0], orh[..., 1], orh[..., 2]
    d = PUB / "detail"
    nrm = rd(d / f"{name}_normal.webp") * 2 - 1
    rough = rd(d / f"{name}_rough.webp", "L")
    alb = np.full(nrm.shape, 0.45, np.float32)
    return alb, nrm, np.ones(rough.shape, np.float32), rough, None


def shade(alb, n, ao, rough):
    n = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    ndl = np.clip((n * LIGHT).sum(-1), 0, 1)
    h = LIGHT + VIEW
    h /= np.linalg.norm(h)
    ndh = np.clip((n * h).sum(-1), 0, 1)
    gloss = (1 - rough) ** 2
    spec = 0.6 * gloss * ndh ** (6 + 220 * gloss)
    amb = 0.22 * ao
    c = alb * (amb + 0.95 * ndl * (0.35 + 0.65 * ao))[..., None] + spec[..., None] * 0.9
    return np.clip(c, 0, 1)


def tile3(a, cell):
    small = np.asarray(Image.fromarray(to8(a)).resize((cell, cell), Image.LANCZOS))
    return np.tile(small, (3, 3, 1))


def to8(a):
    return np.clip(np.round(a * 255), 0, 255).astype(np.uint8)


def sphere(alb, n, ao, rough, size=640, rep=(2, 1)):
    ys, xs = np.mgrid[0:size, 0:size]
    x = (xs + 0.5) / size * 2 - 1
    y = 1 - (ys + 0.5) / size * 2
    r2 = x * x + y * y
    inside = r2 < 1
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    N = np.stack([x, y, z], -1)
    u = (np.arctan2(x, z) / (2 * np.pi) + 0.5) * rep[0] * 2  # Vorderseite ~ halber Umfang
    v = (np.arcsin(np.clip(y, -1, 1)) / np.pi + 0.5) * rep[1] * 2
    H, W = n.shape[:2]
    col = (np.mod(u, 1) * W).astype(int) % W
    row = ((1 - np.mod(v, 1)) * H).astype(int) % H
    T = np.stack([z, np.zeros_like(z), -x], -1)
    T /= np.maximum(np.linalg.norm(T, axis=-1, keepdims=True), 1e-6)
    B = np.cross(N, T)
    tn = n[row, col]
    P = T * tn[..., :1] + B * tn[..., 1:2] + N * tn[..., 2:3]
    c = shade(alb[row, col], P, ao[row, col], rough[row, col])
    bg = np.full(c.shape, 0.18, np.float32)
    return np.where(inside[..., None], c, bg)


def panel(name, kind):
    alb, n, ao, rough, h = load_set(name, kind)
    cell = 400
    left = tile3(lin_to_srgb(alb), cell) if kind == "ground" else tile3(n * 0.5 + 0.5, cell)
    lit = lin_to_srgb(shade(alb, n, ao, rough))
    mid = tile3(lit, cell)
    sph = to8(lin_to_srgb(sphere(alb, n, ao, rough)))
    S = 3 * cell
    crop = to8(lit[:S // 2, :S // 2])  # 1:1-Ausschnitt der 2k-Karte
    img = Image.new("RGB", (S * 2 + 660 + S // 2 + 10, S + 40), (24, 24, 24))
    img.paste(Image.fromarray(crop), (2 * S + 670, 40))
    img.paste(Image.fromarray(left), (0, 40))
    img.paste(Image.fromarray(mid), (S + 10, 40))
    img.paste(Image.fromarray(sph), (2 * S + 20, 40 + (S - 640) // 2))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        f = None
    lab = "Farbe 3x3" if kind == "ground" else "Normalen 3x3"
    d.text((8, 8), f"{name} ({kind})  |  {lab}  |  Ebene 3x3, Licht oben links  |  Kugel  |  1:1-Ausschnitt", fill=(230, 230, 230), font=f)
    SHOTS.mkdir(parents=True, exist_ok=True)
    p = SHOTS / f"{name}_check.jpg"
    img.save(p, quality=90)
    thumb = [Image.fromarray(left).resize((300, 300)), Image.fromarray(mid).resize((300, 300)),
             Image.fromarray(sph).resize((300, 300)), Image.fromarray(crop).resize((300, 300))]
    return p, thumb


def contact(rows):
    colw = 200 + 4 * 310
    nr = (len(rows) + 1) // 2
    sheet = Image.new("RGB", (2 * colw + 20, nr * 310 + 50), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        f = None
    d.text((10, 10), "Violet Reach Texturen: Farbe/Normalen 3x3 | Ebene 3x3 beleuchtet | Kugel | 1:1-Ausschnitt (2k)",
           fill=(230, 230, 230), font=f)
    for i, (name, kind, th) in enumerate(rows):
        x0 = (i // nr) * (colw + 20)
        y = 50 + (i % nr) * 310
        d.text((x0 + 10, y + 130), f"{name}\n({kind})", fill=(230, 230, 230), font=f)
        for k, t in enumerate(th):
            sheet.paste(t, (x0 + 200 + k * 310, y))
    p = SHOTS / "contact_sheet.jpg"
    sheet.save(p, quality=88)
    return p


if __name__ == "__main__":
    cfg = json.loads((Path(__file__).parent / "textures.json").read_text(encoding="utf-8"))
    want = set(sys.argv[1:])
    rows = []
    for t in cfg["textures"]:
        if want and t["name"] not in want:
            continue
        p, th = panel(t["name"], t["kind"])
        rows.append((t["name"], t["kind"], th))
        print(p)
    if not want:
        print(contact(rows))

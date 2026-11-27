"""Local fallback concept image for ruin_blocks_a.

This is not a Grok result. It exists because the Grok CLI was unavailable with HTTP 402.
Run with system Python; writes reference_concept_fallback.png next to this file.
"""
from PIL import Image, ImageDraw, ImageFont
import math
import os
import random

ROOT = r"C:\Users\Mark Waldeis\Desktop\Violet Reach"
OUT = os.path.join(ROOT, r"assets\monuments\ruin_blocks_a\reference_concept_fallback.png")
W = H = 1024
img = Image.new("RGB", (W, H), (215, 218, 211))
d = ImageDraw.Draw(img, "RGBA")
rng = random.Random(73129)

for y in range(H):
    f = y / H
    col = (int(226 - 22 * f), int(228 - 21 * f), int(222 - 18 * f))
    d.line([(0, y), (W, y)], fill=col)

ivory = (232, 218, 190)
weathered = (220, 205, 177)
shadow = (170, 169, 164)
deep = (112, 112, 108)
moss = (61, 76, 43)
soil = (102, 85, 72)

try:
    f_title = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 30)
    f_small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
    f_tiny = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
except OSError:
    f_title = f_small = f_tiny = ImageFont.load_default()

d.text((42, 30), "ruin_blocks_a — Konzept/Fallback-Moodboard", font=f_title, fill=(54, 54, 48))
d.text((42, 67), "modulare elfenbeinweiße Ruinenblöcke · ca. 7,2 m breit · geerdet, massiv, matt", font=f_small, fill=(86, 86, 78))

cx, cy = 512, 488
scale = 58
ca = math.cos(math.radians(30))
sa = math.sin(math.radians(30))


def proj(p):
    x, y, z = p
    return (cx + (x - y) * ca * scale, cy + (x + y) * sa * scale - z * scale)


pts = []
for i in range(80):
    a = math.tau * i / 80
    rx = 4.15 * (1 + 0.06 * math.sin(5 * a))
    ry = 2.75 * (1 + 0.08 * math.cos(3 * a))
    pts.append(proj((rx * math.cos(a), ry * math.sin(a), 0)))
d.polygon(pts, fill=(157, 154, 133, 115))

bed = []
for i in range(72):
    a = math.tau * i / 72
    rx = 3.55 * (1 + 0.11 * math.sin(4 * a + 1))
    ry = 2.28 * (1 + 0.09 * math.cos(5 * a))
    bed.append(proj((rx * math.cos(a), ry * math.sin(a), 0.015)))
d.polygon(bed, fill=(126, 108, 87, 145))

for _ in range(650):
    a = rng.uniform(0, math.tau)
    r = math.sqrt(rng.random())
    x = 3.35 * r * math.cos(a)
    y = 2.05 * r * math.sin(a)
    px, py = proj((x, y, 0.02))
    c = rng.choice([(103, 88, 72, 45), (142, 126, 101, 45), (61, 76, 43, 35), (220, 205, 177, 35)])
    d.ellipse((px - 1.2, py - 1.2, px + 1.2, py + 1.2), fill=c)


def block(x, y, z0, dx, dy, h, yawdeg, tone=0.0, chips=(), cracks=(), lean=0):
    yaw = math.radians(yawdeg)
    local = [(-dx / 2, -dy / 2), (dx / 2, -dy / 2), (dx / 2, dy / 2), (-dx / 2, dy / 2)]
    c, s = math.cos(yaw), math.sin(yaw)

    def tr(p):
        xx, yy = p
        return (x + xx * c - yy * s, y + xx * s + yy * c)

    base = [tr(p) for p in local]
    lx = math.cos(yaw) * lean
    ly = math.sin(yaw) * lean
    topbase = [(xx + lx, yy + ly) for xx, yy in base]
    b = [proj((xx, yy, z0)) for xx, yy in base]
    t = [proj((xx, yy, z0 + h)) for xx, yy in topbase]

    def shade(rgb, k):
        return tuple(max(0, min(255, int(v * k))) for v in rgb)

    basecol = tuple(int(ivory[i] * (1 - tone) + weathered[i] * tone) for i in range(3))
    side1 = shade(basecol, 0.79)
    side2 = shade(basecol, 0.68)
    topc = shade(basecol, 1.04)
    d.polygon([b[0], b[1], t[1], t[0]], fill=side1, outline=deep)
    d.polygon([b[1], b[2], t[2], t[1]], fill=side2, outline=deep)
    poly = list(t)
    if 2 in chips:
        mx = (t[1][0] + t[2][0]) / 2
        my = (t[1][1] + t[2][1]) / 2
        poly = [t[0], t[1], (mx, my), t[3]]
    if 0 in chips:
        mx = (t[0][0] + t[1][0]) / 2
        my = (t[0][1] + t[1][1]) / 2
        poly = [(mx, my), t[1], t[2], t[3]]
    d.polygon(poly, fill=topc, outline=deep)

    for _ in range(int(dx * dy * 30)):
        u = rng.random()
        v = rng.random()
        px = t[0][0] * (1 - u) * (1 - v) + t[1][0] * u * (1 - v) + t[2][0] * u * v + t[3][0] * (1 - u) * v
        py = t[0][1] * (1 - u) * (1 - v) + t[1][1] * u * (1 - v) + t[2][1] * u * v + t[3][1] * (1 - u) * v
        col = (120 + rng.randint(-15, 15), 114 + rng.randint(-12, 12), 99 + rng.randint(-10, 10), rng.randint(18, 36))
        d.ellipse((px - 0.9, py - 0.9, px + 0.9, py + 0.9), fill=col)

    for face, pts2 in cracks:
        if face == "front":
            polyg = [b[0], b[1], t[1], t[0]]
        elif face == "side":
            polyg = [b[1], b[2], t[2], t[1]]
        else:
            polyg = t
        pp = []
        for u, v in pts2:
            p0, p1, p2, p3 = polyg
            px = p0[0] * (1 - u) * (1 - v) + p1[0] * u * (1 - v) + p2[0] * u * v + p3[0] * (1 - u) * v
            py = p0[1] * (1 - u) * (1 - v) + p1[1] * u * (1 - v) + p2[1] * u * v + p3[1] * (1 - u) * v
            pp.append((px, py))
        d.line(pp, fill=(82, 81, 75, 175), width=2)
        d.line(pp, fill=(232, 218, 190, 90), width=1)

    if h < 2.2:
        for q in (b[0], b[1], b[2]):
            if rng.random() < 0.8:
                px, py = q
                d.ellipse((px - 7, py - 3, px + 7, py + 5), fill=(*moss, 85))
    return b, t


# Rear mass first, foreground last: the ordering approximates painterly depth.
block(0.25, 1.25, -0.08, 1.45, 1.05, 2.85, 7, 0.12, chips={2}, cracks=[
    ("front", [(0.42, 0.04), (0.47, 0.30), (0.39, 0.54), (0.45, 0.82)]),
    ("top", [(0.25, 0.28), (0.52, 0.43), (0.72, 0.62)]),
], lean=0.05)
block(-2.25, 0.55, -0.10, 2.10, 0.92, 2.45, 15, 0.05, chips={0}, cracks=[
    ("front", [(0.20, 0.06), (0.28, 0.35), (0.23, 0.68), (0.33, 0.92)]),
    ("side", [(0.56, 0.12), (0.44, 0.48), (0.54, 0.82)]),
], lean=-0.04)
block(1.75, 0.55, -0.11, 2.45, 1.55, 1.50, -17, 0.18, chips={2}, cracks=[
    ("front", [(0.12, 0.22), (0.34, 0.34), (0.58, 0.41), (0.79, 0.53)]),
    ("top", [(0.15, 0.70), (0.38, 0.49), (0.68, 0.58)]),
], lean=0.02)
block(-0.35, -0.05, -0.12, 3.75, 1.28, 0.92, -8, 0.10, chips={2}, cracks=[
    ("front", [(0.12, 0.48), (0.34, 0.38), (0.52, 0.45), (0.77, 0.33)]),
    ("top", [(0.20, 0.22), (0.42, 0.37), (0.60, 0.32), (0.84, 0.46)]),
])
block(0.35, -0.38, 0.42, 3.25, 0.72, 0.68, -28, 0.02, chips={0}, cracks=[
    ("front", [(0.16, 0.15), (0.34, 0.36), (0.46, 0.63), (0.60, 0.91)]),
    ("top", [(0.28, 0.28), (0.49, 0.42), (0.70, 0.37)]),
], lean=0.12)
block(-2.30, -1.20, -0.09, 1.55, 1.05, 0.82, 23, 0.20, chips={2}, cracks=[
    ("top", [(0.28, 0.22), (0.48, 0.41), (0.66, 0.58)]),
])
block(-0.35, -1.58, -0.08, 1.10, 0.90, 0.66, -5, 0.08, chips={0}, cracks=[
    ("front", [(0.35, 0.05), (0.42, 0.40), (0.36, 0.78)]),
])
block(1.85, -1.18, -0.07, 1.65, 1.00, 0.58, -20, 0.16, chips={2}, cracks=[
    ("top", [(0.20, 0.20), (0.42, 0.40), (0.62, 0.36), (0.78, 0.54)]),
])
block(3.05, -0.05, -0.07, 0.95, 0.82, 1.02, 10, 0.07, chips={0}, cracks=[
    ("side", [(0.46, 0.12), (0.40, 0.48), (0.52, 0.83)]),
], lean=-0.02)

for _ in range(72):
    a = rng.uniform(0, math.tau)
    r = math.sqrt(rng.random())
    x = 3.25 * r * math.cos(a)
    y = 2.0 * r * math.sin(a)
    px, py = proj((x, y, 0.03))
    if rng.random() < 0.52:
        col = (*moss, rng.randint(55, 100))
        rx = rng.uniform(3, 9)
        ry = rng.uniform(1.5, 4)
    else:
        col = (214, 201, 174, rng.randint(70, 110))
        rx = rng.uniform(2, 5)
        ry = rng.uniform(1, 3)
    d.ellipse((px - rx, py - ry, px + rx, py + ry), fill=col)

# Scale bar and palette swatches.
d.line((92, 795, 92 + 7.2 * 58, 795), fill=(56, 56, 52), width=3)
for xx in (92, 92 + 7.2 * 58):
    d.line((xx, 787, xx, 803), fill=(56, 56, 52), width=3)
d.text((230, 805), "Gruppenbreite ≈ 7,2 m · Einzelteile 0,8–4,0 m", font=f_small, fill=(60, 60, 55))
swatches = [("monument_white", ivory), ("stone_weathered", weathered), ("monument_shadow", shadow), ("moss", moss), ("soil", soil)]
x0 = 650
for i, (name, col) in enumerate(swatches):
    x = x0 + i * 68
    d.rounded_rectangle((x, 775, x + 56, 826), radius=5, fill=col, outline=(70, 70, 66))
    d.text((x, 831), name.replace("_", " "), font=f_tiny, fill=(64, 64, 58))

refs = []
for nm in ["ref_06_weathered_wall.jpg", "ref_03_canyon_cliffs.jpg", "ref_04_white_ribbed_arches.jpg"]:
    p = os.path.join(ROOT, "art", "reference", nm)
    if os.path.exists(p):
        im = Image.open(p).convert("RGB")
        im = im.crop((80, 70, 1050, 620)).resize((292, 162))
        refs.append(im)
if refs:
    y = 875
    for i, im in enumerate(refs):
        x = 42 + i * 308
        img.paste(im, (x, y))
        d.rectangle((x, y, x + 292, y + 162), outline=(70, 70, 66), width=2)
    d.text((42, 852), "Stilreferenzen aus art/reference: weiße Monumente, Kreidebrüche, matte helle Massen", font=f_tiny, fill=(63, 63, 57))

d.text((650, 852), "Fallback-Konzept: Grok-CLI 402/429, daher redaktionell aus Projektstil + Layoutschema", font=f_tiny, fill=(112, 70, 54))
img.save(OUT, quality=94)
print(OUT)

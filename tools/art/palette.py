"""Kuratierte Bildregionen, Kanalmedian → sRGB und IEC-61966-2-1-Linearwerte.

Benötigt Pillow: python3 -m venv ~/art-env; ~/art-env/bin/pip install pillow
Aufruf: ~/art-env/bin/python tools/art/palette.py [--check]
Kein Weißabgleich: dies sind Bildfarben unter Referenzlicht, keine gemessenen Albedos.
"""
import argparse
import json
from pathlib import Path
from statistics import median
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = [
    ("monument_white", "Monument", "Heller Kalkstein", 7, (920, 115, 960, 165)),
    ("monument_shadow", "Monument", "Kühler Stein in Vertiefungen", 7, (740, 175, 770, 220)),
    ("stone_weathered", "Monument", "Verwitterte Kanten", 3, (390, 430, 425, 460)),
    ("canyon_chalk", "Fels", "Helle Bruchflächen", 3, (730, 470, 760, 510)),
    ("canyon_strata", "Fels", "Dunkle Schichten", 3, (860, 520, 880, 550)),
    ("sandstone", "Fels", "Warmer Naturbogen", 3, (360, 190, 390, 215)),
    ("moss", "Vegetation", "Moospolster", 9, (1020, 490, 1060, 520)),
    ("grass_green", "Vegetation", "Gras-Mittelton", 9, (900, 380, 960, 410)),
    ("grass_dry", "Vegetation", "Sonnige Halme", 13, (760, 350, 800, 390)),
    ("leaf_green", "Vegetation", "Laub-Mittelton", 14, (520, 135, 560, 160)),
    ("leaf_shadow", "Vegetation", "Laub-Schatten", 14, (620, 185, 650, 210)),
    ("bark", "Vegetation", "Baumrinde", 14, (526, 233, 536, 261)),
    ("soil", "Boden", "Offene Erde", 7, (400, 450, 450, 480)),
    ("path_sand", "Boden", "Trockener Ufersaum", 10, (700, 460, 740, 480)),
    ("shore_wet", "Boden", "Feuchter Stein", 10, (230, 270, 260, 285)),
    ("water_deep", "Wasser", "Tiefes Seewasser", 11, (450, 490, 510, 520)),
    ("water_shallow", "Wasser", "Flachwasser", 10, (660, 375, 690, 395)),
    ("sky_blue", "Himmel", "Himmelsblau", 4, (750, 10, 800, 40)),
    ("haze", "Himmel", "Ferne und Dunst", 11, (1000, 270, 1040, 290)),
    ("cloud_cream", "Himmel", "Warme Wolken", 4, (790, 140, 820, 155)),
    ("violet_body", "Kristall", "Violetter Körper", 7, (191, 275, 207, 287)),
    ("violet_shadow", "Kristall", "Tiefe Facetten", 7, (145, 267, 165, 280)),
    ("violet_glow", "Kristall", "Helle Energieadern", 7, (692, 237, 700, 243)),
    ("accent_ochre", "Akzent", "Ockerfarbene Steinfassungen, kein belegtes Metall", 7, (750, 353, 768, 366)),
]


def linear(v):
    v /= 255
    return round(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4, 7)


def generate():
    colors = {}
    for name, group, role, frame, box in SAMPLES:
        path = next((ROOT / "art/reference").glob(f"ref_{frame:02}_*.jpg"))
        pixels = list(Image.open(path).crop(box).getdata())
        rgb = [round(median(p[c] for p in pixels)) for c in range(3)]
        colors[name] = dict(group=group, role=role, srgb_hex="#" + "".join(f"{c:02X}" for c in rgb),
                            linear_rgb=[linear(c) for c in rgb], frame=path.name, region_xyxy=box)
    return {"method": "Kuratierte Regionen; Kanalmedian sRGB; IEC 61966-2-1", "colors": colors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = generate()
    target = ROOT / "art/palette.json"
    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if target.read_text() != serialized:
            raise SystemExit("Palette weicht von den Referenzmessungen ab")
        print(f"palette ok: {len(data['colors'])} gemessene Farben")
        return
    target.write_text(serialized)
    chart = Image.new("RGB", (1200, 100 + 6 * 130), "#141B20")
    draw = ImageDraw.Draw(chart)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
        title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    except OSError:
        font, title = ImageFont.load_default(size=18), ImageFont.load_default(size=30)
    draw.text((24, 22), "VIOLET REACH  /  Referenzpalette", font=title, fill="#F0EEE3")
    for i, (name, color) in enumerate(data["colors"].items()):
        x, y = 24 + (i % 4) * 296, 90 + (i // 4) * 130
        draw.rounded_rectangle((x, y, x + 272, y + 62), radius=5, fill=color["srgb_hex"])
        draw.text((x, y + 69), name, font=font, fill="#F0EEE3")
        draw.text((x, y + 92), color["srgb_hex"] + " · " + color["group"], font=font, fill="#A9B7BE")
    chart.save(ROOT / "art/palette.png")
    print(f"Palette: {len(data['colors'])} Farben")


if __name__ == "__main__":
    main()

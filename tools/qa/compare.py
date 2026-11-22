"""Side-by-side comparison images and image metrics for tools/qa/capture.mjs.

Usage: python tools/qa/compare.py <jobs.json>
jobs.json: {"metrics": "<out metrics.json>", "jobs": [{"id", "reference", "game", "compare", "label"}]}

Metrics (all on 8-bit sRGB values scaled to 0..1, no linearisation):
  brightness   mean Rec.709 luma  Y' = 0.2126 R + 0.7152 G + 0.0722 B
  contrast     5th..95th percentile spread of Y' (p95 - p5)
  saturation   mean HSV saturation
  green        pixels with hue 60..170 deg, S >= 0.25, V >= 0.12: circular mean hue (deg), mean S, area share
  sky          top third of the image, pixels with hue 180..260 deg and S >= 0.08 (blue sky) or
               S < 0.12 and V >= 0.75 (bright haze/cloud): circular mean hue of the blue part, mean Y', area share
Values are hints for the reviewers, not targets.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HALF_W, HALF_H, BAR = 960, 540, 28


def hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    safe = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g - b) / safe) % 6, np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4)) * 60
    h = np.where(d > 0, h, 0)
    return h, s, mx


def circular_mean(deg):
    if deg.size == 0:
        return None
    a = np.radians(deg)
    return round(float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())) % 360), 1)


def metrics(path):
    im = Image.open(path).convert("RGB")
    if im.width > 1920:
        im = im.resize((1920, round(im.height * 1920 / im.width)), Image.LANCZOS)
    rgb = np.asarray(im, dtype=np.float32) / 255
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    h, s, v = hsv(rgb)
    p5, p95 = np.percentile(luma, [5, 95])
    green = (h >= 60) & (h <= 170) & (s >= 0.25) & (v >= 0.12)
    top = slice(0, rgb.shape[0] // 3)
    ht, st, vt, lt = h[top], s[top], v[top], luma[top]
    blue = (ht >= 180) & (ht <= 260) & (st >= 0.08)
    sky = blue | ((st < 0.12) & (vt >= 0.75))
    r3 = lambda x: round(float(x), 4)
    return {
        "size": [im.width, im.height],
        "brightness": r3(luma.mean()),
        "contrast": r3(p95 - p5),
        "luma_p5": r3(p5), "luma_p95": r3(p95),
        "saturation": r3(s.mean()),
        "green": {"hue": circular_mean(h[green]), "saturation": r3(s[green].mean()) if green.any() else None, "share": r3(green.mean())},
        "sky": {"hue": circular_mean(ht[blue]), "brightness": r3(lt[sky].mean()) if sky.any() else None, "share": r3(sky.mean())},
    }


def font(size):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def fit(path):
    im = Image.open(path).convert("RGB")
    scale = min(HALF_W / im.width, HALF_H / im.height)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    tile = Image.new("RGB", (HALF_W, HALF_H), (18, 20, 26))
    tile.paste(im, ((HALF_W - im.width) // 2, (HALF_H - im.height) // 2))
    return tile


def compose(job):
    sheet = Image.new("RGB", (HALF_W * 2, HALF_H + BAR), (18, 20, 26))
    if job.get("reference"):
        sheet.paste(fit(job["reference"]), (0, BAR))
    sheet.paste(fit(job["game"]), (HALF_W, BAR))
    draw, f = ImageDraw.Draw(sheet), font(16)
    left = f"Referenz · {Path(job['reference']).name}" if job.get("reference") else "Referenz fehlt"
    draw.text((10, 5), left, fill=(235, 228, 245), font=f)
    draw.text((HALF_W + 10, 5), f"Spiel · {job['label']}", fill=(235, 228, 245), font=f)
    draw.line([(HALF_W, 0), (HALF_W, HALF_H + BAR)], fill=(60, 60, 70), width=2)
    sheet.save(job["compare"], quality=90)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = {"method": __doc__.split("Metrics", 1)[1].strip(), "bookmarks": {}}
    for job in spec["jobs"]:
        compose(job)
        entry = {"game": metrics(job["game"])}
        if job.get("reference"):
            entry["reference"] = metrics(job["reference"])
            entry["reference_file"] = job["reference"]
            delta = {k: round(entry["game"][k] - entry["reference"][k], 4) for k in ("brightness", "contrast", "saturation")}
            entry["delta_game_minus_reference"] = delta
        out["bookmarks"][job["id"]] = entry
        print(f"{job['id']}: compare -> {Path(job['compare']).name}")
    Path(spec["metrics"]).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

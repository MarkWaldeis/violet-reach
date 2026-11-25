"""Annotate the orange diagnostic scale figure in R5 review images.

Creates *_annotated.jpg copies only; the renderer outputs remain untouched.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def orange_mask(arr):
    r = arr[..., 0].astype(np.float32)
    g = arr[..., 1].astype(np.float32)
    b = arr[..., 2].astype(np.float32)
    return (r > 95) & (r > g * 1.25) & (g > 25) & (g < 155) & (b < 105)


def annotate_image(src, dst, tile_size=None):
    im = Image.open(src).convert("RGB")
    arr = np.asarray(im)
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()

    regions = []
    if tile_size:
        tw, th = tile_size
        # Sheet padding is 8 px and tiles are 960x720.
        for row in range(arr.shape[0] // (th + 8)):
            for col in range(arr.shape[1] // (tw + 8)):
                x0 = 8 + col * (tw + 8)
                y0 = 8 + row * (th + 8)
                if x0 + tw <= arr.shape[1] and y0 + th <= arr.shape[0]:
                    regions.append((x0, y0, x0 + tw, y0 + th, row * 4 + col))
    else:
        regions.append((0, 0, arr.shape[1], arr.shape[0], 0))

    labels = 0
    for x0, y0, x1, y1, index in regions:
        cropmask = orange_mask(arr[y0:y1, x0:x1])
        # The figure always stands on the ground in the lower half. This avoids warm stone pixels.
        cropmask[: (y1 - y0) // 2] = False
        ys, xs = np.where(cropmask)
        if len(xs) < 5:
            continue
        bx0, bx1 = x0 + int(xs.min()) - 8, x0 + int(xs.max()) + 8
        by0, by1 = y0 + int(ys.min()) - 10, y0 + int(ys.max()) + 10
        draw.rectangle((bx0, by0, bx1, by1), outline=(255, 96, 0), width=3)
        if labels == 0:
            text = "QA scale 1.8 m (not asset)"
            tx = min(max(8, bx0 - 8), im.width - 285)
            ty = max(8, by0 - 42)
            pad = 5
            bbox = draw.textbbox((tx, ty), text, font=font)
            draw.rectangle((bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
                           fill=(12, 12, 12), outline=(255, 96, 0), width=1)
            draw.text((tx, ty), text, fill=(255, 150, 35), font=font)
            labels += 1

    im.save(dst, quality=92)
    return labels


def main(render_dir):
    jobs = [
        ("hero_r5.jpg", "hero_r5_annotated.jpg", None),
        ("sheet_r5.jpg", "sheet_r5_annotated.jpg", (960, 720)),
    ]
    made = []
    for srcname, dstname, tile in jobs:
        src = os.path.join(render_dir, srcname)
        if os.path.exists(src):
            dst = os.path.join(render_dir, dstname)
            annotate_image(src, dst, tile)
            made.append(dst)
    print("ANNOTATED", made)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)) + "/render")

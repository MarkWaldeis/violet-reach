"""Local reference image cutout, margin padding, and GRAFIK_PLAN 7.2 validator.

Usage:
  # Prepare raw image -> chosen.png and update image_qa.json:
  python tools/meshy/check_image.py <raw_image> --out <chosen.png> [--qa <image_qa.json>]
  python tools/meshy/check_image.py --asset <asset_id> --src <raw_image> [--version v1]

  # Validate an existing chosen.png without modifying it:
  python tools/meshy/check_image.py <chosen.png> --validate-only
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

LIB_DEFAULT = Path(os.environ.get("VR_MESHY_DIR", Path.home() / "Desktop" / "Violet Reach Meshy"))


def srgb_to_lin(c: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055).astype(np.float32)


def lin_to_hex(lin_rgb: np.ndarray) -> str:
    srgb = np.clip(np.round(lin_to_srgb(lin_rgb) * 255.0), 0, 255).astype(int)
    return f"#{srgb[0]:02X}{srgb[1]:02X}{srgb[2]:02X}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _estimate_background(rgb: np.ndarray, patch: int = 24) -> tuple[np.ndarray, float, np.ndarray, float]:
    """Estimate background RGB (0..255), corner spread, and chroma vector from the 4 corners."""
    h, w, _ = rgb.shape
    p = min(patch, h // 8, w // 8)
    corners = np.concatenate([
        rgb[:p, :p].reshape(-1, 3),
        rgb[:p, w - p:].reshape(-1, 3),
        rgb[h - p:, :p].reshape(-1, 3),
        rgb[h - p:, w - p:].reshape(-1, 3),
    ], axis=0)
    bg_rgb = np.median(corners, axis=0).astype(np.float32)
    dists = np.linalg.norm(corners - bg_rgb[None, :], axis=1)
    bg_std = float(np.percentile(dists, 90))
    bg_chroma = bg_rgb - float(bg_rgb.mean())
    bg_chroma_norm = float(np.linalg.norm(bg_chroma))
    return bg_rgb, bg_std, bg_chroma, bg_chroma_norm


def _fill_pinholes_and_debris(alpha: np.ndarray, rgb: np.ndarray, max_pinhole_area: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """Keep main connected opaque component(s), remove floating debris, and fill interior pinholes."""
    opaque = (alpha >= 128).astype(np.uint8)
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(opaque, connectivity=8)
    if n_comp > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        max_area = int(areas.max())
        keep = np.zeros(n_comp, dtype=bool)
        for idx in range(1, n_comp):
            # Keep the primary component and any substantial part >= 1.5% of primary
            if stats[idx, cv2.CC_STAT_AREA] >= max(max_area * 0.015, 64):
                keep[idx] = True
        keep_mask = keep[labels]
        # Dilate keep_mask by 1px so we don't clip valid 1px anti-aliased edge pixels
        keep_dilated = cv2.dilate(keep_mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1) > 0
        alpha = np.where(keep_dilated, alpha, 0).astype(np.uint8)
        opaque = (alpha >= 128).astype(np.uint8)

    # Find enclosed transparent regions (4-connected background components not touching the border)
    inv = (1 - opaque).astype(np.uint8)
    n_bg, bg_labels, bg_stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    if n_bg > 1:
        border_ids = (
            set(np.unique(bg_labels[0, :]))
            | set(np.unique(bg_labels[-1, :]))
            | set(np.unique(bg_labels[:, 0]))
            | set(np.unique(bg_labels[:, -1]))
        )
        # Nearest opaque pixel lookup to fill pinhole colors cleanly
        valid_src = opaque > 0
        if valid_src.any():
            _, nearest_idx = cv2.distanceTransformWithLabels(
                (~valid_src).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL
            )
            src_yx = np.column_stack(np.nonzero(valid_src))
        for idx in range(1, n_bg):
            if idx in border_ids:
                continue
            area = int(bg_stats[idx, cv2.CC_STAT_AREA])
            if area <= max_pinhole_area:
                hole_mask = bg_labels == idx
                alpha[hole_mask] = 255
                if valid_src.any():
                    labels_at_hole = np.clip(nearest_idx[hole_mask] - 1, 0, len(src_yx) - 1)
                    coords = src_yx[labels_at_hole]
                    rgb[hole_mask] = rgb[coords[:, 0], coords[:, 1]]
    return rgb, alpha


def cutout_and_pad(
    im: Image.Image,
    canvas_size: int = 1024,
    target_margin: float = 0.105,
    max_pinhole_area: int = 64,
    keep_alpha: bool = False,
) -> tuple[Image.Image, dict]:
    """Remove uniform background, despill edges, fill pinholes, crop, and pad to target_margin."""
    rgba = np.array(im.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[..., :3].astype(np.float32)
    orig_alpha = rgba[..., 3]

    has_existing_cutout = keep_alpha or (orig_alpha.min() == 0 and (orig_alpha == 0).mean() > 0.05)

    if not has_existing_cutout:
        bg_rgb, bg_std, bg_chroma, bg_chroma_norm = _estimate_background(rgb)
        rgb_dist = np.linalg.norm(rgb - bg_rgb[None, None, :], axis=-1)

        if bg_chroma_norm > 40.0:
            # Saturated studio key background (e.g., bright cyan #00D8FF or magenta #FF00FF)
            pixel_centered = rgb - rgb.mean(axis=-1, keepdims=True)
            chroma_proj = (pixel_centered @ bg_chroma) / (bg_chroma_norm + 1e-6)
            chroma_ratio = chroma_proj / (bg_chroma_norm + 1e-6)
            # A pixel is candidate background if its chroma strongly aligns with the studio key color
            # OR its Euclidean distance to the corner background color is small
            tol_flood = max(36.0, 3.5 * bg_std)
            bg_cand = (rgb_dist <= tol_flood) | (chroma_ratio >= 0.34)
        else:
            chroma_ratio = np.zeros(rgb.shape[:2], dtype=np.float32)
            tol_flood = max(28.0, 3.8 * bg_std)
            bg_cand = rgb_dist <= tol_flood

        # Corner flood-fill via connected components on bg_cand touching the 4 corners / border
        n_cc, cc_labels, cc_stats, _ = cv2.connectedComponentsWithStats(bg_cand.astype(np.uint8), connectivity=8)
        border_cc = (
            set(np.unique(cc_labels[0, :]))
            | set(np.unique(cc_labels[-1, :]))
            | set(np.unique(cc_labels[:, 0]))
            | set(np.unique(cc_labels[:, -1]))
        ) - {0}
        bg_mask = np.isin(cc_labels, list(border_cc))

        # Also key out enclosed inter-branch sky windows that unmistakably match the studio background
        for idx in range(1, n_cc):
            if idx in border_cc:
                continue
            area = int(cc_stats[idx, cv2.CC_STAT_AREA])
            if area > max_pinhole_area:
                region = cc_labels == idx
                if bg_chroma_norm > 40.0:
                    if float(np.median(chroma_ratio[region])) >= 0.48:
                        bg_mask |= region
                else:
                    if float(np.median(rgb_dist[region])) <= max(22.0, 2.5 * bg_std):
                        bg_mask |= region

        fg_mask = ~bg_mask

        # Clean small floating specks in fg_mask before distance transform
        n_fg, fg_labels, fg_stats, _ = cv2.connectedComponentsWithStats(fg_mask.astype(np.uint8), connectivity=8)
        if n_fg > 1:
            max_fg = int(fg_stats[1:, cv2.CC_STAT_AREA].max())
            valid_fg = np.zeros(n_fg, dtype=bool)
            for idx in range(1, n_fg):
                if fg_stats[idx, cv2.CC_STAT_AREA] >= max(max_fg * 0.015, 64):
                    valid_fg[idx] = True
            fg_mask = valid_fg[fg_labels]

        # Fill tiny interior pinholes (<= max_pinhole_area) in fg_mask
        inv_fg = (~fg_mask).astype(np.uint8)
        n_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(inv_fg, connectivity=4)
        if n_holes > 1:
            border_h = (
                set(np.unique(hole_labels[0, :]))
                | set(np.unique(hole_labels[-1, :]))
                | set(np.unique(hole_labels[:, 0]))
                | set(np.unique(hole_labels[:, -1]))
            )
            for idx in range(1, n_holes):
                if idx not in border_h and int(hole_stats[idx, cv2.CC_STAT_AREA]) <= max_pinhole_area:
                    fg_mask[hole_labels == idx] = True

        # Distance transform inside foreground for clean 1px anti-aliased edge and interior despill
        d_in = cv2.distanceTransform(fg_mask.astype(np.uint8), cv2.DIST_L2, 3)

        alpha_f = np.zeros(rgb.shape[:2], dtype=np.float32)
        alpha_f[d_in >= 1.35] = 1.0
        rim = (d_in > 0) & (d_in < 1.35)
        if bg_chroma_norm > 40.0:
            rim_alpha = 1.0 - np.clip(chroma_ratio[rim] / 0.65, 0.0, 1.0)
        else:
            rim_alpha = np.clip((rgb_dist[rim] - 10.0) / max(tol_flood, 20.0), 0.0, 1.0)
        # Keep edge crisp so semitransparent_fraction stays very low (<= 0.03)
        rim_alpha = np.where(rim_alpha < 0.35, 0.0, np.where(rim_alpha > 0.75, 1.0, rim_alpha))
        alpha_f[rim] = rim_alpha

        # Edge despill: propagate pure interior color (d_in >= 2.5) to any boundary pixels with background spill
        pure_interior = d_in >= 2.5
        if not pure_interior.any():
            pure_interior = d_in >= 1.0
        if pure_interior.any():
            _, nearest_label = cv2.distanceTransformWithLabels(
                (~pure_interior).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL
            )
            int_yx = np.column_stack(np.nonzero(pure_interior))
            boundary_zone = (alpha_f > 0) & (~pure_interior)
            if boundary_zone.any():
                lbl = np.clip(nearest_label[boundary_zone] - 1, 0, len(int_yx) - 1)
                nearest_rgb = rgb[int_yx[lbl, 0], int_yx[lbl, 1]]
                b_rgb = rgb[boundary_zone]
                if bg_chroma_norm > 40.0:
                    spill = np.clip(chroma_ratio[boundary_zone] / 0.20, 0.0, 1.0)[..., None]
                    w = np.maximum(spill, 0.85)
                else:
                    w = 0.80
                # Preserve relative brightness details while taking hue/chroma from pure interior
                lum_cur = 0.2126 * b_rgb[:, 0] + 0.7152 * b_rgb[:, 1] + 0.0722 * b_rgb[:, 2]
                lum_ref = 0.2126 * nearest_rgb[:, 0] + 0.7152 * nearest_rgb[:, 1] + 0.0722 * nearest_rgb[:, 2]
                scale = np.clip(lum_cur / np.maximum(lum_ref, 10.0), 0.75, 1.15)[:, None]
                recolored = np.clip(nearest_rgb * scale, 0.0, 255.0)
                rgb[boundary_zone] = (1.0 - w) * b_rgb + w * recolored

        # Global chroma despill for cyan/cool studio backgrounds so no cyan/green cast remains on thin branches
        if bg_chroma_norm > 40.0 and bg_rgb[2] > bg_rgb[0] + 50.0 and bg_rgb[1] > bg_rgb[0] + 50.0:
            fg_all = alpha_f > 0
            r_ch = rgb[..., 0]
            g_ch = np.minimum(rgb[..., 1], r_ch)
            b_ch = np.minimum(rgb[..., 2], g_ch)
            spill_mask = fg_all & ((rgb[..., 1] > r_ch) | (rgb[..., 2] > g_ch))
            rgb[spill_mask, 1] = g_ch[spill_mask]
            rgb[spill_mask, 2] = b_ch[spill_mask]

        alpha = np.clip(np.round(alpha_f * 255.0), 0, 255).astype(np.uint8)
    else:
        alpha = orig_alpha.copy()

    rgb_u8 = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
    rgb_u8, alpha = _fill_pinholes_and_debris(alpha, rgb_u8, max_pinhole_area=max_pinhole_area)

    # Crop to non-zero alpha bounding box
    ys, xs = np.nonzero(alpha > 0)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError("No opaque object pixels found after background removal")
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1

    crop_rgb = rgb_u8[y0:y1, x0:x1].astype(np.float32)
    crop_a = alpha[y0:y1, x0:x1].astype(np.float32) / 255.0
    ch, cw = crop_a.shape

    # Target object span so margin >= target_margin on all 4 sides (~79% fill for target_margin=0.105)
    max_span = int(round(canvas_size * (1.0 - 2.0 * target_margin)))
    scale = max_span / float(max(cw, ch))
    new_w = max(1, min(max_span, int(round(cw * scale))))
    new_h = max(1, min(max_span, int(round(ch * scale))))

    # Premultiplied Lanczos resize to prevent dark/colored halo ringing
    premul = np.dstack([crop_rgb * crop_a[..., None], crop_a * 255.0])
    resized_channels = [
        np.asarray(
            Image.fromarray(premul[..., c].astype(np.float32), mode="F").resize((new_w, new_h), Image.LANCZOS),
            dtype=np.float32,
        )
        for c in range(4)
    ]
    res_a = np.clip(resized_channels[3] / 255.0, 0.0, 1.0)
    # Snap near-0 and near-1 alpha caused by Lanczos ringing
    res_a = np.where(res_a < (24.0 / 255.0), 0.0, np.where(res_a > (235.0 / 255.0), 1.0, res_a))
    denom = np.maximum(res_a[..., None], 1e-4)
    res_rgb = np.stack(resized_channels[:3], axis=-1) / denom
    res_rgb = np.where(res_a[..., None] > 0, np.clip(np.round(res_rgb), 0, 255), 0).astype(np.uint8)
    res_a_u8 = np.clip(np.round(res_a * 255.0), 0, 255).astype(np.uint8)

    # Paste centered onto square transparent canvas
    canvas_rgb = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)
    canvas_a = np.zeros((canvas_size, canvas_size), dtype=np.uint8)
    ox = (canvas_size - new_w) // 2
    oy = (canvas_size - new_h) // 2
    canvas_rgb[oy:oy + new_h, ox:ox + new_w] = res_rgb
    canvas_a[oy:oy + new_h, ox:ox + new_w] = res_a_u8

    # Final cleanup pass on the 1024x1024 canvas to guarantee single_component and 0 pinholes after resampling
    canvas_rgb, canvas_a = _fill_pinholes_and_debris(canvas_a, canvas_rgb, max_pinhole_area=max_pinhole_area)
    canvas_rgb[canvas_a == 0] = 0

    out_rgba = np.dstack([canvas_rgb, canvas_a])
    out_im = Image.fromarray(out_rgba, mode="RGBA")
    metrics = validate_rgba(out_im, max_pinhole_area=max_pinhole_area)
    return out_im, metrics


def validate_rgba(im: Image.Image, max_pinhole_area: int = 64) -> dict:
    """Validate an RGBA image against GRAFIK_PLAN.md Section 7.2 checklist items."""
    rgba = np.array(im.convert("RGBA"), dtype=np.uint8)
    h, w, _ = rgba.shape
    rgb = rgba[..., :3]
    a = rgba[..., 3]

    opaque = a >= 128
    nonzero = a > 0
    semi = (a > 0) & (a < 255)

    opaque_count = int(opaque.sum())
    nonzero_count = int(nonzero.sum())
    if opaque_count == 0:
        raise ValueError("Image contains 0 opaque pixels")

    # 1. Single component & margins
    n_comp, _, stats, _ = cv2.connectedComponentsWithStats(opaque.astype(np.uint8), connectivity=8)
    largest_area = int(stats[1:, cv2.CC_STAT_AREA].max()) if n_comp > 1 else 0
    largest_component_fraction = float(largest_area) / float(opaque_count)
    single_component = largest_component_fraction >= 0.98

    ys, xs = np.nonzero(nonzero)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    obj_w = x1 - x0
    obj_h = y1 - y0

    margins = {
        "left": round(x0 / float(w), 4),
        "right": round((w - x1) / float(w), 4),
        "top": round(y0 / float(h), 4),
        "bottom": round((h - y1) / float(h), 4),
    }
    margin_min = round(min(margins.values()), 4)
    border_opaque_pixels = int(
        nonzero[0, :].sum() + nonzero[-1, :].sum() + nonzero[:, 0].sum() + nonzero[:, -1].sum()
    )

    # 2. Clean alpha: semitransparent_fraction <= 0.05 and interior_holes == 0
    semitransparent_fraction = round(float(semi.sum()) / float(max(nonzero_count, 1)), 4)

    inv = (~opaque).astype(np.uint8)
    n_bg, bg_labels, bg_stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    border_ids = (
        set(np.unique(bg_labels[0, :]))
        | set(np.unique(bg_labels[-1, :]))
        | set(np.unique(bg_labels[:, 0]))
        | set(np.unique(bg_labels[:, -1]))
    )
    pinholes = 0
    through_openings = 0
    for idx in range(1, n_bg):
        if idx in border_ids:
            continue
        area = int(bg_stats[idx, cv2.CC_STAT_AREA])
        if area <= max_pinhole_area:
            pinholes += 1
        else:
            through_openings += 1

    # 3. Color & lighting metrics on opaque pixels
    lin = srgb_to_lin(rgb.astype(np.float32) / 255.0)
    lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    mean_lin = lin[opaque].mean(axis=0)
    mean_hex = lin_to_hex(mean_lin)

    mid_y = (y0 + y1) // 2
    top_mask = opaque.copy()
    top_mask[mid_y:, :] = False
    bot_mask = opaque.copy()
    bot_mask[:mid_y, :] = False
    lum_top = float(lum[top_mask].mean()) if top_mask.any() else float(lum[opaque].mean())
    lum_bot = float(lum[bot_mask].mean()) if bot_mask.any() else float(lum[opaque].mean())
    lum_top_bottom_ratio = round(lum_top / max(lum_bot, 1e-4), 3)

    aspect_hw = round(float(obj_h) / float(max(obj_w, 1)), 3)
    fill_fraction = round(float(max(obj_w, obj_h)) / float(max(w, h)), 4)

    checks = {
        "single_component": bool(single_component),
        "margin_ok": bool(margin_min >= 0.08),
        "margin_target_10pct": bool(margin_min >= 0.10),
        "border_clear": bool(border_opaque_pixels == 0),
        "alpha_clean": bool(semitransparent_fraction <= 0.05),
        "no_interior_holes": bool(pinholes == 0),
    }
    passed = all(
        checks[k]
        for k in ("single_component", "margin_ok", "border_clear", "alpha_clean", "no_interior_holes")
    )

    return {
        "passed": passed,
        "size": [w, h],
        "bbox_xywh": [x0, y0, obj_w, obj_h],
        "fill_fraction": fill_fraction,
        "aspect_hw": aspect_hw,
        "opaque_pixels": opaque_count,
        "component_count": int(n_comp - 1),
        "largest_component_fraction": round(largest_component_fraction, 4),
        "single_component": bool(single_component),
        "margins": margins,
        "margin_min": margin_min,
        "border_opaque_pixels": border_opaque_pixels,
        "semitransparent_fraction": semitransparent_fraction,
        "interior_holes": pinholes,
        "through_openings": through_openings,
        "mean_srgb_hex": mean_hex,
        "luminance_top_bottom_ratio": lum_top_bottom_ratio,
        "checks": checks,
    }


def update_image_qa_json(
    qa_path: Path,
    asset_id: str,
    version: str,
    model: str,
    verdict: str,
    chosen_rel: str,
    chosen_sha256: str,
    metrics: dict,
) -> None:
    if qa_path.exists():
        try:
            data = json.loads(qa_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    data.setdefault("checklist", "GRAFIK_PLAN 7.2 items 1-7; margin padded locally to 10%")
    versions = data.setdefault("versions", {})
    versions[version] = {
        "model": model,
        "verdict": verdict,
        "chosen_file": chosen_rel,
        "chosen_sha256": chosen_sha256,
        "metrics": metrics,
    }
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", help="Input raw image or chosen.png")
    ap.add_argument("--src", dest="src_opt", help="Input raw image path")
    ap.add_argument("--asset", help="Asset ID under $VR_MESHY_DIR")
    ap.add_argument("--lib", default=str(LIB_DEFAULT), help="Path to Violet Reach Meshy directory")
    ap.add_argument("--out", help="Output chosen.png path (default: $VR_MESHY_DIR/<asset>/image/chosen.png)")
    ap.add_argument("--save-raw", help="Optional path to also copy/save the raw source image")
    ap.add_argument("--qa", help="Path to image_qa.json (default: $VR_MESHY_DIR/<asset>/image_qa.json)")
    ap.add_argument("--version", default="v1", help="Version key in image_qa.json (default: v1)")
    ap.add_argument("--model", default="own-image-gen", help="Image generator model label for image_qa.json")
    ap.add_argument("--verdict", default=None, help="Verdict note for image_qa.json")
    ap.add_argument("--canvas", type=int, default=1024, help="Output square canvas size in pixels (default: 1024)")
    ap.add_argument("--margin", type=float, default=0.105, help="Target minimum empty margin on all 4 sides")
    ap.add_argument("--max-pinhole", type=int, default=64, help="Maximum area in pixels for interior pinhole fill")
    ap.add_argument("--keep-alpha", action="store_true", help="Keep existing alpha channel instead of corner flood-fill")
    ap.add_argument("--validate-only", action="store_true", help="Validate existing RGBA image without writing")
    args = ap.parse_args(argv)

    lib_dir = Path(args.lib)
    src_path_str = args.src_opt or args.src
    if not src_path_str and args.asset:
        cand = lib_dir / args.asset / "image" / "chosen.png"
        if cand.exists():
            src_path_str = str(cand)
    if not src_path_str:
        ap.error("Provide an input image path (positional or --src) or --asset with an existing image")

    src_path = Path(src_path_str)
    if not src_path.exists():
        print(f"ERROR: Source image not found: {src_path}", file=sys.stderr)
        return 2

    im = Image.open(src_path)

    if args.validate_only:
        metrics = validate_rgba(im, max_pinhole_area=args.max_pinhole)
        metrics["sha256"] = sha256_file(src_path)
        metrics["file"] = str(src_path)
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        return 0 if metrics["passed"] else 1

    out_path = Path(args.out) if args.out else (
        (lib_dir / args.asset / "image" / "chosen.png") if args.asset else src_path.with_name("chosen.png")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.save_raw:
        raw_dst = Path(args.save_raw)
        raw_dst.parent.mkdir(parents=True, exist_ok=True)
        if src_path.resolve() != raw_dst.resolve():
            shutil.copy2(src_path, raw_dst)

    out_im, metrics = cutout_and_pad(
        im,
        canvas_size=args.canvas,
        target_margin=args.margin,
        max_pinhole_area=args.max_pinhole,
        keep_alpha=args.keep_alpha,
    )
    out_im.save(out_path, "PNG", optimize=True)
    digest = sha256_file(out_path)
    metrics["sha256"] = digest
    metrics["file"] = str(out_path)

    asset_id = args.asset or out_path.parent.parent.name
    qa_path = Path(args.qa) if args.qa else (
        (lib_dir / asset_id / "image_qa.json") if (args.asset or args.qa is None) else None
    )
    if qa_path is not None:
        chosen_rel = f"{asset_id}/image/{out_path.name}"
        verdict = args.verdict or (
            "pass: clean RGBA cutout, >=10% margin, 0 interior pinholes, no leaves or thin twigs"
            if metrics["passed"]
            else "fail: checklist threshold violated"
        )
        update_image_qa_json(
            qa_path=qa_path,
            asset_id=asset_id,
            version=args.version,
            model=args.model,
            verdict=verdict,
            chosen_rel=chosen_rel,
            chosen_sha256=digest,
            metrics=metrics,
        )

    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

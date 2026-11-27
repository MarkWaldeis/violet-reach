#!/usr/bin/env python3
"""Regression checks for macro-map channel-packed WebP encoding."""
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_macromap as macro  # noqa: E402

FAILURES = []


def expect(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        FAILURES.append(name)


def main():
    rng = np.random.default_rng(73129)
    arr = rng.random((37, 41, 4), dtype=np.float32)
    arr[..., 3] = 0.0  # legitimate packed data in RGB with a zero fourth channel
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "packed.webp"
        macro.save_rgba_webp(arr, path, exact_data=True)
        roundtrip = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
        expected = np.clip(np.round(arr * 255.0), 0, 255).astype(np.uint8)
        expect("exact channel-packed RGBA survives zero alpha byte-identically", np.array_equal(roundtrip, expected))

    public = Path(__file__).resolve().parents[2] / "web" / "explore" / "public" / "ground"
    wa = public / "macro_weights_a.webp"
    wb = public / "macro_weights_b.webp"
    if wa.exists() and wb.exists():
        a = np.asarray(Image.open(wa).convert("RGBA"), dtype=np.uint16)
        b = np.asarray(Image.open(wb).convert("RGBA"), dtype=np.uint16)
        total = (a.sum(axis=2) + b.sum(axis=2)).astype(np.int16)
        expect("macro layer weights remain normalized after decoding", float(np.abs(total - 255).mean()) < 1.0)
    else:
        expect("macro weight fixtures exist", False)

    if FAILURES:
        raise SystemExit(f"{len(FAILURES)} macro-map checks failed: {FAILURES}")
    print("macro-map checks passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Stage 4a pass 2 visual crops: before/after at pass 2 change locations.

Uses XOR raster diff to find changed regions — does NOT modify pipeline.
Every crop asserts non-zero pixel diff before writing (hard requirement).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label

from src.colors import COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS
from src.geometry_fit import geometry_fit
from src.pipeline import vectorize_to_svg

OUT_DIR = Path("output/stage4a_pass2_visual")
ZOOM = 4
CROP_SIZE = 160  # source-px before zoom
MAX_CROPS_PER_SAMPLE = 3
MIN_DIFF_PX = 4  # minimum diff pixels to consider a region


def render_svg_to_png(svg_text: str, size: tuple[int, int]) -> Image.Image:
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="w") as sf:
        sf.write(svg_text)
        svg_path = sf.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as pf:
        png_path = pf.name
    try:
        subprocess.run(
            ["rsvg-convert", svg_path, "-o", png_path, "-w", str(size[0])],
            check=True, capture_output=True, timeout=60,
        )
        return Image.open(png_path).convert("RGB")
    finally:
        Path(svg_path).unlink(missing_ok=True)
        Path(png_path).unlink(missing_ok=True)


def make_crop_strip(
    src_img: Image.Image,
    img_v4: Image.Image,
    img_fit: Image.Image,
    box: tuple[int, int, int, int],
    label: str,
) -> Image.Image:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    out_w, out_h = w * ZOOM, h * ZOOM
    panels = [("SOURCE", src_img), ("v4", img_v4), ("v4+fit", img_fit)]
    total_h = out_h * len(panels)
    strip = Image.new("RGB", (out_w, total_h), (30, 30, 30))
    for pi, (lbl, img) in enumerate(panels):
        crop = img.crop((x1, y1, x2, y2))
        crop = crop.resize((out_w, out_h), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(crop)
        draw.rectangle([1, 1, out_w - 2, out_h - 2], outline="red", width=2)
        draw.text((4, 4), f"{lbl}  {label}", fill="red")
        strip.paste(crop, (0, pi * out_h))
    return strip


def find_diff_bboxes(
    arr_v4: np.ndarray, arr_fit: np.ndarray, min_area: int = MIN_DIFF_PX
) -> list[tuple[int, int, int, int]]:
    """Find bounding boxes of connected components in XOR diff."""
    diff_mask = (arr_v4 != arr_fit).any(axis=2)
    if diff_mask.sum() < min_area:
        return []
    labeled, n_labels = label(diff_mask)
    bboxes = []
    for lbl in range(1, n_labels + 1):
        ys, xs = np.where(labeled == lbl)
        if len(ys) < min_area:
            continue
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        bboxes.append((x1, y1, x2, y2))
    # Sort by area descending
    bboxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    return bboxes


def expand_to_crop_size(
    bbox: tuple[int, int, int, int], w: int, h: int
) -> tuple[int, int, int, int] | None:
    """Expand a tight bbox to CROP_SIZE×CROP_SIZE centered on it."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    half = CROP_SIZE // 2
    nx1 = cx - half
    ny1 = cy - half
    nx2 = cx + half
    ny2 = cy + half
    # Clamp to image bounds
    if nx1 < 0:
        nx2 -= nx1
        nx1 = 0
    if ny1 < 0:
        ny2 -= ny1
        ny1 = 0
    if nx2 > w:
        nx1 -= (nx2 - w)
        nx2 = w
    if ny2 > h:
        ny1 -= (ny2 - h)
        ny2 = h
    nx1 = max(0, nx1)
    ny1 = max(0, ny1)
    nx2 = min(w, nx2)
    ny2 = min(h, ny2)
    if nx2 - nx1 < 20 or ny2 - ny1 < 20:
        return None
    return (nx1, ny1, nx2, ny2)


def main():
    samples = sorted(
        list(Path("input").glob("sample_*.jpg"))
        + list(Path("input").glob("sample_*.png"))
    )
    if not samples:
        print("No samples", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_crops = 0
    samples_with_crops = 0
    zero_diff_samples: list[str] = []

    for sp in samples:
        print(f"\n{sp.name}...", flush=True)
        src_img = Image.open(sp).convert("RGB")
        w, h = src_img.size

        svg_v4, _, _ = vectorize_to_svg(
            input_path=sp, colors=DEFAULT_COLORS, colors_mode=COLORS_MODE_UP_TO,
            engine="vtracer", upscale=True,
        )
        svg_fit, stats = geometry_fit(svg_v4)

        p1 = stats["pass_stats"][0]
        p2 = stats["pass_stats"][1]
        p3 = stats["pass_stats"][2]
        print(f"  P1: merged={p1['lines_merged']} changed={p1['shapes_changed']} r={p1['reverts']}")
        print(f"  P2: snapped={p2['axes_snapped']} changed={p2['shapes_changed']} r={p2['reverts']}")
        print(f"  P3: smoothed={p3['joints_smoothed']} corners={p3['corners_kept']} changed={p3['shapes_changed']} r={p3['reverts']}")

        if p2["axes_snapped"] == 0 and p3["joints_smoothed"] == 0:
            print(f"  SKIP: no geometry changes")
            continue

        png_v4 = render_svg_to_png(svg_v4, (w, h))
        png_fit = render_svg_to_png(svg_fit, (w, h))

        arr_v4 = np.array(png_v4)
        arr_fit = np.array(png_fit)

        total_diff = int((arr_v4 != arr_fit).any(axis=2).sum())
        if total_diff == 0:
            print(f"  ZERO DIFF: pass 2+3 produced no raster-level change")
            zero_diff_samples.append(sp.stem)
            continue

        bboxes = find_diff_bboxes(arr_v4, arr_fit)
        print(f"  Total diff px: {total_diff}, components: {len(bboxes)}")

        crops_made = 0
        for bbox in bboxes:
            if crops_made >= MAX_CROPS_PER_SAMPLE:
                break
            crop_box = expand_to_crop_size(bbox, w, h)
            if crop_box is None:
                continue

            # Verify non-zero diff in this crop
            x1, y1, x2, y2 = crop_box
            crop_v4 = arr_v4[y1:y2, x1:x2]
            crop_fit = arr_fit[y1:y2, x1:x2]
            crop_diff = int((crop_v4 != crop_fit).any(axis=2).sum())
            if crop_diff == 0:
                continue  # hard requirement

            label_str = f"{sp.stem} diff={crop_diff}px"
            strip = make_crop_strip(src_img, png_v4, png_fit, crop_box, label_str)
            name = f"{sp.stem}_crop{crops_made}.png"
            strip.save(OUT_DIR / name)
            print(f"  → {name} box=({x1},{y1},{x2},{y2}) diff={crop_diff}px")
            crops_made += 1
            total_crops += 1

        if crops_made > 0:
            samples_with_crops += 1

    print(f"\n{'='*60}")
    print(f"Done. {total_crops} crops in {OUT_DIR}/")
    print(f"Samples with crops: {samples_with_crops}/{len(samples)}")
    if zero_diff_samples:
        print(f"ZERO DIFF samples (pass 2+3 produced no raster change): {', '.join(zero_diff_samples)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

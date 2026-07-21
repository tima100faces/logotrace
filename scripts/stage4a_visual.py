#!/usr/bin/env python3
"""Stage 4a visual crops: SOURCE | v4 | v4+fit at detected changes.

Requirements:
- Every crop must contain at least one geometry_fit change.
- Non-zero pixel diff between v4 and v4+fit rasters before writing crop.
"""

from pathlib import Path
import subprocess, tempfile

from PIL import Image, ImageDraw
import numpy as np

from src.pipeline import vectorize_to_svg
from src.geometry_fit import geometry_fit
from src.colors import COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS

OUT_DIR = Path("output/stage4a_visual")
ZOOM = 4
BOX_SIZE = 160


def render_svg_to_png(svg_text: str, size: tuple[int, int]) -> Image.Image:
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="w") as sf:
        sf.write(svg_text)
        svg_path = sf.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as pf:
        png_path = pf.name
    try:
        subprocess.run(
            ["rsvg-convert", svg_path, "-o", png_path, "-w", str(size[0])],
            check=True, capture_output=True, timeout=30,
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


def main():
    samples = sorted(
        list(Path("input").glob("sample_*.jpg"))
        + list(Path("input").glob("sample_*.png"))
    )
    if not samples:
        print("No samples")
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_crops = 0

    for sp in samples:
        print(f"\n{sp.name}...")
        src_img = Image.open(sp).convert("RGB")
        w, h = src_img.size

        svg_v4, _, _ = vectorize_to_svg(
            input_path=sp, colors=DEFAULT_COLORS, colors_mode=COLORS_MODE_UP_TO,
            engine="vtracer", upscale=True,
        )
        svg_fit, stats = geometry_fit(svg_v4)

        change_log = stats.get("change_log", [])
        print(f"  Changes: {len(change_log)} (lines={stats.get('lines_merged',0)} "
              f"axes={stats.get('axes_snapped',0)} joints={stats.get('joints_smoothed',0)})")

        if not change_log:
            print(f"  SKIP: no changes detected")
            continue

        png_v4 = render_svg_to_png(svg_v4, (w, h))
        png_fit = render_svg_to_png(svg_fit, (w, h))

        # Pick up to 3 crop regions at change locations
        crops_made = 0
        used_boxes: set[tuple] = set()

        for entry in change_log[:20]:  # sample first 20 changes
            if crops_made >= 3:
                break

            cx, cy = int(entry["x"]), int(entry["y"])
            # Skip if outside image bounds
            if cx < BOX_SIZE // 2 or cy < BOX_SIZE // 2:
                continue
            if cx + BOX_SIZE // 2 >= w or cy + BOX_SIZE // 2 >= h:
                continue

            box = (cx - BOX_SIZE // 2, cy - BOX_SIZE // 2,
                   cx + BOX_SIZE // 2, cy + BOX_SIZE // 2)

            # Deduplicate nearby boxes
            box_key = (box[0] // 50, box[1] // 50)
            if box_key in used_boxes:
                continue
            used_boxes.add(box_key)

            # Verify non-zero diff between v4 and v4+fit in this crop
            crop_v4 = np.array(png_v4.crop(box))
            crop_fit = np.array(png_fit.crop(box))
            diff = int((crop_v4 != crop_fit).any(axis=2).sum())
            if diff == 0:
                continue

            angle = entry.get("angle", "?")
            label = f"joint {angle}°"
            strip = make_crop_strip(src_img, png_v4, png_fit, box, label)
            name = f"{sp.stem}_crop{crops_made}.png"
            strip.save(OUT_DIR / name)
            print(f"  → {name} ({strip.size}) diff={diff}px joint={angle}°")
            crops_made += 1
            total_crops += 1

    print(f"\nDone. {total_crops} files in {OUT_DIR}")


if __name__ == "__main__":
    main()

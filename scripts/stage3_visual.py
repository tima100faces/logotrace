#!/usr/bin/env python3
"""Generate 400% zoom visual crop comparisons for Stage 3 subpixel evaluation."""
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from src.pipeline import vectorize_to_svg
from src.colors import COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS


OUT_DIR = Path("output/stage3_visual")
ZOOM = 4
BOX_SIZE = 200  # source px, becomes 800 at 4x


def render_svg_to_png(svg_text: str, size: tuple[int, int]) -> Image.Image:
    """Render SVG to PNG using rsvg-convert."""
    import subprocess
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
    img_a: Image.Image,
    img_b: Image.Image,
    img_c: Image.Image | None,
    source_img: Image.Image,
    box: tuple[int, int, int, int],
    label_a: str,
    label_b: str,
    label_c: str | None,
) -> Image.Image:
    """Create a horizontal comparison strip with zoom crops."""
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1

    crops = []
    labels = [label_a, label_b]
    images = [img_a, img_b]
    if img_c:
        images.append(img_c)
        labels.append(label_c or "C")

    for img, label in zip(images, labels):
        crop = img.crop((x1, y1, x2, y2))
        crop = crop.resize((w * ZOOM, h * ZOOM), Image.Resampling.NEAREST)
        # Add 2px red outline
        draw = ImageDraw.Draw(crop)
        draw.rectangle([1, 1, crop.width - 2, crop.height - 2], outline="red", width=2)
        draw.text((4, 4), label, fill="red")
        crops.append(crop)

    # Source crop for reference
    src_crop = source_img.crop((x1, y1, x2, y2))
    src_crop = src_crop.resize((w * ZOOM, h * ZOOM), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(src_crop)
    draw.text((4, 4), "SOURCE", fill="red")
    crops.insert(0, src_crop)

    # Stack vertically
    total_h = sum(c.height for c in crops)
    strip = Image.new("RGB", (crops[0].width, total_h), (30, 30, 30))
    y = 0
    for c in crops:
        strip.paste(c, (0, y))
        y += c.height

    return strip


def main():
    samples = sorted(Path("input").glob("sample_*.jpg"))
    if not samples:
        print("No samples found")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for sp in samples:
        print(f"Processing {sp.name}...")

        # Load source
        src_img = Image.open(sp).convert("RGB")
        w, h = src_img.size

        # Crop boxes: center and bottom-right
        boxes = [
            (w // 3, h // 3, w // 3 + BOX_SIZE, h // 3 + BOX_SIZE),
            (w - BOX_SIZE - 20, h - BOX_SIZE - 20, w - 20, h - 20),
        ]

        # Render variants
        try:
            svg_a, _, _ = vectorize_to_svg(input_path=sp, colors=DEFAULT_COLORS,
                                            colors_mode=COLORS_MODE_UP_TO,
                                            engine="vtracer", upscale=True)
            png_a = render_svg_to_png(svg_a, (w, h))

            svg_b, _, _ = vectorize_to_svg(input_path=sp, colors=DEFAULT_COLORS,
                                            colors_mode=COLORS_MODE_UP_TO,
                                            engine="subpixel", upscale=False)
            png_b = render_svg_to_png(svg_b, (w, h))

            svg_c, _, _ = vectorize_to_svg(input_path=sp, colors=DEFAULT_COLORS,
                                            colors_mode=COLORS_MODE_UP_TO,
                                            engine="subpixel", upscale=True)
            png_c = render_svg_to_png(svg_c, (w, h))

        except Exception as exc:
            print(f"  SKIP: {exc}")
            continue

        for bi, box in enumerate(boxes):
            strip = make_crop_strip(
                png_a, png_b, png_c, src_img, box,
                "VTracer+upscale", "Subpixel", "Subpix+upscale",
            )
            name = f"{sp.stem}_crop{bi}.png"
            strip.save(OUT_DIR / name)
            print(f"  → {name} ({strip.size})")

    print(f"\nDone. {len(list(OUT_DIR.glob('*.png')))} files in {OUT_DIR}")


if __name__ == "__main__":
    main()

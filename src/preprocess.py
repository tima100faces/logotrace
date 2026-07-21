from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from src.config import MAX_COLORS, MIN_COLORS


class PreprocessError(ValueError):
    pass


def _validate_colors(max_colors: int) -> int:
    if not isinstance(max_colors, int) or max_colors < MIN_COLORS or max_colors > MAX_COLORS:
        raise PreprocessError(
            f"colors must be an integer in {MIN_COLORS}..{MAX_COLORS}, got {max_colors!r}"
        )
    return max_colors


def load_image(source: Path | bytes | Image.Image) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.copy()
    if isinstance(source, bytes):
        try:
            img = Image.open(BytesIO(source))
            img.load()
            return img
        except Exception as exc:  # noqa: BLE001
            raise PreprocessError(f"cannot decode image bytes: {exc}") from exc
    path = Path(source)
    if not path.is_file():
        raise PreprocessError(f"file not found: {path}")
    try:
        img = Image.open(path)
        img.load()
        return img
    except Exception as exc:  # noqa: BLE001
        raise PreprocessError(f"cannot open image {path}: {exc}") from exc


def has_meaningful_alpha(img: Image.Image) -> bool:
    """True if image has an alpha channel with any non-opaque pixel."""
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
        extrema = alpha.getextrema()
        return extrema[0] < 255
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False


def quantize_max_colors(img: Image.Image, max_colors: int) -> Image.Image:
    """Reduce to at most `max_colors` solid colors. Preserve alpha if present."""
    max_colors = _validate_colors(max_colors)
    keep_alpha = has_meaningful_alpha(img)

    if keep_alpha:
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        rgb = Image.new("RGB", rgba.size, (255, 255, 255))
        rgb.paste(rgba, mask=alpha)
        # Quantize only visible RGB; alpha stays separate (no white matte in output).
        # Using paste-on-white only as temporary quantize aid for transparent holes;
        # final pixels use original alpha.
        quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
        q_rgb = quantized.convert("RGB")
        out = q_rgb.convert("RGBA")
        out.putalpha(alpha)
        return out

    rgb = img.convert("RGB")
    quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    return quantized.convert("RGB")


def prepare_for_trace(
    source: Path | bytes | Image.Image,
    max_colors: int,
    dest_path: Path,
) -> Path:
    """Load, quantize to <= max_colors, write PNG (with alpha if needed)."""
    img = load_image(source)
    prepared = quantize_max_colors(img, max_colors)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    # PNG preserves alpha; never force JPEG white background
    prepared.save(dest_path, format="PNG")
    return dest_path

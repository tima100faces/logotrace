from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from src.colors import COLORS_MODE_UP_TO, analyze_palette, remap_to_palette
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
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
        extrema = alpha.getextrema()
        if not extrema:
            return False
        lo = extrema[0]
        if isinstance(lo, tuple):
            lo = lo[0]
        return int(lo) < 255
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False


def prepare_for_trace(
    source: Path | bytes | Image.Image,
    max_colors: int,
    dest_path: Path,
    *,
    colors_mode: str = COLORS_MODE_UP_TO,
) -> tuple[Path, list[tuple[int, int, int]]]:
    """Brand palette (mass-aware + gradient crush) → hard remap → PNG for VTracer.

    Background is always detected and kept as the first palette entry.
    No pixel upscale / morph / disk-snap here.
    """
    max_colors = _validate_colors(max_colors)
    img = load_image(source)
    keep_alpha = has_meaningful_alpha(img)

    analysis = analyze_palette(img, max_colors, colors_mode=colors_mode)
    prepared = remap_to_palette(
        img,
        analysis.colors,
        background=analysis.background,
        keep_alpha=keep_alpha,
    )

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.save(dest_path, format="PNG")
    return dest_path, analysis.colors

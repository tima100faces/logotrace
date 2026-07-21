from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from src.colors import COLORS_MODE_UP_TO, analyze_palette, remap_to_palette
from src.config import MAX_COLORS, MIN_COLORS
from src.disks import snap_disks_in_label_image


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


def _smooth_label_edges(img: Image.Image) -> Image.Image:
    """Morphological close+open per solid color — less stair-step without new hues."""
    if img.mode == "RGBA":
        rgb = img.convert("RGB")
        alpha = img.getchannel("A")
        has_a = True
    else:
        rgb = img.convert("RGB")
        alpha = None
        has_a = False

    arr = np.asarray(rgb, dtype=np.uint8)
    h, w, _ = arr.shape
    flat = arr.reshape(-1, 3)
    uniq = np.unique(flat, axis=0)
    if len(uniq) == 0 or len(uniq) > 32:
        return img

    # Paint lighter colors first, darker ink last so ink wins overlaps
    order = sorted(
        [tuple(int(x) for x in c) for c in uniq],
        key=lambda c: (c[0] + c[1] + c[2]),
        reverse=True,
    )
    out = np.zeros_like(arr)
    painted = np.zeros((h, w), dtype=bool)
    for col in order:
        mask = (
            (arr[:, :, 0] == col[0])
            & (arr[:, :, 1] == col[1])
            & (arr[:, :, 2] == col[2])
        )
        if not mask.any():
            continue
        m_img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
        m_img = m_img.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
        m_img = m_img.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
        m2 = np.asarray(m_img) > 127
        out[m2] = np.array(col, dtype=np.uint8)
        painted |= m2
    if (~painted).any():
        out[~painted] = arr[~painted]

    result = Image.fromarray(out, mode="RGB")
    if has_a and alpha is not None:
        a = alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
        result = result.convert("RGBA")
        result.putalpha(a)
    return result


def prepare_for_trace(
    source: Path | bytes | Image.Image,
    max_colors: int,
    dest_path: Path,
    *,
    colors_mode: str = COLORS_MODE_UP_TO,
) -> tuple[Path, list[tuple[int, int, int]], str]:
    """Extract palette (gradient-crushed), remap, edge smooth, write PNG."""
    max_colors = _validate_colors(max_colors)
    img = load_image(source)
    keep_alpha = has_meaningful_alpha(img)

    analysis = analyze_palette(img, max_colors, colors_mode=colors_mode)
    prepared = remap_to_palette(
        img,
        analysis.colors,
        background=analysis.background,
        mode=analysis.mode,
        keep_alpha=keep_alpha,
    )
    # Snap large badge-like disks to true circles before trace (sample_08).
    prepared = snap_disks_in_label_image(prepared)
    # Mild upscale helps JPEG contours before VTracer.
    max_side = max(prepared.size)
    if max_side < 2800:
        prepared = prepared.resize(
            (prepared.width * 2, prepared.height * 2),
            Image.Resampling.NEAREST,  # keep hard labels; no new gray edges
        )

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.save(dest_path, format="PNG")
    return dest_path, analysis.colors, analysis.mode

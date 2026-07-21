from __future__ import annotations

import tempfile
from pathlib import Path

from src.config import DEFAULT_COLORS, MAX_COLORS, MIN_COLORS
from src.postprocess import finalize_svg
from src.preprocess import PreprocessError, prepare_for_trace
from src.tracer_vtracer import TracerError, run_vtracer


class VectorizeError(RuntimeError):
    pass


def _check_colors(colors: int) -> int:
    if not isinstance(colors, int) or colors < MIN_COLORS or colors > MAX_COLORS:
        raise VectorizeError(
            f"colors must be integer {MIN_COLORS}..{MAX_COLORS}, got {colors!r}"
        )
    return colors


def vectorize_file(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    output_path: Path | str | None = None,
) -> str:
    """Vectorize image file → SVG string. Optionally write SVG to output_path."""
    colors = _check_colors(colors)
    input_path = Path(input_path)
    if not input_path.is_file():
        raise VectorizeError(f"input not found: {input_path}")

    try:
        with tempfile.TemporaryDirectory(prefix="logotrace-") as tmp:
            tmpdir = Path(tmp)
            prepared = tmpdir / "prepared.png"
            svg_tmp = tmpdir / "out.svg"
            prepare_for_trace(input_path, colors, prepared)
            run_vtracer(prepared, svg_tmp)
            svg_text = finalize_svg(svg_tmp)
    except (PreprocessError, TracerError) as exc:
        raise VectorizeError(str(exc)) from exc

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg_text, encoding="utf-8")

    return svg_text


def vectorize_bytes(
    data: bytes,
    *,
    colors: int = DEFAULT_COLORS,
    filename_hint: str = "upload.png",
) -> str:
    """Vectorize raw image bytes → SVG string."""
    colors = _check_colors(colors)
    if not data:
        raise VectorizeError("empty image payload")

    try:
        with tempfile.TemporaryDirectory(prefix="logotrace-") as tmp:
            tmpdir = Path(tmp)
            # keep original bytes for Pillow decode
            src = tmpdir / Path(filename_hint).name
            if not src.suffix:
                src = src.with_suffix(".bin")
            src.write_bytes(data)
            prepared = tmpdir / "prepared.png"
            svg_tmp = tmpdir / "out.svg"
            prepare_for_trace(data, colors, prepared)
            run_vtracer(prepared, svg_tmp)
            return finalize_svg(svg_tmp)
    except (PreprocessError, TracerError) as exc:
        raise VectorizeError(str(exc)) from exc

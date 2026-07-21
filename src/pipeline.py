from __future__ import annotations

import tempfile
from pathlib import Path

from src.config import (
    DEFAULT_COLORS,
    MAX_COLORS,
    MIN_COLORS,
    VTRACER_FILTER_SPECKLE,
)
from src.pdf_export import PdfError, svg_to_pdf_bytes
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


def vectorize_to_svg(
    input_path: Path | str | None = None,
    *,
    data: bytes | None = None,
    colors: int = DEFAULT_COLORS,
    filename_hint: str = "upload.bin",
) -> tuple[str, list[tuple[int, int, int]]]:
    """Core: raster → SVG string + extracted palette."""
    colors = _check_colors(colors)
    if input_path is None and data is None:
        raise VectorizeError("input_path or data required")

    try:
        with tempfile.TemporaryDirectory(prefix="logotrace-") as tmp:
            tmpdir = Path(tmp)
            prepared = tmpdir / "prepared.png"
            svg_tmp = tmpdir / "out.svg"
            if data is not None:
                source: Path | bytes = data
            else:
                source = Path(input_path)  # type: ignore[arg-type]
                if not source.is_file():
                    raise VectorizeError(f"input not found: {source}")

            _path, palette, _mode = prepare_for_trace(source, colors, prepared)
            # Lower speckle filter so thin second-color strokes survive (e.g. black+red)
            run_vtracer(
                prepared,
                svg_tmp,
                filter_speckle=max(2, VTRACER_FILTER_SPECKLE // 2),
                color_precision=8,
            )
            svg_text = finalize_svg(svg_tmp)
            return svg_text, palette
    except (PreprocessError, TracerError) as exc:
        raise VectorizeError(str(exc)) from exc


def vectorize_file(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    output_path: Path | str | None = None,
    fmt: str = "pdf",
) -> Path:
    """
    Vectorize image file → PDF (default) or SVG.
    Returns path to written file.
    """
    fmt = fmt.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise VectorizeError("fmt must be 'pdf' or 'svg'")

    input_path = Path(input_path)
    svg_text, _palette = vectorize_to_svg(input_path=input_path, colors=colors)

    if output_path is None:
        output_path = input_path.with_suffix(f".{fmt}")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "svg":
        out.write_text(svg_text, encoding="utf-8")
        return out

    try:
        pdf = svg_to_pdf_bytes(svg_text)
    except PdfError as exc:
        raise VectorizeError(str(exc)) from exc
    out.write_bytes(pdf)
    return out


def vectorize_bytes(
    data: bytes,
    *,
    colors: int = DEFAULT_COLORS,
    filename_hint: str = "upload.png",
    fmt: str = "pdf",
) -> bytes:
    """Vectorize raw bytes → PDF or SVG bytes."""
    fmt = fmt.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise VectorizeError("fmt must be 'pdf' or 'svg'")
    if not data:
        raise VectorizeError("empty image payload")

    svg_text, _palette = vectorize_to_svg(
        data=data, colors=colors, filename_hint=filename_hint
    )
    if fmt == "svg":
        return svg_text.encode("utf-8")
    try:
        return svg_to_pdf_bytes(svg_text)
    except PdfError as exc:
        raise VectorizeError(str(exc)) from exc


# Back-compat alias used in older tests: returns SVG string
def vectorize_file_svg_string(input_path: Path | str, *, colors: int = DEFAULT_COLORS) -> str:
    svg, _ = vectorize_to_svg(input_path=input_path, colors=colors)
    return svg

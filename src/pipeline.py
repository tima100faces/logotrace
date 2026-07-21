from __future__ import annotations

import tempfile
from pathlib import Path

from src.colors import COLORS_MODE_EXACT, COLORS_MODE_UP_TO
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
from src.verify import VerifyError, verify_vector_output


class VectorizeError(RuntimeError):
    pass


def _check_colors(colors: int) -> int:
    if not isinstance(colors, int) or colors < MIN_COLORS or colors > MAX_COLORS:
        raise VectorizeError(
            f"colors must be integer {MIN_COLORS}..{MAX_COLORS}, got {colors!r}"
        )
    return colors


def _check_colors_mode(colors_mode: str) -> str:
    m = (colors_mode or COLORS_MODE_UP_TO).lower().strip()
    if m not in (COLORS_MODE_UP_TO, COLORS_MODE_EXACT):
        raise VectorizeError("colors_mode must be 'up_to' or 'exact'")
    return m


def vectorize_to_svg(
    input_path: Path | str | None = None,
    *,
    data: bytes | None = None,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    filename_hint: str = "upload.bin",
    geom: str = "off",
) -> tuple[str, list[tuple[int, int, int]]]:
    """Core: raster → SVG string + extracted palette."""
    colors = _check_colors(colors)
    colors_mode = _check_colors_mode(colors_mode)
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

            _path, palette, _mode = prepare_for_trace(
                source, colors, prepared, colors_mode=colors_mode
            )
            # Same as color-v1: color mode + mild speckle so thin strokes survive
            run_vtracer(
                prepared,
                svg_tmp,
                colormode="color",
                filter_speckle=max(2, VTRACER_FILTER_SPECKLE // 2),
                color_precision=8,
            )
            svg_text = finalize_svg(svg_tmp, geom=geom)
            return svg_text, palette
    except (PreprocessError, TracerError) as exc:
        raise VectorizeError(str(exc)) from exc


def vectorize_file(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    output_path: Path | str | None = None,
    fmt: str = "pdf",
    geom: str = "off",
) -> Path:
    """Vectorize image file → PDF (default) or SVG."""
    fmt = fmt.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise VectorizeError("fmt must be 'pdf' or 'svg'")

    input_path = Path(input_path)
    svg_text, _palette = vectorize_to_svg(
        input_path=input_path,
        colors=colors,
        colors_mode=colors_mode,
        geom=geom,
    )

    if output_path is None:
        output_path = input_path.with_suffix(f".{fmt}")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "svg":
        out.write_text(svg_text, encoding="utf-8")
    else:
        try:
            pdf = svg_to_pdf_bytes(svg_text)
        except PdfError as exc:
            raise VectorizeError(str(exc)) from exc
        out.write_bytes(pdf)

    try:
        verify_vector_output(out, source_image=input_path)
    except VerifyError as exc:
        raise VectorizeError(f"output failed self-check: {exc}") from exc
    return out


def vectorize_bytes(
    data: bytes,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    filename_hint: str = "upload.png",
    fmt: str = "pdf",
    geom: str = "off",
) -> bytes:
    """Vectorize raw bytes → PDF or SVG bytes."""
    fmt = fmt.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise VectorizeError("fmt must be 'pdf' or 'svg'")
    if not data:
        raise VectorizeError("empty image payload")

    svg_text, _palette = vectorize_to_svg(
        data=data,
        colors=colors,
        colors_mode=colors_mode,
        filename_hint=filename_hint,
        geom=geom,
    )
    if fmt == "svg":
        payload = svg_text.encode("utf-8")
    else:
        try:
            payload = svg_to_pdf_bytes(svg_text)
        except PdfError as exc:
            raise VectorizeError(str(exc)) from exc

    # self-check via temp file
    import tempfile

    suffix = ".pdf" if fmt == "pdf" else ".svg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tmp_path = Path(tf.name)
        tf.write(payload)
    try:
        verify_vector_output(tmp_path)
    except VerifyError as exc:
        raise VectorizeError(f"output failed self-check: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return payload
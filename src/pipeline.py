from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

from PIL import Image

from src.colors import COLORS_MODE_EXACT, COLORS_MODE_UP_TO
from src.config import (
    DEFAULT_COLORS,
    MAX_COLORS,
    MIN_COLORS,
    VTRACER_FILTER_SPECKLE,
    VTRACER_SEGMENT_LENGTH,
)
from src.pdf_export import PdfError, svg_to_pdf_bytes
from src.postprocess import finalize_svg
from src.preprocess import PreprocessError, prepare_for_trace
from src.tracer_vtracer import TracerError, run_vtracer
from src.verify import VerifyError, verify_vector_output


class VectorizeError(RuntimeError):
    pass


# ---- upscale policy (v4) ---------------------------------------------------

UPSCALE_MAX_SIDE = 3072
UPSCALE_MAX_PX = 9_500_000
UPSCALE_MIN_EFFECTIVE = 1.05


def _compute_upscale_factor(w: int, h: int) -> float:
    """effective = max(1.0, min(2.0, 3072/max_side, sqrt(9.5M/(w*h))))"""
    max_side = max(w, h)
    total_px = w * h
    effective = min(
        2.0,
        UPSCALE_MAX_SIDE / max_side,
        (UPSCALE_MAX_PX / total_px) ** 0.5 if total_px > 0 else 2.0,
    )
    return max(1.0, effective)


def _wrap_svg_scaled(svg_text: str, scale: float, orig_w: int, orig_h: int) -> str:
    """Wrap SVG in <g transform='scale(1/s,…)'> and fix viewport to orig_w×orig_h."""
    if scale <= 1.0:
        return svg_text
    inv = 1.0 / scale
    svg_text = re.sub(r'width="\d+(\.\d+)?"', f'width="{orig_w}"', svg_text)
    svg_text = re.sub(r'height="\d+(\.\d+)?"', f'height="{orig_h}"', svg_text)
    svg_text = re.sub(
        r'(<svg\b[^>]*>)',
        rf'\1\n<g transform="scale({inv:.6f}, {inv:.6f})">',
        svg_text,
        count=1,
    )
    svg_text = svg_text.replace("</svg>", "</g>\n</svg>")
    return svg_text


# ---- public API ------------------------------------------------------------


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
    upscale: bool = True,
    engine: str = "vtracer",
) -> tuple[str, list[tuple[int, int, int]], float]:
    """Core: raster → SVG string + extracted palette + effective upscale factor.

    upscale=True (default): apply auto upscale policy (≤ 2x, capped by memory).
    upscale=False: no upscale (off escape hatch, factor=1.0).
    """
    colors = _check_colors(colors)
    colors_mode = _check_colors_mode(colors_mode)
    if engine not in ("vtracer", "subpixel"):
        raise VectorizeError("engine must be 'vtracer' or 'subpixel'")
    if input_path is None and data is None:
        raise VectorizeError("input_path or data required")

    try:
        with tempfile.TemporaryDirectory(prefix="logotrace-") as tmp:
            tmpdir = Path(tmp)

            # 0 ─ Determine source dimensions and upscale factor
            if data is not None:
                src_img = Image.open(io.BytesIO(data))
            else:
                src_img = Image.open(input_path)
            orig_w, orig_h = src_img.size

            if upscale:
                eff = _compute_upscale_factor(orig_w, orig_h)
            else:
                eff = 1.0

            if eff > UPSCALE_MIN_EFFECTIVE:
                new_w = int(orig_w * eff)
                new_h = int(orig_h * eff)
                src_img = src_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                upscaled_path = tmpdir / "upscaled.png"
                src_img.save(upscaled_path, format="PNG")
                source: Path | bytes = upscaled_path
            else:
                eff = 1.0
                if data is not None:
                    source = data
                else:
                    source = Path(input_path)  # type: ignore[arg-type]
                    if not source.is_file():
                        raise VectorizeError(f"input not found: {source}")

            # 1 ─ Palette + remap
            prepared = tmpdir / "prepared.png"
            svg_tmp = tmpdir / "out.svg"
            _path, palette, _mode = prepare_for_trace(
                source, colors, prepared, colors_mode=colors_mode
            )

            if engine == "subpixel":
                # Subpixel contour tracer: works from original image + palette
                from src.tracer_subpixel import subpixel_trace

                bg = None
                if "paper" in (_mode or ""):
                    from src.colors import estimate_background
                    bg = estimate_background(src_img)
                svg_raw = subpixel_trace(src_img, list(palette), bg_color=bg)
                subpixel_svg = tmpdir / "subpixel.svg"
                subpixel_svg.write_text(svg_raw, encoding="utf-8")
                svg_text = finalize_svg(subpixel_svg, geom=geom)
                return svg_text, palette, eff

            # 2 ─ VTracer (scale pixel-unit thresholds)
            if eff > UPSCALE_MIN_EFFECTIVE:
                speckle = max(1, int(max(2, VTRACER_FILTER_SPECKLE // 2) * eff))
                seglen = min(10, max(3, int(VTRACER_SEGMENT_LENGTH * eff)))  # VTracer range [3.5,10]
            else:
                speckle = max(2, VTRACER_FILTER_SPECKLE // 2)
                seglen = VTRACER_SEGMENT_LENGTH

            run_vtracer(
                prepared,
                svg_tmp,
                colormode="color",
                filter_speckle=speckle,
                segment_length=seglen,
                color_precision=8,
            )

            # 3 ─ Postprocess + scale back viewport
            svg_text = finalize_svg(svg_tmp, geom=geom)
            if eff > 1.0:
                svg_text = _wrap_svg_scaled(svg_text, eff, orig_w, orig_h)

            return svg_text, palette, eff
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
    upscale: bool = True,
    engine: str = "vtracer",
) -> Path:
    """Vectorize image file → PDF (default) or SVG."""
    fmt = fmt.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise VectorizeError("fmt must be 'pdf' or 'svg'")

    input_path = Path(input_path)
    svg_text, _palette, _eff = vectorize_to_svg(
        input_path=input_path,
        colors=colors,
        colors_mode=colors_mode,
        geom=geom,
        upscale=upscale,
        engine=engine,
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
    upscale: bool = True,
    engine: str = "vtracer",
    debug_save: bool = True,
) -> tuple[bytes, float]:
    """Vectorize raw bytes → (PDF or SVG bytes, effective upscale factor).

    Optionally dumps to input/output for debugging.
    """
    fmt = fmt.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise VectorizeError("fmt must be 'pdf' or 'svg'")
    if not data:
        raise VectorizeError("empty image payload")

    svg_text, palette, eff = vectorize_to_svg(
        data=data,
        colors=colors,
        colors_mode=colors_mode,
        filename_hint=filename_hint,
        geom=geom,
        upscale=upscale,
        engine=engine,
    )
    if fmt == "svg":
        payload = svg_text.encode("utf-8")
    else:
        try:
            payload = svg_to_pdf_bytes(svg_text)
        except PdfError as exc:
            raise VectorizeError(str(exc)) from exc

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

    if debug_save:
        try:
            from src.debug_save import save_debug_run

            save_debug_run(
                input_bytes=data,
                filename_hint=filename_hint,
                output_bytes=payload,
                fmt=fmt,
                colors=colors,
                colors_mode=colors_mode,
                palette=palette,
                geom=geom,
                source="api",
            )
        except Exception:
            pass
    return payload, eff
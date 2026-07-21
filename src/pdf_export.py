"""SVG → PDF (RGB vector)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class PdfError(RuntimeError):
    pass


def svg_to_pdf_bytes(svg_text: str) -> bytes:
    """Convert SVG string to RGB PDF bytes."""
    # Prefer rsvg-convert (fast, solid); fallback cairosvg
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        with tempfile.TemporaryDirectory(prefix="logotrace-pdf-") as tmp:
            tdir = Path(tmp)
            svg_path = tdir / "in.svg"
            pdf_path = tdir / "out.pdf"
            svg_path.write_text(svg_text, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [rsvg, "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise PdfError(f"rsvg-convert failed: {exc}") from exc
            if proc.returncode != 0 or not pdf_path.is_file():
                err = (proc.stderr or proc.stdout or "").strip()
                raise PdfError(f"rsvg-convert error: {err}")
            data = pdf_path.read_bytes()
            if not data.startswith(b"%PDF"):
                raise PdfError("rsvg-convert output is not PDF")
            return data

    try:
        import cairosvg
    except ImportError as exc:
        raise PdfError("neither rsvg-convert nor cairosvg available") from exc

    try:
        data = cairosvg.svg2pdf(bytestring=svg_text.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"cairosvg failed: {exc}") from exc
    if not data or not data.startswith(b"%PDF"):
        raise PdfError("cairosvg produced invalid PDF")
    return data


def svg_file_to_pdf(svg_path: Path | str, pdf_path: Path | str) -> Path:
    svg_text = Path(svg_path).read_text(encoding="utf-8")
    data = svg_to_pdf_bytes(svg_text)
    out = Path(pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out

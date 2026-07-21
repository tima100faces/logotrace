"""Self-check vector outputs: non-empty PDF/SVG and non-blank raster coverage."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


class VerifyError(RuntimeError):
    pass


def _ink_coverage(img: Image.Image, white_thresh: int = 250) -> float:
    """Fraction of pixels that are not near-white (or transparent)."""
    if img.mode == "RGBA":
        rgba = img
        alpha = rgba.getchannel("A")
        rgb = rgba.convert("RGB")
    else:
        rgb = img.convert("RGB")
        alpha = None
    w, h = rgb.size
    total = w * h
    if total == 0:
        return 0.0
    # downsample for speed
    scale = max(w, h) / 400.0
    if scale > 1:
        nw, nh = max(1, int(w / scale)), max(1, int(h / scale))
        rgb = rgb.resize((nw, nh))
        if alpha is not None:
            alpha = alpha.resize((nw, nh))
        total = nw * nh
    px = list(rgb.getdata())
    ink = 0
    if alpha is not None:
        ap = list(alpha.getdata())
        for (r, g, b), a in zip(px, ap):
            if a < 16:
                continue
            if r < white_thresh or g < white_thresh or b < white_thresh:
                ink += 1
    else:
        for r, g, b in px:
            if r < white_thresh or g < white_thresh or b < white_thresh:
                ink += 1
    return ink / total


def rasterize_svg(svg_path: Path, out_png: Path, scale: float = 0.25) -> Path:
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        raise VerifyError("rsvg-convert required for verify")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    # zoom via width
    proc = subprocess.run(
        [rsvg, "-f", "png", "-z", str(scale), "-o", str(out_png), str(svg_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0 or not out_png.is_file():
        raise VerifyError(f"rsvg svg→png failed: {proc.stderr}")
    return out_png


def rasterize_pdf(pdf_path: Path, out_png: Path) -> Path:
    """Render first PDF page to PNG via pdftoppm or rsvg won't work — use pdftoppm/ImageMagick."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        prefix = out_png.with_suffix("")
        proc = subprocess.run(
            [pdftoppm, "-png", "-singlefile", "-r", "72", str(pdf_path), str(prefix)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        cand = Path(str(prefix) + ".png")
        if proc.returncode == 0 and cand.is_file():
            if cand != out_png:
                cand.replace(out_png)
            return out_png
    convert = shutil.which("convert")
    if convert:
        proc = subprocess.run(
            [convert, "-density", "72", f"{pdf_path}[0]", str(out_png)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0 and out_png.is_file():
            return out_png
    raise VerifyError("need pdftoppm or ImageMagick convert to rasterize PDF")


def verify_vector_output(
    path: Path,
    *,
    min_bytes: int = 500,
    min_ink_coverage: float = 0.002,
    source_image: Path | None = None,
) -> dict:
    """
    Verify PDF/SVG is non-empty and not a blank page.
    Returns metrics dict or raises VerifyError.
    """
    path = Path(path)
    if not path.is_file():
        raise VerifyError(f"missing output: {path}")
    size = path.stat().st_size
    if size < min_bytes:
        raise VerifyError(f"output too small ({size} bytes): {path}")

    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise VerifyError(f"not a PDF: {path}")
    elif suffix == ".svg":
        text = data.decode("utf-8", errors="replace")
        if "<svg" not in text.lower():
            raise VerifyError(f"not an SVG: {path}")
        # degenerate geom marker
        if re.search(r'd="M 0\.00 0\.00 L 0\.00 0\.00 Z"', text):
            # allow only if other real paths exist
            bad = len(re.findall(r'd="M 0\.00 0\.00 L 0\.00 0\.00 Z"', text))
            total = len(re.findall(r"<path\b", text, flags=re.I))
            if total > 0 and bad / total > 0.5:
                raise VerifyError(f"SVG mostly degenerate zero-paths: {path}")
    else:
        raise VerifyError(f"unsupported verify type: {suffix}")

    with tempfile.TemporaryDirectory(prefix="logotrace-verify-") as tmp:
        png = Path(tmp) / "page.png"
        if suffix == ".pdf":
            rasterize_pdf(path, png)
        else:
            rasterize_svg(path, png, scale=0.2)
        img = Image.open(png)
        cov = _ink_coverage(img)
        if cov < min_ink_coverage:
            raise VerifyError(
                f"blank/near-blank render ink_coverage={cov:.5f} < {min_ink_coverage}: {path}"
            )

        metrics = {
            "path": str(path),
            "bytes": size,
            "ink_coverage": round(cov, 5),
            "render_size": img.size,
        }
        if source_image and Path(source_image).is_file():
            src = Image.open(source_image)
            src_cov = _ink_coverage(src.convert("RGB"))
            metrics["source_ink_coverage"] = round(src_cov, 5)
            # output should retain some fraction of source ink presence
            if src_cov > 0.01 and cov < src_cov * 0.05:
                raise VerifyError(
                    f"output ink much lower than source ({cov:.4f} vs {src_cov:.4f}): {path}"
                )
        return metrics

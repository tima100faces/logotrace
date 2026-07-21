"""SVG post-process: optional svgo + optional geometry normalize."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.geometry import GEOM_OFF, normalize_svg_geometry


class PostprocessError(RuntimeError):
    pass


_SVG_START = re.compile(r"<svg\b", re.IGNORECASE)


def read_svg(path: Path | str) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not _SVG_START.search(text):
        raise PostprocessError("output does not look like SVG")
    return text


def maybe_svgo(svg_text: str) -> str:
    svgo = shutil.which("svgo")
    if not svgo:
        return svg_text
    try:
        with tempfile.TemporaryDirectory(prefix="logotrace-svgo-") as tmp:
            p = Path(tmp) / "in.svg"
            p.write_text(svg_text, encoding="utf-8")
            proc = subprocess.run(
                [svgo, str(p), "-o", str(p), "--multipass"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                return svg_text
            return p.read_text(encoding="utf-8")
    except (OSError, subprocess.TimeoutExpired):
        return svg_text


def finalize_svg(svg_path: Path | str, *, geom: str = "off", geometry_fit: bool = False) -> str:
    """
    Default geom=off: raw VTracer splines (production quality).
    basic/strict: experimental only — can facet curves.
    geometry_fit: primitive fitting (line detection, axis snap, G1 smoothing).
    """
    text = read_svg(svg_path)
    text = maybe_svgo(text)
    level = (geom or GEOM_OFF).lower().strip()
    if level != GEOM_OFF:
        text = normalize_svg_geometry(text, level=level)
    if geometry_fit:
        from src.geometry_fit import geometry_fit as apply_fit
        text, _ = apply_fit(text)
    return text

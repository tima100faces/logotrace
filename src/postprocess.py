"""SVG post-process: optional svgo + geometry normalize."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from src.geometry import normalize_svg_geometry


class PostprocessError(RuntimeError):
    pass


_SVG_START = re.compile(r"<svg\b", re.IGNORECASE)


def read_svg(path: Path | str) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not _SVG_START.search(text):
        raise PostprocessError("output does not look like SVG")
    return text


def maybe_svgo(svg_text: str) -> str:
    """Run svgo on temp content if available."""
    svgo = shutil.which("svgo")
    if not svgo:
        return svg_text
    import tempfile

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


def finalize_svg(svg_path: Path | str, *, geom: str = "off") -> str:
    text = read_svg(svg_path)
    text = maybe_svgo(text)
    text = normalize_svg_geometry(text, level=geom)
    return text

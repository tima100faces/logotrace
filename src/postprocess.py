from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class PostprocessError(RuntimeError):
    pass


_SVG_START = re.compile(r"<svg\b", re.IGNORECASE)


def read_svg(path: Path | str) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not _SVG_START.search(text):
        raise PostprocessError("output does not look like SVG")
    return text


def maybe_svgo(svg_path: Path | str) -> str:
    """Run svgo if available; otherwise return file contents unchanged."""
    path = Path(svg_path)
    raw = read_svg(path)
    svgo = shutil.which("svgo")
    if not svgo:
        return raw

    try:
        proc = subprocess.run(
            [svgo, str(path), "-o", str(path), "--multipass"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return raw

    if proc.returncode != 0:
        return raw
    return read_svg(path)


def finalize_svg(svg_path: Path | str) -> str:
    return maybe_svgo(svg_path)

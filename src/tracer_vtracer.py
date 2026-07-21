from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.config import (
    TRACE_TIMEOUT_SEC,
    VTRACER_BIN,
    VTRACER_BIN_FALLBACK,
    VTRACER_COLOR_PRECISION,
    VTRACER_FILTER_SPECKLE,
    VTRACER_HIERARCHICAL,
    VTRACER_MODE,
)


class TracerError(RuntimeError):
    pass


def resolve_vtracer_bin() -> str:
    bundled = Path(VTRACER_BIN)
    if bundled.is_file() and bundled.stat().st_mode & 0o111:
        return str(bundled)
    found = shutil.which(VTRACER_BIN_FALLBACK)
    if found:
        return found
    raise TracerError(
        f"vtracer binary not found at {bundled} and not on PATH. "
        "Install release binary into bin/vtracer."
    )


def run_vtracer(
    input_path: Path | str,
    output_path: Path | str,
    *,
    colormode: str = "color",
    filter_speckle: int = VTRACER_FILTER_SPECKLE,
    color_precision: int = VTRACER_COLOR_PRECISION,
    mode: str = VTRACER_MODE,
    hierarchical: str = VTRACER_HIERARCHICAL,
    timeout: int = TRACE_TIMEOUT_SEC,
) -> Path:
    """Run vtracer CLI. Returns path to written SVG."""
    binary = resolve_vtracer_bin()
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.is_file():
        raise TracerError(f"input not found: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        binary,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--colormode",
        colormode,
        "--filter_speckle",
        str(filter_speckle),
        "--color_precision",
        str(color_precision),
        "--mode",
        mode,
        "--hierarchical",
        hierarchical,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TracerError(f"vtracer timed out after {timeout}s") from exc
    except OSError as exc:
        raise TracerError(f"failed to execute vtracer: {exc}") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise TracerError(f"vtracer failed (code {proc.returncode}): {err}")

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise TracerError(f"vtracer produced no output at {output_path}")

    return output_path

"""Persist UI/CLI runs under input/ + output/ for interactive QA."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import PROJECT_ROOT

INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Soft cap only — no time-based delete (Tim: keep while few examples; ~month-ish headroom)
MAX_UI_RUNS = int(os.environ.get("LOGOTRACE_DEBUG_MAX_RUNS", "500"))
DEBUG_SAVE = os.environ.get("LOGOTRACE_DEBUG_SAVE", "1").strip().lower() not in (
    "0",
    "false",
    "off",
    "no",
)

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_name(name: str) -> str:
    base = Path(name or "upload.bin").name
    base = _SAFE.sub("_", base).strip("._") or "upload.bin"
    return base[:80]


def _ext_from_name_or_bytes(name: str, data: bytes) -> str:
    suf = Path(name).suffix.lower()
    if suf in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bin"}:
        return ".jpg" if suf == ".jpeg" else suf
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".bin"


def _run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{int(time.time() * 1000) % 100000:05d}"


def prune_ui_runs(max_runs: int = MAX_UI_RUNS) -> int:
    """Keep newest max_runs ui_* pairs; delete oldest. No time-based purge."""
    if max_runs <= 0:
        return 0
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # group by run id prefix ui_<id>
    ids: dict[str, float] = {}
    for p in list(INPUT_DIR.glob("ui_*")) + list(OUTPUT_DIR.glob("ui_*")):
        name = p.name
        if not name.startswith("ui_"):
            continue
        # ui_YYYYMMDD_HHMMSS_xxxxx_rest
        parts = name.split("_")
        if len(parts) < 4:
            key = name
        else:
            key = "_".join(parts[:4])  # ui_date_time_ms
        mtime = p.stat().st_mtime
        ids[key] = max(ids.get(key, 0), mtime)
    if len(ids) <= max_runs:
        return 0
    ordered = sorted(ids.items(), key=lambda kv: kv[1])
    drop = [k for k, _ in ordered[: len(ids) - max_runs]]
    removed = 0
    for key in drop:
        for folder in (INPUT_DIR, OUTPUT_DIR):
            for p in folder.glob(f"{key}*"):
                try:
                    p.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed


def save_debug_run(
    *,
    input_bytes: bytes,
    filename_hint: str,
    output_bytes: bytes,
    fmt: str,
    colors: int,
    colors_mode: str,
    palette: list[tuple[int, int, int]] | None = None,
    geom: str = "off",
    source: str = "api",
) -> dict | None:
    """
    Write input/<ui_id>.* + output/<ui_id>.pdf|svg + meta.json.
    Returns paths dict or None if disabled.
    """
    if not DEBUG_SAVE:
        return None
    if not input_bytes or not output_bytes:
        return None

    rid = _run_id()
    stem = f"ui_{rid}"
    in_ext = _ext_from_name_or_bytes(filename_hint, input_bytes)
    out_ext = ".pdf" if fmt == "pdf" else ".svg"

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    in_path = INPUT_DIR / f"{stem}{in_ext}"
    out_path = OUTPUT_DIR / f"{stem}{out_ext}"
    meta_path = OUTPUT_DIR / f"{stem}.meta.json"

    in_path.write_bytes(input_bytes)
    out_path.write_bytes(output_bytes)

    meta = {
        "id": stem,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "filename_hint": _safe_name(filename_hint),
        "colors": colors,
        "colors_mode": colors_mode,
        "geom": geom,
        "fmt": fmt,
        "palette": list(palette or []),
        "input_bytes": len(input_bytes),
        "output_bytes": len(output_bytes),
        "input_path": str(in_path),
        "output_path": str(out_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # also refresh convenient "last" pointers for quick agent checks
    try:
        last_in = INPUT_DIR / f"last{in_ext}"
        last_out = OUTPUT_DIR / f"last{out_ext}"
        last_meta = OUTPUT_DIR / "last.meta.json"
        last_in.write_bytes(input_bytes)
        last_out.write_bytes(output_bytes)
        last_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError:
        pass

    prune_ui_runs()
    return meta

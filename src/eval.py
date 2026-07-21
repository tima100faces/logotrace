"""Evaluation harness: objective quality metrics for tracer outputs.

Usage:
    python -m src.eval input/ --report output/eval_baseline.md
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, sobel

from src.colors import COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS
from src.pipeline import VectorizeError, vectorize_to_svg
from src.preprocess import load_image, prepare_for_trace
from src.verify import rasterize_svg

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _color_mask(arr: np.ndarray, color: tuple[int, int, int], radius: int = 20) -> np.ndarray:
    """Boolean mask: pixels within L2 radius of target color."""
    c = np.array(color, dtype=np.int32)
    d2 = np.sum((arr.astype(np.int32) - c) ** 2, axis=2)
    return d2 <= radius**2


def _edge_map(arr: np.ndarray) -> np.ndarray:
    """Binary edge map from RGB image via grayscale Sobel."""
    gray = np.mean(arr.astype(np.float64), axis=2)
    grad_x = sobel(gray, axis=1)
    grad_y = sobel(gray, axis=0)
    mag = np.hypot(grad_x, grad_y)
    # threshold at 95th percentile of non-zero magnitudes
    nonzero = mag[mag > 0]
    if len(nonzero) == 0:
        return np.zeros_like(mag, dtype=bool)
    thresh = np.percentile(nonzero, 95)
    return mag >= thresh


def _chamfer_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean Chamfer distance (pixels) from edge set a to edge set b.

    Uses Euclidean distance transform for O(N) memory and speed.
    """
    ay, ax = np.where(a)
    if len(ay) == 0:
        return float("inf")
    # Distance transform of target edge map b
    dt = distance_transform_edt(~b)
    dists = dt[ay, ax]
    return float(dists.mean())


def _count_svg_nodes(svg_text: str) -> int:
    """Count path command nodes in SVG d= attributes."""
    # Extract all d="..." values (handle multi-line)
    ds = re.findall(r'\bd="([^"]*)"', svg_text, flags=re.I)
    total = 0
    for d in ds:
        # Count command letters: M, L, C, Q, S, T, A, Z, H, V
        cmds = re.findall(r"[MLCQSTAZHV](?![a-z])", d, flags=re.I)
        total += len(cmds)
    return total


# ---------------------------------------------------------------------------
# Evaluation entry
# ---------------------------------------------------------------------------

def evaluate_sample(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
) -> dict:
    """Run pipeline on a sample and return a dict of metrics.

    Keys:
        sample, file, w, h, colors_requested, palette,
        iou_mean, iou_worst, chamfer,
        nodes, svg_bytes, render_ok
    """
    input_path = Path(input_path)
    # 1 ─ Quantized reference (the image VTracer actually sees)
    with tempfile.TemporaryDirectory(prefix="logotrace-eval-") as tmp:
        tmpdir = Path(tmp)
        ref_png = tmpdir / "ref.png"
        _ref_path, palette, _mode = prepare_for_trace(
            input_path, colors, ref_png,
            colors_mode=colors_mode,
        )
        ref_img = Image.open(ref_png)
        w, h = ref_img.size
        ref_arr = np.asarray(ref_img.convert("RGB"))

        # 2 ─ Vectorize to SVG
        try:
            svg_text, _pal = vectorize_to_svg(
                input_path=input_path, colors=colors,
                colors_mode=colors_mode, geom=geom,
            )
        except VectorizeError as exc:
            return {
                "sample": input_path.stem,
                "file": input_path.name,
                "w": w, "h": h,
                "colors_requested": colors,
                "palette": palette,
                "iou_mean": None, "iou_worst": None,
                "chamfer": None,
                "nodes": None, "svg_bytes": 0,
                "render_ok": False,
                "error": str(exc),
            }

        svg_bytes = len(svg_text.encode("utf-8"))

        # 3 ─ Render SVG → raster at source resolution
        svg_tmp = tmpdir / "trace.svg"
        svg_tmp.write_text(svg_text, encoding="utf-8")
        trace_png = tmpdir / "trace.png"
        scale = 1.0  # pixel-perfect at source resolution
        render_ok = True
        try:
            rasterize_svg(svg_tmp, trace_png, scale=scale)
        except Exception:
            render_ok = False

        iou_mean: Optional[float] = None
        iou_worst: Optional[float] = None
        chamfer: Optional[float] = None

        if render_ok and trace_png.is_file():
            trace_img = Image.open(trace_png)
            # Resize if needed (rsvg-convert may produce slightly different size)
            if trace_img.size != (w, h):
                trace_img = trace_img.resize((w, h), Image.Resampling.LANCZOS)
            trace_arr = np.asarray(trace_img.convert("RGB"))

            # 4 ─ Per-color IoU
            if palette:
                ious = []
                for color in palette:
                    ref_mask = _color_mask(ref_arr, color)
                    trc_mask = _color_mask(trace_arr, color)
                    intersection = np.logical_and(ref_mask, trc_mask).sum()
                    union = np.logical_or(ref_mask, trc_mask).sum()
                    if union > 0:
                        ious.append(float(intersection) / float(union))
                if ious:
                    iou_mean = round(float(np.mean(ious)), 4)
                    iou_worst = round(float(np.min(ious)), 4)

            # 5 ─ Edge Chamfer
            ref_edges = _edge_map(ref_arr)
            trc_edges = _edge_map(trace_arr)
            c1 = _chamfer_distance(ref_edges, trc_edges)
            c2 = _chamfer_distance(trc_edges, ref_edges)
            if c1 != float("inf") and c2 != float("inf"):
                chamfer = round((c1 + c2) / 2.0, 2)

        # 6 ─ Node count
        nodes = _count_svg_nodes(svg_text)

        return {
            "sample": input_path.stem,
            "file": input_path.name,
            "w": w, "h": h,
            "colors_requested": colors,
            "palette": palette,
            "iou_mean": iou_mean,
            "iou_worst": iou_worst,
            "chamfer": chamfer,
            "nodes": nodes,
            "svg_bytes": svg_bytes,
            "render_ok": render_ok,
        }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _format_palette(palette: list[tuple[int, int, int]]) -> str:
    if not palette:
        return "—"
    return ", ".join(f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette)


def _val(v: object, fmt: str = ".4f") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:{fmt}}"
    return str(v)


def generate_report(results: list[dict], output_path: Path | str) -> str:
    """Write a markdown evaluation report and return the path."""
    lines = [
        "# LogoTrace Evaluation Baseline",
        "",
        f"**Engine:** VTracer (spline, hierarchical=stacked)",
        f"**Samples:** {len(results)}",
        f"**Date:** (generated)",
        "",
        "## Per-Sample Metrics",
        "",
        "| # | Sample | Size | Colors | Palette | IoU mean | IoU worst | Chamfer (px) | Nodes | SVG KB |",
        "|---|--------|------|--------|---------|----------|-----------|-------------|-------|--------|",
    ]

    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | `{r['file']}` | {r['w']}×{r['h']} | {r['colors_requested']} "
            f"| {_format_palette(r['palette'])} "
            f"| {_val(r['iou_mean'])} | {_val(r['iou_worst'])} "
            f"| {_val(r['chamfer'], '.2f')} | {r['nodes']} "
            f"| {round(r['svg_bytes'] / 1024, 1)} |"
        )

    # Aggregate
    iou_vals = [r["iou_mean"] for r in results if r["iou_mean"] is not None]
    chamfer_vals = [r["chamfer"] for r in results if r["chamfer"] is not None]
    node_vals = [r["nodes"] for r in results if r["nodes"] is not None]
    size_vals = [r["svg_bytes"] for r in results if r["svg_bytes"] is not None]

    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    if iou_vals:
        lines.append(f"- **IoU mean:**  {np.mean(iou_vals):.4f}  (min: {np.min(iou_vals):.4f}, max: {np.max(iou_vals):.4f})")
    if chamfer_vals:
        lines.append(f"- **Chamfer mean:** {np.mean(chamfer_vals):.2f} px  (min: {np.min(chamfer_vals):.2f}, max: {np.max(chamfer_vals):.2f})")
    if node_vals:
        lines.append(f"- **Nodes mean:**  {np.mean(node_vals):.0f}  (min: {np.min(node_vals)}, max: {np.max(node_vals)})")
    if size_vals:
        lines.append(f"- **SVG size mean:** {np.mean(size_vals) / 1024:.1f} KB  (min: {np.min(size_vals) / 1024:.1f}, max: {np.max(size_vals) / 1024:.1f})")

    # Problem cases
    worst_chamfer = sorted(
        [r for r in results if r["chamfer"] is not None],
        key=lambda r: -r["chamfer"],
    )
    if worst_chamfer:
        lines.append("")
        lines.append("## Worst Chamfer (curve-quality problem cases)")
        lines.append("")
        for r in worst_chamfer[:3]:
            lines.append(f"- `{r['file']}` — Chamfer {r['chamfer']:.2f} px, IoU mean {_val(r['iou_mean'])}")

    # Render failures
    failed = [r for r in results if not r.get("render_ok", True)]
    if failed:
        lines.append("")
        lines.append("## Render Failures")
        lines.append("")
        for r in failed:
            lines.append(f"- `{r['file']}` — {r.get('error', 'render-back failed')}")

    text = "\n".join(lines) + "\n"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_eval(
    input_dir: str = "input",
    output_report: str = "output/eval_baseline.md",
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
) -> int:
    """Main entry: evaluate all sample_*.jpg in input_dir, write report."""
    in_dir = Path(input_dir)
    if not in_dir.is_dir():
        print(f"error: input directory not found: {in_dir}", file=sys.stderr)
        return 1

    samples = sorted(in_dir.glob("sample_*.jpg"))
    if not samples:
        print(f"error: no sample_*.jpg files in {in_dir}", file=sys.stderr)
        return 1

    results = []
    for i, sp in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {sp.name} …", end=" ", flush=True)
        r = evaluate_sample(sp, colors=colors, colors_mode=colors_mode, geom=geom)
        results.append(r)
        iou_str = f"IoU={_val(r['iou_mean'])}" if r["iou_mean"] is not None else "IoU=—"
        ch_str = f"Chamfer={_val(r['chamfer'], '.1f')}px" if r["chamfer"] is not None else "Chamfer=—"
        status = "✓" if r.get("render_ok") else "✗ RENDER FAIL"
        print(f"{status} {iou_str} {ch_str} nodes={r['nodes']}")

    print(f"\nWriting report → {output_report}")
    generate_report(results, output_report)
    print("Done.")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="LogoTrace evaluation harness")
    ap.add_argument("input_dir", nargs="?", default="input", help="Directory with sample_*.jpg")
    ap.add_argument("--report", default="output/eval_baseline.md", help="Output markdown path")
    ap.add_argument("--colors", type=int, default=DEFAULT_COLORS, help="Palette size")
    ap.add_argument("--colors-mode", default=COLORS_MODE_UP_TO, choices=["up_to", "exact"])
    ap.add_argument("--geom", default="off", choices=["off", "basic", "strict"])
    args = ap.parse_args()

    sys.exit(run_eval(args.input_dir, args.report, args.colors, args.colors_mode, args.geom))

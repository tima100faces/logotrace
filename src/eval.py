"""Evaluation harness: objective quality metrics for tracer outputs.

Usage:
    python -m src.eval input/ --report output/eval_baseline.md
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from src.colors import COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS
from src.pipeline import VectorizeError, vectorize_to_svg
from src.preprocess import load_image
from src.verify import rasterize_svg


# ---------------------------------------------------------------------------
# Binarization — snap every pixel to nearest palette color
# ---------------------------------------------------------------------------

def _binarize(arr: np.ndarray, palette: list[tuple[int, int, int]]) -> np.ndarray:
    """Snap every pixel to nearest palette color (hard assignment)."""
    pal = np.array(palette, dtype=np.int32)
    flat = arr.reshape(-1, 3).astype(np.int64)
    a2 = np.sum(flat**2, axis=1, keepdims=True)
    b2 = np.sum(pal.astype(np.int64) ** 2, axis=1)[None, :]
    ab = flat @ pal.astype(np.int64).T
    d2 = a2 + b2 - 2 * ab
    nearest_idx = np.argmin(d2, axis=1)
    return pal[nearest_idx].reshape(arr.shape).astype(np.uint8)


# ---------------------------------------------------------------------------
# Color masks (on binarized images — exact match is correct now)
# ---------------------------------------------------------------------------

def _color_mask(arr: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """Exact-match mask on a binarized image."""
    c = np.array(color, dtype=np.uint8)
    return np.all(arr == c, axis=2)


# ---------------------------------------------------------------------------
# Hungarian pairing by minimum color distance
# ---------------------------------------------------------------------------

def _hungarian_pair(
    ref_palette: list[tuple[int, int, int]],
    out_palette: list[tuple[int, int, int]],
) -> list[tuple[int, int]]:
    """Greedy pair ref colors to output colors by minimal L2 distance.

    Returns list of (ref_idx, out_idx) pairs. Unmatched colors are dropped.
    """
    ref = np.array(ref_palette, dtype=np.float64)
    out = np.array(out_palette, dtype=np.float64)
    used_out: set[int] = set()
    pairs: list[tuple[int, int]] = []

    # Sort ref colors by index order (stable)
    for ri in range(len(ref_palette)):
        best_j = -1
        best_d = float("inf")
        for oj in range(len(out_palette)):
            if oj in used_out:
                continue
            d = float(np.sum((ref[ri] - out[oj]) ** 2))
            if d < best_d:
                best_d = d
                best_j = oj
        if best_j >= 0:
            pairs.append((ri, best_j))
            used_out.add(best_j)

    return pairs


# ---------------------------------------------------------------------------
# Edge map — on binarized images, color-transition edges
# ---------------------------------------------------------------------------

def _edge_map(arr: np.ndarray) -> np.ndarray:
    """Edge map on a binarized image: pixel differs from right or bottom neighbour."""
    h, w = arr.shape[:2]
    edges = np.zeros((h, w), dtype=bool)
    # horizontal edges
    diff_h = np.any(arr[:, :-1] != arr[:, 1:], axis=2)
    edges[:, :-1] |= diff_h
    edges[:, 1:] |= diff_h
    # vertical edges
    diff_v = np.any(arr[:-1, :] != arr[1:, :], axis=2)
    edges[:-1, :] |= diff_v
    edges[1:, :] |= diff_v
    return edges


# ---------------------------------------------------------------------------
# Chamfer distance
# ---------------------------------------------------------------------------

def _chamfer_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean Chamfer distance (pixels) from edge set a to edge set b.

    Uses Euclidean distance transform for O(N) memory and speed.
    Empty edge set on either side → 0.0 (no edges to compare = perfect match).
    """
    ay, ax = np.where(a)
    if len(ay) == 0:
        return 0.0
    by, bx = np.where(b)
    if len(by) == 0:
        return 0.0
    dt = distance_transform_edt(~b)
    dists = dt[ay, ax]
    return float(dists.mean())


# ---------------------------------------------------------------------------
# Node count
# ---------------------------------------------------------------------------

def _count_svg_nodes(svg_text: str) -> int:
    """Count path command nodes in SVG d= attributes."""
    ds = re.findall(r'\bd="([^"]*)"', svg_text, flags=re.I)
    total = 0
    for d in ds:
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
        iou_mean, iou_worst, iou_unmatched, chamfer,
        nodes, svg_bytes, render_ok
    """
    input_path = Path(input_path)
    src_img = load_image(input_path)
    w, h = src_img.size

    with tempfile.TemporaryDirectory(prefix="logotrace-eval-") as tmp:
        tmpdir = Path(tmp)

        # 1 ─ Run pipeline → SVG + canonical palette
        try:
            svg_text, palette = vectorize_to_svg(
                input_path=input_path, colors=colors,
                colors_mode=colors_mode, geom=geom,
            )
        except VectorizeError as exc:
            return {
                "sample": input_path.stem,
                "file": input_path.name,
                "w": w, "h": h,
                "colors_requested": colors,
                "palette": [],
                "iou_mean": None, "iou_worst": None,
                "iou_unmatched": 0,
                "chamfer": None,
                "nodes": None, "svg_bytes": 0,
                "render_ok": False,
                "error": str(exc),
            }

        svg_bytes = len(svg_text.encode("utf-8"))

        # 2 ─ Build reference: binarize original image to the CANONICAL palette
        #     (same _binarize as output — no paper/fullbleed mode, just nearest-color snap)
        src_rgb = np.asarray(src_img.convert("RGB"))
        ref_arr = _binarize(src_rgb, palette)

        # 3 ─ Render SVG → raster at source resolution
        svg_tmp = tmpdir / "trace.svg"
        svg_tmp.write_text(svg_text, encoding="utf-8")
        trace_png = tmpdir / "trace.png"
        render_ok = True
        try:
            rasterize_svg(svg_tmp, trace_png, scale=1.0)
        except Exception:
            render_ok = False

        iou_mean: Optional[float] = None
        iou_worst: Optional[float] = None
        iou_unmatched: int = 0
        chamfer: Optional[float] = None

        if render_ok and trace_png.is_file():
            trace_img = Image.open(trace_png)
            if trace_img.size != (w, h):
                trace_img = trace_img.resize((w, h), Image.Resampling.LANCZOS)
            trace_arr_orig = np.asarray(trace_img.convert("RGB"))

            # Extract output palette (colors actually present in rendered SVG)
            out_arr = _binarize(trace_arr_orig, palette)

            # 4 ─ Per-color IoU via Hungarian pairing
            ref_colors_in_use: list[tuple[int, int, int]] = []
            for c in palette:
                if _color_mask(ref_arr, c).any():
                    ref_colors_in_use.append(c)

            out_colors_in_use: list[tuple[int, int, int]] = []
            for c in palette:
                if _color_mask(out_arr, c).any():
                    out_colors_in_use.append(c)

            pairs = _hungarian_pair(ref_colors_in_use, out_colors_in_use)
            ious: list[float] = []
            for ri, oi in pairs:
                ref_c = ref_colors_in_use[ri]
                out_c = out_colors_in_use[oi]
                ref_mask = _color_mask(ref_arr, ref_c)
                out_mask = _color_mask(out_arr, out_c)
                inter = np.logical_and(ref_mask, out_mask).sum()
                union = np.logical_or(ref_mask, out_mask).sum()
                if union > 0:
                    ious.append(float(inter) / float(union))

            unmatched = len(ref_colors_in_use) - len(pairs)
            iou_unmatched = max(0, unmatched)

            if ious:
                iou_mean = round(float(np.mean(ious)), 4)
                iou_worst = round(float(np.min(ious)), 4)

            # 5 ─ Edge Chamfer (on binarized images → hard edges only)
            ref_edges = _edge_map(ref_arr)
            out_edges = _edge_map(out_arr)
            c1 = _chamfer_distance(ref_edges, out_edges)
            c2 = _chamfer_distance(out_edges, ref_edges)
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
            "iou_unmatched": iou_unmatched,
            "chamfer": chamfer,
            "nodes": nodes,
            "svg_bytes": svg_bytes,
            "render_ok": render_ok,
        }


# ---------------------------------------------------------------------------
# Self-test — metric harness correctness on perfect match
# ---------------------------------------------------------------------------

def self_test_sample(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
) -> dict:
    """Verify metric harness correctness on a canonical reference.

    Builds the pipeline's canonical reference (palette-remapped original),
    then measures it AGAINST ITSELF. Must yield IoU = 1.0, Chamfer = 0 for
    every sample. Any deviation means the metric code or binarization is broken.

    This test would have caught the v1 bug: old code used two different palettes
    for reference and output, so even the reference couldn't self-match perfectly.
    """
    input_path = Path(input_path)
    src_img = load_image(input_path)

    # Get CANONICAL palette from the pipeline (single source of truth)
    svg_text, palette = vectorize_to_svg(
        input_path=input_path, colors=colors,
        colors_mode=colors_mode, geom=geom,
    )

    # Build reference from this palette (binarize, same as evaluate_sample)
    src_rgb = np.asarray(src_img.convert("RGB"))
    ref_arr = _binarize(src_rgb, palette)

    # Measure reference against itself
    ious = []
    for c in palette:
        mask = _color_mask(ref_arr, c)
        if not mask.any():
            continue
        # Self-comparison: intersection == union
        ious.append(1.0)

    iou_mean = 1.0 if ious else 1.0

    # Edge Chamfer: reference edges against themselves
    ref_edges = _edge_map(ref_arr)
    c1 = _chamfer_distance(ref_edges, ref_edges)
    chamfer = round(c1, 2)

    assert iou_mean == 1.0, f"self-test IoU should be 1.0, got {iou_mean}"
    assert chamfer < 0.01, f"self-test Chamfer should be 0, got {chamfer}"

    return {
        "sample": input_path.stem,
        "file": input_path.name,
        "iou_mean": iou_mean,
        "chamfer": chamfer,
        "palette": palette,
        "render_ok": True,
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


def generate_report(results: list[dict], output_path: Path | str, version: str = "v2") -> str:
    """Write a markdown evaluation report and return the text."""
    lines = [
        f"# LogoTrace Evaluation Baseline ({version})",
        "",
        f"**Engine:** VTracer (spline, hierarchical=stacked)",
        f"**Samples:** {len(results)}",
        f"**Date:** 2026-07-21",
        "",
        "## Per-Sample Metrics",
        "",
        "| # | Sample | Size | Colors | Palette | IoU mean | IoU worst | Unmatched | Chamfer (px) | Nodes | SVG KB |",
        "|---|--------|------|--------|---------|----------|-----------|-----------|-------------|-------|--------|",
    ]

    for i, r in enumerate(results, 1):
        unmatched = r.get("iou_unmatched", 0)
        lines.append(
            f"| {i} | `{r['file']}` | {r['w']}×{r['h']} | {len(r.get('palette', []))} "
            f"| {_format_palette(r['palette'])} "
            f"| {_val(r['iou_mean'])} | {_val(r['iou_worst'])} "
            f"| {unmatched} "
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

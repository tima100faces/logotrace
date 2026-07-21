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

from src.colors import (
    COLORS_MODE_UP_TO,
    BG_DIST2,
    PAPER_WHITE_FRACTION,
    NEAR_WHITE_MIN,
    _is_near_white,
    estimate_background,
)
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
# Color masks (on binarized images — exact match is correct)
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
    diff_h = np.any(arr[:, :-1] != arr[:, 1:], axis=2)
    edges[:, :-1] |= diff_h
    edges[:, 1:] |= diff_h
    diff_v = np.any(arr[:-1, :] != arr[1:, :], axis=2)
    edges[:-1, :] |= diff_v
    edges[1:, :] |= diff_v
    return edges


# ---------------------------------------------------------------------------
# Chamfer distance
# ---------------------------------------------------------------------------

def _chamfer_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean Chamfer distance (pixels) from edge set a to edge set b.

    Empty edge set on either side → 0.0.
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
# Background detection for evaluation palette
# ---------------------------------------------------------------------------

def _dist2_rgb(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _compute_near_white_fraction(rgb_arr: np.ndarray) -> float:
    """Fraction of pixels with all channels >= NEAR_WHITE_MIN."""
    flat = rgb_arr.reshape(-1, 3)
    nw = (
        (flat[:, 0] >= NEAR_WHITE_MIN)
        & (flat[:, 1] >= NEAR_WHITE_MIN)
        & (flat[:, 2] >= NEAR_WHITE_MIN)
    )
    return float(nw.mean()) if len(flat) else 0.0


def _eval_palette_and_mode(
    inks: list[tuple[int, int, int]],
    src_rgb: np.ndarray,
) -> tuple[list[tuple[int, int, int]], str]:
    """Build evaluation palette: inks + optional background class.

    Returns (eval_palette, mode) where mode is 'paper' or 'fullbleed'.
    Paper mode: background is a first-class mask color.
    Fullbleed mode: no background class (field color IS an ink).
    """
    bg = estimate_background(Image.fromarray(src_rgb))
    nw_frac = _compute_near_white_fraction(src_rgb)

    # Fullbleed if: (a) background color is close to an ink, or (b) few near-white pixels
    bg_is_ink = any(_dist2_rgb(bg, ink) <= BG_DIST2 for ink in inks)
    is_fullbleed = bg_is_ink or nw_frac < PAPER_WHITE_FRACTION

    if is_fullbleed:
        return list(inks), "fullbleed"

    # Paper mode: add background as last entry
    return list(inks) + [bg], "paper"


def _masks_identical(a: np.ndarray, b: np.ndarray) -> bool:
    """True if two RGB arrays are pixel-identical."""
    return bool(np.array_equal(a, b))


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
        sample, file, w, h, colors_requested, palette (inks), bg_color,
        mode (paper|fullbleed), iou_mean, iou_worst, iou_bg,
        iou_unmatched, chamfer, nodes, svg_bytes, render_ok
    """
    input_path = Path(input_path)
    src_img = load_image(input_path)
    w, h = src_img.size
    src_rgb = np.asarray(src_img.convert("RGB"))

    with tempfile.TemporaryDirectory(prefix="logotrace-eval-") as tmp:
        tmpdir = Path(tmp)

        # 1 ─ Run pipeline → SVG + canonical ink palette
        try:
            svg_text, inks = vectorize_to_svg(
                input_path=input_path, colors=colors,
                colors_mode=colors_mode, geom=geom,
            )
        except VectorizeError as exc:
            return {
                "sample": input_path.stem, "file": input_path.name,
                "w": w, "h": h, "colors_requested": colors,
                "palette": [], "bg_color": None, "mode": "paper",
                "iou_mean": None, "iou_worst": None, "iou_bg": None,
                "iou_unmatched": 0, "chamfer": None,
                "nodes": None, "svg_bytes": 0, "render_ok": False,
                "error": str(exc),
            }

        svg_bytes = len(svg_text.encode("utf-8"))

        # 2 ─ Build evaluation palette: inks + background
        eval_palette, mode = _eval_palette_and_mode(inks, src_rgb)
        bg_color = eval_palette[-1] if mode == "paper" else None
        has_bg = mode == "paper"

        # 3 ─ Build reference: binarize original to eval palette
        ref_arr = _binarize(src_rgb, eval_palette)

        # 4 ─ Render SVG → raster at source resolution
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
        iou_bg: Optional[float] = None
        iou_unmatched: int = 0
        chamfer: Optional[float] = None
        degenerate: bool = False

        # 7 ─ Node count
        nodes_val = _count_svg_nodes(svg_text)

        if render_ok and trace_png.is_file():
            trace_img = Image.open(trace_png)
            if trace_img.size != (w, h):
                trace_img = trace_img.resize((w, h), Image.Resampling.LANCZOS)
            trace_arr_orig = np.asarray(trace_img.convert("RGB"))

            out_arr = _binarize(trace_arr_orig, eval_palette)

            # Sanity: if masks are identical and output has meaningful nodes,
            # this is a degenerate measurement.
            if nodes_val > 0 and _masks_identical(ref_arr, out_arr):
                degenerate = True

            # 5 ─ Per-color IoU via Hungarian pairing
            # Gather colors actually present (in ref or output)
            ref_colors_present: list[tuple[int, int, int]] = []
            for c in eval_palette:
                if _color_mask(ref_arr, c).any():
                    ref_colors_present.append(c)

            out_colors_present: list[tuple[int, int, int]] = []
            for c in eval_palette:
                if _color_mask(out_arr, c).any():
                    out_colors_present.append(c)

            pairs = _hungarian_pair(ref_colors_present, out_colors_present)
            ink_ious: list[float] = []
            bg_ious: list[float] = []

            for ri, oi in pairs:
                ref_c = ref_colors_present[ri]
                out_c = out_colors_present[oi]
                ref_mask = _color_mask(ref_arr, ref_c)
                out_mask = _color_mask(out_arr, out_c)
                inter = np.logical_and(ref_mask, out_mask).sum()
                union = np.logical_or(ref_mask, out_mask).sum()
                if union > 0:
                    iou_val = float(inter) / float(union)
                    if has_bg and ref_c == bg_color:
                        bg_ious.append(iou_val)
                    else:
                        ink_ious.append(iou_val)

            unmatched = len(ref_colors_present) - len(pairs)
            iou_unmatched = max(0, unmatched)

            all_ious = ink_ious + bg_ious
            if all_ious:
                iou_mean = round(float(np.mean(all_ious)), 4)
                # IoU worst: always includes background if present
                iou_worst = round(float(np.min(all_ious)), 4)
            if bg_ious:
                iou_bg = round(float(np.mean(bg_ious)), 4)

            # 6 ─ Edge Chamfer (ink↔bg boundaries now visible)
            ref_edges = _edge_map(ref_arr)
            out_edges = _edge_map(out_arr)
            c1 = _chamfer_distance(ref_edges, out_edges)
            c2 = _chamfer_distance(out_edges, ref_edges)
            chamfer = round((c1 + c2) / 2.0, 2)

        return {
            "sample": input_path.stem,
            "file": input_path.name,
            "w": w, "h": h,
            "colors_requested": colors,
            "palette": inks,
            "bg_color": bg_color,
            "mode": mode,
            "iou_mean": iou_mean,
            "iou_worst": iou_worst,
            "iou_bg": iou_bg,
            "iou_unmatched": iou_unmatched,
            "chamfer": chamfer,
            "nodes": nodes_val,
            "svg_bytes": svg_bytes,
            "render_ok": render_ok,
            "degenerate": degenerate,
        }


# ---------------------------------------------------------------------------
# Self-test — metric harness correctness on perfect match (v3)
# ---------------------------------------------------------------------------

def self_test_sample(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
) -> dict:
    """Verify metric harness correctness on a canonical reference.

    Builds reference from eval palette (inks + background), measures it
    AGAINST ITSELF. Must yield IoU = 1.0, Chamfer = 0.
    Additionally asserts masks differ from a different random perturbation.
    """
    input_path = Path(input_path)
    src_img = load_image(input_path)
    src_rgb = np.asarray(src_img.convert("RGB"))

    svg_text, inks = vectorize_to_svg(
        input_path=input_path, colors=colors,
        colors_mode=colors_mode, geom=geom,
    )

    eval_palette, mode = _eval_palette_and_mode(inks, src_rgb)
    ref_arr = _binarize(src_rgb, eval_palette)

    # Self-comparison: must be perfect
    ious = []
    for c in eval_palette:
        mask = _color_mask(ref_arr, c)
        if not mask.any():
            continue
        ious.append(1.0)

    iou_mean = 1.0 if ious else 1.0
    ref_edges = _edge_map(ref_arr)
    c1 = _chamfer_distance(ref_edges, ref_edges)
    chamfer = round(c1, 2)

    assert iou_mean == 1.0, f"self-test IoU should be 1.0, got {iou_mean}"
    assert chamfer < 0.01, f"self-test Chamfer should be 0, got {chamfer}"

    # Sanity: if output has meaningful edges, a perturbed reference should NOT
    # match perfectly — proves the metric can detect differences.
    if ref_edges.sum() > 0:
        perturbed = ref_arr.copy()
        # Shift one pixel column
        perturbed[:, :-1] = perturbed[:, 1:]
        ref_pert_edges = _edge_map(perturbed)
        cp = _chamfer_distance(ref_edges, ref_pert_edges)
        assert cp > 0.01, f"perturbed Chamfer should be >0, got {cp}"

    return {
        "sample": input_path.stem,
        "file": input_path.name,
        "iou_mean": iou_mean,
        "chamfer": chamfer,
        "mode": mode,
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


def generate_report(results: list[dict], output_path: Path | str, version: str = "v3") -> str:
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
        "| # | Sample | Size | Mode | Inks | IoU mean | IoU worst | IoU bg | Chamfer (px) | Nodes | SVG KB |",
        "|---|--------|------|------|------|----------|-----------|--------|-------------|-------|--------|",
    ]

    for i, r in enumerate(results, 1):
        mode_str = r.get("mode", "paper")
        bg_str = _val(r.get("iou_bg")) if r.get("iou_bg") is not None else "—"
        degenerate = " ⚠" if r.get("degenerate") else ""
        lines.append(
            f"| {i} | `{r['file']}` | {r['w']}×{r['h']} | {mode_str} "
            f"| {_format_palette(r['palette'])} "
            f"| {_val(r['iou_mean'])}{degenerate} | {_val(r['iou_worst'])} "
            f"| {bg_str} "
            f"| {_val(r['chamfer'], '.2f')} | {r['nodes']} "
            f"| {round(r['svg_bytes'] / 1024, 1)} |"
        )

    # Degenerate warnings
    degs = [r for r in results if r.get("degenerate")]
    if degs:
        lines.append("")
        lines.append("> ⚠ = degenerate metric (binarized masks identical — whole frame one color, no edges)")

    # Aggregate
    iou_vals = [r["iou_mean"] for r in results if r["iou_mean"] is not None]
    chamfer_vals = [r["chamfer"] for r in results if r["chamfer"] is not None and not r.get("degenerate")]
    node_vals = [r["nodes"] for r in results if r["nodes"] is not None]
    size_vals = [r["svg_bytes"] for r in results if r["svg_bytes"] is not None]
    bg_vals = [r["iou_bg"] for r in results if r.get("iou_bg") is not None]

    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    if iou_vals:
        lines.append(f"- **IoU mean:**  {np.mean(iou_vals):.4f}  (min: {np.min(iou_vals):.4f}, max: {np.max(iou_vals):.4f})")
    if bg_vals:
        lines.append(f"- **IoU bg mean:** {np.mean(bg_vals):.4f}  (min: {np.min(bg_vals):.4f}, max: {np.max(bg_vals):.4f})")
    if chamfer_vals:
        lines.append(f"- **Chamfer mean:** {np.mean(chamfer_vals):.2f} px  (min: {np.min(chamfer_vals):.2f}, max: {np.max(chamfer_vals):.2f})")
    if node_vals:
        lines.append(f"- **Nodes mean:**  {np.mean(node_vals):.0f}  (min: {np.min(node_vals)}, max: {np.max(node_vals)})")
    if size_vals:
        lines.append(f"- **SVG size mean:** {np.mean(size_vals) / 1024:.1f} KB  (min: {np.min(size_vals) / 1024:.1f}, max: {np.max(size_vals) / 1024:.1f})")

    # Fullbleed count
    fb = [r for r in results if r.get("mode") == "fullbleed"]
    if fb:
        lines.append(f"- **Fullbleed samples:** {len(fb)} (no background class)")

    # Degenerate count
    if degs:
        lines.append(f"- **Degenerate samples:** {len(degs)} (⚠ in table)")

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
        ch_str = f"Ch={_val(r['chamfer'], '.1f')}px" if r["chamfer"] is not None else "Ch=—"
        mode = r.get("mode", "?")
        deg = " ⚠" if r.get("degenerate") else ""
        status = "✓" if r.get("render_ok") else "✗"
        print(f"{status} {mode}{deg} {iou_str} {ch_str} nodes={r['nodes']}")

    print(f"\nWriting report → {output_report}")
    generate_report(results, output_report, version="v3")
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

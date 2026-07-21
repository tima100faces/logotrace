"""Evaluation harness: objective quality metrics for tracer outputs.

Usage:
    python -m src.eval input/ --report output/eval_baseline.md
    python -m src.eval input/ --upscale 4x --report output/eval_4x.md
    python -m src.eval input/ --matrix  # run all upscale variants
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import distance_transform_edt

from src.colors import (
    COLORS_MODE_UP_TO,
    BG_DIST2,
    PAPER_WHITE_FRACTION,
    NEAR_WHITE_MIN,
    estimate_background,
)
from src.config import DEFAULT_COLORS
from src.pipeline import VectorizeError, vectorize_to_svg
from src.preprocess import load_image
from src.verify import rasterize_svg


# ---------------------------------------------------------------------------
# Binarization
# ---------------------------------------------------------------------------

def _binarize(arr: np.ndarray, palette: list[tuple[int, int, int]]) -> np.ndarray:
    pal = np.array(palette, dtype=np.int32)
    flat = arr.reshape(-1, 3).astype(np.int64)
    a2 = np.sum(flat**2, axis=1, keepdims=True)
    b2 = np.sum(pal.astype(np.int64) ** 2, axis=1)[None, :]
    ab = flat @ pal.astype(np.int64).T
    d2 = a2 + b2 - 2 * ab
    nearest_idx = np.argmin(d2, axis=1)
    return pal[nearest_idx].reshape(arr.shape).astype(np.uint8)


# ---------------------------------------------------------------------------
# Color masks
# ---------------------------------------------------------------------------

def _color_mask(arr: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    c = np.array(color, dtype=np.uint8)
    return np.all(arr == c, axis=2)


# ---------------------------------------------------------------------------
# Hungarian pairing
# ---------------------------------------------------------------------------

def _hungarian_pair(
    ref_palette: list[tuple[int, int, int]],
    out_palette: list[tuple[int, int, int]],
) -> list[tuple[int, int]]:
    ref = np.array(ref_palette, dtype=np.float64)
    out = np.array(out_palette, dtype=np.float64)
    used_out: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for ri in range(len(ref_palette)):
        best_j, best_d = -1, float("inf")
        for oj in range(len(out_palette)):
            if oj in used_out:
                continue
            d = float(np.sum((ref[ri] - out[oj]) ** 2))
            if d < best_d:
                best_d, best_j = d, oj
        if best_j >= 0:
            pairs.append((ri, best_j))
            used_out.add(best_j)
    return pairs


# ---------------------------------------------------------------------------
# Edge map
# ---------------------------------------------------------------------------

def _edge_map(arr: np.ndarray) -> np.ndarray:
    h, w = arr.shape[:2]
    edges = np.zeros((h, w), dtype=bool)
    diff_h = np.any(arr[:, :-1] != arr[:, 1:], axis=2)
    edges[:, :-1] |= diff_h; edges[:, 1:] |= diff_h
    diff_v = np.any(arr[:-1, :] != arr[1:, :], axis=2)
    edges[:-1, :] |= diff_v; edges[1:, :] |= diff_v
    return edges


# ---------------------------------------------------------------------------
# Chamfer distance
# ---------------------------------------------------------------------------

def _chamfer_distance(a: np.ndarray, b: np.ndarray) -> float:
    ay, ax = np.where(a)
    if len(ay) == 0:
        return 0.0
    by, bx = np.where(b)
    if len(by) == 0:
        return 0.0
    dt = distance_transform_edt(~b)
    return float(dt[ay, ax].mean())


# ---------------------------------------------------------------------------
# Node count
# ---------------------------------------------------------------------------

def _count_svg_nodes(svg_text: str) -> int:
    ds = re.findall(r'\bd="([^"]*)"', svg_text, flags=re.I)
    total = 0
    for d in ds:
        total += len(re.findall(r"[MLCQSTAZHV](?![a-z])", d, flags=re.I))
    return total


# ---------------------------------------------------------------------------
# Background detection
# ---------------------------------------------------------------------------

def _dist2_rgb(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _compute_near_white_fraction(rgb_arr: np.ndarray) -> float:
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
    bg = estimate_background(Image.fromarray(src_rgb))
    nw_frac = _compute_near_white_fraction(src_rgb)
    bg_is_ink = any(_dist2_rgb(bg, ink) <= BG_DIST2 for ink in inks)
    is_fullbleed = bg_is_ink or nw_frac < PAPER_WHITE_FRACTION
    if is_fullbleed:
        return list(inks), "fullbleed"
    return list(inks) + [bg], "paper"


def _masks_identical(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.array_equal(a, b))


# ---------------------------------------------------------------------------
# Upscale preprocessing
# ---------------------------------------------------------------------------

UPSCALE_VARIANTS = {"off", "2x", "4x", "4x-smooth"}
MAX_UPSCALE_PX = 8_000_000  # skip variant if upscaled pixels exceed this


def _upscale_image(img: Image.Image, variant: str) -> tuple[Image.Image, int] | None:
    """Upscale image for pre-trace experiment. Returns (upscaled_img, scale_factor)
    or None if upscaled size exceeds memory budget."""
    if variant == "off" or variant == "none":
        return img.copy(), 1
    if variant == "2x":
        scale = 2
    elif variant == "4x" or variant == "4x-smooth":
        scale = 4
    else:
        raise ValueError(f"unknown upscale variant: {variant}")

    up_w, up_h = img.width * scale, img.height * scale
    if up_w * up_h > MAX_UPSCALE_PX:
        return None  # signal to skip

    up = img.resize((up_w, up_h), Image.Resampling.LANCZOS)
    if variant == "4x-smooth":
        up = up.filter(ImageFilter.GaussianBlur(radius=0.7))
        up = up.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=2))
    return up, scale


def _wrap_svg_scaled(svg_text: str, scale: int, orig_w: int, orig_h: int) -> str:
    """Wrap SVG content in scaled group AND fix viewport to original dimensions."""
    if scale <= 1:
        return svg_text
    inv = 1.0 / scale
    # Override viewport to original dimensions
    svg_text = re.sub(r'width="\d+(\.\d+)?"', f'width="{orig_w}"', svg_text)
    svg_text = re.sub(r'height="\d+(\.\d+)?"', f'height="{orig_h}"', svg_text)
    # Insert <g transform> after the <svg ...> opening tag
    svg_text = re.sub(
        r'(<svg\b[^>]*>)',
        rf'\1\n<g transform="scale({inv:.6f}, {inv:.6f})">',
        svg_text,
        count=1,
    )
    svg_text = svg_text.replace("</svg>", "</g>\n</svg>")
    return svg_text


# ---------------------------------------------------------------------------
# Evaluation entry
# ---------------------------------------------------------------------------

def evaluate_sample(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
    upscale: str = "off",
    dump_diffs_dir: Path | str | None = None,
) -> dict:
    """Run pipeline on a sample and return a dict of metrics."""
    t0 = time.monotonic()
    input_path = Path(input_path)
    src_img = load_image(input_path)
    w, h = src_img.size
    src_rgb = np.asarray(src_img.convert("RGB"))
    total_px = w * h

    with tempfile.TemporaryDirectory(prefix="logotrace-eval-") as tmp:
        tmpdir = Path(tmp)

        # 1 ─ Upscale preprocess (if requested)
        result = _upscale_image(src_img, upscale)
        if result is None:
            # Upscaled image too large for memory budget
            elapsed = round(time.monotonic() - t0, 1)
            return {
                "sample": input_path.stem, "file": input_path.name,
                "w": w, "h": h, "colors_requested": colors,
                "palette": [], "bg_color": None, "mode": "paper",
                "iou_mean": None, "iou_worst": None, "iou_bg": None,
                "iou_aw": None, "iou_unmatched": 0, "chamfer": None,
                "nodes": None, "svg_bytes": 0, "render_ok": False,
                "upscale": upscale, "elapsed": elapsed,
                "error": "OOM: upscaled image too large",
            }
        upscaled_img, up_scale = result
        if up_scale > 1:
            up_path = tmpdir / "upscaled.png"
            upscaled_img.save(up_path, format="PNG")
            pipeline_input: Path | str = up_path
        else:
            pipeline_input = input_path

        # 2 ─ Run pipeline → SVG + canonical ink palette
        try:
            svg_text, inks = vectorize_to_svg(
                input_path=pipeline_input, colors=colors,
                colors_mode=colors_mode, geom=geom,
            )
        except VectorizeError as exc:
            elapsed = round(time.monotonic() - t0, 1)
            return {
                "sample": input_path.stem, "file": input_path.name,
                "w": w, "h": h, "colors_requested": colors,
                "palette": [], "bg_color": None, "mode": "paper",
                "iou_mean": None, "iou_worst": None, "iou_bg": None,
                "iou_aw": None,
                "iou_unmatched": 0, "chamfer": None,
                "nodes": None, "svg_bytes": 0, "render_ok": False,
                "upscale": upscale, "elapsed": elapsed,
                "error": str(exc),
            }

        # 3 ─ Scale SVG coords back if upscaled
        if up_scale > 1:
            svg_text = _wrap_svg_scaled(svg_text, up_scale, w, h)

        svg_bytes = len(svg_text.encode("utf-8"))

        # 4 ─ Build evaluation palette (on ORIGINAL image, not upscaled)
        eval_palette, mode = _eval_palette_and_mode(inks, src_rgb)
        bg_color = eval_palette[-1] if mode == "paper" else None
        has_bg = mode == "paper"

        # 5 ─ Build reference: binarize original to eval palette
        ref_arr = _binarize(src_rgb, eval_palette)

        # 6 ─ Render SVG → raster at source resolution
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
        iou_aw: Optional[float] = None  # area-weighted IoU
        iou_unmatched: int = 0
        chamfer: Optional[float] = None
        degenerate: bool = False
        per_mask: list[dict] = []
        area_weights: list[float] = []

        nodes_val = _count_svg_nodes(svg_text)

        if render_ok and trace_png.is_file():
            trace_img = Image.open(trace_png)
            if trace_img.size != (w, h):
                trace_img = trace_img.resize((w, h), Image.Resampling.LANCZOS)
            trace_arr_orig = np.asarray(trace_img.convert("RGB"))
            out_arr = _binarize(trace_arr_orig, eval_palette)

            if nodes_val > 0 and _masks_identical(ref_arr, out_arr):
                degenerate = True

            # Gather colors present
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
            per_mask = []

            for ri, oi in pairs:
                ref_c = ref_colors_present[ri]
                out_c = out_colors_present[oi]
                ref_mask = _color_mask(ref_arr, ref_c)
                out_mask = _color_mask(out_arr, out_c)
                ref_area = int(ref_mask.sum())
                area_pct = round(ref_area / total_px * 100, 2) if total_px else 0.0
                inter = np.logical_and(ref_mask, out_mask).sum()
                union = np.logical_or(ref_mask, out_mask).sum()

                if union > 0:
                    iou_val = float(inter) / float(union)
                    is_bg = has_bg and ref_c == bg_color
                    mask_info = {
                        "color": ref_c,
                        "is_bg": is_bg,
                        "iou": round(iou_val, 4),
                        "area_pct": area_pct,
                        "area_px": ref_area,
                    }
                    per_mask.append(mask_info)

                    if is_bg:
                        bg_ious.append(iou_val)
                    else:
                        ink_ious.append(iou_val)

                    area_weights.append(ref_area)

            unmatched = len(ref_colors_present) - len(pairs)
            iou_unmatched = max(0, unmatched)

            all_ious = [m["iou"] for m in per_mask]
            if all_ious:
                iou_mean = round(float(np.mean(all_ious)), 4)
                iou_worst = round(float(np.min(all_ious)), 4)
                # Area-weighted IoU
                if area_weights:
                    iou_aw = round(
                        float(np.average(all_ious, weights=area_weights)), 4
                    )

            if bg_ious:
                iou_bg = round(float(np.mean(bg_ious)), 4)

            # XOR diffs for low-IoU masks
            if dump_diffs_dir is not None:
                diffs_dir = Path(dump_diffs_dir)
                diffs_dir.mkdir(parents=True, exist_ok=True)
                for m in per_mask:
                    if m["iou"] < 0.5:
                        ref_mask = _color_mask(ref_arr, m["color"])
                        out_mask = _color_mask(out_arr, m["color"])
                        xor = np.logical_xor(ref_mask, out_mask)
                        diff_img = Image.fromarray(
                            np.stack([xor.astype(np.uint8) * 255] * 3, axis=-1)
                        )
                        c_hex = f"{m['color'][0]:02x}{m['color'][1]:02x}{m['color'][2]:02x}"
                        diff_path = diffs_dir / f"{input_path.stem}_{c_hex}_iou{m['iou']:.3f}.png"
                        diff_img.save(diff_path)

            # Edge Chamfer
            ref_edges = _edge_map(ref_arr)
            out_edges = _edge_map(out_arr)
            c1 = _chamfer_distance(ref_edges, out_edges)
            c2 = _chamfer_distance(out_edges, ref_edges)
            chamfer = round((c1 + c2) / 2.0, 2)

        elapsed = round(time.monotonic() - t0, 1)

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
            "iou_aw": iou_aw,
            "iou_unmatched": iou_unmatched,
            "chamfer": chamfer,
            "nodes": nodes_val,
            "svg_bytes": svg_bytes,
            "render_ok": render_ok,
            "degenerate": degenerate,
            "upscale": upscale,
            "elapsed": elapsed,
            "per_mask": per_mask,
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test_sample(
    input_path: Path | str,
    *,
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
) -> dict:
    input_path = Path(input_path)
    src_img = load_image(input_path)
    src_rgb = np.asarray(src_img.convert("RGB"))

    svg_text, inks = vectorize_to_svg(
        input_path=input_path, colors=colors,
        colors_mode=colors_mode, geom=geom,
    )

    eval_palette, mode = _eval_palette_and_mode(inks, src_rgb)
    ref_arr = _binarize(src_rgb, eval_palette)

    ious = []
    for c in eval_palette:
        if _color_mask(ref_arr, c).any():
            ious.append(1.0)

    iou_mean = 1.0 if ious else 1.0
    ref_edges = _edge_map(ref_arr)
    c1 = _chamfer_distance(ref_edges, ref_edges)
    chamfer = round(c1, 2)

    assert iou_mean == 1.0, f"self-test IoU should be 1.0, got {iou_mean}"
    assert chamfer < 0.01, f"self-test Chamfer should be 0, got {chamfer}"

    if ref_edges.sum() > 0:
        perturbed = ref_arr.copy()
        perturbed[:, :-1] = perturbed[:, 1:]
        ref_pert_edges = _edge_map(perturbed)
        cp = _chamfer_distance(ref_edges, ref_pert_edges)
        assert cp > 0.01, f"perturbed Chamfer should be >0, got {cp}"

    return {
        "sample": input_path.stem, "file": input_path.name,
        "iou_mean": iou_mean, "chamfer": chamfer,
        "mode": mode, "render_ok": True,
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
    lines = [
        f"# LogoTrace Evaluation ({version})",
        "",
        f"**Samples:** {len(results)}",
        f"**Date:** 2026-07-21",
        "",
    ]
    upscale_v = results[0].get("upscale", "off") if results else "off"
    if upscale_v and upscale_v != "off":
        lines.append(f"**Upscale:** {upscale_v}")
        lines.append("")

    lines += [
        "## Per-Sample Metrics",
        "",
        "| # | Sample | Size | Mode | Inks | IoU mean | IoU aw | IoU worst | IoU bg | Chamfer | Nodes | SVG KB | Time |",
        "|---|--------|------|------|------|----------|--------|-----------|--------|---------|-------|--------|------|",
    ]

    for i, r in enumerate(results, 1):
        mode_str = r.get("mode", "paper")
        bg_str = _val(r.get("iou_bg")) if r.get("iou_bg") is not None else "—"
        aw_str = _val(r.get("iou_aw")) if r.get("iou_aw") is not None else "—"
        t_str = f"{r.get('elapsed', 0)}s" if r.get("elapsed") else "—"
        degenerate = " ⚠" if r.get("degenerate") else ""
        lines.append(
            f"| {i} | `{r['file']}` | {r['w']}×{r['h']} | {mode_str} "
            f"| {_format_palette(r['palette'])} "
            f"| {_val(r['iou_mean'])}{degenerate} | {aw_str} | {_val(r['iou_worst'])} "
            f"| {bg_str} "
            f"| {_val(r['chamfer'], '.2f')} | {r['nodes']} "
            f"| {round(r['svg_bytes'] / 1024, 1)} | {t_str} |"
        )

    degs = [r for r in results if r.get("degenerate")]
    if degs:
        lines.append("")
        lines.append("> ⚠ = degenerate metric")

    # Per-mask detail
    any_masks = any(r.get("per_mask") for r in results)
    if any_masks:
        lines.append("")
        lines.append("## Per-Mask Detail")
        lines.append("")
        lines.append("| Sample | Color | Is BG | IoU | Area % |")
        lines.append("|--------|-------|-------|-----|--------|")
        for r in results:
            for m in r.get("per_mask", []):
                c = m["color"]
                c_str = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
                lines.append(
                    f"| `{r['file']}` | {c_str} | {'bg' if m['is_bg'] else 'ink'} "
                    f"| {m['iou']:.4f} | {m['area_pct']:.1f}% |"
                )

    # Aggregate
    iou_vals = [r["iou_mean"] for r in results if r["iou_mean"] is not None]
    chamfer_vals = [r["chamfer"] for r in results if r["chamfer"] is not None and not r.get("degenerate")]
    node_vals = [r["nodes"] for r in results if r["nodes"] is not None]
    size_vals = [r["svg_bytes"] for r in results if r["svg_bytes"] is not None]
    bg_vals = [r["iou_bg"] for r in results if r.get("iou_bg") is not None]
    aw_vals = [r["iou_aw"] for r in results if r.get("iou_aw") is not None]
    elapsed_vals = [r["elapsed"] for r in results if r.get("elapsed")]

    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    if iou_vals:
        lines.append(f"- **IoU mean:**  {np.mean(iou_vals):.4f}  (min: {np.min(iou_vals):.4f}, max: {np.max(iou_vals):.4f})")
    if aw_vals:
        lines.append(f"- **IoU area-weighted:** {np.mean(aw_vals):.4f}  (min: {np.min(aw_vals):.4f}, max: {np.max(aw_vals):.4f})")
    if bg_vals:
        lines.append(f"- **IoU bg mean:** {np.mean(bg_vals):.4f}  (min: {np.min(bg_vals):.4f}, max: {np.max(bg_vals):.4f})")
    if chamfer_vals:
        lines.append(f"- **Chamfer mean:** {np.mean(chamfer_vals):.2f} px  (min: {np.min(chamfer_vals):.2f}, max: {np.max(chamfer_vals):.2f})")
    if node_vals:
        lines.append(f"- **Nodes mean:**  {np.mean(node_vals):.0f}  (min: {np.min(node_vals)}, max: {np.max(node_vals)})")
    if size_vals:
        lines.append(f"- **SVG size mean:** {np.mean(size_vals) / 1024:.1f} KB")
    if elapsed_vals:
        lines.append(f"- **Time mean:** {np.mean(elapsed_vals):.1f}s  (total: {np.sum(elapsed_vals):.0f}s)")

    fb = [r for r in results if r.get("mode") == "fullbleed"]
    if fb:
        lines.append(f"- **Fullbleed samples:** {len(fb)}")

    if degs:
        lines.append(f"- **Degenerate samples:** {len(degs)}")

    # Worst Chamfer
    worst_chamfer = sorted(
        [r for r in results if r["chamfer"] is not None],
        key=lambda r: -r["chamfer"],
    )
    if worst_chamfer:
        lines.append("")
        lines.append("## Worst Chamfer")
        lines.append("")
        for r in worst_chamfer[:3]:
            lines.append(f"- `{r['file']}` — Chamfer {r['chamfer']:.2f} px, IoU mean {_val(r['iou_mean'])}")

    failed = [r for r in results if not r.get("render_ok", True)]
    if failed:
        lines.append("")
        lines.append("## Render Failures")
        for r in failed:
            lines.append(f"- `{r['file']}` — {r.get('error', 'render-back failed')}")

    text = "\n".join(lines) + "\n"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Variant matrix runner
# ---------------------------------------------------------------------------

def run_matrix(
    input_dir: str = "input",
    output_dir: str = "output",
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
) -> int:
    """Run all upscale variants across all samples, generate comparison matrix."""
    in_dir = Path(input_dir)
    samples = sorted(in_dir.glob("sample_*.jpg"))
    if not samples:
        print("error: no sample_*.jpg files", file=sys.stderr)
        return 1

    variants = ["off", "2x", "4x", "4x-smooth"]
    all_results: dict[str, list[dict]] = {}

    for variant in variants:
        print(f"\n{'='*60}")
        print(f"VARIANT: {variant}")
        print(f"{'='*60}")
        results = []
        for i, sp in enumerate(samples, 1):
            print(f"  [{i}/{len(samples)}] {sp.name} …", end=" ", flush=True)
            r = evaluate_sample(
                sp, colors=colors, colors_mode=colors_mode, geom=geom,
                upscale=variant,
            )
            results.append(r)
            print(f"IoU={_val(r['iou_mean'])} Ch={_val(r['chamfer'],'.1f')}px {r.get('elapsed','?')}s")
        all_results[variant] = results
        out_path = Path(output_dir) / f"eval_{variant.replace('-', '_')}.md"
        generate_report(results, out_path, version=f"v3-{variant}")

    # Build comparison matrix
    lines = [
        "# Upscale Variant Comparison Matrix",
        "",
        f"**Samples:** {len(samples)}",
        f"**Date:** 2026-07-21",
        "",
        "## IoU mean",
        "",
        "| Sample | off | 2x | 4x | 4x-smooth | Best |",
        "|--------|-----|----|----|-----------|------|",
    ]
    for i, sp in enumerate(samples):
        vals = {}
        for v in variants:
            r = all_results[v][i]
            vals[v] = r["iou_mean"]
        best = max(v for v in vals.values() if v is not None)
        best_var = [v for v in variants if vals[v] == best][0]
        lines.append(
            f"| `{sp.stem}` | {_val(vals['off'])} | {_val(vals['2x'])} "
            f"| {_val(vals['4x'])} | {_val(vals['4x-smooth'])} | **{best_var}** {best:.4f} |"
        )

    lines.append("")
    lines.append("## Chamfer (px)")
    lines.append("")
    lines.append("| Sample | off | 2x | 4x | 4x-smooth | Best |")
    lines.append("|--------|-----|----|----|-----------|------|")
    for i, sp in enumerate(samples):
        vals = {}
        for v in variants:
            r = all_results[v][i]
            vals[v] = r["chamfer"]
        valid = {v: c for v, c in vals.items() if c is not None}
        if valid:
            best = min(valid.values())
            best_var = [v for v, c in valid.items() if c == best][0]
        else:
            best, best_var = None, "—"
        lines.append(
            f"| `{sp.stem}` | {_val(vals['off'],'.2f')} | {_val(vals['2x'],'.2f')} "
            f"| {_val(vals['4x'],'.2f')} | {_val(vals['4x-smooth'],'.2f')} | **{best_var}** {_val(best,'.2f')} |"
        )

    lines.append("")
    lines.append("## Nodes")
    lines.append("")
    lines.append("| Sample | off | 2x | 4x | 4x-smooth |")
    lines.append("|--------|-----|----|----|-----------|")
    for i, sp in enumerate(samples):
        vals = {v: all_results[v][i]["nodes"] for v in variants}
        lines.append(
            f"| `{sp.stem}` | {vals['off']} | {vals['2x']} "
            f"| {vals['4x']} | {vals['4x-smooth']} |"
        )

    lines.append("")
    lines.append("## Time (s)")
    lines.append("")
    lines.append("| Sample | off | 2x | 4x | 4x-smooth |")
    lines.append("|--------|-----|----|----|-----------|")
    for i, sp in enumerate(samples):
        vals = {v: all_results[v][i].get("elapsed", 0) for v in variants}
        lines.append(
            f"| `{sp.stem}` | {vals['off']} | {vals['2x']} "
            f"| {vals['4x']} | {vals['4x-smooth']} |"
        )

    # Aggregate row
    lines.append("")
    lines.append("## Aggregate (mean across samples)")
    lines.append("")
    lines.append("| Metric | off | 2x | 4x | 4x-smooth |")
    lines.append("|--------|-----|----|----|-----------|")
    for metric, key, fmt in [
        ("IoU mean", "iou_mean", ".4f"),
        ("IoU aw", "iou_aw", ".4f"),
        ("Chamfer", "chamfer", ".2f"),
        ("Nodes", "nodes", ".0f"),
        ("SVG KB", "svg_bytes", ".1f"),
        ("Time (s)", "elapsed", ".1f"),
    ]:
        row = f"| {metric} |"
        for v in variants:
            vals = [r[key] for r in all_results[v] if r.get(key) is not None]
            if not vals:
                row += " — |"
            elif key == "svg_bytes":
                row += f" {np.mean(vals) / 1024:{fmt}} |"
            else:
                row += f" {np.mean(vals):{fmt}} |"
        lines.append(row)

    text = "\n".join(lines) + "\n"
    matrix_path = Path(output_dir) / "matrix_comparison.md"
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.write_text(text, encoding="utf-8")
    print(f"\nMatrix written → {matrix_path}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_eval(
    input_dir: str = "input",
    output_report: str = "output/eval_baseline.md",
    colors: int = DEFAULT_COLORS,
    colors_mode: str = COLORS_MODE_UP_TO,
    geom: str = "off",
    upscale: str = "off",
    dump_diffs: bool = False,
) -> int:
    in_dir = Path(input_dir)
    if not in_dir.is_dir():
        print(f"error: input directory not found: {in_dir}", file=sys.stderr)
        return 1

    samples = sorted(in_dir.glob("sample_*.jpg"))
    if not samples:
        print(f"error: no sample_*.jpg files in {in_dir}", file=sys.stderr)
        return 1

    diffs_dir = Path("output/eval_diffs") if dump_diffs else None

    results = []
    for i, sp in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {sp.name} …", end=" ", flush=True)
        r = evaluate_sample(
            sp, colors=colors, colors_mode=colors_mode, geom=geom,
            upscale=upscale, dump_diffs_dir=diffs_dir,
        )
        results.append(r)
        iou_str = f"IoU={_val(r['iou_mean'])}" if r["iou_mean"] is not None else "IoU=—"
        ch_str = f"Ch={_val(r['chamfer'],'.1f')}px" if r["chamfer"] is not None else "Ch=—"
        t_str = f"{r.get('elapsed','?')}s"
        print(f"✓ {iou_str} {ch_str} nodes={r['nodes']} {t_str}")

    print(f"\nWriting report → {output_report}")
    ver = f"v3-{upscale}" if upscale != "off" else "v3"
    generate_report(results, output_report, version=ver)
    print("Done.")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="LogoTrace evaluation harness")
    ap.add_argument("input_dir", nargs="?", default="input")
    ap.add_argument("--report", default="output/eval_baseline.md")
    ap.add_argument("--colors", type=int, default=DEFAULT_COLORS)
    ap.add_argument("--colors-mode", default=COLORS_MODE_UP_TO, choices=["up_to", "exact"])
    ap.add_argument("--geom", default="off", choices=["off", "basic", "strict"])
    ap.add_argument("--upscale", default="off", choices=["off", "2x", "4x", "4x-smooth"])
    ap.add_argument("--dump-diffs", action="store_true", help="Save XOR diff PNGs for low-IoU masks")
    ap.add_argument("--matrix", action="store_true", help="Run all upscale variants and generate comparison matrix")

    args = ap.parse_args()

    if args.matrix:
        sys.exit(run_matrix(args.input_dir, colors=args.colors, colors_mode=args.colors_mode, geom=args.geom))
    else:
        sys.exit(run_eval(
            args.input_dir, args.report, args.colors, args.colors_mode, args.geom,
            args.upscale, args.dump_diffs,
        ))

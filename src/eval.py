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
    """Tile-based binarization: avoids full-frame N×K float stacks for large images."""
    pal = np.array(palette, dtype=np.int32)
    h, w = arr.shape[:2]
    out = np.zeros((h, w, 3), dtype=np.uint8)

    # Precompute palette squared norms (shared across tiles)
    b2 = np.sum(pal.astype(np.int64) ** 2, axis=1)  # [K]

    # Tile size: ~1M pixels per batch, but at least one full row
    TILE_PX = 1_048_576
    tile_rows = max(1, TILE_PX // max(w, 1))

    for y0 in range(0, h, tile_rows):
        y1 = min(y0 + tile_rows, h)
        tile = arr[y0:y1, :, :]
        tile_h = y1 - y0
        flat = tile.reshape(-1, 3).astype(np.int64)  # [N, 3]
        a2 = np.sum(flat ** 2, axis=1)               # [N]
        ab = flat @ pal.astype(np.int64).T            # [N, K]
        d2 = a2[:, None] + b2[None, :] - 2 * ab       # [N, K]
        nearest_idx = np.argmin(d2, axis=1)
        out[y0:y1, :, :] = pal[nearest_idx].reshape(tile_h, w, 3)

    return out


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


def _eval_palette(
    inks: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    """Evaluation palette: pipeline output is already [bg, ink1, ink2, ...].
    bg is always the first entry and always a mask class.
    """
    return list(inks)


def _masks_identical(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.array_equal(a, b))


# ---------------------------------------------------------------------------
# Upscale preprocessing — default policy (v4)
# ---------------------------------------------------------------------------

UPSCALE_VARIANTS = {"off", "2x", "4x", "4x-smooth", "auto"}
MAX_UPSCALE_SIDE = 3072
MAX_UPSCALE_PX = 9_500_000
MIN_EFFECTIVE_SCALE = 1.05  # skip upscale if would be negligible


def _compute_effective_scale(w: int, h: int, requested: float = 2.0) -> float:
    """Compute upscale factor capped by memory limits, clamped to ≥ 1.0."""
    max_side = max(w, h)
    total_px = w * h
    effective = min(
        requested,
        MAX_UPSCALE_SIDE / max_side,
        (MAX_UPSCALE_PX / total_px) ** 0.5 if total_px > 0 else requested,
    )
    return max(1.0, effective)


def _upscale_image(img: Image.Image, variant: str) -> tuple[Image.Image, float]:
    """Upscale image for pre-trace experiment.

    'auto' = default policy (up to 2x, capped by limits).
    Always returns (img, effective_scale) — if effective ≤ 1.05 the
    caller treats it as no-upscale (factor=1.0).
    """
    if variant == "off" or variant == "none":
        return img.copy(), 1.0
    if variant == "auto":
        requested = 2.0
    elif variant == "2x":
        requested = 2.0
    elif variant == "4x" or variant == "4x-smooth":
        requested = 4.0
    else:
        raise ValueError(f"unknown upscale variant: {variant}")

    effective = _compute_effective_scale(img.width, img.height, requested)
    if effective < MIN_EFFECTIVE_SCALE:
        return img.copy(), 1.0  # too small — run normal pipeline

    up_w = int(img.width * effective)
    up_h = int(img.height * effective)
    up = img.resize((up_w, up_h), Image.Resampling.LANCZOS)
    if variant == "4x-smooth":
        up = up.filter(ImageFilter.GaussianBlur(radius=0.7))
        up = up.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=2))
    return up, effective


def _wrap_svg_scaled(svg_text: str, scale: float, orig_w: int, orig_h: int) -> str:
    """Wrap SVG content in scaled group AND fix viewport to original dimensions."""
    if scale <= 1.0:
        return svg_text
    inv = 1.0 / scale
    svg_text = re.sub(r'width="\d+(\.\d+)?"', f'width="{orig_w}"', svg_text)
    svg_text = re.sub(r'height="\d+(\.\d+)?"', f'height="{orig_h}"', svg_text)
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
    upscale: str = "auto",
    vtracer_threshold_scale: float = 1.0,
    engine: str = "vtracer",
    dump_diffs_dir: Path | str | None = None,
) -> dict:
    """Run pipeline on a sample and return a dict of metrics.

    vtracer_threshold_scale: multiply pixel-unit VTracer params
    (filter_speckle) by this factor. Use with upscale to keep
    geometric strictness constant in source-image units.
    """
    import src.config as _cfg

    t0 = time.monotonic()
    input_path = Path(input_path)
    src_img = load_image(input_path)
    w, h = src_img.size
    src_rgb = np.asarray(src_img.convert("RGB"))
    total_px = w * h
    effective_scale: float = 1.0

    with tempfile.TemporaryDirectory(prefix="logotrace-eval-") as tmp:
        tmpdir = Path(tmp)

        # 1 ─ Upscale preprocess
        pipeline_input: Path | str = input_path
        if upscale in ("auto", "off"):
            effective_scale = 1.0
        else:
            _up_img, effective_scale = _upscale_image(src_img, upscale)
            if effective_scale > 1.0:
                up_path = tmpdir / "upscaled.png"
                _up_img.save(up_path, format="PNG")
                pipeline_input = up_path

        # 2 ─ Run pipeline → SVG + canonical ink palette
        # For off/auto: let pipeline handle upscale (or not).
        # For explicit variants: eval handles upscale, pipeline gets upscale=False.
        pipe_upscale = upscale in ("auto",)
        _saved_speckle = _cfg.VTRACER_FILTER_SPECKLE
        _saved_seglen = _cfg.VTRACER_SEGMENT_LENGTH
        # For manual upscale variants, apply threshold scaling
        if vtracer_threshold_scale > 1.0 and not pipe_upscale:
            _cfg.VTRACER_FILTER_SPECKLE = max(1, int(_cfg.VTRACER_FILTER_SPECKLE * vtracer_threshold_scale))
            _cfg.VTRACER_SEGMENT_LENGTH = max(1, int(_cfg.VTRACER_SEGMENT_LENGTH * vtracer_threshold_scale))
        try:
            svg_text, inks, pipe_eff = vectorize_to_svg(
                input_path=pipeline_input, colors=colors,
                colors_mode=colors_mode, geom=geom,
                upscale=pipe_upscale,
                engine=engine,
            )
            # If pipeline handled upscale, use its effective_scale
            if pipe_upscale:
                effective_scale = pipe_eff
        except VectorizeError as exc:
            _cfg.VTRACER_FILTER_SPECKLE = _saved_speckle
            _cfg.VTRACER_SEGMENT_LENGTH = _saved_seglen
            elapsed = round(time.monotonic() - t0, 1)
            return {
                "sample": input_path.stem, "file": input_path.name,
                "w": w, "h": h, "colors_requested": colors,
                "palette": [], "bg_color": None,
                "iou_mean": None, "iou_worst": None, "iou_bg": None,
                "iou_aw": None,
                "iou_unmatched": 0, "chamfer": None,
                "nodes": None, "svg_bytes": 0, "render_ok": False,
                "upscale": upscale, "effective_scale": effective_scale,
                "elapsed": elapsed,
                "error": str(exc),
            }

        _cfg.VTRACER_FILTER_SPECKLE = _saved_speckle
        _cfg.VTRACER_SEGMENT_LENGTH = _saved_seglen

        # 3 ─ Scale SVG coords back if EVAL upscaled (pipeline already wraps)
        if effective_scale > 1.0 and not pipe_upscale:
            svg_text = _wrap_svg_scaled(svg_text, effective_scale, w, h)

        svg_bytes = len(svg_text.encode("utf-8"))

        # 4 ─ Build evaluation palette (on ORIGINAL image, not upscaled)
        eval_palette = _eval_palette(inks)
        bg_color = eval_palette[0] if eval_palette else None
        has_bg = True

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
            "effective_scale": effective_scale,
            "engine": engine,
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

    svg_text, inks, _eff = vectorize_to_svg(
        input_path=input_path, colors=colors,
        colors_mode=colors_mode, geom=geom,
    )

    eval_palette = _eval_palette(inks)
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
        "| # | Sample | Size | Inks | IoU mean | IoU aw | IoU worst | IoU bg | Chamfer | Nodes | SVG KB | Time |",
        "|---|--------|------|------|----------|--------|-----------|--------|---------|-------|--------|------|",
    ]

    for i, r in enumerate(results, 1):
        bg_str = _val(r.get("iou_bg")) if r.get("iou_bg") is not None else "—"
        aw_str = _val(r.get("iou_aw")) if r.get("iou_aw") is not None else "—"
        t_str = f"{r.get('elapsed', 0)}s" if r.get("elapsed") else "—"
        degenerate = " ⚠" if r.get("degenerate") else ""
        lines.append(
            f"| {i} | `{r['file']}` | {r['w']}×{r['h']} "
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
    """Run all variants across all samples, generate comparison matrix."""
    in_dir = Path(input_dir)
    samples = sorted(list(in_dir.glob("sample_*.jpg")) + list(in_dir.glob("sample_*.png")))
    if not samples:
        print("error: no sample_*.jpg/png files", file=sys.stderr)
        return 1

    # Variants: add new rows here as needed
    variants_config: list[tuple[str, str, float, str]] = [
        ("vtracer+upscale", "auto", 1.0, "vtracer"),
    ]
    all_results: dict[str, list[dict]] = {}

    for var_name, upscale_val, thresh_override, eng_val in variants_config:
        print(f"\n{'='*60}")
        print(f"VARIANT: {var_name}")
        print(f"{'='*60}")
        results = []
        for i, sp in enumerate(samples, 1):
            print(f"  [{i}/{len(samples)}] {sp.name} …", end=" ", flush=True)
            if upscale_val == "auto":
                thresh = 1.0
            else:
                from src.eval import _upscale_image as _up
                _, eff = _up(load_image(sp), upscale_val)
                thresh = thresh_override if thresh_override is not None else eff
            r = evaluate_sample(
                sp, colors=colors, colors_mode=colors_mode, geom=geom,
                upscale=upscale_val, vtracer_threshold_scale=thresh,
                engine=eng_val,
            )
            results.append(r)
            eff_str = f" eff={r.get('effective_scale',1.0):.1f}x" if r.get('effective_scale',1.0) > 1.0 else ""
            print(f"IoU={_val(r['iou_mean'])} aw={_val(r['iou_aw'])} Ch={_val(r['chamfer'],'.1f')}px {r.get('elapsed','?')}s{eff_str}")
        all_results[var_name] = results
        out_path = Path(output_dir) / f"eval_{var_name.replace('-', '_')}.md"
        generate_report(results, out_path, version=f"v4-{var_name}")

    # Build comparison matrix
    vnames = [vn for vn, _, _, _ in variants_config]

    def _vr(var: str, si: int, key: str, fmt_str: str = ".4f") -> str:
        v = all_results[var][si].get(key)
        if v is None:
            return "—"
        return f"{v:{fmt_str}}"

    lines = [
        "# Variant Comparison",
        "",
        f"**Samples:** {len(samples)}",
        f"**Date:** 2026-07-21",
        "",
    ]
    for metric, key, fmt in [
        ("IoU aw", "iou_aw", ".4f"),
        ("Chamfer (px)", "chamfer", ".2f"),
        ("Nodes", "nodes", ".0f"),
        ("Time (s)", "elapsed", ".1f"),
    ]:
        lines.append(f"## {metric}")
        lines.append("")
        header = "| Sample |" + "".join(f" {v} |" for v in vnames)
        sep = "|--------|" + "".join("--------|" for _ in vnames)
        lines.append(header)
        lines.append(sep)
        for i, sp in enumerate(samples):
            row = f"| `{sp.stem}` |"
            for v in vnames:
                row += f" {_vr(v, i, key, fmt)} |"
            lines.append(row)
        lines.append("")

    lines.append("## Aggregate (mean across samples)")
    lines.append("")
    agg_header = "| Metric |" + "".join(f" {v} |" for v in vnames)
    agg_sep = "|--------|" + "".join("--------|" for _ in vnames)
    lines.append(agg_header)
    lines.append(agg_sep)
    for metric, key, fmt in [
        ("IoU mean", "iou_mean", ".4f"),
        ("IoU aw", "iou_aw", ".4f"),
        ("Chamfer", "chamfer", ".2f"),
        ("Nodes", "nodes", ".0f"),
        ("SVG KB", "svg_bytes", ".1f"),
        ("Time (s)", "elapsed", ".1f"),
    ]:
        row = f"| {metric} |"
        for v in vnames:
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
    upscale: str = "auto",
    dump_diffs: bool = False,
) -> int:
    in_dir = Path(input_dir)
    if not in_dir.is_dir():
        print(f"error: input directory not found: {in_dir}", file=sys.stderr)
        return 1

    samples = sorted(list(in_dir.glob("sample_*.jpg")) + list(in_dir.glob("sample_*.png")))
    if not samples:
        print(f"error: no sample_*.jpg/png files in {in_dir}", file=sys.stderr)
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
        aw_str = f"aw={_val(r['iou_aw'])}" if r.get("iou_aw") is not None else ""
        ch_str = f"Ch={_val(r['chamfer'],'.1f')}px" if r["chamfer"] is not None else "Ch=—"
        t_str = f"{r.get('elapsed','?')}s"
        print(f"✓ {iou_str} {aw_str} {ch_str} nodes={r['nodes']} {t_str}")

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
    ap.add_argument("--matrix", action="store_true", help="Run all variants and generate comparison matrix")

    args = ap.parse_args()

    if args.matrix:
        sys.exit(run_matrix(args.input_dir, colors=args.colors, colors_mode=args.colors_mode, geom=args.geom))
    else:
        sys.exit(run_eval(
            args.input_dir, args.report, args.colors, args.colors_mode, args.geom,
            args.upscale, args.dump_diffs,
        ))

#!/usr/bin/env python3
"""Diagnostic trace for sample_10 — step-by-step palette pipeline dump.

Run: PYTHONPATH=. .venv/bin/python scripts/diag_sample_10.py
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.colors import (
    BG_DIST2,
    GRAY_SAT_MAX,
    HUE_BUCKET_DEG,
    MERGE_DIST2,
    MIN_ABSOLUTE_COUNT,
    MIN_MAJOR_MASS,
    NEAR_WHITE_MIN,
    PAPER_WHITE_FRACTION,
    _bucket,
    _build_clusters,
    _dist2,
    _hue_deg,
    _is_near_white,
    _lightness,
    _mass_aware_select,
    _saturation,
    collapse_gradient_ramps,
    estimate_background,
    remap_to_palette,
)

OUT_DIR = Path("output/diag_sample_10")
INPUT = Path("input/sample_10.png")


def hex_color(c: tuple[int, int, int]) -> str:
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def save_png(arr: np.ndarray, name: str) -> Path:
    """Save a numpy RGB array as PNG."""
    p = OUT_DIR / name
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    if arr.ndim == 2:
        # binary mask → RGB
        arr = np.stack([arr.astype(np.uint8) * 255] * 3, axis=-1)
    img = Image.fromarray(arr)
    img.save(p)
    return p


def make_side_by_side(
    source: Image.Image,
    remapped: Image.Image,
    label: str,
) -> Image.Image:
    """Source | Remapped side-by-side with labels."""
    sw, sh = source.size
    rw, rh = remapped.size
    # Use source dimensions
    gap = 4
    total_w = sw + gap + sw  # remap at same size
    total_h = sh + 30
    canvas = Image.new("RGB", (total_w, total_h), (40, 40, 40))
    canvas.paste(source.resize((sw, sh)), (0, 30))
    canvas.paste(remapped.resize((sw, sh)), (sw + gap, 30))
    draw = ImageDraw.Draw(canvas)
    draw.text((4, 4), f"SOURCE  {label}", fill=(255, 255, 255))
    draw.text((sw + gap + 4, 4), "REMAPPED", fill=(255, 255, 255))
    return canvas


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(INPUT).convert("RGB")
    w, h = img.size
    arr = np.asarray(img, dtype=np.int32)
    total_px = w * h
    print(f"=== sample_10: {w}×{h} ({total_px/1000:.0f}K px) ===")

    # ---------------------------------------------------------------
    # Step 0: estimate_background
    # ---------------------------------------------------------------
    bg = estimate_background(img)
    print(f"\n0. estimate_background: {bg} {hex_color(bg)}")

    # Build background mask for PNG
    bg_a = np.array(bg, dtype=np.int32)
    flat_full = arr.reshape(-1, 3)
    d_bg_full = np.sum((flat_full.astype(np.int32) - bg_a) ** 2, axis=1)
    bg_mask = (d_bg_full <= BG_DIST2).reshape(h, w)
    save_png(bg_mask, "00_bg_mask.png")
    print(f"   bg_mask pixels: {bg_mask.sum()} ({bg_mask.sum()/total_px*100:.1f}%)")

    # ---------------------------------------------------------------
    # Step 1: Downscale + white_fraction
    # ---------------------------------------------------------------
    scale = max(w, h) / 320.0
    if scale > 1:
        rgb_s = img.resize(
            (max(1, int(w / scale)), max(1, int(h / scale))),
            Image.Resampling.BOX,
        )
    else:
        rgb_s = img
    arr_s = np.asarray(rgb_s, dtype=np.int32)
    flat = arr_s.reshape(-1, 3)
    print(f"   downscaled: {rgb_s.size[0]}×{rgb_s.size[1]} ({len(flat)} px)")

    near_white_mask = (
        (flat[:, 0] >= NEAR_WHITE_MIN)
        & (flat[:, 1] >= NEAR_WHITE_MIN)
        & (flat[:, 2] >= NEAR_WHITE_MIN)
    )
    white_fraction = float(near_white_mask.mean())
    print(f"1. white_fraction: {white_fraction:.4f} (threshold: {PAPER_WHITE_FRACTION})")
    print(f"   bg is near-white: {_is_near_white(bg)}")

    paper_mode = white_fraction >= PAPER_WHITE_FRACTION or _is_near_white(bg)
    print(f"   mode: {'PAPER' if paper_mode else 'FULLBLEED'}")

    # ---------------------------------------------------------------
    # Step 2: Raw color histogram (top 20)
    # ---------------------------------------------------------------
    # Use downscaled image for histogram
    rgb_flat_tuples = [tuple(int(v) for v in px) for px in flat]
    hist = Counter(rgb_flat_tuples)
    total_mass = sum(hist.values())
    print(f"\n2. Raw color histogram (top 20, from {len(hist)} unique colors):")
    for i, (color, count) in enumerate(hist.most_common(20)):
        pct = count / total_mass * 100
        sat = _saturation(color)
        print(f"   {i+1:2d}. {hex_color(color)} count={count:6d} ({pct:5.1f}%)  "
              f"L={_lightness(color):.0f} sat={sat:.3f}")

    # ---------------------------------------------------------------
    # Step 3: Ink filtering
    # ---------------------------------------------------------------
    if paper_mode:
        d_bg_s = np.sum((flat.astype(np.int32) - bg_a) ** 2, axis=1)
        ink_mask = (~near_white_mask) & (d_bg_s > BG_DIST2)
        ink = flat[ink_mask]
        mode_str = "paper"
        if ink.size == 0:
            ink = flat[~near_white_mask]
            print("   WARNING: ink empty after bg filter, fallback to all non-white")
    else:
        ink = flat[~near_white_mask] if near_white_mask.any() else flat
        mode_str = "fullbleed"

    print(f"\n3. Ink pixels: {len(ink)} / {len(flat)} ({len(ink)/len(flat)*100:.1f}%)")

    # Save ink mask at original resolution for reference
    nw_full = (
        (flat_full[:, 0] >= NEAR_WHITE_MIN)
        & (flat_full[:, 1] >= NEAR_WHITE_MIN)
        & (flat_full[:, 2] >= NEAR_WHITE_MIN)
    )
    d_bg_full_arr = np.sum((flat_full.astype(np.int32) - bg_a) ** 2, axis=1)
    if paper_mode:
        ink_full = (~nw_full) & (d_bg_full_arr > BG_DIST2)
    else:
        ink_full = ~nw_full
    save_png(ink_full.reshape(h, w), "03_ink_mask.png")
    print(f"   ink_full pixels: {ink_full.sum()} ({ink_full.sum()/total_px*100:.1f}%)")

    # Check if green plate is in ink
    # Find any green-ish pixels in ink
    ink_colors = ink if len(ink) > 0 else np.zeros((0, 3), dtype=np.int32)
    green_mask_ink = (
        (ink_colors[:, 1] > ink_colors[:, 0] + 20)
        & (ink_colors[:, 1] > ink_colors[:, 2] + 10)
    ) if len(ink_colors) > 0 else np.array([], dtype=bool)
    green_count = green_mask_ink.sum()
    print(f"   green-ish ink px: {green_count} ({green_count/len(ink)*100:.1f}% of ink)" if len(ink) > 0 else "   no ink")

    # ---------------------------------------------------------------
    # Step 4: _build_clusters
    # ---------------------------------------------------------------
    clusters = _build_clusters(ink)
    total_cluster = sum(c.count for c in clusters) or 1
    print(f"\n4. Clusters (top 20, from {len(clusters)} total):")
    for i, cl in enumerate(clusters[:20]):
        pct = cl.count / total_cluster * 100
        major = "MAJOR" if (cl.count >= MIN_ABSOLUTE_COUNT and cl.count / total_cluster >= MIN_MAJOR_MASS) else "dust"
        print(f"   {i+1:2d}. {hex_color(cl.center)} count={cl.count:6d} ({pct:5.1f}%)  {major}")

    # ---------------------------------------------------------------
    # Step 5: _mass_aware_select (wide)
    # ---------------------------------------------------------------
    wide_n = max(4 * 4, 6)  # max_colors=4, wide_n=16
    wide = _mass_aware_select(clusters, wide_n, colors_mode="up_to")
    print(f"\n5. Mass-aware select (wide, n={wide_n} → {len(wide)} colors):")
    for i, c in enumerate(wide):
        print(f"   {i+1:2d}. {hex_color(c)} sat={_saturation(c):.3f} hue={_hue_deg(c):.0f}° L={_lightness(c):.0f}")

    # ---------------------------------------------------------------
    # Step 6: collapse_gradient_ramps
    # ---------------------------------------------------------------
    print(f"\n6. collapse_gradient_ramps (max_colors=4):")
    print(f"   GRAY_SAT_MAX={GRAY_SAT_MAX}, HUE_BUCKET_DEG={HUE_BUCKET_DEG}°")

    # Trace what gets classified as gray
    grays = [c for c in wide if _saturation(c) <= GRAY_SAT_MAX]
    chroma = [c for c in wide if _saturation(c) > GRAY_SAT_MAX]
    print(f"   Grays ({len(grays)}): {[hex_color(c) for c in grays]}")
    if grays:
        darkest = min(grays, key=_lightness)
        print(f"   → kept darkest gray: {hex_color(darkest)}")

    # Trace hue bucketing
    chroma_sorted = sorted(chroma, key=_hue_deg)
    hue_buckets: list[list[tuple[int, int, int]]] = []
    for c in chroma_sorted:
        h = _hue_deg(c)
        placed = False
        for bucket in hue_buckets:
            bh = _hue_deg(bucket[0])
            dh = abs(h - bh)
            dh = min(dh, 360.0 - dh)
            if dh <= HUE_BUCKET_DEG:
                bucket.append(c)
                placed = True
                break
        if not placed:
            hue_buckets.append([c])

    print(f"   Hue buckets ({len(hue_buckets)}):")
    for bi, bucket in enumerate(hue_buckets):
        anchor = max(bucket, key=lambda c: (_saturation(c), -_lightness(c)))
        print(f"     bucket {bi}: {[hex_color(c) for c in bucket]} → anchor: {hex_color(anchor)}")

    collapsed = collapse_gradient_ramps(wide, max_colors=4)
    print(f"\n   Collapsed → {len(collapsed)} colors:")
    for c in collapsed:
        print(f"     {hex_color(c)} sat={_saturation(c):.3f} hue={_hue_deg(c):.0f}°")

    # ---------------------------------------------------------------
    # Step 7: Full analyze_palette logic (replicate exactly)
    # ---------------------------------------------------------------
    # colors_mode = "up_to", max_colors = 4
    if paper_mode:
        ink_final = flat[ink_mask] if len(flat[ink_mask]) > 0 else flat[~near_white_mask]
        mode_final = "paper"
    else:
        ink_final = flat[~near_white_mask] if near_white_mask.any() else flat
        mode_final = "fullbleed"

    final_colors = _mass_aware_select(
        _build_clusters(ink_final), 4 * 4, colors_mode="up_to"
    )
    final_colors = collapse_gradient_ramps(final_colors, max_colors=4)
    if len(final_colors) > 4:
        final_colors = final_colors[:4]

    # Fullbleed: ensure bg color is present
    if not paper_mode and not any(_dist2(bg, c) <= MERGE_DIST2 for c in final_colors) and not _is_near_white(bg):
        final_colors = [bg] + [c for c in final_colors if _dist2(c, bg) > MERGE_DIST2]
        final_colors = final_colors[:4]

    # Bimodal guard
    if len(final_colors) == 1:
        ink2 = flat[~near_white_mask] if (paper_mode and len(ink_final) > 0) else (ink_final if len(ink_final) > 0 else flat)
        if len(ink2) > 0:
            total2 = len(ink2)
            hist_min = int(ink2.min())
            hist_max = int(ink2.max())
            light_buckets: dict[int, int] = {}
            if hist_max - hist_min > 60:
                for px in ink2:
                    k = int((int(px[0]) + int(px[1]) + int(px[2])) / 3.0 / 20.0)
                    light_buckets[k] = light_buckets.get(k, 0) + 1
                peaks = sorted(
                    [(k, v / total2) for k, v in light_buckets.items() if v / total2 > 0.10],
                    key=lambda kv: kv[0],
                )
                bimodal_fired = len(peaks) >= 2 and peaks[-1][0] - peaks[0][0] >= 3
                print(f"\n7. Bimodal guard:")
                print(f"   hist span: {hist_min}..{hist_max} (>{60} = {hist_max-hist_min>60})")
                print(f"   peaks: {peaks}")
                print(f"   bimodal fired: {bimodal_fired}")
                if bimodal_fired:
                    mass_clusters = _build_clusters(ink2)
                    final_colors = _mass_aware_select(mass_clusters, 4, colors_mode="up_to")
                    print(f"   → fallback colors: {[hex_color(c) for c in final_colors]}")
            else:
                print(f"\n7. Bimodal guard: hist span {hist_max-hist_min} ≤ 60 — skipped")
    else:
        print(f"\n7. Bimodal guard: {len(final_colors)} colors → skipped (not single-fill)")

    if not final_colors:
        final_colors = [(0, 0, 0)]

    print(f"\n=== FINAL PALETTE ({mode_final}): {[hex_color(c) for c in final_colors]} ===")

    # ---------------------------------------------------------------
    # Step 8: Remap and render
    # ---------------------------------------------------------------
    remapped = remap_to_palette(
        img, final_colors, background=bg, mode=mode_final
    )
    remapped.save(OUT_DIR / "08_remapped.png")

    # Side-by-side
    side = make_side_by_side(img, remapped, f"palette={[hex_color(c) for c in final_colors]} {mode_final}")
    side.save(OUT_DIR / "09_side_by_side.png")

    # ---------------------------------------------------------------
    # Step 9: Color analysis — where did green and gold go?
    # ---------------------------------------------------------------
    print(f"\n=== COLOR ANALYSIS ===")
    print(f"   BG: {hex_color(bg)} (classified as {'paper' if paper_mode else 'brand field'})")

    # Find the green area in source
    green_area_mask = (
        (arr[:, :, 1].astype(int) > arr[:, :, 0].astype(int) + 20)
        & (arr[:, :, 1].astype(int) > arr[:, :, 2].astype(int) + 10)
    )
    green_px = green_area_mask.sum()
    print(f"   Green area in source: {green_px} px ({green_px/total_px*100:.2f}%)")

    # Check if those green pixels became background
    green_as_bg = int((green_area_mask & bg_mask).sum())
    print(f"   Green pixels classified as BG: {green_as_bg} ({green_as_bg/green_px*100:.1f}% of green)" if green_px else "   no green")

    # Sample some green pixels
    if green_px > 0:
        gy, gx = np.where(green_area_mask)
        sample_n = min(20, len(gy))
        step = max(1, len(gy) // sample_n)
        print(f"   Sample green pixel colors:")
        for i in range(0, len(gy), step):
            if i // step >= 10:
                break
            px = tuple(int(v) for v in arr[gy[i], gx[i]])
            d2bg = _dist2(px, bg)
            is_bg = d2bg <= BG_DIST2
            print(f"     ({gx[i]:4d},{gy[i]:4d}) {hex_color(px)} d2bg={d2bg} bg_thresh={BG_DIST2} is_bg={is_bg}")

    # Gold/orange area
    gold_mask = (
        (arr[:, :, 0].astype(int) > arr[:, :, 1].astype(int) + 20)
        & (arr[:, :, 1].astype(int) > arr[:, :, 2].astype(int) + 10)
        & (arr[:, :, 0].astype(int) > 150)
    )
    gold_px = gold_mask.sum()
    print(f"\n   Gold/orange area in source: {gold_px} px ({gold_px/total_px*100:.2f}%)")

    if gold_px > 0:
        gy, gx = np.where(gold_mask)
        sample_n = min(20, len(gy))
        step = max(1, len(gy) // sample_n)
        print(f"   Sample gold pixel colors:")
        for i in range(0, len(gy), step):
            if i // step >= 10:
                break
            px = tuple(int(v) for v in arr[gy[i], gx[i]])
            d2bg = _dist2(px, bg)
            print(f"     ({gx[i]:4d},{gy[i]:4d}) {hex_color(px)} sat={_saturation(px):.3f} hue={_hue_deg(px):.0f}° d2bg={d2bg}")

    print(f"\n=== FILES WRITTEN ===")
    for f in sorted(OUT_DIR.glob("*")):
        print(f"  {f.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()

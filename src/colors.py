"""Dominant palette extraction and remap for flat JPEG/PNG logos."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from PIL import Image

# Squared distance thresholds (0-255 RGB space)
BG_DIST2 = 45**2
NEAR_WHITE_MIN = 230
# If fewer than this fraction of pixels are near-white, treat as full-bleed brand art
# (field color is part of the logo, not disposable paper).
PAPER_WHITE_FRACTION = 0.22
MERGE_DIST2 = 35**2
# Cluster is "major" (peer brand color) if it has at least this fraction of ink pixels.
MIN_MAJOR_MASS = 0.03
# Dust below this absolute count (on downsampled ink) always eligible to merge.
MIN_ABSOLUTE_COUNT = 8

COLORS_MODE_UP_TO = "up_to"
COLORS_MODE_EXACT = "exact"

# Gradient collapse: low-saturation chain → one ink; same-hue L-ramp → one anchor
GRAY_SAT_MAX = 0.14
HUE_BUCKET_DEG = 28.0


def _dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _is_near_white(rgb: tuple[int, int, int]) -> bool:
    return rgb[0] >= NEAR_WHITE_MIN and rgb[1] >= NEAR_WHITE_MIN and rgb[2] >= NEAR_WHITE_MIN


def _as_rgb_tuple(px: object) -> tuple[int, int, int]:
    if not isinstance(px, tuple) or len(px) < 3:
        raise TypeError(f"expected RGB tuple, got {px!r}")
    return (int(px[0]), int(px[1]), int(px[2]))


def _median_rgb(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not pixels:
        return (255, 255, 255)
    rs, gs, bs = zip(*pixels)
    n = len(pixels) // 2
    return (sorted(rs)[n], sorted(gs)[n], sorted(bs)[n])


def estimate_background(img: Image.Image) -> tuple[int, int, int]:
    """Background ≈ median of border pixels (JPEG paper / studio bg)."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    border: list[tuple[int, int, int]] = []
    step = max(1, min(w, h) // 200)
    for x in range(0, w, step):
        border.append(_as_rgb_tuple(rgb.getpixel((x, 0))))
        border.append(_as_rgb_tuple(rgb.getpixel((x, h - 1))))
    for y in range(0, h, step):
        border.append(_as_rgb_tuple(rgb.getpixel((0, y))))
        border.append(_as_rgb_tuple(rgb.getpixel((w - 1, y))))
    light = [p for p in border if _is_near_white(p) or sum(p) > 600]
    if len(light) >= max(1, len(border) // 3):
        return _median_rgb(light)
    return _median_rgb(border)


def _bucket(rgb: tuple[int, int, int], bits: int = 4) -> tuple[int, int, int]:
    shift = 8 - bits
    return (rgb[0] >> shift, rgb[1] >> shift, rgb[2] >> shift)


@dataclass
class _Cluster:
    center: tuple[int, int, int]
    count: int


def _build_clusters(ink: np.ndarray) -> list[_Cluster]:
    if ink.size == 0:
        return []
    buckets: Counter[tuple[int, int, int]] = Counter()
    bucket_sums: dict[tuple[int, int, int], list[int]] = {}
    for px in ink:
        t = (int(px[0]), int(px[1]), int(px[2]))
        b = _bucket(t, bits=4)
        buckets[b] += 1
        if b not in bucket_sums:
            bucket_sums[b] = [0, 0, 0, 0]
        s = bucket_sums[b]
        s[0] += t[0]
        s[1] += t[1]
        s[2] += t[2]
        s[3] += 1
    out: list[_Cluster] = []
    for b, _cnt in buckets.most_common():
        s = bucket_sums[b]
        n = s[3]
        out.append(_Cluster(center=(s[0] // n, s[1] // n, s[2] // n), count=n))
    return out


def _mass_aware_select(
    clusters: list[_Cluster],
    max_colors: int,
    colors_mode: str = COLORS_MODE_UP_TO,
) -> list[tuple[int, int, int]]:
    """
    Pick palette colors with mass-aware merge:
    - dust (low mass) may merge into nearest major color when close
    - two major peers are never merged even if close (protects near brand hues)
    - up_to: return 1..max_colors majors (+ leftover dust folded away)
    - exact: collapse to exactly max_colors by folding weakest into nearest kept
      (if fewer majors exist than N, return fewer — do not invent colors)
    """
    if not clusters:
        return [(0, 0, 0)]
    colors_mode = colors_mode if colors_mode in (COLORS_MODE_UP_TO, COLORS_MODE_EXACT) else COLORS_MODE_UP_TO
    total = sum(c.count for c in clusters) or 1
    # sort by mass desc
    ordered = sorted(clusters, key=lambda c: c.count, reverse=True)

    def is_major(c: _Cluster) -> bool:
        return c.count >= MIN_ABSOLUTE_COUNT and (c.count / total) >= MIN_MAJOR_MASS

    # Pass 1: keep majors that are not dust-merged; dust goes to nearest selected major if close
    selected: list[_Cluster] = []
    dust: list[_Cluster] = []

    for cl in ordered:
        if not is_major(cl):
            dust.append(cl)
            continue
        # Extremely close centers (same paint, bucket jitter) → absorb
        ultra = [s for s in selected if _dist2(cl.center, s.center) <= 12**2]
        if ultra:
            nearest = min(ultra, key=lambda s: _dist2(cl.center, s.center))
            nearest.count += cl.count
            continue
        # Two major peers stay separate even when moderately close (near brand hues)
        selected.append(_Cluster(center=cl.center, count=cl.count))

    # Fold dust into nearest selected if close; else keep as minor candidate
    minors: list[_Cluster] = []
    for d in dust:
        if selected:
            nearest = min(selected, key=lambda s: _dist2(d.center, s.center))
            if _dist2(d.center, nearest.center) <= MERGE_DIST2:
                nearest.count += d.count
                continue
        minors.append(d)

    # Candidates = majors first, then remaining minors by mass
    candidates = sorted(selected + minors, key=lambda c: c.count, reverse=True)
    if not candidates:
        return [(0, 0, 0)]

    if colors_mode == COLORS_MODE_EXACT:
        # Keep top max_colors by mass; fold the rest into nearest kept
        kept = candidates[:max_colors]
        rest = candidates[max_colors:]
        for r in rest:
            nearest = min(kept, key=lambda s: _dist2(r.center, s.center))
            nearest.count += r.count
        return [c.center for c in kept]

    # up_to: take majors first up to max_colors; fill with minors only if room
    majors = [c for c in candidates if is_major(c) or c in selected]
    # recompute major on updated counts
    majors = [c for c in candidates if c.count >= MIN_ABSOLUTE_COUNT and (c.count / total) >= MIN_MAJOR_MASS]
    if not majors:
        majors = candidates[:1]
    picked = majors[:max_colors]
    if len(picked) < max_colors:
        for c in candidates:
            if c in picked:
                continue
            if any(_dist2(c.center, p.center) <= MERGE_DIST2 for p in picked):
                continue
            picked.append(c)
            if len(picked) >= max_colors:
                break
    return [c.center for c in picked] or [(0, 0, 0)]


def _lightness(rgb: tuple[int, int, int]) -> float:
    return (rgb[0] + rgb[1] + rgb[2]) / 3.0


def _saturation(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    if mx < 1e-9:
        return 0.0
    return (mx - mn) / mx


def _hue_deg(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 1e-9:
        return 0.0
    if mx == r:
        h = (g - b) / (mx - mn)
    elif mx == g:
        h = 2.0 + (b - r) / (mx - mn)
    else:
        h = 4.0 + (r - g) / (mx - mn)
    h *= 60.0
    if h < 0:
        h += 360.0
    return h


def collapse_gradient_ramps(
    colors: list[tuple[int, int, int]],
    max_colors: int,
) -> list[tuple[int, int, int]]:
    """
    Crush JPEG/gradient steps while keeping distinct brand hues.

    - Near-grays (low saturation): keep a single darkest ink (banding → one fill)
    - Same-hue lightness ramps: keep one anchor (highest chroma, else darkest)
    - Different hues stay separate
    """
    if not colors:
        return [(0, 0, 0)]
    if len(colors) == 1:
        return list(colors)

    grays: list[tuple[int, int, int]] = []
    chroma: list[tuple[int, int, int]] = []
    for c in colors:
        if _saturation(c) <= GRAY_SAT_MAX:
            grays.append(c)
        else:
            chroma.append(c)

    out: list[tuple[int, int, int]] = []
    if grays:
        out.append(min(grays, key=_lightness))

    chroma_sorted = sorted(chroma, key=_hue_deg)
    buckets: list[list[tuple[int, int, int]]] = []
    for c in chroma_sorted:
        h = _hue_deg(c)
        placed = False
        for bucket in buckets:
            bh = _hue_deg(bucket[0])
            dh = abs(h - bh)
            dh = min(dh, 360.0 - dh)
            if dh <= HUE_BUCKET_DEG:
                bucket.append(c)
                placed = True
                break
        if not placed:
            buckets.append([c])

    for bucket in buckets:
        anchor = max(bucket, key=lambda c: (_saturation(c), -_lightness(c)))
        out.append(anchor)

    deduped: list[tuple[int, int, int]] = []
    for c in out:
        if any(_dist2(c, d) <= 12**2 for d in deduped):
            continue
        deduped.append(c)
    out = deduped

    if len(out) > max_colors:
        out = sorted(
            out,
            key=lambda c: (_saturation(c) > GRAY_SAT_MAX, _saturation(c), -_lightness(c)),
            reverse=True,
        )[:max_colors]

    return out or list(colors[:1])


def _select_from_pixels(
    ink: np.ndarray,
    max_colors: int,
    colors_mode: str = COLORS_MODE_UP_TO,
) -> list[tuple[int, int, int]]:
    """Mass-aware palette + gradient ramp collapse."""
    clusters = _build_clusters(ink)
    wide_n = max(max_colors * 4, max_colors + 2)
    wide = _mass_aware_select(clusters, wide_n, colors_mode=COLORS_MODE_UP_TO)
    collapsed = collapse_gradient_ramps(wide, max_colors=max_colors)
    if len(collapsed) > max_colors:
        collapsed = collapsed[:max_colors]
    return collapsed or [(0, 0, 0)]


@dataclass(frozen=True)
class PaletteResult:
    colors: list[tuple[int, int, int]]
    mode: str  # "paper" | "fullbleed"
    background: tuple[int, int, int]
    white_fraction: float
    colors_mode: str = COLORS_MODE_UP_TO


def analyze_palette(
    img: Image.Image,
    max_colors: int,
    colors_mode: str = COLORS_MODE_UP_TO,
) -> PaletteResult:
    """
    Extract brand colors (up_to or exact N ink colors).

    paper: lots of near-white → drop paper/bg, keep ink only
    fullbleed: brand field fills frame → keep field color in palette;
               only pure near-white becomes print white

    Mass-aware merge: dust folds into majors; two major peers never merge.
    """
    if max_colors < 1:
        raise ValueError("max_colors must be >= 1")
    if colors_mode not in (COLORS_MODE_UP_TO, COLORS_MODE_EXACT):
        raise ValueError(f"colors_mode must be up_to|exact, got {colors_mode!r}")

    rgb = img.convert("RGB")
    w, h = rgb.size
    scale = max(w, h) / 320.0
    if scale > 1:
        rgb_s = rgb.resize(
            (max(1, int(w / scale)), max(1, int(h / scale))),
            Image.Resampling.BOX,
        )
    else:
        rgb_s = rgb

    arr = np.asarray(rgb_s, dtype=np.int32)
    flat = arr.reshape(-1, 3)
    near_white = (
        (flat[:, 0] >= NEAR_WHITE_MIN)
        & (flat[:, 1] >= NEAR_WHITE_MIN)
        & (flat[:, 2] >= NEAR_WHITE_MIN)
    )
    white_fraction = float(near_white.mean()) if len(flat) else 0.0
    bg = estimate_background(rgb)
    bg_a = np.array(bg, dtype=np.int32)
    d_bg = np.sum((flat - bg_a) ** 2, axis=1)

    paper_mode = white_fraction >= PAPER_WHITE_FRACTION or _is_near_white(bg)

    if paper_mode:
        ink_mask = (~near_white) & (d_bg > BG_DIST2)
        ink = flat[ink_mask]
        mode = "paper"
        if ink.size == 0:
            ink = flat[~near_white]
        colors = _select_from_pixels(ink, max_colors, colors_mode=colors_mode)
    else:
        ink = flat[~near_white] if near_white.any() else flat
        mode = "fullbleed"
        colors = _select_from_pixels(ink, max_colors, colors_mode=colors_mode)
        # ensure border/field color is present if distinct major
        if not any(_dist2(bg, c) <= MERGE_DIST2 for c in colors) and not _is_near_white(bg):
            colors = [bg] + [c for c in colors if _dist2(c, bg) > MERGE_DIST2]
            if colors_mode == COLORS_MODE_EXACT:
                colors = colors[:max_colors]
            else:
                colors = colors[:max_colors]

    if not colors:
        colors = [(0, 0, 0)]

    return PaletteResult(
        colors=colors,
        mode=mode,
        background=bg,
        white_fraction=white_fraction,
        colors_mode=colors_mode,
    )


def extract_logo_colors(
    img: Image.Image,
    max_colors: int,
    *,
    ignore_background: bool = True,
) -> list[tuple[int, int, int]]:
    """Backward-compatible helper → list of RGB tuples."""
    res = analyze_palette(img, max_colors)
    if not ignore_background and res.mode == "paper":
        # force include all major colors
        return analyze_palette(img, max_colors).colors
    return res.colors


def remap_to_palette(
    img: Image.Image,
    palette: list[tuple[int, int, int]],
    *,
    background: tuple[int, int, int] | None = None,
    mode: str = "paper",
    keep_alpha: bool = False,
) -> Image.Image:
    """
    Snap every pixel to nearest palette color (numpy).

    paper: near-white OR border-bg → pure white
    fullbleed: only near-white → pure white (brand field stays)
    """
    if not palette:
        raise ValueError("palette must not be empty")

    bg = background if background is not None else estimate_background(img.convert("RGB"))
    bg_a = np.array(bg, dtype=np.int32)
    pal = np.array(palette, dtype=np.int32)

    if keep_alpha and img.mode in ("RGBA", "LA"):
        rgba = np.asarray(img.convert("RGBA"))
        rgb = rgba[:, :, :3].astype(np.int32)
        alpha = rgba[:, :, 3]
    else:
        rgb = np.asarray(img.convert("RGB"), dtype=np.int32)
        alpha = None

    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.int64)

    a2 = np.sum(flat**2, axis=1, keepdims=True)
    b2 = np.sum(pal.astype(np.int64) ** 2, axis=1)[None, :]
    ab = flat @ pal.astype(np.int64).T
    d2 = a2 + b2 - 2 * ab
    nearest_idx = np.argmin(d2, axis=1)
    mapped = pal[nearest_idx].copy()

    near_white = (
        (flat[:, 0] >= NEAR_WHITE_MIN)
        & (flat[:, 1] >= NEAR_WHITE_MIN)
        & (flat[:, 2] >= NEAR_WHITE_MIN)
    )
    d_bg = np.sum((flat.astype(np.int32) - bg_a) ** 2, axis=1)

    if mode == "fullbleed":
        is_bg = near_white
    else:
        is_bg = near_white | (d_bg <= BG_DIST2)

    mapped[is_bg] = np.array([255, 255, 255], dtype=np.int32)

    if keep_alpha and alpha is not None:
        out_rgb = mapped.reshape(h, w, 3).astype(np.uint8)
        out_a = alpha.copy()
        out_a[is_bg.reshape(h, w)] = 0
        out_a[alpha < 16] = 0
        out = np.dstack([out_rgb, out_a])
        return Image.fromarray(out, mode="RGBA")

    out_rgb = mapped.reshape(h, w, 3).astype(np.uint8)
    return Image.fromarray(out_rgb, mode="RGB")

"""Subpixel contour tracer — extracts smooth vector curves from soft image masks.

Uses skimage.measure.find_contours on per-color soft-membership masks
computed from the *original* (pre-remap) image. This preserves subpixel
edge information encoded in antialiasing, producing smoother curves than
tracing a hard-quantized bitmap.

Pipeline:
  1. Soft membership mask per palette color (relative color distance)
  2. skimage find_contours(mask, 0.5) → float polylines
  3. Corner detection: split polylines at sharp angle changes
  4. Cubic Bezier fit on smooth segments (Schneider fitCurves)
  5. Z-order by area, SVG output
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from skimage.measure import find_contours

from src.config import PROJECT_ROOT

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUBPIXEL_BEZIER_ERROR = 0.5        # max fit error in source-image pixels
SUBPIXEL_CORNER_ANGLE = 45.0       # degrees — split at angles sharper than this
SUBPIXEL_CORNER_WINDOW = 12        # arc-length window for corner detection
SUBPIXEL_GAUSS_SIGMA = 0.6         # gaussian blur to suppress JPEG noise
SUBPIXEL_MIN_CONTOUR_LEN = 16      # skip contours shorter than this (px)
SUBPIXEL_MIN_CONTOUR_AREA = 64     # skip contours enclosing fewer than this (px²)
SUBPIXEL_SCALE = 0.5               # work at this fraction of source resolution

# ---------------------------------------------------------------------------
# Soft membership masks
SUBPIXEL_SCALE = 0.5               # work at this fraction of source resolution
SUBPIXEL_CONTOUR_LEVEL = 0.5       # find_contours level (0.5 for hard binary masks)


def _soft_membership_masks(
    rgb: np.ndarray,
    palette: Sequence[tuple[int, int, int]],
    bg_color: tuple[int, int, int] | None = None,
    sigma: float = SUBPIXEL_GAUSS_SIGMA,
) -> list[np.ndarray]:
    """Build per-color soft membership masks from the original image.

    Uses relative weighting: soft[i] = exp(-(d[i] / min_dist)²) / sum.
    Light gaussian filter to stabilise JPEG noise.
    """
    h, w, _ = rgb.shape
    palette_arr = np.array(palette, dtype=np.float64)
    n_colors = len(palette_arr)

    flat = rgb.reshape(-1, 3).astype(np.float64)

    # Distances to each palette color
    diffs = np.zeros((flat.shape[0], n_colors))
    for i in range(n_colors):
        diffs[:, i] = np.sqrt(((flat - palette_arr[i]) ** 2).sum(axis=1))

    # Adaptive delta: median of min distances per pixel
    min_dists = diffs.min(axis=1)
    delta = float(np.median(min_dists)) or 1.0

    # Exponential falloff, normalized
    weights = np.exp(-(diffs / delta) ** 2)
    row_sums = weights.sum(axis=1, keepdims=True)
    row_sums[row_sums < 1e-9] = 1.0
    weights /= row_sums

    masks = []
    for i in range(n_colors):
        mask = weights[:, i].reshape(h, w)
        if sigma > 0:
            mask = gaussian_filter(mask, sigma=sigma, mode="nearest")
        masks.append(mask)

    return masks


def _simplify_polyline(points: np.ndarray, epsilon: float = 1.0) -> np.ndarray:
    """Ramer-Douglas-Peucker simplification."""
    if len(points) < 3:
        return points
    # Find point farthest from line segment
    dmax = 0.0
    idx = 0
    end = len(points) - 1
    for i in range(1, end):
        d = _point_line_distance(points[i], points[0], points[end])
        if d > dmax:
            dmax = d
            idx = i
    if dmax > epsilon:
        left = _simplify_polyline(points[: idx + 1], epsilon)
        right = _simplify_polyline(points[idx:], epsilon)
        return np.vstack([left[:-1], right])
    return np.array([points[0], points[end]])


def _point_line_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Perpendicular distance from point p to line segment ab."""
    ab = b - a
    ap = p - a
    t = np.dot(ap, ab) / max(1e-9, np.dot(ab, ab))
    t = max(0.0, min(1.0, t))
    proj = a + t * ab
    return float(np.linalg.norm(p - proj))


# ---------------------------------------------------------------------------
# Corner detection on polylines
# ---------------------------------------------------------------------------


def _detect_corners(
    points: np.ndarray,
    angle_threshold_deg: float = SUBPIXEL_CORNER_ANGLE,
    window: int = SUBPIXEL_CORNER_WINDOW,
) -> list[int]:
    """Find corner indices in a polyline (N,2) based on angle change.

    At each point i, compute the angle between the vectors
    (i-window → i) and (i → i+window). If the angle < angle_threshold,
    insert a corner at i.

    Returns sorted list of corner indices (including 0 and len-1).
    """
    n = len(points)
    if n < 5:
        return [0, n - 1] if n > 1 else [0]

    corners = {0, n - 1}
    for i in range(window, n - window):
        p_prev = points[i - window]
        p_curr = points[i]
        p_next = points[i + window]

        v1 = p_prev.astype(np.float64) - p_curr.astype(np.float64)
        v2 = p_next.astype(np.float64) - p_curr.astype(np.float64)
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < 1e-6 or n2 < 1e-6:
            continue

        cos_angle = np.dot(v1, v2) / (n1 * n2)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle = math.degrees(math.acos(cos_angle))

        if angle < angle_threshold_deg:
            corners.add(i)

    return sorted(corners)


# ---------------------------------------------------------------------------
# Bezier fitting (Schneider fitCurves, simplified)
# ---------------------------------------------------------------------------


def _fit_cubic_bezier(
    points: np.ndarray,
    max_error: float = SUBPIXEL_BEZIER_ERROR,
) -> list[np.ndarray]:
    """Fit a polyline segment with cubic Bezier curves.

    Uses recursive Schneider fitCurves. Returns list of (4,2) control-point arrays,
    each = [P0, P1, P2, P3].

    Based on: Philip J. Schneider, "An Algorithm for Automatically Fitting
    Digitized Curves", Graphics Gems, 1990.
    """
    n = len(points)
    if n < 2:
        return []

    result: list[np.ndarray] = []

    def _fit(pts: np.ndarray):
        n_pts = len(pts)
        if n_pts < 2:
            return

        # Parameterise by chord length
        chords = np.zeros(n_pts)
        for i in range(1, n_pts):
            chords[i] = chords[i - 1] + np.linalg.norm(pts[i] - pts[i - 1])
        total = chords[-1]
        if total < 1e-9:
            return
        u = chords / total  # parameterisation in [0,1]

        # Initial tangent estimates
        t0 = pts[1] - pts[0]
        tn = pts[-1] - pts[-2]

        # Fit single cubic: P0=pts[0], P3=pts[-1], find P1, P2
        bez = _fit_single_cubic(pts, u, t0, tn)
        if bez is None:
            # Fallback: linear segment
            bez = np.array([pts[0], pts[0], pts[-1], pts[-1]])

        # Compute max error
        max_err, split_idx = _bezier_error(bez, pts)
        if max_err <= max_error:
            result.append(bez)
        else:
            # Split and recurse
            _fit(pts[: split_idx + 1])
            _fit(pts[split_idx:])

    _fit(points)
    return result


def _fit_single_cubic(
    pts: np.ndarray,
    u: np.ndarray,
    t0: np.ndarray,
    tn: np.ndarray,
) -> np.ndarray | None:
    """Least-squares fit a single cubic Bezier to points with given tangents.

    Returns (4,2) array [P0, P1, P2, P3] or None on failure.
    """
    n = len(pts)
    if n < 2:
        return None

    P0 = pts[0].astype(np.float64)
    P3 = pts[-1].astype(np.float64)

    # Normalise tangents
    alpha = np.linalg.norm(t0)
    beta = np.linalg.norm(tn)
    if alpha < 1e-9:
        alpha = 1.0
    if beta < 1e-9:
        beta = 1.0
    t0_n = t0 / alpha
    tn_n = tn / beta

    # Chord length
    chord = np.linalg.norm(P3 - P0)
    if chord < 1e-9:
        chord = 1.0
    d1 = chord / 3.0
    d2 = chord / 3.0

    # Solve for P1, P2
    A = np.zeros((2, 2))
    B = np.zeros((2, 2))
    for k in range(n):
        uk = u[k]
        b0 = (1.0 - uk) ** 3
        b1 = 3.0 * uk * (1.0 - uk) ** 2
        b2 = 3.0 * uk**2 * (1.0 - uk)

        a1 = t0_n * d1 * b1
        a2 = tn_n * d2 * b2
        A[0, 0] += np.dot(a1, a1)
        A[0, 1] += np.dot(a1, a2)
        A[1, 0] += np.dot(a2, a1)
        A[1, 1] += np.dot(a2, a2)

        c = pts[k].astype(np.float64) - b0 * P0 - uk**3 * P3
        B[0] += np.dot(c, a1) * np.array([1.0, 1.0])
        B[1] += np.dot(c, a2) * np.array([1.0, 1.0])

    det = A[0, 0] * A[1, 1] - A[0, 1] * A[1, 0]
    if abs(det) < 1e-12:
        return None

    inv = np.array([[A[1, 1], -A[0, 1]], [-A[1, 0], A[0, 0]]]) / det
    X = inv @ B

    P1 = P0 + t0_n * d1 * X[0]
    P2 = P3 + tn_n * d2 * X[1]
    return np.array([P0, P1, P2, P3])


def _bezier_error(bez: np.ndarray, pts: np.ndarray) -> tuple[float, int]:
    """Compute max distance from bezier curve to polyline points.
    Returns (max_error, split_index).
    """
    n = len(bez)
    max_err = 0.0
    split_idx = 0
    P0, P1, P2, P3 = bez[0], bez[1], bez[2], bez[3]
    for i, p in enumerate(pts):
        t = i / max(1, len(pts) - 1)
        t2 = t * t
        t3 = t2 * t
        mt = 1.0 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        q = mt3 * P0 + 3.0 * mt2 * t * P1 + 3.0 * mt * t2 * P2 + t3 * P3
        err = np.linalg.norm(p - q)
        if err > max_err:
            max_err = err
            split_idx = i
    return float(max_err), split_idx


def _bezier_to_svg_d(control_points: list[np.ndarray]) -> str:
    """Convert list of (4,2) Bezier control points to SVG path d string."""
    parts = []
    for i, bez in enumerate(control_points):
        p0, p1, p2, p3 = bez
        if i == 0:
            parts.append(f"M {p0[0]:.3f},{p0[1]:.3f}")
        parts.append(f"C {p1[0]:.3f},{p1[1]:.3f} {p2[0]:.3f},{p2[1]:.3f} {p3[0]:.3f},{p3[1]:.3f}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Contour extraction for a single color layer
# ---------------------------------------------------------------------------


def _trace_layer(
    mask: np.ndarray,
    color: tuple[int, int, int],
    scale: float = SUBPIXEL_SCALE,
    min_len: int = SUBPIXEL_MIN_CONTOUR_LEN,
    min_area: int = SUBPIXEL_MIN_CONTOUR_AREA,
) -> list[str]:
    """Extract SVG path strings for one color layer.

    Works at reduced scale (scale < 1.0), simplifies polylines, then
    scales coordinates back to source resolution.
    """
    h, w = mask.shape

    # Downscale mask for faster contour extraction
    if scale < 1.0:
        from PIL import Image as PILImage
        sw, sh = int(w * scale), int(h * scale)
        mask_img = PILImage.fromarray((mask * 255).astype(np.uint8))
        mask_img = mask_img.resize((sw, sh), PILImage.Resampling.LANCZOS)
        mask_scaled = np.array(mask_img, dtype=np.float64) / 255.0
        inv_scale = 1.0 / scale
    else:
        mask_scaled = mask
        inv_scale = 1.0

    contours = find_contours(mask_scaled, level=SUBPIXEL_CONTOUR_LEVEL, fully_connected="high")

    # Filter and simplify
    valid = []
    for contour in contours:
        if len(contour) < min_len * scale:
            continue
        d_close = np.linalg.norm(contour[0] - contour[-1])
        perimeter = sum(
            np.linalg.norm(contour[i] - contour[i - 1]) for i in range(1, len(contour))
        )
        if d_close > 1.0 or perimeter < 5.0 * scale:
            continue
        # Close exactly
        if d_close > 0.01:
            contour = np.vstack([contour, contour[0:1]])
        valid.append(contour)

    if not valid:
        return []

    # Area for z-order + filter
    areas = []
    for c in valid:
        xs, ys = c[:, 1], c[:, 0]
        area = 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))
        areas.append(area * inv_scale**2)  # back to source px²

    order = sorted(range(len(valid)), key=lambda i: areas[i], reverse=True)
    ordered = [(valid[i], areas[i]) for i in order if areas[i] >= min_area]

    paths = []
    for contour, _area in ordered:
        # (row, col) → (x, y), scale back
        pts = np.column_stack([contour[:, 1] * inv_scale, contour[:, 0] * inv_scale])

        # Simplify polyline (RDP)
        pts = _simplify_polyline(pts, epsilon=1.0)
        if len(pts) < 4:
            continue

        # Corner detection
        corners = _detect_corners(pts)

        # Fit Beziers between corners
        all_beziers = []
        for ci in range(len(corners) - 1):
            a, b = corners[ci], corners[ci + 1]
            seg = pts[a : b + 1]
            if len(seg) < 4:
                all_beziers.append(
                    np.array([seg[0], seg[0], seg[-1], seg[-1]])
                )
            else:
                beziers = _fit_cubic_bezier(seg)
                all_beziers.extend(beziers)

        if all_beziers:
            d = _bezier_to_svg_d(all_beziers)
            paths.append(d + " Z")

    return paths


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def subpixel_trace(
    image: Image.Image | np.ndarray,
    palette: list[tuple[int, int, int]],
    bg_color: tuple[int, int, int] | None = None,
) -> str:
    """Trace a flat-color image into an SVG string using contour extraction.

    Uses the quantized palette-remapped image (same as VTracer input) for
    clean contours, then fits cubic Beziers for smooth curves. The name
    'subpixel' is aspirational — current implementation uses pixel-precision
    contours with Bezier smoothing. Future: gradient-based subpixel refinement.

    Args:
        image: PIL Image or RGB numpy array (H,W,3), the ORIGINAL pre-remap image.
        palette: canonical ink colors.
        bg_color: paper color.

    Returns:
        SVG string with Bezier paths.
    """
    if isinstance(image, Image.Image):
        rgb = np.array(image.convert("RGB"), dtype=np.uint8)
    else:
        rgb = np.asarray(image, dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("image must be H×W×3 RGB")

    h, w = rgb.shape[:2]

    # Remap image to palette (use pipeline's remap logic via soft masks as proxy)
    # Build hard binary mask per color: snap each pixel to nearest palette color
    palette_arr = np.array(palette, dtype=np.float64)
    flat = rgb.reshape(-1, 3).astype(np.float64)
    diffs = np.zeros((flat.shape[0], len(palette_arr)))
    for i in range(len(palette_arr)):
        diffs[:, i] = ((flat - palette_arr[i]) ** 2).sum(axis=1)
    labels = diffs.argmin(axis=1).reshape(h, w)

    # Build SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
    ]

    # Background rect
    if bg_color is not None:
        r, g, b = bg_color
        svg_parts.append(
            f'<rect width="{w}" height="{h}" fill="rgb({r},{g},{b})"/>'
        )
    else:
        r, g, b = palette[0]
        svg_parts.append(
            f'<rect width="{w}" height="{h}" fill="rgb({r},{g},{b})"/>'
        )

    # Trace each color layer
    for ci, color in enumerate(palette):
        mask = (labels == ci).astype(np.float64)
        # Skip if color covers < 0.1% of image
        if mask.mean() < 0.001:
            continue
        paths = _trace_layer(mask, color)
        if paths:
            r, g, b = color
            svg_parts.append(
                f'<path fill="rgb({r},{g},{b})" stroke="none" d="{" ".join(paths)}"/>'
            )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)

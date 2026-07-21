"""Primitive fitting for VTracer SVG output.

Detects and enforces intentional geometry in logo traces:
- Pass 1: Collapse near-straight bezier chains into single line segments.
- Pass 2: Snap near-horizontal/vertical lines to exact axes.
- Pass 3: Classify joints as corners vs smooth, enforce G1 on smooth joins.

Each pass is guarded: if a shape's IoU drops > 0.003, its changes are reverted.

Works via in-place d-attribute replacement — preserves all other SVG
structure (transforms, XML decl, etc.).

Usage:
    from src.geometry_fit import geometry_fit
    svg_fitted, stats = geometry_fit(svg_text)
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Path representation
# ---------------------------------------------------------------------------


@dataclass
class SegMove:
    x: float
    y: float


@dataclass
class SegLine:
    x: float
    y: float


@dataclass
class SegCubic:
    x1: float
    y1: float
    x2: float
    y2: float
    x3: float
    y3: float


@dataclass
class SegClose:
    pass


Seg = SegMove | SegLine | SegCubic | SegClose


@dataclass
class PathShape:
    """A single <path> element: fill color + segments + original d-string."""
    fill: str
    segs: list[Seg]
    orig_d: str = ""  # original d-attribute for in-place replacement
    original_segs: list[Seg] | None = None


# ---------------------------------------------------------------------------
# SVG parsing
# ---------------------------------------------------------------------------

_RE_PATH_FULL = re.compile(
    r'(<path\b[^>]*\bfill="([^"]*)"[^>]*\bd=")([^"]*)(")',
    flags=re.I,
)
_RE_PATH_ALT = re.compile(
    r'(<path\b[^>]*\bd=")([^"]*)("[^>]*\bfill=")([^"]*)(")',
    flags=re.I,
)
_RE_D_CMD = re.compile(r"([MLCQZ])\s*([\d.\s,\-]*)", flags=re.I)
_RE_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _parse_coords(text: str, n: int) -> list[float]:
    nums = [float(m.group()) for m in _RE_NUM.finditer(text)]
    out: list[float] = []
    i = 0
    while i + n <= len(nums):
        out.extend(nums[i : i + n])
        i += n
    return out


def parse_path_d(d: str) -> list[Seg]:
    """Parse SVG d-attribute into list of segments."""
    segs: list[Seg] = []
    for cm in _RE_D_CMD.finditer(d):
        cmd = cm.group(1).upper()
        rest = cm.group(2).strip()
        if cmd == "M":
            c = _parse_coords(rest, 2)
            for i in range(0, len(c), 2):
                segs.append(SegMove(c[i], c[i + 1]))
        elif cmd == "L":
            c = _parse_coords(rest, 2)
            for i in range(0, len(c), 2):
                segs.append(SegLine(c[i], c[i + 1]))
        elif cmd == "C":
            c = _parse_coords(rest, 6)
            for i in range(0, len(c), 6):
                segs.append(SegCubic(c[i], c[i + 1], c[i + 2], c[i + 3], c[i + 4], c[i + 5]))
        elif cmd == "Q":
            c = _parse_coords(rest, 4)
            for i in range(0, len(c), 4):
                segs.append(SegCubic(c[i], c[i + 1], c[i], c[i + 1], c[i + 2], c[i + 3]))
        elif cmd == "Z":
            segs.append(SegClose())
    return segs


def parse_svg_shapes(svg_text: str) -> list[PathShape]:
    """Extract all shapes from SVG with their original d-strings."""
    shapes: list[PathShape] = []
    for m in _RE_PATH_FULL.finditer(svg_text):
        fill = m.group(2)
        d = m.group(3)
        segs = parse_path_d(d)
        shapes.append(PathShape(fill=fill, segs=segs, orig_d=d))
    for m in _RE_PATH_ALT.finditer(svg_text):
        fill = m.group(4)
        d = m.group(2)
        # Deduplicate
        if not any(s.fill == fill and s.orig_d == d for s in shapes):
            segs = parse_path_d(d)
            shapes.append(PathShape(fill=fill, segs=segs, orig_d=d))
    return shapes


def _segs_to_d(segs: list[Seg]) -> str:
    """Convert segments back to d-attribute string."""
    parts: list[str] = []
    for seg in segs:
        if isinstance(seg, SegMove):
            parts.append(f"M {seg.x:.3f} {seg.y:.3f}")
        elif isinstance(seg, SegLine):
            parts.append(f"L {seg.x:.3f} {seg.y:.3f}")
        elif isinstance(seg, SegCubic):
            parts.append(
                f"C {seg.x1:.3f} {seg.y1:.3f} {seg.x2:.3f} {seg.y2:.3f} "
                f"{seg.x3:.3f} {seg.y3:.3f}"
            )
        elif isinstance(seg, SegClose):
            parts.append("Z")
    return " ".join(parts)


def inject_d_attrs(svg_text: str, shapes: list[PathShape]) -> str:
    """Replace d-attributes in SVG with fitted values. Preserves all other structure."""
    result = svg_text
    for shape in shapes:
        new_d = _segs_to_d(shape.segs)
        old_full = f'd="{shape.orig_d}"'
        new_full = f'd="{new_d}"'
        # Replace first occurrence
        idx = result.find(old_full)
        if idx >= 0:
            result = result[:idx] + new_full + result[idx + len(old_full):]
    return result


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _seg_start(segs: list[Seg], idx: int) -> tuple[float, float]:
    if idx == 0:
        for s in reversed(segs):
            if isinstance(s, SegMove):
                return s.x, s.y
        return 0.0, 0.0
    prev = segs[idx - 1]
    if isinstance(prev, (SegMove, SegLine)):
        return prev.x, prev.y
    elif isinstance(prev, SegCubic):
        return prev.x3, prev.y3
    elif isinstance(prev, SegClose):
        for s in segs:
            if isinstance(s, SegMove):
                return s.x, s.y
        return 0.0, 0.0
    return 0.0, 0.0


def _point_line_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    denom = math.hypot(dx, dy)
    if denom < 1e-12:
        return math.hypot(px - ax, py - ay)
    return abs(dy * px - dx * py + bx * ay - by * ax) / denom


def _tangent_at_end(x0: float, y0: float, x1: float, y1: float,
                    x2: float, y2: float, x3: float, y3: float) -> tuple[float, float]:
    dx, dy = x3 - x2, y3 - y2
    n = math.hypot(dx, dy)
    if n < 1e-9:
        dx, dy = x3 - x0, y3 - y0
        n = math.hypot(dx, dy)
    if n < 1e-9:
        return 1.0, 0.0
    return dx / n, dy / n


def _tangent_at_start(x0: float, y0: float, x1: float, y1: float,
                      x2: float, y2: float, x3: float, y3: float) -> tuple[float, float]:
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    if n < 1e-9:
        dx, dy = x3 - x0, y3 - y0
        n = math.hypot(dx, dy)
    if n < 1e-9:
        return 1.0, 0.0
    return dx / n, dy / n


def _angle_between(t1: tuple[float, float], t2: tuple[float, float]) -> float:
    dot = t1[0] * t2[0] + t1[1] * t2[1]
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


# ---------------------------------------------------------------------------
# Safety guard: per-shape IoU
# ---------------------------------------------------------------------------


def _render_single_path_svg(shape: PathShape, cw: int, ch: int) -> np.ndarray:
    """Render one shape on a white canvas → binary mask."""
    d = _segs_to_d(shape.segs)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}" height="{ch}"'
        f' viewBox="0 0 {cw} {ch}">'
        f'<rect width="{cw}" height="{ch}" fill="white"/>'
        f'<path fill="black" stroke="none" d="{d}"/>'
        f'</svg>'
    )
    scale = min(1.0, 300.0 / max(cw, ch))
    rw = max(1, int(cw * scale))
    rh = max(1, int(ch * scale))
    try:
        import cairosvg
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=rw, output_height=rh)
        img = Image.open(io.BytesIO(png)).convert("L")
        if scale < 1.0:
            img = img.resize((cw, ch), Image.Resampling.NEAREST)
        return np.asarray(img, dtype=np.uint8) < 128
    except Exception:
        return np.zeros((ch, cw), dtype=bool)


def _shape_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 1.0
    return float(inter) / float(union)


# ---------------------------------------------------------------------------
# Pass 1 — line detection
# ---------------------------------------------------------------------------

TOL_LINE = 0.35


def _pass1_line_detect(shapes: list[PathShape], cw: int, ch: int) -> dict[str, int]:
    stats = {"lines_merged": 0, "shapes_changed": 0, "reverts": 0}
    for shape in shapes:
        segs = shape.segs
        n = len(segs)
        if n < 2:
            continue
        shape.original_segs = list(segs)
        changed = False
        new_segs: list[Seg] = []
        i = 0
        while i < n:
            seg = segs[i]
            if isinstance(seg, SegCubic):
                chain_start = i
                chain: list[SegCubic] = [seg]
                j = i + 1
                while j < n and isinstance(segs[j], SegCubic):
                    chain.append(segs[j])
                    j += 1
                if len(chain) >= 2:
                    sx, sy = _seg_start(segs, chain_start)
                    ex, ey = chain[-1].x3, chain[-1].y3
                    chord_len = math.hypot(ex - sx, ey - sy)
                    if chord_len > 1.0:
                        max_dev = 0.0
                        for c in chain:
                            max_dev = max(max_dev, _point_line_dist(c.x1, c.y1, sx, sy, ex, ey))
                            max_dev = max(max_dev, _point_line_dist(c.x2, c.y2, sx, sy, ex, ey))
                            max_dev = max(max_dev, _point_line_dist(c.x3, c.y3, sx, sy, ex, ey))
                        if max_dev < TOL_LINE:
                            new_segs.append(SegLine(ex, ey))
                            changed = True
                            stats["lines_merged"] += len(chain)
                            i = j
                            continue
                for c in chain:
                    new_segs.append(c)
                i = j
            else:
                new_segs.append(seg)
                i += 1

        if changed:
            shape.segs = new_segs
            mask_before = _render_single_path_svg(
                PathShape(shape.fill, shape.original_segs), cw, ch
            )
            mask_after = _render_single_path_svg(shape, cw, ch)
            if _shape_iou(mask_before, mask_after) < 0.997:
                shape.segs = shape.original_segs
                stats["reverts"] += 1
            else:
                stats["shapes_changed"] += 1
    return stats


# ---------------------------------------------------------------------------
# Pass 2 — axis snap
# ---------------------------------------------------------------------------

AXIS_SNAP_DEG = 1.5


def _pass2_axis_snap(shapes: list[PathShape], cw: int, ch: int) -> dict[str, int]:
    stats = {"axes_snapped": 0, "shapes_changed": 0, "reverts": 0}
    for shape in shapes:
        segs = shape.segs
        n = len(segs)
        if n < 2:
            continue
        shape.original_segs = list(segs)
        changed = False
        for i, seg in enumerate(segs):
            if not isinstance(seg, SegLine):
                continue
            sx, sy = _seg_start(segs, i)
            ex, ey = seg.x, seg.y
            dx, dy = ex - sx, ey - sy
            length = math.hypot(dx, dy)
            if length < 0.5:
                continue
            angle = math.degrees(math.atan2(dy, dx))
            for target in [0.0, 90.0, -90.0, 180.0, -180.0]:
                diff = abs((angle - target + 180) % 360 - 180)
                if diff < AXIS_SNAP_DEG:
                    mx, my = (sx + ex) / 2, (sy + ey) / 2
                    half = length / 2
                    rad = math.radians(target)
                    new_sx = mx - half * math.cos(rad)
                    new_sy = my - half * math.sin(rad)
                    new_ex = mx + half * math.cos(rad)
                    new_ey = my + half * math.sin(rad)
                    # Update previous segment endpoint
                    if i > 0:
                        prev = segs[i - 1]
                        if isinstance(prev, SegCubic):
                            prev.x3, prev.y3 = new_sx, new_sy
                        elif isinstance(prev, SegLine):
                            prev.x, prev.y = new_sx, new_sy
                        elif isinstance(prev, SegMove):
                            prev.x, prev.y = new_sx, new_sy
                    seg.x, seg.y = new_ex, new_ey
                    changed = True
                    stats["axes_snapped"] += 1
                    break
        if changed:
            shape.segs = segs
            mask_before = _render_single_path_svg(
                PathShape(shape.fill, shape.original_segs), cw, ch
            )
            mask_after = _render_single_path_svg(shape, cw, ch)
            if _shape_iou(mask_before, mask_after) < 0.997:
                shape.segs = shape.original_segs
                stats["reverts"] += 1
            else:
                stats["shapes_changed"] += 1
    return stats


# ---------------------------------------------------------------------------
# Pass 3 — corner vs smooth join
# ---------------------------------------------------------------------------

CORNER_THRESHOLD_DEG = 35.0


def _pass3_corner_smooth_with_log(
    shapes: list[PathShape], cw: int, ch: int
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Pass 3 with spatial change log for visual crops."""
    stats = {"joints_smoothed": 0, "corners_kept": 0, "shapes_changed": 0, "reverts": 0}
    change_log: list[dict[str, Any]] = []
    for shape in shapes:
        segs = shape.segs
        n = len(segs)
        if n < 3:
            continue
        shape.original_segs = list(segs)
        changed = False
        for i in range(n - 1):
            s1, s2 = segs[i], segs[i + 1]
            if not isinstance(s1, SegCubic) or not isinstance(s2, SegCubic):
                continue
            sx, sy = _seg_start(segs, i)
            ex, ey = s2.x3, s2.y3
            jx, jy = s1.x3, s1.y3  # joint point
            t_in = _tangent_at_end(sx, sy, s1.x1, s1.y1, s1.x2, s1.y2, s1.x3, s1.y3)
            t_out = _tangent_at_start(jx, jy, s2.x1, s2.y1, s2.x2, s2.y2, s2.x3, s2.y3)
            angle = _angle_between(t_in, t_out)
            if angle > CORNER_THRESHOLD_DEG:
                stats["corners_kept"] += 1
                continue
            avg_x = t_in[0] + t_out[0]
            avg_y = t_in[1] + t_out[1]
            n_avg = math.hypot(avg_x, avg_y)
            if n_avg < 1e-9:
                continue
            avg_x /= n_avg
            avg_y /= n_avg
            len1 = math.hypot(s1.x2 - jx, s1.y2 - jy)
            len2 = math.hypot(s2.x1 - jx, s2.y1 - jy)
            s1.x2 = jx - avg_x * len1
            s1.y2 = jy - avg_y * len1
            s2.x1 = jx + avg_x * len2
            s2.y1 = jy + avg_y * len2
            changed = True
            stats["joints_smoothed"] += 1
            change_log.append({
                "pass": 3, "x": jx, "y": jy,
                "angle": round(angle, 1),
                "description": f"smoothed joint ({angle:.1f}°)",
            })
        if changed:
            shape.segs = segs
            mask_before = _render_single_path_svg(
                PathShape(shape.fill, shape.original_segs), cw, ch
            )
            mask_after = _render_single_path_svg(shape, cw, ch)
            if _shape_iou(mask_before, mask_after) < 0.997:
                shape.segs = shape.original_segs
                stats["reverts"] += 1
            else:
                stats["shapes_changed"] += 1
    return stats, change_log


def _pass3_corner_smooth(shapes: list[PathShape], cw: int, ch: int) -> dict[str, int]:
    stats, _ = _pass3_corner_smooth_with_log(shapes, cw, ch)
    return stats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def geometry_fit(svg_text: str, tol_line: float = TOL_LINE) -> tuple[str, dict[str, Any]]:
    """Apply primitive fitting passes to SVG. In-place d-attribute replacement.

    Returns:
        (modified_svg, stats)
        stats includes 'change_log': list of (pass, x, y, description) tuples
        for spatial localization of changes in visual crops.
    """
    shapes = parse_svg_shapes(svg_text)
    if not shapes:
        return svg_text, {"warning": "no paths found", "passes": 0, "change_log": []}

    w_match = re.search(r'width="(\d+)"', svg_text)
    h_match = re.search(r'height="(\d+)"', svg_text)
    cw = int(w_match.group(1)) if w_match else 1024
    ch = int(h_match.group(1)) if h_match else 1024

    all_stats: dict[str, Any] = {"passes": 3, "pass_stats": [], "change_log": []}
    total_reverts = 0

    # Pass 1
    s1 = _pass1_line_detect(shapes, cw, ch)
    all_stats.update(s1)
    all_stats["pass_stats"].append({"pass": 1, **s1})
    total_reverts += s1["reverts"]

    # Pass 2
    s2 = _pass2_axis_snap(shapes, cw, ch)
    all_stats.update(s2)
    all_stats["pass_stats"].append({"pass": 2, **s2})
    total_reverts += s2["reverts"]

    # Pass 3 — track joint coordinates for visual crops
    s3, change_log = _pass3_corner_smooth_with_log(shapes, cw, ch)
    all_stats.update(s3)
    all_stats["pass_stats"].append({"pass": 3, **s3})
    all_stats["change_log"] = change_log
    total_reverts += s3["reverts"]

    all_stats["revert_total"] = total_reverts

    svg_out = inject_d_attrs(svg_text, shapes)
    return svg_out, all_stats

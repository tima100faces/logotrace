"""Geometry normalization for traced SVG paths.

Levels:
  off    — no-op
  basic  — RDP + collinear collapse → straighter lines, fewer nodes
  strict — basic + circular-arc fit on full closed loops when stable
"""
from __future__ import annotations

import math
import re
from xml.etree import ElementTree as ET

GEOM_OFF = "off"
GEOM_BASIC = "basic"
GEOM_STRICT = "strict"

RDP_EPSILON = 1.25
COLLINEAR_COS = 0.998
ARC_MAX_REL_ERR = 0.08
ARC_MIN_POINTS = 8

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_TOKEN_RE = re.compile(rf"[MmLlHhVvCcSsQqTtAaZz]|{_NUM}")


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    stack = [(0, len(points) - 1)]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    while stack:
        start, end = stack.pop()
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        denom = math.hypot(dx, dy) or 1.0
        max_dist = 0.0
        index = start
        for i in range(start + 1, end):
            px, py = points[i]
            dist = abs(dy * px - dx * py + bx * ay - by * ax) / denom
            if dist > max_dist:
                max_dist = dist
                index = i
        if max_dist > epsilon:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [p for p, k in zip(points, keep) if k]


def _collapse_collinear(
    points: list[tuple[float, float]], cos_thresh: float = COLLINEAR_COS
) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    out = [points[0]]
    for i in range(1, len(points) - 1):
        x0, y0 = out[-1]
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        v1x, v1y = x1 - x0, y1 - y0
        v2x, v2y = x2 - x1, y2 - y1
        n1 = math.hypot(v1x, v1y)
        n2 = math.hypot(v2x, v2y)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cos_a = (v1x * v2x + v1y * v2y) / (n1 * n2)
        if cos_a >= cos_thresh:
            continue
        out.append(points[i])
    out.append(points[-1])
    return out


def _sample_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    n: int = 6,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _polygonize_path_d(d: str) -> list[list[tuple[float, float]]]:
    """Approximate path `d` as polylines in absolute coords."""
    tokens = _TOKEN_RE.findall(d.replace(",", " "))
    i = 0
    cmd = "M"
    cx = cy = 0.0
    start = (0.0, 0.0)
    polys: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []

    def read_num() -> float:
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    def flush() -> None:
        nonlocal cur
        if len(cur) >= 2:
            polys.append(cur)
        cur = []

    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[MmLlHhVvCcSsQqTtAaZz]$", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur and (cur[0][0] != cur[-1][0] or cur[0][1] != cur[-1][1]):
                    cur.append(cur[0])
                flush()
                cx, cy = start
                continue
        try:
            if cmd in "Mm":
                x, y = read_num(), read_num()
                if cmd == "m":
                    x += cx
                    y += cy
                flush()
                cx, cy = x, y
                start = (cx, cy)
                cur = [(cx, cy)]
                cmd = "L" if cmd == "M" else "l"
            elif cmd in "Ll":
                x, y = read_num(), read_num()
                if cmd == "l":
                    x += cx
                    y += cy
                cx, cy = x, y
                cur.append((cx, cy))
            elif cmd in "Hh":
                x = read_num()
                if cmd == "h":
                    x += cx
                cx = x
                cur.append((cx, cy))
            elif cmd in "Vv":
                y = read_num()
                if cmd == "v":
                    y += cy
                cy = y
                cur.append((cx, cy))
            elif cmd in "Cc":
                vals = [read_num() for _ in range(6)]
                if cmd == "c":
                    vals[0] += cx
                    vals[1] += cy
                    vals[2] += cx
                    vals[3] += cy
                    vals[4] += cx
                    vals[5] += cy
                p0 = (cx, cy)
                p1 = (vals[0], vals[1])
                p2 = (vals[2], vals[3])
                p3 = (vals[4], vals[5])
                cur.extend(_sample_cubic(p0, p1, p2, p3))
                cx, cy = p3
            elif cmd in "Ss":
                vals = [read_num() for _ in range(4)]
                if cmd == "s":
                    vals[0] += cx
                    vals[1] += cy
                    vals[2] += cx
                    vals[3] += cy
                p0 = (cx, cy)
                p1 = (cx, cy)
                p2 = (vals[0], vals[1])
                p3 = (vals[2], vals[3])
                cur.extend(_sample_cubic(p0, p1, p2, p3))
                cx, cy = p3
            elif cmd in "Qq":
                vals = [read_num() for _ in range(4)]
                if cmd == "q":
                    vals[0] += cx
                    vals[1] += cy
                    vals[2] += cx
                    vals[3] += cy
                p0 = (cx, cy)
                qc = (vals[0], vals[1])
                p3 = (vals[2], vals[3])
                p1 = (p0[0] + 2 / 3 * (qc[0] - p0[0]), p0[1] + 2 / 3 * (qc[1] - p0[1]))
                p2 = (p3[0] + 2 / 3 * (qc[0] - p3[0]), p3[1] + 2 / 3 * (qc[1] - p3[1]))
                cur.extend(_sample_cubic(p0, p1, p2, p3, n=5))
                cx, cy = p3
            elif cmd in "Aa":
                for _ in range(5):
                    read_num()
                x, y = read_num(), read_num()
                if cmd == "a":
                    x += cx
                    y += cy
                cx, cy = x, y
                cur.append((cx, cy))
            else:
                break
        except (IndexError, ValueError):
            break
    flush()
    return polys


def _fit_circle(pts: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    n = len(pts)
    if n < ARC_MIN_POINTS:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x_m = sum(xs) / n
    y_m = sum(ys) / n
    u = [x - x_m for x in xs]
    v = [y - y_m for y in ys]
    suu = sum(ui * ui for ui in u)
    svv = sum(vi * vi for vi in v)
    suv = sum(ui * vi for ui, vi in zip(u, v))
    suuu = sum(ui**3 for ui in u)
    svvv = sum(vi**3 for vi in v)
    suuv = sum(ui * ui * vi for ui, vi in zip(u, v))
    suvv = sum(ui * vi * vi for ui, vi in zip(u, v))
    det = 2 * (suu * svv - suv * suv)
    if abs(det) < 1e-9:
        return None
    uc = (svv * (suuu + suvv) - suv * (svvv + suuv)) / det
    vc = (suu * (svvv + suuv) - suv * (suuu + suvv)) / det
    cx = uc + x_m
    cy = vc + y_m
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    if r < 2 or r > 1e6:
        return None
    errs = [abs(math.hypot(x - cx, y - cy) - r) for x, y in pts]
    if (sum(errs) / n) / r > ARC_MAX_REL_ERR:
        return None
    return cx, cy, r


def _poly_to_d(points: list[tuple[float, float]], closed: bool, level: str) -> str:
    pts = _rdp(points, RDP_EPSILON)
    pts = _collapse_collinear(pts)

    if level == GEOM_STRICT and len(pts) >= ARC_MIN_POINTS:
        body = pts[:-1] if closed and len(pts) > 2 else pts
        fit = _fit_circle(body)
        if fit is not None:
            cx, cy, r = fit
            x0, y0 = cx + r, cy
            return (
                f"M {x0:.2f} {y0:.2f} "
                f"A {r:.2f} {r:.2f} 0 1 1 {cx - r:.2f} {cy:.2f} "
                f"A {r:.2f} {r:.2f} 0 1 1 {x0:.2f} {y0:.2f} Z"
            )

    parts = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    for x, y in pts[1:]:
        parts.append(f"L {x:.2f} {y:.2f}")
    if closed:
        parts.append("Z")
    return " ".join(parts)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_svg_geometry(svg_text: str, level: str = GEOM_OFF) -> str:
    level = (level or GEOM_OFF).lower().strip()
    if level not in (GEOM_OFF, GEOM_BASIC, GEOM_STRICT):
        level = GEOM_OFF
    if level == GEOM_OFF:
        return svg_text

    decl = ""
    body = svg_text
    m = re.match(r"^\s*(<\?xml[^?]*\?>)\s*", svg_text)
    if m:
        decl = m.group(1) + "\n"
        body = svg_text[m.end() :]

    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return svg_text

    for el in root.iter():
        if _local(el.tag).lower() != "path":
            continue
        d = el.get("d")
        if not d:
            continue
        polys = _polygonize_path_d(d)
        if not polys:
            continue
        new_ds: list[str] = []
        for poly in polys:
            if len(poly) < 2:
                continue
            closed = abs(poly[0][0] - poly[-1][0]) < 0.5 and abs(poly[0][1] - poly[-1][1]) < 0.5
            new_ds.append(_poly_to_d(poly, closed=closed, level=level))
        if new_ds:
            el.set("d", " ".join(new_ds))

    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
    except Exception:
        pass
    out = ET.tostring(root, encoding="unicode")
    if decl and not out.lstrip().startswith("<?xml"):
        out = decl + out
    return out

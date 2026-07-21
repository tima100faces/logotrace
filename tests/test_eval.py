"""Tests for eval harness: metric correctness on synthetic fixtures."""

import numpy as np
from PIL import Image

from src.eval import (
    _chamfer_distance,
    _color_mask,
    _count_svg_nodes,
    _edge_map,
)


# ---------------------------------------------------------------------------
# Color mask (IoU helper)
# ---------------------------------------------------------------------------

def test_color_mask_perfect_match():
    """A solid-color block: mask should cover it entirely."""
    arr = np.full((20, 20, 3), (100, 150, 200), dtype=np.uint8)
    mask = _color_mask(arr, (100, 150, 200), radius=20)
    assert mask.sum() == 400  # all 400 pixels


def test_color_mask_excludes_distant():
    """A different color should produce empty mask."""
    arr = np.full((20, 20, 3), (255, 0, 0), dtype=np.uint8)
    mask = _color_mask(arr, (0, 255, 0), radius=20)
    assert mask.sum() == 0


def test_color_mask_radius_boundary():
    """Pixels within radius match, pixels beyond don't."""
    arr = np.full((3, 3, 3), (0, 0, 0), dtype=np.uint8)
    # center pixel at distance 0, corners at distance ~35 (√(25²×3))
    arr[1, 1] = (30, 0, 0)  # dist 30 from red
    arr[0, 0] = (100, 0, 0)  # dist 100 from red
    mask = _color_mask(arr, (0, 0, 0), radius=40)
    # center (30 away) should match, corner (100 away) should not
    assert mask[1, 1]
    assert not mask[0, 0]


# ---------------------------------------------------------------------------
# Edge map
# ---------------------------------------------------------------------------

def test_edge_map_blank_image():
    """Uniform image has no edges."""
    arr = np.full((30, 30, 3), (128, 128, 128), dtype=np.uint8)
    edges = _edge_map(arr)
    assert edges.sum() == 0


def test_edge_map_sharp_boundary():
    """Half-black half-white image has an edge along the boundary."""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[:, 20:] = 255
    edges = _edge_map(arr)
    # Should have at least some edge pixels near the boundary
    assert edges.sum() > 5
    # Edge should be concentrated near column 20
    edge_cols = np.where(edges)[1]
    assert abs(edge_cols.mean() - 20) < 5


# ---------------------------------------------------------------------------
# Chamfer distance
# ---------------------------------------------------------------------------

def test_chamfer_perfect_match_zero():
    """Identical edge maps → Chamfer ≈ 0."""
    a = np.zeros((50, 50), dtype=bool)
    a[10, 10:20] = True  # small horizontal line
    b = a.copy()
    d = _chamfer_distance(a, b)
    assert d < 0.1


def test_chamfer_known_shift():
    """Edge shifted by N pixels → Chamfer ≈ N."""
    a = np.zeros((60, 60), dtype=bool)
    a[20, 10:30] = True  # horizontal line at row 20
    b = np.zeros((60, 60), dtype=bool)
    b[25, 10:30] = True  # same line at row 25 (5 px shift)
    d = _chamfer_distance(a, b)
    assert 4.5 <= d <= 5.5, f"expected ~5, got {d}"


def test_chamfer_empty_source():
    """Empty edge set a → inf."""
    a = np.zeros((20, 20), dtype=bool)
    b = np.ones((20, 20), dtype=bool)
    d = _chamfer_distance(a, b)
    assert d == float("inf")


# ---------------------------------------------------------------------------
# Node count
# ---------------------------------------------------------------------------

def test_count_svg_nodes_simple():
    svg = '<svg><path d="M 0 0 L 10 10 C 15 15 20 20 25 25 Z"/></svg>'
    assert _count_svg_nodes(svg) == 4  # M, L, C, Z


def test_count_svg_nodes_multiple_paths():
    svg = '<svg><path d="M 0 0 L 1 1"/><path d="M 2 2 C 3 3 4 4 5 5 Q 6 6 7 7 Z"/></svg>'
    assert _count_svg_nodes(svg) == 6  # M,L + M,C,Q,Z = 6


def test_count_svg_nodes_empty_d():
    svg = '<svg><path d=""/></svg>'
    assert _count_svg_nodes(svg) == 0


# ---------------------------------------------------------------------------
# Synthetic round-trip: perfect reconstruction → IoU = 1.0
# ---------------------------------------------------------------------------

def test_synthetic_iou_perfect():
    """Two solid-color rectangles — perfect self-comparison gives IoU 1.0."""
    from src.eval import _color_mask

    w, h = 80, 60
    arr = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)
    arr[5:25, 5:35] = (200, 50, 50)  # red rect
    arr[30:55, 40:75] = (20, 80, 200)  # blue rect
    palette = [(200, 50, 50), (20, 80, 200)]

    ious = []
    for color in palette:
        ref = _color_mask(arr, color)
        trc = _color_mask(arr, color)
        i = ref & trc
        u = ref | trc
        if u.sum() > 0:
            ious.append(i.sum() / u.sum())

    assert len(ious) == 2
    assert all(abs(io - 1.0) < 0.01 for io in ious), f"expected ~1.0, got {ious}"


def test_synthetic_shifted_rect_iou():
    """Red rect shifted by 2 px → IoU should be measurably lower than 1.0."""
    from src.eval import _color_mask

    w, h = 80, 60
    ref = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)
    ref[10:30, 10:40] = (200, 50, 50)

    trc = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)
    trc[12:32, 12:42] = (200, 50, 50)  # shifted by +2,+2

    ref_mask = _color_mask(ref, (200, 50, 50))
    trc_mask = _color_mask(trc, (200, 50, 50))
    intersection = (ref_mask & trc_mask).sum()
    union = (ref_mask | trc_mask).sum()
    iou = intersection / union if union > 0 else 0

    assert 0.5 < iou < 0.95, f"expected partial overlap, got {iou}"

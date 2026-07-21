"""Tests for eval harness: metric correctness on synthetic fixtures."""

from pathlib import Path

import numpy as np
import pytest

from src.eval import (
    _binarize,
    _chamfer_distance,
    _color_mask,
    _count_svg_nodes,
    _edge_map,
    _hungarian_pair,
    self_test_sample,
)


SAMPLES = Path(__file__).resolve().parents[1] / "input"


# ---------------------------------------------------------------------------
# Binarization
# ---------------------------------------------------------------------------

def test_binarize_snaps_to_nearest():
    """Each pixel maps to exactly one palette color."""
    arr = np.full((10, 10, 3), (128, 128, 128), dtype=np.uint8)
    arr[0, 0] = (200, 50, 50)
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    out = _binarize(arr, palette)
    # All gray pixels → nearest is (255,0,0) since all are equally far
    # (128,128,128) - dist² to (255,0,0) = 127²+128²+128² = 48897
    # to (0,255,0) = 128²+127²+128² = 48897 — same distance
    # The pixel at (0,0) → (200,50,50) → nearest (255,0,0)
    assert out.shape == (10, 10, 3)
    # Every output pixel must be exactly one of the palette colors
    for px in out.reshape(-1, 3):
        assert tuple(px) in palette


def test_binarize_preserves_shape():
    arr = np.zeros((5, 7, 3), dtype=np.uint8)
    palette = [(0, 0, 0)]
    out = _binarize(arr, palette)
    assert out.shape == (5, 7, 3)


# ---------------------------------------------------------------------------
# Color mask (exact match on binarized image)
# ---------------------------------------------------------------------------

def test_color_mask_perfect_match():
    """On a binarized image, exact match finds all pixels of a color."""
    arr = np.full((20, 20, 3), (100, 150, 200), dtype=np.uint8)
    arr[5:15, 5:15] = (255, 0, 0)
    mask = _color_mask(arr, (255, 0, 0))
    assert mask.sum() == 100  # 10×10 red block


def test_color_mask_excludes_different():
    """Different color returns zero mask."""
    arr = np.full((10, 10, 3), (255, 0, 0), dtype=np.uint8)
    mask = _color_mask(arr, (0, 255, 0))
    assert mask.sum() == 0


# ---------------------------------------------------------------------------
# Hungarian pairing
# ---------------------------------------------------------------------------

def test_hungarian_identical_palettes():
    """Same palette → 1:1 pairing."""
    pal = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    pairs = _hungarian_pair(pal, pal)
    assert len(pairs) == 3
    assert pairs == [(0, 0), (1, 1), (2, 2)]


def test_hungarian_missing_color():
    """One color missing in output → that color is unmatched."""
    ref = [(255, 0, 0), (0, 255, 0)]
    out = [(255, 0, 0)]  # green missing
    pairs = _hungarian_pair(ref, out)
    assert len(pairs) == 1  # only red paired
    assert pairs[0] == (0, 0)  # ref[0] → out[0]


def test_hungarian_permuted():
    """Output palette in different order → correct pairing by distance."""
    ref = [(255, 0, 0), (0, 255, 0)]
    out = [(0, 255, 0), (255, 0, 0)]  # reversed
    pairs = _hungarian_pair(ref, out)
    assert len(pairs) == 2
    # ref[0] red → out[1] red, ref[1] green → out[0] green
    assert (0, 1) in pairs
    assert (1, 0) in pairs


# ---------------------------------------------------------------------------
# Edge map (on binarized images)
# ---------------------------------------------------------------------------

def test_edge_map_uniform():
    """Uniform image → no edges."""
    arr = np.full((30, 30, 3), (128, 128, 128), dtype=np.uint8)
    edges = _edge_map(arr)
    assert edges.sum() == 0


def test_edge_map_sharp_boundary():
    """Half-red half-blue → edge along the boundary."""
    arr = np.full((40, 40, 3), (255, 0, 0), dtype=np.uint8)
    arr[:, 20:] = (0, 0, 255)  # blue right half
    edges = _edge_map(arr)
    assert edges.sum() > 10
    # Edge should be near column 20
    edge_cols = np.where(edges)[1]
    assert abs(float(edge_cols.mean()) - 20) < 3


# ---------------------------------------------------------------------------
# Chamfer distance
# ---------------------------------------------------------------------------

def test_chamfer_perfect_match_zero():
    """Identical edge maps → Chamfer ≈ 0."""
    a = np.zeros((50, 50), dtype=bool)
    a[10, 10:20] = True
    d = _chamfer_distance(a, a)
    assert d < 0.01


def test_chamfer_known_shift():
    """Edge shifted by 5 px → Chamfer ≈ 5."""
    a = np.zeros((60, 60), dtype=bool)
    a[20, 10:30] = True
    b = np.zeros((60, 60), dtype=bool)
    b[25, 10:30] = True
    d = _chamfer_distance(a, b)
    assert 4.5 <= d <= 5.5, f"expected ~5, got {d}"


def test_chamfer_empty_source():
    """Empty edge set → 0.0 (no edges to compare = no distance)."""
    a = np.zeros((20, 20), dtype=bool)
    b = np.ones((20, 20), dtype=bool)
    d = _chamfer_distance(a, b)
    assert d == 0.0


# ---------------------------------------------------------------------------
# Node count
# ---------------------------------------------------------------------------

def test_count_svg_nodes_simple():
    svg = '<svg><path d="M 0 0 L 10 10 C 15 15 20 20 25 25 Z"/></svg>'
    assert _count_svg_nodes(svg) == 4


def test_count_svg_nodes_multiple_paths():
    svg = '<svg><path d="M 0 0 L 1 1"/><path d="M 2 2 C 3 3 4 4 5 5 Q 6 6 7 7 Z"/></svg>'
    assert _count_svg_nodes(svg) == 6


def test_count_svg_nodes_empty_d():
    svg = '<svg><path d=""/></svg>'
    assert _count_svg_nodes(svg) == 0


# ---------------------------------------------------------------------------
# Synthetic IoU: binarized self-comparison → perfect 1.0
# ---------------------------------------------------------------------------

def test_synthetic_iou_perfect():
    """Binarized image measured against itself → IoU = 1.0 per color."""
    palette = [(200, 50, 50), (20, 80, 200)]
    arr = np.full((60, 80, 3), (255, 255, 255), dtype=np.uint8)
    arr[5:25, 5:35] = palette[0]
    arr[30:55, 40:75] = palette[1]

    for c in palette:
        mask = _color_mask(arr, c)
        ref_mask = _color_mask(arr, c)
        inter = (mask & ref_mask).sum()
        union = (mask | ref_mask).sum()
        if union > 0:
            iou = inter / union
            assert abs(iou - 1.0) < 0.01, f"color {c}: IoU={iou}"


def test_synthetic_shifted_rect_iou():
    """Shifted rect → partial overlap → IoU measurably < 1.0."""
    color = (200, 50, 50)
    ref = np.full((60, 80, 3), (255, 255, 255), dtype=np.uint8)
    ref[10:30, 10:40] = color
    trc = np.full((60, 80, 3), (255, 255, 255), dtype=np.uint8)
    trc[12:32, 12:42] = color

    ref_mask = _color_mask(ref, color)
    trc_mask = _color_mask(trc, color)
    inter = (ref_mask & trc_mask).sum()
    union = (ref_mask | trc_mask).sum()
    iou = inter / union
    assert 0.5 < iou < 0.95, f"expected partial IoU, got {iou}"


# ---------------------------------------------------------------------------
# Regression: self-test on every sample must give IoU=1.0, Chamfer=0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "sample_01.jpg", "sample_02.jpg", "sample_03.jpg", "sample_04.jpg",
    "sample_05.jpg", "sample_06.jpg", "sample_07.jpg", "sample_08.jpg",
])
def test_self_test_perfect_on_all_samples(name: str):
    """Canonical reference measured against itself → perfect metrics.

    This test catches palette mismatch bugs: if the harness uses different
    palettes for reference and output, even self-comparison fails.
    """
    src = SAMPLES / name
    if not src.is_file():
        pytest.skip(f"{name} missing")
    r = self_test_sample(src)
    assert r["iou_mean"] == 1.0, f"{name}: self-test IoU must be 1.0"
    assert r["chamfer"] is not None and r["chamfer"] < 0.01, f"{name}: self-test Chamfer must be 0"

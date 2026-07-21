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
    _eval_palette_and_mode,
    _hungarian_pair,
    _masks_identical,
    evaluate_sample,
    self_test_sample,
)


SAMPLES = Path(__file__).resolve().parents[1] / "input"


# ---------------------------------------------------------------------------
# Binarization
# ---------------------------------------------------------------------------

def test_binarize_snaps_to_nearest():
    arr = np.full((10, 10, 3), (128, 128, 128), dtype=np.uint8)
    arr[0, 0] = (200, 50, 50)
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    out = _binarize(arr, palette)
    assert out.shape == (10, 10, 3)
    for px in out.reshape(-1, 3):
        assert tuple(px) in palette


def test_binarize_preserves_shape():
    arr = np.zeros((5, 7, 3), dtype=np.uint8)
    palette = [(0, 0, 0)]
    out = _binarize(arr, palette)
    assert out.shape == (5, 7, 3)


# ---------------------------------------------------------------------------
# Color mask
# ---------------------------------------------------------------------------

def test_color_mask_perfect_match():
    arr = np.full((20, 20, 3), (100, 150, 200), dtype=np.uint8)
    arr[5:15, 5:15] = (255, 0, 0)
    mask = _color_mask(arr, (255, 0, 0))
    assert mask.sum() == 100


def test_color_mask_excludes_different():
    arr = np.full((10, 10, 3), (255, 0, 0), dtype=np.uint8)
    mask = _color_mask(arr, (0, 255, 0))
    assert mask.sum() == 0


# ---------------------------------------------------------------------------
# Hungarian pairing
# ---------------------------------------------------------------------------

def test_hungarian_identical_palettes():
    pal = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    pairs = _hungarian_pair(pal, pal)
    assert len(pairs) == 3
    assert pairs == [(0, 0), (1, 1), (2, 2)]


def test_hungarian_missing_color():
    ref = [(255, 0, 0), (0, 255, 0)]
    out = [(255, 0, 0)]
    pairs = _hungarian_pair(ref, out)
    assert len(pairs) == 1
    assert pairs[0] == (0, 0)


def test_hungarian_permuted():
    ref = [(255, 0, 0), (0, 255, 0)]
    out = [(0, 255, 0), (255, 0, 0)]
    pairs = _hungarian_pair(ref, out)
    assert len(pairs) == 2
    assert (0, 1) in pairs
    assert (1, 0) in pairs


# ---------------------------------------------------------------------------
# Edge map
# ---------------------------------------------------------------------------

def test_edge_map_uniform():
    arr = np.full((30, 30, 3), (128, 128, 128), dtype=np.uint8)
    edges = _edge_map(arr)
    assert edges.sum() == 0


def test_edge_map_sharp_boundary():
    arr = np.full((40, 40, 3), (255, 0, 0), dtype=np.uint8)
    arr[:, 20:] = (0, 0, 255)
    edges = _edge_map(arr)
    assert edges.sum() > 10
    edge_cols = np.where(edges)[1]
    assert abs(float(edge_cols.mean()) - 20) < 3


# ---------------------------------------------------------------------------
# Chamfer distance
# ---------------------------------------------------------------------------

def test_chamfer_perfect_match_zero():
    a = np.zeros((50, 50), dtype=bool)
    a[10, 10:20] = True
    d = _chamfer_distance(a, a)
    assert d < 0.01


def test_chamfer_known_shift():
    a = np.zeros((60, 60), dtype=bool)
    a[20, 10:30] = True
    b = np.zeros((60, 60), dtype=bool)
    b[25, 10:30] = True
    d = _chamfer_distance(a, b)
    assert 4.5 <= d <= 5.5, f"expected ~5, got {d}"


def test_chamfer_empty_source():
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
# Background detection
# ---------------------------------------------------------------------------

def test_eval_palette_paper_mode():
    """White-background image → paper mode with bg class."""
    arr = np.full((60, 80, 3), (255, 255, 255), dtype=np.uint8)
    arr[10:30, 10:40] = (200, 50, 50)  # red ink
    inks = [(200, 50, 50)]
    eval_pal, mode = _eval_palette_and_mode(inks, arr)
    assert mode == "paper"
    assert len(eval_pal) == 2  # ink + bg
    # bg should be near white (255,255,255)
    bg = eval_pal[1]
    assert bg[0] > 200 and bg[1] > 200 and bg[2] > 200


def test_eval_palette_fullbleed():
    """All-dark image with bg ≈ ink → fullbleed, no bg class."""
    arr = np.full((60, 80, 3), (30, 30, 30), dtype=np.uint8)
    arr[10:30, 10:40] = (200, 50, 50)
    inks = [(200, 50, 50)]
    eval_pal, mode = _eval_palette_and_mode(inks, arr)
    assert mode == "fullbleed"
    assert len(eval_pal) == 1  # inks only


# ---------------------------------------------------------------------------
# Masks identical
# ---------------------------------------------------------------------------

def test_masks_identical_true():
    a = np.full((10, 10, 3), (128, 128, 128), dtype=np.uint8)
    assert _masks_identical(a, a.copy())


def test_masks_identical_false():
    a = np.full((10, 10, 3), (128, 128, 128), dtype=np.uint8)
    b = a.copy()
    b[0, 0] = (255, 0, 0)
    assert not _masks_identical(a, b)


# ---------------------------------------------------------------------------
# Degenerate detection via evaluate_sample
# ---------------------------------------------------------------------------

def test_single_ink_paper_mode_not_perfect():
    """Single-ink on white bg: masks must differ → not degenerate."""
    src = SAMPLES / "sample_03.jpg"
    if not src.is_file():
        pytest.skip("sample_03 missing")
    r = evaluate_sample(src)
    assert not r.get("degenerate"), f"sample_03 should not be degenerate with bg class: {r}"
    # With background class, single-ink should have meaningful edges
    assert r["mode"] == "paper" or r["mode"] == "fullbleed"
    if r["mode"] == "paper":
        assert r["iou_mean"] is not None and r["iou_mean"] < 0.99, \
            f"paper single-ink should be <1.0, got {r['iou_mean']}"
    if r["iou_bg"] is not None:
        assert r["iou_bg"] < 1.0, f"bg IoU should be measurable, got {r['iou_bg']}"


# ---------------------------------------------------------------------------
# Area-weighted IoU + per-mask detail
# ---------------------------------------------------------------------------

def test_per_mask_area_and_iou_aw():
    """Per-mask area % and area-weighted IoU are computed correctly."""
    src = SAMPLES / "sample_02.jpg"
    if not src.is_file():
        pytest.skip("sample_02 missing")
    r = evaluate_sample(src, dump_diffs_dir=None)
    masks = r.get("per_mask", [])
    assert len(masks) >= 2, f"should have ink+bg masks, got {masks}"

    # Area percentages should sum to ~100%
    total_area = sum(m["area_pct"] for m in masks)
    assert 99.0 < total_area < 101.0, f"area sum {total_area}%"

    # Area-weighted IoU should differ from mean when areas are skewed
    iou_aw = r.get("iou_aw")
    iou_mean = r.get("iou_mean")
    assert iou_aw is not None
    # For paper mode: bg has large area, small masks drag mean down
    if r["mode"] == "paper":
        assert iou_aw > iou_mean, f"aw={iou_aw} should be > mean={iou_mean} (bg dominates)"


def test_upscale_variants_run():
    """Each upscale variant produces results without crashing."""
    src = SAMPLES / "sample_01.jpg"
    if not src.is_file():
        pytest.skip("sample_01 missing")
    for variant in ["off", "2x", "4x", "4x-smooth"]:
        r = evaluate_sample(src, upscale=variant)
        assert r["render_ok"], f"{variant} render failed"
        assert r["iou_mean"] is not None, f"{variant} IoU is None"
        assert r["elapsed"] is not None


def test_upscale_svg_scaling():
    """_wrap_svg_scaled correctly wraps SVG with transform and fixes viewport."""
    from src.eval import _wrap_svg_scaled

    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><path d="M 10 10"/></svg>'
    scaled = _wrap_svg_scaled(svg, 4, 100, 100)
    assert 'scale(0.25' in scaled
    assert 'width="100"' in scaled
    assert 'height="100"' in scaled
    assert '<g transform=' in scaled
    assert '</g>' in scaled
    assert '<path' in scaled


def test_upscale_noop():
    """off variant returns same result as no upscale."""
    from src.eval import _wrap_svg_scaled
    svg = "<svg><path/></svg>"
    assert _wrap_svg_scaled(svg, 1, 100, 100) == svg

# ---------------------------------------------------------------------------
# Regression: self-test on every sample
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "sample_01.jpg", "sample_02.jpg", "sample_03.jpg", "sample_04.jpg",
    "sample_05.jpg", "sample_06.jpg", "sample_07.jpg", "sample_08.jpg",
])
def test_self_test_perfect_on_all_samples(name: str):
    """Canonical reference measured against itself → perfect metrics."""
    src = SAMPLES / name
    if not src.is_file():
        pytest.skip(f"{name} missing")
    r = self_test_sample(src)
    assert r["iou_mean"] == 1.0, f"{name}: self-test IoU must be 1.0"
    assert r["chamfer"] < 0.01, f"{name}: self-test Chamfer must be 0"


def test_large_image_auto_returns_result_not_none():
    """Image larger than upscale cap → auto returns result with eff=1.0."""
    from src.eval import _compute_effective_scale, _upscale_image
    from PIL import Image
    # 4000×3000 — longest side > 3072 cap, pixels > 9.5M
    img = Image.new("RGB", (4000, 3000), (128, 128, 128))
    up_img, eff = _upscale_image(img, "auto")
    assert eff == 1.0, f"expected eff=1.0 for oversize image, got {eff}"
    assert up_img.size == img.size, "image must be unchanged (no upscale)"

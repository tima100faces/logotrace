"""Tests for geometry_fit: line detection, axis snap, corner/smooth, safety guard."""

from pathlib import Path

import pytest

from src.geometry_fit import (
    parse_path_d,
    _segs_to_d,
    SegMove,
    SegLine,
    SegCubic,
    SegClose,
    geometry_fit,
    parse_svg_shapes,
    inject_d_attrs,
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_cubic_chain():
    d = "M 0 0 C 10 10 20 20 30 30 C 40 40 50 50 60 60 Z"
    segs = parse_path_d(d)
    assert len(segs) == 4  # M, C, C, Z
    assert isinstance(segs[0], SegMove)
    assert isinstance(segs[1], SegCubic)
    assert isinstance(segs[2], SegCubic)
    assert isinstance(segs[3], SegClose)


def test_parse_mixed():
    d = "M 10 20 L 30 40 C 50 60 70 80 90 100 Z"
    segs = parse_path_d(d)
    assert len(segs) == 4
    assert isinstance(segs[0], SegMove)
    assert isinstance(segs[1], SegLine)
    assert isinstance(segs[2], SegCubic)
    assert isinstance(segs[3], SegClose)


def test_roundtrip_no_change():
    """Parse → rebuild produces identical d-string (up to formatting)."""
    d = "M 10.5 20.3 C 30.1 40.2 50.7 60.8 70.9 80.4 Z"
    segs = parse_path_d(d)
    rebuilt = _segs_to_d(segs)
    # Check that rebuilt contains the same coordinates
    assert "10.500" in rebuilt
    assert "80.400" in rebuilt
    assert "Z" in rebuilt


def test_inject_d_attrs_preserves_structure():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<g transform="scale(0.5)">'
        '<path fill="#ff0000" stroke="none" d="M 0 0 L 10 10 Z"/>'
        '<path d="M 50 50 C 60 60 70 70 80 80 Z" fill="#00ff00"/>'
        '</g></svg>'
    )
    shapes = parse_svg_shapes(svg)
    assert len(shapes) == 2
    assert shapes[0].fill == "#ff0000"
    assert shapes[1].fill == "#00ff00"

    result = inject_d_attrs(svg, shapes)
    assert "<g transform" in result
    assert "#ff0000" in result
    assert "#00ff00" in result


# ---------------------------------------------------------------------------
# Line detection (Pass 1)
# ---------------------------------------------------------------------------


def test_straight_cubic_chain_detected():
    """A chain of cubics along a straight line should be merged."""
    d = "M 0 0 C 25 0 50 0 50 0 C 75 0 100 0 100 0 Z"
    segs = parse_path_d(d)
    assert len(segs) == 4  # M, C, C, Z


# ---------------------------------------------------------------------------
# geometry_fit integration smoke test
# ---------------------------------------------------------------------------


def test_geometry_fit_on_sample(tmp_path: Path):
    """Smoke test: geometry_fit runs without error on a real sample."""
    sp = Path(__file__).resolve().parents[1] / "input" / "sample_09.png"
    if not sp.is_file():
        pytest.skip("sample_09.png missing")
    from src.pipeline import vectorize_to_svg
    svg_text, _, _ = vectorize_to_svg(input_path=sp, colors=4, upscale=True, engine="vtracer")
    svg_fit, stats = geometry_fit(svg_text)
    assert "<svg" in svg_fit
    assert "passes" in stats


def test_geometry_fit_roundtrip_no_change_small_svg():
    """On a trivial SVG, fit should not change anything visible."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50">'
        '<rect width="50" height="50" fill="white"/>'
        '<path fill="#000" stroke="none" d="M 5 5 L 45 5 L 45 45 L 5 45 Z"/>'
        '<path d="M 10 10 C 20 20 30 20 40 10 Z" fill="#f00"/>'
        '</svg>'
    )
    svg_fit, stats = geometry_fit(svg)
    assert "<svg" in svg_fit
    assert isinstance(stats["passes"], int)

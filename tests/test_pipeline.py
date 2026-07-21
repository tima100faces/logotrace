from pathlib import Path

import pytest
from PIL import Image

from src.colors import extract_logo_colors, remap_to_palette
from src.config import DEFAULT_COLORS
from src.pipeline import VectorizeError, vectorize_bytes, vectorize_file, vectorize_to_svg
from src.tracer_vtracer import resolve_vtracer_bin


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _make_tiny_logo(path: Path) -> None:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(10, 54):
        for y in range(10, 54):
            img.putpixel((x, y), (20, 20, 200, 255))
    for x in range(20, 44):
        for y in range(20, 44):
            img.putpixel((x, y), (220, 40, 40, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


@pytest.fixture(scope="session")
def tiny_logo() -> Path:
    path = FIXTURES / "tiny_logo.png"
    if not path.is_file():
        _make_tiny_logo(path)
    return path


def test_default_colors_is_four():
    assert DEFAULT_COLORS == 4


def test_vtracer_binary_resolves():
    assert resolve_vtracer_bin()


def test_extract_two_colors_on_white():
    img = Image.new("RGB", (80, 80), (255, 255, 255))
    for x in range(10, 40):
        for y in range(10, 70):
            img.putpixel((x, y), (200, 30, 30))
    for x in range(45, 70):
        for y in range(10, 70):
            img.putpixel((x, y), (20, 20, 20))
    pal = extract_logo_colors(img, max_colors=4)
    assert len(pal) >= 2
    # should include something reddish and something dark
    assert any(r > 150 and g < 100 for r, g, b in pal)
    assert any(r < 80 and g < 80 and b < 80 for r, g, b in pal)


def test_remap_keeps_palette(tiny_logo: Path):
    img = Image.open(tiny_logo)
    pal = extract_logo_colors(img, 2)
    out = remap_to_palette(img, pal, keep_alpha=True)
    assert out.mode in ("RGB", "RGBA")


def test_vectorize_svg_string(tiny_logo: Path):
    svg, pal = vectorize_to_svg(input_path=tiny_logo, colors=2)
    assert "<svg" in svg.lower()
    assert "</svg>" in svg.lower()
    assert len(pal) >= 1


def test_vectorize_file_pdf(tiny_logo: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    path = vectorize_file(tiny_logo, colors=2, output_path=out, fmt="pdf")
    assert path == out
    data = out.read_bytes()
    assert data.startswith(b"%PDF")


def test_vectorize_bytes_pdf(tiny_logo: Path):
    data = vectorize_bytes(tiny_logo.read_bytes(), colors=2, fmt="pdf")
    assert data.startswith(b"%PDF")


def test_vectorize_bad_colors(tiny_logo: Path):
    with pytest.raises(VectorizeError):
        vectorize_file(tiny_logo, colors=0)


@pytest.mark.parametrize("name", ["sample_06.jpg", "sample_07.jpg"])
def test_multi_color_samples_keep_multiple_fills(name: str, tmp_path: Path):
    """Problem cases: should not collapse to a single ink fill."""
    import re

    src = SAMPLES / name
    if not src.is_file():
        pytest.skip("sample missing")
    svg_path = tmp_path / f"{name}.svg"
    vectorize_file(src, colors=4, output_path=svg_path, fmt="svg")
    svg = svg_path.read_text(encoding="utf-8")
    fills = set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg, flags=re.I))
    # drop near-white fills
    ink = []
    for f in fills:
        h = f.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if r >= 230 and g >= 230 and b >= 230:
            continue
        ink.append((r, g, b))
    assert len(ink) >= 2, f"{name} ink fills={ink} all={fills}"

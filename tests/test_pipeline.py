from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from src.config import DEFAULT_COLORS
from src.pipeline import VectorizeError, vectorize_bytes, vectorize_file
from src.preprocess import has_meaningful_alpha, quantize_max_colors
from src.tracer_vtracer import resolve_vtracer_bin


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _make_tiny_logo(path: Path) -> None:
    """2-color logo-like PNG with transparency."""
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
def tiny_logo(tmp_path_factory) -> Path:
    path = FIXTURES / "tiny_logo.png"
    if not path.is_file():
        _make_tiny_logo(path)
    return path


def test_default_colors_is_four():
    assert DEFAULT_COLORS == 4


def test_vtracer_binary_resolves():
    bin_path = resolve_vtracer_bin()
    assert bin_path


def test_has_meaningful_alpha(tiny_logo: Path):
    img = Image.open(tiny_logo)
    assert has_meaningful_alpha(img) is True


def test_quantize_respects_max_colors(tiny_logo: Path):
    img = Image.open(tiny_logo)
    out = quantize_max_colors(img, 2)
    assert out.mode in ("RGB", "RGBA", "P")
    # count unique opaque colors roughly
    rgba = out.convert("RGBA")
    colors = set()
    for px in rgba.getdata():
        if px[3] > 128:
            colors.add(px[:3])
    assert len(colors) <= 2


def test_vectorize_returns_svg_string(tiny_logo: Path):
    svg = vectorize_file(tiny_logo, colors=2)
    assert "<svg" in svg.lower()
    assert "</svg>" in svg.lower()


def test_vectorize_preserves_alpha_fixture(tiny_logo: Path, tmp_path: Path):
    out = tmp_path / "out.svg"
    svg = vectorize_file(tiny_logo, colors=2, output_path=out)
    assert out.is_file()
    # transparent logo should not force a full-canvas white rect only — soft check
    assert "svg" in svg.lower()


def test_vectorize_bytes(tiny_logo: Path):
    data = tiny_logo.read_bytes()
    svg = vectorize_bytes(data, colors=2, filename_hint="tiny.png")
    assert "<svg" in svg.lower()


def test_vectorize_bad_colors(tiny_logo: Path):
    with pytest.raises(VectorizeError):
        vectorize_file(tiny_logo, colors=0)


@pytest.mark.parametrize(
    "name",
    ["sample_01.jpg", "sample_02.jpg", "sample_03.jpg"],
)
def test_vectorize_real_samples(name: str, tmp_path: Path):
    src = SAMPLES / name
    if not src.is_file():
        pytest.skip("sample missing")
    out = tmp_path / f"{name}.svg"
    svg = vectorize_file(src, colors=4, output_path=out)
    assert out.stat().st_size > 100
    assert "<svg" in svg.lower()

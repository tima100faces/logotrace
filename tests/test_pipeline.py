from pathlib import Path

import pytest
from PIL import Image

from src.colors import (
    COLORS_MODE_EXACT,
    COLORS_MODE_UP_TO,
    analyze_palette,
    collapse_gradient_ramps,
    extract_logo_colors,
    remap_to_palette,
)
from src.config import DEFAULT_COLORS
from src.geometry import GEOM_BASIC, GEOM_OFF, normalize_svg_geometry
from src.pipeline import VectorizeError, vectorize_bytes, vectorize_file, vectorize_to_svg
from src.tracer_vtracer import resolve_vtracer_bin


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = Path(__file__).resolve().parents[1] / "input"


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
    assert any(r > 150 and g < 100 for r, g, b in pal)
    assert any(r < 80 and g < 80 and b < 80 for r, g, b in pal)


def test_exact_mode_collapses_to_n():
    img = Image.new("RGB", (120, 80), (255, 255, 255))
    # three ink blobs
    for x in range(5, 35):
        for y in range(5, 75):
            img.putpixel((x, y), (200, 20, 20))
    for x in range(40, 70):
        for y in range(5, 75):
            img.putpixel((x, y), (20, 20, 20))
    for x in range(75, 110):
        for y in range(5, 75):
            img.putpixel((x, y), (20, 180, 40))
    up = analyze_palette(img, 4, colors_mode=COLORS_MODE_UP_TO)
    ex = analyze_palette(img, 2, colors_mode=COLORS_MODE_EXACT)
    assert len(up.colors) >= 2
    # exact, max_colors=2 → bg + 2 inks = 3 total
    assert len(ex.colors) == 3
    assert ex.colors[0] == (255, 255, 255)  # bg is always first


def test_mass_aware_keeps_two_close_majors():
    """Two large regions with distinct hues must both survive."""
    img = Image.new("RGB", (100, 60), (255, 255, 255))
    for x in range(5, 45):
        for y in range(5, 55):
            img.putpixel((x, y), (200, 40, 40))  # red
    for x in range(55, 95):
        for y in range(5, 55):
            img.putpixel((x, y), (40, 50, 190))  # blue
    pal = analyze_palette(img, 4, colors_mode=COLORS_MODE_UP_TO).colors
    assert len(pal) >= 2


def test_gradient_grays_collapse_to_one_ink():
    cols = [(20, 20, 20), (60, 60, 60), (100, 100, 100), (160, 160, 160), (210, 40, 40)]
    out = collapse_gradient_ramps(cols, max_colors=4)
    grays = [c for c in out if max(c) - min(c) < 40]
    assert len(grays) == 1
    assert any(c[0] > 150 for c in out)  # red kept


def test_resolve_palette_policy_auto_and_manual():
    from src.colors import resolve_palette_policy

    n, m = resolve_palette_policy(colors="auto", colors_mode="auto")
    assert (n, m) == (4, COLORS_MODE_UP_TO)
    n, m = resolve_palette_policy(colors=2, colors_mode="auto")
    assert (n, m) == (2, COLORS_MODE_EXACT)
    n, m = resolve_palette_policy(colors=4, colors_mode=COLORS_MODE_UP_TO)
    assert (n, m) == (4, COLORS_MODE_UP_TO)


def test_sample_05_exact_two_keeps_dual_gray():
    """Manual exact 2 → black + mid-gray. Auto up_to keeps bimodal grays (≥2)."""
    src = SAMPLES / "sample_05.jpg"
    if not src.is_file():
        pytest.skip("sample_05 missing")
    auto = analyze_palette(Image.open(src), 4, colors_mode=COLORS_MODE_UP_TO).colors
    exact = analyze_palette(Image.open(src), 2, colors_mode=COLORS_MODE_EXACT).colors
    # Auto with bimodal guard now keeps both gray masses (skip crush)
    assert len(auto) >= 2, f"auto should detect bimodal, got {auto}"
    assert len(exact) >= 2
    lights = sorted(sum(c) / 3 for c in exact)
    assert lights[0] < 80  # dark
    assert lights[1] > 60  # mid gray distinct


def test_remap_keeps_palette(tiny_logo: Path):
    img = Image.open(tiny_logo)
    pal = extract_logo_colors(img, 2)
    out = remap_to_palette(img, pal, keep_alpha=True)
    assert out.mode in ("RGB", "RGBA")


def test_geom_basic_reduces_nodes():
    # wavy almost-line path
    d = "M 0 0 " + " ".join(
        f"C {i+1} {0.2 if i % 2 else -0.2} {i+2} {0.2 if i % 2 else -0.2} {i+3} 0"
        for i in range(0, 30, 3)
    )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{d}" fill="#000"/></svg>'
    out = normalize_svg_geometry(svg, level=GEOM_BASIC)
    assert "<path" in out
    # should prefer L commands after normalize
    assert "L " in out or "l " in out.lower() or out.count("C") < svg.count("C")


def test_vectorize_svg_string(tiny_logo: Path):
    svg, pal, _eff = vectorize_to_svg(input_path=tiny_logo, colors=2, geom=GEOM_OFF)
    assert "<svg" in svg.lower()
    assert "</svg>" in svg.lower()
    assert len(pal) >= 1


def test_vectorize_file_pdf(tiny_logo: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    path = vectorize_file(tiny_logo, colors=2, output_path=out, fmt="pdf", geom=GEOM_OFF)
    assert path == out
    assert out.read_bytes().startswith(b"%PDF")


def test_vectorize_bytes_pdf(tiny_logo: Path):
    data, _eff = vectorize_bytes(tiny_logo.read_bytes(), colors=2, fmt="pdf", geom=GEOM_OFF)
    assert data.startswith(b"%PDF")


def test_vectorize_bad_colors(tiny_logo: Path):
    with pytest.raises(VectorizeError):
        vectorize_file(tiny_logo, colors=0)


@pytest.mark.parametrize("name", ["sample_06.jpg", "sample_07.jpg"])
def test_multi_color_samples_keep_multiple_fills(name: str, tmp_path: Path):
    import re

    src = SAMPLES / name
    if not src.is_file():
        pytest.skip("sample missing")
    svg_path = tmp_path / f"{name}.svg"
    vectorize_file(src, colors=4, output_path=svg_path, fmt="svg", geom=GEOM_OFF)
    svg = svg_path.read_text(encoding="utf-8")
    fills = set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg, flags=re.I))
    ink = []
    for f in fills:
        h = f.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if r >= 230 and g >= 230 and b >= 230:
            continue
        ink.append((r, g, b))
    assert len(ink) >= 2, f"{name} ink fills={ink} all={fills}"

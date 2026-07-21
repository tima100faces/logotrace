from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from src.api import app

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _ensure_fixture() -> Path:
    path = FIXTURES / "tiny_logo.png"
    if not path.is_file():
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        for x in range(4, 28):
            for y in range(4, 28):
                img.putpixel((x, y), (0, 0, 200, 255))
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
    return path


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_vectorize_endpoint_pdf():
    path = _ensure_fixture()
    client = TestClient(app)
    with path.open("rb") as f:
        r = client.post(
            "/vectorize",
            files={"file": ("tiny.png", f, "image/png")},
            data={"palette": "2", "format": "pdf"},
        )
    assert r.status_code == 200, r.text
    assert "pdf" in r.headers.get("content-type", "").lower()
    assert r.content.startswith(b"%PDF")
    assert r.headers.get("X-LogoTrace-Colors") == "2"
    assert r.headers.get("X-LogoTrace-Colors-Mode") == "exact"


def test_vectorize_palette_auto_header():
    path = _ensure_fixture()
    client = TestClient(app)
    with path.open("rb") as f:
        r = client.post(
            "/vectorize",
            files={"file": ("tiny.png", f, "image/png")},
            data={"palette": "auto", "format": "pdf"},
        )
    assert r.status_code == 200, r.text
    assert r.headers.get("X-LogoTrace-Colors-Mode") == "up_to"

from fastapi.testclient import TestClient

from src.api import app
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_vectorize_endpoint():
    path = FIXTURES / "tiny_logo.png"
    if not path.is_file():
        from PIL import Image

        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        for x in range(4, 28):
            for y in range(4, 28):
                img.putpixel((x, y), (0, 0, 200, 255))
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)

    client = TestClient(app)
    with path.open("rb") as f:
        r = client.post(
            "/vectorize",
            files={"file": ("tiny.png", f, "image/png")},
            data={"colors": "2"},
        )
    assert r.status_code == 200, r.text
    assert "svg" in r.headers.get("content-type", "").lower()
    assert "<svg" in r.text.lower()

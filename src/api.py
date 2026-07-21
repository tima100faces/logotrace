from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from src.colors import COLORS_MODE_EXACT, COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS, MAX_COLORS, MAX_UPLOAD_BYTES, MIN_COLORS
from src.geometry import GEOM_BASIC, GEOM_OFF, GEOM_STRICT
from src.pipeline import VectorizeError, vectorize_bytes

app = FastAPI(title="LogoTrace", version="0.3.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    colors: int = Form(DEFAULT_COLORS),
    colors_mode: str = Form(COLORS_MODE_UP_TO),
    format: str = Form("pdf"),
    geom: str = Form(GEOM_OFF),
) -> Response:
    if colors < MIN_COLORS or colors > MAX_COLORS:
        raise HTTPException(
            status_code=400,
            detail=f"colors must be {MIN_COLORS}..{MAX_COLORS}",
        )
    fmt = format.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise HTTPException(status_code=400, detail="format must be pdf or svg")
    cm = colors_mode.lower().strip()
    if cm not in (COLORS_MODE_UP_TO, COLORS_MODE_EXACT):
        raise HTTPException(status_code=400, detail="colors_mode must be up_to or exact")
    gl = geom.lower().strip()
    if gl not in (GEOM_OFF, GEOM_BASIC, GEOM_STRICT):
        raise HTTPException(status_code=400, detail="geom must be off|basic|strict")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    name = file.filename or "upload.png"
    try:
        payload = vectorize_bytes(
            data,
            colors=colors,
            colors_mode=cm,
            filename_hint=name,
            fmt=fmt,
            geom=gl,
        )
    except VectorizeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if fmt == "pdf":
        return Response(
            content=payload,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="logotrace.pdf"'},
        )
    return Response(
        content=payload,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'attachment; filename="logotrace.svg"'},
    )


@app.exception_handler(Exception)
async def unhandled(_request, exc: Exception):  # type: ignore[no-untyped-def]
    return JSONResponse(status_code=500, content={"detail": str(exc)})

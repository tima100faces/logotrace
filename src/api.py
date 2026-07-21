from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from src.config import DEFAULT_COLORS, MAX_COLORS, MAX_UPLOAD_BYTES, MIN_COLORS
from src.pipeline import VectorizeError, vectorize_bytes

app = FastAPI(title="LogoTrace", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    colors: int = Form(DEFAULT_COLORS),
) -> Response:
    if colors < MIN_COLORS or colors > MAX_COLORS:
        raise HTTPException(
            status_code=400,
            detail=f"colors must be {MIN_COLORS}..{MAX_COLORS}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    name = file.filename or "upload.png"
    try:
        svg = vectorize_bytes(data, colors=colors, filename_hint=name)
    except VectorizeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'attachment; filename="logotrace.svg"'},
    )


@app.exception_handler(Exception)
async def unhandled(_request, exc: Exception):  # type: ignore[no-untyped-def]
    return JSONResponse(status_code=500, content={"detail": str(exc)})

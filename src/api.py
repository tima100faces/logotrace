from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from src.colors import COLORS_MODE_AUTO, resolve_palette_policy
from src.config import DEFAULT_COLORS, MAX_UPLOAD_BYTES
from src.geometry import GEOM_BASIC, GEOM_OFF, GEOM_STRICT
from src.pipeline import VectorizeError, vectorize_bytes

app = FastAPI(
    title="LogoTrace",
    version="0.4.0",
    description=(
        "Flat logo → RGB PDF. "
        "Form palette=auto (smart up_to) or palette=1..N (exact manual). "
        "Legacy: colors + colors_mode=up_to|exact|auto."
    ),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.4.0"}


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    palette: str = Form("auto"),
    colors: str | None = Form(None),
    colors_mode: str = Form(COLORS_MODE_AUTO),
    format: str = Form("pdf"),
    geom: str = Form(GEOM_OFF),
) -> Response:
    fmt = format.lower().strip()
    if fmt not in ("pdf", "svg"):
        raise HTTPException(status_code=400, detail="format must be pdf or svg")
    gl = geom.lower().strip()
    if gl not in (GEOM_OFF, GEOM_BASIC, GEOM_STRICT):
        raise HTTPException(status_code=400, detail="geom must be off|basic|strict")

    # Prefer legacy `colors` when provided; else UI `palette`.
    raw = colors if (colors is not None and str(colors).strip() != "") else palette
    try:
        n, cm = resolve_palette_policy(
            colors=raw,
            colors_mode=colors_mode,
            default_colors=DEFAULT_COLORS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    name = file.filename or "upload.png"
    try:
        payload = vectorize_bytes(
            data,
            colors=n,
            colors_mode=cm,
            filename_hint=name,
            fmt=fmt,
            geom=gl,
        )
    except VectorizeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    headers = {
        "X-LogoTrace-Colors": str(n),
        "X-LogoTrace-Colors-Mode": cm,
    }
    if fmt == "pdf":
        headers["Content-Disposition"] = 'attachment; filename="logotrace.pdf"'
        return Response(content=payload, media_type="application/pdf", headers=headers)
    headers["Content-Disposition"] = 'attachment; filename="logotrace.svg"'
    return Response(content=payload, media_type="image/svg+xml", headers=headers)


@app.exception_handler(Exception)
async def unhandled(_request, exc: Exception):  # type: ignore[no-untyped-def]
    return JSONResponse(status_code=500, content={"detail": str(exc)})

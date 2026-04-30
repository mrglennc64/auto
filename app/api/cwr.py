"""CWR v2.1 generation endpoint — Phase 1 scaffold.

Status: scaffold only. The actual CWR builder is intentionally not
implemented yet. Two known options:

  (a) Port the working JS generator from
      /root/traproyalties-new/packages/frontend (TRP cwr-generator route)
      into a Python module here. That generator's output has been
      validated by the operator as CISAC-compliant.

  (b) License/integrate a third-party CWR validator (CISAC CIS-Net or
      equivalent) and call it from this endpoint.

Until one of those is wired up, the endpoint accepts requests and
returns 501 with a clear note. Wire-up plan when the builder lands:

  POST /api/cwr/generate
    Headers: X-API-Key: <tenant key>
    Body (multipart):
      cleaned_catalog_csv: <file>            # output of /api/upload/corrections
      submitter_name:      <str>             # HDR record submitter
      submitter_ipi:       <11-digit str>    # HDR sender IPI
      target_pro:          <enum: ASCAP|BMI|SESAC|STIM|...>   # routing
      collection_scope:    <enum: WORLDWIDE|LOCAL|CUSTOM>     # share basis
    Returns:
      200 application/octet-stream  (the .v21 file)
      400 with structured error if the catalog is malformed
      422 with structured error if CWR validation fails before emit
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.services.auth import verify_api_key


router = APIRouter()


TargetPRO = Literal["ASCAP", "BMI", "SESAC", "STIM", "PRS", "GEMA", "SACEM", "OTHER"]
CollectionScope = Literal["WORLDWIDE", "LOCAL", "CUSTOM"]


@router.get("/cwr/health")
def cwr_health() -> dict[str, str]:
    """Cheap probe so the front-end can detect the endpoint exists."""
    return {"status": "scaffold", "implemented": "no", "see_module_docstring": "yes"}


@router.post("/cwr/generate")
async def generate_cwr(
    cleaned_catalog_csv: UploadFile = File(...),
    submitter_name: str = Form(..., min_length=1, max_length=45),
    submitter_ipi: str = Form(..., min_length=9, max_length=11),
    target_pro: str = Form(...),
    collection_scope: str = Form(default="WORLDWIDE"),
    custom_share_bp: int | None = Form(default=None, description="basis points (10000 = 100%)"),
    api_key: str = Depends(verify_api_key),
) -> Response:
    # Validate enums up-front so callers get a useful error before we touch the body.
    if target_pro not in {"ASCAP", "BMI", "SESAC", "STIM", "PRS", "GEMA", "SACEM", "OTHER"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown target_pro: {target_pro!r}")
    if collection_scope not in {"WORLDWIDE", "LOCAL", "CUSTOM"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown collection_scope: {collection_scope!r}")
    if collection_scope == "CUSTOM" and (custom_share_bp is None or not (0 <= custom_share_bp <= 10000)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="custom_share_bp must be 0..10000 when scope=CUSTOM")
    if not submitter_ipi.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="submitter_ipi must be all digits")

    # Body is read here so the endpoint can later swap to a real builder
    # without changing the call shape.
    body = await cleaned_catalog_csv.read()
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty catalog file")

    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": "not_implemented",
            "message": (
                "CWR builder is not wired up yet. The endpoint shape is final; "
                "swap the implementation when the validated generator lands."
            ),
            "got": {
                "submitter_name": submitter_name,
                "submitter_ipi": submitter_ipi,
                "target_pro": target_pro,
                "collection_scope": collection_scope,
                "custom_share_bp": custom_share_bp,
                "catalog_bytes": len(body),
            },
        },
    )

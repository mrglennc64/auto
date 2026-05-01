"""CWR v2.1 generation endpoint.

Wires the partner-facing /api/cwr/generate POST to the production-tested
``cwr_builder.build_cwr`` (a Python port of the TRP cwr-generator with
STIM-specific corrections — see app/services/cwr_builder.py docstring).

Input shape (multipart):
  cleaned_catalog_csv: <file>            output of /api/upload/corrections,
                                          columns: title, iswc, isrc, name,
                                          role, share_percent, ipi, society
  submitter_name:      <str>             HDR record submitter
  submitter_ipi:       <11-digit str>    HDR sender IPI
  target_pro:          ASCAP|BMI|SESAC|STIM|PRS|GEMA|SACEM|OTHER
  collection_scope:    WORLDWIDE|LOCAL|CUSTOM   default WORLDWIDE
  custom_share_bp:     <int 0..10000>    required when scope=CUSTOM
                                          (basis points; 10000 = 100%)

Returns 200 application/octet-stream with the .v21 file body, or:
  400 with structured error if the inputs are malformed
  422 with structured error if a CWR validation rule fails
"""
from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.services.auth import verify_api_key
from app.services.cwr_builder import CwrValidationError, build_cwr


router = APIRouter()


TargetPRO = Literal["ASCAP", "BMI", "SESAC", "STIM", "PRS", "GEMA", "SACEM", "OTHER"]
CollectionScope = Literal["WORLDWIDE", "LOCAL", "CUSTOM"]

# Local-collection territory codes (CISAC TIS). Used when scope=LOCAL.
_LOCAL_TERRITORY_BY_PRO: dict[str, str] = {
    "STIM": "752",   # Sweden
    "ASCAP": "840",  # USA
    "BMI": "840",
    "SESAC": "840",
    "GMR": "840",
    "PRS": "826",    # UK
    "GEMA": "276",   # Germany
    "SACEM": "250",  # France
}
_WORLDWIDE_TERRITORY = "2136"


@router.get("/cwr/health")
def cwr_health() -> dict[str, str]:
    """Cheap probe so the front-end can detect the endpoint is wired up."""
    return {"status": "ok", "implemented": "yes"}


def _parse_cleaned_csv(body: bytes) -> list[dict]:
    """Group the cleaned-catalog CSV rows into the works-dict shape that
    ``build_cwr`` expects. One work per distinct title; one contributor
    entry per row."""
    text = body.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="CSV has no header row")

    expected = {"title", "name"}
    missing = expected - {(c or "").strip().lower() for c in reader.fieldnames}
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"CSV missing required columns: {sorted(missing)}",
        )

    # Normalize header lookup so `Title` and `title` both work.
    def col(row: dict, name: str) -> str:
        for k, v in row.items():
            if (k or "").strip().lower() == name:
                return (v or "").strip()
        return ""

    works: dict[str, dict] = {}
    work_seq = 0
    for row in reader:
        title = col(row, "title")
        if not title:
            continue
        if title not in works:
            work_seq += 1
            works[title] = {
                "id": f"W{work_seq:08d}",
                "title": title,
                "iswc": col(row, "iswc"),
                "isrc": col(row, "isrc"),
                "duration": "000000",
                "contributors": [],
            }
        share_raw = col(row, "share_percent") or col(row, "share")
        try:
            share = float((share_raw or "0").replace(",", ".").replace("%", ""))
        except ValueError:
            share = 0.0
        works[title]["contributors"].append({
            "name_clean": col(row, "name"),
            "name_raw": col(row, "name"),
            "ipi": col(row, "ipi"),
            "role": (col(row, "role") or "CA").upper(),
            "share": share,
            "society": col(row, "society") or "STIM",
        })

    if not works:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="CSV had no rows with a title")
    return list(works.values())


def _territories_for(scope: str, target_pro: str) -> list[str]:
    if scope == "WORLDWIDE":
        return [_WORLDWIDE_TERRITORY]
    if scope == "LOCAL":
        return [_LOCAL_TERRITORY_BY_PRO.get(target_pro, _WORLDWIDE_TERRITORY)]
    # CUSTOM: territory falls back to worldwide; the partner's choice is
    # in publisher_share_bp, not in the territory list.
    return [_WORLDWIDE_TERRITORY]


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
    if target_pro not in {"ASCAP", "BMI", "SESAC", "STIM", "PRS", "GEMA", "SACEM", "OTHER"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown target_pro: {target_pro!r}")
    if collection_scope not in {"WORLDWIDE", "LOCAL", "CUSTOM"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown collection_scope: {collection_scope!r}")
    if collection_scope == "CUSTOM" and (custom_share_bp is None or not (0 <= custom_share_bp <= 10000)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="custom_share_bp must be 0..10000 when scope=CUSTOM")
    if not submitter_ipi.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="submitter_ipi must be all digits")

    body = await cleaned_catalog_csv.read()
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty catalog file")

    works = _parse_cleaned_csv(body)
    territories = _territories_for(collection_scope, target_pro)
    publisher_share_bp = custom_share_bp if (collection_scope == "CUSTOM" and custom_share_bp is not None) else 3333
    publisher_pro = "STIM" if target_pro == "OTHER" else target_pro

    try:
        cwr_text = build_cwr(
            works=works,
            submitter=submitter_name,
            sender_ipi=submitter_ipi,
            publisher_ipi=submitter_ipi,
            publisher_name=submitter_name,
            publisher_pro=publisher_pro,
            territories=territories,
            publisher_share_bp=publisher_share_bp,
        )
    except CwrValidationError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "cwr_validation_failed", "message": str(exc)},
        )

    return Response(
        content=cwr_text,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="cwr-package.v21"'},
    )

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.models import File as FileRow, Job
from app.models.db import session_scope
from app.services import storage
from app.services.auth import verify_api_key
from app.workers.analyze import analyze_catalog

router = APIRouter()


@router.post("/upload/catalog")
async def upload_catalog(
    file: UploadFile = File(...),
    publisher_id: str = Form(...),
    publisher_email: str = Form(""),
    catalog_name: str = Form(""),
    api_key: str = Depends(verify_api_key),
) -> dict[str, str]:
    body = await file.read()

    job_id = uuid.uuid4()
    s3_key = storage.put_object(
        "original_catalogs",
        str(job_id),
        file.filename or "catalog.csv",
        body,
        content_type=file.content_type or "text/csv",
    )

    with session_scope() as s:
        s.add(
            Job(
                id=job_id,
                publisher_id=publisher_id,
                publisher_email=publisher_email or None,
                catalog_name=catalog_name or None,
                phase="analysis",
                status="pending",
            )
        )
        s.add(FileRow(job_id=job_id, role="original_catalog", s3_key=s3_key))

    analyze_catalog.delay(str(job_id))

    return {"job_id": str(job_id), "status": "queued", "catalog_name": catalog_name}

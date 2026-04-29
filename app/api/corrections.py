from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.models import CorrectionJob, File as FileRow, Job
from app.models.db import session_scope
from app.services import storage
from app.services.auth import verify_api_key
from app.workers.correct import apply_corrections

router = APIRouter()


@router.post("/upload/corrections")
async def upload_corrections(
    job_id: str = Form(...),
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key),
) -> dict[str, str]:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="job_id must be a UUID") from exc

    body = await file.read()

    with session_scope() as s:
        job = s.get(Job, job_uuid)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.phase != "awaiting_corrections":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"job phase is {job.phase!r}, expected 'awaiting_corrections'",
            )

    s3_key = storage.put_object(
        "corrections_uploaded",
        str(job_uuid),
        file.filename or "corrections.csv",
        body,
        content_type=file.content_type or "text/csv",
    )

    correction_job_id = uuid.uuid4()
    with session_scope() as s:
        s.add(CorrectionJob(id=correction_job_id, job_id=job_uuid, status="pending"))
        s.add(FileRow(job_id=job_uuid, role="corrections_uploaded", s3_key=s3_key))
        s.get(Job, job_uuid).phase = "correction"

    apply_corrections.delay(str(correction_job_id))

    return {"correction_job_id": str(correction_job_id), "status": "queued"}

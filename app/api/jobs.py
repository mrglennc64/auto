from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.models import File as FileRow, Issue, Job, Report, Work
from app.models.db import session_scope
from app.services import storage
from app.services.auth import verify_api_key

router = APIRouter()


def _parse_uuid(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="job_id must be a UUID") from exc


@router.get("/jobs/{job_id}/status")
def job_status(job_id: str, api_key: str = Depends(verify_api_key)) -> dict[str, str]:
    job_uuid = _parse_uuid(job_id)
    with session_scope() as s:
        job = s.get(Job, job_uuid)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
        return {"job_id": str(job.id), "phase": job.phase, "status": job.status}


@router.get("/jobs/{job_id}/results")
def job_results(job_id: str, api_key: str = Depends(verify_api_key)) -> dict:
    job_uuid = _parse_uuid(job_id)
    with session_scope() as s:
        job = s.get(Job, job_uuid)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")

        report = s.scalars(
            select(Report).where(Report.job_id == job_uuid, Report.type == "before")
        ).one_or_none()
        template = s.scalars(
            select(FileRow).where(
                FileRow.job_id == job_uuid, FileRow.role == "correction_template"
            )
        ).one_or_none()
        works_count = s.scalar(select(func.count()).select_from(Work).where(Work.job_id == job_uuid)) or 0
        issues_count = s.scalar(select(func.count()).select_from(Issue).where(Issue.job_id == job_uuid)) or 0
        blocking_count = s.scalar(
            select(func.count()).select_from(Issue).where(
                Issue.job_id == job_uuid, Issue.severity == "blocking"
            )
        ) or 0

        return {
            "job_id": str(job_uuid),
            "phase": job.phase,
            "status": job.status,
            "health_report_before_url": storage.presigned_url(report.s3_key) if report else None,
            "correction_template_url": storage.presigned_url(template.s3_key) if template else None,
            "summary": {
                "works": int(works_count),
                "issues": int(issues_count),
                "blocking": int(blocking_count),
                "resolvable": int(issues_count) - int(blocking_count),
            },
        }


@router.get("/jobs/{job_id}/after")
def job_after(job_id: str, api_key: str = Depends(verify_api_key)) -> dict:
    job_uuid = _parse_uuid(job_id)
    with session_scope() as s:
        job = s.get(Job, job_uuid)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")

        report = s.scalars(
            select(Report).where(Report.job_id == job_uuid, Report.type == "after")
        ).one_or_none()
        cleaned = s.scalars(
            select(FileRow).where(FileRow.job_id == job_uuid, FileRow.role == "corrected_catalog")
        ).one_or_none()

        return {
            "job_id": str(job_uuid),
            "phase": job.phase,
            "status": job.status,
            "health_report_after_url": storage.presigned_url(report.s3_key) if report else None,
            "corrected_catalog_url": storage.presigned_url(cleaned.s3_key) if cleaned else None,
        }

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select

from app.models import (
    File as FileRow,
    Issue,
    Job,
    Notification,
    Report,
)
from app.models.db import session_scope
from app.services import storage
from app.services.auth import verify_dashboard_basic
from app.services.email import send_via_resend

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_index(request: Request, _user: str = Depends(verify_dashboard_basic)) -> HTMLResponse:
    with session_scope() as s:
        jobs = s.scalars(select(Job).order_by(desc(Job.created_at)).limit(50)).all()
        rows = []
        for j in jobs:
            issues_count = s.scalar(
                select(__import__("sqlalchemy").func.count())
                .select_from(Issue)
                .where(Issue.job_id == j.id)
            ) or 0
            pending_drafts = s.scalar(
                select(__import__("sqlalchemy").func.count())
                .select_from(Notification)
                .where(Notification.job_id == j.id, Notification.status == "pending")
            ) or 0
            rows.append(
                {
                    "id": str(j.id),
                    "publisher_id": j.publisher_id,
                    "publisher_email": j.publisher_email or "—",
                    "catalog_name": j.catalog_name or "—",
                    "phase": j.phase,
                    "status": j.status,
                    "created_at": j.created_at,
                    "issues": int(issues_count),
                    "pending_drafts": int(pending_drafts),
                }
            )
    return templates.TemplateResponse("dashboard.html", {"request": request, "jobs": rows})


@router.get("/dashboard/jobs/{job_id}", response_class=HTMLResponse)
def dashboard_job_detail(
    job_id: str,
    request: Request,
    _user: str = Depends(verify_dashboard_basic),
) -> HTMLResponse:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="job_id must be a UUID") from exc

    with session_scope() as s:
        job = s.get(Job, job_uuid)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")

        files = s.scalars(select(FileRow).where(FileRow.job_id == job_uuid)).all()
        reports = s.scalars(select(Report).where(Report.job_id == job_uuid)).all()
        issues = s.scalars(select(Issue).where(Issue.job_id == job_uuid).order_by(Issue.issue_code)).all()
        notifications = s.scalars(
            select(Notification).where(Notification.job_id == job_uuid).order_by(desc(Notification.created_at))
        ).all()

        ctx = {
            "request": request,
            "job": {
                "id": str(job.id),
                "publisher_id": job.publisher_id,
                "publisher_email": job.publisher_email,
                "catalog_name": job.catalog_name,
                "phase": job.phase,
                "status": job.status,
                "created_at": job.created_at,
            },
            "files": [
                {"role": f.role, "url": storage.presigned_url(f.s3_key), "key": f.s3_key}
                for f in files
            ],
            "reports": [
                {"type": r.type, "url": storage.presigned_url(r.s3_key), "key": r.s3_key}
                for r in reports
            ],
            "issues": [
                {
                    "code": i.issue_code,
                    "field": i.field,
                    "current": i.current_value,
                    "suggested": i.suggested_value,
                    "severity": i.severity,
                    "status": i.status,
                }
                for i in issues
            ],
            "notifications": [
                {
                    "id": str(n.id),
                    "template": n.template,
                    "recipient": n.recipient,
                    "subject": n.subject,
                    "status": n.status,
                    "sent_at": n.sent_at,
                    "error": n.error,
                }
                for n in notifications
            ],
        }
    return templates.TemplateResponse("job_detail.html", ctx)


@router.post("/dashboard/notifications/{notification_id}/send")
def dashboard_send_notification(
    notification_id: str,
    _user: str = Depends(verify_dashboard_basic),
) -> RedirectResponse:
    try:
        n_uuid = uuid.UUID(notification_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="notification_id must be a UUID") from exc

    with session_scope() as s:
        n = s.get(Notification, n_uuid)
        if n is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="notification not found")
        if n.status != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"notification status is {n.status!r}, expected 'pending'",
            )
        try:
            send_via_resend(recipient=n.recipient, subject=n.subject, body_html=n.body_html)
            n.status = "sent"
            n.sent_at = datetime.now(timezone.utc)
            n.error = None
            redirect_target = f"/dashboard/jobs/{n.job_id}"
        except Exception as exc:  # noqa: BLE001
            n.status = "failed"
            n.error = str(exc)
            redirect_target = f"/dashboard/jobs/{n.job_id}"
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)

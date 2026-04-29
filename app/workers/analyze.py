from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from app.engine.detect import detect_issues
from app.engine.report import render_health_report
from app.engine.worksheet import build_worksheet_csv
from app.models import File, Issue, Job, Notification, Work
from app.models.db import session_scope
from app.services import storage
from app.services.email import render_analyzed
from app.workers.celery_app import celery_app


def _scan_id_for(date_iso: str) -> str:
    return f"HR-{date_iso.replace('-', '')}-{secrets.token_hex(2).upper()}"


def _run(job_id_str: str) -> None:
    job_uuid = UUID(job_id_str)

    with session_scope() as s:
        job = s.get(Job, job_uuid)
        if job is None:
            raise RuntimeError(f"Job {job_id_str} not found")
        original = next((f for f in job.files if f.role == "original_catalog"), None)
        if original is None:
            raise RuntimeError(f"Job {job_id_str} has no original_catalog file")
        original_key = original.s3_key
        publisher_id = job.publisher_id
        job.status = "running"

    catalog_bytes = storage.get_object(original_key)
    catalog_text = catalog_bytes.decode("utf-8")

    scan = detect_issues(catalog_text)

    scan_date = datetime.now(timezone.utc).date().isoformat()
    scan_id = _scan_id_for(scan_date)

    report_html = render_health_report(scan, scan_id=scan_id, scan_date=scan_date)
    report_key = storage.put_object(
        "reports_before",
        str(job_uuid),
        "report.html",
        report_html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
    )

    worksheet_csv = build_worksheet_csv(scan)
    worksheet_key = storage.put_object(
        "correction_templates",
        str(job_uuid),
        "corrections-worksheet.csv",
        worksheet_csv.encode("utf-8"),
        content_type="text/csv; charset=utf-8",
    )

    title_to_work_id: dict[str, UUID] = {}
    with session_scope() as s:
        for title in scan.titles:
            w = Work(job_id=job_uuid, title=title)
            s.add(w)
            s.flush()
            title_to_work_id[title] = w.id
        for issue in scan.issues:
            s.add(
                Issue(
                    job_id=job_uuid,
                    work_id=title_to_work_id[issue.work],
                    issue_code=issue.id,
                    issue_type=issue.field,
                    field=issue.field,
                    current_value=issue.current,
                    suggested_value=issue.suggested,
                    severity=issue.severity,
                    status="open",
                )
            )
        s.add(File(job_id=job_uuid, role="correction_template", s3_key=worksheet_key))

        from app.models import Report

        s.add(Report(job_id=job_uuid, type="before", s3_key=report_key))

        job = s.get(Job, job_uuid)
        job.phase = "awaiting_corrections"
        job.status = "done"

        if job.publisher_email:
            email = render_analyzed(
                job_id=str(job_uuid),
                health_report_url=storage.presigned_url(report_key),
                worksheet_url=storage.presigned_url(worksheet_key),
            )
            s.add(
                Notification(
                    job_id=job_uuid,
                    template="analyzed",
                    recipient=job.publisher_email,
                    subject=email.subject,
                    body_html=email.body_html,
                    status="pending",
                )
            )


@celery_app.task(name="analyze_catalog")
def analyze_catalog(job_id: str) -> str:
    _run(job_id)
    return job_id

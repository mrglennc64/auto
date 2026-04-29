from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from app.engine.apply import apply_decisions
from app.engine.detect import detect_issues
from app.engine.report import render_health_report
from app.models import (
    BeforeAfterDiff,
    CorrectionEntry,
    CorrectionJob,
    File,
    Job,
    Notification,
    Report,
    Work,
)
from app.models.db import session_scope
from app.services import storage
from app.services.email import render_after, render_received
from app.workers.celery_app import celery_app


def _scan_id_for(date_iso: str) -> str:
    return f"HR-{date_iso.replace('-', '')}-{secrets.token_hex(2).upper()}"


def _run(correction_job_id_str: str) -> None:
    cj_uuid = UUID(correction_job_id_str)

    with session_scope() as s:
        cj = s.get(CorrectionJob, cj_uuid)
        if cj is None:
            raise RuntimeError(f"CorrectionJob {correction_job_id_str} not found")
        job = s.get(Job, cj.job_id)
        if job is None:
            raise RuntimeError(f"Parent Job {cj.job_id} not found")
        job_uuid = job.id
        original = next((f for f in job.files if f.role == "original_catalog"), None)
        corrections = next((f for f in job.files if f.role == "corrections_uploaded"), None)
        if original is None or corrections is None:
            raise RuntimeError(f"Job {job_uuid} missing files for correction")
        original_key = original.s3_key
        corrections_key = corrections.s3_key
        publisher_email = job.publisher_email
        cj.status = "running"
        job.status = "running"

        if publisher_email:
            received = render_received(job_id=str(job_uuid))
            s.add(
                Notification(
                    job_id=job_uuid,
                    template="received",
                    recipient=publisher_email,
                    subject=received.subject,
                    body_html=received.body_html,
                    status="pending",
                )
            )

    catalog_text = storage.get_object(original_key).decode("utf-8")
    worksheet_text = storage.get_object(corrections_key).decode("utf-8")

    result = apply_decisions(catalog_text, worksheet_text)

    cleaned_key = storage.put_object(
        "corrected_catalogs",
        str(job_uuid),
        "catalog-cleaned.csv",
        result.cleaned_csv.encode("utf-8"),
        content_type="text/csv; charset=utf-8",
    )

    after_scan = detect_issues(result.cleaned_csv)
    scan_date = datetime.now(timezone.utc).date().isoformat()
    after_html = render_health_report(after_scan, scan_id=_scan_id_for(scan_date), scan_date=scan_date)
    after_key = storage.put_object(
        "reports_after",
        str(job_uuid),
        "report.html",
        after_html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
    )

    with session_scope() as s:
        s.add(File(job_id=job_uuid, role="corrected_catalog", s3_key=cleaned_key))
        s.add(Report(job_id=job_uuid, type="after", s3_key=after_key))

        works = {w.title: w.id for w in s.query(Work).filter_by(job_id=job_uuid).all()}
        for entry in result.log:
            work_id = works.get(entry.work)
            if work_id is None:
                continue
            s.add(
                CorrectionEntry(
                    correction_job_id=cj_uuid,
                    work_id=work_id,
                    field=entry.field,
                    current_value="",
                    corrected_value=entry.applied,
                    decision=entry.decision,
                    notes="",
                )
            )
            s.add(
                BeforeAfterDiff(
                    job_id=job_uuid,
                    work_id=work_id,
                    field=entry.field,
                    value_before="",
                    value_after=entry.applied,
                )
            )

        job = s.get(Job, job_uuid)
        cj_db = s.get(CorrectionJob, cj_uuid)
        job.phase = "after_report_ready"
        job.status = "done"
        cj_db.status = "done"

        if publisher_email:
            after = render_after(
                job_id=str(job_uuid),
                after_report_url=storage.presigned_url(after_key),
                corrected_catalog_url=storage.presigned_url(cleaned_key),
            )
            s.add(
                Notification(
                    job_id=job_uuid,
                    template="after",
                    recipient=publisher_email,
                    subject=after.subject,
                    body_html=after.body_html,
                    status="pending",
                )
            )


@celery_app.task(name="apply_corrections")
def apply_corrections(correction_job_id: str) -> str:
    _run(correction_job_id)
    return correction_job_id

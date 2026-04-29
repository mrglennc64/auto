from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


JobPhase = SAEnum(
    "analysis",
    "awaiting_corrections",
    "correction",
    "after_report_ready",
    name="job_phase",
)
JobStatus = SAEnum("pending", "running", "done", "error", name="job_status")
IssueSeverity = SAEnum("blocking", "resolvable", name="issue_severity")
IssueStatus = SAEnum("open", "resolved", name="issue_status")
ReportType = SAEnum("before", "after", name="report_type")
FileRole = SAEnum(
    "original_catalog",
    "correction_template",
    "corrections_uploaded",
    "corrected_catalog",
    "cwr_export",
    name="file_role",
)
DeclarationType = SAEnum("E", "SE", "AM", name="declaration_type")
NotificationStatus = SAEnum("pending", "sent", "failed", name="notification_status")
NotificationTemplate = SAEnum("analyzed", "received", "after", name="notification_template")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    publisher_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    publisher_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    catalog_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phase: Mapped[str] = mapped_column(JobPhase, nullable=False, default="analysis")
    status: Mapped[str] = mapped_column(JobStatus, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=_now,
    )

    works: Mapped[list[Work]] = relationship(back_populates="job", cascade="all, delete-orphan")
    issues: Mapped[list[Issue]] = relationship(back_populates="job", cascade="all, delete-orphan")
    correction_jobs: Mapped[list[CorrectionJob]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    diffs: Mapped[list[BeforeAfterDiff]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    reports: Mapped[list[Report]] = relationship(back_populates="job", cascade="all, delete-orphan")
    files: Mapped[list[File]] = relationship(back_populates="job", cascade="all, delete-orphan")
    agreements: Mapped[list[Agreement]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Work(Base):
    __tablename__ = "works"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_work_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    iswc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    isrc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_score_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped[Job] = relationship(back_populates="works")
    issues: Mapped[list[Issue]] = relationship(back_populates="work", cascade="all, delete-orphan")
    correction_entries: Mapped[list[CorrectionEntry]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    diffs: Mapped[list[BeforeAfterDiff]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    agreements: Mapped[list[Agreement]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_code: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    current_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(IssueSeverity, nullable=False)
    status: Mapped[str] = mapped_column(IssueStatus, nullable=False, default="open")

    job: Mapped[Job] = relationship(back_populates="issues")
    work: Mapped[Work] = relationship(back_populates="issues")


class CorrectionJob(Base):
    __tablename__ = "correction_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(JobStatus, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=_now,
    )

    job: Mapped[Job] = relationship(back_populates="correction_jobs")
    entries: Mapped[list[CorrectionEntry]] = relationship(
        back_populates="correction_job", cascade="all, delete-orphan"
    )


class CorrectionEntry(Base):
    __tablename__ = "correction_entries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    correction_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("correction_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    current_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    correction_job: Mapped[CorrectionJob] = relationship(back_populates="entries")
    work: Mapped[Work] = relationship(back_populates="correction_entries")


class BeforeAfterDiff(Base):
    __tablename__ = "before_after_diff"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value_before: Mapped[str] = mapped_column(Text, nullable=False, default="")
    value_after: Mapped[str] = mapped_column(Text, nullable=False, default="")

    job: Mapped[Job] = relationship(back_populates="diffs")
    work: Mapped[Work] = relationship(back_populates="diffs")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(ReportType, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="reports")


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(FileRole, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="files")


class Agreement(Base):
    __tablename__ = "agreements"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), nullable=False, index=True
    )
    foreign_writer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    foreign_society: Mapped[str] = mapped_column(String(32), nullable=False)
    declaration_type: Mapped[str] = mapped_column(DeclarationType, nullable=False, default="E")
    territory: Mapped[str | None] = mapped_column(String(64), nullable=True)

    job: Mapped[Job] = relationship(back_populates="agreements")
    work: Mapped[Work] = relationship(back_populates="agreements")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template: Mapped[str] = mapped_column(NotificationTemplate, nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(NotificationStatus, nullable=False, default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="notifications")

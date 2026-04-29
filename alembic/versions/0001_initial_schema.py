"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-29

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JOB_PHASE = sa.Enum(
    "analysis", "awaiting_corrections", "correction", "after_report_ready",
    name="job_phase",
)
JOB_STATUS = sa.Enum("pending", "running", "done", "error", name="job_status")
ISSUE_SEVERITY = sa.Enum("blocking", "resolvable", name="issue_severity")
ISSUE_STATUS = sa.Enum("open", "resolved", name="issue_status")
REPORT_TYPE = sa.Enum("before", "after", name="report_type")
FILE_ROLE = sa.Enum(
    "original_catalog", "correction_template", "corrections_uploaded",
    "corrected_catalog", "cwr_export",
    name="file_role",
)
DECLARATION_TYPE = sa.Enum("E", "SE", "AM", name="declaration_type")


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("publisher_id", sa.String(255), nullable=False, index=True),
        sa.Column("phase", JOB_PHASE, nullable=False),
        sa.Column("status", JOB_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_publisher_id", "jobs", ["publisher_id"])

    op.create_table(
        "works",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_work_id", sa.String(255), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("iswc", sa.String(64), nullable=True),
        sa.Column("isrc", sa.String(64), nullable=True),
        sa.Column("risk_score_before", sa.Integer, nullable=True),
        sa.Column("risk_score_after", sa.Integer, nullable=True),
    )
    op.create_index("ix_works_job_id", "works", ["job_id"])

    op.create_table(
        "issues",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_id", UUID(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_code", sa.String(32), nullable=False),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("current_value", sa.Text, nullable=False, server_default=""),
        sa.Column("suggested_value", sa.Text, nullable=False, server_default=""),
        sa.Column("severity", ISSUE_SEVERITY, nullable=False),
        sa.Column("status", ISSUE_STATUS, nullable=False, server_default="open"),
    )
    op.create_index("ix_issues_job_id", "issues", ["job_id"])
    op.create_index("ix_issues_work_id", "issues", ["work_id"])

    op.create_table(
        "correction_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", JOB_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_correction_jobs_job_id", "correction_jobs", ["job_id"])

    op.create_table(
        "correction_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("correction_job_id", UUID(as_uuid=True), sa.ForeignKey("correction_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_id", UUID(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("current_value", sa.Text, nullable=False, server_default=""),
        sa.Column("corrected_value", sa.Text, nullable=False, server_default=""),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_correction_entries_cj_id", "correction_entries", ["correction_job_id"])
    op.create_index("ix_correction_entries_work_id", "correction_entries", ["work_id"])

    op.create_table(
        "before_after_diff",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_id", UUID(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("value_before", sa.Text, nullable=False, server_default=""),
        sa.Column("value_after", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_before_after_diff_job_id", "before_after_diff", ["job_id"])
    op.create_index("ix_before_after_diff_work_id", "before_after_diff", ["work_id"])

    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", REPORT_TYPE, nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reports_job_id", "reports", ["job_id"])

    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", FILE_ROLE, nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_files_job_id", "files", ["job_id"])

    op.create_table(
        "agreements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_id", UUID(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("foreign_writer_name", sa.String(255), nullable=False),
        sa.Column("foreign_society", sa.String(32), nullable=False),
        sa.Column("declaration_type", DECLARATION_TYPE, nullable=False, server_default="E"),
        sa.Column("territory", sa.String(64), nullable=True),
    )
    op.create_index("ix_agreements_job_id", "agreements", ["job_id"])
    op.create_index("ix_agreements_work_id", "agreements", ["work_id"])


def downgrade() -> None:
    op.drop_table("agreements")
    op.drop_table("files")
    op.drop_table("reports")
    op.drop_table("before_after_diff")
    op.drop_table("correction_entries")
    op.drop_table("correction_jobs")
    op.drop_table("issues")
    op.drop_table("works")
    op.drop_table("jobs")
    DECLARATION_TYPE.drop(op.get_bind())
    FILE_ROLE.drop(op.get_bind())
    REPORT_TYPE.drop(op.get_bind())
    ISSUE_STATUS.drop(op.get_bind())
    ISSUE_SEVERITY.drop(op.get_bind())
    JOB_STATUS.drop(op.get_bind())
    JOB_PHASE.drop(op.get_bind())

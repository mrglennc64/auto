"""publisher_email + notifications

Revision ID: 0002_publisher_email_and_notifications
Revises: 0001_initial_schema
Create Date: 2026-04-29

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002_publisher_email_and_notifications"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOTIFICATION_TEMPLATE = sa.Enum("analyzed", "received", "after", name="notification_template")
NOTIFICATION_STATUS = sa.Enum("pending", "sent", "failed", name="notification_status")


def upgrade() -> None:
    op.add_column("jobs", sa.Column("publisher_email", sa.String(320), nullable=True))
    op.add_column("jobs", sa.Column("catalog_name", sa.String(255), nullable=True))

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template", NOTIFICATION_TEMPLATE, nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("body_html", sa.Text, nullable=False),
        sa.Column("status", NOTIFICATION_STATUS, nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_job_id", "notifications", ["job_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])


def downgrade() -> None:
    op.drop_table("notifications")
    NOTIFICATION_STATUS.drop(op.get_bind())
    NOTIFICATION_TEMPLATE.drop(op.get_bind())
    op.drop_column("jobs", "catalog_name")
    op.drop_column("jobs", "publisher_email")

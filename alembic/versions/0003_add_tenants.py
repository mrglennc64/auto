"""tenants table

Revision ID: 0003_add_tenants
Revises: 0002_publisher_email_notifs
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_add_tenants"
down_revision: Union[str, None] = "0002_publisher_email_notifs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_STATUS = sa.Enum("active", "suspended", "deleted", name="tenant_status")


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("brand_name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(320), nullable=False),
        sa.Column("custom_domain", sa.String(255), nullable=False, unique=True),
        sa.Column("primary_color", sa.String(16), nullable=False, server_default="#1dd4b7"),
        sa.Column("status", TENANT_STATUS, nullable=False, server_default="active"),
        sa.Column("api_key", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tenants_custom_domain", "tenants", ["custom_domain"])
    op.create_index("ix_tenants_status", "tenants", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tenants_status", table_name="tenants")
    op.drop_index("ix_tenants_custom_domain", table_name="tenants")
    op.drop_table("tenants")
    TENANT_STATUS.drop(op.get_bind())

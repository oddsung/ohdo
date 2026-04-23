"""device_codes table for Device Flow

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_codes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("device_code", sa.Text(), nullable=False),
        sa.Column("user_code", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("hostname", sa.Text(), nullable=True),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("agent_version", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="device_codes_user_id_fkey",
        ),
    )
    op.create_index(
        "device_codes_device_code_idx",
        "device_codes",
        ["device_code"],
        unique=True,
    )
    op.create_index(
        "device_codes_user_code_idx",
        "device_codes",
        ["user_code"],
        unique=True,
    )
    op.create_index("device_codes_status_idx", "device_codes", ["status"])


def downgrade() -> None:
    op.drop_index("device_codes_status_idx", table_name="device_codes")
    op.drop_index("device_codes_user_code_idx", table_name="device_codes")
    op.drop_index("device_codes_device_code_idx", table_name="device_codes")
    op.drop_table("device_codes")

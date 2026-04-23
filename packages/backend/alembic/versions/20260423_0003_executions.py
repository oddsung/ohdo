"""executions table (M2.1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23

에이전트에서 실행된 RPA 세션 단위를 저장한다.
상세 설계: docs/saas/architecture/08-m2.1-executions-schema.md
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "executions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("session_snapshot", sa.JSON(), nullable=True),
        sa.Column("from_step", sa.Integer(), nullable=True),
        sa.Column("to_step", sa.Integer(), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=True),
        sa.Column("executed_steps", sa.Integer(), nullable=True),
        sa.Column("successful_steps", sa.Integer(), nullable=True),
        sa.Column("failed_steps", sa.Integer(), nullable=True),
        sa.Column("total_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            ["agent_id"],
            ["agents.id"],
            ondelete="CASCADE",
            name="executions_agent_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="executions_user_id_fkey",
        ),
    )
    op.create_index(
        "executions_execution_id_idx",
        "executions",
        ["execution_id"],
        unique=True,
    )
    op.create_index("executions_agent_id_idx", "executions", ["agent_id"])
    op.create_index("executions_user_id_idx", "executions", ["user_id"])
    op.create_index("executions_status_idx", "executions", ["status"])


def downgrade() -> None:
    op.drop_index("executions_status_idx", table_name="executions")
    op.drop_index("executions_user_id_idx", table_name="executions")
    op.drop_index("executions_agent_id_idx", table_name="executions")
    op.drop_index("executions_execution_id_idx", table_name="executions")
    op.drop_table("executions")

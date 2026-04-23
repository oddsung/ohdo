"""execution_logs table (M2.4)

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23

한 execution 에서 흐른 로그를 line-per-row 로 저장한다. 에이전트가
``execution.log`` 프레임으로 배치 전송한 entries 를 서버가 인서트.

상세 설계: docs/saas/architecture/11-m2.4-execution-log.md
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("stream", sa.Text(), nullable=False),
        sa.Column("line", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.execution_id"],
            ondelete="CASCADE",
            name="execution_logs_execution_id_fkey",
        ),
    )
    op.create_index(
        "execution_logs_execution_id_idx",
        "execution_logs",
        ["execution_id"],
    )
    op.create_index(
        "execution_logs_execution_id_seq_idx",
        "execution_logs",
        ["execution_id", "seq"],
    )
    op.create_index(
        "execution_logs_stream_idx",
        "execution_logs",
        ["stream"],
    )


def downgrade() -> None:
    op.drop_index("execution_logs_stream_idx", table_name="execution_logs")
    op.drop_index(
        "execution_logs_execution_id_seq_idx", table_name="execution_logs"
    )
    op.drop_index("execution_logs_execution_id_idx", table_name="execution_logs")
    op.drop_table("execution_logs")

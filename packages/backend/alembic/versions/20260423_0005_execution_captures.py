"""execution_captures table (M2.6)

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-23

스텝 실패 시 캡처된 스크린샷 등 바이너리 메타데이터. 실제 바이트는 로컬
파일시스템 (``data/captures/...``) 에 저장된다. Railway 컨테이너 파일시스템은
ephemeral 이므로 재배포 시 캡처 소실. 운영 전 S3/R2 로 교체 필요.

상세 설계: docs/saas/architecture/13-m2.6-captures-upload.md
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_captures",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default="error_screenshot",
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
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
            name="execution_captures_execution_id_fkey",
        ),
    )
    op.create_index(
        "execution_captures_execution_id_idx",
        "execution_captures",
        ["execution_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "execution_captures_execution_id_idx", table_name="execution_captures"
    )
    op.drop_table("execution_captures")

"""user_sessions + magic_links tables (M3.1.1)

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24

브라우저 사용자 인증을 위한 두 테이블. 기존 users 테이블 (M1.1) 을 그대로
사용하고 세션/로그인만 신규.

상세 설계: docs/saas/architecture/18-m3.1.1-web-auth.md
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="user_sessions_user_id_fkey",
        ),
    )
    op.create_index(
        "user_sessions_token_hash_idx",
        "user_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index("user_sessions_user_id_idx", "user_sessions", ["user_id"])

    op.create_table(
        "magic_links",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "magic_links_token_hash_idx",
        "magic_links",
        ["token_hash"],
        unique=True,
    )
    op.create_index("magic_links_email_idx", "magic_links", ["email"])


def downgrade() -> None:
    op.drop_index("magic_links_email_idx", table_name="magic_links")
    op.drop_index("magic_links_token_hash_idx", table_name="magic_links")
    op.drop_table("magic_links")

    op.drop_index("user_sessions_user_id_idx", table_name="user_sessions")
    op.drop_index("user_sessions_token_hash_idx", table_name="user_sessions")
    op.drop_table("user_sessions")

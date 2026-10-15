"""classroom capacity 46 students for every level (was 45)

The analysis reads the capacity from app/domain/analysis.py (LEVELS); level_norms records it per school year and is
brought in line here.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15 14:00:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE level_norms SET classroom_capacity = 46 WHERE classroom_capacity = 45")


def downgrade() -> None:
    op.execute("UPDATE level_norms SET classroom_capacity = 45 WHERE classroom_capacity = 46")

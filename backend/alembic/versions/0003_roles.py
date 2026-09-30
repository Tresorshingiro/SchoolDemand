"""roles (admin / viewer), forced password change, audit log

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # every existing account becomes a viewer; promote with: python -m app.users role EMAIL admin
    op.add_column('users', sa.Column('role', sa.String(length=10), server_default='viewer', nullable=False,
                                     comment='admin or viewer'))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('users', sa.Column('created_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_created_by_id', 'users', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('admin', 'viewer')")
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('target', sa.String(length=200), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_at', 'audit_log', [sa.text('at DESC')])


def downgrade() -> None:
    op.drop_index('ix_audit_log_at', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_constraint('fk_users_created_by_id', 'users', type_='foreignkey')
    op.drop_column('users', 'created_by_id')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'role')

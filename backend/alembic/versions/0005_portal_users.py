"""users sign in with their MINEDUC GIS portal account: username, no password kept here

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Earlier email / password accounts keep their row (their name stays on the history) with the email as username;
    # they can no longer sign in unless the portal has a user with that name.
    op.add_column('users', sa.Column('username', sa.String(length=128), nullable=True,
                                     comment='portal username, as the portal writes it'))
    op.execute("UPDATE users SET username = email")
    op.alter_column('users', 'username', nullable=False)
    op.create_index('ux_users_username', 'users', [sa.text('lower(username)')], unique=True)
    op.drop_constraint('users_email_key', 'users', type_='unique')  # the portal allows one email on several accounts
    op.alter_column('users', 'email', nullable=True, comment='from the portal profile')
    op.alter_column('users', 'full_name', comment='from the portal profile')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'must_change_password')


def downgrade() -> None:
    # Accounts get an unusable password: set one with python -m app.users password (the version before 0005).
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), server_default='!', nullable=False,
                                     comment='argon2id'))
    op.alter_column('users', 'password_hash', server_default=None)
    op.execute("UPDATE users SET email = lower(username) WHERE email IS NULL")
    op.alter_column('users', 'email', nullable=False, comment='stored in lower case')
    op.alter_column('users', 'full_name', comment=None)
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.drop_index('ux_users_username', table_name='users')
    op.drop_column('users', 'username')

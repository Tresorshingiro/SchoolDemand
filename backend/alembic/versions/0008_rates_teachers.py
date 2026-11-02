"""repetition and dropout rates, teachers: district_flow_rates, school_teachers, school_staff

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'district_flow_rates',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('district_id', sa.SmallInteger(), sa.ForeignKey('districts.id'), nullable=True, comment='NULL = Rwanda'),
        sa.Column('school_year', sa.String(9), nullable=False, comment='as in the file, e.g. 2023/24'),
        sa.Column('end_year', sa.SmallInteger(), nullable=False, comment='2023/24 -> 2024'),
        sa.Column('repetition', sa.Numeric(6, 4), nullable=False, comment='share, Average of boys and girls'),
        sa.Column('dropout', sa.Numeric(6, 4), nullable=False),
        sa.Column('import_run_id', sa.BigInteger(), sa.ForeignKey('import_runs.id'), nullable=True),
        sa.UniqueConstraint('district_id', 'end_year', postgresql_nulls_not_distinct=True),
    )
    op.create_table(
        'school_teachers',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('academic_year_id', sa.SmallInteger(), sa.ForeignKey('academic_years.id'), nullable=False),
        sa.Column('level_id', sa.SmallInteger(), sa.ForeignKey('school_levels.id'), nullable=False),
        sa.Column('teachers', sa.Integer(), nullable=False),
        sa.Column('import_run_id', sa.BigInteger(), sa.ForeignKey('import_runs.id'), nullable=True),
        sa.UniqueConstraint('school_id', 'academic_year_id', 'level_id'),
    )
    op.create_table(
        'school_staff',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('academic_year_id', sa.SmallInteger(), sa.ForeignKey('academic_years.id'), nullable=False),
        sa.Column('status', sa.String(30), nullable=True, comment='PUBLIC, GOVERNMENT_AIDED ...'),
        sa.Column('administrative_staff', sa.Integer(), nullable=True),
        sa.Column('import_run_id', sa.BigInteger(), sa.ForeignKey('import_runs.id'), nullable=True),
        sa.UniqueConstraint('school_id', 'academic_year_id'),
    )
    # the two new kinds of upload (an existing database gets them without running the import job)
    op.execute("INSERT INTO data_sources (code, name) VALUES ('FLOW_RATES', 'Repetition and dropout (MINEDUC)'), "
               "('TEACHERS', 'Teachers (MINEDUC)') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    op.drop_table('school_staff')
    op.drop_table('school_teachers')
    op.drop_table('district_flow_rates')

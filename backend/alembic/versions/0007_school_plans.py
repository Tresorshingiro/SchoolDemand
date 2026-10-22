"""saved plans of new schools: school_plans, planned_schools, planned_school_levels

Planned schools live only here, never in the actual data (schools, class_groups ...).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20 18:00:00
"""
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'school_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('base_year_id', sa.SmallInteger(), sa.ForeignKey('academic_years.id'), nullable=False),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='classrooms short before / after, per level, area and year'),
    )
    op.create_table(
        'planned_schools',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_plan_id', sa.Integer(), sa.ForeignKey('school_plans.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('opening_year', sa.SmallInteger(), nullable=False),
        sa.Column('walking_km', sa.Numeric(4, 1), nullable=False),
        sa.Column('geom', geoalchemy2.Geometry('POINT', srid=4326, spatial_index=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        'planned_school_levels',
        sa.Column('planned_school_id', sa.Integer(), sa.ForeignKey('planned_schools.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('level_id', sa.SmallInteger(), sa.ForeignKey('school_levels.id'), primary_key=True),
        sa.Column('classrooms', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint('classrooms BETWEEN 1 AND 200', name='ck_planned_school_levels_classrooms'),
    )


def downgrade() -> None:
    op.drop_table('planned_school_levels')
    op.drop_table('planned_schools')
    op.drop_table('school_plans')

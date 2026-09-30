"""imports from the admin portal: import_runs lifecycle, classrooms per school year, NISR district population

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30 09:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- import_runs: one row per upload, with its check report and whether it is the live data
    op.add_column('import_runs', sa.Column('kind', sa.String(20), server_default='school_data', nullable=False,
                                           comment='school_data, catchment, nisr_population'))
    op.add_column('import_runs', sa.Column('academic_year', sa.SmallInteger(), nullable=True,
                                           comment='school data: the school year of the file'))
    op.add_column('import_runs', sa.Column('file_name', sa.String(255), nullable=True))
    op.add_column('import_runs', sa.Column('file_sha256', sa.String(64), nullable=True))
    op.add_column('import_runs', sa.Column('file_size', sa.BigInteger(), nullable=True))
    op.add_column('import_runs', sa.Column('uploaded_by_id', sa.Integer(), nullable=True))
    op.add_column('import_runs', sa.Column('published_by_id', sa.Integer(), nullable=True))
    op.add_column('import_runs', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('import_runs', sa.Column('progress', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('import_runs', sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('import_runs', sa.Column('is_live', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.alter_column('import_runs', 'status', type_=sa.String(12))  # 'withdrawing', 'superseded' ...
    op.create_foreign_key('fk_import_runs_uploaded_by_id', 'import_runs', 'users', ['uploaded_by_id'], ['id'],
                          ondelete='SET NULL')
    op.create_foreign_key('fk_import_runs_published_by_id', 'import_runs', 'users', ['published_by_id'], ['id'],
                          ondelete='SET NULL')
    op.execute("UPDATE import_runs r SET academic_year = y.year FROM academic_years y WHERE y.id = r.academic_year_id")
    op.execute("UPDATE import_runs SET file_name = endpoint, progress = 100, "
               "status = CASE WHEN status = 'success' THEN 'superseded' ELSE 'failed' END")
    op.execute("UPDATE import_runs SET status = 'published', is_live = true, published_at = finished_at "
               "WHERE id = (SELECT max(id) FROM import_runs WHERE status = 'superseded')")
    op.execute("INSERT INTO data_sources (code, name) VALUES "
               "('SCHOOL_DATA', 'MINEDUC school data (Excel upload or API)'), "
               "('CATCHMENT', 'Children aged 3 per pre-primary school catchment (GIS)'), "
               "('NISR_POPULATION', 'NISR population by district (age 3)') ON CONFLICT (code) DO NOTHING")
    # the catchment already loaded becomes a live catchment import
    op.execute("INSERT INTO import_runs (source_id, kind, endpoint, file_name, status, is_live, started_at, finished_at, "
               "published_at, rows_loaded, progress) "
               "SELECT (SELECT id FROM data_sources WHERE code = 'CATCHMENT'), 'catchment', 'Chachement area.xlsx', "
               "'Chachement area.xlsx', 'published', true, now(), now(), now(), count(*), 100 "
               "FROM catchment_population HAVING count(*) > 0")
    op.execute("UPDATE catchment_population SET import_run_id = "
               "(SELECT id FROM import_runs WHERE kind = 'catchment' AND is_live)")
    op.create_index('ux_import_runs_live', 'import_runs', ['kind', sa.text('COALESCE(academic_year, 0)')], unique=True,
                    postgresql_where=sa.text('is_live'))

    # ---- classrooms belong to a school year (schools build rooms between years)
    op.add_column('classrooms', sa.Column('academic_year_id', sa.SmallInteger(), nullable=True))
    op.execute("UPDATE classrooms c SET academic_year_id = cg.academic_year_id FROM "
               "(SELECT DISTINCT classroom_id, academic_year_id FROM class_groups) cg WHERE cg.classroom_id = c.id")
    op.execute("UPDATE classrooms SET academic_year_id = (SELECT id FROM academic_years WHERE year = 2026) "
               "WHERE academic_year_id IS NULL")
    op.alter_column('classrooms', 'academic_year_id', nullable=False)
    op.create_foreign_key('fk_classrooms_academic_year_id', 'classrooms', 'academic_years', ['academic_year_id'], ['id'])
    op.drop_constraint('classrooms_school_id_mineduc_classroom_id_key', 'classrooms', type_='unique')
    op.create_unique_constraint('uq_classrooms_year_school_room', 'classrooms',
                                ['academic_year_id', 'school_id', 'mineduc_classroom_id'])

    # ---- NISR population per district
    op.create_table('district_population',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('district_id', sa.SmallInteger(), nullable=False),
    sa.Column('year', sa.SmallInteger(), nullable=False),
    sa.Column('age', sa.SmallInteger(), nullable=False),
    sa.Column('population', sa.Integer(), nullable=False),
    sa.Column('import_run_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
    sa.ForeignKeyConstraint(['import_run_id'], ['import_runs.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('district_id', 'year', 'age')
    )


def downgrade() -> None:
    op.drop_table('district_population')
    op.drop_constraint('uq_classrooms_year_school_room', 'classrooms', type_='unique')
    op.create_unique_constraint('classrooms_school_id_mineduc_classroom_id_key', 'classrooms',
                                ['school_id', 'mineduc_classroom_id'])
    op.drop_constraint('fk_classrooms_academic_year_id', 'classrooms', type_='foreignkey')
    op.drop_column('classrooms', 'academic_year_id')
    op.drop_index('ux_import_runs_live', table_name='import_runs')
    op.execute("UPDATE catchment_population SET import_run_id = NULL")
    op.execute("DELETE FROM import_runs WHERE kind <> 'school_data'")
    op.execute("UPDATE import_runs SET status = CASE WHEN status IN ('published', 'superseded') THEN 'success' "
               "ELSE 'failed' END")
    for c in ('is_live', 'report', 'progress', 'published_at', 'published_by_id', 'uploaded_by_id', 'file_size',
              'file_sha256', 'file_name', 'academic_year', 'kind'):
        op.drop_column('import_runs', c)

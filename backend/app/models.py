"""
Database tables. They follow database/schema.dbml (MINEDUC school data + NISR demand + planning scenarios);
this is the part in use today. Cells, villages, teachers and stored projection results are in the design but not
created yet — there is no data for them.

Additions to the design: `countries` (the outline the map masks outside of), `catchment_population` (children per
pre-primary school catchment — the GIS file gives school catchments, not the village x school shares of
`school_catchments`), and `classrooms.source_classroom_id` (the roster's classroom_id; `mineduc_classroom_id`
holds test_code, the cleaned room ID), `users` / `user_sessions` (sign-in to the dashboard, admin / viewer roles), `audit_log` (who changed what), `district_population` (NISR district totals), `classrooms.academic_year_id` (rooms per
school year).
"""
from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint, false, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# ---------------------------------------------------------------- administrative units


class Country(Base):
    __tablename__ = "countries"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(3), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)


class Province(Base):
    __tablename__ = "provinces"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class District(Base):
    __tablename__ = "districts"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, comment="NISR code when known; the upper-case name for now")
    province_id: Mapped[int] = mapped_column(ForeignKey("provinces.id"))
    name: Mapped[str] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)


class Sector(Base):
    __tablename__ = "sectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, comment="NISR code when known; DISTRICT/SECTOR for now")
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    name: Mapped[str] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)


# ---------------------------------------------------------------- reference data


class AcademicYear(Base):
    __tablename__ = "academic_years"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, unique=True)


class SchoolLevel(Base):
    __tablename__ = "school_levels"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(5), unique=True, comment="NUR, PRI, LSE, USE, TVE, TTC")
    name: Mapped[str] = mapped_column(String(50))
    entry_age: Mapped[int | None] = mapped_column(SmallInteger)
    duration_years: Mapped[int] = mapped_column(SmallInteger)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    full_day: Mapped[bool] = mapped_column(Boolean, default=False, comment="no double shift: every class group needs a room")


class Grade(Base):
    __tablename__ = "grades"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(5), unique=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("school_levels.id"))
    sequence: Mapped[int] = mapped_column(SmallInteger, comment="1 = entry grade of the level")
    next_grade_id: Mapped[int | None] = mapped_column(ForeignKey("grades.id"))


class LevelNorm(Base):
    __tablename__ = "level_norms"
    __table_args__ = (UniqueConstraint("level_id", "academic_year_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("school_levels.id"))
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    classroom_capacity: Mapped[int] = mapped_column(SmallInteger, default=45)


# ---------------------------------------------------------------- schools, classrooms, class groups


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mineduc_code: Mapped[str] = mapped_column(String(20), unique=True, comment="school_code")
    name: Mapped[str] = mapped_column(String(200))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    latitude = mapped_column(Numeric(9, 6), nullable=True)
    longitude = mapped_column(Numeric(9, 6), nullable=True)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Classroom(Base):
    """One row per physical room and school year."""
    __tablename__ = "classrooms"
    __table_args__ = (UniqueConstraint("academic_year_id", "school_id", "mineduc_classroom_id",
                                       name="uq_classrooms_year_school_room"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"), comment="rooms belong to a school year")
    mineduc_classroom_id: Mapped[str] = mapped_column(String(64), comment="test_code: cleaned room ID")
    source_classroom_id: Mapped[str | None] = mapped_column(String(64), comment="classroom_id as recorded in the roster")
    name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))


class ClassGroup(Base):
    """The roster: one row per class group (e.g. P1A)."""
    __tablename__ = "class_groups"
    __table_args__ = (Index("ix_class_groups_year_school", "academic_year_id", "school_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    name: Mapped[str | None] = mapped_column(String(100))
    combination: Mapped[str | None] = mapped_column(String(100), comment="subject combination / trade")
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classrooms.id"), index=True)
    students_total: Mapped[int] = mapped_column(Integer)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))


# ---------------------------------------------------------------- demand


class CatchmentPopulation(Base):
    """Children of an age living in a pre-primary school's catchment area (GIS split of NISR population)."""
    __tablename__ = "catchment_population"
    __table_args__ = (UniqueConstraint("school_id", "year", "age"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    year: Mapped[int] = mapped_column(SmallInteger)
    age: Mapped[int] = mapped_column(SmallInteger)
    population: Mapped[int] = mapped_column(Integer)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))


class DistrictPopulation(Base):
    """Children of an age per district and year (NISR): the default N1 plan's district totals."""
    __tablename__ = "district_population"
    __table_args__ = (UniqueConstraint("district_id", "year", "age"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    year: Mapped[int] = mapped_column(SmallInteger)
    age: Mapped[int] = mapped_column(SmallInteger)
    population: Mapped[int] = mapped_column(Integer)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))


# ---------------------------------------------------------------- ingestion and quality


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, comment="VERSION2_XLSX, CATCHMENT_XLSX, MINEDUC_API ...")
    name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str | None] = mapped_column(Text)


class ImportRun(Base):
    """One upload (or command-line load) of a data file: its check report and whether it is the live data."""
    __tablename__ = "import_runs"
    __table_args__ = (Index("ux_import_runs_live", "kind", text("COALESCE(academic_year, 0)"), unique=True,
                            postgresql_where=text("is_live")),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    kind: Mapped[str] = mapped_column(String(20), default="school_data", server_default="school_data",
                                      comment="school_data, catchment, nisr_population")
    academic_year: Mapped[int | None] = mapped_column(SmallInteger, comment="school data: the school year of the file")
    endpoint: Mapped[str | None] = mapped_column(String(200), comment="API endpoint or file name")
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    academic_year_id: Mapped[int | None] = mapped_column(ForeignKey("academic_years.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="uploaded", comment=(
        "uploaded, checking, ready, failed, publishing, published, superseded, discarded, withdrawing, withdrawn"))
    progress: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    report = mapped_column(JSONB, nullable=True)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_received: Mapped[int | None] = mapped_column(Integer)
    rows_loaded: Mapped[int | None] = mapped_column(Integer)
    params = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))
    academic_year_id: Mapped[int | None] = mapped_column(ForeignKey("academic_years.id"))
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), index=True)
    entity: Mapped[str] = mapped_column(String(50), comment="table the issue is about")
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    issue_code: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- planning scenarios


class ProjectionScenario(Base):
    """A saved intake plan (the default "Catchment" plan is computed, not stored)."""
    __tablename__ = "projection_scenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    base_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    end_year: Mapped[int] = mapped_column(SmallInteger)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------- users and sign-in


class User(Base):
    """A person who can sign in to the dashboard. Admins manage accounts and saved plans; viewers only read."""
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'viewer')", name="ck_users_role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, comment="stored in lower case")
    full_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255), comment="argon2id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(10), default="viewer", server_default="viewer", comment="admin or viewer")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored."""
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Who changed what: accounts, saved plans (and, later, the data)."""
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", text("at DESC")),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40), comment="user.create, user.role, scenario.delete ...")
    target: Mapped[str] = mapped_column(String(200), comment="e.g. the user's email or the plan name")
    detail = mapped_column(JSONB, nullable=True)


class ScenarioIntake(Base):
    """New entrants of an entry grade per district and year in a scenario (today: N1)."""
    __tablename__ = "scenario_intake"
    __table_args__ = (UniqueConstraint("scenario_id", "year", "grade_id", "district_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("projection_scenarios.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(SmallInteger)
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"), comment="entry grade, e.g. N1")
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    new_entrants: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(12), default="manual", comment="catchment, manual, csv_upload")

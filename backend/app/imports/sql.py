"""Small SQL helpers shared by the publish step and the command-line job."""
from __future__ import annotations

import math

import pandas as pd
from sqlalchemy import Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session


def none(v):
    """NaN / NaT -> None for the database."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT or v is pd.NA else v


def upsert(session: Session, table: Table, rows: list[dict], key: str) -> dict:
    """Insert or update rows by their unique `key`; returns {key value: id}."""
    if not rows:
        return {}
    stmt = pg_insert(table).values(rows)
    # a key-only table still "updates" the key to itself, so existing rows are returned too
    cols = [c for c in rows[0] if c not in (key, "id")] or [key]
    stmt = stmt.on_conflict_do_update(index_elements=[key], set_={c: stmt.excluded[c] for c in cols}
                                      ).returning(table.c[key], table.c.id)
    return {k: i for k, i in session.execute(stmt).all()}


def reset_sequence(session: Session, table: str) -> None:
    session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 0) + 1, false) "
                         f"FROM {table}"))

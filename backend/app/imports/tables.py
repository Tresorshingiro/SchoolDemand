"""Reading uploaded tables and matching their columns."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def norm(name) -> str:
    """Column names are matched ignoring case, spaces and underscores: "Number of students" == "number_of_students"."""
    return re.sub(r"[\s_]+", "", str(name)).casefold()


def read_table(path: Path) -> pd.DataFrame:
    """The first sheet of an .xlsx, or a .csv (comma or semicolon, with or without a byte-order mark; cells kept as
    text and converted by the checks)."""
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    return pd.read_excel(path, sheet_name=0)


def pick_columns(df: pd.DataFrame, required: list[str], optional: list[str] | tuple = (),
                 aliases: dict[str, str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """The file's columns renamed to the canonical names (other columns dropped), and the required names not found.
    `aliases` = {other name: canonical name}."""
    by_norm: dict[str, str] = {}
    for c in df.columns:
        by_norm.setdefault(norm(c), c)
    rename, missing = {}, []
    for name in [*required, *optional]:
        candidates = [name, *[a for a, target in (aliases or {}).items() if target == name]]
        found = next((by_norm[norm(c)] for c in candidates if norm(c) in by_norm), None)
        if found is not None:
            rename[found] = name
        elif name in required:
            missing.append(name)
    return df[list(rename)].rename(columns=rename), missing


def year_columns(df: pd.DataFrame, prefix: str) -> dict[int, str]:
    """{year: column} for the columns named <prefix><year>, e.g. Pop2028 / pop_2028 (prefix "pop"), pop3_2028 ("pop3")."""
    out = {}
    for c in df.columns:
        m = re.fullmatch(rf"{re.escape(prefix)}(\d{{4}})", norm(c))
        if m:
            out[int(m.group(1))] = c
    return dict(sorted(out.items()))

"""Small data files for the import tests, made from the live data."""
from io import BytesIO

import pandas as pd

from app.db import SessionLocal
from app.imports.checks import ROSTER_COLUMNS
from app.services import repository as R


def school_file(district: str = "Nyarugenge", year: int = 2026) -> pd.DataFrame:
    """The live roster of one district, as a school-data file (with its test_code)."""
    with SessionLocal() as s:
        roster = R.read_roster(s, year)
    return roster.loc[roster["district"] == district, ROSTER_COLUMNS].reset_index(drop=True)


def live_catchment() -> pd.DataFrame:
    """The live catchment as a file: school_code, Pop2027 ..."""
    with SessionLocal() as s:
        pop = R.read_catchment_population(s)
    return pd.DataFrame({"school_code": pop.index, **{f"Pop{y}": pop[y].to_numpy() for y in pop.columns}})


def xlsx(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

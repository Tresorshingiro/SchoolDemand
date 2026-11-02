"""
Repetition and dropout rates per district (MINEDUC) — how students move from one grade to the next.

The file has two sheets, "Repetition Rate" and "Dropout Rate", in the same layout: a row of school years
("2021/22", "2022/23", "2023/24", each over three columns), a row of Male / Female / Average under them, then one row
per district and a last row "Rwanda". Rates are shares (0.204 = 20.4%).

Rules (projection.py applies them):
* The latest school year of the file, Average column (the school data has no boys / girls split).
* The same rates for every level, grade and projected year (the file has no breakdown).
* A school whose district is not in the file (Unknown) takes the Rwanda row.
* Both apply by default; the dashboard can switch each off for a what-if run (switched).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis as A

RATES_XLSX = A.DATA_DIR / "Repetition and dropout rates.xlsx"
NATIONAL = "Rwanda"
SHEETS = {"repetition": "repet", "dropout": "dropout"}  # measure -> text the sheet name contains
SCHOOL_YEAR = re.compile(r"(\d{4})\s*/\s*(\d{2,4})")


@dataclass(frozen=True)
class FlowRates:
    """The rates the projection uses: one school year, district (and Rwanda) x repetition, dropout."""
    school_year: str
    table: pd.DataFrame


ZERO = FlowRates("none", pd.DataFrame({"repetition": [0.0], "dropout": [0.0]}, index=[NATIONAL]))


def switched(rates: FlowRates, repetition: bool = True, dropout: bool = True) -> FlowRates:
    """The rates with repetition and / or dropout switched off (0): those students are promoted instead."""
    table = rates.table.copy()
    if not repetition:
        table["repetition"] = 0.0
    if not dropout:
        table["dropout"] = 0.0
    return FlowRates(rates.school_year, table)


def _end_year(label: str) -> int:
    """"2023/24" -> 2024."""
    m = SCHOOL_YEAR.search(label)
    start, end = int(m.group(1)), m.group(2)
    return int(end) if len(end) == 4 else start // 100 * 100 + int(end) + (100 if int(end) < start % 100 else 0)


def _read_sheet(raw: pd.DataFrame, title: str) -> pd.DataFrame:
    """One sheet (read with header=None) -> rows district, school_year, value (the Average columns)."""
    cells = raw.astype(object).where(raw.notna(), None)
    head = next((i for i in range(len(cells))
                 if any(str(v).strip().casefold() == "average" for v in cells.iloc[i] if v is not None)), None)
    if head is None or head == 0:
        raise ValueError(f"The {title} sheet has no Average columns under the school years.")
    years, label = {}, None
    for j, v in enumerate(cells.iloc[head - 1]):  # school years are merged cells: carry the label right
        if v is not None and SCHOOL_YEAR.search(str(v)):
            label = SCHOOL_YEAR.search(str(v)).group(0).replace(" ", "")
        if label and str(cells.iat[head, j]).strip().casefold() == "average":
            years[j] = label
    if not years:
        raise ValueError(f"The {title} sheet has no school years (2023/24 ...) above its Average columns.")
    name_col = min(j for j in range(cells.shape[1]) if cells.iloc[head + 1:, j].map(lambda v: isinstance(v, str)).any())
    rows = []
    for i in range(head + 1, len(cells)):
        district = cells.iat[i, name_col]
        if not isinstance(district, str) or not district.strip():
            continue
        for j, sy in years.items():
            rows.append({"district": district.strip(), "school_year": sy, "value": cells.iat[i, j]})
    return pd.DataFrame(rows, columns=["district", "school_year", "value"])


def read_sheets(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Both sheets (read with header=None) -> rows district, school_year, end_year, repetition, dropout: the Average
    of every school year in the file. ValueError when a sheet or its layout is missing."""
    parts = []
    for measure, key in SHEETS.items():
        name = next((n for n in sheets if key in str(n).casefold()), None)
        if name is None:
            raise ValueError(f"No {measure.title()} sheet (expected sheets named Repetition Rate and Dropout Rate).")
        parts.append(_read_sheet(sheets[name], name).rename(columns={"value": measure})
                     .set_index(["district", "school_year"]))
    long = parts[0].join(parts[1], how="outer").reset_index()
    long.insert(2, "end_year", long["school_year"].map(_end_year))
    return long


def latest(long: pd.DataFrame) -> FlowRates:
    """The rates of the latest school year of read_sheets' rows."""
    rows = long[long["end_year"] == long["end_year"].max()]
    table = rows.set_index("district")[["repetition", "dropout"]].astype(float)
    table.index.name = None
    return FlowRates(str(rows["school_year"].iloc[0]), table)


def load_rates(path: Path = RATES_XLSX) -> FlowRates:
    """The latest rates of a rates workbook (the development file by default)."""
    return latest(read_sheets(pd.read_excel(path, sheet_name=None, header=None)))


def school_rates(rates: FlowRates, district: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """(repetition, dropout) for each row of `district`; a district not in the rates takes the Rwanda row."""
    t = rates.table
    national = t.loc[NATIONAL]
    rep = district.map(t["repetition"]).fillna(national["repetition"]).to_numpy(dtype=float)
    drop = district.map(t["dropout"]).fillna(national["dropout"]).to_numpy(dtype=float)
    return rep, drop

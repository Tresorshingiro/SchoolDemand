"""The checks of each kind of data file. Each returns (parsed rows or None when there are errors, Report)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from ..domain import analysis as A
from ..domain import projection as P
from ..domain import rates as RT
from ..domain import teachers as T
from ..services.boundaries import place_key
from .report import Report
from .rooms import room_ids
from .summary import expand_summary, is_summary
from .tables import pick_columns, year_columns

# The roster columns, in the order the database gives them back (repository.ROSTER_SQL)
ROSTER_COLUMNS = ["school_code", "school_name", "district", "sector", "latitude", "longitude", "grade", "combination",
                  "class_group", "classroom_id", "classroom_name", A.STUDENTS, A.ROOM_ID]
SCHOOL_REQUIRED = ["school_code", "school_name", "district", "sector", "latitude", "longitude", "grade", "class_group",
                   "classroom_id", "classroom_name", A.STUDENTS]
SCHOOL_OPTIONAL = ["combination", A.ROOM_ID]
SCHOOL_ALIASES = {"students": A.STUDENTS}
DIFFERENCE = 0.20  # NISR vs catchment district totals: warn above this share


@dataclass
class CheckContext:
    """What the checks compare a file with (the live data)."""
    horizon: P.Horizon                               # the projection years with the data live today
    sectors: set[tuple[str, str]]                    # (district, sector) of the boundaries
    districts: list[str]                             # the 30 districts
    live_years: list[int]                            # published school years
    preprimary: set[int]                             # pre-primary school codes of the newest school year
    catchment_totals: pd.DataFrame | None            # district x year: children aged 3 from the live catchment
    roster_of: Callable[[int], pd.DataFrame]         # the published roster of a school year


def _rows(df: pd.DataFrame, mask, cols: list[str]) -> pd.DataFrame:
    return df.loc[mask, [c for c in cols if c in df.columns]]


def _whole(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Numbers (text accepted) and the mask of cells that are empty, not numbers or not whole numbers."""
    n = pd.to_numeric(values, errors="coerce")
    return n, n.isna() | (n % 1 != 0)


def _text(values: pd.Series) -> pd.Series:
    """Trimmed text, missing stays missing."""
    return values.where(values.isna(), values.astype(str).str.strip())


# ---------------------------------------------------------------- school data
def check_school_data(raw: pd.DataFrame, year: int | None, ctx: CheckContext) -> tuple[pd.DataFrame | None, Report]:
    """School data in either layout: one row per class group, or a grade summary (summary.py) turned into one."""
    rep = Report()
    summary = is_summary(raw)
    if summary:
        raw = expand_summary(raw, rep)
        if raw is None:
            return None, rep
    df, missing = pick_columns(raw, SCHOOL_REQUIRED, [*SCHOOL_OPTIONAL, "row"], SCHOOL_ALIASES)
    if missing:
        rep.error("missing_columns", "Missing columns: " + ", ".join(missing))
        return None, rep
    if df.empty:
        rep.error("no_rows", "The file has no rows.")
        return None, rep
    df = df.reset_index(drop=True)
    if "row" not in df:
        df.insert(0, "row", df.index + 2)  # the row in the workbook (row 1 = the headers)
    show = ["row", "school_code", "school_name", "grade", "class_group"]

    code, bad_code = _whole(df["school_code"])
    rep.error("school_code", "School code empty or not a number", _rows(df, bad_code, show))
    no_name = df["school_name"].isna() | (df["school_name"].astype(str).str.strip() == "")
    rep.error("school_name", "School without a name", _rows(df, no_name, show))
    grade = df["grade"].astype(str).str.strip().str.upper()
    rep.error("grade", "Unknown grade (expected N1-N3, P1-P6, S1-S6, L1-L5, Y1-Y3)",
              _rows(df, ~grade.isin(A.GRADE_ORDER), show))
    students, bad_students = _whole(df[A.STUDENTS])
    rep.error("students", "Number of students empty, negative or not a whole number",
              _rows(df.assign(students=df[A.STUDENTS]), bad_students | (students < 0), [*show, "students"]))
    if not rep.ok:
        return None, rep

    df["school_code"] = code.astype("int64")
    df["grade"] = grade
    df[A.STUDENTS] = students.astype(int)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    for c in ("school_name", "district", "sector"):
        df[c] = _text(df[c])
    if "combination" not in df:
        df["combination"] = None

    # schools that cannot be placed on the map are left out, as when Version 2.xlsx was made
    first = df.groupby("school_code").agg(latitude=("latitude", "first"), longitude=("longitude", "first"),
                                          students=(A.STUDENTS, "sum"))
    lost = first[first["latitude"].isna() | first["longitude"].isna()
                 | ~first["latitude"].between(*A.RW_LAT) | ~first["longitude"].between(*A.RW_LON)]
    if len(lost):
        rows = df[df["school_code"].isin(lost.index)].drop_duplicates("school_code")
        rep.warning("excluded", f"{len(lost)} school(s) left out: no coordinates or outside Rwanda "
                                f"({int(lost['students'].sum())} students)",
                    rows[["row", "school_code", "school_name", "district", "latitude", "longitude"]])
        df = df[~df["school_code"].isin(lost.index)]

    several = df.groupby("school_code")[["school_name", "district", "sector", "latitude", "longitude"]].nunique()
    several = several[(several > 1).any(axis=1)].index
    rep.warning("several_values", "A school with several names, districts, sectors or coordinates (the first is used)",
                df[df["school_code"].isin(several)].drop_duplicates("school_code")[["row", "school_code", "school_name"]])
    info = df.drop_duplicates("school_code")
    known = {place_key(d, s) for d, s in ctx.sectors}
    unknown = [place_key(d, s) not in known for d, s in zip(info["district"], info["sector"])]
    rep.warning("unknown_sector", "District / sector not in the boundaries (the school shows as Unknown)",
                info.loc[unknown, ["row", "school_code", "school_name", "district", "sector"]])

    if A.ROOM_ID not in df or df[A.ROOM_ID].isna().all():
        no_room = df["classroom_id"].isna() | (df["classroom_id"].astype(str).str.strip() == "")
        rep.warning("no_classroom", "Class group without classroom_id (counted as a room of its own)",
                    _rows(df, no_room, show))
        df[A.ROOM_ID] = room_ids(df)

    roster = A.prepare_roster(df[ROSTER_COLUMNS].reset_index(drop=True))
    for issue, rows in A.data_quality(roster).groupby("issue", sort=False):
        rep.warning("quality", issue, rows.drop(columns=["issue"]))
    rep.changes = _compare(roster, year, ctx)
    rep.summary = {"schools": int(roster["school_code"].nunique()), "class_groups": len(roster),
                   "students": int(roster[A.STUDENTS].sum()), "rooms": int(roster["room_key"].nunique()),
                   "layout": "grade summary" if summary else "class groups"}
    return roster, rep


LEVEL_MEASURES = {"total_students": "students", "total_classrooms": "class_groups", "available": "rooms",
                  "required": "required", "gap": "gap"}


def _level_totals(roster: pd.DataFrame) -> pd.DataFrame:
    t = A.school_table(roster).groupby("level")[list(LEVEL_MEASURES)].sum().rename(columns=LEVEL_MEASURES)
    return t.reindex(A.LEVEL_ORDER).fillna(0).astype(int)


def _compare(roster: pd.DataFrame, year: int | None, ctx: CheckContext) -> dict | None:
    """Against the same year when it is live (it will be replaced), else the newest live year."""
    if not ctx.live_years:
        return None
    against = year if year in ctx.live_years else max(ctx.live_years)
    old = ctx.roster_of(against)
    a, b = _level_totals(old), _level_totals(roster)
    old_codes, new_codes = set(old["school_code"]), set(roster["school_code"])
    return {
        "against": against,
        "replaces": year in ctx.live_years,
        "schools": [len(old_codes), len(new_codes)],
        "schools_added": len(new_codes - old_codes),
        "schools_removed": len(old_codes - new_codes),
        "levels": [{"level": lvl, **{m: [int(a.at[lvl, m]), int(b.at[lvl, m])] for m in LEVEL_MEASURES.values()}}
                   for lvl in A.LEVEL_ORDER if a.loc[lvl].any() or b.loc[lvl].any()],
    }


# ---------------------------------------------------------------- catchment and NISR
def _years_covered(rep: Report, years: list[int], horizon: P.Horizon) -> None:
    later = [y for y in horizon.future if y > max(years)]
    if later:
        rep.warning("years", f"No figures after {max(years)}: " + ", ".join(f"{y} repeats {max(years)}" for y in later))


def _values(rep: Report, t: pd.DataFrame, years: list[int], show: list[str]) -> pd.DataFrame | None:
    """The year columns as numbers; errors for text or negative values."""
    values = t[years].apply(pd.to_numeric, errors="coerce")
    bad = (values.isna() & t[years].notna()) | (values < 0)
    rep.error("values", "Population not a number or negative", t.loc[bad.any(axis=1), [*show, *years]])
    return values if rep.ok else None


def check_catchment(raw: pd.DataFrame, year: int | None, ctx: CheckContext) -> tuple[pd.DataFrame | None, Report]:
    rep = Report()
    df, missing = pick_columns(raw, ["school_code"])
    pops = year_columns(raw, "pop")
    if missing:
        rep.error("missing_columns", "Missing column: school_code")
    if not pops:
        rep.error("missing_columns", "No population columns: expected Pop2027, Pop2028 ...")
    if not rep.ok:
        return None, rep
    years = list(pops)
    t = pd.DataFrame({"row": raw.index + 2, "school_code": df["school_code"].to_numpy()})
    for y, col in pops.items():
        t[y] = raw[col].to_numpy()
    code, bad_code = _whole(t["school_code"])
    rep.error("school_code", "School code empty or not a number", t.loc[bad_code, ["row", "school_code"]])
    values = _values(rep, t, years, ["row", "school_code"])
    if values is None:
        return None, rep
    t[years] = values
    t["school_code"] = code.astype("int64")
    dup = t.duplicated("school_code")
    rep.warning("duplicates", "Repeated school code (the first row is kept)", t.loc[dup, ["row", "school_code"]])
    t = t[~dup]
    unknown = ~t["school_code"].isin(ctx.preprimary)
    rep.warning("unknown_schools", "Not a pre-primary school in the newest school data (ignored)",
                t.loc[unknown, ["row", "school_code"]])
    t = t[~unknown]
    with_figure = set(t.loc[t[years].notna().any(axis=1), "school_code"])
    rep.warning("no_figure", "Pre-primary schools without a figure (they keep their N1 students)",
                pd.DataFrame({"school_code": sorted(ctx.preprimary - with_figure)}))
    _years_covered(rep, years, ctx.horizon)
    parsed = t.set_index("school_code")[years]
    rep.summary = {"schools": len(parsed), "years": years}
    return parsed, rep


def check_nisr(raw: pd.DataFrame, year: int | None, ctx: CheckContext) -> tuple[pd.DataFrame | None, Report]:
    rep = Report()
    df, missing = pick_columns(raw, ["district_name"], aliases={"district": "district_name"})
    pops = year_columns(raw, "pop3")
    if missing:
        rep.error("missing_columns", "Missing column: district_name")
    if not pops:
        rep.error("missing_columns", "No population columns: expected pop3_2027, pop3_2028 ...")
    if not rep.ok:
        return None, rep
    years = list(pops)
    t = pd.DataFrame({"row": raw.index + 2, "district_name": df["district_name"].astype(str).str.strip().to_numpy()})
    for y, col in pops.items():
        t[y] = raw[col].to_numpy()
    canonical = {d.casefold(): d for d in ctx.districts}
    t["district"] = t["district_name"].str.casefold().map(canonical)
    rep.error("unknown_districts", "Unknown district (not one of the 30 districts)",
              t.loc[t["district"].isna(), ["row", "district_name"]])
    rep.error("duplicates", "The same district twice",
              t.loc[t["district"].notna() & t.duplicated("district", keep=False), ["row", "district_name"]])
    values = _values(rep, t, years, ["row", "district_name"])
    if values is None:
        return None, rep
    parsed = pd.DataFrame({y: values[y].to_numpy() for y in years}, index=pd.Index(t["district"], name="district"))
    rep.warning("missing_districts", "Districts not in the file (they keep the catchment total)",
                pd.DataFrame({"district": [d for d in ctx.districts if d not in parsed.index]}))
    _years_covered(rep, years, ctx.horizon)
    if ctx.catchment_totals is not None:
        rows = []
        for d, row in parsed.iterrows():
            for y, v in row.items():
                c = ctx.catchment_totals.at[d, y] if d in ctx.catchment_totals.index and y in ctx.catchment_totals else None
                if c and not pd.isna(v) and abs(v - c) / c > DIFFERENCE:
                    rows.append({"district": d, "year": y, "nisr": int(v), "catchment": int(c),
                                 "difference": f"{(v - c) / c:+.0%}"})
        rep.warning("difference", f"NISR total differs from the catchment total by more than {DIFFERENCE:.0%}",
                    pd.DataFrame(rows))
    rep.summary = {"districts": len(parsed), "years": years}
    return parsed, rep


# ---------------------------------------------------------------- repetition / dropout rates and teachers
def check_flow_rates(raw: dict[str, pd.DataFrame], year: int | None, ctx: CheckContext
                     ) -> tuple[pd.DataFrame | None, Report]:
    """The MINEDUC rates workbook (both sheets, read with header=None): rows of RT.read_sheets, every school year."""
    rep = Report()
    try:
        long = RT.read_sheets(raw)
    except ValueError as e:
        rep.error("structure", str(e))
        return None, rep
    show = ["district", "school_year", "repetition", "dropout"]
    values = long[["repetition", "dropout"]].apply(pd.to_numeric, errors="coerce")
    bad = (values.isna() | (values < 0) | (values > 1)).any(axis=1)
    rep.error("values", "Rate empty, not a number or outside 0-1 (0.204 = 20.4%)", long.loc[bad, show])
    long[["repetition", "dropout"]] = values
    rep.error("sum", "Repetition + dropout of 1 or more (nobody would be promoted)",
              long.loc[~bad & (values.sum(axis=1) >= 1), show])
    canonical = {d.casefold(): d for d in [*ctx.districts, RT.NATIONAL]}
    long["district"] = long["district"].map(lambda d: canonical.get(d.casefold(), d))
    newest = long[long["end_year"] == long["end_year"].max()]
    if RT.NATIONAL not in set(newest["district"]):
        rep.error("no_national", f"No {RT.NATIONAL} row in {newest['school_year'].iloc[0]}: it is used for schools "
                                 "without a district")
    if not rep.ok:
        return None, rep
    unknown = ~long["district"].isin(canonical.values())
    rep.warning("unknown_districts", "Unknown district (not one of the 30 districts; ignored)",
                long.loc[unknown, ["district", "school_year"]].drop_duplicates("district"))
    long = long[~unknown].reset_index(drop=True)
    rep.warning("missing_districts", f"Districts without rates in {newest['school_year'].iloc[0]} (they use the "
                                     f"{RT.NATIONAL} rates)",
                pd.DataFrame({"district": [d for d in ctx.districts if d not in set(newest["district"])]}))
    rep.summary = {"school_year": newest["school_year"].iloc[0], "districts": int(newest["district"].nunique()),
                   "school_years": sorted(long["school_year"].unique().tolist())}
    return long, rep


def check_teachers(raw: pd.DataFrame, year: int | None, ctx: CheckContext) -> tuple[pd.DataFrame | None, Report]:
    """The MINEDUC teachers file: one row per school, teachers per level (blank = none)."""
    rep = Report()
    df, missing = pick_columns(raw, ["school_code"], [*T.LEVEL_COLUMNS, *T.STAFF_COLUMNS])
    levels = [c for c in T.LEVEL_COLUMNS if c in df]
    if missing:
        rep.error("missing_columns", "Missing column: school_code")
    if not levels:
        rep.error("missing_columns", "No teacher columns: expected " + ", ".join(T.LEVEL_COLUMNS))
    if not rep.ok:
        return None, rep
    df = df.reset_index(drop=True)
    df.insert(0, "row", df.index + 2)
    code, bad_code = _whole(df["school_code"])
    rep.error("school_code", "School code empty or not a number", df.loc[bad_code, ["row", "school_code"]])
    numbers = df[levels].apply(pd.to_numeric, errors="coerce")
    bad = ((numbers.isna() & df[levels].notna()) | (numbers < 0) | (numbers % 1 > 0)).any(axis=1)
    rep.error("values", "Teachers not a whole number or negative", df.loc[bad, ["row", "school_code", *levels]])
    dup = ~bad_code & code.duplicated(keep=False)
    rep.error("duplicates", "The same school twice", df.loc[dup, ["row", "school_code"]])
    if not rep.ok:
        return None, rep
    df["school_code"] = code.astype("int64")
    df[levels] = numbers
    if "total_teaching_staff" in df:
        total = pd.to_numeric(df["total_teaching_staff"], errors="coerce")
        off = total.notna() & (numbers.fillna(0).sum(axis=1) != total)
        rep.warning("total", "The levels do not add up to total_teaching_staff (the levels are used)",
                    df.loc[off, ["row", "school_code", *levels, "total_teaching_staff"]])
    if ctx.live_years and year is not None and year > max(ctx.live_years):
        rep.warning("no_school_year", f"No school data for {year} yet: these teachers show on the dashboard once the "
                                      f"{year} school data is published (checked against {max(ctx.live_years)})")
    if ctx.live_years:
        roster = ctx.roster_of(year if year in ctx.live_years else max(ctx.live_years))
        unknown = ~df["school_code"].isin(set(roster["school_code"]))
        rep.warning("unknown_schools", "Not a school of the school data (ignored)",
                    df.loc[unknown, ["row", "school_code"]])
        issues = T.teacher_issues(roster, T.to_long(df))
        for code_, issue in (("no_teachers", T.NO_TEACHERS), ("no_students", T.NO_STUDENTS)):
            rep.warning(code_, issue, issues.loc[issues["issue"] == issue, ["school_code", "detail"]])
    rep.summary = {"schools": len(df), "teachers": int(numbers.sum().sum())}
    return df.drop(columns=["row"]), rep


CHECKS = {"school_data": check_school_data, "catchment": check_catchment, "nisr_population": check_nisr,
          "flow_rates": check_flow_rates, "teachers": check_teachers}


# ---------------------------------------------------------------- templates (the portal's "Template" downloads)
def _school_template(h: P.Horizon) -> pd.DataFrame:
    return pd.DataFrame([{
        "school_code": 110103, "school_name": "EP GITEGA", "district": "Nyarugenge", "sector": "Gitega",
        "latitude": -1.95978, "longitude": 30.05631, "grade": "P1", "combination": "", "class_group": "P1 A",
        "classroom_id": "a9c0b300-8280-4d7e-bed5-b991837c0262", "classroom_name": "P1 A", A.STUDENTS: 45}])


def _rates_sheet(title: str, rows: dict[str, tuple[float, float, float]]) -> pd.DataFrame:
    """A rates sheet in the MINEDUC layout (written without a header row): rows = {district: (male, female, average)}."""
    head = [[title, None, None, None], [None, "2023/24", None, None], ["District", "Male", "Female", "Average"]]
    return pd.DataFrame(head + [[d, *v] for d, v in rows.items()])


def _rates_template(h: P.Horizon) -> dict[str, pd.DataFrame]:
    return {"Repetition Rate": _rates_sheet("Repetition rate", {"Gasabo": (0.117, 0.096, 0.107),
                                                                RT.NATIONAL: (0.223, 0.186, 0.204)}),
            "Dropout Rate": _rates_sheet("Dropout rate", {"Gasabo": (0.039, 0.031, 0.035),
                                                          RT.NATIONAL: (0.054, 0.043, 0.049)})}


def _teachers_template(h: P.Horizon) -> pd.DataFrame:
    return pd.DataFrame([{"school_code": 110103, "school_name": "EP GITEGA", "district": "Nyarugenge",
                          "sector": "Gitega", "school_status": "PUBLIC", "total_preprimary_teachers": 6,
                          "total_primary_teachers": 27, "total_lower_secondary_teachers": None,
                          "Prof_sec_teacher_total": None, "total_upper_secondary_teachers": None,
                          "total_tvet_teachers": None, "total_teaching_staff": 33, "total_administrative_staff": 2}])


# A table, or {sheet name: sheet written as laid out} for a workbook of several sheets
TEMPLATES: dict[str, Callable[[P.Horizon], pd.DataFrame | dict[str, pd.DataFrame]]] = {
    "school_data": _school_template,
    "catchment": lambda h: pd.DataFrame([{"school_code": 110103, **{f"Pop{y}": 37 for y in h.future}}]),
    "nisr_population": lambda h: pd.DataFrame([{"district_name": "Gasabo", **{f"pop3_{y}": 12000 for y in h.future}}]),
    "flow_rates": _rates_template,
    "teachers": _teachers_template,
}

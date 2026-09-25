"""
Build a classroom projection workbook (2026-2030, all levels) for an intake plan:

  output/Classroom_Projection_2026_2030_Catchment.xlsx  new N1 = children aged 3 in each pre-primary school's
                                                         catchment (default); new P1 = N3 of the year before
  output/Classroom_Projection_2026_2030_<plan>.xlsx     with --intake <plan>.csv (e.g. the CSV downloaded
                                                         from the dashboard's intake planner)

Same layout and measures as School_Classroom_Analysis_2026.xlsx, with a Year
column. Projected students, class groups and rooms shared to each grade come
from scripts/projection.py and are written as values; double shift, required
classrooms, gap and every summary are Excel formulas, so editing a capacity on
the Settings sheet recalculates the workbook.

Run:  python scripts/build_projection_workbook.py
      python scripts/build_projection_workbook.py --intake intake_plan.csv
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

import analysis as A
import projection as P
from build_workbook import (
    BOX, F_BODY, F_BOLD, F_HEAD, F_INPUT, F_LINK, F_NOTE, F_SUB, FILL_HEAD, FILL_INPUT, FILL_TOTAL, GAP, HEAD_ALIGN,
    METRIC_WIDTHS, NUM, PCT, SUMMARY_METRICS, WRAP, gap_colours, header, metric_formulas, put, q,
    status_colours, title, write_metrics,
)

OUT_DIR = A.ROOT / "output"
README, SETTINGS, ENTRANTS, NATIONAL, DISTRICT, SECTOR = (
    "Read Me", "Settings", "New Students", "National Summary", "District Summary", "Sector Summary",
)
SCHOOL, GRADE, TOP = "School-Level Summary", "Per-Grade Breakdown", "Top Deficits"
COMBO = "Per-Combination Breakdown"
LEVEL_LABELS = [label for label, _ in P.LEVELS]
SET_FIRST = 5  # first level row on the Settings sheet; capacity in column C
CAP_CELL = {label: f"{q(SETTINGS)}$C${SET_FIRST + i}" for i, label in enumerate(LEVEL_LABELS)}

# Source columns on the School-Level / Per-Grade sheets, for the summary formulas
SCHOOL_COLS = {"year": "A", "district": "D", "sector": "E", "level": "F", "students": "G", "total": "H",
               "double": "I", "available": "J", "required": "L", "gap": "M"}
GRADE_COLS = {"year": "A", "district": "D", "sector": "E", "level": "F", "grade": "G", "students": "H", "total": "I",
              "available": "J", "double": "K", "required": "M", "gap": "N"}


# ---------------------------------------------------------------- inputs
def build_settings(ws, label: str) -> None:
    title(ws, "Settings", "Blue values on yellow are inputs. Change a capacity and every sheet recalculates.")
    header(ws, 4, ["Level", "Grades Projected", "Standard Classroom Capacity", "Note"], [20, 22, 16, 80])
    for i, (lvl, grades) in enumerate(P.LEVELS):
        r = SET_FIRST + i
        put(ws, r, 1, lvl, font=F_BOLD)
        put(ws, r, 2, ", ".join(grades))
        c = put(ws, r, 3, P.CAPACITY[lvl], NUM, F_INPUT)
        c.fill = FILL_INPUT
        note = "Students per classroom (brief: 45; the client confirmed 45 for every level)."
        if lvl == "TVET":
            note += " L1-L2 short courses are not projected."
        put(ws, r, 4, note).alignment = WRAP
        for col in range(1, 5):
            ws.cell(row=r, column=col).border = BOX
    r = SET_FIRST + len(P.LEVELS) + 1
    put(ws, r, 1, "Intake plan", font=F_BOLD)
    put(ws, r, 2, label, font=F_BOLD)
    put(ws, r, 4, f"Fixed for this workbook (see the {ENTRANTS} sheet). Other plans are built into their own "
                  "workbooks.").alignment = WRAP
    ws.freeze_panes = "A5"


def build_entrants(ws, info: pd.DataFrame, g: pd.DataFrame, intake: dict, pop: dict, label: str) -> None:
    title(ws, f"New Students — intake: {label}",
          "Where each level's new students come from, by district. Values from projection.py.")
    ws["A3"] = ("N1: the intake plan (default: children aged 3 in the schools' catchment areas). P1: the N3 of the year "
                "before (own school; stand-alone nurseries shared by sector). S1: all P6 of the district the year before. "
                "S4 / L3 / Y1: all S3 of the district the year before, split by the district's 2026 mix. 'In schools' = "
                "after sharing to schools and rounding per school, so it can differ by a few students.")
    ws["A3"].font = F_NOTE
    by = g.pivot_table(index="district", columns=["grade", "year"], values="students", aggfunc="sum", fill_value=0)
    districts = sorted(info["district"].unique())
    years = P.YEARS[1:]
    ws.column_dimensions["A"].width = 16
    r = 5
    for grade in [grades[0] for _, grades in P.LEVELS]:
        feed = next((f for f in P.FEEDS if grade in f[1]), None) or \
            next(((src, [dst]) for src, dst in P.SCHOOL_FEEDS if dst == grade), None)
        same_school = any(dst == grade for _, dst in P.SCHOOL_FEEDS)
        if grade in P.INTAKES:
            age = P.INTAKES[grade]
            est = P.ESTIMATED.get(grade, [])
            heading = f"{grade} — children aged {age} (intake plan)"
            cols = ["District", f"{grade} Students {P.BASE_YEAR}",
                    *[f"Catchment Aged {age} in {y}{' (= prior year)' if y in est else ''}" for y in years],
                    *[f"Plan {y}" for y in years], *[f"In Schools {y}" for y in years]]

            def values(d, grade=grade):
                nisr = [int(pop[grade].loc[d, y]) if d in pop[grade].index else 0 for y in years]
                plan = [int(intake[grade].loc[d, y]) if d in intake[grade].index and y in intake[grade].columns else 0
                        for y in years]
                return [int(by.get((grade, P.BASE_YEAR), pd.Series()).get(d, 0)), *nisr, *plan,
                        *[int(by.get((grade, y), pd.Series()).get(d, 0)) for y in years]], nisr, plan
        else:
            src, targets = feed
            split = len(targets) > 1
            heading = f"{grade} — from the {src} of the year before" + (f" ({' / '.join(targets)} split)" if split else "") + \
                (" (same school; stand-alone nurseries shared by sector)" if same_school else "")
            cols = ["District", f"{grade} Students {P.BASE_YEAR}", *([f"Share of {src} Leavers"] if split else []),
                    *[f"{src} in {y - 1}" for y in years], *[f"New {grade} {y}" for y in years]]

            def values(d, grade=grade, src=src, targets=targets, split=split):
                base = [int(by.get((t, P.BASE_YEAR), pd.Series()).get(d, 0)) for t in targets]
                mix = [base[targets.index(grade)] / sum(base)] if split and sum(base) else ([0] if split else [])
                return [int(by.get((grade, P.BASE_YEAR), pd.Series()).get(d, 0)), *mix,
                        *[int(by.get((src, y - 1), pd.Series()).get(d, 0)) for y in years],
                        *[int(by.get((grade, y), pd.Series()).get(d, 0)) for y in years]], None, None
        ws.cell(row=r, column=1, value=heading).font = F_SUB
        header(ws, r + 1, cols, [16] + [12] * (len(cols) - 1))
        first = r + 2
        for i, d in enumerate(districts):
            rr = first + i
            vals, nisr, plan = values(d)
            put(ws, rr, 1, d, font=F_BOLD)
            for c, v in enumerate(vals, 2):
                fmt = PCT if isinstance(v, float) else NUM
                changed = plan is not None and 2 + 1 + len(years) <= c < 2 + 1 + 2 * len(years) and \
                    plan[c - 3 - len(years)] != nisr[c - 3 - len(years)]
                put(ws, rr, c, v, fmt, F_BOLD if changed else F_BODY)
            for c in range(1, len(cols) + 1):
                ws.cell(row=rr, column=c).border = BOX
        last = first + len(districts) - 1
        tot = last + 1
        put(ws, tot, 1, "Rwanda", font=F_BOLD)
        for c in range(2, len(cols) + 1):
            col = get_column_letter(c)
            if cols[c - 1].startswith("Share"):
                continue
            put(ws, tot, c, f"=SUM({col}{first}:{col}{last})", NUM, F_BOLD)
        for c in range(1, len(cols) + 1):
            ws.cell(row=tot, column=c).fill = FILL_TOTAL
        r = tot + 3
    ws.cell(row=r - 1, column=1, value=f"Bold plan values differ from the {P.DEFAULT_LABEL.lower()} default.").font = F_NOTE


# ---------------------------------------------------------------- detail tables
def build_school(ws, s: pd.DataFrame) -> int:
    title(ws, "School-Level Summary", "One row per school x level x year. Rooms are the level's 2026 physical rooms, "
                                      "held constant. Counts come from projection.py; the rest are formulas.")
    cols = ["Year", "School Code", "School Name", "District", "Sector", "Level", "Total Students", "Total Classrooms",
            "Total Classrooms in Double Shift", "Total Classrooms Available", "Standard Classroom Capacity",
            "Required Classrooms", "Gap (Deficit vs Surplus)", "Status"]
    header(ws, 4, cols, [11, 11, 34, 13, 15, 16, 13, 17, 20.5, 18, 17, 17, 18, 12])
    ws["H4"].comment = Comment("Class groups. Each cohort keeps its groups as it moves up; new entry-grade groups are "
                               "formed at the school's average group size for that grade in 2026.", "Analysis")
    ws["I4"].comment = Comment("= MAX(0, class groups - rooms): groups that must share a room.", "Analysis")
    ws["J4"].comment = Comment("The school's distinct physical rooms used by the level in 2026 (no construction "
                               "assumed).", "Analysis")
    for i, row in enumerate(s.itertuples(index=False)):
        r = 5 + i
        put(ws, r, 1, row.year)
        put(ws, r, 2, int(row.school_code))
        put(ws, r, 3, row.school_name)
        put(ws, r, 4, row.district)
        put(ws, r, 5, row.sector)
        put(ws, r, 6, row.level)
        put(ws, r, 7, int(row.students), NUM)
        put(ws, r, 8, int(row.class_groups), NUM)
        put(ws, r, 9, f"=MAX(0,H{r}-J{r})", NUM)
        put(ws, r, 10, int(row.rooms), NUM)
        put(ws, r, 11, f"={CAP_CELL[row.level]}", NUM)
        put(ws, r, 12, int(row.required) if row.level in A.FULL_DAY else f"=ROUNDUP(G{r}/K{r},0)", NUM)
        put(ws, r, 13, f"=J{r}-L{r}", GAP)
        put(ws, r, 14, f'=IF(M{r}<0,"Deficit",IF(M{r}=0,"Exact fit","Surplus"))')
    last = 4 + len(s)
    gap_colours(ws, f"M5:M{last}")
    status_colours(ws, f"N5:N{last}", "$N5")
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:N{last}"
    return last


def build_grade(ws, g: pd.DataFrame) -> int:
    title(ws, "Per-Grade Breakdown", "One row per school x grade x year. The level's rooms are shared between its "
                                     "grades each year (see Read Me); counts come from projection.py.")
    cols = ["Year", "School Code", "School Name", "District", "Sector", "Level", "Grade", "Total Students",
            "Total Classrooms", "Classrooms Assigned", "Total Classrooms in Double Shift", "Standard Classroom Capacity",
            "Required Classrooms", "Gap (Deficit vs Surplus)", "Status"]
    header(ws, 4, cols, [11, 11, 34, 13, 15, 16, 9, 13, 17, 16, 20.5, 17, 17, 18, 12])
    ws["J4"].comment = Comment("Rooms this grade gets this year. More groups than rooms: rooms shared in proportion "
                               "to class groups. Enough rooms: every group keeps a room and spare rooms go to grades "
                               "that need them.", "Analysis")
    ws["K4"].comment = Comment("= MAX(0, class groups - classrooms assigned).", "Analysis")
    for i, row in enumerate(g.itertuples(index=False)):
        r = 5 + i
        put(ws, r, 1, row.year)
        put(ws, r, 2, int(row.school_code))
        put(ws, r, 3, row.school_name)
        put(ws, r, 4, row.district)
        put(ws, r, 5, row.sector)
        put(ws, r, 6, row.level)
        put(ws, r, 7, row.grade)
        put(ws, r, 8, int(row.students), NUM)
        put(ws, r, 9, int(row.class_groups), NUM)
        put(ws, r, 10, int(row.rooms), NUM)
        put(ws, r, 11, f"=MAX(0,I{r}-J{r})", NUM)
        put(ws, r, 12, f"={CAP_CELL[row.level]}", NUM)
        put(ws, r, 13, int(row.required) if row.level in A.FULL_DAY else f"=ROUNDUP(H{r}/L{r},0)", NUM)
        put(ws, r, 14, f"=J{r}-M{r}", GAP)
        put(ws, r, 15, f'=IF(N{r}<0,"Deficit",IF(N{r}=0,"Exact fit","Surplus"))')
    last = 4 + len(g)
    gap_colours(ws, f"N5:N{last}")
    status_colours(ws, f"O5:O{last}", "$O5")
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:O{last}"
    return last


def build_combo(ws, c: pd.DataFrame) -> int:
    title(ws, "Per-Combination Breakdown", "One row per school x grade x combination x year (Upper Secondary, TVET, TTC). "
                                           "A breakdown of the Per-Grade rows; values from projection.py.")
    cols = ["Year", "School Code", "School Name", "District", "Sector", "Level", "Grade", "Combination",
            "Total Students", "Total Classrooms"]
    header(ws, 4, cols, [11, 11, 34, 13, 15, 16, 9, 28, 13, 17])
    ws["H4"].comment = Comment("Students keep their combination as they move up. A school's new S4 / L3 / Y1 students "
                               "and class groups are split by its 2026 mix in that grade.", "Analysis")
    for i, row in enumerate(c.itertuples(index=False)):
        r = 5 + i
        for col, v in enumerate([row.year, int(row.school_code), row.school_name, row.district, row.sector, row.level,
                                 row.grade, row.combination], 1):
            put(ws, r, col, v)
        put(ws, r, 9, int(row.students), NUM)
        put(ws, r, 10, int(row.class_groups), NUM)
    last = 4 + len(c)
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:J{last}"
    return last


# ---------------------------------------------------------------- summaries
def crit_pairs(sheet: str, cols: dict, last: int, keys: list[tuple[str, str]]) -> str:
    """SUMIFS criteria pairs: keys = [(column key on `sheet`, criteria cell)]."""
    return ",".join(f"{q(sheet)}${cols[k]}$5:${cols[k]}${last},{cell}" for k, cell in keys)


def build_national(ws, s_last: int, g_last: int, c: pd.DataFrame, c_last: int) -> None:
    title(ws, "National Summary", "All figures are formulas over the School-Level Summary and Per-Grade Breakdown sheets.")
    ws["A3"] = ("Classrooms Short adds up only the shortages of schools in deficit (a spare room in one school cannot seat "
                "pupils from another) — it is the number of classrooms to build. Net Gap nets surpluses against deficits.")
    ws["A3"].font = F_NOTE

    # --- classrooms to build: year x level (headline)
    r = 5
    ws.cell(row=r, column=1, value="Classrooms to build (Classrooms Short)").font = F_SUB
    header(ws, r + 1, ["Year", *LEVEL_LABELS, "All Levels"], [16] + [14] * (len(LEVEL_LABELS) + 1))
    b_first = r + 2
    gap = f"{q(SCHOOL)}${SCHOOL_COLS['gap']}$5:${SCHOOL_COLS['gap']}${s_last}"
    for i, year in enumerate(P.YEARS):
        rr = b_first + i
        put(ws, rr, 1, year, font=F_BOLD)
        for j, _ in enumerate(LEVEL_LABELS):
            lvl_cell = f"{get_column_letter(2 + j)}${r + 1}"
            crit = crit_pairs(SCHOOL, SCHOOL_COLS, s_last, [("year", f"$A{rr}"), ("level", lvl_cell)])
            put(ws, rr, 2 + j, f'=-SUMIFS({gap},{crit},{gap},"<0")', NUM)
        c_tot = 2 + len(LEVEL_LABELS)
        put(ws, rr, c_tot, f"=SUM(B{rr}:{get_column_letter(c_tot - 1)}{rr})", NUM, F_BOLD)
    b_last = b_first + len(P.YEARS) - 1

    # --- by level and year
    r = b_last + 3
    ws.cell(row=r, column=1, value="By level and year").font = F_SUB
    header(ws, r + 1, ["Level", "Year", *SUMMARY_METRICS], [16, 8, *METRIC_WIDTHS])
    first = r + 2
    rr = first
    for level in LEVEL_LABELS:
        for year in P.YEARS:
            put(ws, rr, 1, level, font=F_BOLD)
            put(ws, rr, 2, year)
            crit = crit_pairs(SCHOOL, SCHOOL_COLS, s_last, [("level", f"$A{rr}"), ("year", f"$B{rr}")])
            write_metrics(ws, rr, 3, metric_formulas(rr, 3, SCHOOL, SCHOOL_COLS, crit, s_last))
            rr += 1
    gap_colours(ws, f"I{first}:I{rr - 1}")

    # --- by grade and year
    r = rr + 2
    ws.cell(row=r, column=1, value="By grade and year").font = F_SUB
    ws.cell(row=r + 1, column=1, value=(
        "Read down a grade's rows to follow the grade; follow a cohort diagonally (P1 2026 -> P2 2027 -> P3 2028 ...). "
        "Grade rows use the classrooms assigned to each grade; Schools counts schools offering the grade's level.")).font = F_NOTE
    header(ws, r + 2, ["Grade", "Year", *SUMMARY_METRICS])
    g_first = r + 3
    rr = g_first
    for grade in P.GRADES:
        for year in P.YEARS:
            put(ws, rr, 1, grade, font=F_BOLD)
            put(ws, rr, 2, year)
            crit = crit_pairs(GRADE, GRADE_COLS, g_last, [("grade", f"$A{rr}"), ("year", f"$B{rr}")])
            write_metrics(ws, rr, 3, metric_formulas(rr, 3, GRADE, GRADE_COLS, crit, g_last))
            rr += 1
    gap_colours(ws, f"I{g_first}:I{rr - 1}")

    # --- students by combination and year (Upper Secondary, TVET, TTC)
    r = rr + 2
    ws.cell(row=r, column=1, value="Students by combination and year").font = F_SUB
    ws.cell(row=r + 1, column=1, value=(
        f"Formulas over the {COMBO} sheet. Students keep their combination as they move up; new S4 / L3 / Y1 follow "
        "each school's 2026 mix. Rooms are counted per grade, not per combination.")).font = F_NOTE
    header(ws, r + 2, ["Level", "Combination", *[f"Students {y}" for y in P.YEARS], *[f"Class Groups {y}" for y in P.YEARS]])
    rng = lambda col: f"{q(COMBO)}${col}$5:${col}${c_last}"  # noqa: E731
    tot = c.groupby(["level", "combination"])["students"].sum()
    rr = r + 3
    for level in [x for x in LEVEL_LABELS if x in P.COMBO_LEVELS]:
        for combo in tot[level].sort_values(ascending=False).index:
            put(ws, rr, 1, level, font=F_BOLD)
            put(ws, rr, 2, combo)
            for j, year in enumerate(P.YEARS):
                crit = f"{rng('F')},$A{rr},{rng('H')},$B{rr},{rng('A')},{year}"
                put(ws, rr, 3 + j, f"=SUMIFS({rng('I')},{crit})", NUM)
                put(ws, rr, 3 + len(P.YEARS) + j, f"=SUMIFS({rng('J')},{crit})", NUM)
            rr += 1
    ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 0, 30)
    ws.freeze_panes = "B5"


def build_area(ws, s: pd.DataFrame, s_last: int, by_sector: bool) -> None:
    name = "Sector" if by_sector else "District"
    title(ws, f"{name} Summary", f"One row per {name.lower()} x level x year. Formulas over the School-Level Summary "
                                 "sheet. Classrooms Short counts only schools in deficit. Filter Level and Year to compare areas.")
    keys = ["district", "sector", "level"] if by_sector else ["district", "level"]
    labels = ["District", "Sector", "Level", "Year"] if by_sector else ["District", "Level", "Year"]
    header(ws, 4, [*labels, *SUMMARY_METRICS], ([14, 16, 16] if by_sector else [14, 16]) + [8] + METRIC_WIDTHS)
    combos = s[keys].drop_duplicates()
    combos["_l"] = combos["level"].map({x: i for i, x in enumerate(LEVEL_LABELS)})
    combos = combos.sort_values([*keys[:-1], "_l"])
    c0 = len(labels) + 1
    r = 5
    for row in combos.itertuples(index=False):
        for year in P.YEARS:
            parts = []
            for j, key in enumerate(keys):
                put(ws, r, j + 1, getattr(row, key), font=F_BOLD if key == "level" else F_BODY)
                parts.append((key, f"${get_column_letter(j + 1)}{r}"))
            put(ws, r, len(labels), year)
            parts.append(("year", f"${get_column_letter(len(labels))}{r}"))
            write_metrics(ws, r, c0, metric_formulas(r, c0, SCHOOL, SCHOOL_COLS, crit_pairs(SCHOOL, SCHOOL_COLS, s_last, parts), s_last))
            r += 1
    last = r - 1
    gap_col = get_column_letter(c0 + 6)
    gap_colours(ws, f"{gap_col}5:{gap_col}{last}")
    ws.freeze_panes = ws.cell(row=5, column=c0)
    ws.auto_filter.ref = f"A4:{get_column_letter(c0 + 11)}{last}"


def build_top(ws, s: pd.DataFrame, year: int, n: int = 50) -> None:
    title(ws, f"Top Deficits {year}", f"The {n} schools with the largest classroom deficit in {year} for each level, "
                                      "with their 2026 gap for comparison. Values link live to the School-Level Summary.")
    cols = ["Level", "Rank", "School Code", "School Name", "District", "Sector", f"Students {year}", "Classrooms Available",
            f"Required {year}", f"Gap {year}", f"Double Shift {year}", "Gap 2026 (actual)"]
    header(ws, 4, cols, [16, 7, 11, 34, 13, 15, 12, 14, 12, 11, 12, 13])
    rows = s.reset_index(drop=True)
    row_of = {(y, c, lv): 5 + i for i, (y, c, lv) in enumerate(zip(rows["year"], rows["school_code"], rows["level"]))}
    r = 5
    for level in LEVEL_LABELS:
        sel = rows[(rows["year"] == year) & (rows["level"] == level) & (rows["gap"] < 0)]
        top = sel.sort_values(["gap", "students"], ascending=[True, False]).head(n)
        for rank, rec in enumerate(top.itertuples(index=False), 1):
            src, base = row_of[(year, rec.school_code, level)], row_of[(P.BASE_YEAR, rec.school_code, level)]
            put(ws, r, 1, level, font=F_BOLD)
            put(ws, r, 2, rank)
            for c, (col, fmt) in enumerate([("B", None), ("C", None), ("D", None), ("E", None), ("G", NUM), ("J", NUM),
                                            ("L", NUM), ("M", GAP), ("I", NUM)], 3):
                put(ws, r, c, f"={q(SCHOOL)}{col}{src}", fmt, F_LINK)
            put(ws, r, 12, f"={q(SCHOOL)}M{base}", GAP, F_LINK)
            r += 1
    last = r - 1
    gap_colours(ws, f"J5:J{last}")
    gap_colours(ws, f"L5:L{last}")
    ws.freeze_panes = "E5"
    ws.auto_filter.ref = f"A4:L{last}"


# ---------------------------------------------------------------- read me
def build_readme(ws, label: str, info: pd.DataFrame, summ: pd.DataFrame, s_last: int, p5: int, p6: int) -> None:
    title(ws, f"Classroom Projection 2026-2030, all levels — intake: {label}")
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 110
    est = ", ".join(f"{g} {', '.join(map(str, ys))}" for g, ys in P.ESTIMATED.items())
    lines = [
        ("Question", "As each cohort moves up a grade and new children start school, how are each school's existing "
                     "classrooms shared, how much double shift is needed, and how many classrooms are short each year, "
                     "for every level?", "row"),
        ("Sources", f"{A.SOURCE_XLSX.name} (2026 roster, {len(info):,} schools) and {P.CATCHMENT_XLSX.name} (children "
                    f"aged 3 in each pre-primary school's catchment area, 2027-2030: NISR population shared to schools "
                    f"by GIS). Built {date.today():%d %B %Y}.", "row"),
        ("Intake plan", f"{label}. New students per district and year are on the {ENTRANTS} sheet.", "row"),
        ("", None, "gap"),
        ("Sheets", None, "head"),
        (NATIONAL, "Classrooms to build by year and level, totals by level and year, and every grade x year.", "row"),
        (DISTRICT, "District x level x year.", "row"),
        (SECTOR, "Sector x level x year.", "row"),
        (SCHOOL, "School x level x year (like brief section 3b).", "row"),
        (GRADE, "School x grade x year (like brief section 3a), with the classrooms assigned to each grade.", "row"),
        (COMBO, "School x grade x combination x year for Upper Secondary, TVET and TTC (students, class groups).", "row"),
        (TOP, f"Largest deficits in {P.YEARS[-1]} for each level.", "row"),
        (ENTRANTS, "Where each level's new students come from, by district and year.", "row"),
        ("", None, "gap"),
        ("Method", None, "head"),
        ("Levels", "Pre-Primary N1-N3, Primary P1-P6, Lower Secondary S1-S3, Upper Secondary S4-S6, TVET L3-L5 and TTC "
                   "Y1-Y3. TVET L1-L2 (short courses) are not projected.", "row"),
        ("Cohorts move up", "Each year every grade moves up one step with its class groups; the last grade of a level "
                            "leaves it.", "row"),
        ("New N1", "The intake plan: by default every child aged 3 in a pre-primary school's catchment area enters "
                   "that school's N1. A school without a figure for a year keeps its last known one (its 2026 N1 when it "
                   "has none). A district's plan is shared to its schools in proportion to their catchment. "
                   f"Not measured (the catchment data repeats the year before): {est}.", "row"),
        ("New P1", "The N3 of the year before: each school's N3 moves up to its own P1; the N3 of schools without "
                   "primary (stand-alone nurseries) is shared to the primary schools of their sector by their 2026 P1. "
                   "Children who did not attend pre-primary are not added, so new P1 follows pre-primary enrolment.", "row"),
        ("New S1", "All P6 pupils of the district the year before.", "row"),
        ("New S4, L3 and Y1", "All S3 students of the district the year before, split by the district's 2026 mix of "
                              "S4 / L3 / Y1 students.", "row"),
        ("Into schools", "A district's new S1 / S4 / L3 / Y1 students are shared to its schools in proportion to each school's "
                         "students in that grade in 2026 (rounded per school) and formed into class groups at the "
                         "school's 2026 average group size for that grade.", "row"),
        ("Combinations", "Upper Secondary, TVET and TTC grades are also split by combination / trade. Students and "
                         "class groups keep their combination as they move up; a school's new S4 / L3 / Y1 are split "
                         "by its 2026 mix in that grade. S4 in 2026 already follows the new streams (Math and Science "
                         "Stream One / Two, Arts and Humanities, Languages), so the old S5-S6 combinations (MEG, HGL "
                         "...) leave by 2028. A breakdown only: rooms are counted per grade.", "row"),
        ("Classrooms", "Each school keeps the physical rooms each level used in 2026 (no construction assumed). A room "
                       "used by two levels counts in both, as in the 2026 analysis.", "row"),
        ("Sharing rooms between grades", "More class groups than rooms: the rooms are shared out between the level's "
                                         "grades in proportion to their class groups and the extra groups are on double "
                                         "shift. Enough rooms: every group keeps a room and spare rooms go to the grades "
                                         "whose students need more rooms than they have groups.", "row"),
        ("Measures", "Same as the 2026 analysis: Double Shift = MAX(0, class groups - rooms); Required = "
                     "CEILING(students / capacity); Gap = rooms - required; Classrooms Short = sum of deficits.", "row"),
        ("Full-day levels", "Lower and Upper Secondary, TVET and TTC study full day: no double shift. Each grade needs, "
                            "per combination, MAX(class groups, CEILING(students / capacity)) rooms; the school's rooms "
                            "are shared between grades in proportion to those needs; Required = the sum of the needs "
                            "(value from projection.py — a capacity change on Settings does not update these rows). "
                            "'Double Shift' on these rows means class groups without a room of their own.", "row"),
        ("2026", "The 2026 rows reproduce the current analysis at school level exactly (TVET without L1-L2). Grade rows "
                 "use the room sharing above in every year, so 2026 grade rows can differ slightly from the 2026 "
                 "analysis workbook, which counts a room shared by two grades in both.", "row"),
        ("", None, "gap"),
        ("Limits", None, "head"),
        ("Promotion", "Everyone is promoted each year and every N3, P6 and S3 student continues; repetition and "
                      "dropout are not modelled. P1 comes only from N3, so it drops while the small 2026 N1 moves "
                      "through pre-primary (new P1 2029 = N1 2026).", "row"),
        ("Small P6 in 2026", f"P6 ({p6 / 1000:,.0f}k) is much smaller than P5 ({p5 / 1000:,.0f}k); the large P5 enters "
                             "P6 in 2027 and S1 in 2028, which drives much of the jump in primary and lower secondary. "
                             "Worth confirming the 2026 P6 roster is complete.", "row"),
        ("Moves", "Students stay in their school inside a level and in their district between levels.", "row"),
        ("New schools", "Only schools that offered a level in 2026 receive its students.", "row"),
        ("", None, "gap"),
        ("Checks", None, "head"),
    ]
    r = 3
    for lbl, text, kind in lines:
        if kind == "head":
            ws.cell(row=r, column=1, value=lbl).font = F_SUB
        elif kind == "row":
            put(ws, r, 1, lbl, font=F_BOLD).alignment = WRAP
            put(ws, r, 2, text).alignment = WRAP
        r += 1

    for c, lbl in enumerate(["Check", "projection.py", "Workbook", "Result"], 1):
        cell = ws.cell(row=r, column=c, value=lbl)
        cell.font, cell.fill, cell.alignment = F_HEAD, FILL_HEAD, HEAD_ALIGN
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 12
    rng = lambda k: f"{q(SCHOOL)}${SCHOOL_COLS[k]}$5:${SCHOOL_COLS[k]}${s_last}"  # noqa: E731
    for level in LEVEL_LABELS:
        for year in P.YEARS:
            crit = f'{rng("year")},{year},{rng("level")},"{level}"'
            for lbl, value, formula in (
                (f"{level} students {year}", summ.loc[(level, year), "students"], f"=SUMIFS({rng('students')},{crit})"),
                (f"{level} classrooms short {year}", summ.loc[(level, year), "short"],
                 f'=-SUMIFS({rng("gap")},{crit},{rng("gap")},"<0")'),
            ):
                r += 1
                put(ws, r, 1, lbl, font=F_BOLD)
                put(ws, r, 2, int(value), NUM)
                put(ws, r, 3, formula, NUM)
                put(ws, r, 4, f'=IF(B{r}=C{r},"OK","MISMATCH")', font=F_BOLD)


# ---------------------------------------------------------------- main
def build(roster: pd.DataFrame, intake: dict, label: str, out: Path) -> None:
    pop = P.load_population()
    intake = {**pop, **intake}
    info, s, g, c = P.project(roster, intake)
    b = P.base_schools(roster)
    names = info.set_index("school_code")[["school_name", "district", "sector"]]
    lvl = {x: i for i, x in enumerate(LEVEL_LABELS)}
    grd = {x: i for i, x in enumerate(P.GRADES)}
    order = ["year", "district", "sector", "school_name", "school_code", "_l"]
    s = s.join(names, on="school_code").assign(_l=lambda d: d["level"].map(lvl))
    s = s.sort_values(order).drop(columns="_l").reset_index(drop=True)
    g = g.join(names, on="school_code").assign(_l=lambda d: d["level"].map(lvl), _g=lambda d: d["grade"].map(grd))
    g = g.sort_values([*order, "_g"]).drop(columns=["_l", "_g"]).reset_index(drop=True)
    c = c.join(names, on="school_code").assign(_l=lambda d: d["level"].map(lvl), _g=lambda d: d["grade"].map(grd))
    c = c.sort_values([*order, "_g", "combination"]).drop(columns=["_l", "_g"]).reset_index(drop=True)

    wb = Workbook()
    ws_readme = wb.active
    ws_readme.title = README
    sheets = {n: wb.create_sheet(n) for n in (SETTINGS, NATIONAL, DISTRICT, SECTOR, SCHOOL, GRADE, COMBO, TOP, ENTRANTS)}
    build_settings(sheets[SETTINGS], label)
    build_entrants(sheets[ENTRANTS], info, g, intake, pop, label)
    s_last = build_school(sheets[SCHOOL], s)
    g_last = build_grade(sheets[GRADE], g)
    c_last = build_combo(sheets[COMBO], c)
    build_national(sheets[NATIONAL], s_last, g_last, c, c_last)
    build_area(sheets[DISTRICT], s, s_last, by_sector=False)
    build_area(sheets[SECTOR], s, s_last, by_sector=True)
    build_top(sheets[TOP], s, P.YEARS[-1])
    k5, k6 = P.GRADES.index("P5"), P.GRADES.index("P6")
    build_readme(ws_readme, label, info, P.summary(s), s_last, int(b.students[:, k5].sum()), int(b.students[:, k6].sum()))

    for n in (SETTINGS, ENTRANTS):
        sheets[n].sheet_properties.tabColor = "FFC000"
    for n in (NATIONAL, DISTRICT, SECTOR, TOP):
        sheets[n].sheet_properties.tabColor = "1F3864"
    wb.calculation.fullCalcOnLoad = True
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"Saved {out}  (school-level-year rows {len(s):,}, grade rows {len(g):,})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--intake", type=Path,
                        help="CSV of new N1 per district (columns pop3_YYYY); default: the catchment totals")
    args = parser.parse_args()
    roster = A.load_roster()
    if args.intake:
        intake = P.load_intake_csv(args.intake)
        if not intake:
            raise SystemExit(f"{args.intake.name}: no pop3_YYYY columns found.")
        known = set(P.load_population()["N1"].index)
        unknown = sorted(set().union(*(t.index for t in intake.values())) - known)
        if unknown:
            print(f"Warning: unknown districts are ignored: {', '.join(unknown)}")
        build(roster, intake, f"Custom plan ({args.intake.name}: {', '.join(intake)})",
              OUT_DIR / f"Classroom_Projection_2026_2030_{args.intake.stem}.xlsx")
        return
    build(roster, {}, P.DEFAULT_LABEL, OUT_DIR / f"Classroom_Projection_2026_2030_{P.DEFAULT_LABEL}.xlsx")


if __name__ == "__main__":
    main()

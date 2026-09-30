"""
Build output/School_Classroom_Analysis_2026.xlsx from the classroom roster.

Counted inputs (students, class groups, double-shift sessions) are written as
values; every derived column and every summary is an Excel formula, so editing
a capacity on the Settings sheet recalculates the whole workbook.

Run:  python scripts/build_workbook.py
"""
from __future__ import annotations

from datetime import date

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import analysis as A

OUT = A.ROOT / "output" / "School_Classroom_Analysis_2026.xlsx"

# Sheet names
README, SETTINGS, NATIONAL, DISTRICT, SECTOR = "Read Me", "Settings", "National Summary", "District Summary", "Sector Summary"
SCHOOL, GRADE, TOP, QUALITY = "School-Level Summary", "Per-Grade Breakdown", "Top Deficits", "Data Quality"

# ---------------------------------------------------------------- styles
FONT = "Arial"
F_BODY = Font(name=FONT, size=10)
F_BOLD = Font(name=FONT, size=10, bold=True)
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_TITLE = Font(name=FONT, size=14, bold=True, color="1F3864")
F_SUB = Font(name=FONT, size=11, bold=True, color="1F3864")
F_NOTE = Font(name=FONT, size=9, italic=True, color="595959")
F_INPUT = Font(name=FONT, size=10, color="0000FF")
F_LINK = Font(name=FONT, size=10, color="008000")
FILL_HEAD = PatternFill("solid", fgColor="1F3864")
FILL_INPUT = PatternFill("solid", fgColor="FFFF00")
FILL_TOTAL = PatternFill("solid", fgColor="D9E1F2")
FILL_BAD = PatternFill("solid", fgColor="F8CBAD")
FILL_GOOD = PatternFill("solid", fgColor="C6EFCE")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
HEAD_ALIGN = Alignment(wrap_text=True, vertical="center", horizontal="center")

NUM = "#,##0;-#,##0;0"
GAP = "+#,##0;-#,##0;0"
PCT = "0.0%"
DEC = "0.0"

RED_TEXT = Font(name=FONT, size=10, color="9C0006")
GREEN_TEXT = Font(name=FONT, size=10, color="006100")


def q(sheet: str) -> str:
    """Quoted sheet reference prefix."""
    return f"'{sheet}'!"


# Header sizing: bold Arial 10 is wider than Excel's width unit, and Excel / Google Sheets draw
# a filter button inside each header cell, so leave room for it.
HEAD_CHAR = 1.2   # width units per bold character
FILTER_PAD = 4.5  # width units taken by the filter button and cell padding
LINE_PT = 13      # points per wrapped header line


def _head_lines(label: str, width: float) -> int:
    """Number of lines `label` wraps to (word wrap only) in a column of `width`."""
    usable = (width - FILTER_PAD) / HEAD_CHAR
    lines, used = 1, 0
    for word in label.split():
        if used and used + 1 + len(word) > usable:
            lines, used = lines + 1, len(word)
        else:
            used += (1 if used else 0) + len(word)
    return lines


def header(ws: Worksheet, row: int, labels: list[str], widths: list[float] | None = None, height: float = 30) -> None:
    """Header row. Columns are widened so no word is split, and the row is made tall enough for the
    longest wrapped label (`height` is a minimum)."""
    lines = 1
    for c, label in enumerate(labels, 1):
        cell = ws.cell(row=row, column=c, value=label)
        cell.font, cell.fill, cell.alignment, cell.border = F_HEAD, FILL_HEAD, HEAD_ALIGN, BOX
        dim = ws.column_dimensions[get_column_letter(c)]
        width = widths[c - 1] if widths and c <= len(widths) else (dim.width or 13)
        width = max(width, max(len(w) for w in label.split()) * HEAD_CHAR + FILTER_PAD)
        if widths or width > (dim.width or 13):
            dim.width = width
        lines = max(lines, _head_lines(label, width))
    ws.row_dimensions[row].height = max(height, lines * LINE_PT + 10)


def put(ws: Worksheet, row: int, col: int, value, fmt: str | None = None, font: Font = F_BODY):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = font
    if fmt:
        cell.number_format = fmt
    return cell


def gap_colours(ws: Worksheet, rng: str) -> None:
    ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"], fill=FILL_BAD, font=RED_TEXT))
    ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_GOOD, font=GREEN_TEXT))


def status_colours(ws: Worksheet, rng: str, first: str) -> None:
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'{first}="Deficit"'], font=RED_TEXT))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'{first}="Surplus"'], font=GREEN_TEXT))


def title(ws: Worksheet, text: str, sub: str | None = None) -> None:
    ws["A1"] = text
    ws["A1"].font = F_TITLE
    if sub:
        ws["A2"] = sub
        ws["A2"].font = F_NOTE
    ws.sheet_view.showGridLines = False


# ---------------------------------------------------------------- settings
SET_FIRST, SET_LAST = 5, 4 + len(A.LEVELS)
CAP_LOOKUP = (
    f"INDEX({SETTINGS}!$C${SET_FIRST}:$C${SET_LAST},"
    f"MATCH({{lvl}},{SETTINGS}!$A${SET_FIRST}:$A${SET_LAST},0))"
)


def build_settings(ws: Worksheet) -> None:
    title(ws, "Settings", "Blue values on yellow are inputs. Change a capacity and every sheet recalculates when the workbook is opened.")
    header(ws, 4, ["Level", "Grades", "Standard Classroom Capacity", "Source"], [20, 22, 16, 70])
    for i, (_, label, grades, cap) in enumerate(A.LEVELS):
        r = SET_FIRST + i
        put(ws, r, 1, label, font=F_BOLD)
        put(ws, r, 2, ", ".join(grades))
        c = put(ws, r, 3, cap, NUM, F_INPUT)
        c.fill = FILL_INPUT
        src = ("Data Transformation Brief, section 4: fixed at 45 students per classroom."
               if label == "Primary" else
               "Brief sets 45 for primary; the client confirmed the same 45 applies to this level.")
        put(ws, r, 4, src).alignment = WRAP
        for col in range(1, 5):
            ws.cell(row=r, column=col).border = BOX
    ws.freeze_panes = "A5"


# ---------------------------------------------------------------- detail tables
def build_grade(ws: Worksheet, g) -> int:
    title(ws, "Per-Grade Breakdown", "One row per school x grade (brief section 3a). Grey columns are counted from the roster; the rest are formulas.")
    cols = ["School Code", "School Name", "District", "Sector", "Level", "Grade", "Total Students", "Total Classrooms",
            "Total Classrooms in Double Shift", "Total Classrooms Available", "Standard Classroom Capacity",
            "Required Classrooms", "Gap (Deficit vs Surplus)", "Status"]
    header(ws, 4, cols, [11, 38, 13, 15, 16, 7, 11, 12, 13, 13, 12, 12, 13, 11])
    ws["H4"].comment = Comment("Number of class groups (one roster row = one class group).", "Analysis")
    ws["I4"].comment = Comment("Extra sessions held in shared rooms: class groups minus distinct physical rooms "
                               "(room ID test_code) within this grade.", "Analysis")
    ws["J4"].comment = Comment("= Total Classrooms - Double Shift = distinct physical rooms.", "Analysis")
    r0 = 5
    for i, row in enumerate(g.itertuples(index=False)):
        r = r0 + i
        put(ws, r, 1, int(row.school_code))
        put(ws, r, 2, row.school_name)
        put(ws, r, 3, row.district)
        put(ws, r, 4, row.sector)
        put(ws, r, 5, row.level)
        put(ws, r, 6, row.grade)
        put(ws, r, 7, int(row.total_students), NUM)
        put(ws, r, 8, int(row.total_classrooms), NUM)
        put(ws, r, 9, int(row.double_shift), NUM)
        put(ws, r, 10, f"=H{r}-I{r}", NUM)
        put(ws, r, 11, "=" + CAP_LOOKUP.format(lvl=f"E{r}"), NUM)
        put(ws, r, 12, int(row.required) if row.level in A.FULL_DAY else f"=ROUNDUP(G{r}/K{r},0)", NUM)
        put(ws, r, 13, f"=J{r}-L{r}", GAP)
        put(ws, r, 14, f'=IF(M{r}<0,"Deficit",IF(M{r}=0,"Exact fit","Surplus"))')
    last = r0 + len(g) - 1
    gap_colours(ws, f"M{r0}:M{last}")
    status_colours(ws, f"N{r0}:N{last}", f"$N{r0}")
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:N{last}"
    return last


def build_school(ws: Worksheet, s) -> int:
    title(ws, "School-Level Summary", "One row per school x level, all grades of the level rolled up (brief section 3b).")
    cols = ["School Code", "School Name", "District", "Sector", "Level", "Total Students", "Total Classrooms",
            "Total Classrooms in Double Shift", "Total Classrooms Available", "Standard Classroom Capacity",
            "Required Classrooms", "Gap (Deficit vs Surplus)", "Status"]
    header(ws, 4, cols, [11, 38, 13, 15, 16, 11, 12, 13, 13, 12, 12, 13, 11])
    ws["H4"].comment = Comment("Class groups minus distinct physical rooms across all grades of the level. A room shared "
                               "by two grades counts once here, so this can exceed the sum of the grade rows.", "Analysis")
    ws["K4"].comment = Comment("CEILING(Total Students / capacity) on the school total, so it can be lower than the "
                               "sum of the per-grade values. Secondary, TVET and Professional Education (full day): value = SUM over grade x "
                               "combination of MAX(class groups, CEILING(students / capacity)) — see Read Me.", "Analysis")
    r0 = 5
    for i, row in enumerate(s.itertuples(index=False)):
        r = r0 + i
        put(ws, r, 1, int(row.school_code))
        put(ws, r, 2, row.school_name)
        put(ws, r, 3, row.district)
        put(ws, r, 4, row.sector)
        put(ws, r, 5, row.level)
        put(ws, r, 6, int(row.total_students), NUM)
        put(ws, r, 7, int(row.total_classrooms), NUM)
        put(ws, r, 8, int(row.double_shift), NUM)
        put(ws, r, 9, f"=G{r}-H{r}", NUM)
        put(ws, r, 10, "=" + CAP_LOOKUP.format(lvl=f"E{r}"), NUM)
        put(ws, r, 11, int(row.required) if row.level in A.FULL_DAY else f"=ROUNDUP(F{r}/J{r},0)", NUM)
        put(ws, r, 12, f"=I{r}-K{r}", GAP)
        put(ws, r, 13, f'=IF(L{r}<0,"Deficit",IF(L{r}=0,"Exact fit","Surplus"))')
    last = r0 + len(s) - 1
    gap_colours(ws, f"L{r0}:L{last}")
    status_colours(ws, f"M{r0}:M{last}", f"$M{r0}")
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:M{last}"
    return last


# ---------------------------------------------------------------- summaries
SUMMARY_METRICS = ["Schools", "Total Students", "Total Classrooms", "Total Classrooms in Double Shift",
                   "Total Classrooms Available", "Required Classrooms", "Net Gap", "Classrooms Short (deficit schools)",
                   "Schools in Deficit", "% Schools in Deficit", "Double-Shift Share", "Students per Available Classroom"]
METRIC_WIDTHS = [9, 12, 12, 13, 13, 12, 11, 14, 11, 11, 11, 13]
METRIC_FMTS = [NUM, NUM, NUM, NUM, NUM, NUM, GAP, NUM, NUM, PCT, PCT, DEC]


def metric_formulas(r: int, c0: int, src: str, cols: dict[str, str], crit: str, last: int) -> list[str]:
    """Formulas for the 12 summary metrics. `crit` is the SUMIFS criteria pairs string;
    `cols` maps metric -> source column letter on `src`; c0 is the first metric column."""
    L = lambda k: get_column_letter(c0 + k)  # noqa: E731
    rng = lambda col: f"{q(src)}${col}$5:${col}${last}"  # noqa: E731
    gap = rng(cols["gap"])
    return [
        f"=COUNTIFS({crit})",
        f"=SUMIFS({rng(cols['students'])},{crit})",
        f"=SUMIFS({rng(cols['total'])},{crit})",
        f"=SUMIFS({rng(cols['double'])},{crit})",
        f"=SUMIFS({rng(cols['available'])},{crit})",
        f"=SUMIFS({rng(cols['required'])},{crit})",
        f"={L(4)}{r}-{L(5)}{r}",
        f'=-SUMIFS({gap},{crit},{gap},"<0")',
        f'=COUNTIFS({crit},{gap},"<0")',
        f"=IF({L(0)}{r}=0,0,{L(8)}{r}/{L(0)}{r})",
        f"=IF({L(2)}{r}=0,0,{L(3)}{r}/{L(2)}{r})",
        f"=IF({L(4)}{r}=0,0,{L(1)}{r}/{L(4)}{r})",
    ]


SCHOOL_COLS = {"district": "C", "sector": "D", "level": "E", "students": "F", "total": "G", "double": "H",
               "available": "I", "required": "K", "gap": "L"}
GRADE_COLS = {"district": "C", "sector": "D", "level": "E", "grade": "F", "students": "G", "total": "H", "double": "I",
              "available": "J", "required": "L", "gap": "M"}


def write_metrics(ws, r, c0, formulas, font=F_BODY):
    for k, (f, fmt) in enumerate(zip(formulas, METRIC_FMTS)):
        put(ws, r, c0 + k, f, fmt, font)


def build_national(ws: Worksheet, s, g, s_last: int, g_last: int) -> None:
    title(ws, "National Summary", "All figures are formulas over the School-Level Summary and Per-Grade Breakdown sheets.")
    ws["A3"] = ("Net Gap nets surpluses against deficits; Classrooms Short adds up only the shortages of schools in deficit, "
                "because a spare room in one school cannot seat pupils from another.")
    ws["A3"].font = F_NOTE

    # --- by level
    r = 5
    ws.cell(row=r, column=1, value="By level").font = F_SUB
    header(ws, r + 1, ["Level", *SUMMARY_METRICS], [18, *METRIC_WIDTHS])
    first = r + 2
    for i, level in enumerate(A.LEVEL_ORDER):
        rr = first + i
        put(ws, rr, 1, level, font=F_BOLD)
        crit = f'{q(SCHOOL)}$E$5:$E${s_last},$A{rr}'
        write_metrics(ws, rr, 2, metric_formulas(rr, 2, SCHOOL, SCHOOL_COLS, crit, s_last))
    tot = first + len(A.LEVEL_ORDER)
    put(ws, tot, 1, "All levels", font=F_BOLD)
    for k in range(12):
        col = get_column_letter(2 + k)
        if k in (9, 10, 11):  # ratios recomputed from totals
            f = [f"=IF(B{tot}=0,0,J{tot}/B{tot})", f"=IF(D{tot}=0,0,E{tot}/D{tot})", f"=IF(F{tot}=0,0,C{tot}/F{tot})"][k - 9]
        else:
            f = f"=SUM({col}{first}:{col}{tot - 1})"
        put(ws, tot, 2 + k, f, METRIC_FMTS[k], F_BOLD)
    for c in range(1, 14):
        ws.cell(row=tot, column=c).fill = FILL_TOTAL
    ws.cell(row=tot, column=2).comment = Comment("Sum of school-levels: a school with pre-primary and primary is counted once per level.", "Analysis")
    gap_colours(ws, f"H{first}:H{tot}")

    # --- by grade
    r = tot + 3
    ws.cell(row=r, column=1, value="By grade").font = F_SUB
    ws.cell(row=r + 1, column=1, value=(
        "Grade rows count rooms within each grade: a room shared by two grades is available to both, so grade totals "
        "can exceed the level totals above.")).font = F_NOTE
    header(ws, r + 2, ["Grade", *SUMMARY_METRICS])
    first = r + 3
    for i, grade in enumerate(A.GRADE_ORDER):
        rr = first + i
        put(ws, rr, 1, grade, font=F_BOLD)
        crit = f'{q(GRADE)}$F$5:$F${g_last},$A{rr}'
        write_metrics(ws, rr, 2, metric_formulas(rr, 2, GRADE, GRADE_COLS, crit, g_last))
    gap_colours(ws, f"H{first}:H{first + len(A.GRADE_ORDER) - 1}")
    ws.freeze_panes = "B5"


def build_area(ws: Worksheet, s, s_last: int, by_sector: bool) -> None:
    name = "Sector" if by_sector else "District"
    title(ws, f"{name} Summary", f"One row per {name.lower()} x level. Formulas over the School-Level Summary sheet. "
                                 "Classrooms Short counts only schools in deficit.")
    keys = ["district", "sector", "level"] if by_sector else ["district", "level"]
    labels = ["District", "Sector", "Level"] if by_sector else ["District", "Level"]
    header(ws, 4, [*labels, *SUMMARY_METRICS], [14, 16, 16][: len(labels)] + METRIC_WIDTHS)
    combos = s[keys].drop_duplicates().copy()
    combos["_lvl"] = combos["level"].map({l: i for i, l in enumerate(A.LEVEL_ORDER)})
    combos = combos.sort_values(["_lvl", *keys[:-1]])
    c0 = len(labels) + 1
    for i, row in enumerate(combos.itertuples(index=False)):
        r = 5 + i
        crit_parts = []
        for j, key in enumerate(keys):
            put(ws, r, j + 1, getattr(row, key), font=F_BOLD if key == "level" else F_BODY)
            col = SCHOOL_COLS[key]
            crit_parts.append(f"{q(SCHOOL)}${col}$5:${col}${s_last},${get_column_letter(j + 1)}{r}")
        write_metrics(ws, r, c0, metric_formulas(r, c0, SCHOOL, SCHOOL_COLS, ",".join(crit_parts), s_last))
    last = 4 + len(combos)
    gap_col = get_column_letter(c0 + 6)
    gap_colours(ws, f"{gap_col}5:{gap_col}{last}")
    ws.freeze_panes = ws.cell(row=5, column=c0)
    ws.auto_filter.ref = f"A4:{get_column_letter(c0 + 11)}{last}"


def build_top(ws: Worksheet, s, per_level: int = 25) -> None:
    title(ws, "Top Deficits", f"The {per_level} schools with the largest classroom deficit in each level. "
                              "Ranking fixed when the workbook was built; values link live to the School-Level Summary.")
    cols = ["Rank", "Level", "School Code", "School Name", "District", "Sector", "Total Students",
            "Total Classrooms Available", "Required Classrooms", "Gap (Deficit vs Surplus)", "Total Classrooms in Double Shift"]
    header(ws, 4, cols, [6, 16, 11, 38, 13, 15, 11, 13, 12, 13, 13])
    src = {"level": "E", "code": "A", "name": "B", "district": "C", "sector": "D", "students": "F",
           "available": "I", "required": "K", "gap": "L", "double": "H"}
    r = 5
    s = s.reset_index(drop=True)
    for level in A.LEVEL_ORDER:
        sub = s[(s["level"] == level) & (s["gap"] < 0)].sort_values(["gap", "total_students"], ascending=[True, False]).head(per_level)
        for rank, idx in enumerate(sub.index, 1):
            sr = 5 + idx  # row on the School-Level sheet
            put(ws, r, 1, rank)
            for c, key in enumerate(["level", "code", "name", "district", "sector", "students", "available", "required", "gap", "double"], 2):
                fmt = GAP if key == "gap" else (NUM if key in ("students", "available", "required", "double") else None)
                put(ws, r, c, f"={q(SCHOOL)}{src[key]}{sr}", fmt, F_LINK)
            r += 1
    gap_colours(ws, f"J5:J{r - 1}")
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:K{r - 1}"


QUALITY_NOTES = {
    "Room shared across grades": "Expected where one room hosts groups of two grades. Counted once at school level. Confirm it is a real shared room.",
    "Class group over 90 students": "Check for data-entry errors (e.g. two groups entered as one). Inflates required classrooms if wrong.",
    "Grade / class group mismatch": "Grade column and class group label disagree (e.g. grade P1, group N3A). Correct whichever is wrong.",
    "Room shared across levels": "Room used by e.g. pre-primary and primary. Counted as available in each level.",
    "Class group of 1-2 students": "Possibly a placeholder or split entry. Verify the headcount.",
    "Room shared by 3+ class groups": "Three or more sessions in one room. Verify; each extra group counts as a double-shift session.",
    "Repeated class group name": "Same group name twice in a grade. May be a duplicate entry or a naming clash.",
    "Missing coordinates": "School will not appear on the map.",
    "Coordinates outside Rwanda": "Latitude/longitude likely swapped or mistyped. School is excluded from the map.",
    "Missing district / sector": "Reported under 'Unknown' in the district and sector summaries.",
    "Classroom ID used by several schools": "Same room ID under two school codes. Rooms are counted per school, so no effect on totals.",
    "Missing class group": "class_group is empty.",
}


def build_quality(ws: Worksheet, dq) -> None:
    title(ws, "Data Quality", "Issues found in the source roster. Rows are kept in the analysis as recorded; this list is for the data owner to review.")
    header(ws, 4, ["Issue", "Rows Flagged", "What it means / action"], [34, 12, 100], height=22)
    counts = dq["issue"].value_counts()
    n = len(counts)
    detail_head = 5 + n + 2
    d_first, d_last = detail_head + 1, detail_head + len(dq)
    for i, issue in enumerate(counts.index):
        r = 5 + i
        put(ws, r, 1, issue, font=F_BOLD)
        put(ws, r, 2, f"=COUNTIF($A${d_first}:$A${d_last},A{r})", NUM)
        put(ws, r, 3, QUALITY_NOTES.get(issue, "")).alignment = WRAP
        for c in range(1, 4):
            ws.cell(row=r, column=c).border = BOX

    ws.cell(row=detail_head - 1, column=1, value="Detail").font = F_SUB
    cols = ["Issue", "School Code", "School Name", "District", "Grade", "Class Group", "Classroom ID", "Classroom Name",
            "Number of Students", "Detail"]
    for c, label in enumerate(cols, 1):
        cell = ws.cell(row=detail_head, column=c, value=label)
        cell.font, cell.fill, cell.alignment, cell.border = F_HEAD, FILL_HEAD, HEAD_ALIGN, BOX
    for c, w in zip("DEFGHIJ", [13, 7, 14, 38, 16, 11, 60]):
        ws.column_dimensions[c].width = w
    for i, row in enumerate(dq.itertuples(index=False)):
        r = d_first + i
        vals = [row.issue, int(row.school_code), row.school_name, row.district, row.grade, row.class_group,
                row.classroom_id, row.classroom_name, int(getattr(row, "_8")), row.detail]
        for c, v in enumerate(vals, 1):
            put(ws, r, c, None if isinstance(v, float) and v != v else v, NUM if c == 9 else None)
    ws.auto_filter.ref = f"A{detail_head}:J{d_last}"
    ws.freeze_panes = "B5"


def build_readme(ws: Worksheet, roster, g_last: int, s_last: int) -> None:
    title(ws, "Classroom Sufficiency Analysis — 2026")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 110
    lines: list[tuple[str, str | None, str]] = [
        ("Purpose", "For each school and grade, is the number of classrooms enough to seat every enrolled student at the "
                    "standard capacity? Covers all levels in the roster: pre-primary, primary, lower and upper secondary, TVET and Professional Education.", "row"),
        ("Source", f"{A.SOURCE_XLSX.name} ({len(roster):,} class-group rows, {roster['school_code'].nunique():,} schools). "
                   f"Rules from Data_Transformation_Brief.docx. Built {date.today():%d %B %Y}.", "row"),
        ("", None, "gap"),
        ("Sheets", None, "head"),
        (SETTINGS, "Standard classroom capacity per level — the only input cells.", "row"),
        (NATIONAL, "Totals by level and by grade.", "row"),
        (DISTRICT, "District x level totals, deficits and double-shift share.", "row"),
        (SECTOR, "Sector x level — same measures, finer geography.", "row"),
        (SCHOOL, "Brief section 3b: one row per school x level.", "row"),
        (GRADE, "Brief section 3a: one row per school x grade.", "row"),
        (TOP, "Schools with the largest deficit in each level.", "row"),
        (QUALITY, "Issues found in the source data, with a row-level list.", "row"),
        ("", None, "gap"),
        ("Definitions", None, "head"),
        ("Total Students", "Sum of 'Number of students'.", "row"),
        ("Total Classrooms", "Number of class groups (one roster row = one class group, e.g. P1A).", "row"),
        ("Total Classrooms in Double Shift", "Class groups that share a physical room with another group (same room ID) — "
                                             "one per extra session. Example: 6 rooms, 3 of them used morning and afternoon "
                                             "-> 9 class groups, 3 double shift.", "row"),
        ("Total Classrooms Available", "Total Classrooms - Double Shift = distinct physical rooms.", "row"),
        ("Standard Classroom Capacity", "Students per classroom, from the Settings sheet (45 by default).", "row"),
        ("Required Classrooms", "CEILING(Total Students / capacity) — always rounded up.", "row"),
        ("Gap (Deficit vs Surplus)", "Available - Required. Negative = deficit (expansion needed), 0 = exact fit, positive = surplus.", "row"),
        ("", None, "gap"),
        ("Notes", None, "head"),
        ("Double shift detection", "The roster has no morning/afternoon field. A shared classroom_id is the evidence: the 10 schools "
                                   "that label groups SHIFT1/SHIFT2 always share one classroom_id, and room names such as "
                                   "'P1AB' or 'P1 A&B' show the same pattern.", "row"),
        ("Room ID (test_code)", "The source's cleaned room ID. It equals classroom_id, except that a room recorded with "
                                "3 or more class groups is treated as a data-entry error (a room holds at most a morning "
                                "and an afternoon session) and split into one room per group. The Data Quality sheet "
                                "shows the original classroom_id.", "row"),
        ("Schools covered", "Only schools located inside Rwanda (Version 2 of the roster). 291 schools with missing or "
                            "out-of-country coordinates in the first roster are not in this source.", "row"),
        ("Full-day levels", "Lower and Upper Secondary, TVET and Professional Education study full day: no double shift. Every class group "
                            "needs its own room and different combinations never share, so Required Classrooms = SUM over "
                            "grade x combination of MAX(class groups, CEILING(students / capacity)). These rows hold the "
                            "value from the script (a capacity change on Settings does not update them). Rooms are counted "
                            "as recorded, so 'Total Classrooms in Double Shift' on these rows means class groups without a "
                            "room of their own; they are also in the gap.", "row"),
        ("Grade vs school level", "Per-grade rows count rooms within the grade. School-level rows count rooms across all grades of "
                                  "the level, so a room shared by two grades counts once there, and required classrooms are "
                                  "rounded on the school total.", "row"),
        ("Capacity for other levels", "The brief sets 45 for primary; the client confirmed 45 for every level. "
                                      "It can be changed per level on the Settings sheet.", "row"),
        ("Calculation", "Formulas recalculate automatically when the file is opened in Excel.", "row"),
        ("", None, "gap"),
        ("Checks", None, "head"),
    ]
    r = 3
    for label, text, kind in lines:
        if kind == "head":
            ws.cell(row=r, column=1, value=label).font = F_SUB
        elif kind == "row":
            put(ws, r, 1, label, font=F_BOLD).alignment = WRAP
            put(ws, r, 2, text).alignment = WRAP
        r += 1

    # Reconciliation checks: roster totals (values) vs sheet totals (formulas)
    raw_students = int(roster[A.STUDENTS].sum())
    raw_groups = len(roster)
    checks = [
        ("Students in roster", raw_students, f"=SUM({q(GRADE)}G5:G{g_last})", f"=SUM({q(SCHOOL)}F5:F{s_last})"),
        ("Class groups in roster", raw_groups, f"=SUM({q(GRADE)}H5:H{g_last})", f"=SUM({q(SCHOOL)}G5:G{s_last})"),
    ]
    for c, label in enumerate(["Check", "Source roster", "Per-Grade sheet", "School-Level sheet", "Result"], 1):
        cell = ws.cell(row=r, column=c, value=label)
        cell.font, cell.fill, cell.alignment = F_HEAD, FILL_HEAD, HEAD_ALIGN
    for c in "CDE":
        ws.column_dimensions[c].width = 16
    r += 1
    for label, raw, f_grade, f_school in checks:
        put(ws, r, 1, label, font=F_BOLD)
        put(ws, r, 2, raw, NUM).comment = Comment("Counted directly from the source roster when the workbook was built.", "Analysis")
        put(ws, r, 3, f_grade, NUM)
        put(ws, r, 4, f_school, NUM)
        put(ws, r, 5, f'=IF(AND(B{r}=C{r},B{r}=D{r}),"OK","MISMATCH")', font=F_BOLD)
        r += 1


def main() -> None:
    roster = A.load_roster()
    g, s, dq = A.grade_table(roster), A.school_table(roster), A.data_quality(roster)

    wb = Workbook()
    ws_readme = wb.active
    ws_readme.title = README
    sheets = {name: wb.create_sheet(name) for name in (SETTINGS, NATIONAL, DISTRICT, SECTOR, SCHOOL, GRADE, TOP, QUALITY)}

    build_settings(sheets[SETTINGS])
    g_last = build_grade(sheets[GRADE], g)
    s_last = build_school(sheets[SCHOOL], s)
    build_national(sheets[NATIONAL], s, g, s_last, g_last)
    build_area(sheets[DISTRICT], s, s_last, by_sector=False)
    build_area(sheets[SECTOR], s, s_last, by_sector=True)
    build_top(sheets[TOP], s)
    build_quality(sheets[QUALITY], dq)
    build_readme(ws_readme, roster, g_last, s_last)

    sheets[SETTINGS].sheet_properties.tabColor = "FFC000"
    for name in (NATIONAL, DISTRICT, SECTOR, TOP):
        sheets[name].sheet_properties.tabColor = "1F3864"
    wb.calculation.fullCalcOnLoad = True

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Saved {OUT}  (grade rows {len(g):,}, school-level rows {len(s):,}, quality rows {len(dq):,})")


if __name__ == "__main__":
    main()

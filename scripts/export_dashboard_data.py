"""
Export the dashboard's static data files to dashboard/public/data/.

  school_levels.json  one record per school x level (the School-Level Summary)
  grades.json         one compact row per school x grade (the Per-Grade Breakdown)
  meta.json           levels, grades, capacity, build date, data-quality counts
  combos.json         students and class groups per school x grade x combination (Upper Secondary,
                      TVET, TTC) in 2026
  projection_base.json
                      inputs for the all-level projection, which the dashboard runs in the
                      browser (src/projection.ts, same algorithm as scripts/projection.py):
                      the projected levels and grades, how new students enter, 2026 rooms per
                      level and students / class groups per grade for each school, and the
                      children aged 3 in each pre-primary school's catchment

Run:  python scripts/export_dashboard_data.py
"""
from __future__ import annotations

import json
from datetime import date

import analysis as A
import projection as P

OUT_DIR = A.ROOT / "dashboard" / "public" / "data"


def projection_base(roster) -> dict:
    b = P.base_schools(roster)
    return {
        "baseYear": P.BASE_YEAR,
        "years": P.YEARS,
        "levels": [{"level": A.LEVEL_ORDER.index(label), "grades": grades, "capacity": P.CAPACITY[label],
                    "fullDay": label in A.FULL_DAY}
                   for label, grades in P.LEVELS],
        "grades": P.GRADES,
        "gradeIndex": [A.GRADE_ORDER.index(g) for g in P.GRADES],
        "intakes": P.INTAKES,
        "feeds": P.FEEDS,
        "schoolFeeds": P.SCHOOL_FEEDS,
        "population": {g: {d: [int(v) for v in row] for d, row in t.iterrows()} for g, t in P.load_population().items()},
        "estimated": P.ESTIMATED,
        "defaultLabel": P.DEFAULT_LABEL,
        # [code, children aged 3 in the school's catchment per year of years[1..]] (N1 schools)
        "catchment": [[int(c), *map(int, row)] for c, row in P.load_catchment().iterrows()],
        # [code, rooms per level (6), students per grade (len(grades)), class groups per grade]
        "schools": [[int(c), *map(int, r), *map(int, s), *map(int, g)]
                    for c, r, s, g in zip(b.info["school_code"], b.rooms, b.students, b.groups)],
        # combinations of each level (empty = level without combinations), most students first
        "combos": [b.combos.get(label, []) for label, _ in P.LEVELS],
        # 2026 [code, grade index into `grades`, combination index within its level, students, class groups]
        "schoolCombos": [
            [int(b.info["school_code"].iat[i]), P.GRADES.index(grades[k]), int(c),
             int(b.combo_students[label][i, k, c]), int(b.combo_groups[label][i, k, c])]
            for label, grades in P.LEVELS if label in b.combos
            for i, k, c in zip(*((b.combo_students[label] > 0) | (b.combo_groups[label] > 0)).nonzero())
        ],
    }


def combos_2026(roster) -> dict:
    """Students and class groups per school, grade and combination (levels with combinations, all grades)."""
    d = roster[roster["level"].isin(P.COMBO_LEVELS)]
    t = d.groupby(["school_code", "grade", "combination"]).agg(st=(A.STUDENTS, "sum"), g=("room_key", "size")).reset_index()
    names = sorted(t["combination"].unique())
    idx = {n: i for i, n in enumerate(names)}
    return {"names": names,
            # [school, grade index into meta.grades, combination index into names, students, class groups]
            "rows": [[int(r.school_code), A.GRADE_ORDER.index(r.grade), idx[r.combination], int(r.st), int(r.g)]
                     for r in t.itertuples(index=False)]}


def main() -> None:
    roster = A.load_roster()
    s = A.school_table(roster)
    g = A.grade_table(roster)
    dq = A.data_quality(roster)

    level_idx = {label: i for i, label in enumerate(A.LEVEL_ORDER)}
    grade_idx = {grade: i for i, grade in enumerate(A.GRADE_ORDER)}

    def coords(lat, lon):
        ok = lat == lat and lon == lon and A.RW_LAT[0] <= lat <= A.RW_LAT[1] and A.RW_LON[0] <= lon <= A.RW_LON[1]
        return (round(float(lat), 6), round(float(lon), 6)) if ok else (None, None)

    school_levels = []
    for row in s.itertuples(index=False):
        lat, lon = coords(row.latitude, row.longitude)
        school_levels.append({
            "c": int(row.school_code), "n": row.school_name, "d": row.district, "s": row.sector,
            "l": level_idx[row.level], "st": int(row.total_students), "g": int(row.total_classrooms),
            "ds": int(row.double_shift), "a": int(row.available), "r": int(row.required), "gap": int(row.gap),
            "y": lat, "x": lon,
        })

    grades = [
        [int(r.school_code), grade_idx[r.grade], int(r.total_students), int(r.total_classrooms),
         int(r.double_shift), int(r.available), int(r.required), int(r.gap)]
        for r in g.itertuples(index=False)
    ]

    school_issues: dict[str, list] = {}
    for (code, issue), n in dq.groupby(["school_code", "issue"]).size().items():
        school_issues.setdefault(str(int(code)), []).append([issue, int(n)])

    meta = {
        "built": date.today().isoformat(),
        "source": A.SOURCE_XLSX.name,
        "levels": [{"key": k, "label": label, "grades": grades_, "capacity": cap, "fullDay": label in A.FULL_DAY}
                   for k, label, grades_, cap in A.LEVELS],
        "grades": A.GRADE_ORDER,
        "gradeColumns": ["school", "grade", "students", "classGroups", "doubleShift", "available", "required", "gap"],
        "roster": {"rows": len(roster), "schools": int(roster["school_code"].nunique()),
                   "students": int(roster[A.STUDENTS].sum())},
        "issues": {k: int(v) for k, v in dq["issue"].value_counts().items()},
        "schoolIssues": school_issues,
        "unmapped": sum(1 for r in {(x["c"], x["y"]) for x in school_levels} if r[1] is None),
    }

    files = {"school_levels.json": school_levels, "grades.json": grades, "meta.json": meta,
             "combos.json": combos_2026(roster), "projection_base.json": projection_base(roster)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, obj in files.items():
        path = OUT_DIR / name
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{path.relative_to(A.ROOT)}  {path.stat().st_size / 1024:,.0f} KB")


if __name__ == "__main__":
    main()

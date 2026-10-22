import { useCallback, useEffect, useMemo, useState } from 'react';
import { ALL_LEVELS, fmt, loadDataset, type Dataset, type Meta, type SchoolLevel } from '../data';
import {
  catchmentDemand, cohortTable, comboTable, copyScenario, createScenario, defaultIntake, deleteScenario, fetchProjection, getScenario, gradeByDistrict,
  levelTotals, listScenarios, loadProjectionBase, projectionMeta, sameIntake, updateScenario, yearDataset, yearTotals,
  type Intake, type ProjectionBase, type ProjectedYear, type Scenario, type ScenarioSummary,
} from '../projection';
import type { Mode } from '../theme';
import { isAdmin, useAuth } from '../auth';
import {
  copySchoolPlan, createSchoolPlan, DEFAULT_KM, defaultClassrooms, deleteSchoolPlan, getSchoolPlan, listSchoolPlans,
  plannedInfo, saveSchools, storedSchools, updateSchoolPlan,
  type PlannedOut, type PlannedSchoolInput, type SchoolPlan, type SchoolPlanSummary,
} from '../newSchools';
import type { Filters } from '../data';
import type { MapPlanning } from './SchoolMap';
import NewSchoolForm from './NewSchoolForm';
import NewSchoolImpact from './NewSchoolImpact';
import Overview, { Card } from './Overview';
import IntakePlanner, { FedEntrants, type SchoolEntrants } from './IntakePlanner';
import SchoolPlanBar, { type SchoolPlanControls } from './SchoolPlanBar';
import { CatchmentDemandChart, CohortChart, CompareBars, YearTrend, type SchoolDemand } from './Charts';

// The plan on screen (with unsaved edits) and the saved scenario it came from, remembered in this browser.
// v4: plans are shared through the database (scenarios); the browser only remembers where you were.
// v5: one entry per base year, so a plan for 2027-2030 is not read as 2028-2031 after a new school year is published.
const STORAGE_KEY = 'classroom-dashboard-plan-v5';
let storageKey = STORAGE_KEY; // + the base year, set by storedPlan when the projection loads

interface StoredPlan {
  intake: Intake;
  scenarioId: number | null;
}

function storedPlan(base: ProjectionBase): StoredPlan | null {
  storageKey = `${STORAGE_KEY}-${base.baseYear}`;
  const n = base.years.length - 1;
  const valid = (t: unknown, g: string) =>
    !!t && Object.keys(base.population[g]).every((d) => Array.isArray((t as Record<string, number[]>)[d]) && (t as Record<string, number[]>)[d].length === n);
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      const v = JSON.parse(raw) as StoredPlan;
      if (Object.keys(base.intakes).every((g) => valid(v.intake?.[g], g))) return v;
    }
  } catch {
    /* unreadable — fall back to the default plan */
  }
  return null;
}

function savePlan(v: StoredPlan) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(v));
  } catch {
    /* storage unavailable — the plan lasts for this visit only */
  }
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Students by grade and year: each cohort moves one step down and to the right. */
function CohortTable({ years, baseYear, year, rows, entryNote }: {
  years: number[]; baseYear: number; year: number; rows: { grade: string; byYear: number[] }[]; entryNote: string;
}) {
  return (
    <div className="overflow-x-auto px-4 pb-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            <th className="px-2 py-1.5 text-left font-medium">Grade</th>
            {years.map((y) => (
              <th key={y} className={`px-2 py-1.5 text-right font-medium ${y === year ? 'text-ink' : ''}`}>
                {y}{y === baseYear ? '*' : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, gi) => (
            <tr key={r.grade} className="border-b border-line">
              <td className="px-2 py-1.5 text-ink">{r.grade}</td>
              {r.byYear.map((v, yi) => (
                <td key={yi}
                  className={`num px-2 py-1.5 text-right ${years[yi] === year ? 'bg-[var(--line)] font-semibold text-ink' : 'text-ink2'} ${
                    gi === yi ? 'underline decoration-accent decoration-2 underline-offset-4' : ''}`}>
                  {fmt(v)}
                </td>
              ))}
            </tr>
          ))}
          <tr className="text-ink">
            <td className="px-2 py-1.5 font-semibold">Total</td>
            {years.map((y, yi) => (
              <td key={y} className="num px-2 py-1.5 text-right font-semibold">
                {fmt(rows.reduce((s, r) => s + r.byYear[yi], 0))}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">
        * actual. Underlined: the {baseYear} {rows[0]?.grade} cohort moving up a grade each year. Each year the last grade
        leaves the level and {entryNote}.
      </p>
    </div>
  );
}

/** Students per combination (rows) and year (columns); rows sorted by the selected year. */
function CombinationTable({ years, baseYear, year, rows }: {
  years: number[]; baseYear: number; year: number;
  rows: { combination: string; students: number[]; groups: number[] }[];
}) {
  const yi = Math.max(years.indexOf(year), 0);
  const sorted = [...rows].sort((a, b) => b.students[yi] - a.students[yi] || b.students[0] - a.students[0]);
  return (
    <div className="px-4 pb-4">
      <div className="print-expand max-h-[420px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-line text-xs text-muted">
              <th className="px-2 py-1.5 text-left font-medium">Combination</th>
              {years.map((y) => (
                <th key={y} className={`px-2 py-1.5 text-right font-medium ${y === year ? 'text-ink' : ''}`}>
                  {y}{y === baseYear ? '*' : ''}
                </th>
              ))}
              <th className="px-2 py-1.5 text-right font-medium">Class streams {year}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.combination} className="border-b border-line">
                <td className="px-2 py-1.5 text-ink">{r.combination}</td>
                {r.students.map((v, k) => (
                  <td key={k} className={`num px-2 py-1.5 text-right ${k === yi ? 'bg-[var(--line)] font-semibold text-ink' : 'text-ink2'}`}>
                    {fmt(v)}
                  </td>
                ))}
                <td className="num px-2 py-1.5 text-right text-ink2">{fmt(r.groups[yi])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">
        * actual. Students keep their combination as they move up; each school's new entrants are split by its {baseYear} mix
        in the entry grade. A breakdown of the grade totals — rooms are counted per grade, not per combination.
      </p>
    </div>
  );
}

const TOP_CATCHMENTS = 50; // schools in the catchment demand chart

/** Pre-primary: children aged 3 in each school's catchment area (the demand for N1) against its N1 today. */
function CatchmentDemandCard({ base, result, meta, year, codes, info, mode, onPick }: {
  base: ProjectionBase; result: ProjectedYear[]; meta: Meta; year: number; codes: Set<number>;
  info: Map<number, SchoolLevel>; mode: Mode; onPick: (code: string) => void;
}) {
  const { year: used, rows } = useMemo(() => catchmentDemand(base, result, meta, year, codes), [base, result, meta, year, codes]);
  const data: SchoolDemand[] = useMemo(
    () => [...rows].sort((a, b) => b.demand - a.demand).slice(0, TOP_CATCHMENTS).map((d) => {
      const s = info.get(d.code);
      return { ...d, name: s?.n ?? String(d.code), sub: s ? `${s.d} · ${s.s} · code ${d.code}` : `code ${d.code}` };
    }),
    [rows, info],
  );
  const total = rows.reduce((s, d) => s + d.demand, 0);
  const enrolled = rows.reduce((s, d) => s + d.enrolled, 0);
  const capacity = base.levels.find((l) => l.grades.includes('N1'))?.capacity ?? 45;
  const notes = [
    year !== used ? `${year} has no catchment figures: showing ${used}` : '',
    base.estimated.N1?.includes(used) ? `${used} repeats 2029 in the catchment file` : '',
  ].filter(Boolean).join(' · ');

  return (
    <Card title={`Demand per school from its catchment area, ${used}`}
      sub={`Children aged 3 living in each pre-primary school's catchment area (NISR population shared to schools by GIS) against its N1 students in ${base.baseYear}. ${fmt(rows.length)} schools in scope: ${fmt(total)} children aged 3, ${fmt(enrolled)} in N1 in ${base.baseYear}.${notes ? ` ${notes}.` : ''} Largest first; click a bar for the school's details.`}>
      <div className="print-expand max-h-[480px] overflow-y-auto px-2 pb-2">
        {data.length ? (
          <CatchmentDemandChart data={data} year={used} baseYear={base.baseYear} capacity={capacity} mode={mode} onPick={onPick} />
        ) : (
          <p className="px-2 py-6 text-sm text-muted">No pre-primary school with a catchment figure in this area.</p>
        )}
      </div>
      <p className="px-4 pb-3 text-xs text-muted">
        {data.length < rows.length ? `The ${data.length} largest catchments of ${fmt(rows.length)}. ` : ''}
        The default intake plan brings exactly these children into N1; an edited plan scales each district's schools in proportion.
      </p>
    </Card>
  );
}

export default function ProjectionPage({ current, mode }: { current: Dataset; mode: Mode }) {
  const { user } = useAuth();
  const [base, setBase] = useState<ProjectionBase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [intake, setIntake] = useState<Intake | null>(null);
  const [picked, setYear] = useState<number | null>(null); // null = the base year (the newest actual school year)
  const [plannerOpen, setPlannerOpen] = useState(true);
  // Saved scenarios (database) and the one on screen
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [active, setActive] = useState<Scenario | null>(null);
  const [archived, setArchived] = useState<ScenarioSummary | null>(null); // an older plan picked: shown, not loaded
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioMessage, setScenarioMessage] = useState<string | null>(null);
  // Planned new schools (separate from the intake plan) and the saved plan of new schools they came from
  const [schools, setSchools] = useState<PlannedSchoolInput[]>([]);
  const [schoolsOn, setSchoolsOn] = useState(true);
  const [schoolPlan, setSchoolPlan] = useState<SchoolPlan | null>(null);
  const [schoolPlans, setSchoolPlans] = useState<SchoolPlanSummary[]>([]);
  const [archivedSchools, setArchivedSchools] = useState<SchoolPlanSummary | null>(null);
  const [schoolBusy, setSchoolBusy] = useState(false);
  const [schoolMessage, setSchoolMessage] = useState<string | null>(null);
  // Placing a school on the map, and the one in the form (index into `schools`, null = a new one)
  const [placing, setPlacing] = useState(false);
  const [editing, setEditing] = useState<{ index: number | null; school: PlannedSchoolInput } | null>(null);
  const [draftKm, setDraftKm] = useState(2);
  const [formError, setFormError] = useState<string | null>(null);
  const [formBusy, setFormBusy] = useState(false);

  const refreshScenarios = useCallback(() => {
    listScenarios().then(setScenarios).catch(() => undefined); // the plan still works without the list
  }, []);
  const refreshSchoolPlans = useCallback(() => {
    listSchoolPlans().then(setSchoolPlans).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadProjectionBase()
      .then((b) => {
        setBase(b);
        const stored = storedPlan(b);
        setIntake(stored?.intake ?? defaultIntake(b));
        if (stored?.scenarioId != null) {
          getScenario(stored.scenarioId).then((s) => (s.archived ? undefined : setActive(s))).catch(() => undefined);
        }
        const kept = storedSchools(b.baseYear);
        if (kept) {
          setSchools(kept.schools);
          setSchoolsOn(kept.on);
          if (kept.planId != null) {
            getSchoolPlan(kept.planId).then((p) => (p.archived ? undefined : setSchoolPlan(p))).catch(() => undefined);
          }
        }
      })
      .catch((e: unknown) => setError(message(e)));
    refreshScenarios();
    refreshSchoolPlans();
  }, [refreshScenarios, refreshSchoolPlans]);

  // Remember the planned schools on screen in this browser (per base year)
  useEffect(() => {
    if (base) saveSchools(base.baseYear, { planId: schoolPlan?.id ?? null, on: schoolsOn, schools });
  }, [base, schools, schoolsOn, schoolPlan]);

  const changeIntake = useCallback((next: Intake) => {
    setIntake(next);
    setActive((a) => {
      savePlan({ intake: next, scenarioId: a?.id ?? null });
      return a;
    });
  }, []);

  const runScenario = useCallback(async (work: () => Promise<void>) => {
    setScenarioBusy(true);
    setScenarioMessage(null);
    try {
      await work();
    } catch (e) {
      setScenarioMessage(message(e));
    } finally {
      setScenarioBusy(false);
    }
  }, []);
  const scenarioControls = base && intake ? {
    list: scenarios,
    active,
    dirty: !!active && !sameIntake(intake, active.intake),
    busy: scenarioBusy,
    message: scenarioMessage,
    defaultLabel: base.defaultLabel,
    canEdit: isAdmin(user),
    archived,
    onCopy: (name: string) => runScenario(async () => {
      if (!archived) return;
      const s = await copyScenario(archived.id, name);
      setArchived(null);
      setActive(s);
      setIntake(s.intake);
      savePlan({ intake: s.intake, scenarioId: s.id });
      setScenarioMessage(`Copied to "${s.name}" for ${base.years[1]}–${base.years[base.years.length - 1]}.`);
      refreshScenarios();
    }),
    onOpen: (id: number | null) => runScenario(async () => {
      const pick = id === null ? null : scenarios.find((x) => x.id === id) ?? null;
      if (pick?.archived) {
        setArchived(pick); // older years: not loaded into the planner
        return;
      }
      setArchived(null);
      const s = id === null ? null : await getScenario(id);
      const next = s ? s.intake : defaultIntake(base);
      setActive(s);
      setIntake(next);
      savePlan({ intake: next, scenarioId: s?.id ?? null });
    }),
    onSave: () => runScenario(async () => {
      if (!active) return;
      const s = await updateScenario(active.id, active.name, intake, active.description);
      setActive(s);
      savePlan({ intake, scenarioId: s.id });
      setScenarioMessage(`Saved "${s.name}".`);
      refreshScenarios();
    }),
    onSaveAs: (name: string) => runScenario(async () => {
      const s = await createScenario(name, intake);
      setActive(s);
      savePlan({ intake, scenarioId: s.id });
      setScenarioMessage(`Saved as "${s.name}" — everyone using the dashboard can open it.`);
      refreshScenarios();
    }),
    onDelete: () => runScenario(async () => {
      if (!active || !window.confirm(`Delete the saved plan "${active.name}" for everyone?`)) return;
      await deleteScenario(active.id);
      setScenarioMessage(`Deleted "${active.name}". The plan stays on screen as an unsaved plan.`);
      setActive(null);
      savePlan({ intake, scenarioId: null });
      refreshScenarios();
    }),
  } : null;

  // Name, district, sector and coordinates of every school (from any of its 2026 rows)
  const info = useMemo(() => {
    const m = new Map<number, SchoolLevel>();
    for (const r of current.schools) if (!m.has(r.c)) m.set(r.c, r);
    return m;
  }, [current]);
  // Earlier actual school years (the projection starts from the newest, `current`)
  const pastYears = useMemo(() => current.meta.actualYears.filter((y) => y < current.meta.baseYear), [current]);
  const [history, setHistory] = useState<Map<number, Dataset>>(new Map());
  useEffect(() => {
    if (!pastYears.length) return;
    let cancelled = false;
    Promise.all(pastYears.map((y) => loadDataset(y).then((d) => [y, d] as const)))
      .then((pairs) => !cancelled && setHistory(new Map(pairs)))
      .catch(() => undefined); // the projection still works without the past years
    return () => {
      cancelled = true;
    };
  }, [pastYears]);
  // The projection runs on the server; the previous result stays on screen while a new plan is calculated. With
  // planned new schools on, the run without them (`before`) is kept too, for the before -> after figures.
  const [result, setResult] = useState<ProjectedYear[] | null>(null);
  const [planned, setPlanned] = useState<PlannedOut[]>([]);
  const [before, setBefore] = useState<ProjectedYear[] | null>(null);
  const [computing, setComputing] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const activeSchools = useMemo(() => (schoolsOn ? schools : []), [schoolsOn, schools]);
  useEffect(() => {
    if (!base || !intake) return;
    let cancelled = false;
    setComputing(true);
    Promise.all([
      fetchProjection(base, intake, info, activeSchools),
      activeSchools.length ? fetchProjection(base, intake, info) : Promise.resolve(null),
    ])
      .then(([r, without]) => {
        if (cancelled) return;
        setResult(r.years);
        setPlanned(r.planned);
        setBefore(without?.years ?? null);
        setRunError(null);
      })
      .catch((e: unknown) => !cancelled && setRunError(message(e)))
      .finally(() => !cancelled && setComputing(false));
    return () => {
      cancelled = true;
    };
  }, [base, intake, info, activeSchools]);
  // The school lookup with the planned schools of the run
  const infoAll = useMemo(
    () => (planned.length ? new Map([...info, ...planned.map((p) => [p.c, plannedInfo(p)] as const)]) : info),
    [info, planned],
  );

  const startEdit = (i: number) => {
    const s = schools[i];
    if (!s) return;
    setPlacing(false);
    setFormError(null);
    setDraftKm(s.walking_km);
    setEditing({ index: i, school: s });
  };
  // The school of the form is checked by a run with it (the API refuses a point outside Rwanda's sectors ...) before
  // it joins the planned schools
  const submitSchool = async (s: PlannedSchoolInput) => {
    if (!base || !intake || !editing) return;
    const list = editing.index === null ? [...schools, s] : schools.map((x, k) => (k === editing.index ? s : x));
    setFormBusy(true);
    setFormError(null);
    try {
      await fetchProjection(base, intake, info, list);
      setSchools(list);
      setSchoolsOn(true);
      setEditing(null);
    } catch (e) {
      setFormError(message(e));
    } finally {
      setFormBusy(false);
    }
  };
  const planning = (filters: Filters): MapPlanning | undefined => {
    if (!base) return undefined;
    // All levels: a new school is a Primary school until the form says otherwise
    const li = filters.level === ALL_LEVELS ? current.meta.levels.findIndex((l) => l.key === 'PRI') : filters.level;
    const key = current.meta.levels[li]?.key ?? 'PRI';
    return {
      planned,
      dimmed: !schoolsOn,
      placing,
      draft: editing ? { latitude: editing.school.latitude, longitude: editing.school.longitude, km: draftKm } : null,
      form: editing ? (
        <NewSchoolForm key={`${editing.index}-${editing.school.latitude}-${editing.school.longitude}`} base={base}
          meta={current.meta} initial={editing.school} editing={editing.index !== null} error={formError} busy={formBusy}
          onKm={setDraftKm} onSubmit={(s) => void submitSchool(s)} onCancel={() => setEditing(null)} />
      ) : null,
      onPlacing: (on) => {
        setPlacing(on);
        if (on) setEditing(null);
      },
      onPlace: (latitude, longitude) => {
        const km = DEFAULT_KM[key] ?? 2;
        setPlacing(false);
        setFormError(null);
        setDraftKm(km);
        setEditing({
          index: null,
          school: {
            name: `New school ${schools.length + 1}`, latitude, longitude,
            levels: { [key]: defaultClassrooms(base, li) }, opening_year: base.years[1], walking_km: km,
          },
        });
      },
      // The pins come from the last run: while a new one is calculated their codes may not match the list any more
      onPick: (code) => !computing && startEdit(-code - 1),
    };
  };

  const runSchoolPlan = useCallback(async (work: () => Promise<void>) => {
    setSchoolBusy(true);
    setSchoolMessage(null);
    try {
      await work();
    } catch (e) {
      setSchoolMessage(message(e));
    } finally {
      setSchoolBusy(false);
    }
  }, []);
  const schoolControls: SchoolPlanControls | null = base && intake ? {
    plans: schoolPlans,
    active: schoolPlan,
    archived: archivedSchools,
    on: schoolsOn,
    schools,
    dirty: !!schoolPlan && JSON.stringify(schools) !== JSON.stringify(schoolPlan.plan_schools),
    canEdit: isAdmin(user),
    busy: schoolBusy,
    message: schoolMessage,
    onOpen: (id) => runSchoolPlan(async () => {
      const pick = id === null ? null : schoolPlans.find((p) => p.id === id) ?? null;
      if (pick?.archived) {
        setArchivedSchools(pick); // older years: shown, not loaded
        return;
      }
      setArchivedSchools(null);
      const p = id === null ? null : await getSchoolPlan(id);
      setSchoolPlan(p);
      setSchools(p ? p.plan_schools : []);
      setSchoolsOn(true);
    }),
    onToggle: setSchoolsOn,
    onEdit: (i) => startEdit(i),
    onRemove: (i) => {
      setEditing(null); // its index into the list would no longer be right
      setSchools((list) => list.filter((_, k) => k !== i));
    },
    onSave: () => runSchoolPlan(async () => {
      if (!schoolPlan) return;
      const p = await updateSchoolPlan(schoolPlan.id, schoolPlan.name, schools, intake, schoolPlan.description);
      setSchoolPlan(p);
      setSchools(p.plan_schools);
      setSchoolMessage(`Saved "${p.name}".`);
      refreshSchoolPlans();
    }),
    onSaveAs: (name) => runSchoolPlan(async () => {
      const p = await createSchoolPlan(name, schools, intake);
      setSchoolPlan(p);
      setSchools(p.plan_schools);
      setSchoolMessage(`Saved as "${p.name}" — everyone using the dashboard can open it.`);
      refreshSchoolPlans();
    }),
    onDelete: () => runSchoolPlan(async () => {
      if (!schoolPlan || !window.confirm(`Delete the plan of new schools "${schoolPlan.name}" for everyone?`)) return;
      await deleteSchoolPlan(schoolPlan.id);
      setSchoolMessage(`Deleted "${schoolPlan.name}". Its schools stay on screen, unsaved.`);
      setSchoolPlan(null);
      refreshSchoolPlans();
    }),
    onCopy: (name) => runSchoolPlan(async () => {
      if (!archivedSchools) return;
      const p = await copySchoolPlan(archivedSchools.id, name);
      setArchivedSchools(null);
      setSchoolPlan(p);
      setSchools(p.plan_schools);
      setSchoolsOn(true);
      setSchoolMessage(`Copied to "${p.name}".`);
      refreshSchoolPlans();
    }),
  } : null;
  const meta = useMemo(() => (base ? projectionMeta(base, current.meta) : current.meta), [base, current]);
  // Students per district and year for every entry grade
  const entryByDistrict = useMemo(() => {
    if (!base || !result) return {};
    return Object.fromEntries(base.levels.map((l) => [l.grades[0], gradeByDistrict(result, meta, l.grades[0], infoAll)]));
  }, [base, result, meta, infoAll]);
  const presetLabel = useMemo(() => {
    if (!base || !intake) return '';
    if (active) return sameIntake(intake, active.intake) ? active.name : `${active.name} (edited)`;
    return sameIntake(intake, base.population) ? base.defaultLabel : 'Unsaved plan';
  }, [base, intake, active]);
  const pickYear = useCallback((y: string) => setYear(Number(y)), []);

  if (error) return <div className="p-8 text-sm text-ink2">Could not load the projection: {error}</div>;
  if (!result && runError) return <div className="p-8 text-sm text-ink2">Could not calculate the projection: {runError}</div>;
  if (!base || !intake || !result) {
    return <div className="grid min-h-[50vh] place-items-center text-sm text-muted">Calculating the projection…</div>;
  }

  const year = picked ?? base.baseYear;
  const past = year < base.baseYear ? history.get(year) : undefined;
  const py = result.find((r) => r.year === year) ?? result[result.length - 1];
  const isActual = year <= base.baseYear;
  const shown = past ?? yearDataset(py, meta);
  const pastTotals = (level: number, codes: Set<number>) =>
    pastYears.flatMap((y) => {
      const d = history.get(y);
      return d ? [{ year: y, ...levelTotals(d.schools, level, codes) }] : [];
    });
  const years = base.years.slice(1);
  // Where the new students of an entry grade come from: a district pool (P6 -> S1) or the same school (N3 -> P1)
  const feedOf = (grade: string) => {
    const f = base.feeds.find(([, targets]) => targets.includes(grade));
    if (f) return { source: f[0], targets: f[1], sameSchool: false };
    const sf = base.schoolFeeds.find(([, dst]) => dst === grade);
    return sf ? { source: sf[0], targets: [sf[1]], sameSchool: true } : undefined;
  };
  const entryNote = (grade: string) => {
    if (base.intakes[grade] !== undefined) return `the new ${grade} from the intake plan arrives`;
    const feed = feedOf(grade);
    return feed ? `the new ${grade} arrives from the ${feed.source} of the year before` : `no new ${grade} arrives`;
  };

  return (
    <Overview
      key="projection"
      data={shown}
      mode={mode}
      showLevels
      scopePrefix={`${year}${isActual ? ' actual' : ' projected'} · Intake: ${presetLabel}`}
      panelContext={`${isActual ? 'Actual' : 'Projected'} ${year} · Intake: ${presetLabel}`}
      notes={{
        available: isActual ? `${year} rooms` : `${base.baseYear} rooms, no new construction`,
        gradeChart: "Each grade's rooms = the school's rooms for the level shared out between its grades that year.",
      }}
      controls={
        <>
          {computing && (
            <span className="inline-flex items-center gap-1.5 text-xs text-accent" role="status">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />Recalculating…
            </span>
          )}
          {runError && !computing && <span className="text-xs text-[var(--deficit)]" role="alert">{runError}</span>}
          <span className="hidden text-xs text-muted sm:inline">Intake: {presetLabel}</span>
          <label className="flex items-center gap-2 text-sm text-ink2">
            Year
            <select aria-label="Year" value={year} className="h-8 px-2 text-sm font-medium text-ink"
              onChange={(e) => setYear(Number(e.target.value))}>
              {[...pastYears, ...base.years].map((y) => (
                <option key={y} value={y}>{y}{y <= base.baseYear ? ' (actual)' : ''}</option>
              ))}
            </select>
          </label>
        </>
      }
      planning={planning}
      afterCharts={(codes, filters, pickSchool) => {
        if (filters.level === ALL_LEVELS) return null;
        const level = base.levels.find((l) => l.level === filters.level) ?? base.levels[0];
        // Pre-primary (the level whose entry grade comes from the catchment population): demand per school
        return base.intakes[level.grades[0]] !== undefined ? (
          <CatchmentDemandCard base={base} result={result} meta={meta} year={year} codes={codes} info={infoAll}
            mode={mode} onPick={pickSchool} />
        ) : null;
      }}
      top={(codes, filters) => {
        // All levels: the intake plan (the level whose new students come from the catchment population) and every grade
        const all = filters.level === ALL_LEVELS;
        const level = (all ? base.levels.find((l) => base.intakes[l.grades[0]] !== undefined)
          : base.levels.find((l) => l.level === filters.level)) ?? base.levels[0];
        const entry = level.grades[0];
        const age = base.intakes[entry];
        const feed = feedOf(entry);
        const byDistrict = entryByDistrict[entry];
        const cohort = cohortTable(result, meta, all ? base.grades : level.grades, codes);
        const national = years.map((_, yi) => [...byDistrict.values()].reduce((s, v) => s + v[yi + 1], 0));
        const perYear = years.map((y, yi) => `${y} ${fmt(national[yi])}`).join(' · ');
        // The school picked with the search box: its own students of each entry grade per year
        const school: SchoolEntrants | undefined = filters.school === null ? undefined : {
          name: infoAll.get(filters.school)?.n ?? String(filters.school),
          byGrade: Object.fromEntries([entry, ...(feed?.targets ?? [])].map((g) => [
            g, cohortTable(result, meta, [g], new Set([filters.school!]))[0].byYear,
          ])),
        };
        const levelPlanned = planned.filter((p) => p.levels.includes(filters.level));
        const pyBefore = before?.find((r) => r.year === py.year);
        return (
          <>
            {schoolsOn && levelPlanned.length > 0 && pyBefore && year >= base.baseYear && (
              <Card title="What the new schools change"
                sub={`${current.meta.levels[filters.level].label}, ${py.year}. Pick another year with the Year control.`}>
                <NewSchoolImpact planned={levelPlanned} before={pyBefore} after={py} level={filters.level} year={py.year}
                  meta={meta} info={infoAll} />
              </Card>
            )}
            {schoolControls && (
              <Card title="New schools" sub="What if a new school is built here? Plans of new schools are separate from the intake plan.">
                <SchoolPlanBar c={schoolControls} meta={meta} />
              </Card>
            )}
            {age !== undefined ? (
              <Card title={`${entry} intake plan — new ${entry} students per district${school ? ` · ${school.name}` : ''}`}
                sub={`Children aged ${age} in the schools' catchment areas · Plan: ${presetLabel} · new ${entry} nationally: ${perYear}`}
                aside={<button type="button" onClick={() => setPlannerOpen((o) => !o)} aria-expanded={plannerOpen} className="rounded-md border border-line px-2.5 py-1 text-xs text-ink2 hover:text-ink print:hidden">{plannerOpen ? 'Hide table' : 'Show table'}</button>}>
                {plannerOpen ? (
                  <IntakePlanner base={base} intake={intake} onChange={changeIntake} grade={entry}
                    baseByDistrict={byDistrict} district={filters.district} school={school} mode={mode} scenarios={scenarioControls} />
                ) : null}

              </Card>
            ) : null}
            {age === undefined && feed ? (
              <Card title={school ? `New ${entry} students · ${school.name}` : `New ${entry} students per district`}
                sub={`From the ${feed.source} of the year before${feed.sameSchool ? ' in the same school' : ''}${feed.targets.length > 1 ? `, split between ${feed.targets.join(' / ')} by each district's ${base.baseYear} mix` : ''} · nationally: ${perYear}`}
                aside={<button type="button" onClick={() => setPlannerOpen((o) => !o)} aria-expanded={plannerOpen} className="rounded-md border border-line px-2.5 py-1 text-xs text-ink2 hover:text-ink print:hidden">{plannerOpen ? 'Hide table' : 'Show table'}</button>}>
                {plannerOpen && (
                  <FedEntrants base={base} grade={entry} source={feed.source} targets={feed.targets} sameSchool={feed.sameSchool}
                    byDistrict={Object.fromEntries(feed.targets.map((t) => [t, entryByDistrict[t]]))} district={filters.district}
                    school={school} mode={mode} />
                )}
              </Card>
            ) : null}
            <Card title="Students by grade and year"
              sub="Cohorts move up one grade a year. The selected year is highlighted; click a column to show that year.">
              <div className="print-cols-5 grid items-start gap-4 px-2 lg:grid-cols-5">
                <div className="print-span-3 pb-3 lg:col-span-3">
                  <CohortChart rows={cohort} years={base.years} baseYear={base.baseYear} year={year} mode={mode} onPick={pickYear} />
                </div>
                <div className="print-span-2 lg:col-span-2">
                  <CohortTable years={base.years} baseYear={base.baseYear} year={year} rows={cohort}
                    entryNote={all ? 'new students enter the first grade of each level' : entryNote(entry)} />
                </div>
              </div>
            </Card>
            {!all && (base.combos[base.levels.indexOf(level)] ?? []).length > 0 && (
              <Card title="Students by combination and year"
                sub={`${level.grades.join(', ')} combined. The selected year is highlighted; largest first.`}>
                <CombinationTable years={base.years} baseYear={base.baseYear} year={year}
                  rows={comboTable(result, meta, level.grades, codes)} />
              </Card>
            )}
          </>
        );
      }}
      shortageTop={(codes, filters) => {
        const level = base.levels.find((l) => l.level === filters.level);
        const rule = level ? level.fullDay : null; // null: all levels together
        const byYear = [...pastTotals(filters.level, codes), ...yearTotals(result, filters.level, codes)];
        return (
          <div className="print-cols-2 grid gap-4 lg:grid-cols-2">
            <Card title="Classrooms short by year" sub="Classrooms to build if no rooms are added. Click a bar to show that year.">
              <div className="px-2 pb-3">
                <YearTrend data={byYear} mode={mode} year={year} baseYear={base.baseYear} actual={[...pastYears, base.baseYear]}
                  onPick={pickYear} fullDay={rule} />
              </div>
            </Card>
            <Card title="Rooms available vs required by year"
              sub={`Rooms stay at the ${base.baseYear} count while the rooms needed follow the students. Click a year to show it.`}>
              <div className="px-2 pb-3">
                <CompareBars data={byYear.map((d) => ({ ...d, name: String(d.year) }))} mode={mode} fullDay={rule}
                  highlight={String(year)} onPick={pickYear} label="Rooms available versus required by year" />
              </div>
            </Card>
          </div>
        );
      }}
    />
  );
}

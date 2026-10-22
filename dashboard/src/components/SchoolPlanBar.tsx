import { useState } from 'react';
import type { Meta } from '../data';
import type { PlannedSchoolInput, SchoolPlan, SchoolPlanSummary } from '../newSchools';

export interface SchoolPlanControls {
  plans: SchoolPlanSummary[];
  active: SchoolPlan | null; // the saved plan on screen
  archived: SchoolPlanSummary | null; // an older plan picked: shown, not loaded
  on: boolean;
  schools: PlannedSchoolInput[];
  dirty: boolean; // the schools on screen differ from the saved plan
  canEdit: boolean; // admins save, viewers only try
  busy: boolean;
  message: string | null;
  onOpen: (id: number | null) => void;
  onToggle: (on: boolean) => void;
  onEdit: (i: number) => void;
  onRemove: (i: number) => void;
  onSave: () => void;
  onSaveAs: (name: string) => void;
  onDelete: () => void;
  onCopy: (name: string) => void;
}

/** "New schools": the plan of planned schools on screen, switched on or off, separate from the intake plan. */
export default function SchoolPlanBar({ c, meta }: { c: SchoolPlanControls; meta: Meta }) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  const btn = 'rounded-md border border-line px-3 py-1 text-ink2 hover:text-ink disabled:opacity-50 disabled:hover:text-ink2';
  const levelLabel = (levels: Record<string, number>) =>
    Object.entries(levels).map(([k, n]) => `${meta.levels.find((l) => l.key === k)?.label ?? k} ${n} rooms`).join(' + ');
  const submit = () => {
    if (!name.trim()) return;
    c.onSaveAs(name.trim());
    setNaming(false);
    setName('');
  };

  return (
    <div className="px-4 pb-4">
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-[var(--line)] px-3 py-2 text-sm print:hidden">
        <label className="flex items-center gap-2 text-ink2">
          Plan
          <select aria-label="Open a saved plan of new schools" className="h-8 max-w-[260px] px-2 text-sm font-medium text-ink"
            disabled={c.busy} value={c.archived?.id ?? c.active?.id ?? ''}
            onChange={(e) => c.onOpen(e.target.value === '' ? null : Number(e.target.value))}>
            <option value="">{c.active || !c.schools.length ? 'None' : 'Unsaved schools'}</option>
            {c.plans.filter((p) => !p.archived).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {c.plans.some((p) => p.archived) && (
              <optgroup label="Archived (older years)">
                {c.plans.filter((p) => p.archived).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.base_year + 1}–{p.base_year + 4})</option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        <button type="button" role="switch" aria-checked={c.on} disabled={!c.schools.length}
          onClick={() => c.onToggle(!c.on)}
          className="inline-flex items-center gap-2 rounded-md px-1 text-ink2 disabled:opacity-50">
          <span className={`relative inline-block h-4 w-8 rounded-full ${c.on ? 'bg-accent' : 'bg-[var(--muted,#999)]'}`}>
            <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${c.on ? 'right-0.5' : 'left-0.5'}`} />
          </span>
          <span className="font-medium text-ink">{c.on ? 'On' : 'Off'}</span>
        </button>
        <span className="text-xs text-muted">
          {c.schools.length ? `${c.schools.length} planned school${c.schools.length === 1 ? '' : 's'}` : 'No planned school yet'}
          {c.dirty && <span className="ml-1 font-medium text-accent">· {c.canEdit ? 'unsaved changes' : 'changed (not saved)'}</span>}
        </span>
        {c.canEdit && (
          <>
            <button type="button" className={btn} disabled={c.busy || !c.active || !c.dirty || !c.schools.length} onClick={c.onSave}>
              Save
            </button>
            {naming ? (
              <span className="flex items-center gap-1">
                <input autoFocus value={name} maxLength={100} placeholder="Name of the plan" aria-label="Name of the plan"
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') submit();
                    if (e.key === 'Escape') setNaming(false);
                  }}
                  className="h-8 w-52 px-2 text-sm" />
                <button type="button" className={btn} disabled={c.busy || !name.trim()} onClick={submit}>Save</button>
                <button type="button" className="px-2 text-sm text-muted hover:text-ink" onClick={() => setNaming(false)}>Cancel</button>
              </span>
            ) : (
              <button type="button" className={btn} disabled={c.busy || !c.schools.length} onClick={() => setNaming(true)}>
                Save as new plan…
              </button>
            )}
            {c.active && (
              <button type="button" className="px-2 text-sm text-[var(--deficit)] hover:underline disabled:opacity-50"
                disabled={c.busy} onClick={c.onDelete}>
                Delete
              </button>
            )}
          </>
        )}
        <span className="ml-auto text-xs text-muted">
          {c.canEdit ? 'Saved plans are shared with everyone who uses the dashboard.'
            : 'You can try new schools; only an administrator can save them.'}
        </span>
      </div>

      {c.schools.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Planned schools">
          {c.schools.map((s, i) => (
            <li key={i} className={`inline-flex items-center gap-1 rounded-md border border-accent bg-[var(--accent-soft)] py-0.5 pl-2.5 pr-1 text-sm text-ink ${c.on ? '' : 'opacity-60'}`}>
              <span>{s.name} · {levelLabel(s.levels)} · opens {s.opening_year}</span>
              <button type="button" aria-label={`Edit ${s.name}`} title="Edit" onClick={() => c.onEdit(i)}
                className="grid h-6 w-6 place-items-center rounded text-ink2 hover:text-ink">✎</button>
              <button type="button" aria-label={`Remove ${s.name}`} title="Remove" onClick={() => c.onRemove(i)}
                className="grid h-6 w-6 place-items-center rounded text-ink2 hover:text-ink">✕</button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">
        Use <b>+ Plan a new school</b> on the map, then click where it would be built. A new school takes the extra students
        of the crowded schools of its level within walking distance, every year from its opening year, up to its own
        classrooms. Switch <b>Off</b> to see the projection without the new schools.
      </p>
      {c.archived && (
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink2" role="status">
          “{c.archived.name}” was made for {c.archived.base_year + 1}–{c.archived.base_year + 4} and is archived.
          {c.canEdit ? (
            <button type="button" className={btn} disabled={c.busy}
              onClick={() => c.onCopy(`${c.archived!.name} (from ${c.archived!.base_year + 1})`)}>
              Copy to the current years
            </button>
          ) : ' An administrator can copy it to the current years.'}
        </p>
      )}
      {c.message && <p className="mt-1.5 text-xs text-ink2" role="status">{c.message}</p>}
    </div>
  );
}

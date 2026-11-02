import { useState } from 'react';
import type { Meta } from '../data';
import type { ProjectionBase } from '../projection';
import { DEFAULT_KM, defaultClassrooms, type PlannedSchoolInput } from '../newSchools';

const TOGETHER = 'NUR+PRI'; // Pre-Primary and Primary in one school

/** Name, level(s), classrooms, opening year and walking distance of a new school placed on the map. */
export default function NewSchoolForm({ base, meta, initial, editing, error, busy, onSubmit, onCancel }: {
  base: ProjectionBase;
  meta: Meta;
  initial: PlannedSchoolInput;
  editing: boolean; // an existing planned school (else a new one)
  error: string | null;
  busy: boolean;
  onSubmit: (s: PlannedSchoolInput) => void;
  onCancel: () => void;
}) {
  const keyOf = (levelIndex: number) => meta.levels[levelIndex].key;
  const projected = base.levels.map((l) => l.level);
  const [name, setName] = useState(initial.name);
  const [choice, setChoice] = useState(Object.keys(initial.levels).sort().join('+') === 'NUR+PRI' ? TOGETHER : Object.keys(initial.levels)[0]);
  const [rooms, setRooms] = useState<Record<string, number>>(initial.levels);
  const [opening, setOpening] = useState(initial.opening_year);
  const [km, setKm] = useState(initial.walking_km);
  const keys = choice === TOGETHER ? ['NUR', 'PRI'] : [choice];

  const pickLevel = (next: string) => {
    setChoice(next);
    const nextKeys = next === TOGETHER ? ['NUR', 'PRI'] : [next];
    setRooms(Object.fromEntries(nextKeys.map((k) => [k, defaultClassrooms(base, meta.levels.findIndex((l) => l.key === k))])));
    setKm(DEFAULT_KM[nextKeys[0]] ?? 3);
  };
  const field = 'mt-0.5 h-8 w-full px-2 text-sm';
  const label = 'mt-2 block text-xs text-ink2';
  const valid = name.trim() && keys.every((k) => rooms[k] >= 1 && rooms[k] <= 200) && km > 0 && km <= 20;

  return (
    <form className="p-3 text-ink"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) {
          onSubmit({ ...initial, name: name.trim(), levels: Object.fromEntries(keys.map((k) => [k, rooms[k]])),
            opening_year: opening, walking_km: km });
        }
      }}>
      <div className="text-sm font-semibold">{editing ? 'Edit the planned school' : 'New school'}</div>
      <p className="text-[11px] text-muted">
        {initial.latitude.toFixed(5)}, {initial.longitude.toFixed(5)}
      </p>

      <label className={label}>Name
        <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} className={field} />
      </label>
      <label className={label}>Level
        <select value={choice} onChange={(e) => pickLevel(e.target.value)} className={field}>
          {projected.map((i) => <option key={i} value={keyOf(i)}>{meta.levels[i].label}</option>)}
          <option value={TOGETHER}>Pre-Primary + Primary</option>
        </select>
      </label>
      {keys.map((k) => {
        const i = meta.levels.findIndex((l) => l.key === k);
        const standard = defaultClassrooms(base, i);
        return (
          <label key={k} className={label}>
            Classrooms{keys.length > 1 ? ` · ${meta.levels[i].label}` : ''}{' '}
            <span className="text-muted">(standard: {standard}, 2 per grade)</span>
            <input type="number" min={1} max={200} value={rooms[k] ?? standard}
              onChange={(e) => setRooms((r) => ({ ...r, [k]: Math.round(Number(e.target.value)) }))} className={field} />
          </label>
        );
      })}
      <label className={label}>Opens in
        <select value={opening} onChange={(e) => setOpening(Number(e.target.value))} className={field}>
          {base.years.slice(1).map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
      <label className={label}>Walking distance (km), along roads and paths
        <input type="number" min={0.5} max={20} step={0.5} value={km}
          onChange={(e) => setKm(Number(e.target.value))} className={field} />
      </label>
      <p className="mt-1 text-[11px] text-muted">Walking area appears after calculation</p>

      {error && <p className="mt-2 text-xs text-[var(--deficit)]" role="alert">{error}</p>}
      <div className="mt-3 flex items-center gap-2">
        <button type="submit" disabled={!valid || busy}
          className="h-8 flex-1 rounded-md bg-accent px-3 text-sm font-semibold text-white disabled:opacity-50">
          {busy ? 'Calculating…' : 'See what changes'}
        </button>
        <button type="button" onClick={onCancel} className="h-8 px-2 text-sm text-muted hover:text-ink">Cancel</button>
      </div>
    </form>
  );
}

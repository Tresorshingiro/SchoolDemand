import { useEffect, useRef, useState } from 'react';
import { CAPACITY_MAX, CAPACITY_MIN, DEFAULT_ASSUMPTIONS, isDefaultAssumptions, type Assumptions } from '../projection';

const WAIT_MS = 400; // a typed number runs this long after typing stops

const validCapacity = (text: string): number | null => {
  if (!/^\d+$/.test(text.trim())) return null;
  const n = Number(text);
  return n >= CAPACITY_MIN && n <= CAPACITY_MAX ? n : null;
};

/** Filter-bar controls to try another number of students per classroom and switch repetition and dropout. */
export default function AssumptionControls({ value, onChange }: {
  value: Assumptions; onChange: (a: Assumptions) => void;
}) {
  const [text, setText] = useState(String(value.capacity));
  const timer = useRef<number | undefined>(undefined);
  const invalid = validCapacity(text) === null;

  // Always the latest values when the wait ends, so a switch used meanwhile is kept
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const type = (next: string) => {
    setText(next);
    window.clearTimeout(timer.current);
    const n = validCapacity(next);
    if (n === null) return;
    timer.current = window.setTimeout(() => {
      if (n !== latest.current.capacity) onChange({ ...latest.current, capacity: n });
    }, WAIT_MS);
  };
  const reset = () => {
    window.clearTimeout(timer.current);
    setText(String(DEFAULT_ASSUMPTIONS.capacity));
    onChange(DEFAULT_ASSUMPTIONS);
  };
  const changed = invalid || !isDefaultAssumptions(value) || validCapacity(text) !== DEFAULT_ASSUMPTIONS.capacity;

  return (
    <>
      <label className="flex items-center gap-2 text-sm text-ink2"
        title="Secondary, TVET and Professional Education: each class stream still needs its own room, so a higher number may barely reduce the shortage.">
        Students per classroom
        <input type="number" inputMode="numeric" min={CAPACITY_MIN} max={CAPACITY_MAX} step={1} value={text}
          aria-label="Students per classroom" aria-invalid={invalid}
          className={`h-8 w-16 rounded-md border bg-surface px-2 text-sm font-medium text-ink ${invalid ? 'border-[var(--deficit)]' : 'border-line'}`}
          onChange={(e) => type(e.target.value)} />
      </label>
      {invalid && <span className="text-xs text-[var(--deficit)]" role="alert">{CAPACITY_MIN} to {CAPACITY_MAX}</span>}
      <label className="flex items-center gap-1.5 text-sm text-ink2">
        <input type="checkbox" role="switch" checked={value.repetition}
          onChange={(e) => onChange({ ...value, repetition: e.target.checked })} />
        Repetition
      </label>
      <label className="flex items-center gap-1.5 text-sm text-ink2">
        <input type="checkbox" role="switch" checked={value.dropout}
          onChange={(e) => onChange({ ...value, dropout: e.target.checked })} />
        Dropout
      </label>
      {changed && (
        <button type="button" onClick={reset} className="text-sm text-accent underline underline-offset-2">Reset</button>
      )}
    </>
  );
}

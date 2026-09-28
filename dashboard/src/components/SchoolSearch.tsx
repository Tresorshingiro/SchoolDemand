import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { Meta, SchoolLevel } from '../data';

const MAX_RESULTS = 10;

/** Lower case, accents removed: "École" matches "ecole". */
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

interface Entry {
  code: number;
  name: string;
  district: string;
  sector: string;
  levels: number[]; // indexes into meta.levels, in order
  key: string; // folded name
}

/**
 * Find any school in the country by name (words in any order, accents ignored) or code, whatever the filters.
 * `/` focuses the box; arrows move through the results, Enter picks, Escape closes.
 */
export default function SchoolSearch({ schools, meta, onPick }: {
  schools: SchoolLevel[]; meta: Meta; onPick: (code: number, levels: number[]) => void;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const index = useMemo(() => {
    const byCode = new Map<number, Entry>();
    for (const r of schools) {
      const e = byCode.get(r.c);
      if (e) e.levels.push(r.l);
      else byCode.set(r.c, { code: r.c, name: r.n, district: r.d, sector: r.s, levels: [r.l], key: fold(r.n) });
    }
    const entries = [...byCode.values()];
    for (const e of entries) e.levels.sort((a, b) => a - b);
    return entries.sort((a, b) => a.name.localeCompare(b.name));
  }, [schools]);

  const results = useMemo(() => {
    const q = fold(query.trim());
    if (!q) return [];
    if (/^\d+$/.test(q)) return index.filter((e) => String(e.code).startsWith(q)).slice(0, MAX_RESULTS);
    const words = q.split(/\s+/);
    const hits = index.filter((e) => words.every((w) => e.key.includes(w)));
    // Names starting with the query first
    hits.sort((a, b) => Number(b.key.startsWith(words[0])) - Number(a.key.startsWith(words[0])));
    return hits.slice(0, MAX_RESULTS);
  }, [index, query]);

  useEffect(() => setActive(0), [query]);

  // "/" anywhere on the page (outside a text field) jumps to the search box
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key !== '/' || t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const pick = (e: Entry) => {
    onPick(e.code, e.levels);
    setQuery('');
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault();
      pick(results[active]);
    } else if (e.key === 'Escape') {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  const showList = open && query.trim().length > 0;

  return (
    <div className="relative w-full sm:w-72">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75"
        strokeLinecap="round" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true">
        <path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M20 20l-4-4" />
      </svg>
      <input ref={inputRef} type="search" value={query} placeholder="Search any school by name or code…"
        role="combobox" aria-label="Search any school" aria-expanded={showList} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={showList && results[active] ? `${listId}-${results[active].code}` : undefined}
        className="h-8 w-full pl-8 pr-7 text-sm placeholder:text-muted"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown} />
      <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded border border-line px-1 text-[10px] text-muted sm:block"
        aria-hidden="true">/</kbd>

      {showList && (
        <ul id={listId} role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[360px] overflow-y-auto rounded-md border border-line bg-surface py-1 shadow-lg sm:w-[420px]">
          {results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted">No school matches "{query.trim()}".</li>
          ) : (
            results.map((e, i) => (
              <li key={e.code} id={`${listId}-${e.code}`} role="option" aria-selected={i === active}
                onMouseDown={(ev) => { ev.preventDefault(); pick(e); }} // before the input's blur closes the list
                onMouseEnter={() => setActive(i)}
                className={`cursor-pointer px-3 py-1.5 ${i === active ? 'bg-[var(--accent-soft)]' : ''}`}>
                <div className="truncate text-sm text-ink">{e.name}</div>
                <div className="truncate text-xs text-muted">
                  {e.district} · {e.sector} · code {e.code} · {e.levels.map((l) => meta.levels[l].label).join(', ')}
                </div>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

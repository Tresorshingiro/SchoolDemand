import { useCallback, useEffect, useMemo, useState } from 'react';
import { Database, FileText, History, UserRound, type LucideIcon } from 'lucide-react';
import { listAudit, listUsers, type AdminUser, type AuditEntry } from './api';
import { Alert, Avatar, EmptyState, PageHeader, Panel, btn, field } from './ui';

const ACTIONS = [
  { value: '', label: 'All actions' },
  { value: 'user.', label: 'Accounts' },
  { value: 'scenario.', label: 'Saved plans' },
  { value: 'data.', label: 'Data' },
];
const PAGE = 50;
const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' });
const dayName = new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const KIND: Record<string, { icon: LucideIcon; color: string }> = {
  user: { icon: UserRound, color: 'var(--accent)' },
  scenario: { icon: FileText, color: '#8b5cf6' },
  data: { icon: Database, color: '#1f9d55' },
};

/** Who did it: a name, or the system (command line, or an account removed since). */
const actor = (e: AuditEntry) => e.user_name || e.user_email || 'System';

/** What was done, as the rest of a sentence after the actor. */
export function action(e: AuditEntry): string {
  const d = e.detail ?? {};
  switch (e.action) {
    case 'user.create': return `added ${e.target} as ${String(d.role ?? 'viewer')}`;
    case 'user.update': return `renamed ${e.target} to "${String(d.full_name ?? '')}"`;
    case 'user.role': return `changed ${e.target} from ${String(d.from)} to ${String(d.to)}`;
    case 'user.disable': return `disabled ${e.target}`;
    case 'user.enable': return `enabled ${e.target}`;
    case 'user.password_reset': return `reset the password of ${e.target}`;
    case 'user.password_change': return 'changed their password';
    case 'scenario.create': return `saved the plan "${e.target}"`;
    case 'scenario.update': return `updated the plan "${e.target}"`;
    case 'scenario.delete': return `deleted the plan "${e.target}"`;
    case 'data.upload': return `uploaded ${e.target}`;
    case 'data.publish': return `published ${e.target}`;
    case 'data.republish': return `published again ${e.target}`;
    case 'data.discard': return `discarded ${e.target}`;
    case 'data.withdraw': return `withdrew ${e.target}`;
    default: return `${e.action} ${e.target}`;
  }
}

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date(today.getTime() - 864e5);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return dayName.format(d);
}

/** The audit log: who changed what, newest first, by day. */
export default function ActivityPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userId, setUserId] = useState<number | undefined>(undefined);
  const [filter, setFilter] = useState('');
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listUsers().then(setUsers).catch(() => undefined); // the filter still works without names
  }, []);

  const load = useCallback(async (before?: number) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAudit({ before, userId, action: filter, limit: PAGE });
      setEntries((prev) => (before === undefined ? page : [...prev, ...page]));
      setMore(page.length === PAGE);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [userId, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const days = useMemo(() => {
    const out: { label: string; items: AuditEntry[] }[] = [];
    for (const e of entries) {
      const label = dayLabel(new Date(e.at));
      if (out[out.length - 1]?.label !== label) out.push({ label, items: [] });
      out[out.length - 1].items.push(e);
    }
    return out;
  }, [entries]);

  return (
    <div>
      <PageHeader title="Activity" description="Changes to accounts, saved plans and data, newest first."
        actions={
          <>
            <select aria-label="Who" className={field} value={userId ?? ''}
              onChange={(e) => setUserId(e.target.value === '' ? undefined : Number(e.target.value))}>
              <option value="">Everyone</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
            </select>
            <select aria-label="Action" className={field} value={filter} onChange={(e) => setFilter(e.target.value)}>
              {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
          </>
        } />
      {error && <Alert tone="error">{error}</Alert>}

      {!entries.length && !loading ? (
        <Panel><EmptyState icon={<History size={18} />} title="Nothing recorded yet" /></Panel>
      ) : (
        <div className="space-y-6">
          {days.map((day) => (
            <section key={day.label}>
              <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-muted">{day.label}</h2>
              <Panel>
                <ul className="divide-y divide-[var(--line)]">
                  {day.items.map((e) => {
                    const kind = KIND[e.action.split('.')[0]] ?? KIND.user;
                    const Icon = kind.icon;
                    return (
                      <li key={e.id} className="flex items-center gap-3 px-4 py-3">
                        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                          style={{ color: kind.color, background: `color-mix(in srgb, ${kind.color} 12%, transparent)` }}>
                          <Icon size={15} aria-hidden />
                        </span>
                        <p className="min-w-0 flex-1 text-[13px] leading-snug text-ink2">
                          <span className="font-medium text-ink">{actor(e)}</span> {action(e)}
                        </p>
                        <span className="hidden sm:block"><Avatar name={actor(e)} size={24} /></span>
                        <time className="w-12 shrink-0 text-right text-[12px] tabular-nums text-muted" dateTime={e.at}>
                          {time.format(new Date(e.at))}
                        </time>
                      </li>
                    );
                  })}
                </ul>
              </Panel>
            </section>
          ))}
        </div>
      )}
      {more && (
        <div className="mt-4 flex justify-center">
          <button type="button" disabled={loading} onClick={() => void load(entries[entries.length - 1]?.id)} className={btn.secondary}>
            {loading ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}

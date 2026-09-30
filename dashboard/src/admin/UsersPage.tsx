import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Copy, KeyRound, MoreHorizontal, Plus, Search, ShieldCheck, UserRound, Users } from 'lucide-react';
import { useAuth } from '../auth';
import { listUsers, updateUser, type AdminUser } from './api';
import UserPanel, { type PanelMode, type PanelResult } from './UserPanel';
import { Alert, Avatar, EmptyState, PageHeader, Panel, Pill, StatCard, btn, field, td, th, type Tone } from './ui';

type Status = 'Active' | 'Disabled' | 'Must change password';
const statusOf = (u: AdminUser): Status => (!u.is_active ? 'Disabled' : u.must_change_password ? 'Must change password' : 'Active');
const STATUS_TONE: Record<Status, Tone> = { Active: 'green', Disabled: 'grey', 'Must change password': 'amber' };
const lastIn = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const OWN = 'You cannot remove your own admin access.';
const LAST = 'At least one active administrator is needed.';

/** Row menu: edit, reset password, disable / enable. */
function RowMenu({ user, lock, onPick }: {
  user: AdminUser;
  lock: string | null;
  onPick: (action: 'edit' | 'reset' | 'toggle') => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  const item = 'block w-full px-3 py-2 text-left text-[13px] text-ink2 hover:bg-[var(--line)] hover:text-ink disabled:cursor-not-allowed disabled:opacity-50';
  const pick = (a: 'edit' | 'reset' | 'toggle') => {
    setOpen(false);
    onPick(a);
  };
  const toggleLocked = user.is_active && !!lock;
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-label={`Actions for ${user.email}`} aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((o) => !o)} className={btn.icon}>
        <MoreHorizontal size={16} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-1 w-44 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-lg">
          <button role="menuitem" type="button" className={item} onClick={() => pick('edit')}>Edit</button>
          <button role="menuitem" type="button" className={item} onClick={() => pick('reset')}>Reset password</button>
          <button role="menuitem" type="button" className={item} disabled={toggleLocked} title={toggleLocked ? lock! : undefined}
            onClick={() => pick('toggle')}>
            {user.is_active ? 'Disable' : 'Enable'}
          </button>
        </div>
      )}
    </div>
  );
}

/** Accounts: add, edit, reset passwords, disable / enable. */
export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [shown, setShown] = useState<{ name: string; value: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [panel, setPanel] = useState<PanelMode | null>(null);

  const refresh = useCallback(() => {
    listUsers().then(setUsers).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoaded(true));
  }, []);
  useEffect(refresh, [refresh]);

  const activeAdmins = users.filter((u) => u.role === 'admin' && u.is_active).length;
  /** Why this user cannot lose admin access right now, or null. */
  const lockOf = (u: AdminUser): string | null => {
    if (u.role !== 'admin' || !u.is_active) return null;
    if (u.id === me?.id) return OWN;
    return activeAdmins <= 1 ? LAST : null;
  };

  const shownUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) =>
      (!q || u.email.includes(q) || (u.full_name ?? '').toLowerCase().includes(q)) &&
      (!role || u.role === role) && (!status || statusOf(u) === status));
  }, [users, search, role, status]);

  const done = (r: PanelResult) => {
    setPanel(null);
    setNotice(r.message);
    setShown(r.password ?? null);
    setCopied(false);
    refresh();
  };

  const toggle = async (u: AdminUser) => {
    if (u.is_active && !window.confirm(`Disable ${u.email}? They are signed out at once and can no longer sign in.`)) return;
    setError(null);
    try {
      await updateUser(u.id, { is_active: !u.is_active });
      setNotice(`${u.email} ${u.is_active ? 'disabled' : 'enabled'}.`);
      setShown(null);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const copy = async () => {
    if (!shown) return;
    try {
      await navigator.clipboard.writeText(shown.value);
      setCopied(true);
    } catch {
      setCopied(false); // no clipboard (plain http): the password stays visible to copy by hand
    }
  };

  return (
    <div>
      <PageHeader title="Users"
        description="Admins manage users, saved plans and data; viewers see everything and can try plans."
        actions={
          <button type="button" onClick={() => setPanel({ kind: 'add' })} className={btn.primary}>
            <Plus size={16} aria-hidden /> Add user
          </button>
        } />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Accounts" value={users.length} icon={<Users size={18} />} />
        <StatCard label="Administrators" value={users.filter((u) => u.role === 'admin').length}
          icon={<ShieldCheck size={18} />} tone="green" />
        <StatCard label="Viewers" value={users.filter((u) => u.role === 'viewer').length} icon={<UserRound size={18} />} tone="grey" />
        <StatCard label="Must change password" value={users.filter((u) => u.is_active && u.must_change_password).length}
          icon={<KeyRound size={18} />} tone="amber" />
      </div>

      {shown && (
        <Panel className="mb-4 border-[color-mix(in_srgb,var(--accent)_40%,transparent)] p-4">
          <p className="text-[13px] text-ink">Give this password to {shown.name}; they will choose their own at first sign-in.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded-lg border border-line bg-page px-3 py-1.5 font-mono text-[15px] tracking-wide text-ink">{shown.value}</code>
            <button type="button" onClick={() => void copy()} className={btn.secondary}>
              <Copy size={14} aria-hidden /> {copied ? 'Copied' : 'Copy'}
            </button>
            <button type="button" onClick={() => setShown(null)} className="ml-auto text-[12px] text-muted hover:text-ink">
              Done — hide it
            </button>
          </div>
        </Panel>
      )}
      {notice && !shown && <Alert tone="info">{notice}</Alert>}
      {error && <Alert tone="error">{error}</Alert>}

      <Panel className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <input type="search" placeholder="Search name or email" aria-label="Search users" value={search}
              onChange={(e) => setSearch(e.target.value)} className={`${field} w-full pl-9`} />
          </div>
          <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)} className={field}>
            <option value="">All roles</option>
            <option value="admin">Administrators</option>
            <option value="viewer">Viewers</option>
          </select>
          <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
            <option value="">All statuses</option>
            <option>Active</option>
            <option>Must change password</option>
            <option>Disabled</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-page">
              <tr>
                <th className={th}>User</th>
                <th className={th}>Role</th>
                <th className={th}>Status</th>
                <th className={th}>Last sign-in</th>
                <th className="w-12 px-2 py-2.5"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)]">
              {shownUsers.map((u) => (
                <tr key={u.id} className="transition hover:bg-page">
                  <td className={td}>
                    <div className="flex items-center gap-3">
                      <Avatar name={u.full_name || u.email} />
                      <div className="min-w-0">
                        <div className="truncate font-medium text-ink">
                          {u.full_name || '—'}
                          {u.id === me?.id && <span className="ml-1.5 text-[11px] font-normal text-muted">(you)</span>}
                        </div>
                        <div className="truncate text-[12px] text-muted">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className={td}>
                    {u.role === 'admin' ? <Pill tone="blue">Administrator</Pill> : <Pill tone="grey">Viewer</Pill>}
                  </td>
                  <td className={td}><Pill tone={STATUS_TONE[statusOf(u)]}>{statusOf(u)}</Pill></td>
                  <td className={td}>{u.last_login_at ? lastIn.format(new Date(u.last_login_at)) : <span className="text-muted">Never</span>}</td>
                  <td className="px-2 py-3 text-right">
                    <RowMenu user={u} lock={lockOf(u)}
                      onPick={(a) => (a === 'toggle' ? void toggle(u) : setPanel({ kind: a, user: u }))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loaded && !shownUsers.length && (
            <EmptyState icon={<Search size={18} />} title="No user matches"
              text="Change the search or the filters, or add a user." />
          )}
        </div>
      </Panel>

      {panel && (
        <UserPanel mode={panel} roleLock={panel.kind === 'edit' ? lockOf(panel.user) : null}
          onClose={() => setPanel(null)} onDone={done} />
      )}
    </div>
  );
}

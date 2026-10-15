import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MoreHorizontal, Search, ShieldCheck, UserRound, UserX, Users } from 'lucide-react';
import { useAuth } from '../auth';
import { listUsers, updateUser, type AdminUser, type Role } from './api';
import { Alert, Avatar, EmptyState, PageHeader, Panel, Pill, StatCard, btn, field, td, th, type Tone } from './ui';

type Status = 'Active' | 'Disabled';
const statusOf = (u: AdminUser): Status => (u.is_active ? 'Active' : 'Disabled');
const STATUS_TONE: Record<Status, Tone> = { Active: 'green', Disabled: 'grey' };
const lastIn = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const OWN = 'You cannot remove your own admin access.';
const LAST = 'At least one active administrator is needed.';
const nameOf = (u: AdminUser) => u.full_name || u.username;

type Action = 'role' | 'toggle';

/** Row menu: make admin / viewer, disable / enable. */
function RowMenu({ user, lock, onPick }: {
  user: AdminUser;
  lock: string | null; // why this user cannot lose admin access now, or null
  onPick: (action: Action) => void;
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
  const pick = (a: Action) => {
    setOpen(false);
    onPick(a);
  };
  const demoteLocked = user.role === 'admin' && !!lock;
  const disableLocked = user.is_active && !!lock;
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-label={`Actions for ${user.username}`} aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((o) => !o)} className={btn.icon}>
        <MoreHorizontal size={16} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-1 w-48 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-lg">
          <button role="menuitem" type="button" className={item} disabled={demoteLocked} title={demoteLocked ? lock! : undefined}
            onClick={() => pick('role')}>
            {user.role === 'admin' ? 'Make viewer' : 'Make administrator'}
          </button>
          <button role="menuitem" type="button" className={item} disabled={disableLocked} title={disableLocked ? lock! : undefined}
            onClick={() => pick('toggle')}>
            {user.is_active ? 'Disable' : 'Enable'}
          </button>
        </div>
      )}
    </div>
  );
}

/** Accounts: everyone who has signed in with a MINEDUC GIS portal account; change their role, disable / enable. */
export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');

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
      (!q || [u.username, u.full_name, u.email].some((v) => (v ?? '').toLowerCase().includes(q))) &&
      (!role || u.role === role) && (!status || statusOf(u) === status));
  }, [users, search, role, status]);

  const change = async (u: AdminUser, body: { role?: Role; is_active?: boolean }, message: string) => {
    setError(null);
    try {
      await updateUser(u.id, body);
      setNotice(message);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const pick = (u: AdminUser, a: Action) => {
    if (a === 'role') {
      const to: Role = u.role === 'admin' ? 'viewer' : 'admin';
      void change(u, { role: to }, `${nameOf(u)} is now ${to === 'admin' ? 'an administrator' : 'a viewer'}.`);
      return;
    }
    if (u.is_active && !window.confirm(`Disable ${nameOf(u)}? They are signed out at once and can no longer sign in here, even with their portal password.`)) return;
    void change(u, { is_active: !u.is_active }, `${nameOf(u)} ${u.is_active ? 'disabled' : 'enabled'}.`);
  };

  return (
    <div>
      <PageHeader title="Users"
        description="Everyone with a MINEDUC GIS portal account can sign in. People appear here after their first sign-in, as administrators; make someone a viewer or disable them here. Passwords are managed in the portal." />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Accounts" value={users.length} icon={<Users size={18} />} />
        <StatCard label="Administrators" value={users.filter((u) => u.role === 'admin').length}
          icon={<ShieldCheck size={18} />} tone="green" />
        <StatCard label="Viewers" value={users.filter((u) => u.role === 'viewer').length} icon={<UserRound size={18} />} tone="grey" />
        <StatCard label="Disabled" value={users.filter((u) => !u.is_active).length} icon={<UserX size={18} />} tone="amber" />
      </div>

      {notice && <Alert tone="info">{notice}</Alert>}
      {error && <Alert tone="error">{error}</Alert>}

      <Panel className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <input type="search" placeholder="Search name, username or email" aria-label="Search users" value={search}
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
                      <Avatar name={nameOf(u)} />
                      <div className="min-w-0">
                        <div className="truncate font-medium text-ink">
                          {u.full_name || u.username}
                          {u.id === me?.id && <span className="ml-1.5 text-[11px] font-normal text-muted">(you)</span>}
                        </div>
                        <div className="truncate text-[12px] text-muted">
                          {u.username}{u.email ? ` · ${u.email}` : ''}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className={td}>
                    {u.role === 'admin' ? <Pill tone="blue">Administrator</Pill> : <Pill tone="grey">Viewer</Pill>}
                  </td>
                  <td className={td}><Pill tone={STATUS_TONE[statusOf(u)]}>{statusOf(u)}</Pill></td>
                  <td className={td}>{u.last_login_at ? lastIn.format(new Date(u.last_login_at)) : <span className="text-muted">Never</span>}</td>
                  <td className="px-2 py-3 text-right">
                    <RowMenu user={u} lock={lockOf(u)} onPick={(a) => pick(u, a)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loaded && !shownUsers.length && (
            <EmptyState icon={<Search size={18} />} title="No user matches" text="Change the search or the filters." />
          )}
        </div>
      </Panel>
    </div>
  );
}

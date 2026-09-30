import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Activity, ArrowLeft, Database, History, LogOut, Menu, Users, X, type LucideIcon } from 'lucide-react';
import { displayName, useAuth } from '../auth';
import { ThemeToggle } from '../theme';
import { LogoMark } from '../site/SiteChrome';
import { Avatar, btn } from './ui';

const GROUPS: { label: string; links: { to: string; label: string; icon: LucideIcon; end?: boolean }[] }[] = [
  { label: 'People', links: [
    { to: '/admin/users', label: 'Users', icon: Users },
    { to: '/admin/activity', label: 'Activity', icon: Activity },
  ] },
  { label: 'Data', links: [
    { to: '/admin/data', label: 'Data sources', icon: Database, end: true },
    { to: '/admin/data/history', label: 'Import history', icon: History },
  ] },
];

/** The admin portal's frame: a sidebar on wide screens, a top bar with a menu on phones. */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);

  const onSignOut = () => {
    navigate('/', { replace: true });
    void signOut();
  };

  const nav = (
    <nav className="flex flex-1 flex-col" aria-label="Admin">
      {GROUPS.map((g) => (
        <div key={g.label} className="mb-4">
          <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">{g.label}</div>
          <div className="flex flex-col gap-0.5">
            {g.links.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end}
                className={({ isActive }) => `relative flex h-9 items-center gap-2.5 rounded-lg px-3 text-[13px] transition ${
                  isActive ? 'bg-[var(--accent-soft)] font-medium text-accent' : 'text-ink2 hover:bg-[var(--line)] hover:text-ink'}`}>
                {({ isActive }) => (
                  <>
                    {isActive && <span className="absolute -left-3 top-1.5 h-6 w-[3px] rounded-r bg-accent" aria-hidden />}
                    <Icon size={16} aria-hidden />
                    {label}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
  const footer = (
    <div className="space-y-3 border-t border-line pt-3">
      <Link to="/dashboard" className="flex h-9 items-center gap-2.5 rounded-lg px-3 text-[13px] text-ink2 transition hover:bg-[var(--line)] hover:text-ink">
        <ArrowLeft size={16} aria-hidden />
        Back to the dashboard
      </Link>
      {user && (
        <div className="flex items-center gap-2.5 rounded-xl border border-line bg-page p-2.5">
          <Avatar name={displayName(user)} size={34} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium text-ink" title={user.email}>{displayName(user)}</div>
            <div className="text-[11px] text-muted">Administrator</div>
          </div>
          <ThemeToggle className={btn.icon} />
          <button type="button" onClick={onSignOut} title="Sign out" aria-label="Sign out" className={btn.icon}>
            <LogOut size={16} aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
  const brand = (
    <Link to="/admin" className="flex items-center gap-2.5 px-1">
      <LogoMark size={30} />
      <span className="leading-tight">
        <span className="block text-[14px] font-semibold text-ink">Admin portal</span>
        <span className="block text-[11px] text-muted">School Demand &amp; Demographics</span>
      </span>
    </Link>
  );

  return (
    <div className="min-h-screen bg-page md:flex">
      <aside className="hidden w-60 shrink-0 flex-col gap-6 border-r border-line bg-surface px-3 py-5 md:sticky md:top-0 md:flex md:h-screen">
        {brand}
        {nav}
        {footer}
      </aside>
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface px-4 py-2.5 md:hidden">
        <div className="flex-1">{brand}</div>
        <button type="button" aria-expanded={menuOpen} aria-label="Menu" onClick={() => setMenuOpen((o) => !o)}
          className={`${btn.icon} border border-line`}>
          {menuOpen ? <X size={16} aria-hidden /> : <Menu size={16} aria-hidden />}
        </button>
      </header>
      {menuOpen && <div className="flex flex-col gap-2 border-b border-line bg-surface p-4 md:hidden">{nav}{footer}</div>}
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-[1600px]">{children}</div>
      </main>
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { PASSWORD_PAGE, displayName, isAdmin, useAuth } from './auth';

/** The signed-in user's menu in the dashboard header: change password, admin portal (admins), sign out. */
export default function UserMenu({ onSignOut }: { onSignOut: () => void }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const click = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', click);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('mousedown', click);
      document.removeEventListener('keydown', key);
    };
  }, [open]);

  if (!user) return null;
  const item = 'block w-full px-3 py-2 text-left text-sm text-ink2 hover:bg-[var(--line)] hover:text-ink';
  return (
    <div ref={ref} className="relative print:hidden">
      <button type="button" aria-haspopup="menu" aria-expanded={open} title={user.email} onClick={() => setOpen((o) => !o)}
        className="flex h-8 max-w-[260px] items-center gap-1.5 rounded-md border border-line px-2.5 text-xs text-ink2 hover:text-ink">
        <span className="truncate">{displayName(user)}</span>
        {isAdmin(user) && (
          <span className="rounded bg-[var(--accent-soft)] px-1 text-[10px] font-semibold uppercase text-accent">Admin</span>
        )}
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-50 mt-1 w-48 overflow-hidden rounded-md border border-line bg-surface py-1 shadow-lg">
          <Link role="menuitem" to={PASSWORD_PAGE} className={item} onClick={() => setOpen(false)}>Change password</Link>
          {isAdmin(user) && (
            <Link role="menuitem" to="/admin" className={item} onClick={() => setOpen(false)}>Admin portal</Link>
          )}
          <button role="menuitem" type="button" className={item}
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

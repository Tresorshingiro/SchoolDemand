import { useState, type FormEvent } from 'react';
import { X } from 'lucide-react';
import { createUser, resetPassword, updateUser, type AdminUser, type Role } from './api';
import { generatePassword } from './password';
import { btn as buttons, field as input } from './ui';

export type PanelMode = { kind: 'add' } | { kind: 'edit'; user: AdminUser } | { kind: 'reset'; user: AdminUser };
export interface PanelResult {
  message: string;
  password?: { name: string; value: string }; // shown once on the page
}

const MIN_PASSWORD = 8;
const field = `mt-1.5 w-full ${input}`;
const btn = buttons.secondary;

/** Side panel: add a user, edit name / role, or set a temporary password. */
export default function UserPanel({ mode, roleLock, onClose, onDone }: {
  mode: PanelMode;
  roleLock: string | null; // why the role cannot change (own account, last admin), or null
  onClose: () => void;
  onDone: (result: PanelResult) => void;
}) {
  const user = mode.kind === 'add' ? null : mode.user;
  const [email, setEmail] = useState('');
  const [name, setName] = useState(user?.full_name ?? '');
  const [role, setRole] = useState<Role>(user?.role ?? 'viewer');
  const [password, setPassword] = useState(mode.kind === 'edit' ? '' : generatePassword());
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const title = mode.kind === 'add' ? 'Add user' : mode.kind === 'edit' ? 'Edit user' : 'Reset password';
  const who = (u: { full_name: string | null; email: string }) => u.full_name || u.email;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (mode.kind !== 'edit' && password.length < MIN_PASSWORD) {
      setError(`The password must have at least ${MIN_PASSWORD} characters.`);
      return;
    }
    setBusy(true);
    try {
      if (mode.kind === 'add') {
        const u = await createUser({ email: email.trim(), full_name: name.trim() || null, role, password });
        onDone({ message: `Added ${u.email}.`, password: { name: who(u), value: password } });
      } else if (mode.kind === 'edit') {
        const body: { full_name?: string | null; role?: Role } = {};
        if ((name.trim() || null) !== mode.user.full_name) body.full_name = name.trim() || null;
        if (role !== mode.user.role) body.role = role;
        const u = Object.keys(body).length ? await updateUser(mode.user.id, body) : mode.user;
        onDone({ message: `Saved ${u.email}.` });
      } else {
        await resetPassword(mode.user.id, password);
        onDone({ message: `${mode.user.email} is signed out and must choose a new password.`,
          password: { name: who(mode.user), value: password } });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-[2px]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} noValidate role="dialog" aria-label={title}
        className="flex h-full w-full max-w-md flex-col gap-5 overflow-y-auto border-l border-line bg-surface p-6 shadow-2xl [&_label]:text-[13px] [&_label]:font-medium">
        <div className="flex items-center justify-between border-b border-line pb-4">
          <h2 className="text-[16px] font-semibold text-ink">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className={buttons.icon}>
            <X size={16} aria-hidden />
          </button>
        </div>
        {user && <p className="text-sm text-ink2">{user.email}</p>}

        {mode.kind === 'add' && (
          <label className="text-sm text-ink2">Email
            <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
          </label>
        )}
        {mode.kind !== 'reset' && (
          <>
            <label className="text-sm text-ink2">Name
              <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} className={field} />
            </label>
            <label className="text-sm text-ink2">Role
              <select value={role} disabled={!!roleLock} title={roleLock ?? undefined}
                onChange={(e) => setRole(e.target.value as Role)} className={field}>
                <option value="viewer">Viewer — sees everything, can try plans</option>
                <option value="admin">Admin — manages users and saved plans</option>
              </select>
              {roleLock && <span className="mt-1 block text-xs text-muted">{roleLock}</span>}
            </label>
          </>
        )}
        {mode.kind !== 'edit' && (
          <label className="text-sm text-ink2">Temporary password
            <span className="mt-1 flex gap-2">
              <input value={password} onChange={(e) => setPassword(e.target.value)} spellCheck={false} autoComplete="off"
                className={`${field} mt-0 font-mono`} />
              <button type="button" className={btn} onClick={() => setPassword(generatePassword())}>Generate</button>
            </span>
            <span className="mt-1 block text-xs text-muted">
              They will choose their own password the first time they sign in.
            </span>
          </label>
        )}

        {error && <p className="text-sm text-[var(--deficit)]" role="alert">{error}</p>}
        <div className="mt-auto flex justify-end gap-2">
          <button type="button" className={btn} onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy}
            className={buttons.primary}>
            {busy ? 'Saving…' : mode.kind === 'add' ? 'Add user' : mode.kind === 'edit' ? 'Save' : 'Set password'}
          </button>
        </div>
      </form>
    </div>
  );
}

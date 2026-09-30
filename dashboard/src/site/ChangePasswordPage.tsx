import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Lock, LogOut } from 'lucide-react';
import { sendJson } from '../api';
import { useAuth } from '../auth';
import AuthFrame from './AuthFrame';

const MIN_PASSWORD = 8; // backend/app/services/auth.py

function PasswordField({ label, value, onChange, autoComplete, disabled, autoFocus = false }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
  disabled: boolean;
  autoFocus?: boolean;
}) {
  return (
    <label className="auth2-field">
      <span>{label}</span>
      <span className="auth2-input">
        <Lock size={16} aria-hidden />
        <input type="password" autoComplete={autoComplete} value={value} autoFocus={autoFocus} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      </span>
    </label>
  );
}

/** Change your own password. Forced after an administrator created the account or reset its password. */
export default function ChangePasswordPage() {
  const { user, refresh, signOut } = useAuth();
  const navigate = useNavigate();
  const forced = !!user?.must_change_password;
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (next.length < MIN_PASSWORD) return setError(`The new password must have at least ${MIN_PASSWORD} characters.`);
    if (next !== repeat) return setError('The two new passwords differ.');
    setLoading(true);
    try {
      await sendJson<void>('POST', '/auth/password', { current_password: current, new_password: next });
      await refresh();
      navigate('/dashboard', { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  }

  const onSignOut = () => {
    navigate('/', { replace: true });
    void signOut();
  };

  return (
    <AuthFrame>
      <form className="auth2-form" onSubmit={onSubmit} noValidate>
        <div className="auth2-head">
          <h1>{forced ? 'Choose your password' : 'Change password'}</h1>
          <p>
            {forced
              ? 'You signed in with a temporary password from your administrator. Choose your own to continue.'
              : `Signed in as ${user?.email ?? ''}.`}
          </p>
        </div>
        <PasswordField label={forced ? 'Temporary password' : 'Current password'} value={current} onChange={setCurrent}
          autoComplete="current-password" disabled={loading} autoFocus />
        <PasswordField label={`New password (at least ${MIN_PASSWORD} characters)`} value={next} onChange={setNext}
          autoComplete="new-password" disabled={loading} />
        <PasswordField label="Repeat the new password" value={repeat} onChange={setRepeat}
          autoComplete="new-password" disabled={loading} />
        {error ? <p className="auth2-alert auth2-alert-error" role="alert">{error}</p> : null}
        <button type="submit" className="auth2-submit" disabled={loading}>
          {loading ? <><Loader2 size={16} className="auth2-spin" aria-hidden /> Saving…</> : 'Save password'}
        </button>
        <p className="auth2-foot">
          {forced
            ? <button type="button" className="auth2-foot-btn" onClick={onSignOut}><LogOut size={14} aria-hidden /> Sign out</button>
            : <Link to="/dashboard"><ArrowLeft size={14} aria-hidden /> Back to the dashboard</Link>}
        </p>
      </form>
    </AuthFrame>
  );
}

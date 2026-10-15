import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Eye, EyeOff, Loader2, Lock, UserRound } from 'lucide-react';
import { safeNext, useAuth } from '../auth';
import AuthFrame from './AuthFrame';

/** Sign in with a MINEDUC GIS portal account: the API checks the username and password with the portal. */
export default function LoginPage() {
  const { user, checking, signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);

  if (!checking && user && !loading) return <Navigate to={next} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setInfo('');
    if (!username.trim() || !password) {
      setError('Username and password are required.');
      return;
    }
    setLoading(true);
    try {
      await signIn(username.trim(), password, remember);
      navigate(next, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPassword('');
      setLoading(false);
    }
  }

  return (
    <AuthFrame>
      <form className="auth2-form" onSubmit={onSubmit} noValidate>
        <div className="auth2-head">
          <h1>Welcome back</h1>
          <p>Sign in to your account to open the dashboard.</p>
        </div>

        <label className="auth2-field">
          <span>Username</span>
          <span className="auth2-input">
            <UserRound size={16} aria-hidden />
            <input type="text" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
              placeholder="Your username" value={username}
              onChange={(e) => setUsername(e.target.value)} disabled={loading} autoFocus />
          </span>
        </label>

        <label className="auth2-field">
          <span>Password</span>
          <span className="auth2-input">
            <Lock size={16} aria-hidden />
            <input type={show ? 'text' : 'password'} name="password" autoComplete="current-password" placeholder="Your password"
              value={password} onChange={(e) => setPassword(e.target.value)} disabled={loading} />
            <button type="button" className="auth2-eye" onClick={() => setShow((s) => !s)}
              aria-label={show ? 'Hide the password' : 'Show the password'} title={show ? 'Hide' : 'Show'}>
              {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </span>
        </label>

        <div className="auth2-row">
          <label className="auth2-check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} disabled={loading} />
            Remember me
          </label>
          <button type="button" className="auth-link-btn"
            onClick={() => setInfo('Your password is the one of the MINEDUC GIS portal (gh.space.gov.rw/portal). Reset it there, or ask the portal administrator.')}>
            Forgot password?
          </button>
        </div>

        {error ? <p className="auth2-alert auth2-alert-error" role="alert">{error}</p> : null}
        {info ? <p className="auth2-alert auth2-alert-info" role="status">{info}</p> : null}

        <button type="submit" className="auth2-submit" disabled={loading}>
          {loading ? <><Loader2 size={16} className="auth2-spin" aria-hidden /> Signing in…</> : 'Sign in'}
        </button>

        <p className="auth2-foot">
          <Link to="/"><ArrowLeft size={14} aria-hidden /> Back to the home page</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

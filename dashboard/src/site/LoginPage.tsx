import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-react';
import { safeNext, useAuth } from '../auth';
import AuthFrame from './AuthFrame';

export default function LoginPage() {
  const { user, checking, signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const [email, setEmail] = useState('');
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
    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return;
    }
    setLoading(true);
    try {
      await signIn(email.trim(), password, remember);
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
          <span>Email</span>
          <span className="auth2-input">
            <Mail size={16} aria-hidden />
            <input type="email" name="email" autoComplete="email" placeholder="you@mineduc.gov.rw" value={email}
              onChange={(e) => setEmail(e.target.value)} disabled={loading} autoFocus />
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
            onClick={() => setInfo('Ask your administrator to set a new password for your account.')}>
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

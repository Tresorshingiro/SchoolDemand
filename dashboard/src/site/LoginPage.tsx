import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { safeNext, useAuth } from '../auth';
import { LogoMark } from './SiteChrome';

export default function LoginPage() {
  const { user, checking, signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
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
    <div className="auth-page">
      <form className="login-card" onSubmit={onSubmit} noValidate>
        <LogoMark size={56} />
        <h2>School Demand &amp; Demographics</h2>
        <p className="auth-subtitle">Sign in to access the School Demand &amp; Demographics platform.</p>

        <label>
          Email
          <input type="email" name="email" autoComplete="email" placeholder="Email" value={email}
            onChange={(e) => setEmail(e.target.value)} disabled={loading} autoFocus />
        </label>

        <label>
          Password
          <input type="password" name="password" autoComplete="current-password" placeholder="Password"
            value={password} onChange={(e) => setPassword(e.target.value)} disabled={loading} />
        </label>

        <div className="auth-row">
          <label className="auth-remember">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} disabled={loading} />
            Remember me
          </label>
          <button type="button" className="auth-link-btn"
            onClick={() => setInfo('Ask your administrator to set a new password for your account.')}>
            Forgot password?
          </button>
        </div>

        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        {info ? <p className="auth-subtitle" role="status">{info}</p> : null}

        <button type="submit" className="btn btn-cosmic login-btn" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign in'}
        </button>

        <p className="auth-back">
          <Link to="/">Back to landing page</Link>
        </p>
      </form>
    </div>
  );
}

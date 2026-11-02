/** Header and footer of the public pages (legal), and the logo. */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ThemeToggle } from '../theme';
import { portal } from './content';
import appIcon from './assets/app-icon.png';

export function LogoMark({ size = 48 }: { size?: number }) {
  return (
    <img className="logo-mark" src={appIcon} alt="" aria-hidden="true" width={size} height={size}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.33), objectFit: 'cover', display: 'block' }} />
  );
}

/** The dashboard is the site's home page (it signs the user in through the portal when needed). */
function DashboardLink({ className }: { className?: string }) {
  return <Link to="/" className={className}>Open dashboard</Link>;
}

export function SiteNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`lp-nav${scrolled ? ' is-solid' : ''}`}>
      <div className="lp-nav-inner">
        <Link to="/" className="lp-brand">
          <LogoMark size={32} />
          <span>{portal.name}</span>
        </Link>
        <div className="lp-nav-actions">
          <ThemeToggle className="lp-theme-btn" />
          <DashboardLink className="lp-nav-signin" />
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="lp-footer">
      <div className="lp-footer-inner">
        <div className="lp-footer-brand">
          <LogoMark size={36} />
          <h2>{portal.name}</h2>
          <p>
            Spatial intelligence for understanding education demand, accessibility, and future infrastructure needs.
          </p>
        </div>
        <div className="lp-footer-col">
          <h3>Dashboard</h3>
          <DashboardLink />
        </div>
      </div>
      <div className="lp-footer-base">
        <p>© 2026 School Demand &amp; Demographics</p>
        <nav aria-label="Legal">
          <Link to="/legal/privacy">Privacy</Link>
          <Link to="/legal/terms">Terms</Link>
          <Link to="/legal/disclaimer">Data Disclaimer</Link>
          <Link to="/legal/accessibility">Accessibility</Link>
        </nav>
      </div>
    </footer>
  );
}

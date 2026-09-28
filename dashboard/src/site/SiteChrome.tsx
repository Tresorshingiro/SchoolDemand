/** Header and footer of the public pages (landing, legal), and the logo. */
import { useEffect, useState, type MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { useAuth } from '../auth';
import { SECTIONS, portal } from './content';
import appIcon from './assets/app-icon.png';

export function LogoMark({ size = 48 }: { size?: number }) {
  return (
    <img className="logo-mark" src={appIcon} alt="" aria-hidden="true" width={size} height={size}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.33), objectFit: 'cover', display: 'block' }} />
  );
}

export function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** A landing-page section: scrolls on the landing page, opens the landing page elsewhere. */
function SectionLink({ id, label, onLanding, onDone }: { id: string; label: string; onLanding: boolean; onDone?: () => void }) {
  if (!onLanding) return <Link to={`/#${id}`} onClick={onDone}>{label}</Link>;
  const onClick = (e: MouseEvent) => {
    e.preventDefault();
    onDone?.();
    scrollToSection(id);
  };
  return <a href={`#${id}`} onClick={onClick}>{label}</a>;
}

/** Sign in, or open the dashboard when already signed in. */
function AccountLink({ className, onDone }: { className?: string; onDone?: () => void }) {
  const { user } = useAuth();
  return (
    <Link to={user ? '/dashboard' : '/login'} className={className} onClick={onDone}>
      {user ? 'Open dashboard' : 'Sign in'}
    </Link>
  );
}

export function SiteNav({ onLanding = false }: { onLanding?: boolean }) {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const close = () => setMenuOpen(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`lp-nav${scrolled ? ' is-solid' : ''}`}>
      <div className="lp-nav-inner">
        {onLanding ? (
          <a href="#overview" className="lp-brand" onClick={(e) => { e.preventDefault(); scrollToSection('overview'); }}>
            <LogoMark size={32} />
            <span>{portal.name}</span>
          </a>
        ) : (
          <Link to="/" className="lp-brand">
            <LogoMark size={32} />
            <span>{portal.name}</span>
          </Link>
        )}

        <nav className="lp-nav-links" aria-label="Landing">
          {SECTIONS.map((s) => <SectionLink key={s.id} {...s} onLanding={onLanding} />)}
        </nav>

        <div className="lp-nav-actions">
          <AccountLink className="lp-nav-signin" />
          <button type="button" className="lp-menu-btn" aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>
            {menuOpen ? <X size={18} strokeWidth={1.8} /> : <Menu size={18} strokeWidth={1.8} />}
          </button>
        </div>
      </div>

      {menuOpen ? (
        <div className="lp-nav-drawer">
          {SECTIONS.map((s) => <SectionLink key={s.id} {...s} onLanding={onLanding} onDone={close} />)}
          <AccountLink onDone={close} />
        </div>
      ) : null}
    </header>
  );
}

export function SiteFooter({ onLanding = false }: { onLanding?: boolean }) {
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
        <nav className="lp-footer-col" aria-label="Footer navigation">
          <h3>Navigation</h3>
          {SECTIONS.map((s) => <SectionLink key={s.id} {...s} onLanding={onLanding} />)}
        </nav>
        <div className="lp-footer-col">
          <h3>Account</h3>
          <AccountLink />
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

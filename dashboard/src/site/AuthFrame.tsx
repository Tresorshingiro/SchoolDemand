/**
 * The frame of the sign-in and password pages: a brand panel (Rwanda's districts, what the platform does) beside the
 * form. On phones the brand panel becomes a slim header.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Check } from 'lucide-react';
import { ThemeToggle } from '../theme';
import { LogoMark } from './SiteChrome';
import { DISTRICTS, DOTS, MAP_HEIGHT, MAP_WIDTH } from './rwandaMap';

const POINTS = [
  'Classrooms available and needed at every school and level',
  'Projection of the coming school years as cohorts move up',
  'Every district and sector, on the map and in the report',
];

export default function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="auth2">
      <aside className="auth2-brand">
        <Link to="/" className="auth2-logo">
          <LogoMark size={36} />
          <span>School Demand &amp; Demographics</span>
        </Link>
        <div className="auth2-copy">
          <h2>Plan classrooms where the children will be.</h2>
          <p>Enrolment, rooms and population in one place, for every school in Rwanda.</p>
          <ul className="auth2-points">
            {POINTS.map((p) => (
              <li key={p}><Check size={14} strokeWidth={3} aria-hidden />{p}</li>
            ))}
          </ul>
        </div>
        <p className="auth2-brand-foot">© {new Date().getFullYear()} School Demand &amp; Demographics</p>
        <svg className="auth2-map" viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} aria-hidden>
          {DISTRICTS.map((d) => <path key={d.name} d={d.d} />)}
          {DOTS.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={3} />)}
        </svg>
      </aside>
      <main className="auth2-main">
        <ThemeToggle className="lp-theme-btn auth2-theme" />
        {children}
      </main>
    </div>
  );
}

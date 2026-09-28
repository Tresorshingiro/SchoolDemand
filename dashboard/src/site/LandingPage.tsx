import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Activity, Map, MapPin, Target, type LucideIcon } from 'lucide-react';
import { useAuth } from '../auth';
import { landingDemo, portal } from './content';
import { SiteFooter, SiteNav, scrollToSection } from './SiteChrome';
import {
  CapacityIllustration, DemandIllustration, FutureIllustration, PopulationIllustration, demandColors,
} from './Illustrations';
import { useTheme } from '../theme';

const PLANNING_ICONS: Record<string, LucideIcon> = { 'map-pin': MapPin, target: Target, map: Map, activity: Activity };

function SectionHeader({ eyebrow, title, lead }: { eyebrow?: string; title: string; lead?: string }) {
  return (
    <header className="lp-section-header">
      {eyebrow ? <p className="lp-eyebrow">{eyebrow}</p> : null}
      <h2>{title}</h2>
      {lead ? <p className="lp-lead">{lead}</p> : null}
    </header>
  );
}

function ConceptList({ items }: { items: readonly { title: string; text: string }[] }) {
  return (
    <ul className="lp-concept-list">
      {items.map((row) => (
        <li key={row.title}>
          <strong>{row.title}</strong>
          <span>{row.text}</span>
        </li>
      ))}
    </ul>
  );
}

export default function LandingPage() {
  const { user } = useAuth();
  const { mode } = useTheme();
  const { hash } = useLocation();
  const [year, setYear] = useState(landingDemo.projectionYears[0]);

  // Arriving from another page with a section in the address (/#planning): go to it
  useEffect(() => {
    if (hash) scrollToSection(hash.slice(1));
  }, [hash]);

  return (
    <div className="lp">
      <SiteNav onLanding />

      <main>
        <section className="lp-hero" id="overview">
          <div className="lp-hero-copy">
            <p className="lp-eyebrow">School Demand &amp; Demographics</p>
            <h1>Understanding where education demand is changing.</h1>
            <p className="lp-lead">
              Explore population patterns, education capacity, accessibility, and future demand
              through one geographic view.
            </p>
            <div className="lp-hero-actions">
              <Link to="/dashboard" className="btn btn-cosmic">
                View National Overview
              </Link>
              {!user && (
                <Link to="/login" className="btn btn-ghost">
                  Sign in
                </Link>
              )}
            </div>
          </div>

          <div className="lp-hero-visual" aria-label="Geographic overview visual">
            <img src={portal.hero} alt="" />
            <div className="lp-hero-shade" />
            <div className="lp-map-frame" aria-hidden="true">
              <div className="lp-map-grid" />
              <span className="lp-map-dot lp-map-dot--a" />
              <span className="lp-map-dot lp-map-dot--b" />
              <span className="lp-map-dot lp-map-dot--c" />
            </div>
            <ul className="lp-hero-indicators">
              {landingDemo.heroIndicators.map((item) => (
                <li key={item.title}>
                  <span className="lp-indicator-value">{item.title}</span>
                  <span className="lp-indicator-label">{item.text}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-section" id="demographics">
          <SectionHeader
            eyebrow="01 — Population"
            title="Who needs education?"
            lead="Population distribution and age structure provide the foundation for understanding education demand."
          />
          <div className="lp-split">
            <div className="lp-viz-card lp-viz-card--map">
              <p className="lp-viz-kicker">Demographic map</p>
              <div className="lp-geo-panel">
                <div className="lp-geo-wash" />
                <PopulationIllustration />
                <p>Conceptual view of population and age structure across administrative areas</p>
              </div>
            </div>
            <aside className="lp-panel">
              <h3>Demographic snapshot</h3>
              <ConceptList items={landingDemo.demographicSnapshot} />
              <div className="lp-mini-chart" aria-hidden="true">
                <span style={{ height: '42%' }} />
                <span style={{ height: '68%' }} />
                <span style={{ height: '54%' }} />
                <span style={{ height: '76%' }} />
                <span style={{ height: '48%' }} />
              </div>
              <p className="lp-caption">Age structure — conceptual view</p>
            </aside>
          </div>
          <figure className="lp-image-moment">
            <img src={portal.hero} alt="" />
            <figcaption>
              <h3>Demand begins with people.</h3>
              <p>Understanding who needs education starts with where learners live and grow.</p>
            </figcaption>
          </figure>
        </section>

        <section className="lp-section" id="capacity">
          <SectionHeader
            eyebrow="02 — Capacity & Accessibility"
            title="Can existing infrastructure serve the population?"
            lead="Understanding education demand requires looking at both available capacity and how easily communities can reach schools."
          />
          <div className="lp-split">
            <div className="lp-viz-card lp-viz-card--map">
              <p className="lp-viz-kicker">Schools · capacity · access</p>
              <div className="lp-geo-panel lp-geo-panel--capacity">
                <div className="lp-geo-wash" />
                <CapacityIllustration />
                <p>School locations, service areas, and how communities reach education</p>
              </div>
            </div>
            <aside className="lp-panel">
              <h3>Service picture</h3>
              <ConceptList items={landingDemo.capacityPanel} />
            </aside>
          </div>
          <div className="lp-compare">
            <div>
              <p className="lp-eyebrow">Population need</p>
              <div className="lp-compare-bar lp-compare-bar--need" />
            </div>
            <p className="lp-compare-vs">vs</p>
            <div>
              <p className="lp-eyebrow">Available capacity</p>
              <div className="lp-compare-bar lp-compare-bar--capacity" />
            </div>
          </div>
        </section>

        <section className="lp-section" id="demand">
          <SectionHeader
            eyebrow="03 — Demand"
            title="Where are the largest gaps?"
            lead="Combine population, capacity, and accessibility to identify areas where education demand may exceed available provision."
          />
          <div className="lp-split lp-split--demand">
            <div className="lp-viz-card lp-viz-card--map lp-viz-card--demand">
              <p className="lp-viz-kicker">Demand map</p>
              <div className="lp-geo-panel lp-geo-panel--demand">
                <div className="lp-geo-wash" />
                <DemandIllustration />
                <div className="lp-demand-legend">
                  {landingDemo.demandLevels.map((level, i) => (
                    <span key={level}><i style={{ background: demandColors(mode)[i] }} aria-hidden="true" />{level}</span>
                  ))}
                </div>
              </div>
              <p className="lp-flow-line">Population × Capacity × Accessibility → Demand</p>
            </div>
            <aside className="lp-panel">
              <h3>Demand factors</h3>
              <ConceptList items={landingDemo.demandPanel} />
              <div className="lp-gap-steps">
                <span>Population need</span>
                <span>Available capacity</span>
                <span>Capacity gap</span>
                <span>Demand pressure</span>
              </div>
            </aside>
          </div>
        </section>

        <section className="lp-section" id="future">
          <SectionHeader
            eyebrow="04 — Future Demand"
            title="Planning for tomorrow's learners."
            lead="Population change can reshape education needs over time."
          />
          <div className="lp-split">
            <div className="lp-viz-card">
              <div className="lp-year-tabs" role="tablist" aria-label="Projection year">
                {landingDemo.projectionYears.map((y) => (
                  <button key={y} type="button" role="tab" aria-selected={year === y}
                    className={year === y ? 'is-active' : undefined} onClick={() => setYear(y)}>
                    {y}
                  </button>
                ))}
              </div>
              <FutureIllustration years={landingDemo.projectionYears} year={year} />
              <div className="lp-projection-key">
                <span><i style={{ background: 'var(--available)' }} aria-hidden="true" />Current capacity</span>
                <span><i style={{ background: 'var(--required)' }} aria-hidden="true" />Projected demand</span>
                <span><i style={{ background: 'var(--deficit)', opacity: 0.35 }} aria-hidden="true" />Shortage</span>
              </div>
            </div>
            <figure className="lp-image-moment lp-image-moment--side">
              <img src={portal.hero} alt="" />
              <figcaption>
                <h3>Plan with changing needs in view.</h3>
                <p>Timeline: 2026 → 2030 → 2035 → 2040</p>
              </figcaption>
            </figure>
          </div>
        </section>

        <section className="lp-section" id="planning">
          <SectionHeader eyebrow="05 — Planning" title="From geographic insight to better planning." />
          <div className="lp-plan-grid">
            {landingDemo.planningCards.map((card) => {
              const Icon = PLANNING_ICONS[card.icon] ?? MapPin;
              return (
                <article key={card.title} className="lp-plan-card">
                  <span className="lp-plan-icon" aria-hidden="true">
                    <Icon size={18} strokeWidth={1.6} />
                  </span>
                  <h3>{card.title}</h3>
                  <p>{card.text}</p>
                </article>
              );
            })}
          </div>
        </section>

        <section className="lp-section lp-section--method" id="methodology">
          <SectionHeader title="How the analysis works" />
          <div className="lp-method-flow">
            {landingDemo.methodologySteps.map((step, index) => (
              <div key={step} className="lp-method-step">
                <span>{step}</span>
                {index < landingDemo.methodologySteps.length - 1 ? (
                  <span className="lp-method-arrow" aria-hidden="true">→</span>
                ) : null}
              </div>
            ))}
          </div>
          <p className="lp-lead lp-lead--center">
            The platform combines demographic, school, capacity, accessibility, and population trend
            data to provide a geographic view of education demand.
          </p>
          <p className="lp-signin-hint">
            Access detailed demographic, capacity, accessibility, and demand analysis after signing in.
          </p>
        </section>

        <section className="lp-final-cta" id="cta">
          <h2>Understand where education demand is changing.</h2>
          <p>
            Explore demographic patterns, capacity, accessibility, and future demand through a
            geographic view of education needs.
          </p>
          <Link to="/dashboard" className="btn btn-cosmic">
            {user ? 'Open the dashboard' : 'Sign in to explore'}
          </Link>
        </section>
      </main>

      <SiteFooter onLanding />
    </div>
  );
}

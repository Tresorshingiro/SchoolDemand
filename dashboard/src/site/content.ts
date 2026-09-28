/**
 * Copy of the public pages (landing, sign-in, legal) — from the School Demand & Demographics site.
 * Capability descriptions, not analytical results or official statistics.
 */
import hero from './assets/hero.jpg';

export const portal = {
  name: 'School Demand & Demographics',
  hero,
};

export const landingDemo = {
  heroIndicators: [
    { title: 'Population Trends', text: 'Explore demographic change over time' },
    { title: 'School Distribution', text: 'Explore school locations geographically' },
    { title: 'Demand Analysis', text: 'Identify areas where demand may exceed provision' },
  ],
  demographicSnapshot: [
    { title: 'School-age population', text: 'Understand who needs education and where learners live.' },
    { title: 'Population density', text: 'See how settlement patterns shape education need.' },
    { title: 'Population trends', text: 'Explore demographic change over time.' },
  ],
  capacityPanel: [
    { title: 'Available capacity', text: 'Review how existing schools can serve communities.' },
    { title: 'Students served', text: 'See how provision relates to local population.' },
    { title: 'Accessibility', text: 'Understand how communities reach education services.' },
    { title: 'Service coverage', text: 'Identify places that may sit outside convenient access.' },
  ],
  demandPanel: [
    { title: 'Population', text: 'Who needs education in each area.' },
    { title: 'Capacity', text: 'Whether existing provision can meet that need.' },
    { title: 'Accessibility', text: 'How easily communities can reach schools.' },
    { title: 'Demand', text: 'Where need may exceed available provision.' },
  ],
  demandLevels: ['Low', 'Moderate', 'High', 'Very High'],
  projectionYears: [2026, 2030, 2035, 2040],
  planningCards: [
    { title: 'Identify', text: 'Find areas where demand is concentrated.', icon: 'map-pin' },
    { title: 'Prioritize', text: 'Understand capacity and accessibility gaps.', icon: 'target' },
    { title: 'Plan', text: 'Support evidence-based infrastructure planning.', icon: 'map' },
    { title: 'Monitor', text: 'Track changing population and education needs.', icon: 'activity' },
  ],
  methodologySteps: ['Population', 'Capacity', 'Accessibility', 'Demand', 'Future Demand'],
};

/** Sections of the landing page (header and footer links). */
export const SECTIONS = [
  { label: 'Overview', id: 'overview' },
  { label: 'Demographics', id: 'demographics' },
  { label: 'Demand', id: 'demand' },
  { label: 'Planning', id: 'planning' },
  { label: 'Methodology', id: 'methodology' },
];

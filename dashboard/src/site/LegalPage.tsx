import { Link, Navigate, useParams } from 'react-router-dom';
import { SiteFooter, SiteNav } from './SiteChrome';

const PAGES: Record<string, { title: string; paragraphs: string[] }> = {
  disclaimer: {
    title: 'Data Disclaimer',
    paragraphs: [
      'Mapping applications and related geospatial data are provided as-is for planning and operational use. Completeness, accuracy, and currency may vary by source and refresh cycle.',
      'Users should verify critical decisions against authoritative records. Rwanda Space Agency and contributing institutions are not liable for decisions made solely on the basis of these maps.',
    ],
  },
  privacy: {
    title: 'Privacy',
    paragraphs: [
      'Accounts are created by an administrator. Signing in uses your email address and a password; the password is stored only as a one-way hash, never in readable form.',
      'After you sign in, a session cookie keeps you signed in: until you close the browser, or for up to 30 days when you tick "Remember me". Signing out ends the session. The platform records when you last signed in and the name on intake plans you save.',
      'The map loads basemap tiles from ArcGIS / OpenStreetMap services, which see the map area requested but not your account.',
    ],
  },
  terms: {
    title: 'Terms of Use',
    paragraphs: [
      'Use this workspace only for lawful, authorized purposes related to school demand, demographics, and institutional mandates in Rwanda.',
      'Do not attempt to bypass access controls, scrape protected services, or redistribute proprietary content without permission. Keep your password to yourself; each person uses their own account.',
    ],
  },
  accessibility: {
    title: 'Accessibility',
    paragraphs: [
      'This portal supports keyboard navigation for its pages, tables and controls. The map inherits accessibility features from ArcGIS.',
      'If you encounter a barrier, contact your administrator so the issue can be routed to the application owner.',
    ],
  },
};

export default function LegalPage() {
  const { page } = useParams();
  const article = page ? PAGES[page] : undefined;
  if (!article) return <Navigate to="/" replace />;

  return (
    <>
      <SiteNav />
      <main className="site-main legal-page">
        <div className="legal-canvas">
          <nav className="crumbs">
            <Link to="/">Home</Link>
            <span>/</span>
            <strong>{article.title}</strong>
          </nav>
          <h1>{article.title}</h1>
          {article.paragraphs.map((text) => (
            <p key={text}>{text}</p>
          ))}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}

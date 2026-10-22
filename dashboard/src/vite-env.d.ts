/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional ArcGIS API key — not needed for the grey canvas basemap. */
  readonly VITE_ARCGIS_TOKEN?: string;
  /** MINEDUC GIS portal (default https://gh.space.gov.rw/portal): its sign-in is used on its own site. */
  readonly VITE_PORTAL_URL?: string;
  /** Client ID of the dashboard's application item in that portal (single sign-on). */
  readonly VITE_PORTAL_CLIENT_ID?: string;
}

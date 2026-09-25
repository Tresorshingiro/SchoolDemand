/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional ArcGIS API key — not needed for the grey canvas basemap. */
  readonly VITE_ARCGIS_TOKEN?: string;
}

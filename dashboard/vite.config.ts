import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The site lives under /school/ (http://localhost:5173/school/ in development, https://server/school/ in production):
// the pages, their files and the API (<base>/api) all live under it. For another sub-path, or the root of a site,
// build with VITE_BASE (e.g. VITE_BASE=/ for the root).
// Development: <base>api and /api are forwarded to the FastAPI backend (uvicorn on port 8000, see backend/README.md).
const base = process.env.VITE_BASE ?? '/school/';
const api = { target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true };

export default defineConfig({
  base,
  plugins: [react()],
  build: { chunkSizeWarningLimit: 4000 },
  server: {
    proxy: {
      // <base>api/... -> the API's /api/...
      ...(base === '/' ? {} : { [`${base}api`]: { ...api, rewrite: (path: string) => path.slice(base.length - 1) } }),
      '/api': api, // a build with VITE_API_URL=/api (as on gis.mineduc.gov.rw)
    },
  },
});

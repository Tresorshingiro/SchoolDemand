import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The site lives under /school-demand/ (http://localhost:5173/school-demand/). For another sub-path, or the root of
// its address, build with VITE_BASE=/other/ or VITE_BASE=/ — the pages, their files and the API (<base>/api) then all
// live under it.
// Development: <base>/api is forwarded to the FastAPI backend's /api (uvicorn on port 8000, see backend/README.md).
const base = process.env.VITE_BASE ?? '/school-demand/';

export default defineConfig({
  base,
  plugins: [react()],
  build: { chunkSizeWarningLimit: 4000 },
  server: {
    port: 5173,
    proxy: {
      [`${base}api`]: {
        target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(base.replace(/\/$/, ''), ''),
      },
    },
  },
});

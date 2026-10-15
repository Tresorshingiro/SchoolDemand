import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The site is served from the root of its address by default. Under a sub-path (e.g. https://server/school/) build
// with VITE_BASE=/school/ — the pages, their files and the API (<base>/api) then all live under it.
// Development: /api is forwarded to the FastAPI backend (uvicorn on port 8000, see backend/README.md).
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  build: { chunkSizeWarningLimit: 4000 },
  server: {
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});

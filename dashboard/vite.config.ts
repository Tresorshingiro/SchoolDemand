import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' so the built dist/ folder can be served from any path.
// Development: /api is forwarded to the FastAPI backend (uvicorn on port 8000, see backend/README.md).
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { chunkSizeWarningLimit: 4000 },
  server: {
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});

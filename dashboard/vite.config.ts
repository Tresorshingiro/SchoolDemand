import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' so the built dist/ folder can be served from any path or opened from a file share.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { chunkSizeWarningLimit: 4000 },
});

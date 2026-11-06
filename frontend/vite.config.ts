import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // Inside Docker Compose the backend is reachable as http://backend:8000.
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

  return {
    plugins: [react(), tailwindcss()],
    build: {
      // The map chunk is ~1.1 MB because MapLibre itself is; it's already split out of the main
      // bundle and loaded lazily, so the default 500 kB warning isn't actionable.
      chunkSizeWarningLimit: 1200,
    },
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
      },
    },
  };
});

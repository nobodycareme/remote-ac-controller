import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Relative base so the built SPA can be served from any sub-path.
export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3100',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

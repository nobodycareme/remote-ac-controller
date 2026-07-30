import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { execSync } from 'node:child_process';

// Resolve the current git commit at build time (best-effort, never fails the build).
function safeGitCommit(): string {
  try {
    return execSync('git rev-parse HEAD', { cwd: __dirname, encoding: 'utf-8' }).trim();
  } catch {
    return 'unknown';
  }
}

const GIT_COMMIT = safeGitCommit();
const BUILD_TS = new Date().toISOString();
const BUILD_ID = `${GIT_COMMIT.slice(0, 12)}-${BUILD_TS}`;

// Relative base so the built SPA can be served from any sub-path.
export default defineConfig({
  base: './',
  plugins: [vue()],
  define: {
    __APP_BUILD_ID__: JSON.stringify(BUILD_ID),
    __APP_GIT_COMMIT__: JSON.stringify(GIT_COMMIT),
    __APP_BUILD_TS__: JSON.stringify(BUILD_TS),
  },
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

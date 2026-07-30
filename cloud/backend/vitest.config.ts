import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

// Alias `node:sqlite` to a native .cjs shim so vite never tries to transform the
// builtin (it would otherwise strip the `node:` prefix and fail to resolve `sqlite`).
// The shim does `require('node:sqlite')`, which Node resolves natively. This keeps a
// single shared db module instance across test files and lets them import from src/.
const sqliteShim = fileURLToPath(new URL('./tests/_sqlite_stub.cjs', import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      'node:sqlite': sqliteShim,
    },
  },
  test: {
    environment: 'node',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.ts'],
  },
});

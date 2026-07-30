import { defineConfig } from 'vitest/config';

// 仅测试纯逻辑层（src/lib），node 环境即可，无需 DOM。
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});

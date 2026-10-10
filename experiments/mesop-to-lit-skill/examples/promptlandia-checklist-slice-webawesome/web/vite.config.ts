import { defineConfig } from 'vite';

// Single-service target (target-architecture §7): build into ../web/dist, which
// FastAPI's StaticFiles mount serves. Dev proxies /api -> the uvicorn backend.
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['test/**/*.test.ts'],
  },
});

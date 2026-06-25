import { defineConfig } from 'vite';

// SkyForge dev/build config. Base is relative so the built bundle works
// from any path (e.g. opened from a file server or a packaged .app).
export default defineConfig({
  base: './',
  server: {
    host: true,
    port: 5173,
  },
  build: {
    target: 'es2020',
    outDir: 'dist',
    assetsInlineLimit: 0,
  },
});

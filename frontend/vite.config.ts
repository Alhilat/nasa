import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';
import type { ProxyOptions } from 'vite';

const tileProxy = (service: string, prefix: string): ProxyOptions => ({
  target: 'https://services.arcgisonline.com',
  changeOrigin: true,
  secure: true,
  proxyTimeout: 15000,
  timeout: 15000,
  rewrite: (path: string) => path.replace(prefix, `/ArcGIS/rest/services/${service}/MapServer/tile`),
  configure(proxy) {
    proxy.on('proxyReq', request => {
      request.removeHeader('cookie');
      request.removeHeader('authorization');
    });
  },
});

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: '..',
  server: { proxy: {
    '/api': process.env.FIRESCOPE_API_TARGET ?? 'http://127.0.0.1:8000',
    '^/basemap/imagery/[0-9]+/[0-9]+/[0-9]+$': tileProxy('World_Imagery', '/basemap/imagery'),
    '^/basemap/reference/[0-9]+/[0-9]+/[0-9]+$': tileProxy('Reference/World_Boundaries_and_Places', '/basemap/reference'),
  } },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], restoreMocks: true },
  build: {
    rollupOptions: {
      output: {
        manualChunks: { map: ['maplibre-gl'], charts: ['echarts'], react: ['react', 'react-dom'] },
      },
    },
  },
});

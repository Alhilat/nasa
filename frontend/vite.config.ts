import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: '..',
  server: { proxy: { '/api': process.env.FIRESCOPE_API_TARGET ?? 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], restoreMocks: true },
  build: {
    rollupOptions: {
      output: {
        manualChunks: { map: ['maplibre-gl'], charts: ['echarts'], react: ['react', 'react-dom'] },
      },
    },
  },
});

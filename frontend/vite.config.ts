import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: '..',
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], restoreMocks: true },
  build: {
    rollupOptions: {
      output: {
        manualChunks: { map: ['maplibre-gl'], charts: ['echarts'], react: ['react', 'react-dom'] },
      },
    },
  },
});

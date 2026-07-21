import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const deployWorkRoot = process.env.QWQ_DEPLOY_WORK_ROOT;
const deployTarget = process.env.QWQ_DEPLOY_TARGET || 'prod-hosted';

if (!deployWorkRoot) {
  throw new Error('QWQ_DEPLOY_WORK_ROOT is required for portal deployment builds');
}

const outputDir = path.resolve(deployWorkRoot, deployTarget, 'build', 'ops-portal');

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 4173,
  },
  build: {
    outDir: outputDir,
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          icons: ['lucide-react'],
        },
      },
    },
  },
});

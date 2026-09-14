import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const directory = path.dirname(fileURLToPath(import.meta.url));
const opsPortal = path.resolve(directory, '../../quwoquan_ops/portal');

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@ops-ui': path.resolve(opsPortal, 'src/shared/ui/index.ts'),
      '@ops-styles': path.resolve(opsPortal, 'src/styles.css'),
    },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host: '127.0.0.1',
    fs: { allow: [directory, opsPortal] },
  },
  preview: { host: '127.0.0.1' },
});

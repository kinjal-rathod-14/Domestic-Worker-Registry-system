import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    allowedHosts: [
      'eligibility-exists-monetary-mitchell.trycloudflare.com',
      'localhost',
      '.trycloudflare.com'
    ]
  }
});

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  // Deployed under www.enochmgmt.com/investapp/, not the domain root -- dev
  // server and tests still run at "/" (unaffected), only `vite build` needs
  // this so asset URLs and import.meta.env.BASE_URL resolve correctly.
  base: command === 'build' ? '/investapp/' : '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:5001',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    exclude: ['**/node_modules/**', 'e2e/**'],
  },
}))

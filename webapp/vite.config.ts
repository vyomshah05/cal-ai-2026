import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // GitHub Pages serves project sites at https://<user>.github.io/<repo>/,
  // so assets must be referenced relative to that subpath in production.
  base: process.env.GH_PAGES === 'true' ? '/cal-ai-2026/' : '/',
})

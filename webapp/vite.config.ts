import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // GitHub Pages serves project sites at https://<user>.github.io/<repo>/,
  // so assets must be referenced relative to that subpath in production.
  // VITE_GH_PAGES_BASE is injected by the deploy workflow from the live repo
  // name so a future repo rename can't silently break asset paths again.
  base: process.env.GH_PAGES === 'true' ? (process.env.VITE_GH_PAGES_BASE || '/lockstep/') : '/',
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Dev-only: the Vite dev server proxies /api to a locally-running backend.
    // Production serves the committed dist/ from FastAPI on the same origin
    // (reached via the public Tailscale Funnel) — no absolute URLs anywhere.
    proxy: {
      '/api': 'http://localhost:8787',
    },
  },
})

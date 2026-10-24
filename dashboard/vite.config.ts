import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server forwards /api, /media and /ws to the FastAPI backend on port 8000,
// so the dashboard code can use relative URLs like "/api/frames" (no CORS problems).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})

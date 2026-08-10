import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Base path must match the route the SPA is served from.
  // Without this, Vite emits absolute paths like /assets/... which 404
  // because the gateway serves assets at /app/assets/...
  base: '/app/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
  },
})

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../../api/www'  // 2026-06-11 改: 之前是 '../api/www' 错 (写到了 app/api/www/)
  },
  server: {
    host: '0.0.0.0',
    port: 35173,
    proxy: {
      // Default to the local FastAPI port used in this repo.
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:5100',
        changeOrigin: true,
        secure: false,
        timeout: 600000
      },
      '/ws': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:5100',
        ws: true,
        changeOrigin: true,
        secure: false
      }
    }
  }
})

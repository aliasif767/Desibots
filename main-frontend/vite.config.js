import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // All API requests go through the main backend
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // No more /proxy — Streamlit iframes are gone!
    }
  }
})

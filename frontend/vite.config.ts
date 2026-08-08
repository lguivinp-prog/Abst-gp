import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/auth': {
        target: process.env.VITE_API_URL || 'http://backend-app:8000',
        changeOrigin: true,
      },
      '/cases': {
        target: process.env.VITE_API_URL || 'http://backend-app:8000',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/auth': {
        target: process.env.VITE_API_URL || 'http://backend-app:8000',
        changeOrigin: true,
      },
      '/cases': {
        target: process.env.VITE_API_URL || 'http://backend-app:8000',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      }
    }
  }
})

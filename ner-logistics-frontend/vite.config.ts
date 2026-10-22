import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/roads': 'http://localhost:8000',
      '/bridges': 'http://localhost:8000',
      '/weather': 'http://localhost:8000',
      '/incidents': 'http://localhost:8000',
      '/vehicles': 'http://localhost:8000',
      '/risk': 'http://localhost:8000',
      '/alerts': 'http://localhost:8000',
      '/districts': 'http://localhost:8000',
      '/routes': 'http://localhost:8000',
      '/routing': 'http://localhost:8000',
      '/docs': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})


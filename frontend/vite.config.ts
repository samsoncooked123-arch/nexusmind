import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    proxy: { '/api': { target: 'http://localhost:8000', rewrite: path => path.replace(/^\/api/, '') } },
  },
})

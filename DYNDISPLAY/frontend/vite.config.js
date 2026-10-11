import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
      // Regex obligatoire ('^/media/') et non '/media' : la clé littérale
      // attrapait aussi la route SPA « Médiathèque » (/media), qui était
      // donc proxyfiee vers FastAPI au lieu de servir index.html -> 404.
      '^/media/': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
    },
  },
})

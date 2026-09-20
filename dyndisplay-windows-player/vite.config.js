import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Le player charge son contenu depuis le cache local via le protocole
// custom `dyndisplay-media://` (enregistré par electron/main.js). On fixe
// une base relative pour que le build fonctionne aussi en chargement
// file:// (production).
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    // 5174 pour cohabiter avec le dev server du frontend web (5173).
    port: 5174,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    emptyOutDir: true,
  },
})
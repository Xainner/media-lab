import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  root: __dirname,
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') }, dedupe: ['react', 'react-dom'] },
  server: { host: '127.0.0.1', port: 5374, proxy: { '/v1': { target: process.env.RVL_API_URL || 'http://127.0.0.1:8390', changeOrigin: false } } },
  build: { outDir: 'dist', emptyOutDir: true, sourcemap: false, rollupOptions: {output: {manualChunks(id) {if(id.includes("node_modules") && /[\\/]motion[\\/]|[\\/]framer-motion[\\/]/.test(id)) return "motion"; if(id.includes("node_modules") && /[\\/]@radix-ui[\\/]|[\\/]radix-ui[\\/]|[\\/]@floating-ui[\\/]/.test(id)) return "interaction"}}} },
})

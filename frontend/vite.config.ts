import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 18437,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18438',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})

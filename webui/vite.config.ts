import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  base: '/', // 确保在生产环境中，静态资源的路径是相对于根目录的
  plugins: [
    vue(),
    vueJsx(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001', // Flask 后端地址
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, ''), // 如果后端 API 没有 /api 前缀，则需要重写
      },
    },
  },
})

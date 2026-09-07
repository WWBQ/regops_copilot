import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // Quality 走 Python，避免 java-service 未热加载新代理时页面一直 pending。
      // Java BFF 仍实现 /api/ops/quality/*；重启 java 后也可改回只走 8080。
      '/api/ops/quality': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
      // RestClient 会把 SSE 攒完再转发；开发时直连 Python 才能看见逐字。
      '/api/chat/stream': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 180_000,
        proxyTimeout: 180_000,
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        timeout: 180_000,
        proxyTimeout: 180_000,
      },
    },
  },
})

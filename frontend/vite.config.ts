import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 35173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:38000',
        changeOrigin: false,
      },
    },
  },
  test: { environment: 'jsdom' },
})

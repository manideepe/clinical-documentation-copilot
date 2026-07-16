import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
        configure(proxy) {
          const proxyWithRequestEvents = proxy as unknown as {
            on(
              event: 'proxyReq',
              listener: (request: { setHeader(name: string, value: string): void }) => void,
            ): void
          }

          proxyWithRequestEvents.on('proxyReq', (proxyRequest) => {
            proxyRequest.setHeader('X-Internal-Auth', 'local-development-gateway')
            proxyRequest.setHeader('X-User-ID', 'local-browser-user')
            proxyRequest.setHeader('X-Role', 'CLINICAL_SUPERVISOR')
            proxyRequest.setHeader(
              'X-Session-Expires-At',
              new Date(Date.now() + 60 * 60 * 1000).toISOString(),
            )
          })
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    globals: true,
  },
})

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// One edition only: the page at gesture.roycarlous.com. Nothing here talks to a server; the hand
// landmarker runs in the browser and the relay side is a model of the controller and the firmware.
export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2022',
    sourcemap: false,
  },
  server: {
    port: 5173,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}', 'test/**/*.test.js'],
    setupFiles: ['./vitest.setup.ts'],
  },
})

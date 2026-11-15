import { alphaTab } from '@coderline/alphatab-vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// alphaTab's plugin copies its music font + SoundFont into the build and wires up
// the audio worker/worklet. API calls are proxied to the FastAPI backend in dev.
export default defineConfig({
  plugins: [react(), alphaTab()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})

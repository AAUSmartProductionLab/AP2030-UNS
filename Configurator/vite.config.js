import { defineConfig, searchForWorkspaceRoot } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // This is the key setting that allows refresh to work with React Router
    historyApiFallback: true,
    fs: {
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        resolve(__dirname, '..')
      ]
    }
  }
})
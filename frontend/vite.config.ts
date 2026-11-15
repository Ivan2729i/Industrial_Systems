import { defineConfig, loadEnv } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxy = { '/api': { target: env.DJANGO_URL || 'http://127.0.0.1:8000' } }
  return {
    plugins: [
      tailwindcss(),
      viteStaticCopy({ targets: ['Cesium.js', 'Assets', 'Widgets', 'ThirdParty', 'Workers'].map(directory => ({
        src: 'node_modules/cesium/Build/Cesium/' + directory, dest: 'cesium'
      })) }),
    ],
    server: { proxy },
    preview: { proxy },
  }
})

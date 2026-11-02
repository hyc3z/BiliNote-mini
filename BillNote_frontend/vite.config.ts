import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,fileURLToPath(new URL('../',import.meta.url)))
  return {plugins:[react(),tailwindcss()],resolve:{alias:{'@':fileURLToPath(new URL('./src',import.meta.url))}},server:{host:'127.0.0.1',port:Number(env.VITE_FRONTEND_PORT||3015),proxy:{'/api':{target:env.VITE_API_BASE_URL||'http://127.0.0.1:8483',changeOrigin:true}}}}
})

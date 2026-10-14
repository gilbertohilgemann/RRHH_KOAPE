import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Puerto propio (no el 5173 por defecto de Vite) para no chocar con otras
// aplicaciones; strictPort: si está ocupado, falla en vez de tomar otro solo.
const PUERTO = 5204

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    // Escucha en toda la red (no solo localhost) y acepta pedidos con
    // cualquier Host (IP de la red local, etc.) — así se puede probar desde
    // el celular sin pasar --host a mano ni tocar configuración cada vez que
    // cambia la IP.
    host: true,
    allowedHosts: true,
    port: PUERTO,
    strictPort: true,
  },
  preview: {
    port: PUERTO,
    strictPort: true,
  },
})

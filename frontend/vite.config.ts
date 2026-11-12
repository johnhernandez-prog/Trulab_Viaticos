/// <reference types="vitest/config" />
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// La SPA llama a la API en la misma origen (`/api/v1`): en desarrollo Vite reenvía `/api` al
// backend. Así no hace falta CORS en local y la cookie de refresh (S1-08) es de primera parte.
// En Docker el destino es el servicio `api`; fuera de Docker, la API publicada en localhost.
const destinoApi = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: destinoApi, xfwd: true },
    },
    // Los volúmenes montados desde Windows no emiten eventos de archivos (ver docker-compose).
    watch: process.env.CHOKIDAR_USEPOLLING === "true" ? { usePolling: true, interval: 300 } : {},
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
    unstubGlobals: true,
  },
});

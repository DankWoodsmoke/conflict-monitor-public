import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import cesium from "vite-plugin-cesium";

export default defineConfig({
  worker: { format: "es" },
  build: { target: "esnext" },
  plugins: [react(), cesium()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    allowedHosts: ["localhost"],
    // Polling required for Docker volumes on Windows (WSL2 inotify doesn't propagate)
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      // Preserve the page host so the backend can verify same-origin WebSockets,
      // exactly as the production nginx proxy does. Do not rewrite Origin.
      "/api": { target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8000", changeOrigin: false, ws: true, rewrite: path => path.replace(/^\/api/, "") },
      // Proxy adsb.lol V2 API to avoid CORS issues
      "/adsb-api": {
        target: "https://api.adsb.lol",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/adsb-api/, ""),
        secure: true,
      },
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_MODE__: JSON.stringify("agent"),
  },
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
      "/agent-api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/agent-api/, "/api/agent"),
      },
      "/agent-ws": {
        target: "ws://127.0.0.1:8001",
        ws: true,
        rewrite: (path) => path.replace(/^\/agent-ws/, "/ws/agent"),
      },
    },
  },
});

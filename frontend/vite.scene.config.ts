import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const port = Number(process.env.QR_PORT || 5173);
const backendOrigin = process.env.QR_BACKEND_ORIGIN || "http://127.0.0.1:8000";
const backendWsOrigin = backendOrigin.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_MODE__: JSON.stringify("scene"),
  },
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: {
      "/api": backendOrigin,
      "/ws": { target: backendWsOrigin, ws: true },
    },
  },
});

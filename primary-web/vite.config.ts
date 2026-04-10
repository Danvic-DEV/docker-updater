import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const allowedHostsEnv = process.env.VITE_ALLOWED_HOSTS?.trim();
const allowedHosts = allowedHostsEnv
  ? allowedHostsEnv.split(",").map((host) => host.trim()).filter(Boolean)
  : true;

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts,
    proxy: {
      "/admin-api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/admin-api/, ""),
      },
    },
  },
});

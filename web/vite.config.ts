import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The server address comes from `calflab lab --dev` (CALFLAB_API).
const api = process.env.CALFLAB_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // The work directory may reach `src/` through a junction (ADR-003): keep
    // module paths inside the work directory so node_modules resolve.
    preserveSymlinks: true,
    alias: { "@": path.resolve(process.cwd(), "src") },
  },
  server: {
    host: "127.0.0.1",
    watch: { usePolling: true, interval: 300 },
    proxy: {
      "/api": { target: api, changeOrigin: true },
      "/hops": { target: api, changeOrigin: true },
      "/ws": { target: api.replace("http", "ws"), ws: true },
    },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 2500 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});

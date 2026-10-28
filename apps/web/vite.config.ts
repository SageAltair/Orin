import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { watch: { usePolling: process.env.VITE_USE_POLLING === "true", interval: 250 }, proxy: { "/api": { target: "http://127.0.0.1:8100", changeOrigin: true } } },
  test: { exclude: ["e2e/**", "node_modules/**"] },
});

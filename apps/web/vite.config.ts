import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { watch: { usePolling: process.env.VITE_USE_POLLING === "true", interval: 250 } },
  test: { exclude: ["e2e/**", "node_modules/**"] },
});

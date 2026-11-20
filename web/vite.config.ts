import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FastAPI serves ../frontend: index.html at "/" and the files under "/assets".
// Keep the entry names stable so the backend and the smoke test find them.
const backend = "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": backend, "/demo": backend, "/health": backend },
  },
  build: {
    outDir: "../frontend",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (asset) =>
          (asset.names?.[0] ?? "").endsWith(".css") ? "assets/styles.css" : "assets/[name]-[hash][extname]",
      },
    },
  },
});

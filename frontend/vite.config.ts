import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Minimal Vite config: build the SPA into ./dist, which the staging
// Dockerfile.web copies into nginx's web root.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});

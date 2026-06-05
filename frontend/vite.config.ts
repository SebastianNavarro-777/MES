/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest config is colocated with the Vite config so unit tests and the dev
// build share a single source of truth for resolution/plugins.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Playwright specs live under tests/e2e and must not be picked up by Vitest.
    exclude: ["node_modules", "dist", "tests/e2e/**"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/tests/**",
        "src/main.tsx",
        "src/mocks/**",
        "src/**/*.d.ts",
      ],
    },
  },
});

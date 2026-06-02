/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// AC-1: dev server with HMR. AC-5: configurable backend baseURL/proxy — never
// pinned to one developer's machine; driven by env vars with a localhost default.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  // Where the Vite dev server proxies /api to. Overridable per environment.
  const proxyTarget = env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
  const devPort = Number(env.VITE_DEV_PORT ?? "5173");

  return {
    plugins: [react()],
    server: {
      port: devPort,
      proxy: {
        // The app talks to the backend through a relative /api prefix; the dev
        // server forwards it to the Django/DRF origin. CSRF cookies survive
        // because the browser sees a same-origin request.
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
    },
  };
});

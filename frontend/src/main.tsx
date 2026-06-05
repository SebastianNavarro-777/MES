import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { createQueryClient } from "./queryClient";
import "./styles/global.css";

// Enable MSW only when explicitly requested (dev / E2E), so production builds
// never ship the mock layer. The orders backend (Epic NSG-14) replaces it.
async function enableMocking(): Promise<void> {
  if (import.meta.env.VITE_ENABLE_MSW !== "true") {
    return;
  }
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

const queryClient = createQueryClient();

void enableMocking().then(() => {
  const container = document.getElementById("root");
  if (container === null) {
    throw new Error("Root container #root not found");
  }
  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  );
});

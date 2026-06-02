import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { queryClient } from "./queryClient";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Root container #root not found");
}

// AC-3: the single QueryClient is provided to the whole app here.
createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);

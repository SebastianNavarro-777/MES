import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

// Browser-side MSW worker used in dev and Playwright E2E (gated by VITE_ENABLE_MSW).
export const worker = setupWorker(...handlers);

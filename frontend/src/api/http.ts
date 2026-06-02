import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./generated/schema";
import { getCsrfToken } from "./csrf";

// HTTP methods that mutate server state and therefore require a CSRF token
// under Django's SessionAuthentication.
const MUTATING_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * AC-5: attach Django's CSRF token to mutating requests. Safe (read-only)
 * methods are left untouched.
 */
const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (MUTATING_METHODS.has(request.method.toUpperCase())) {
      const token = getCsrfToken();
      if (token !== null) {
        request.headers.set("X-CSRFToken", token);
      }
    }
    return request;
  },
};

/**
 * AC-4 / AC-5: the single typed API client for the whole app.
 *
 * - Types come from the generated OpenAPI client (`./generated/schema`); no
 *   route is hardcoded and no bespoke HTTP client is hand-written.
 * - `baseUrl` is configurable via `VITE_API_BASE_URL` and defaults to the
 *   relative `/api` prefix so the dev proxy / production reverse proxy keep
 *   requests same-origin.
 * - `credentials: "include"` sends Django's session cookie; the CSRF
 *   middleware echoes the CSRF cookie back on mutating requests. Nothing is
 *   read from or written to localStorage.
 */
const baseUrl: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

export const apiClient = createClient<paths>({
  baseUrl,
  credentials: "include",
});

apiClient.use(csrfMiddleware);

export { csrfMiddleware };

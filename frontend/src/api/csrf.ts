// AC-5: Django session auth uses a CSRF cookie. We read the token from the
// `csrftoken` cookie (set by Django) and echo it back in the `X-CSRFToken`
// header on mutating requests. Credentials are never persisted to localStorage.

const CSRF_COOKIE_NAME = "csrftoken";

/**
 * Returns the value of Django's CSRF cookie, or null if absent.
 *
 * Reads `document.cookie` rather than any client-side storage so we never
 * cache or duplicate the token — the browser remains the single source of
 * truth for both the session and the CSRF cookie.
 */
export function getCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const prefix = `${CSRF_COOKIE_NAME}=`;
  const cookies = document.cookie ? document.cookie.split("; ") : [];
  for (const cookie of cookies) {
    if (cookie.startsWith(prefix)) {
      return decodeURIComponent(cookie.slice(prefix.length));
    }
  }
  return null;
}

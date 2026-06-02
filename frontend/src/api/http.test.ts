import { afterEach, describe, expect, it } from "vitest";

import { csrfMiddleware } from "./http";

// The middleware contract from openapi-fetch: onRequest receives an object with
// a `request` field and may return a (possibly mutated) Request.
async function runMiddleware(request: Request): Promise<Request> {
  const onRequest = csrfMiddleware.onRequest;
  if (onRequest === undefined) {
    throw new Error("csrfMiddleware.onRequest is not defined");
  }
  // The extra context fields are unused by our middleware.
  const result = await onRequest({ request } as never);
  return result instanceof Request ? result : request;
}

function clearCookies(): void {
  for (const cookie of document.cookie.split("; ")) {
    const name = cookie.split("=")[0];
    if (name) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    }
  }
}

describe("csrfMiddleware", () => {
  afterEach(() => {
    clearCookies();
  });

  // AC-5: mutating requests carry the CSRF token.
  it("adds X-CSRFToken to POST requests", async () => {
    document.cookie = "csrftoken=tok-post";
    const out = await runMiddleware(new Request("https://x/api/orders/", { method: "POST" }));
    expect(out.headers.get("X-CSRFToken")).toBe("tok-post");
  });

  it.each(["PUT", "PATCH", "DELETE"])("adds X-CSRFToken to %s requests", async (method) => {
    document.cookie = "csrftoken=tok-mut";
    const out = await runMiddleware(new Request("https://x/api/orders/1/", { method }));
    expect(out.headers.get("X-CSRFToken")).toBe("tok-mut");
  });

  // AC-5: safe methods are not given a CSRF header.
  it("does not add X-CSRFToken to GET requests", async () => {
    document.cookie = "csrftoken=tok-get";
    const out = await runMiddleware(new Request("https://x/api/orders/", { method: "GET" }));
    expect(out.headers.get("X-CSRFToken")).toBeNull();
  });

  it("omits the header when no csrf cookie exists", async () => {
    const out = await runMiddleware(new Request("https://x/api/orders/", { method: "POST" }));
    expect(out.headers.get("X-CSRFToken")).toBeNull();
  });
});

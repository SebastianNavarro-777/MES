import { afterEach, describe, expect, it } from "vitest";

import { getCsrfToken } from "./csrf";

function clearCookies(): void {
  for (const cookie of document.cookie.split("; ")) {
    const name = cookie.split("=")[0];
    if (name) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    }
  }
}

describe("getCsrfToken", () => {
  afterEach(() => {
    clearCookies();
  });

  // AC-5: the CSRF token is read from Django's cookie, not from localStorage.
  it("reads the csrftoken cookie", () => {
    document.cookie = "csrftoken=abc123";
    expect(getCsrfToken()).toBe("abc123");
  });

  // AC-5: credentials are never persisted to localStorage.
  it("does not read or write localStorage", () => {
    document.cookie = "csrftoken=fromcookie";
    getCsrfToken();
    expect(localStorage.getItem("csrftoken")).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("returns null when the cookie is absent", () => {
    expect(getCsrfToken()).toBeNull();
  });

  it("picks csrftoken out of multiple cookies", () => {
    document.cookie = "sessionid=xyz";
    document.cookie = "csrftoken=tok";
    expect(getCsrfToken()).toBe("tok");
  });
});

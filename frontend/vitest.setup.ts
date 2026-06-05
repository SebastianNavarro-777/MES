import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./src/mocks/server";
import { resetOrdersStore } from "./src/mocks/handlers";

// Start the MSW request interceptor once for the whole unit-test run.
// `onUnhandledRequest: "error"` surfaces any request we forgot to mock.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  resetOrdersStore();
  cleanup();
});
afterAll(() => server.close());

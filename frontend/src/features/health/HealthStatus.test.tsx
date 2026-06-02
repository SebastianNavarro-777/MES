import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/http";
import { HealthStatus } from "./HealthStatus";

const getSpy = vi.spyOn(apiClient, "GET");

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  getSpy.mockReset();
});

// AC-3: the example query renders distinct loading, success and error states.
describe("HealthStatus", () => {
  it("shows the loading state while the query is pending", () => {
    getSpy.mockReturnValue(new Promise(() => {}) as never);
    renderWithClient(<HealthStatus />);
    expect(screen.getByTestId("health-loading")).toBeInTheDocument();
  });

  it("shows the success state when the backend responds", async () => {
    getSpy.mockResolvedValue({ data: { status: "ok" }, error: undefined } as never);
    renderWithClient(<HealthStatus />);
    await waitFor(() => expect(screen.getByTestId("health-success")).toBeInTheDocument());
    expect(screen.getByTestId("health-success")).toHaveTextContent("healthy");
  });

  it("shows the error state when the query fails", async () => {
    getSpy.mockResolvedValue({ data: undefined, error: { detail: "boom" } } as never);
    renderWithClient(<HealthStatus />);
    await waitFor(() => expect(screen.getByTestId("health-error")).toBeInTheDocument());
  });
});

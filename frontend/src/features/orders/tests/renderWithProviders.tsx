import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";

/** Render a component at the order-detail route with isolated query state. */
export function renderAtOrderRoute(
  orderId: string,
  element: ReactElement,
): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/orders/${orderId}`]}>
        <Routes>
          <Route path="/orders/:orderId" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { API_BASE } from "../../../api/client";
import { server } from "../../../mocks/server";
import { WipPanel } from "../WipPanel";

function renderWithQuery(element: ReactElement): void {
  const queryClient = new QueryClient({
    // The hook owns its retry policy (don't retry 4xx, retry 5xx/transient).
    // Collapse the backoff to 0 so the error-then-recover path resolves fast
    // in tests instead of waiting on real exponential backoff.
    defaultOptions: { queries: { retryDelay: 0 } },
  });
  render(
    <QueryClientProvider client={queryClient}>{element}</QueryClientProvider>,
  );
}

describe("WipPanel", () => {
  it("lists the WIP balance per route step for the order", async () => {
    // AC-1: el panel muestra los balances de WIP por paso de ruta (route_step,
    // qty_in, qty_out, qty_scrap y el balance neto) de la OF.
    renderWithQuery(<WipPanel orderId="OF-2002" />);

    const table = await screen.findByTestId("wip-table");
    expect(table).toBeInTheDocument();

    // Three seeded route steps for OF-2002.
    expect(screen.getByTestId("wip-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("wip-row-2")).toBeInTheDocument();
    expect(screen.getByTestId("wip-row-3")).toBeInTheDocument();

    // Step 2 figures (qty_in 250, qty_out 200, qty_scrap 5, balance 45).
    const step2 = screen.getByTestId("wip-row-2");
    expect(step2).toHaveTextContent("Paso 2");
    expect(step2).toHaveTextContent("250");
    expect(step2).toHaveTextContent("200");
    expect(step2).toHaveTextContent("5");
    expect(step2).toHaveTextContent("45");
  });

  it("requests the wip-context read URL filtered by order_id (ADR 0004)", async () => {
    // AC-1: el contrato consumido es GET /api/v1/wip/positions/?order_id={id}
    // (no /api/v1/orders/{id}/wip/), preservando la frontera de contextos.
    let requestedUrl: string | null = null;
    server.use(
      http.get(`${API_BASE}/wip/positions/`, ({ request }) => {
        requestedUrl = request.url;
        return HttpResponse.json([]);
      }),
    );

    renderWithQuery(<WipPanel orderId="OF-2002" />);

    await waitFor(() => expect(requestedUrl).not.toBeNull());
    const url = new URL(requestedUrl as unknown as string);
    expect(url.pathname).toBe(`${API_BASE}/wip/positions/`);
    expect(url.searchParams.get("order_id")).toBe("OF-2002");
  });

  it("shows a loading state while the balances are being fetched", () => {
    // AC-2: mientras se cargan los balances, el panel muestra un estado de carga.
    renderWithQuery(<WipPanel orderId="OF-2002" />);

    // First render is pending before the mocked response resolves.
    expect(screen.getByRole("status")).toHaveTextContent(
      "Cargando balances de WIP",
    );
  });

  it("shows a clear empty state (no error) when the order has no positions", async () => {
    // AC-3: si la OF no tiene posiciones WIP el API responde 200 con [] (nunca
    // 404) y el panel muestra un estado vacío claro, no un error.
    renderWithQuery(<WipPanel orderId="OF-1001" />);

    expect(await screen.findByTestId("wip-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("wip-error")).toBeNull();
    expect(screen.queryByTestId("wip-table")).toBeNull();
  });

  it("shows a readable error with retry when the fetch fails, then recovers", async () => {
    // AC-4: ante un fallo de carga el panel muestra un error legible con la
    // opción de reintentar; al reintentar con éxito se muestran los balances.
    server.use(
      http.get(`${API_BASE}/wip/positions/`, () =>
        HttpResponse.json(
          { type: "about:blank", title: "boom", status: 500 },
          { status: 500 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithQuery(<WipPanel orderId="OF-2002" />);

    expect(await screen.findByTestId("wip-error")).toBeInTheDocument();
    expect(
      screen.getByText("No se pudieron cargar los balances de WIP"),
    ).toBeInTheDocument();

    // Recovery: the endpoint heals and the operator retries.
    server.use(
      http.get(`${API_BASE}/wip/positions/`, () =>
        HttpResponse.json([
          { order_id: "OF-2002", route_step: 1, qty_in: 10, qty_out: 4, qty_scrap: 1, balance: 5 },
        ]),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByTestId("wip-table")).toBeInTheDocument();
    expect(screen.queryByTestId("wip-error")).toBeNull();
  });

  it("renders the API-provided net balance verbatim (never recomputed)", async () => {
    // AC-5: el balance mostrado es exactamente el que devuelve el API (lo calcula
    // el dominio de wip). Se usa un valor deliberadamente distinto de
    // qty_in - qty_out - qty_scrap para probar que el frontend no recalcula.
    server.use(
      http.get(`${API_BASE}/wip/positions/`, () =>
        HttpResponse.json([
          // Naive formula would be 100 - 30 - 10 = 60, but the domain says 999.
          { order_id: "OF-2002", route_step: 1, qty_in: 100, qty_out: 30, qty_scrap: 10, balance: 999 },
        ]),
      ),
    );
    renderWithQuery(<WipPanel orderId="OF-2002" />);

    const row = await screen.findByTestId("wip-row-1");
    expect(row).toHaveTextContent("999");
    expect(row).not.toHaveTextContent("60");
  });
});

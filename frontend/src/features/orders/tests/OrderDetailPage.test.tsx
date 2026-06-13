import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { API_BASE } from "../../../api/client";
import { server } from "../../../mocks/server";
import { OrderDetailPage } from "../OrderDetailPage";
import { renderAtOrderRoute } from "./renderWithProviders";

function renderOrder(orderId: string): void {
  renderAtOrderRoute(orderId, <OrderDetailPage />);
}

describe("OrderDetailPage", () => {
  it("shows the order's data when navigating to an existing order", async () => {
    // AC-1: Al navegar a la ruta de detalle de una OF existente, la pantalla
    // muestra los datos de la orden: identificador, producto, cantidad, ruta
    // (routing), fecha compromiso (due date) y estado actual.
    renderOrder("OF-1001");

    expect(
      await screen.findByRole("heading", { name: "OF-1001" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Soporte de aluminio A")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("RUTA-ESTÁNDAR")).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();
    expect(screen.getByText("Borrador")).toBeInTheDocument();
  });

  it("offers only the valid transition for the current state", async () => {
    // AC-2: La pantalla ofrece únicamente las transiciones de estado válidas
    // desde el estado actual; las transiciones no permitidas no se muestran.
    renderOrder("OF-1001"); // draft → only "Liberar" (released)

    expect(await screen.findByTestId("transition-released")).toBeInTheDocument();
    expect(screen.queryByTestId("transition-in_progress")).toBeNull();
    expect(screen.queryByTestId("transition-completed")).toBeNull();
    expect(screen.queryByTestId("transition-closed")).toBeNull();
  });

  it("shows no transitions for a terminal (closed) order", async () => {
    // AC-2: el estado terminal no ofrece ninguna transición disponible.
    renderOrder("OF-3003"); // closed

    expect(await screen.findByText("Cerrada")).toBeInTheDocument();
    expect(screen.queryByTestId("transition-released")).toBeNull();
    expect(
      screen.getByText(/No hay cambios de estado disponibles/),
    ).toBeInTheDocument();
  });

  it("opens a confirmation modal showing source and destination states", async () => {
    // AC-3: Al elegir una transición, se abre un modal de confirmación que
    // indica el estado origen y el estado destino y exige confirmación explícita.
    const user = userEvent.setup();
    renderOrder("OF-1001");

    await user.click(await screen.findByTestId("transition-released"));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("Estado actual")).toBeInTheDocument();
    expect(screen.getByText("Nuevo estado")).toBeInTheDocument();
    // Both origin (Borrador) and destination (Liberada) are shown.
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Liberada").length).toBeGreaterThan(0);
    expect(screen.getByTestId("confirm-transition")).toBeInTheDocument();
  });

  it("reflects the new state after a successful transition without reload", async () => {
    // AC-4: Al confirmar, tras la respuesta exitosa del API la pantalla refleja
    // el nuevo estado de la OF y las nuevas transiciones disponibles, sin
    // necesidad de recargar la página manualmente.
    const user = userEvent.setup();
    renderOrder("OF-1001");

    await user.click(await screen.findByTestId("transition-released"));
    await user.click(await screen.findByTestId("confirm-transition"));

    // Header pill now shows the new state and the next transition appears.
    expect(await screen.findByText("Liberada")).toBeInTheDocument();
    expect(
      await screen.findByTestId("transition-in_progress"),
    ).toBeInTheDocument();
    // Modal closed.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows a readable error and keeps the state when the API rejects (conflict)", async () => {
    // AC-5: Si el API rechaza la transición (transición inválida, conflicto de
    // estado, error de red), la pantalla muestra un mensaje de error legible y
    // la OF conserva su estado anterior sin cambios.
    server.use(
      http.post(`${API_BASE}/orders/:orderId/transition/`, () =>
        HttpResponse.json(
          {
            type: "https://nsg.mx/problems/orders/invalid-transition",
            title: "Invalid order transition",
            status: 409,
            detail: "state conflict",
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderOrder("OF-1001");

    await user.click(await screen.findByTestId("transition-released"));
    await user.click(await screen.findByTestId("confirm-transition"));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // State unchanged: still draft, modal still open.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Estado actual")).toBeInTheDocument();
  });

  it("shows a readable error on a network failure and keeps the state", async () => {
    // AC-5: error de red — mensaje legible y la OF conserva su estado.
    server.use(
      http.post(`${API_BASE}/orders/:orderId/transition/`, () =>
        HttpResponse.error(),
      ),
    );
    const user = userEvent.setup();
    renderOrder("OF-1001");

    await user.click(await screen.findByTestId("transition-released"));
    await user.click(await screen.findByTestId("confirm-transition"));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("does not transition when the modal is cancelled", async () => {
    // AC-6: Al cancelar o cerrar el modal, no se ejecuta ninguna transición y
    // la OF mantiene su estado actual.
    const user = userEvent.setup();
    renderOrder("OF-1001");

    await user.click(await screen.findByTestId("transition-released"));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Still draft.
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(screen.queryByTestId("transition-in_progress")).toBeNull();
  });

  it("closes the modal without transitioning when ESC is pressed", async () => {
    // AC-6: cerrar el modal (ESC) tampoco ejecuta la transición.
    const user = userEvent.setup();
    renderOrder("OF-1001");

    await user.click(await screen.findByTestId("transition-released"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("Borrador")).toBeInTheDocument();
  });

  it("shows a clear not-found state for a missing order", async () => {
    // AC-7: Si la OF no existe o el id es inválido, la pantalla muestra un
    // estado de "no encontrada" claro, en lugar de un error genérico.
    renderOrder("OF-9999");

    expect(await screen.findByTestId("order-not-found")).toBeInTheDocument();
    expect(screen.getByText("Orden no encontrada")).toBeInTheDocument();
  });
});

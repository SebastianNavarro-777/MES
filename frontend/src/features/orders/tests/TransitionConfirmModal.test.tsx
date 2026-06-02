import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderStatus } from "../orderStatus";
import { TransitionConfirmModal } from "../TransitionConfirmModal";

function renderModal(
  overrides: Partial<Parameters<typeof TransitionConfirmModal>[0]> = {},
) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <TransitionConfirmModal
      fromStatus={OrderStatus.Draft}
      toStatus={OrderStatus.Released}
      isSubmitting={false}
      errorMessage={null}
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { onConfirm, onCancel };
}

describe("TransitionConfirmModal", () => {
  it("shows source and destination states and requires explicit confirmation", () => {
    // AC-3: el modal indica el estado origen y el estado destino y exige
    // confirmación explícita antes de ejecutar.
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Estado actual")).toBeInTheDocument();
    expect(screen.getByText("Nuevo estado")).toBeInTheDocument();
    // Origin (Borrador) and destination (Liberada) are both shown.
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Liberada").length).toBeGreaterThan(0);
    expect(screen.getByTestId("confirm-transition")).toHaveTextContent(
      "Liberar",
    );
  });

  it("invokes onConfirm only when the primary button is pressed", async () => {
    // AC-3: solo el botón primario confirma.
    const user = userEvent.setup();
    const { onConfirm } = renderModal();
    await user.click(screen.getByTestId("confirm-transition"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("cancels via the Cancel button, the overlay and the ESC key", async () => {
    // AC-6: cancelar o cerrar el modal no ejecuta ninguna transición.
    const user = userEvent.setup();
    const { onConfirm, onCancel } = renderModal();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    await user.click(screen.getByTestId("transition-modal-overlay"));
    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(3);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders a readable error message when the transition fails", () => {
    // AC-5: mensaje de error legible para el operador dentro del modal.
    renderModal({ errorMessage: "No se pudo cambiar el estado de la orden." });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se pudo cambiar el estado de la orden.",
    );
  });
});

import { useEffect, useId, useRef } from "react";
import {
  ORDER_STATUS_PRESENTATION,
  ORDER_TRANSITION_ACTION,
  messages,
} from "../../i18n/es-MX";
import type { OrderStatusValue } from "./orderStatus";
import { StatusPill } from "./StatusPill";
import "./TransitionConfirmModal.css";

interface TransitionConfirmModalProps {
  readonly fromStatus: OrderStatusValue;
  readonly toStatus: OrderStatusValue;
  readonly isSubmitting: boolean;
  readonly errorMessage: string | null;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/**
 * Confirmation modal for a state transition (docs/ui-design.md "Confirmation
 * modal"). Shows origin → destination explicitly, requires the primary button
 * to confirm, and treats ESC / overlay click / Cancel as a no-op cancel (AC-6).
 */
export function TransitionConfirmModal({
  fromStatus,
  toStatus,
  isSubmitting,
  errorMessage,
  onConfirm,
  onCancel,
}: TransitionConfirmModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const actionVerb = ORDER_TRANSITION_ACTION[toStatus];

  useEffect(() => {
    dialogRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onCancel();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  return (
    <div
      className="modal-overlay"
      data-testid="transition-modal-overlay"
      onClick={onCancel}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId} className="modal__title">
          {messages.modal.titlePrefix} {actionVerb.toLowerCase()}
        </h2>

        <div className="modal__transition">
          <div className="modal__state">
            <span className="modal__state-label">{messages.modal.from}</span>
            <StatusPill status={fromStatus} />
          </div>
          <span className="modal__arrow" aria-hidden="true">
            →
          </span>
          <div className="modal__state">
            <span className="modal__state-label">{messages.modal.to}</span>
            <StatusPill status={toStatus} />
          </div>
        </div>

        <p className="modal__summary">
          La orden cambiará de{" "}
          <strong>{ORDER_STATUS_PRESENTATION[fromStatus].label}</strong> a{" "}
          <strong>{ORDER_STATUS_PRESENTATION[toStatus].label}</strong>.
        </p>

        {errorMessage !== null && (
          <p className="modal__error" role="alert">
            ⚠ {errorMessage}
          </p>
        )}

        <div className="modal__actions">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={onCancel}
          >
            {messages.modal.cancel}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={onConfirm}
            disabled={isSubmitting}
            data-testid="confirm-transition"
          >
            {actionVerb}
          </button>
        </div>
      </div>
    </div>
  );
}
